"""Thin provider wrapper around Gemini (google-genai).

The LLM only reads and explains; it never produces numbers that the API returns
as facts. Every caller must handle a `None` result with a deterministic fallback,
so the whole API works without an API key.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from app.config import settings

log = logging.getLogger("bozorpilot.llm")

_client: Any = None
_last_error: str | None = None
_last_ok: float | None = None


def available() -> bool:
    """True when an API key is configured and the SDK imports."""
    if not settings.GEMINI_API_KEY:
        return False
    try:
        import google.genai  # noqa: F401
    except ImportError:
        return False
    return True


def status() -> tuple[str, str | None]:
    if not settings.GEMINI_API_KEY:
        return "not_configured", "GEMINI_API_KEY not set; deterministic fallbacks in use"
    if _last_error and (_last_ok is None):
        return "error", _last_error
    return "ok", settings.GEMINI_MODEL


def _get_client() -> Any:
    global _client
    if _client is None:
        from google import genai

        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


def _call(contents: Any, *, json_mode: bool, temperature: float, timeout: float | None,
          system: str | None = None) -> str | None:
    global _last_error, _last_ok
    if not available():
        return None
    from google.genai import types

    cfg = types.GenerateContentConfig(
        temperature=temperature,
        response_mime_type="application/json" if json_mode else "text/plain",
        system_instruction=system,
        http_options=types.HttpOptions(timeout=int((timeout or settings.LLM_TIMEOUT_S) * 1000)),
    )
    try:
        resp = _get_client().models.generate_content(model=settings.GEMINI_MODEL, contents=contents, config=cfg)
        _last_ok = time.time()
        _last_error = None
        return resp.text
    except Exception as exc:  # provider/network errors -> fallback
        _last_error = f"{type(exc).__name__}: {str(exc)[:160]}"
        log.warning("llm call failed: %s", _last_error)
        return None


def parse_json(text: str | None) -> Any:
    """Parse JSON from a model response, tolerating ```json fences."""
    if not text:
        return None
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        return None


def generate_json(prompt: str, *, system: str | None = None, temperature: float = 0.0,
                  timeout: float | None = None) -> Any:
    """JSON-mode completion. Returns parsed JSON or None."""
    return parse_json(_call(prompt, json_mode=True, temperature=temperature, timeout=timeout, system=system))


def generate_text(prompt: str, *, system: str | None = None, temperature: float = 0.2,
                  timeout: float | None = None) -> str | None:
    """Plain-text completion. Returns text or None."""
    out = _call(prompt, json_mode=False, temperature=temperature, timeout=timeout, system=system)
    return out.strip() if out else None


def vision_json(image: bytes, mime_type: str, prompt: str, timeout: float | None = None) -> Any:
    """Image + prompt → parsed JSON (used for invoice OCR). Returns None without a key."""
    if not available():
        return None
    from google.genai import types

    parts = [types.Part.from_bytes(data=image, mime_type=mime_type), prompt]
    return parse_json(_call(parts, json_mode=True, temperature=0.0, timeout=timeout or 30))
