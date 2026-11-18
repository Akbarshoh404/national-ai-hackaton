"""LLM providers: Gemini (google-genai) and a local model served by Ollama.

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

import httpx

from app.core.config import settings

log = logging.getLogger("raft.llm")

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


def transcribe(audio: bytes, mime_type: str, timeout: float | None = None) -> str | None:
    """Speech → text (Uzbek/Russian). Returns None without a key or on failure."""
    if not available():
        return None
    from google.genai import types

    parts = [types.Part.from_bytes(data=audio, mime_type=mime_type),
             "Transcribe this voice note verbatim. It is in Uzbek or Russian. Return only the transcript."]
    out = _call(parts, json_mode=False, temperature=0.0, timeout=timeout or 30)
    return out.strip() if out else None


# --------------------------------------------------------------------------- #
# Local provider: Ollama (used only for extraction / input parsing)            #
# --------------------------------------------------------------------------- #

LOCAL_DOWN_COOLDOWN_S = 30.0
_local_down_until = 0.0
_local_status_cache: tuple[float, bool, str] | None = None


class LocalLLMError(Exception):
    """Local model failed: `kind` is "down", "timeout", "http" or "invalid_json"."""

    def __init__(self, kind: str, detail: str = ""):
        super().__init__(f"{kind}: {detail}")
        self.kind = kind


def local_label() -> str:
    return f"local:{settings.LOCAL_MODEL}"


def local_suspended() -> bool:
    """True while Ollama is in its cooldown after a connection failure (avoids paying a timeout per post)."""
    return time.monotonic() < _local_down_until


def local_chat_json(messages: list[dict[str, str]], timeout: float | None = None) -> Any:
    """`POST {OLLAMA_URL}/api/chat` (stream off, JSON format, temperature 0, 2k context) → parsed JSON.

    Raises `LocalLLMError` on connection failure, timeout, HTTP error or non-JSON output.
    """
    global _local_down_until
    if local_suspended():
        raise LocalLLMError("down", "cooling down after a connection failure")
    payload = {"model": settings.LOCAL_MODEL, "messages": messages, "stream": False, "format": "json",
               "options": {"temperature": 0, "num_ctx": 2048}}
    try:
        resp = httpx.post(f"{settings.OLLAMA_URL.rstrip('/')}/api/chat", json=payload,
                          timeout=timeout or settings.LOCAL_TIMEOUT_S)
    except httpx.TimeoutException as exc:
        raise LocalLLMError("timeout", type(exc).__name__) from exc
    except httpx.TransportError as exc:  # connection refused, DNS, reset ...
        _local_down_until = time.monotonic() + LOCAL_DOWN_COOLDOWN_S
        raise LocalLLMError("down", type(exc).__name__) from exc
    if resp.status_code != 200:
        raise LocalLLMError("http", f"{resp.status_code} {resp.text[:120]}")
    try:
        content = resp.json()["message"]["content"]
    except (ValueError, KeyError, TypeError) as exc:
        raise LocalLLMError("invalid_json", "unexpected Ollama response") from exc
    parsed = parse_json(content)
    if parsed is None:
        raise LocalLLMError("invalid_json", content[:120] if isinstance(content, str) else "")
    return parsed


def local_status(cache_s: float = 30.0) -> tuple[bool, str]:
    """(reachable with the model pulled, detail). Cached so /health stays fast."""
    global _local_status_cache
    now = time.monotonic()
    if _local_status_cache and now - _local_status_cache[0] < cache_s:
        return _local_status_cache[1], _local_status_cache[2]
    model = settings.LOCAL_MODEL
    try:
        r = httpx.get(f"{settings.OLLAMA_URL.rstrip('/')}/api/tags", timeout=1.5)
        names = {m.get("name") for m in r.json().get("models", [])}
        ok = model in names or f"{model}:latest" in names
        detail = f"{model} ready" if ok else f"Ollama reachable but `{model}` is not pulled (ollama pull {model})"
    except Exception as exc:
        ok, detail = False, f"Ollama not reachable at {settings.OLLAMA_URL} ({type(exc).__name__})"
    _local_status_cache = (now, ok, detail)
    return ok, detail
