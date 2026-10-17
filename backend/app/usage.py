"""AI usage tracking: one record per Gemini call, so every token can be traced to a student, a feature and a request.

Each call is written to stdout as one JSON line (Cloud Run turns it into a structured Cloud Logging entry that links to the
request's trace) and saved to the `llmCalls` store for the teacher's AI usage page. Records hold metadata only, never prompts,
answers or student text. Saving is fire-and-forget: a tracking failure can never break a student's lesson.
"""

import asyncio
import contextvars
import json
import logging
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

from .config import GOOGLE_CLOUD_PROJECT
from .store import now_iso, store

REPORT_LIMIT = 5000
RECENT_CALLS = 40
TOP_STUDENTS = 10

_request: contextvars.ContextVar[dict | None] = contextvars.ContextVar("elevate_request", default=None)
log = logging.getLogger("elevate.usage")
_stdout = logging.getLogger("elevate.usage.stdout")
if not _stdout.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _stdout.addHandler(_handler)
    _stdout.setLevel(logging.INFO)
    _stdout.propagate = False


def parse_trace(header: str | None) -> str | None:
    """X-Cloud-Trace-Context looks like TRACE_ID/SPAN_ID;o=1."""
    return (header or "").split("/")[0].split(";")[0].strip() or None


def begin_request(trace_header: str | None) -> None:
    # A mutable holder: code that runs in worker threads or child tasks shares it, so the signed-in user can be added later.
    _request.set({"traceId": parse_trace(trace_header) or uuid.uuid4().hex, "userId": None, "role": None, "ref": None})


def set_user(user: dict) -> None:
    holder = _request.get()
    if holder is not None:
        holder["userId"], holder["role"] = user.get("id"), user.get("role", "student")


def set_ref(ref: str | None) -> None:
    """The lesson or homework this request is about."""
    holder = _request.get()
    if holder is not None:
        holder["ref"] = ref


def _persist(record: dict) -> None:
    try:
        store.save_llm_call(record)
    except Exception as exc:  # noqa: BLE001 - tracking must never break the request
        log.warning("Could not save AI usage record: %s", exc)


def record_call(*, feature: str, model: str, started: float, outcome: str, data: dict | None = None,
                http_status: int | None = None) -> None:
    """outcome: ok | blocked | error | cancelled. `data` is the Vertex AI reply, which carries the token counts."""
    try:
        holder = _request.get() or {}
        meta = (data or {}).get("usageMetadata") or {}
        candidates = (data or {}).get("candidates") or [{}]
        counts = {name: int(meta.get(key) or 0) for name, key in (
            ("inputTokens", "promptTokenCount"), ("outputTokens", "candidatesTokenCount"),
            ("thinkingTokens", "thoughtsTokenCount"), ("cachedTokens", "cachedContentTokenCount"))}
        record = {
            "id": uuid.uuid4().hex[:16], "ts": now_iso(), "traceId": holder.get("traceId"), "userId": holder.get("userId"),
            "role": holder.get("role"), "feature": feature, "ref": holder.get("ref"), "model": model, **counts,
            "totalTokens": int(meta.get("totalTokenCount") or counts["inputTokens"] + counts["outputTokens"] + counts["thinkingTokens"]),
            "latencyMs": round((time.monotonic() - started) * 1000), "outcome": outcome, "httpStatus": http_status,
            "finishReason": candidates[0].get("finishReason") if candidates else None,
        }
        line = {"severity": "ERROR" if outcome == "error" else "INFO", "message": "gemini_usage", **record}
        if record["traceId"] and GOOGLE_CLOUD_PROJECT:
            line["logging.googleapis.com/trace"] = f"projects/{GOOGLE_CLOUD_PROJECT}/traces/{record['traceId']}"
        _stdout.info(json.dumps(line))
        try:
            asyncio.get_running_loop().run_in_executor(None, _persist, record)
        except RuntimeError:
            _persist(record)
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not record AI usage: %s", exc)


# ---------- Report for the teacher page ----------

def _group(rows: list[dict], key) -> list[dict]:
    groups: dict[str, dict] = {}
    for row in rows:
        entry = groups.setdefault(key(row), {"calls": 0, "inputTokens": 0, "outputTokens": 0, "thinkingTokens": 0,
                                             "totalTokens": 0, "_latency": 0, "_timed": 0})
        entry["calls"] += 1
        for field in ("inputTokens", "outputTokens", "thinkingTokens", "totalTokens"):
            entry[field] += row.get(field, 0)
        if row["outcome"] in ("ok", "blocked"):
            entry["_latency"] += row.get("latencyMs", 0)
            entry["_timed"] += 1
    return [{"name": name, **{k: v for k, v in entry.items() if not k.startswith("_")},
             "avgLatencyMs": round(entry["_latency"] / entry["_timed"]) if entry["_timed"] else None}
            for name, entry in sorted(groups.items(), key=lambda item: -item[1]["totalTokens"])]


def report(days: int) -> dict:
    now = datetime.now(timezone.utc)
    rows, truncated = store.llm_calls_since((now - timedelta(days=days)).isoformat(), REPORT_LIMIT)
    overall = _group(rows, lambda row: "all")
    totals = overall[0] if overall else {"calls": 0, "inputTokens": 0, "outputTokens": 0, "thinkingTokens": 0, "totalTokens": 0, "avgLatencyMs": None}
    totals.pop("name", None)
    totals.update(errors=sum(r["outcome"] == "error" for r in rows), blocked=sum(r["outcome"] == "blocked" for r in rows),
                  cancelled=sum(r["outcome"] == "cancelled" for r in rows))

    per_day = {row["name"]: row for row in _group(rows, lambda r: r["ts"][:10])}
    by_day = []
    for offset in range(days - 1, -1, -1):
        day = (now - timedelta(days=offset)).strftime("%Y-%m-%d")
        entry = per_day.get(day)
        by_day.append({"date": day, "calls": entry["calls"] if entry else 0, "totalTokens": entry["totalTokens"] if entry else 0})

    names: dict[str, str] = {}

    def student_name(user_id: str | None) -> str:
        if not user_id:
            return "Not tied to a student"
        if user_id not in names:
            user = store.get_user(user_id)
            names[user_id] = user["name"] if user else "Removed account"
        return names[user_id]

    students = _group([r for r in rows if r.get("userId")], lambda r: r["userId"])[:TOP_STUDENTS]
    by_student = [{"userId": s["name"], "name": student_name(s["name"]), "calls": s["calls"], "totalTokens": s["totalTokens"]} for s in students]
    recent = [{**{k: r.get(k) for k in ("id", "ts", "traceId", "feature", "ref", "model", "inputTokens", "outputTokens",
                                         "thinkingTokens", "totalTokens", "latencyMs", "outcome", "httpStatus")},
               "student": student_name(r.get("userId")) if r.get("userId") else None} for r in rows[:RECENT_CALLS]]
    return {"days": days, "truncated": truncated, "totals": totals, "byFeature": _group(rows, lambda r: r["feature"]),
            "byModel": _group(rows, lambda r: r["model"]), "byDay": by_day, "byStudent": by_student, "recent": recent}
