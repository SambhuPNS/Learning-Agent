"""Vertex AI transport tests: no live credentials or model calls."""

import asyncio
import base64
import json
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import httpx
import pytest
from google.auth.exceptions import DefaultCredentialsError
from google.oauth2.credentials import Credentials

from app import config, gemini


@pytest.fixture
def vertex(monkeypatch):
    monkeypatch.setattr(gemini, "GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setattr(gemini, "VERTEX_AI_LOCATION", "global")
    credentials = Credentials(
        token="test-token",
        expiry=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1),
    )
    default = Mock(return_value=(credentials, "adc-project"))
    monkeypatch.setattr(gemini.google.auth, "default", default)
    gemini._credentials.cache_clear()
    gemini._cooldown_until.clear()
    yield credentials, default
    gemini._credentials.cache_clear()
    gemini._cooldown_until.clear()


def mock_transport(monkeypatch, handler):
    client = httpx.AsyncClient
    monkeypatch.setattr(
        gemini.httpx, "AsyncClient",
        lambda **kwargs: client(transport=httpx.MockTransport(handler), **kwargs),
    )


@pytest.mark.parametrize("location,host", [
    ("global", "aiplatform.googleapis.com"),
    ("us-central1", "us-central1-aiplatform.googleapis.com"),
])
def test_vertex_endpoint_and_adc_headers(vertex, monkeypatch, location, host):
    monkeypatch.setattr(gemini, "VERTEX_AI_LOCATION", location)
    body = {"contents": [{"role": "user", "parts": [{"text": "Hello"}]}]}

    def handler(request):
        assert str(request.url) == (
            f"https://{host}/v1/projects/test-project/locations/{location}"
            "/publishers/google/models/test-model:generateContent"
        )
        assert request.headers["authorization"] == "Bearer test-token"
        assert "x-goog-api-key" not in request.headers
        assert json.loads(request.content) == body
        return httpx.Response(200, json={"candidates": []})

    mock_transport(monkeypatch, handler)
    assert asyncio.run(gemini._generate("test-model", body, 5)) == {"candidates": []}
    vertex[1].assert_called_once_with(scopes=["https://www.googleapis.com/auth/cloud-platform"])


def test_expired_credentials_refresh_and_are_cached(vertex, monkeypatch):
    credentials, default = vertex
    headers = gemini._authorized_headers("https://aiplatform.googleapis.com")
    assert headers["authorization"] == "Bearer test-token"
    credentials.expiry = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)

    def refresh(request):
        credentials.token = "refreshed-token"
        credentials.expiry = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)

    refresh_mock = Mock(side_effect=refresh)
    monkeypatch.setattr(credentials, "refresh", refresh_mock)
    assert gemini._authorized_headers("https://aiplatform.googleapis.com")["authorization"] == "Bearer refreshed-token"
    refresh_mock.assert_called_once()
    default.assert_called_once()


def test_missing_adc_is_explicit_error(vertex):
    vertex[1].side_effect = DefaultCredentialsError("No local credentials")
    with pytest.raises(gemini.GeminiError, match="Application Default Credentials"):
        asyncio.run(gemini._generate("test-model", {}, 5))


def test_missing_project_uses_mock_and_rejects_direct_calls(monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_CLOUD_PROJECT", "")
    monkeypatch.setattr(gemini, "GOOGLE_CLOUD_PROJECT", "")
    assert not config.gemini_enabled()
    with pytest.raises(gemini.GeminiError, match="GOOGLE_CLOUD_PROJECT"):
        asyncio.run(gemini._generate("test-model", {}, 5))


def test_json_and_fallback_preserve_request_schema(vertex, monkeypatch):
    monkeypatch.setattr(gemini, "GEMINI_MODEL", "primary")
    monkeypatch.setattr(gemini, "GEMINI_FALLBACK_MODELS", ["fallback"])
    schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
    calls = []

    def handler(request):
        calls.append(request.url.path)
        body = json.loads(request.content)
        assert body["systemInstruction"]["parts"] == [{"text": "System"}]
        assert body["generationConfig"]["responseJsonSchema"] == schema
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        assert body["safetySettings"] == gemini.SAFETY_SETTINGS
        if len(calls) == 1:
            return httpx.Response(429, json={"error": {"message": "Busy"}})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": '{"answer":"ok"}'}]}}]})

    mock_transport(monkeypatch, handler)
    assert asyncio.run(gemini.generate_json("System", [{"text": "Question"}], schema)) == {"answer": "ok"}
    assert calls[0].endswith("/primary:generateContent")
    assert calls[1].endswith("/fallback:generateContent")
    assert "primary" in gemini._cooldown_until


def test_vertex_http_errors_are_surfaced(vertex, monkeypatch):
    mock_transport(monkeypatch, lambda request: httpx.Response(403, json={"error": {"message": "Permission denied"}}))
    with pytest.raises(gemini.GeminiError, match="Vertex AI test-model returned 403"):
        asyncio.run(gemini._generate("test-model", {}, 5))


def test_vertex_tts_returns_wav(vertex, monkeypatch):
    pcm = b"\x00\x00" * 100

    def handler(request):
        assert request.url.path.endswith(f"/{gemini.GEMINI_TTS_MODEL}:generateContent")
        assert json.loads(request.content)["generationConfig"]["responseModalities"] == ["AUDIO"]
        assert json.loads(request.content)["contents"][0]["role"] == "user"
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{
            "inlineData": {"mimeType": "audio/pcm;rate=24000", "data": base64.b64encode(pcm).decode()},
        }]}}]})

    mock_transport(monkeypatch, handler)
    audio = asyncio.run(gemini.synthesize("Hello"))
    assert audio[:4] == b"RIFF"
    assert audio.endswith(pcm)


def _reply(text: str) -> httpx.Response:
    return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]})


def _model_of(request: httpx.Request) -> str:
    return request.url.path.rsplit("/", 1)[-1].split(":")[0]


@pytest.fixture
def two_models(vertex, monkeypatch):
    monkeypatch.setattr(gemini, "GEMINI_MODEL", "main")
    monkeypatch.setattr(gemini, "GEMINI_FALLBACK_MODELS", [])
    monkeypatch.setattr(gemini, "GEMINI_FAST_MODEL", "fast")


def test_slow_main_model_is_backed_up_by_fast_model(two_models, monkeypatch):
    calls = []

    async def handler(request):
        calls.append(_model_of(request))
        if _model_of(request) == "main":
            await asyncio.sleep(5)
            return _reply('{"from": "main"}')
        return _reply('{"from": "fast"}')

    mock_transport(monkeypatch, handler)
    started = time.monotonic()
    result = asyncio.run(gemini.generate_json("S", [{"text": "Q"}], {"type": "object"}, backup_after=0.05))
    assert result == {"from": "fast"}
    assert calls == ["main", "fast"]
    assert time.monotonic() - started < 2


def test_quick_main_model_reply_does_not_ask_backup(two_models, monkeypatch):
    calls = []
    mock_transport(monkeypatch, lambda request: calls.append(_model_of(request)) or _reply('{"from": "main"}'))
    assert asyncio.run(gemini.generate_json("S", [{"text": "Q"}], {"type": "object"}, backup_after=5)) == {"from": "main"}
    assert calls == ["main"]


def test_failing_main_model_switches_to_fast_model_at_once(two_models, monkeypatch):
    def handler(request):
        if _model_of(request) == "main":
            return httpx.Response(503, json={"error": {"message": "Overloaded"}})
        return _reply('{"from": "fast"}')

    mock_transport(monkeypatch, handler)
    assert asyncio.run(gemini.generate_json("S", [{"text": "Q"}], {"type": "object"}, backup_after=30)) == {"from": "fast"}
    assert "main" in gemini._cooldown_until


def test_fast_jobs_fall_back_to_main_model(two_models, monkeypatch):
    calls = []

    def handler(request):
        calls.append(_model_of(request))
        if _model_of(request) == "fast":
            return httpx.Response(404, json={"error": {"message": "Publisher model not found"}})
        return _reply('{"from": "main"}')

    mock_transport(monkeypatch, handler)
    assert asyncio.run(gemini.generate_json("S", [{"text": "Q"}], {"type": "object"}, fast=True)) == {"from": "main"}
    assert calls == ["fast", "main"]
