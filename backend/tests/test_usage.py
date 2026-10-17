"""AI usage tracking: token counts per Gemini call, who and what each call was for, and the teacher's report."""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import gemini, homework, usage
from app.main import app
from app.store import store

client = TestClient(app)
USAGE = {"promptTokenCount": 120, "candidatesTokenCount": 30, "thoughtsTokenCount": 50, "totalTokenCount": 200,
         "cachedContentTokenCount": 10}


def reply(text='{"ok": true}', usage_metadata=USAGE, **extra):
    return {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}],
            "usageMetadata": usage_metadata, **extra}


@pytest.fixture
def vertex(monkeypatch):
    """A fake Vertex AI endpoint whose behaviour each test chooses."""
    state = {"status": 200, "payload": reply(), "hang": False}

    class Response:
        def __init__(self):
            self.status_code, self.text = state["status"], "boom"

        def json(self):
            return state["payload"]

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, headers=None, json=None):
            if state["hang"]:
                await asyncio.sleep(30)
            return Response()

    monkeypatch.setattr(gemini.httpx, "AsyncClient", Client)
    monkeypatch.setattr(gemini, "GOOGLE_CLOUD_PROJECT", "demo-project")
    monkeypatch.setattr(gemini, "VERTEX_AI_LOCATION", "global")
    monkeypatch.setattr(gemini, "_authorized_headers", lambda url: {})
    store.data["llmCalls"] = []
    return state


def calls(trace=None):
    rows, _ = store.llm_calls_since("2000-01-01", 1000)
    return [row for row in rows if trace is None or row["traceId"] == trace]


def ask(purpose="tutor.step", **kwargs):
    return asyncio.run(gemini.generate_json("system", [{"text": "hi"}], {}, purpose=purpose, **kwargs))


def test_trace_header_is_parsed():
    assert usage.parse_trace("abc123/456;o=1") == "abc123"
    assert usage.parse_trace("abc123") == "abc123"
    assert usage.parse_trace("") is None and usage.parse_trace(None) is None


def test_every_call_records_its_tokens_model_feature_and_trace(vertex):
    usage.begin_request("trace-one/1;o=1")
    usage.set_ref("comparing-fractions")
    assert ask(purpose="tutor.step") == {"ok": True}
    (record,) = calls("trace-one")
    assert (record["inputTokens"], record["outputTokens"], record["thinkingTokens"], record["cachedTokens"], record["totalTokens"]) == (120, 30, 50, 10, 200)
    assert record["feature"] == "tutor.step" and record["ref"] == "comparing-fractions" and record["outcome"] == "ok"
    assert record["model"] == gemini.GEMINI_MODEL and record["latencyMs"] >= 0 and record["finishReason"] == "STOP"
    assert "prompt" not in record and "text" not in json.dumps(record)


def test_the_total_is_summed_when_vertex_omits_it(vertex):
    vertex["payload"] = reply(usage_metadata={"promptTokenCount": 7, "candidatesTokenCount": 3})
    usage.begin_request("trace-sum")
    ask()
    assert calls("trace-sum")[0]["totalTokens"] == 10


def test_failed_calls_are_recorded_with_their_status(vertex):
    vertex["status"] = 503
    usage.begin_request("trace-err")
    with pytest.raises(gemini.GeminiError):
        ask()
    record = calls("trace-err")[0]
    assert record["outcome"] == "error" and record["httpStatus"] == 503 and record["totalTokens"] == 0


def test_blocked_replies_are_recorded_as_blocked(vertex):
    vertex["payload"] = reply(promptFeedback={"blockReason": "SAFETY"})
    usage.begin_request("trace-block")
    with pytest.raises(gemini.GeminiSafetyBlock):
        ask()
    assert calls("trace-block")[0]["outcome"] == "blocked"


def test_a_call_that_is_cancelled_is_still_recorded(vertex):
    vertex["hang"] = True
    usage.begin_request("trace-cancel")

    async def run():
        await asyncio.wait_for(gemini.generate_json("s", [{"text": "x"}], {}, purpose="tutor.step"), 0.05)

    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(run())
    assert calls("trace-cancel")[0]["outcome"] == "cancelled"


def test_a_tracking_failure_never_breaks_the_call(vertex, monkeypatch):
    def broken(record):
        raise RuntimeError("database down")

    monkeypatch.setattr(usage.store, "save_llm_call", broken)
    usage.begin_request("trace-broken")
    assert ask() == {"ok": True}


def test_each_call_is_written_as_a_structured_log_line(vertex, monkeypatch):
    lines = []

    class Collect(logging.Handler):
        def emit(self, record):
            lines.append(record.getMessage())

    handler = Collect()
    usage._stdout.addHandler(handler)
    monkeypatch.setattr(usage, "GOOGLE_CLOUD_PROJECT", "demo-project")
    try:
        usage.begin_request("trace-log/9")
        ask(purpose="tutor.leak_check")
    finally:
        usage._stdout.removeHandler(handler)
    line = json.loads(lines[0])
    assert line["message"] == "gemini_usage" and line["severity"] == "INFO" and line["feature"] == "tutor.leak_check"
    assert line["totalTokens"] == 200 and line["logging.googleapis.com/trace"] == "projects/demo-project/traces/trace-log"


def signup(email, role):
    res = client.post("/api/auth/signup", json={"name": f"{role.title()} {email[:3]}", "email": email, "password": "secret123", "role": role})
    if res.status_code != 200:
        res = client.post("/api/auth/login", json={"email": email, "password": "secret123"})
    return {"Authorization": f"Bearer {res.json()['token']}"}, res.json()["user"]["id"]


def test_calls_are_tied_to_the_signed_in_user_and_the_lesson_through_a_real_endpoint(vertex, monkeypatch):
    monkeypatch.setattr(homework, "gemini_enabled", lambda: True)
    vertex["payload"] = reply('{"questions": []}')
    headers, teacher_id = signup("usage.teacher@example.com", "teacher")
    res = client.post("/api/teacher/homework/draft", headers={**headers, "X-Cloud-Trace-Context": "endpoint-trace/1;o=1"},
                      json={"lessonId": "comparing-fractions", "count": 4})
    assert res.status_code == 200
    (record,) = calls("endpoint-trace")
    assert record["userId"] == teacher_id and record["role"] == "teacher"
    assert record["feature"] == "homework.draft" and record["ref"] == "comparing-fractions"


def seed(minutes_ago, feature, model, tokens, user_id=None, outcome="ok", latency=1000):
    ts = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()
    store.save_llm_call({"id": f"{feature}{minutes_ago}{tokens}", "ts": ts, "traceId": "t", "userId": user_id, "role": "student",
                         "feature": feature, "ref": None, "model": model, "inputTokens": tokens // 2, "outputTokens": tokens // 2,
                         "thinkingTokens": 0, "cachedTokens": 0, "totalTokens": tokens, "latencyMs": latency, "outcome": outcome,
                         "httpStatus": None, "finishReason": None})


def test_teacher_report_groups_usage_and_is_teacher_only():
    store.data["llmCalls"] = []
    teacher, _ = signup("usage.teacher@example.com", "teacher")
    student, student_id = signup("usage.student@example.com", "student")
    seed(5, "tutor.step", "big-model", 1000, student_id, latency=3000)
    seed(4, "tutor.step", "big-model", 500, student_id, latency=1000)
    seed(3, "tutor.leak_check", "small-model", 100, student_id, latency=500)
    seed(2, "speech.tts", "tts-model", 50, None, outcome="error")
    seed(60 * 24 * 40, "tutor.step", "big-model", 9999, student_id)

    assert client.get("/api/teacher/usage", headers=student).status_code == 403
    assert client.get("/api/teacher/usage").status_code == 401
    assert client.get("/api/teacher/usage?days=0", headers=teacher).status_code == 422
    report = client.get("/api/teacher/usage?days=7", headers=teacher).json()

    assert report["totals"]["calls"] == 4 and report["totals"]["totalTokens"] == 1650 and report["totals"]["errors"] == 1
    assert [row["name"] for row in report["byFeature"]] == ["tutor.step", "tutor.leak_check", "speech.tts"]
    assert report["byFeature"][0]["calls"] == 2 and report["byFeature"][0]["avgLatencyMs"] == 2000
    assert [row["name"] for row in report["byModel"]][0] == "big-model"
    assert len(report["byDay"]) == 7 and sum(day["totalTokens"] for day in report["byDay"]) == 1650
    assert report["byStudent"][0]["calls"] == 3 and report["byStudent"][0]["totalTokens"] == 1600
    assert report["recent"][0]["feature"] == "speech.tts" and report["recent"][0]["student"] is None
    assert report["recent"][1]["student"] == report["byStudent"][0]["name"] and report["truncated"] is False
    assert client.get("/api/teacher/usage?days=30", headers=teacher).json()["totals"]["calls"] == 4


def test_an_empty_report_is_valid():
    store.data["llmCalls"] = []
    teacher, _ = signup("usage.teacher@example.com", "teacher")
    report = client.get("/api/teacher/usage", headers=teacher).json()
    assert report["totals"]["calls"] == 0 and report["byFeature"] == [] and report["recent"] == [] and len(report["byDay"]) == 7
