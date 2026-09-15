"""Indexed access to the application's fixed seven-file master dictionary.

The original dictionary assets are never modified.  They are streamed into a
small SQLite index in the application cache directory, then Step 2 performs
targeted exact queries only for Han fragments found in the working novel.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from config.settings import config_dir

from .detector import chinese_segments, has_han, is_han


INDEX_VERSION = "2"
MAX_RULE_CAPTURE = 80
SQLITE_BATCH = 800

REQUIRED_FILES: Tuple[str, ...] = (
    "ChinesePhienAmWords.txt",
    "LuatNhan.txt",
    "Names.txt",
    "QualityOverrides.txt",
    "VietPhrase_1.txt",
    "VietPhrase_2.txt",
    "dict-default.json",
)

SOURCE_LABELS: Dict[str, str] = {
    "QualityOverrides.txt": "QualityOverrides",
    "Names.txt": "Names",
    "VietPhrase_1.txt": "VietPhrase_1",
    "VietPhrase_2.txt": "VietPhrase_2",
    "ChinesePhienAmWords.txt": "ChinesePhienAmWords",
    "dict-default.json": "dict-default",
    "LuatNhan.txt": "LuatNhan",
}

SOURCE_DISPLAY_ORDER = {
    "QualityOverrides": 0,
    "Names": 1,
    "VietPhrase_1": 2,
    "VietPhrase_2": 3,
    "ChinesePhienAmWords": 4,
    "dict-default": 5,
    "LuatNhan": 6,
    "Phonetic": 7,
}


class MasterDictionaryError(RuntimeError):
    """Raised when the fixed dictionary assets or their index are unusable."""


@dataclass(frozen=True)
class MasterSuggestion:
    value: str
    sources: Tuple[str, ...]
    raw_values: Tuple[str, ...] = ()
    kind: str = "exact"  # exact | rule | phonetic
    rule: str = ""
    replacement_start: Optional[int] = None
    replacement_end: Optional[int] = None

    @property
    def source_label(self) -> str:
        return ", ".join(self.sources)

    @property
    def display_text(self) -> str:
        label = self.source_label
        return f"{self.value} — {label}" if label else self.value


@dataclass(frozen=True)
class ExactMatch:
    text: str
    start: int
    end: int
    suggestions: Tuple[MasterSuggestion, ...]


@dataclass
class DictionaryHealth:
    files: Dict[str, int] = field(default_factory=dict)
    malformed_rows: Dict[str, int] = field(default_factory=dict)
    indexed_entries: int = 0
    indexed_rules: int = 0
    indexed_phonetics: int = 0
    rebuilt: bool = False

    def warning_summary(self) -> str:
        total = sum(self.malformed_rows.values())
        return f"Skipped {total} malformed dictionary rows." if total else ""


def default_dictionary_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "dictionary"


def default_index_path() -> Path:
    return config_dir() / "cache" / "master_dictionary_v1.sqlite3"


def _fingerprint(root: Path) -> str:
    records = []
    for name in REQUIRED_FILES:
        path = root / name
        if not path.is_file():
            raise MasterDictionaryError(f"Required dictionary file is missing: {path}")
        try:
            stat = path.stat()
        except OSError as error:
            raise MasterDictionaryError(f"Cannot inspect dictionary file {path}: {error}") from error
        records.append((name, stat.st_size, stat.st_mtime_ns))
    return json.dumps(records, ensure_ascii=False, separators=(",", ":"))


def _split_variants(raw_value: str) -> List[str]:
    """Split native slash alternatives without losing their raw source value."""
    value = raw_value.split("\t", 1)[0].strip()
    variants: List[str] = []
    for item in value.split("/"):
        item = item.strip()
        if item and item not in variants:
            variants.append(item)
    return variants


def _iter_native_pairs(path: Path) -> Iterator[Tuple[int, str, str]]:
    try:
        handle = path.open("r", encoding="utf-8-sig")
    except (OSError, UnicodeError) as error:
        raise MasterDictionaryError(f"Cannot read dictionary file {path}: {error}") from error
    with handle:
        for line_number, raw in enumerate(handle, 1):
            line = raw.rstrip("\r\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if "=" not in line:
                yield line_number, "", ""
                continue
            key, value = line.split("=", 1)
            yield line_number, key.strip().lstrip("\ufeff"), value.strip()


def _han_anchor(text: str) -> str:
    segments = chinese_segments(text.replace("{0}", ""))
    if not segments:
        return ""
    return max((segment.text for segment in segments), key=lambda item: (len(item), item))


class MasterDictionary:
    """Read-only query facade over a derived SQLite dictionary index."""

    def __init__(
        self,
        dictionary_dir: Optional[Path] = None,
        index_path: Optional[Path] = None,
    ) -> None:
        self.dictionary_dir = Path(dictionary_dir) if dictionary_dir else default_dictionary_dir()
        self.index_path = Path(index_path) if index_path else default_index_path()
        self.health = DictionaryHealth()
        self._connection: Optional[sqlite3.Connection] = None
        self._max_exact_length = 1
        self._max_rule_anchor_length = 1

    # --------------------------------------------------------------- setup
    def ensure_ready(self) -> DictionaryHealth:
        self.health.rebuilt = False
        fingerprint = _fingerprint(self.dictionary_dir)
        if not self._index_matches(fingerprint):
            # Windows cannot atomically replace a database while this process
            # still has the previous generation open.
            self.close()
            self._build_index(fingerprint)
            self.health.rebuilt = True
        self.close()
        try:
            connection = sqlite3.connect(str(self.index_path))
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only = ON")
            self._connection = connection
            self._max_exact_length = int(self._meta("max_exact_length") or 1)
            self._max_rule_anchor_length = int(self._meta("max_rule_anchor_length") or 1)
            self.health.indexed_entries = int(self._meta("entry_count") or 0)
            self.health.indexed_rules = int(self._meta("rule_count") or 0)
            self.health.indexed_phonetics = int(self._meta("phonetic_count") or 0)
            malformed = self._meta("malformed_rows") or "{}"
            self.health.malformed_rows = json.loads(malformed)
        except (OSError, sqlite3.Error, ValueError, json.JSONDecodeError) as error:
            self.close()
            raise MasterDictionaryError(f"Cannot open master dictionary index: {error}") from error
        return self.health

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def _connect(self) -> sqlite3.Connection:
        if self._connection is None:
            self.ensure_ready()
        assert self._connection is not None
        return self._connection

    def _meta(self, key: str) -> Optional[str]:
        assert self._connection is not None
        row = self._connection.execute("SELECT value FROM metadata WHERE key = ?", (key,)).fetchone()
        return str(row[0]) if row else None

    def _index_matches(self, fingerprint: str) -> bool:
        if not self.index_path.is_file():
            return False
        try:
            connection = sqlite3.connect(str(self.index_path))
            rows = dict(connection.execute("SELECT key, value FROM metadata"))
            connection.close()
            return rows.get("version") == INDEX_VERSION and rows.get("fingerprint") == fingerprint
        except sqlite3.Error:
            return False

    def _build_index(self, fingerprint: str) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            prefix="master_dictionary_", suffix=".sqlite3", dir=self.index_path.parent, delete=False
        )
        temp_path = Path(handle.name)
        handle.close()
        malformed: Dict[str, int] = {}
        usable: Dict[str, int] = {}
        max_exact = 1
        max_anchor = 1
        connection: Optional[sqlite3.Connection] = None
        try:
            connection = sqlite3.connect(str(temp_path))
            connection.executescript(
                """
                PRAGMA journal_mode = OFF;
                PRAGMA synchronous = OFF;
                PRAGMA temp_store = MEMORY;
                CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE entries (
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    source TEXT NOT NULL,
                    raw_value TEXT NOT NULL,
                    source_line INTEGER NOT NULL,
                    variant_order INTEGER NOT NULL,
                    UNIQUE(key, value, source, raw_value)
                );
                CREATE INDEX entries_key_idx ON entries(key);
                CREATE TABLE phonetics (
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    source TEXT NOT NULL,
                    raw_value TEXT NOT NULL,
                    source_line INTEGER NOT NULL,
                    variant_order INTEGER NOT NULL,
                    UNIQUE(key, value, source, raw_value)
                );
                CREATE INDEX phonetics_key_idx ON phonetics(key);
                CREATE TABLE rules (
                    pattern TEXT NOT NULL,
                    value TEXT NOT NULL,
                    source TEXT NOT NULL,
                    raw_value TEXT NOT NULL,
                    source_line INTEGER NOT NULL,
                    variant_order INTEGER NOT NULL,
                    prefix TEXT NOT NULL,
                    suffix TEXT NOT NULL,
                    anchor TEXT NOT NULL,
                    specificity INTEGER NOT NULL,
                    UNIQUE(pattern, value, raw_value)
                );
                CREATE INDEX rules_anchor_idx ON rules(anchor);
                """
            )

            exact_files = (
                "Names.txt",
                "QualityOverrides.txt",
                "VietPhrase_1.txt",
                "VietPhrase_2.txt",
            )
            for name in exact_files:
                count, bad, longest = self._load_pair_file(
                    connection, self.dictionary_dir / name, SOURCE_LABELS[name], "entries"
                )
                usable[name], malformed[name] = count, bad
                max_exact = max(max_exact, longest)

            for name in ("ChinesePhienAmWords.txt",):
                count, bad, _longest = self._load_pair_file(
                    connection, self.dictionary_dir / name, SOURCE_LABELS[name], "phonetics",
                    single_han_only=True,
                )
                usable[name], malformed[name] = count, bad

            name = "LuatNhan.txt"
            count, bad, max_anchor = self._load_rules(
                connection, self.dictionary_dir / name, SOURCE_LABELS[name]
            )
            usable[name], malformed[name] = count, bad

            name = "dict-default.json"
            count, bad = self._load_json_phonetics(
                connection, self.dictionary_dir / name, SOURCE_LABELS[name]
            )
            usable[name], malformed[name] = count, bad

            empty = [name for name in REQUIRED_FILES if usable.get(name, 0) <= 0]
            if empty:
                raise MasterDictionaryError(
                    "Dictionary files contain no usable records: " + ", ".join(empty)
                )

            counts = {
                "entry_count": connection.execute("SELECT COUNT(*) FROM entries").fetchone()[0],
                "rule_count": connection.execute("SELECT COUNT(*) FROM rules").fetchone()[0],
                "phonetic_count": connection.execute("SELECT COUNT(*) FROM phonetics").fetchone()[0],
            }
            metadata = {
                "version": INDEX_VERSION,
                "fingerprint": fingerprint,
                "max_exact_length": str(max_exact),
                "max_rule_anchor_length": str(max_anchor),
                "malformed_rows": json.dumps(malformed, ensure_ascii=False),
                **{key: str(value) for key, value in counts.items()},
            }
            connection.executemany("INSERT INTO metadata(key, value) VALUES (?, ?)", metadata.items())
            connection.commit()
            connection.close()
            connection = None
            os.replace(temp_path, self.index_path)
            self.health.files = usable
            self.health.malformed_rows = malformed
        except (OSError, UnicodeError, sqlite3.Error, ValueError, json.JSONDecodeError) as error:
            if connection is not None:
                connection.close()
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            if isinstance(error, MasterDictionaryError):
                raise
            raise MasterDictionaryError(f"Cannot build master dictionary index: {error}") from error
        except MasterDictionaryError:
            if connection is not None:
                connection.close()
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def _load_pair_file(
        self,
        connection: sqlite3.Connection,
        path: Path,
        source: str,
        table: str,
        *,
        single_han_only: bool = False,
    ) -> Tuple[int, int, int]:
        rows: List[Tuple[str, str, str, str, int, int]] = []
        count = bad = 0
        longest = 1
        for line_number, key, raw_value in _iter_native_pairs(path):
            if not key or not raw_value:
                bad += 1
                continue
            if single_han_only and not (len(key) == 1 and is_han(key)):
                continue
            if not single_han_only and not has_han(key):
                continue
            variants = _split_variants(raw_value)
            if not variants:
                bad += 1
                continue
            longest = max(longest, len(key))
            for variant_order, value in enumerate(variants):
                rows.append((key, value, source, raw_value, line_number, variant_order))
            count += 1
            if len(rows) >= 5000:
                connection.executemany(
                    f"INSERT OR IGNORE INTO {table}(key,value,source,raw_value,source_line,variant_order) VALUES (?,?,?,?,?,?)",
                    rows,
                )
                rows.clear()
        if rows:
            connection.executemany(
                f"INSERT OR IGNORE INTO {table}(key,value,source,raw_value,source_line,variant_order) VALUES (?,?,?,?,?,?)",
                rows,
            )
        return count, bad, longest

    def _load_rules(
        self, connection: sqlite3.Connection, path: Path, source: str
    ) -> Tuple[int, int, int]:
        rows: List[Tuple[str, str, str, str, int, int, str, str, str, int]] = []
        count = bad = 0
        max_anchor = 1
        for line_number, pattern, raw_value in _iter_native_pairs(path):
            if not pattern or not raw_value or pattern.count("{0}") != 1:
                bad += 1
                continue
            variants = _split_variants(raw_value)
            if not variants:
                bad += 1
                continue
            prefix, suffix = pattern.split("{0}", 1)
            anchor = _han_anchor(pattern)
            if not anchor:
                bad += 1
                continue
            specificity = len(prefix) + len(suffix)
            max_anchor = max(max_anchor, len(anchor))
            for variant_order, value in enumerate(variants):
                rows.append(
                    (pattern, value, source, raw_value, line_number, variant_order, prefix, suffix, anchor, specificity)
                )
            count += 1
            if len(rows) >= 5000:
                connection.executemany(
                    "INSERT OR IGNORE INTO rules(pattern,value,source,raw_value,source_line,variant_order,prefix,suffix,anchor,specificity) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    rows,
                )
                rows.clear()
        if rows:
            connection.executemany(
                "INSERT OR IGNORE INTO rules(pattern,value,source,raw_value,source_line,variant_order,prefix,suffix,anchor,specificity) VALUES (?,?,?,?,?,?,?,?,?,?)",
                rows,
            )
        return count, bad, max_anchor

    def _load_json_phonetics(
        self, connection: sqlite3.Connection, path: Path, source: str
    ) -> Tuple[int, int]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise MasterDictionaryError(f"Invalid dictionary JSON {path}: {error}") from error
        phonetics = payload.get("phienam") if isinstance(payload, dict) else None
        if not isinstance(phonetics, dict):
            raise MasterDictionaryError(f"Invalid dictionary JSON {path}: missing object 'phienam'.")
        rows = []
        bad = 0
        for line_number, (raw_key, raw_value) in enumerate(phonetics.items(), 1):
            key = str(raw_key).strip().lstrip("\ufeff")
            value = str(raw_value).strip()
            if len(key) != 1 or not is_han(key) or not value:
                bad += 1
                continue
            rows.append((key, value, source, value, line_number, 0))
        connection.executemany(
            "INSERT OR IGNORE INTO phonetics(key,value,source,raw_value,source_line,variant_order) VALUES (?,?,?,?,?,?)",
            rows,
        )
        return len(rows), bad

    # ------------------------------------------------------------- queries
    @staticmethod
    def _chunks(items: Sequence[str], size: int = SQLITE_BATCH) -> Iterator[Sequence[str]]:
        for index in range(0, len(items), size):
            yield items[index:index + size]

    def _query_rows(self, table: str, column: str, values: Sequence[str]) -> List[sqlite3.Row]:
        if not values:
            return []
        connection = self._connect()
        rows: List[sqlite3.Row] = []
        for batch in self._chunks(list(dict.fromkeys(values))):
            placeholders = ",".join("?" for _ in batch)
            rows.extend(
                connection.execute(
                    f"SELECT * FROM {table} WHERE {column} IN ({placeholders})", tuple(batch)
                ).fetchall()
            )
        return rows

    @staticmethod
    def _aggregate(rows: Iterable[sqlite3.Row], *, kind: str) -> Tuple[MasterSuggestion, ...]:
        values: Dict[str, Dict[str, List[str]]] = {}
        for row in rows:
            value = str(row["value"]).strip()
            if not value:
                continue
            bucket = values.setdefault(value, {"sources": [], "raw": [], "order": []})
            source = str(row["source"])
            raw = str(row["raw_value"])
            if source not in bucket["sources"]:
                bucket["sources"].append(source)
            if raw not in bucket["raw"]:
                bucket["raw"].append(raw)
            bucket["order"].append(
                (
                    SOURCE_DISPLAY_ORDER.get(source, 99),
                    int(row["source_line"]),
                    int(row["variant_order"]),
                )
            )
        suggestions = [
            MasterSuggestion(
                value=value,
                sources=tuple(sorted(data["sources"], key=lambda item: (SOURCE_DISPLAY_ORDER.get(item, 99), item))),
                raw_values=tuple(data["raw"]),
                kind=kind,
            )
            for value, data in values.items()
        ]
        suggestions.sort(
            key=lambda item: (
                min((SOURCE_DISPLAY_ORDER.get(source, 99) for source in item.sources), default=99),
                min(values[item.value]["order"]),
            )
        )
        return tuple(suggestions)

    def lookup_exact(self, key: str) -> Tuple[MasterSuggestion, ...]:
        rows = self._query_rows("entries", "key", [key])
        return self._aggregate(rows, kind="exact")

    def longest_exact_matches(self, run: str) -> List[ExactMatch]:
        if not run:
            return []
        self._connect()
        max_length = min(self._max_exact_length, len(run))
        candidates = {
            run[start:start + length]
            for start in range(len(run))
            for length in range(1, min(max_length, len(run) - start) + 1)
        }
        rows = self._query_rows("entries", "key", list(candidates))
        by_key: Dict[str, List[sqlite3.Row]] = {}
        for row in rows:
            by_key.setdefault(str(row["key"]), []).append(row)

        matches: List[ExactMatch] = []
        cursor = 0
        while cursor < len(run):
            matched = ""
            for length in range(min(max_length, len(run) - cursor), 0, -1):
                candidate = run[cursor:cursor + length]
                if candidate in by_key:
                    matched = candidate
                    break
            if not matched:
                cursor += 1
                continue
            matches.append(
                ExactMatch(
                    text=matched,
                    start=cursor,
                    end=cursor + len(matched),
                    suggestions=self._aggregate(by_key[matched], kind="exact"),
                )
            )
            cursor += len(matched)
        return matches

    def phonetic_suggestions(self, text: str) -> Tuple[MasterSuggestion, ...]:
        if not text or not all(is_han(char) for char in text):
            return ()
        rows = self._query_rows("phonetics", "key", list(text))
        by_key: Dict[str, List[sqlite3.Row]] = {}
        for row in rows:
            by_key.setdefault(str(row["key"]), []).append(row)
        if any(char not in by_key for char in text):
            return ()

        combinations: List[Tuple[str, Tuple[str, ...], Tuple[str, ...]]] = [("", (), ())]
        for char in text:
            options = self._aggregate(by_key[char], kind="phonetic")
            next_values: List[Tuple[str, Tuple[str, ...], Tuple[str, ...]]] = []
            for prefix, sources, raw_values in combinations:
                for option in options[:4]:
                    value = f"{prefix} {option.value}".strip()
                    merged_sources = tuple(dict.fromkeys((*sources, *option.sources)))
                    merged_raw = tuple(dict.fromkeys((*raw_values, *option.raw_values)))
                    next_values.append((value, merged_sources, merged_raw))
                    if len(next_values) >= 16:
                        break
                if len(next_values) >= 16:
                    break
            combinations = next_values
        unique: Dict[str, MasterSuggestion] = {}
        for value, sources, raw_values in combinations:
            unique.setdefault(
                value,
                MasterSuggestion(value, sources, raw_values, kind="phonetic"),
            )
        return tuple(unique.values())

    def rule_suggestions(
        self,
        sentence: str,
        fragment_start: int,
        fragment_end: int,
        *,
        blocked_spans: Sequence[Tuple[int, int]] = (),
    ) -> Tuple[MasterSuggestion, ...]:
        self._connect()
        runs = chinese_segments(sentence)
        anchors = {
            segment.text[start:start + length]
            for segment in runs
            for start in range(len(segment.text))
            for length in range(1, min(self._max_rule_anchor_length, len(segment.text) - start) + 1)
        }
        rows = self._query_rows("rules", "anchor", list(anchors))
        matches: List[Tuple[int, sqlite3.Row, re.Match[str], str]] = []
        for row in rows:
            prefix = str(row["prefix"])
            suffix = str(row["suffix"])
            pattern = re.compile(
                re.escape(prefix) + rf"(?P<capture>[^\n]{{0,{MAX_RULE_CAPTURE}}}?)" + re.escape(suffix)
            )
            for match in pattern.finditer(sentence):
                if match.end() <= fragment_start or match.start() >= fragment_end:
                    continue
                if any(match.start() < end and match.end() > start for start, end in blocked_spans):
                    continue
                capture = match.group("capture")
                rendered = str(row["value"]).replace("{0}", capture).strip()
                if rendered:
                    matches.append((int(row["specificity"]), row, match, rendered))
        if not matches:
            return ()
        highest = max(item[0] for item in matches)
        best = [item for item in matches if item[0] == highest]
        values: Dict[Tuple[str, int, int], Dict[str, list]] = {}
        rules: Dict[Tuple[str, int, int], str] = {}
        for _specificity, row, match, rendered in best:
            key = (rendered, match.start(), match.end())
            bucket = values.setdefault(key, {"sources": [], "raw": [], "order": []})
            source = str(row["source"])
            raw = str(row["raw_value"])
            if source not in bucket["sources"]:
                bucket["sources"].append(source)
            if raw not in bucket["raw"]:
                bucket["raw"].append(raw)
            bucket["order"].append((int(row["source_line"]), int(row["variant_order"])))
            rules[key] = str(row["pattern"])
        suggestions = [
            MasterSuggestion(
                value=value,
                sources=tuple(data["sources"]),
                raw_values=tuple(data["raw"]),
                kind="rule",
                rule=rules[(value, start, end)],
                replacement_start=start,
                replacement_end=end,
            )
            for (value, start, end), data in values.items()
        ]
        suggestions.sort(
            key=lambda item: (
                item.replacement_start or 0,
                min(values[(item.value, item.replacement_start or 0, item.replacement_end or 0)]["order"]),
            )
        )
        return tuple(suggestions)

    def suggestions_for_unknown(
        self,
        sentence: str,
        start: int,
        end: int,
        *,
        blocked_spans: Sequence[Tuple[int, int]] = (),
    ) -> Tuple[MasterSuggestion, ...]:
        rules = self.rule_suggestions(
            sentence, start, end, blocked_spans=blocked_spans
        )
        if rules:
            return rules
        return self.phonetic_suggestions(sentence[start:end])

    def __enter__(self) -> "MasterDictionary":
        self.ensure_ready()
        return self

    def __exit__(self, *_args) -> None:
        self.close()
