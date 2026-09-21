"""Qt-free preparation of the legacy audiobook bundle."""
from __future__ import annotations

from chapters import build_patterns
from chapters.detector import detect_chapters
from cleaning.tts_prepare import prepare_chapter
from cleaning.tts_text_preprocessor import preprocessing_identity
from chunking.splitter import (TTS_CHUNK_SOFT_TARGET, layout_statistics, split_chapters,
                               verify_chunk_integrity)
from media.artifacts import require_artifact_root, sha256_text, write_step3_artifacts
from media.groups import job_layout_budget, plan_page_summary
from pipeline.document import (Chapter, PipelineStateError, derive_chapters_from_text,
                               render_chapters_text)


def prepare_legacy_bundle(document, settings, *, cancel_event=None):
    """Prepare a document snapshot; callers publish it only if still current."""
    def check_cancel():
        if cancel_event is not None and cancel_event.is_set():
            raise PipelineStateError("Đã hủy chuẩn bị TTS; nguồn và MP3 cũ được giữ lại.")
    check_cancel()
    source = document.require_grouping_input()
    patterns = build_patterns(settings)
    chapters = derive_chapters_from_text(source, patterns, source_name='pipeline')
    if not chapters:
        raise PipelineStateError('No chapter boundaries found in the current pipeline output.')
    _, preamble, _ = detect_chapters(source, patterns)
    preamble = "\n".join(preamble)
    if preamble.strip():
        chapters.insert(0, Chapter(number=0, header_line='', text=preamble))
    prepared_chapters, statistics, warnings = [], {}, []
    for chapter in chapters:
        check_cancel()
        prepared, stats, messages = prepare_chapter(chapter, settings)
        prepared_chapters.append(prepared)
        for key, value in stats.items():
            statistics[key] = statistics.get(key, 0) + value
        warnings.extend(f'Chapter {chapter.number}: {m}' for m in messages)
    check_cancel()
    minimum = min(TTS_CHUNK_SOFT_TARGET, max(50, int(settings.min_chunk_chars or 200)))
    # The soft target only seeds the boundary search; the measured page height of this
    # job's own band decides every chunk boundary before any TTS request.
    limit = TTS_CHUNK_SOFT_TARGET
    budget = job_layout_budget(document)
    identity = preprocessing_identity(settings, layout=budget.identity())
    chunks, layout_plan, diagnostics = split_chapters(prepared_chapters, limit, include_header=True,
                                                     min_chunk=minimum,
                                                     abbreviations=identity['preprocessing']['abbreviations'],
                                                     layout=budget)
    if not chunks:
        raise PipelineStateError('No speakable text after TTS preprocessing.')
    # Hard safety: the finalized chunks must reproduce the prepared text exactly.
    verify_chunk_integrity(render_chapters_text(prepared_chapters), layout_plan)
    statistics.update(layout_statistics(layout_plan))
    base = [{"order": c.order, "chapter": c.chapter, "text": c.text, "text_sha256": sha256_text(c.text),
             "layout": dict(c.layout)} for c in chunks]
    warnings.append(plan_page_summary(document.job_chapter or document.job_title, base, statistics, budget))
    document.chapters = prepared_chapters
    document.set_cleaned_output(render_chapters_text(prepared_chapters))
    document.chunks = chunks
    document.diagnostics.extend(diagnostics)
    check_cancel()
    bundle = write_step3_artifacts(document, require_artifact_root(settings, document.input_directory),
                                   title=document.job_title, chapter=document.job_chapter,
                                   chunk_limit=limit, tts_preparation=identity)
    document.set_step3_artifacts(bundle)
    return document, statistics, warnings
