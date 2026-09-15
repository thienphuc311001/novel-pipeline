"""Input loading: TXT files, ZIP archives and merge ordering.

Only plain text is imported.  Directories, macOS metadata (``__MACOSX``,
``._*``, ``.DS_Store``), hidden files, non-TXT entries and obvious
``metadata``/``readme`` entries are skipped, and every skip is reported so the
user can see exactly what was left out of the merge.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from cleaning.encodings import EncodingResult, detect_encoding
from pipeline.document import Diagnostic, Severity, SourceFile

TEXT_SUFFIXES = (".txt", ".text", ".md", ".log")
IGNORED_NAMES = {"readme", "readme.txt", "metadata", "metadata.txt", "license", "info", "desktop.ini"}
IGNORED_PREFIXES = ("__macosx", "._")
NATURAL_RE = re.compile(r"(\d+)")


def natural_key(name: str) -> Tuple:
    """Natural sort key so ``ch9`` sorts before ``ch10``."""
    parts = NATURAL_RE.split(name.lower())
    key: List[Tuple[int, object]] = []
    for index, part in enumerate(parts):
        if index % 2:
            key.append((1, int(part)))
        else:
            key.append((0, part))
    return tuple(key)


def sort_naturally(names: Iterable[str]) -> List[str]:
    return sorted(names, key=natural_key)


@dataclass
class SkippedEntry:
    name: str
    origin: str = ""
    reason: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "origin": self.origin, "reason": self.reason}


@dataclass
class LoadedInput:
    files: List[SourceFile] = field(default_factory=list)
    skipped: List[SkippedEntry] = field(default_factory=list)
    diagnostics: List[Diagnostic] = field(default_factory=list)
    encodings_used: List[str] = field(default_factory=list)
    raw_bytes: bytes = b""

    @property
    def text(self) -> str:
        """Merged text in the user chosen order."""
        return "\n\n".join(file.text.strip("\n") for file in self.files if file.text.strip())

    def summary(self) -> str:
        if not self.files:
            return "Chưa nạp tệp nào."
        encodings = ", ".join(sorted({f.encoding for f in self.files if f.encoding}))
        return (
            f"{len(self.files)} nguồn, {sum(f.char_count for f in self.files)} ký tự"
            + (f" · mã hoá: {encodings}" if encodings else "")
            + (f" · bỏ qua {len(self.skipped)} mục" if self.skipped else "")
        )


def _should_skip(name: str) -> Optional[str]:
    lowered = name.replace("\\", "/").strip().lower()
    if not lowered or lowered.endswith("/"):
        return "thư mục"
    base = lowered.rsplit("/", 1)[-1]
    if base.startswith(IGNORED_PREFIXES):
        return "tệp metadata của macOS"
    if base.startswith("."):
        return "tệp ẩn"
    if base in IGNORED_NAMES:
        return "tệp metadata/readme"
    if lowered.startswith(IGNORED_PREFIXES):
        return "thư mục metadata của macOS"
    if not base.endswith(TEXT_SUFFIXES):
        return "không phải tệp văn bản"
    return None


def _decode(data: bytes, chain: Sequence[str]) -> EncodingResult:
    return detect_encoding(data, chain)


def read_text_file(
    path: Path,
    *,
    chain: Sequence[str],
    order: int = 0,
) -> Tuple[Optional[SourceFile], Optional[Diagnostic]]:
    try:
        data = path.read_bytes()
    except OSError as error:
        return None, Diagnostic(
            code="file_unreadable",
            severity=Severity.ERROR,
            message=f"Không đọc được tệp {path.name}: {error}",
            stage="input",
        )
    result = _decode(data, chain)
    source = SourceFile(
        name=path.name,
        path=str(path),
        encoding=result.encoding,
        char_count=len(result.text),
        text=result.text,
        order=order,
    )
    diagnostic = None
    if result.note:
        diagnostic = Diagnostic(
            code="encoding_detected",
            severity=Severity.INFO if not result.had_decoding_errors else Severity.WARNING,
            message=f"{path.name}: dùng mã hoá {result.encoding}.",
            detail=result.note + (f" · {result.bom}" if result.bom else ""),
            stage="input",
        )
    return source, diagnostic


def read_zip_entries(
    path: Path,
    *,
    chain: Sequence[str],
    order_start: int = 0,
    include_patterns: Optional[Sequence[str]] = None,
) -> Tuple[List[SourceFile], List[SkippedEntry], List[Diagnostic]]:
    files: List[SourceFile] = []
    skipped: List[SkippedEntry] = []
    diagnostics: List[Diagnostic] = []
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as error:
        diagnostics.append(
            Diagnostic(
                code="archive_unreadable",
                severity=Severity.ERROR,
                message=f"Không mở được ZIP {path.name}: {error}",
                stage="input",
            )
        )
        return files, skipped, diagnostics

    with archive:
        names = [info.filename for info in archive.infolist() if not info.is_dir()]
        for name in names:
            reason = _should_skip(name)
            if reason:
                skipped.append(SkippedEntry(name=name, origin=path.name, reason=reason))
                continue
            if include_patterns and not any(pattern.lower() in name.lower() for pattern in include_patterns):
                skipped.append(SkippedEntry(name=name, origin=path.name, reason="không khớp mẫu chọn"))
                continue
            try:
                data = archive.read(name)
            except (KeyError, OSError) as error:  # pragma: no cover - corrupt archive
                diagnostics.append(
                    Diagnostic(
                        code="entry_unreadable",
                        severity=Severity.WARNING,
                        message=f"Không đọc được mục {name} trong {path.name}: {error}",
                        stage="input",
                    )
                )
                continue
            result = _decode(data, chain)
            files.append(
                SourceFile(
                    name=name.rsplit("/", 1)[-1],
                    path=str(path),
                    origin=path.name,
                    encoding=result.encoding,
                    char_count=len(result.text),
                    text=result.text,
                    order=order_start + len(files),
                )
            )
            if result.had_decoding_errors or result.note:
                diagnostics.append(
                    Diagnostic(
                        code="encoding_detected",
                        severity=Severity.WARNING if result.had_decoding_errors else Severity.INFO,
                        message=f"{path.name}:{name}: dùng mã hoá {result.encoding}.",
                        detail=result.note,
                        stage="input",
                    )
                )
    return files, skipped, diagnostics


def load_paths(
    paths: Sequence[str],
    *,
    chain: Sequence[str],
    sort_mode: str = "natural",
    explicit_order: Optional[Sequence[str]] = None,
    include_patterns: Optional[Sequence[str]] = None,
) -> LoadedInput:
    """Load TXT files and ZIP archives into a single ordered list of sources."""
    loaded = LoadedInput()
    sources: List[SourceFile] = []

    for raw_path in paths:
        path = Path(raw_path).expanduser()
        if not path.exists():
            loaded.diagnostics.append(
                Diagnostic(
                    code="path_missing",
                    severity=Severity.WARNING,
                    message=f"Không tìm thấy đường dẫn: {path}",
                    stage="input",
                )
            )
            continue
        if path.is_dir():
            for child in sorted(path.iterdir(), key=lambda item: natural_key(item.name)):
                if child.is_dir():
                    loaded.skipped.append(SkippedEntry(name=str(child), reason="thư mục"))
                    continue
                reason = _should_skip(child.name)
                if reason:
                    loaded.skipped.append(SkippedEntry(name=str(child), reason=reason))
                    continue
                source, diagnostic = read_text_file(child, chain=chain, order=len(sources))
                if source is not None:
                    sources.append(source)
                if diagnostic is not None:
                    loaded.diagnostics.append(diagnostic)
            continue
        if path.suffix.lower() == ".zip":
            files, skipped, diagnostics = read_zip_entries(
                path,
                chain=chain,
                order_start=len(sources),
                include_patterns=include_patterns,
            )
            sources.extend(files)
            loaded.skipped.extend(skipped)
            loaded.diagnostics.extend(diagnostics)
            continue
        reason = _should_skip(path.name)
        if reason:
            loaded.skipped.append(SkippedEntry(name=str(path), reason=reason))
            continue
        source, diagnostic = read_text_file(path, chain=chain, order=len(sources))
        if source is not None:
            sources.append(source)
        if diagnostic is not None:
            loaded.diagnostics.append(diagnostic)

    if explicit_order:
        lookup = {source.path: source for source in sources}
        lookup.update({source.name: source for source in sources})
        ordered: List[SourceFile] = []
        for key in explicit_order:
            source = lookup.get(key)
            if source is not None and source not in ordered:
                ordered.append(source)
        for source in sources:
            if source not in ordered:
                ordered.append(source)
        sources = ordered
    elif sort_mode == "natural":
        sources.sort(key=lambda source: natural_key(source.name))
    elif sort_mode == "name":
        sources.sort(key=lambda source: source.name.lower())
    # sort_mode == "selection" keeps the user's click order

    for index, source in enumerate(sources):
        source.order = index

    loaded.files = sources
    loaded.encodings_used = sorted({source.encoding for source in sources if source.encoding})
    for entry in loaded.skipped:
        loaded.diagnostics.append(
            Diagnostic(
                code="input_entry_skipped",
                severity=Severity.INFO,
                message=f"Bỏ qua {entry.name}: {entry.reason}.",
                stage="input",
            )
        )
    for name in codecs_probe():
        pass
    return loaded


def codecs_probe() -> List[str]:
    """Encodings actually available in this Python build (for the settings UI)."""
    import codecs

    available: List[str] = []
    for encoding in ("utf-8", "utf-8-sig", "utf-16", "utf-32", "cp1258", "cp1252", "latin-1"):
        try:
            codecs.lookup(encoding)
            available.append(encoding)
        except LookupError:  # pragma: no cover - depends on the Python build
            continue
    return available


def insert_missing_headers(
    sources: Sequence[SourceFile],
    *,
    has_header,
    prefix: str = "Chương {n}",
    continuous: bool = True,
    detect_max_number,
) -> Tuple[List[SourceFile], List[Diagnostic]]:
    """Add a chapter header to sources that have none.

    With ``continuous`` the injected numbers continue after the last chapter
    number seen in the previous source, so merging keeps a single sequence.
    """
    diagnostics: List[Diagnostic] = []
    next_number = 1
    for source in sources:
        maximum = detect_max_number(source.text)
        if maximum is not None:
            next_number = maximum + 1 if continuous else next_number
            continue
        if not source.text.strip():
            continue
        header = prefix.format(n=next_number, number=next_number)
        source.text = f"{header}\n{source.text.lstrip()}"
        source.injected_header = True
        source.char_count = len(source.text)
        diagnostics.append(
            Diagnostic(
                code="header_inserted",
                severity=Severity.INFO,
                message=f"{source.name}: không có tiêu đề chương, đã thêm '{header}'.",
                stage="input",
            )
        )
        next_number += 1
    return list(sources), diagnostics

