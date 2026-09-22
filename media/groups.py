"""Lossless chapter grouping and independent, validated media jobs.

Canonical group files never contain cleaned/TTS text. Only the explicit
manifest establishes group membership; directory contents are not discovery.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from chapters.detector import is_clock_value_match
from chapters.patterns import build_patterns, glued_head
from chapters.numerals import parse_number_token
from media.artifacts import (atomic_write_json, atomic_write_text, require_artifact_root, sha256_file,
                             sha256_text, slugify_job_name)
from pipeline.document import (Chapter, PipelineStateError, Step4MediaBundle, Step5UploadBundle,
                               render_chapters_text)

GROUPING_METHOD_DETECTED = "detected_chapters"
GROUPING_METHOD_NUMERIC = "numeric_boundaries"
# Increment whenever heading detection or numeral parsing changes in a way that
# can move a boundary. Numeric confirmations are intentionally fail-closed.
HEADING_SCANNER_VERSION = "heading-scan-v2"


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
    """Read-only grouping facts for the current, untouched source text."""

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
            # Countdown/clock values inside the story are not chapter headings.
            if match is not None and is_clock_value_match(line, match, pattern.name):
                match = None
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


def _manifest_path(document, settings, title):
    """Resolve the manifest beside the input without abandoning a recorded job."""
    remembered = Path(getattr(document, "group_manifest_path", "") or "").expanduser()
    if remembered.is_file():
        return remembered.resolve()
    root = require_artifact_root(settings, document.input_directory)
    return root / slugify_job_name(title, "").rstrip("_") / "chapter_groups.json"


def write_groups(document, settings, title, size=20, *, method=GROUPING_METHOD_DETECTED, confirmation_fingerprint=""):
    text = document.require_grouping_input()
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
    output_root = require_artifact_root(settings, document.input_directory)
    novel_dir = output_root / title_slug
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
                "source_revision": document.normalized_revision,
                "resolved_output_dir": str(output_root),
                "job_output_dir": str(novel_dir),
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
    text = document.require_grouping_input()
    path = _manifest_path(document, settings, title)
    novel = path.parent
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Manifest must describe chapter groups.")
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
        if "source_revision" in data and data["source_revision"] != document.normalized_revision:
            raise ValueError("Manifest belongs to an older normalized text revision.")
        groups = [ChapterGroup(**row) for row in data["groups"]]
        deleted_ids = data.get("deleted_group_ids", [])
        if (not isinstance(deleted_ids, list) or any(not isinstance(value, str) for value in deleted_ids) or
                len(set(deleted_ids)) != len(deleted_ids) or
                not set(deleted_ids).issubset({group.group_id for group in groups})):
            raise ValueError("Manifest deleted-group membership is invalid.")
        deleted_ids = set(deleted_ids)
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
            if (group.source_sha256 != sha256_text(text) or
                    group.text_sha256 != sha256_text(text[item["start"]:item["end"]])):
                raise ValueError("Manifest group text does not match the current source.")
            if group.group_id not in deleted_ids:
                validate_group(group, text)
                group.state = load_job_state(group)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise PipelineStateError(f"Cannot restore chapter groups: {error}") from error
    document._clear_step3_artifacts()
    document.cleaned_text, document.chunks, document.filtered_output = None, [], None
    document.chapter_groups = [group for group in groups if group.group_id not in deleted_ids]
    document.deleted_chapter_groups = [group for group in groups if group.group_id in deleted_ids]
    document.grouping_config, document.group_manifest_path = data["config"], str(path)
    document.job_title = title
    return document.chapter_groups


def delete_group(document, group_id):
    """Remove one job from later stages, retaining its files for recovery."""
    document.require_chapter_groups(validate_files=False)
    group = next((group for group in document.chapter_groups if group.group_id == group_id), None)
    if group is None:
        raise PipelineStateError("Select a current chapter group to delete.")
    path = Path(document.group_manifest_path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Manifest must describe chapter groups.")
        groups = sorted(document.chapter_groups + document.deleted_chapter_groups, key=lambda item: item.order)
        deleted_ids = [item.group_id for item in document.deleted_chapter_groups]
        if (data.get("schema_version") != 2 or data.get("title") != document.job_title or
                data.get("source_sha256") != group.source_sha256 or
                data.get("config") != document.grouping_config or
                data.get("groups") != [dict(asdict(item), state={}) for item in groups] or
                data.get("deleted_group_ids", []) != deleted_ids):
            raise ValueError("Manifest changed; restore matching groups in Step 2 before deleting.")
        removed = {*deleted_ids, group_id}
        data["deleted_group_ids"] = [item.group_id for item in groups if item.group_id in removed]
        atomic_write_json(path, data)
    except (OSError, ValueError, TypeError) as error:
        raise PipelineStateError(f"Cannot delete chapter group: {error}") from error
    document.chapter_groups = [item for item in document.chapter_groups if item.group_id != group_id]
    document.deleted_chapter_groups.append(group)
    document.deleted_chapter_groups.sort(key=lambda item: item.order)
    return group


def validate_group(group, source):
    try:
        folder = Path(group.output_dir).resolve()
        if any(Path(p).resolve().parent != folder for p in (group.txt_path, group.json_path)):
            raise ValueError("Canonical paths are outside the group folder.")
        expected = source[group.start:group.end]
        if sha256_text(source) != group.source_sha256 or sha256_text(expected) != group.text_sha256:
            raise ValueError("Group source is stale; recreate group files in Step 2.")
        for path, fingerprint in ((Path(group.txt_path), group.text_sha256), (Path(group.json_path), group.json_sha256)):
            if not path.is_file():
                raise ValueError(f"Missing {path.name}; recreate group files in Step 2 or delete this group in Step 3.")
            if sha256_file(path) != fingerprint:
                raise ValueError(f"{path.name} was externally modified; recreate group files in Step 2 or delete this group in Step 3.")
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
    group.state.setdefault("resolved_output_dir", str(Path(group.output_dir).resolve().parents[1]))
    atomic_write_json(Path(group.output_dir) / "job_state.json", group.state)


def record_media(group, kind, path):
    from pipeline.document import PipelineDocument
    group.state[kind] = {"path": str(Path(path).resolve()), "fingerprint": PipelineDocument._fingerprint_file(str(path))}
    group.state.pop("video", None)
    save_job_state(group)


def record_job_visuals(group, cover_image, qr_image):
    """Copy the two required Step 4 pictures into this group's job folder.

    Called when the Create Video step starts a group: the byte-identical copy is
    what the renderer hashes, so the page cache and the Step 5 gate can never
    disagree with what the user picked.
    """
    from media.visuals import record_visuals
    record = record_visuals(Path(group.output_dir), cover_image, qr_image)
    group.state["visuals"] = {"sources": {role: record[role]["source"] for role in ("cover", "qr")},
                              "sha256": {role: record[role]["sha256"] for role in ("cover", "qr")}}
    save_job_state(group)
    return record


def require_media(document, group_id):
    group = document.require_group_artifacts(group_id)
    folder = Path(group.output_dir).resolve()
    for kind in ("thumbnail", "audiobook"):
        row = group.state.get(kind, {})
        if not isinstance(row, dict):
            raise PipelineStateError(f"{group.label}: invalid {kind} recovery state; regenerate it in Step 3.")
        current = document._fingerprint_file(row.get("path", ""))
        if (not current or current["size"] < 1 or current != row.get("fingerprint") or
                Path(row["path"]).resolve().parent != folder):
            raise PipelineStateError(f"{group.label}: generate a current {kind} in Step 3 first.")
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
    from media.visuals import available_images
    images = available_images(folder)
    return Step4MediaBundle(group.title, group.label, group.slug, group.output_dir,
                           group.state["thumbnail"]["path"], group.state["audiobook"]["path"],
                           str(folder / f"{group.slug}.mp4"), group.state["thumbnail"]["fingerprint"], group.state["audiobook"]["fingerprint"],
                           str(folder / "audio_chunks" / "manifest.json"), provenance.get("effective_text_sha256", ""),
                           cover_image_path=images.get("cover", ""), qr_image_path=images.get("qr", ""))


def record_tts_provenance(group, processor):
    folder = Path(group.output_dir)
    overrides = folder / "tts_overrides.json"
    group.state["tts_provenance"] = {
        "voice": processor.voice, "plan_sha256": sha256_file(folder / "tts_chunks.json"),
        "overrides_sha256": sha256_file(overrides) if overrides.exists() else "",
        "effective_text_sha256": sha256_text("\n".join(f"{c.order}\0{c.text}" for c in processor.chunks))}


def video_source(media):
    from media.video_pages import source_fingerprint
    try:
        return source_fingerprint(media)
    except RuntimeError as error:
        raise PipelineStateError(str(error)) from error


def record_video(document, group_id, result):
    group = document.require_group_artifacts(group_id)
    if group.state.get("tts_status") != "Completed":
        raise PipelineStateError("Complete every TTS chunk before Step 4; partial audiobooks cannot be rendered.")
    media = require_media(document, group_id)
    group.state["video"] = {"path": str(result.output_path), "fingerprint": document._fingerprint_file(str(result.output_path)),
                            "source": getattr(result, "source", None) or video_source(media), "result": result.to_dict(), "status": "Completed"}
    save_job_state(group)


def require_video(document, group_id):
    group = document.require_group_artifacts(group_id)
    if group.state.get("tts_status") != "Completed":
        raise PipelineStateError("Complete every TTS chunk before Step 4; partial audiobooks cannot be rendered.")
    media = require_media(document, group_id)
    row = group.state.get("video", {})
    fp = document._fingerprint_file(row.get("path", ""))
    if (not fp or fp["size"] <= 0 or fp != row.get("fingerprint") or row.get("source") != video_source(media) or
            Path(row["path"]).resolve() != Path(media.video_path).resolve()):
        raise PipelineStateError(f"{group.label}: create a current video in Step 4 first.")
    return Step5UploadBundle(group.title, group.label, group.output_dir, row["path"], media.thumbnail_path, fp, media.thumbnail_fingerprint)


def job_layout_budget(document, *, style=None):
    """Page budget of the current single-job preparation.

    The band is measured from the real title and from every chapter label a page of
    this job can draw, so the planner and the renderer share one band instead of the
    worst-case reserve.  All ``Chương N`` labels are one line tall, so the identity
    stays stable whether or not the chapter list has been derived yet.
    """
    from media.text_layout import DEFAULT_STYLE, renderer_budget
    from media.video_pages import page_chapter_label
    chapter = str(getattr(document, "job_chapter", "") or "")
    labels = [page_chapter_label(getattr(item, "number", 0), chapter)
              for item in list(getattr(document, "chapters", []) or [])]
    return renderer_budget(style or DEFAULT_STYLE, title=str(getattr(document, "job_title", "") or ""),
                           chapter_labels=[*labels, chapter])


def job_preprocessing_identity(document, settings):
    """Preparation identity of this job, including its own measured page band."""
    from cleaning.tts_text_preprocessor import preprocessing_identity
    return preprocessing_identity(settings, layout=job_layout_budget(document).identity())


def plan_page_summary(label, base, statistics, budget):
    """One-line page-fill summary for the job console.

    Final pages and standalone headings are legitimate short pages and are counted
    separately, so they never look like a planning failure.
    """
    from media.text_layout import LAYOUT_FILL_MIN, LAYOUT_FILL_TARGET
    fills = [float(row["layout"].get("fill_ratio") or 0.0) for row in base if row.get("layout")]
    average = sum(fills) / len(fills) if fills else 0.0
    return (f"{label}: {len(base)} trang, fill trung bình {average:.1%}, thấp nhất "
            f"{statistics['layout_fill_min']:.1%}, cao nhất {statistics['layout_fill_max']:.1%}, "
            f"trang cuối ngắn {statistics['layout_final_underfilled_pages']}, dưới "
            f"{LAYOUT_FILL_MIN:.0%} {statistics['layout_underfilled_pages']}, tràn trang "
            f"{statistics['layout_overflow_pages']}; band {budget.body_height}px ở "
            f"{budget.min_font_size}px, mục tiêu fill {LAYOUT_FILL_TARGET:.0%}")


def prepare_tts(document, group_id, settings, *, cancel_event=None):
    """Cleaning/chunking lives exclusively in Step 3, never canonical files."""
    from cleaning.textclean import CleaningOptions
    from chunking.splitter import (MAX_CHUNK, TTS_CHUNK_SOFT_TARGET, chunk_layout_metadata,
                                   layout_statistics, split_chapters, verify_chunk_integrity)
    from media.tts import TtsChunk
    group = document.require_group_artifacts(group_id)
    source = validate_group(group, document.require_grouping_input())
    from cleaning.tts_prepare import prepare_chapter
    from cleaning.tts_text_preprocessor import preprocessing_identity
    from cleaning.tts_boundaries import meaningful_text
    from media.text_layout import renderer_budget
    from media.video_pages import page_chapter_label
    # The chunk planner and every page of this job share one measured band: the real
    # title plus every chapter label a page can carry replace the worst-case reserve.
    budget = renderer_budget(title=group.title,
                             chapter_labels=[page_chapter_label(row.get("number"), group.label)
                                             for row in group.chapters] + [group.label])
    def check_cancel():
        if cancel_event is not None and cancel_event.is_set():
            raise PipelineStateError("Đã hủy chuẩn bị TTS; các MP3 đã có được giữ lại.")
    check_cancel()
    options = CleaningOptions.for_tts(settings)
    minimum = min(TTS_CHUNK_SOFT_TARGET, max(50, int(settings.min_chunk_chars or 200)))
    # The soft target only seeds the boundary search: the measured page height decides
    # where each chunk really ends, so no chunk is capped at this character count.
    limit = TTS_CHUNK_SOFT_TARGET
    config = {"cleaning": asdict(options), "limit": limit, "minimum": minimum,
              "hard_ceiling": MAX_CHUNK,
              **preprocessing_identity(settings, layout=budget.identity())}
    identity = sha256_text(json.dumps({
        "source": group.text_sha256,
        "source_revision": document.normalized_revision,
        "config": config,
    }, ensure_ascii=False, sort_keys=True))
    folder = Path(group.output_dir)
    path = folder / "tts_chunks.json"
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
        if plan.get("schema_version") != 2 or plan["plan_id"] != identity or plan["group_id"] != group_id or plan.get("config") != config:
            raise ValueError("Changed TTS plan")
        base = plan["chunks"]
        if [c["order"] for c in base] != list(range(1, len(base) + 1)) or not base:
            raise ValueError("Invalid chunk ordering")
        if any(sha256_text(c["text"]) != c["text_sha256"] for c in base):
            raise ValueError("Changed chunk text")
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        chapters = []
        statistics, warnings = {}, []
        first_start = group.chapters[0]["start"] - group.start
        raw_chapters = []
        if first_start > 0 and source[:first_start].strip():
            raw_chapters.append(Chapter(number=0, header_line="", text=source[:first_start]))
        for row in group.chapters:
            body = source[row["body_start"] - group.start:row["end"] - group.start]
            raw_chapters.append(Chapter(number=row["number"], header_line=row["heading"], text=body))
        for chapter in raw_chapters:
            check_cancel()
            prepared, stats, messages = prepare_chapter(chapter, settings)
            chapters.append(prepared)
            for key, value in stats.items():
                statistics[key] = statistics.get(key, 0) + value
            warnings.extend(f"Chapter {chapter.number}: {message}" for message in messages)
        check_cancel()
        chunks, layout_plan, diagnostics = split_chapters(
            chapters, limit, include_header=True, min_chunk=minimum,
            abbreviations=config["preprocessing"]["abbreviations"], layout=budget)
        warnings.extend(d.message for d in diagnostics)
        # Hard safety: the finalized chunks must reproduce the prepared source exactly
        # (no dropped, duplicated or reordered character) before any TTS request.
        verify_chunk_integrity(render_chapters_text(chapters), layout_plan)
        base = [{"order": c.order, "chapter": c.chapter, "text": c.text, "text_sha256": sha256_text(c.text),
                 "layout": dict(c.layout)} for c in chunks]
        if not base:
            raise PipelineStateError(f"{group.label}: no speakable text after cleaning.")
        statistics.update(layout_statistics(layout_plan))
        warnings.append(plan_page_summary(group.label, base, statistics, budget))
        plan = {"schema_version": 2, "group_id": group_id, "plan_id": identity,
                "source_revision": document.normalized_revision, "config": config, "chunks": base,
                "statistics": statistics, "warnings": warnings}
        check_cancel()
        atomic_write_json(path, plan)
    check_cancel()
    plan = dict(plan)
    plan["warnings"] = list(plan.get("warnings", []))
    overrides = {}
    try:
        saved = json.loads((folder / "tts_overrides.json").read_text(encoding="utf-8"))
        if saved["plan_id"] == identity:
            overrides = saved["overrides"]
        elif saved.get("overrides"):
            plan["warnings"].append("Saved TTS overrides belong to an older plan; retained but not applied.")
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    if not isinstance(overrides, dict):
        raise PipelineStateError("Invalid saved TTS overrides; correct the failed chunk text.")
    effective = []
    for row in base:
        text = overrides.get(str(row["order"]), row["text"])
        if not isinstance(text, str) or not meaningful_text(text) or len(text) > MAX_CHUNK:
            raise PipelineStateError("Invalid saved TTS override; correct the failed chunk text.")
        layout = dict(row.get("layout") or {})
        if text != row["text"]:
            # A user-edited replacement must satisfy the same page budget before TTS.
            measurement = budget.measure(text)
            if not measurement.fits:
                raise PipelineStateError(
                    f"Đoạn {row['order']} sau khi sửa vẫn không vừa trang: chars={len(text)}, "
                    f"visible_lines={measurement.visible_lines}, font_size={measurement.font_size}px, "
                    f"body_width={measurement.body_width}px, body_height={measurement.body_height}px, "
                    f"reason={measurement.reason}. Sửa ngắn hơn hoặc tách thành nhiều đoạn.")
            layout = chunk_layout_metadata(budget, text, "override", "user_override")
        effective.append(TtsChunk(row["order"], text, row["chapter"], layout=layout))
    check_cancel()
    group.state["tts_plan_id"] = identity
    return plan, effective


def edit_failed_chunk(document, group_id, settings, order, text):
    group = document.require_group_artifacts(group_id)
    plan, _ = prepare_tts(document, group_id, settings)
    if order not in {int(f["chunk_number"]) for f in group.state.get("failures", [])}:
        raise PipelineStateError("Only a selected failed TTS chunk can be edited.")
    from cleaning.tts_text_preprocessor import TTSPreprocessConfig, preprocess_for_tts
    from cleaning.tts_boundaries import meaningful_text
    from cleaning.textclean import CleaningOptions, clean_text
    from chunking.splitter import MAX_CHUNK
    from media.text_layout import renderer_budget
    from media.video_pages import page_chapter_label
    cleaned, _ = clean_text(text, CleaningOptions.for_tts(settings))
    text = preprocess_for_tts(cleaned, TTSPreprocessConfig.from_settings(settings))
    if not meaningful_text(text) or len(text) > MAX_CHUNK:
        raise PipelineStateError(f"Replacement must be non-empty and at most {MAX_CHUNK} characters.")
    # The edited text is measured against this job's own page band, exactly like the
    # chunks the planner produced for it.
    budget = renderer_budget(title=group.title,
                             chapter_labels=[page_chapter_label(row.get("number"), group.label)
                                             for row in group.chapters] + [group.label])
    measurement = budget.measure(text)
    if not measurement.fits:
        raise PipelineStateError(
            f"Replacement does not fit the page: chars={len(text)}, visible_lines={measurement.visible_lines}, "
            f"font_size={measurement.font_size}px, body_width={measurement.body_width}px, "
            f"body_height={measurement.body_height}px, reason={measurement.reason}. "
            "Shorten the text or split it into several chapters' chunks.")
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
