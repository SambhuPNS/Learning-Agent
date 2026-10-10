"""Gemini on Vertex AI, authenticated with Application Default Credentials."""

import asyncio
import base64
import io
import json
import logging
import re
import time
import wave
from functools import lru_cache
from threading import Lock

import google.auth
import httpx
from google.auth.credentials import Credentials
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request

from .config import (
    GEMINI_FALLBACK_MODELS, GEMINI_MODEL, GEMINI_TTS_MODEL, GEMINI_TTS_VOICE,
    GOOGLE_CLOUD_PROJECT, VERTEX_AI_LOCATION,
)

RETRYABLE = {429, 500, 502, 503, 504}
COOLDOWN_SECONDS = 90
log = logging.getLogger("tutor.vertex")
_cooldown_until: dict[str, float] = {}
_auth_lock = Lock()


class GeminiError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _credentials() -> Credentials:
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    return credentials


def _authorized_headers(url: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    with _auth_lock:
        _credentials().before_request(Request(), "POST", url, headers)
    return headers


async def _generate(model: str, body: dict, timeout: float, retries: int = 1) -> dict:
    if not GOOGLE_CLOUD_PROJECT or not VERTEX_AI_LOCATION:
        raise GeminiError("GOOGLE_CLOUD_PROJECT and VERTEX_AI_LOCATION are required for Vertex AI")
    host = "aiplatform.googleapis.com" if VERTEX_AI_LOCATION == "global" else f"{VERTEX_AI_LOCATION}-aiplatform.googleapis.com"
    url = (f"https://{host}/v1/projects/{GOOGLE_CLOUD_PROJECT}/locations/{VERTEX_AI_LOCATION}"
           f"/publishers/google/models/{model}:generateContent")
    for attempt in range(retries + 1):
        try:
            headers = await asyncio.to_thread(_authorized_headers, url)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    url,
                    headers=headers,
                    json=body,
                )
        except GoogleAuthError as exc:
            raise GeminiError("Vertex AI authentication failed. Configure Application Default Credentials "
                              "locally or attach an authorized runtime service account.") from exc
        except httpx.HTTPError as exc:
            raise GeminiError(f"Could not reach Vertex AI: {exc}") from exc
        if response.status_code < 400:
            return response.json()
        if response.status_code in RETRYABLE:
            _cooldown_until[model] = time.monotonic() + COOLDOWN_SECONDS
        if response.status_code not in RETRYABLE or attempt == retries:
            raise GeminiError(f"Vertex AI {model} returned {response.status_code}: {response.text[:400]}")
        await asyncio.sleep(1.2 * (attempt + 1))
    raise GeminiError(f"Vertex AI {model} failed")


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
        "contents": [{"role": "user", "parts": [{"text": text}]}],
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
