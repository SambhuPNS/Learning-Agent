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
    GEMINI_FALLBACK_MODELS, GEMINI_FAST_MODEL, GEMINI_MODEL, GEMINI_TTS_MODEL, GEMINI_TTS_VOICE,
    GOOGLE_CLOUD_PROJECT, VERTEX_AI_LOCATION,
)

RETRYABLE = {429, 500, 502, 503, 504}
COOLDOWN_SECONDS = 90
# Learners are school students: block sexual content at the lowest level and other harms from medium.
SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_LOW_AND_ABOVE"},
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
]
SAFETY_FINISH_REASONS = {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII"}
log = logging.getLogger("tutor.vertex")
_cooldown_until: dict[str, float] = {}
_auth_lock = Lock()


class GeminiError(RuntimeError):
    pass


class GeminiSafetyBlock(GeminiError):
    """Vertex AI's safety filters blocked the prompt or the reply."""


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
        started = time.monotonic()
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
            log.info("Vertex AI %s answered in %.1fs", model, time.monotonic() - started)
            return response.json()
        if response.status_code in RETRYABLE:
            _cooldown_until[model] = time.monotonic() + COOLDOWN_SECONDS
        if response.status_code not in RETRYABLE or attempt == retries:
            raise GeminiError(f"Vertex AI {model} returned {response.status_code}: {response.text[:400]}")
        await asyncio.sleep(1.2 * (attempt + 1))
    raise GeminiError(f"Vertex AI {model} failed")


def _cooling(model: str) -> bool:
    return _cooldown_until.get(model, 0) > time.monotonic()


async def _generate_with_fallback(body: dict, timeout: float, chain: list[str]) -> dict:
    chain = list(dict.fromkeys(model for model in chain if model))
    # Recently overloaded models go to the back of the queue instead of being retried first.
    models = [m for m in chain if not _cooling(m)] + [m for m in chain if _cooling(m)]
    last_error: GeminiError | None = None
    for model in models:
        try:
            return await _generate(model, body, timeout, retries=0)
        except GeminiError as exc:
            last_error = exc
            log.warning("Model %s unavailable, trying next: %s", model, str(exc)[:120])
    raise last_error or GeminiError("No Gemini model configured")


async def _generate_with_backup(body: dict, timeout: float, backup_after: float) -> dict:
    """Asks the main model; if it is slow or fails, also asks the fast model. The first good reply wins."""
    main_chain = [GEMINI_MODEL, *GEMINI_FALLBACK_MODELS]
    if not GEMINI_FAST_MODEL or GEMINI_FAST_MODEL == GEMINI_MODEL:
        return await _generate_with_fallback(body, timeout, main_chain)
    if _cooling(GEMINI_MODEL):
        return await _generate_with_fallback(body, timeout, [GEMINI_FAST_MODEL, *main_chain])
    tasks = {asyncio.create_task(_generate_with_fallback(body, timeout, main_chain))}
    backup_started = False
    last_error: BaseException | None = None
    try:
        while tasks:
            done, tasks = await asyncio.wait(tasks, timeout=None if backup_started else backup_after,
                                             return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                if task.exception() is None:
                    return task.result()
                last_error = task.exception()
            if not backup_started:
                backup_started = True
                log.info("%s is %s, asking %s as well", GEMINI_MODEL, "failing" if done else "slow", GEMINI_FAST_MODEL)
                tasks.add(asyncio.create_task(_generate(GEMINI_FAST_MODEL, body, timeout, retries=0)))
        if last_error is None:
            raise GeminiError("Vertex AI returned no reply")
        raise last_error
    finally:
        for task in tasks:
            task.cancel()


def _parts(data: dict) -> list[dict]:
    block_reason = (data.get("promptFeedback") or {}).get("blockReason")
    if block_reason:
        raise GeminiSafetyBlock(f"Vertex AI blocked the prompt: {block_reason}")
    candidates = data.get("candidates") or []
    if not candidates:
        raise GeminiError(f"Gemini returned no candidates: {json.dumps(data)[:300]}")
    if candidates[0].get("finishReason") in SAFETY_FINISH_REASONS:
        raise GeminiSafetyBlock(f"Vertex AI blocked the reply: {candidates[0]['finishReason']}")
    return candidates[0].get("content", {}).get("parts", [])


async def generate_json(system: str, parts: list[dict], schema: dict, timeout: float = 60, thinking: str = "low", *,
                        fast: bool = False, backup_after: float | None = None) -> dict:
    """fast: short classification jobs go to the fast model first.
    backup_after: if the main model has not answered after this many seconds, ask the fast model too."""
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"responseMimeType": "application/json", "responseJsonSchema": schema,
                             "thinkingConfig": {"thinkingLevel": thinking}},
        "safetySettings": SAFETY_SETTINGS,
    }
    if backup_after is not None:
        data = await _generate_with_backup(body, timeout, backup_after)
    elif fast:
        data = await _generate_with_fallback(body, timeout, [GEMINI_FAST_MODEL, GEMINI_MODEL])
    else:
        data = await _generate_with_fallback(body, timeout, [GEMINI_MODEL, *GEMINI_FALLBACK_MODELS])
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
