"""Shared safe clean + preprocessing preparation for both audiobook paths."""
from __future__ import annotations

from copy import copy
from .textclean import CleaningOptions, clean_text
from .tts_text_preprocessor import (TTSPreprocessConfig, format_diagnostic_matches,
                                    preprocess_with_diagnostics)


def prepare_chapter(chapter, settings):
    """Return a new chapter and diagnostics; never edit the upstream chapter."""
    prepared = copy(chapter)
    options = CleaningOptions.for_tts(settings)
    config = TTSPreprocessConfig.from_settings(settings)
    body, clean_report = clean_text(chapter.text or "", options)
    header, header_clean = clean_text(chapter.header_line or "", options)
    body_result = preprocess_with_diagnostics(body, config)
    header_result = preprocess_with_diagnostics(header, config)
    # A glued heading repaired by the sanitizer can expose initial body text.
    header_parts = header_result.text.split('\n\n', 1)
    prepared.header_line = header_parts[0]
    prepared.text = ((header_parts[1] + '\n\n') if len(header_parts) > 1 else '') + body_result.text
    prepared.char_count = len(prepared.text)
    statistics = {}
    for report in (header_result, body_result):
        for key, value in report.statistics.items():
            statistics[key] = statistics.get(key, 0) + value
    statistics['custom_clean_rule_hits'] = clean_report.custom_rule_hits + header_clean.custom_rule_hits
    reports = (("header", header_result), ("body", body_result))
    details = [
        {**detail, "section": section}
        for section, report in reports
        for detail in report.diagnostics
    ]
    mojibake = [detail for detail in details if detail.get("rule") != "replacement-char"]
    replacements = [detail for detail in details if detail.get("rule") == "replacement-char"]
    messages = format_diagnostic_matches(mojibake)
    messages.extend(format_diagnostic_matches(replacements, "replacement character"))
    messages.extend(
        warning
        for report in (header_result, body_result)
        for warning in report.warnings
        if not warning.startswith("possible mojibake") and not warning.startswith("replacement character")
    )
    return prepared, statistics, messages
