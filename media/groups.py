"""Lossless chapter grouping and independent, validated media jobs.

Canonical group files never contain cleaned/TTS text. Only the explicit
manifest establishes group membership; directory contents are not discovery.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from chapters.patterns import build_patterns, glued_head
from chapters.numerals import parse_number_token
from media.artifacts import atomic_write_json, atomic_write_text, sha256_file, sha256_text, slugify_job_name
from pipeline.document import Chapter, PipelineStateError, Step4MediaBundle, Step5UploadBundle

GROUPING_METHOD_DETECTED = "detected_chapters"
GROUPING_METHOD_NUMERIC = "numeric_boundaries"
# Increment whenever heading detection or numeral parsing changes in a way that
# can move a boundary. Numeric confirmations are intentionally fail-closed.
HEADING_SCANNER_VERSION = "heading-scan-v1"


@dataclass
class HeadingSpan:
    number: int
    heading: str
    start: int
    body_start: int
    end: int
    line: int


@dataclass
class ChapterGroup:
    group_id: str
    order: int
    label: str
    range_label: str
    title: str
    slug: str
    output_dir: str
    txt_path: str
    json_path: str
    source_sha256: str
    text_sha256: str
    json_sha256: str
    chapters: list[dict]
    start: int
    end: int
    state: dict = field(default_factory=dict)


@dataclass
class GroupingAnalysis:
    """Read-only grouping facts for the current, untouched Step 2 text."""

    headings: list[HeadingSpan]
    diagnostics: list[str]
    expected_count: int
    requires_numeric_boundaries: bool
    numeric_groups: list[dict] = field(default_factory=list)
    required_group_starts: list[dict] = field(default_factory=list)
    numeric_unavailable_reason: str = ""
    numeric_identity_descriptor: dict = field(default_factory=dict)
    numeric_identity_fingerprint: str = ""


def scan_headings(text, settings):
    """Offsets refer to the untouched string, including CRLF and preambles."""
    patterns = build_patterns(settings).all()
    found = []
    offset = 0
    for line_number, physical in enumerate(text.splitlines(keepends=True), 1):
        line = physical.rstrip("\r\n")
        for pattern in patterns:
            match = pattern.match(line.strip())
            # Built-in headings may have a space-separated title. Only accept
            # a structural marker followed by whitespace/punctuation, not a
            # glued narrative, when the full configured pattern did not match.
            if match is None and pattern.name in {"vietnamese", "english"}:
                head = glued_head(pattern)
                candidate = head.match(line.strip()) if head else None
                if candidate and (candidate.end() == len(line.strip()) or
                                  re.match(r"[\s:：.\-–—]", line.strip()[candidate.end():])):
                    match = candidate
            if match:
                try:
                    number = parse_number_token(match.group("number"))
                except (ValueError, KeyError, IndexError):
                    continue
                if number is None:
                    continue
                found.append(HeadingSpan(number, line, offset, offset + len(physical), len(text), line_number))
                break
        offset += len(physical)
    for left, right in zip(found, found[1:]):
        left.end = right.start
    return found


def heading_diagnostics(headings):
    warnings = []
    for previous, current in zip(headings, headings[1:]):
        if current.number == previous.number:
            kind = "Repeated chapter number"
        elif current.number < previous.number:
            kind = "Numbering reset"
        elif current.number != previous.number + 1:
            kind = "Numbering gap"
        else:
            continue
        warnings.append(f"{kind}: {previous.heading.strip()} → {current.heading.strip()} (line {current.line})")
    return warnings


def _active_patterns(settings):
    return [{"name": p.name, "regex": p.regex.pattern, "flags": p.regex.flags}
            for p in build_patterns(settings).all()]


def _validate_grouping_method(method):
    if method not in {GROUPING_METHOD_DETECTED, GROUPING_METHOD_NUMERIC}:
        raise PipelineStateError(f"Unknown chapter grouping method: {method}")


def _detected_groups(headings, size):
    groups = []
    for index in range(0, len(headings), size):
        entries = headings[index:index + size]
        start = 0 if index == 0 else entries[0].start
        end = entries[-1].end
        range_label = str(entries[0].number) if len(entries) == 1 else f"{entries[0].number}-{entries[-1].number}"
        groups.append({"order": len(groups) + 1, "label": f"Chương {range_label}",
                       "range_label": range_label, "start": start, "end": end,
                       "chapters": [asdict(h) for h in entries]})
    return groups


def _numeric_identity(text, settings, size, headings, groups, required_starts):
    descriptor = {
        "version": 1,
        "source_sha256": sha256_text(text),
        "heading_scanner_version": HEADING_SCANNER_VERSION,
        "patterns": _active_patterns(settings),
        "first_number": headings[0].number,
        "last_number": headings[-1].number,
        "group_size": size,
        "grouping_method": GROUPING_METHOD_NUMERIC,
        "calculated_ranges": [item["range_label"] for item in groups],
        "required_group_starts": required_starts,
    }
    serialized = json.dumps(descriptor, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return descriptor, sha256_text(serialized)


def analyze_grouping(text, settings, size=20):
    """Analyze ordinary and numeric-boundary grouping without mutating state."""
    if not isinstance(size, int) or size < 1:
        raise PipelineStateError("Chapters per group must be a positive integer.")
    headings = scan_headings(text, settings)
    if not headings:
        raise PipelineStateError("No chapter headings detected. Correct the headings in Step 1/2 or enable the matching chapter patterns in Settings.")
    diagnostics = heading_diagnostics(headings)
    expected_count = headings[-1].number - headings[0].number + 1
    has_gap = any(message.startswith("Numbering gap:") for message in diagnostics)
    requires_numeric = has_gap and expected_count > 0 and len(headings) < expected_count
    analysis = GroupingAnalysis(headings, diagnostics, expected_count, requires_numeric)
    if not requires_numeric:
        return analysis

    if any(right.number <= left.number for left, right in zip(headings, headings[1:])):
        analysis.numeric_unavailable_reason = (
            "Chapter numbering contains a duplicate or reset, so a split boundary is ambiguous."
        )
        return analysis

    by_number = {heading.number: heading for heading in headings}
    starts = list(range(headings[0].number, headings[-1].number + 1, size))
    missing = [number for number in starts if number not in by_number]
    if missing:
        analysis.numeric_unavailable_reason = (
            "Missing required group-start heading(s): " + ", ".join(f"Chương {number}" for number in missing) + "."
        )
        return analysis

    required_starts = [{"number": number, "offset": by_number[number].start} for number in starts]
    groups = []
    for order, number in enumerate(starts, 1):
        end_number = min(number + size - 1, headings[-1].number)
        next_start = by_number[starts[order]].start if order < len(starts) else len(text)
        entries = [heading for heading in headings if number <= heading.number <= end_number]
        range_label = str(number) if number == end_number else f"{number}-{end_number}"
        groups.append({"order": order, "label": f"Chương {range_label}", "range_label": range_label,
                       "start": 0 if order == 1 else by_number[number].start, "end": next_start,
                       "chapters": [asdict(heading) for heading in entries]})
    descriptor, fingerprint = _numeric_identity(text, settings, size, headings, groups, required_starts)
    analysis.numeric_groups = groups
    analysis.required_group_starts = required_starts
    analysis.numeric_identity_descriptor = descriptor
    analysis.numeric_identity_fingerprint = fingerprint
    return analysis


def _groups_for_method(analysis, method, size):
    _validate_grouping_method(method)
    if method == GROUPING_METHOD_DETECTED:
        if analysis.requires_numeric_boundaries:
            raise PipelineStateError(
                "Some chapter numbers are missing and heading-count grouping could create incorrect ranges. "
                "Review numeric chapter boundaries instead."
            )
        return _detected_groups(analysis.headings, size)
    if not analysis.requires_numeric_boundaries:
        raise PipelineStateError("Numeric-boundary grouping is only available when missing chapter numbers reduce the detected count.")
    if analysis.numeric_unavailable_reason:
        raise PipelineStateError("Automatic numeric-boundary grouping is unavailable: " + analysis.numeric_unavailable_reason)
    return analysis.numeric_groups


def preview_groups(text, settings, size=20, *, method=GROUPING_METHOD_DETECTED):
    analysis = analyze_grouping(text, settings, size)
    if method == GROUPING_METHOD_DETECTED and not analysis.requires_numeric_boundaries:
        groups = _detected_groups(analysis.headings, size)
    else:
        groups = _groups_for_method(analysis, method, size)
    return analysis.headings, groups, analysis.diagnostics


def grouping_config(settings, size, method=GROUPING_METHOD_DETECTED):
    _validate_grouping_method(method)
    config = {"chapters_per_group": size, "patterns": _active_patterns(settings)}
    if method == GROUPING_METHOD_NUMERIC:
        config["grouping_method"] = method
    return config


def _group_id(source_hash, title, size, item, method, numeric_fingerprint):
    value = f"{source_hash}\0{title}\0{size}\0{item['order']}\0{item['start']}\0{item['end']}"
    if method == GROUPING_METHOD_NUMERIC:
        value += f"\0{method}\0{numeric_fingerprint}"
    return sha256_text(value)[:24]


def write_groups(document, settings, title, size=20, *, method=GROUPING_METHOD_DETECTED, confirmation_fingerprint=""):
    text = document.require_step2_confirmed_output()
    title = title.strip()
    if not title:
        raise PipelineStateError("Enter a novel title before creating group files.")
    analysis = analyze_grouping(text, settings, size)
    if method == GROUPING_METHOD_DETECTED and not analysis.requires_numeric_boundaries:
        preview = _detected_groups(analysis.headings, size)
    else:
        preview = _groups_for_method(analysis, method, size)
    if method == GROUPING_METHOD_NUMERIC and confirmation_fingerprint != analysis.numeric_identity_fingerprint:
        raise PipelineStateError("Numeric-boundary grouping requires a current user confirmation.")
    title_slug = slugify_job_name(title, "").rstrip("_")
    novel_dir = settings.resolved_output_dir(document.input_directory).resolve() / title_slug
    source_hash = sha256_text(text)
    config = grouping_config(settings, size, method)
    groups, used = [], set()
    for item in preview:
        slug = slugify_job_name(title_slug, item["range_label"])
        if slug in used:
            slug += f"_group_{item['order']:03d}"
        used.add(slug)
        folder = novel_dir / slug
        group_text = text[item["start"]:item["end"]]
        group_id = _group_id(source_hash, title, size, item, method, analysis.numeric_identity_fingerprint)
        payload = {"schema_version": 2, "group_id": group_id, "title": title, **item,
                   "source_sha256": source_hash, "text_sha256": sha256_text(group_text), "text": group_text}
        atomic_write_text(folder / "final.txt", group_text)
        atomic_write_json(folder / "final.json", payload)
        group = ChapterGroup(group_id, item["order"], item["label"], item["range_label"], title, slug,
                             str(folder), str(folder / "final.txt"), str(folder / "final.json"), source_hash,
                             sha256_text(group_text), sha256_file(folder / "final.json"), item["chapters"], item["start"], item["end"])
        group.state = load_job_state(group)
        groups.append(group)
    manifest = {"schema_version": 2, "title": title, "source_sha256": source_hash,
                "grouping_method": method, "config": config,
                "groups": [dict(asdict(g), state={}) for g in groups]}
    if method == GROUPING_METHOD_NUMERIC:
        manifest["numeric_confirmation"] = {
            "confirmed_identity": confirmation_fingerprint,
            "descriptor": analysis.numeric_identity_descriptor,
            "fingerprint": analysis.numeric_identity_fingerprint,
        }
    atomic_write_json(novel_dir / "chapter_groups.json", manifest)
    document._clear_step3_artifacts()
    document.cleaned_text = None
    document.chunks = []
    document.filtered_output = None
    document.chapter_groups = groups
    document.grouping_config = config
    document.group_manifest_path = str(novel_dir / "chapter_groups.json")
    document.job_title = title
    return groups


def restore_groups(document, settings, title, size):
    """Restore solely from a manifest, validating it against current content."""
    text = document.require_step2_confirmed_output()
    novel = settings.resolved_output_dir(document.input_directory).resolve() / slugify_job_name(title, "").rstrip("_")
    path = novel / "chapter_groups.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        method = data.get("grouping_method", GROUPING_METHOD_DETECTED)
        _validate_grouping_method(method)
        analysis = analyze_grouping(text, settings, size)
        if method == GROUPING_METHOD_DETECTED and not analysis.requires_numeric_boundaries:
            expected = _detected_groups(analysis.headings, size)
        else:
            expected = _groups_for_method(analysis, method, size)
        numeric_fingerprint = ""
        if method == GROUPING_METHOD_NUMERIC:
            confirmation = data.get("numeric_confirmation")
            if not isinstance(confirmation, dict):
                raise ValueError("Numeric-boundary confirmation is missing from the manifest.")
            numeric_fingerprint = analysis.numeric_identity_fingerprint
            if (confirmation.get("confirmed_identity") != numeric_fingerprint or
                    confirmation.get("fingerprint") != numeric_fingerprint or
                    confirmation.get("descriptor") != analysis.numeric_identity_descriptor):
                raise ValueError("Numeric-boundary confirmation does not match the current source/configuration.")
        if (data["schema_version"] != 2 or data["title"] != title or data["source_sha256"] != sha256_text(text)
                or data["config"] != grouping_config(settings, size, method) or len(data["groups"]) != len(expected)):
            raise ValueError("Manifest does not match the current source/configuration.")
        groups = [ChapterGroup(**row) for row in data["groups"]]
        used = set()
        for group, item in zip(groups, expected):
            if any(getattr(group, key) != item[key] for key in ("order", "start", "end", "chapters", "label", "range_label")):
                raise ValueError("Manifest chapter membership is invalid.")
            slug = slugify_job_name(novel.name, item["range_label"])
            if slug in used:
                slug += f"_group_{item['order']:03d}"
            used.add(slug)
            expected_id = _group_id(sha256_text(text), title, size, item, method, numeric_fingerprint)
            if (Path(group.output_dir).resolve() != novel / slug or group.slug != slug or
                    group.title != title or group.group_id != expected_id or
                    Path(group.txt_path).resolve() != novel / slug / "final.txt" or
                    Path(group.json_path).resolve() != novel / slug / "final.json"):
                raise ValueError("Group path is outside the novel folder.")
            validate_group(group, text)
            group.state = load_job_state(group)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise PipelineStateError(f"Cannot restore chapter groups: {error}") from error
    document._clear_step3_artifacts()
    document.cleaned_text, document.chunks, document.filtered_output = None, [], None
    document.chapter_groups, document.grouping_config, document.group_manifest_path = groups, data["config"], str(path)
    document.job_title = title
    return groups


def validate_group(group, source):
    try:
        folder = Path(group.output_dir).resolve()
        if any(Path(p).resolve().parent != folder for p in (group.txt_path, group.json_path)):
            raise ValueError("Canonical paths are outside the group folder.")
        expected = source[group.start:group.end]
        if (sha256_text(source) != group.source_sha256 or sha256_text(expected) != group.text_sha256 or
                sha256_file(Path(group.txt_path)) != group.text_sha256 or sha256_file(Path(group.json_path)) != group.json_sha256):
            raise ValueError("Group is stale, missing, or externally modified.")
        data = json.loads(Path(group.json_path).read_text(encoding="utf-8"))
        if data["text"] != expected or data["chapters"] != group.chapters or data["group_id"] != group.group_id or "chunks" in data:
            raise ValueError("Group JSON does not describe the canonical text.")
        return expected
    except (OSError, ValueError, KeyError) as error:
        raise PipelineStateError(f"{group.label}: {error}") from error


def load_job_state(group):
    path = Path(group.output_dir) / "job_state.json"
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(state, dict) and state.get("group_id") == group.group_id and state.get("text_sha256") == group.text_sha256:
            return state
    except (OSError, ValueError):
        pass
    return {}


def save_job_state(group):
    group.state.update(schema_version=1, group_id=group.group_id, text_sha256=group.text_sha256)
    atomic_write_json(Path(group.output_dir) / "job_state.json", group.state)


def record_media(group, kind, path):
    from pipeline.document import PipelineDocument
    group.state[kind] = {"path": str(Path(path).resolve()), "fingerprint": PipelineDocument._fingerprint_file(str(path))}
    group.state.pop("video", None)
    save_job_state(group)


def require_media(document, group_id):
    group = document.require_group_artifacts(group_id)
    folder = Path(group.output_dir).resolve()
    for kind in ("thumbnail", "audiobook"):
        row = group.state.get(kind, {})
        if not isinstance(row, dict):
            raise PipelineStateError(f"{group.label}: invalid {kind} recovery state; regenerate it in Step 4.")
        current = document._fingerprint_file(row.get("path", ""))
        if (not current or current["size"] < 1 or current != row.get("fingerprint") or
                Path(row["path"]).resolve().parent != folder):
            raise PipelineStateError(f"{group.label}: generate a current {kind} in Step 4 first.")
    if group.state.get("tts_status") not in {"Completed", "Partial"}:
        raise PipelineStateError(f"{group.label}: TTS is incomplete; resume it or explicitly merge with missing chunks.")
    provenance = group.state.get("tts_provenance", {})
    if provenance:
        for filename, key in (("tts_chunks.json", "plan_sha256"), ("tts_overrides.json", "overrides_sha256")):
            path = folder / filename
            try:
                current_hash = sha256_file(path) if path.exists() else ""
            except OSError as error:
                raise PipelineStateError(f"{group.label}: unavailable TTS plan: {error}") from error
            if current_hash != provenance.get(key):
                raise PipelineStateError(f"{group.label}: TTS text/overrides changed; resume TTS before rendering.")
    return Step4MediaBundle(group.title, group.label, group.slug, group.output_dir,
                           group.state["thumbnail"]["path"], group.state["audiobook"]["path"],
                           str(folder / f"{group.slug}.mp4"), group.state["thumbnail"]["fingerprint"], group.state["audiobook"]["fingerprint"])


def record_tts_provenance(group, processor):
    folder = Path(group.output_dir)
    overrides = folder / "tts_overrides.json"
    group.state["tts_provenance"] = {
        "voice": processor.voice, "plan_sha256": sha256_file(folder / "tts_chunks.json"),
        "overrides_sha256": sha256_file(overrides) if overrides.exists() else "",
        "effective_text_sha256": sha256_text("\n".join(f"{c.order}\0{c.text}" for c in processor.chunks))}


def video_source(media):
    return {"thumbnail": media.thumbnail_fingerprint, "audio": media.audiobook_fingerprint,
            "profile": {"version": 1, "width": 1920, "height": 1080, "fps": 1, "codec": "h264"}}


def record_video(document, group_id, result):
    group = document.require_group_artifacts(group_id)
    media = require_media(document, group_id)
    group.state["video"] = {"path": str(result.output_path), "fingerprint": document._fingerprint_file(str(result.output_path)),
                            "source": video_source(media), "result": result.to_dict(), "status": "Completed"}
    save_job_state(group)


def require_video(document, group_id):
    group = document.require_group_artifacts(group_id)
    media = require_media(document, group_id)
    row = group.state.get("video", {})
    fp = document._fingerprint_file(row.get("path", ""))
    if (not fp or fp["size"] <= 0 or fp != row.get("fingerprint") or row.get("source") != video_source(media) or
            Path(row["path"]).resolve() != Path(media.video_path).resolve()):
        raise PipelineStateError(f"{group.label}: create a current video in Step 5 first.")
    return Step5UploadBundle(group.title, group.label, group.output_dir, row["path"], media.thumbnail_path, fp, media.thumbnail_fingerprint)


def prepare_tts(document, group_id, settings):
    """Cleaning/chunking lives exclusively in Step 4, never canonical files."""
    from cleaning.textclean import CleaningOptions, clean_text
    from chunking.splitter import split_chapters, clamp_chunk_size
    from media.tts import TtsChunk
    group = document.require_group_artifacts(group_id)
    source = validate_group(group, document.require_step2_confirmed_output())
    options = CleaningOptions.from_settings(settings)
    minimum = max(50, int(settings.min_chunk_chars or 200))
    limit = clamp_chunk_size(settings.clamp_chunk_size(), minimum)
    config = {"cleaning": asdict(options), "limit": limit, "minimum": minimum}
    identity = sha256_text(json.dumps({"source": group.text_sha256, "config": config}, ensure_ascii=False, sort_keys=True))
    folder = Path(group.output_dir)
    path = folder / "tts_chunks.json"
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
        if plan["plan_id"] != identity or plan["group_id"] != group_id:
            raise ValueError("Changed TTS plan")
        base = plan["chunks"]
        if [c["order"] for c in base] != list(range(1, len(base) + 1)) or not base:
            raise ValueError("Invalid chunk ordering")
        if any(sha256_text(c["text"]) != c["text_sha256"] for c in base):
            raise ValueError("Changed chunk text")
    except (OSError, ValueError, KeyError):
        chapters = []
        first_start = group.chapters[0]["start"] - group.start
        if first_start > 0 and source[:first_start].strip():
            cleaned, _ = clean_text(source[:first_start], options)
            chapters.append(Chapter(number=0, header_line="", text=cleaned))
        for row in group.chapters:
            body = source[row["body_start"] - group.start:row["end"] - group.start]
            cleaned, _ = clean_text(body, options)
            header, _ = clean_text(row["heading"], options)
            chapters.append(Chapter(number=row["number"], header_line=header, text=cleaned))
        chunks, _, _ = split_chapters(chapters, limit, include_header=True, min_chunk=minimum)
        base = [{"order": c.order, "chapter": c.chapter, "text": c.text, "text_sha256": sha256_text(c.text)} for c in chunks]
        if not base:
            raise PipelineStateError(f"{group.label}: no speakable text after cleaning.")
        plan = {"schema_version": 1, "group_id": group_id, "plan_id": identity, "config": config, "chunks": base}
        atomic_write_json(path, plan)
    overrides = {}
    try:
        saved = json.loads((folder / "tts_overrides.json").read_text(encoding="utf-8"))
        if saved["plan_id"] == identity:
            overrides = saved["overrides"]
    except (OSError, ValueError, KeyError):
        pass
    effective = []
    for row in base:
        text = overrides.get(str(row["order"]), row["text"])
        if not isinstance(text, str) or not text.strip() or len(text) > limit:
            raise PipelineStateError("Invalid saved TTS override; correct the failed chunk text.")
        effective.append(TtsChunk(row["order"], text, row["chapter"]))
    group.state["tts_plan_id"] = identity
    return plan, effective


def edit_failed_chunk(document, group_id, settings, order, text):
    group = document.require_group_artifacts(group_id)
    plan, _ = prepare_tts(document, group_id, settings)
    if order not in {int(f["chunk_number"]) for f in group.state.get("failures", [])}:
        raise PipelineStateError("Only a selected failed TTS chunk can be edited.")
    if not text.strip() or len(text) > plan["config"]["limit"]:
        raise PipelineStateError(f"Replacement must be non-empty and at most {plan['config']['limit']} characters.")
    path = Path(group.output_dir) / "tts_overrides.json"
    saved = {"schema_version": 1, "plan_id": plan["plan_id"], "overrides": {}}
    try:
        old = json.loads(path.read_text(encoding="utf-8"))
        if old["plan_id"] == plan["plan_id"]:
            saved = old
    except (OSError, ValueError, KeyError):
        pass
    saved["overrides"][str(order)] = text
    atomic_write_json(path, saved)
    group.state.update(tts_status="TTS Incomplete")
    group.state.pop("video", None)
    save_job_state(group)
