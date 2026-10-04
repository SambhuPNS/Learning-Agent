"""Minimal Gemini REST client. The API key never leaves the backend."""

import asyncio
import base64
import io
import json
import logging
import re
import time
import wave

import httpx

from .config import GEMINI_API_KEY, GEMINI_FALLBACK_MODELS, GEMINI_MODEL, GEMINI_TTS_MODEL, GEMINI_TTS_VOICE

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"
RETRYABLE = {429, 500, 502, 503, 504}
COOLDOWN_SECONDS = 90
log = logging.getLogger("tutor.gemini")
_cooldown_until: dict[str, float] = {}


class GeminiError(RuntimeError):
    pass


async def _generate(model: str, body: dict, timeout: float, retries: int = 1) -> dict:
    if not GEMINI_API_KEY:
        raise GeminiError("GEMINI_API_KEY is not configured")
    for attempt in range(retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{API_ROOT}/{model}:generateContent",
                    headers={"x-goog-api-key": GEMINI_API_KEY},
                    json=body,
                )
        except httpx.HTTPError as exc:
            raise GeminiError(f"Could not reach Gemini: {exc}") from exc
        if response.status_code < 400:
            return response.json()
        if response.status_code in RETRYABLE:
            _cooldown_until[model] = time.monotonic() + COOLDOWN_SECONDS
        if response.status_code not in RETRYABLE or attempt == retries:
            raise GeminiError(f"Gemini {model} returned {response.status_code}: {response.text[:400]}")
        await asyncio.sleep(1.2 * (attempt + 1))
    raise GeminiError(f"Gemini {model} failed")


async def _generate_with_fallback(body: dict, timeout: float) -> dict:
    chain = [GEMINI_MODEL] + [m for m in GEMINI_FALLBACK_MODELS if m != GEMINI_MODEL]
    now = time.monotonic()
    # Recently overloaded models go to the back of the queue instead of being retried first.
    models = [m for m in chain if _cooldown_until.get(m, 0) <= now] + [m for m in chain if _cooldown_until.get(m, 0) > now]
    last_error: GeminiError | None = None
    for model in models:
        try:
            return await _generate(model, body, timeout, retries=0)
        except GeminiError as exc:
            last_error = exc
            log.warning("Model %s unavailable, trying next: %s", model, str(exc)[:120])
    raise last_error or GeminiError("No Gemini model configured")


def _parts(data: dict) -> list[dict]:
    candidates = data.get("candidates") or []
    if not candidates:
        raise GeminiError(f"Gemini returned no candidates: {json.dumps(data)[:300]}")
    return candidates[0].get("content", {}).get("parts", [])


async def generate_json(system: str, parts: list[dict], schema: dict, timeout: float = 60, thinking: str = "low") -> dict:
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"responseMimeType": "application/json", "responseJsonSchema": schema,
                             "thinkingConfig": {"thinkingLevel": thinking}},
    }
    data = await _generate_with_fallback(body, timeout)
    text = "".join(part.get("text", "") for part in _parts(data) if not part.get("thought"))
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise GeminiError(f"Gemini returned invalid JSON: {text[:200]}") from exc


def _pcm_to_wav(pcm: bytes, rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm)
    return buffer.getvalue()


async def synthesize(text: str) -> bytes:
    body = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": GEMINI_TTS_VOICE}}},
        },
    }
    data = await _generate(GEMINI_TTS_MODEL, body, timeout=60, retries=2)
    for part in _parts(data):
        inline = part.get("inlineData")
        if not inline:
            continue
        audio = base64.b64decode(inline["data"])
        if audio[:4] == b"RIFF":
            return audio
        rate_match = re.search(r"rate=(\d+)", inline.get("mimeType", ""))
        return _pcm_to_wav(audio, int(rate_match.group(1)) if rate_match else 24000)
    raise GeminiError("Gemini TTS returned no audio")
