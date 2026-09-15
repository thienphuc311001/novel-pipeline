"""Optional Gemini service interface for Chinese -> Vietnamese translation.

The whole module is dependency free (``urllib`` only) and optional: without an
API key the application never touches the network, and every failure returns a
clear error while keeping the offline/manual translations untouched.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-2.0-flash"


class GeminiError(RuntimeError):
    """Raised when the Gemini API cannot be used or answered with an error."""


@dataclass
class GeminiSettings:
    api_key: str = ""
    model: str = DEFAULT_MODEL
    target_language: str = "Vietnamese"
    timeout: int = 60
    temperature: float = 0.2

    @property
    def ready(self) -> bool:
        return bool(self.api_key.strip() and self.model.strip())

    def describe(self) -> str:
        if not self.api_key.strip():
            return "Chưa có API key (AI đang tắt)."
        return f"Gemini model: {self.model}"


SYSTEM_PROMPT = (
    "You are a professional literary translator. Translate the given Chinese web-novel "
    "phrases into {language}. Keep names, place names, cultivation terms and titles in a "
    "consistent style. Do not add explanations, notes or extra text: return only the JSON "
    "object described by the schema."
)

USER_PROMPT = (
    "Translate every phrase from Chinese into {language}. "
    "Return a JSON object with a single key \"translations\" whose value is an array of "
    "objects, each having \"phrase\" (the original Chinese text, unchanged) and "
    "\"translation\" (the {language} translation).\n"
    "Phrases:\n{phrases}"
)


def parse_structured_translations(payload: Any) -> Dict[str, str]:
    """Extract a phrase -> translation map from any plausible JSON answer.

    Accepts ``{"translations": [...]}``, a bare list, or a plain
    ``{"phrase": "translation"}`` mapping; entries without a translation are
    ignored instead of producing empty replacements.
    """
    result: Dict[str, str] = {}
    if payload is None:
        return result
    if isinstance(payload, str):
        parsed = _loads(payload)
        return parse_structured_translations(parsed)
    if isinstance(payload, list):
        for item in payload:
            result.update(parse_structured_translations(item))
        return result
    if isinstance(payload, dict):
        for key in ("translations", "items", "results", "data", "output", "translation"):
            if key in payload:
                nested = parse_structured_translations(payload[key])
                if nested:
                    result.update(nested)
        phrase = payload.get("phrase") or payload.get("original") or payload.get("source")
        translation = payload.get("translation") or payload.get("translated") or payload.get("text")
        if isinstance(phrase, str) and isinstance(translation, str) and phrase and translation:
            result.setdefault(phrase, translation)
        if not result:
            for key, value in payload.items():
                if isinstance(value, str) and value.strip() and key.strip():
                    result[key] = value
    return result


def _loads(text: str) -> Any:
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except ValueError:
            return None
    return None


class GeminiClient:
    """Minimal Gemini REST client used by the optional AI translation runner."""

    def __init__(self, settings: GeminiSettings, *, opener=None) -> None:
        self.settings = settings
        self._opener = opener or urllib.request.urlopen

    # ---------------------------------------------------------------- calls
    def build_request(self, phrases: Sequence[str]) -> urllib.request.Request:
        language = self.settings.target_language or "Vietnamese"
        body = {
            "system_instruction": {
                "parts": [{"text": SYSTEM_PROMPT.format(language=language)}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": USER_PROMPT.format(
                                language=language,
                                phrases=json.dumps(list(phrases), ensure_ascii=False, indent=1),
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {
                "temperature": self.settings.temperature,
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "OBJECT",
                    "properties": {
                        "translations": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "phrase": {"type": "STRING"},
                                    "translation": {"type": "STRING"},
                                },
                                "required": ["phrase", "translation"],
                            },
                        }
                    },
                    "required": ["translations"],
                },
            },
        }
        url = f"{API_BASE}/{self.settings.model}:generateContent?key={self.settings.api_key}"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        return urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

    def translate_phrases(self, phrases: Sequence[str], *, cancel=None) -> Dict[str, str]:
        """Translate a batch of phrases, raising :class:`GeminiError` on failure."""
        phrases = [phrase for phrase in phrases if phrase.strip()]
        if not phrases:
            return {}
        if not self.settings.ready:
            raise GeminiError("Chưa cấu hình API key hoặc model cho Gemini.")
        if cancel is not None and cancel():
            raise GeminiError("Đã huỷ theo yêu cầu.")
        request = self.build_request(phrases)
        try:
            with self._opener(request, timeout=self.settings.timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as error:
            detail = ""
            try:
                detail = error.read().decode("utf-8", errors="replace")[:400]
            except Exception:  # pragma: no cover - best effort
                detail = str(error)
            raise GeminiError(f"Gemini trả về lỗi HTTP {error.code}: {detail}") from error
        except urllib.error.URLError as error:
            raise GeminiError(f"Không kết nối được Gemini: {error.reason}") from error
        except TimeoutError as error:
            raise GeminiError(f"Hết thời gian chờ Gemini ({self.settings.timeout}s).") from error

        try:
            payload = json.loads(raw)
        except ValueError as error:
            raise GeminiError(f"Phản hồi Gemini không phải JSON: {raw[:200]}") from error

        text = self._extract_text(payload)
        if text is None:
            raise GeminiError("Phản hồi Gemini không chứa nội dung văn bản.")
        parsed = _loads(text)
        translations = parse_structured_translations(parsed)
        if not translations:
            raise GeminiError("Gemini không trả về bản dịch nào dùng được.")
        return translations

    @staticmethod
    def _extract_text(payload: Dict[str, Any]) -> Optional[str]:
        candidates = payload.get("candidates") or []
        for candidate in candidates:
            content = candidate.get("content") or {}
            for part in content.get("parts") or []:
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    return text
        prompt_feedback = payload.get("promptFeedback") or {}
        if prompt_feedback.get("blockReason"):
            raise GeminiError(f"Gemini chặn yêu cầu: {prompt_feedback['blockReason']}")
        return None


def is_network_available(timeout: float = 2.5) -> bool:
    """Quick connectivity probe used to explain failures to the user."""
    try:
        with urllib.request.urlopen("https://generativelanguage.googleapis.com/", timeout=timeout):
            return True
    except Exception:
        return False

