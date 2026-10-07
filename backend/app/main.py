import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import auth, gemini, speech, student_model, topics, tutor
from .config import GEMINI_MODEL, GEMINI_TTS_MODEL, TEACHER_INVITE_CODE, gemini_enabled
from .store import store

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("tutor.api")

app = FastAPI(title="Brightpath Tutor API")

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_AUDIO_BASE64 = 8_000_000
MAX_PDF_BASE64 = 14_000_000


class SignupIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    email: str = Field(max_length=120)
    password: str = Field(min_length=8, max_length=128)
    role: Literal["student", "teacher"] = "student"
    inviteCode: str = Field(default="", max_length=64)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        if not EMAIL_PATTERN.match(value.strip()):
            raise ValueError("Enter a valid email address.")
        return value


class LoginIn(BaseModel):
    email: str = Field(max_length=120)
    password: str = Field(max_length=128)


class ProfileIn(BaseModel):
    grade: int = Field(ge=3, le=12)
    mathConfidence: int = Field(ge=1, le=5)
    fractionsComfort: Literal["new", "some", "confident"]
    learningStyle: Literal["visual", "step-by-step", "real-world", "practice"]
    pace: Literal["slow", "steady", "fast"]
    interests: list[str] = Field(default_factory=list, max_length=6)
    voiceEnabled: bool = True

    @field_validator("interests")
    @classmethod
    def short_interests(cls, value: list[str]) -> list[str]:
        return [item.strip()[:24] for item in value if item.strip()]


class TurnMeta(BaseModel):
    responseMs: int | None = Field(default=None, ge=0, le=3_600_000)
    inputMode: Literal["typed", "choice", "voice"] | None = None


class TurnIn(BaseModel):
    lessonId: str = Field(max_length=80)
    action: Literal["start", "restart", "continue", "answer", "hint", "explain_again", "ask"]
    text: str | None = Field(default=None, max_length=500)
    meta: TurnMeta | None = None


class UnderstandIn(BaseModel):
    lessonId: str = Field(max_length=80)
    audio: str = Field(max_length=MAX_AUDIO_BASE64)
    mimeType: Literal["audio/wav"] = "audio/wav"


class InterpretIn(BaseModel):
    lessonId: str = Field(max_length=80)
    transcript: str = Field(max_length=500)


class SpeakIn(BaseModel):
    text: str = Field(min_length=1, max_length=1200)


class LessonIn(BaseModel):
    id: str | None = Field(default=None, max_length=80)
    title: str = Field(min_length=1, max_length=80)
    summary: str = Field(default="", max_length=200)
    objectives: list[str] = Field(default_factory=list, max_length=6)
    keyIdeas: list[str] = Field(min_length=1, max_length=8)
    misconceptions: list[str] = Field(default_factory=list, max_length=6)


class TopicIn(BaseModel):
    subject: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=80)
    gradeLevel: int = Field(ge=1, le=12)
    description: str = Field(default="", max_length=4000)
    published: bool = False
    lessons: list[LessonIn] = Field(min_length=1, max_length=8)


class UploadedFile(BaseModel):
    name: str = Field(max_length=120)
    mimeType: Literal["application/pdf", "text/plain", "text/markdown"]
    data: str = Field(default="", max_length=MAX_PDF_BASE64)
    text: str = Field(default="", max_length=60_000)


class DraftIn(BaseModel):
    subject: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=80)
    gradeLevel: int = Field(ge=1, le=12)
    description: str = Field(default="", max_length=8000)
    file: UploadedFile | None = None


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "gemini": gemini_enabled(), "model": GEMINI_MODEL if gemini_enabled() else None,
            "ttsModel": GEMINI_TTS_MODEL if gemini_enabled() else None, "teacherInviteRequired": bool(TEACHER_INVITE_CODE)}


# ---------- Accounts ----------

@app.post("/api/auth/signup")
def signup(body: SignupIn) -> dict:
    token, user = auth.signup(body.name, body.email, body.password, body.role, body.inviteCode)
    return {"token": token, "user": auth.public_user(user)}


@app.post("/api/auth/login")
def login(body: LoginIn) -> dict:
    token, user = auth.login(body.email, body.password)
    return {"token": token, "user": auth.public_user(user)}


@app.post("/api/auth/logout")
def logout(token: str = Depends(auth.current_token)) -> dict:
    auth.logout(token)
    return {"ok": True}


@app.get("/api/me")
def me(user: dict = Depends(auth.current_user)) -> dict:
    return auth.public_user(user)


# ---------- Student ----------

@app.put("/api/profile")
def save_profile(body: ProfileIn, user: dict = Depends(auth.current_student)) -> dict:
    user["profile"] = body.model_dump()
    store.save_user(user)
    return auth.public_user(user)


@app.get("/api/curriculum")
def curriculum(user: dict = Depends(auth.current_user)) -> dict:
    progress = user.get("progress", {})
    subjects: dict[str, list[dict]] = defaultdict(list)
    for topic in sorted(topics.published_topics(), key=lambda t: (t["subject"], t.get("gradeLevel", 0), t["title"])):
        lessons = [
            {"id": lesson["id"], "title": lesson["title"], "summary": lesson.get("summary", ""), "order": index + 1,
             "topicId": topic["id"], "topicTitle": topic["title"],
             **progress.get(lesson["id"], {"mastery": 0, "complete": False, "started": False})}
            for index, lesson in enumerate(topic["lessons"])
        ]
        subjects[topic["subject"]].append({"id": topic["id"], "title": topic["title"], "gradeLevel": topic.get("gradeLevel"),
                                           "description": topic.get("description", ""), "createdByName": topic.get("createdByName"),
                                           "available": True, "lessons": lessons})
    return {"subjects": [{"id": name.lower().replace(" ", "-"), "title": name, "topics": items} for name, items in subjects.items()]}


@app.get("/api/me/insights")
def my_insights(user: dict = Depends(auth.current_student)) -> dict:
    return student_model.insights(user)


@app.post("/api/tutor/turn")
async def tutor_turn(body: TurnIn, user: dict = Depends(auth.current_student)) -> dict:
    meta = body.meta.model_dump() if body.meta else None
    return await tutor.take_turn(user, body.lessonId, body.action, body.text, meta)


@app.post("/api/speech/understand")
async def understand(body: UnderstandIn, user: dict = Depends(auth.current_student)) -> dict:
    if not gemini_enabled():
        raise HTTPException(503, "Gemini speech understanding is not configured.")
    question = tutor.pending_question(user, body.lessonId)
    try:
        return await speech.understand_audio(body.audio, body.mimeType, question)
    except gemini.GeminiError as exc:
        log.warning("Speech understanding failed: %s", exc)
        raise HTTPException(502, "I couldn't understand that audio. Please try again.") from exc


@app.post("/api/speech/interpret")
def interpret(body: InterpretIn, user: dict = Depends(auth.current_student)) -> dict:
    return speech.interpret_transcript(body.transcript, tutor.pending_question(user, body.lessonId))


@app.post("/api/speech/synthesize")
async def synthesize(body: SpeakIn, user: dict = Depends(auth.current_user)) -> Response:
    if not gemini_enabled():
        raise HTTPException(503, "Gemini text-to-speech is not configured.")
    audio = speech.audio_cache.get(body.text)
    if audio is None:
        try:
            audio = await gemini.synthesize(body.text)
        except gemini.GeminiError as exc:
            log.warning("Speech synthesis failed: %s", exc)
            raise HTTPException(502, "Speech synthesis failed.") from exc
        speech.audio_cache.put(body.text, audio)
    return Response(content=audio, media_type="audio/wav", headers={"Cache-Control": "no-store"})


# ---------- Teacher ----------

def _topic_view(topic: dict, teacher: dict) -> dict:
    return {**topic, "canEdit": topic["createdBy"] in (teacher["id"], "system"), "canDelete": topic["createdBy"] == teacher["id"]}


@app.get("/api/teacher/topics")
def teacher_topics(teacher: dict = Depends(auth.current_teacher)) -> dict:
    items = sorted(topics.all_topics(), key=lambda t: t.get("updatedAt") or t["createdAt"], reverse=True)
    return {"topics": [_topic_view(topic, teacher) for topic in items]}


@app.post("/api/teacher/topics/draft")
async def draft_topic(body: DraftIn, teacher: dict = Depends(auth.current_teacher)) -> dict:
    if not body.description.strip() and not body.file:
        raise HTTPException(422, "Add a description or upload your notes.")
    file = body.file.model_dump() if body.file else None
    return await topics.draft_plan(body.subject, body.title, body.gradeLevel, body.description, file)


@app.post("/api/teacher/topics")
def create_topic(body: TopicIn, teacher: dict = Depends(auth.current_teacher)) -> dict:
    return _topic_view(topics.create_topic(teacher, body.model_dump()), teacher)


@app.put("/api/teacher/topics/{topic_id}")
def update_topic(topic_id: str, body: TopicIn, teacher: dict = Depends(auth.current_teacher)) -> dict:
    return _topic_view(topics.update_topic(teacher, topic_id, body.model_dump()), teacher)


@app.delete("/api/teacher/topics/{topic_id}")
def delete_topic(topic_id: str, teacher: dict = Depends(auth.current_teacher)) -> dict:
    topics.delete_topic(teacher, topic_id)
    return {"ok": True}


def _students() -> list[dict]:
    return [user for user in store.all_users() if user.get("role", "student") == "student"]


def _last_active(user_id: str) -> str | None:
    return store.last_active(user_id)


@app.get("/api/teacher/students")
def teacher_students(teacher: dict = Depends(auth.current_teacher)) -> dict:
    rows = []
    for user in _students():
        info = student_model.insights(user)
        progress = user.get("progress", {})
        rows.append({
            "id": user["id"], "name": user["name"], "email": user["email"],
            "grade": (user.get("profile") or {}).get("grade"),
            "onboarded": bool(user.get("profile")),
            "overallMastery": info["overallMastery"],
            "lessonsStarted": sum(1 for p in progress.values() if p.get("started")),
            "lessonsCompleted": sum(1 for p in progress.values() if p.get("complete")),
            "bestStrategy": info["bestStrategy"] if info["behaviour"]["answers"] else None,
            "selfReportedStrategy": info["selfReportedStrategy"],
            "avgResponseSec": info["behaviour"]["avgResponseSec"],
            "answers": info["behaviour"]["answers"],
            "topMisconception": info["misconceptions"][0]["label"] if info["misconceptions"] else None,
            "needsSupport": info["overallMastery"] is not None and info["overallMastery"] < 45,
            "lastActive": _last_active(user["id"]),
        })
    rows.sort(key=lambda row: row["lastActive"] or "", reverse=True)
    return {"students": rows}


@app.get("/api/teacher/students/{student_id}")
def teacher_student(student_id: str, teacher: dict = Depends(auth.current_teacher)) -> dict:
    user = store.get_user(student_id)
    if not user or user.get("role", "student") != "student":
        raise HTTPException(404, "Student not found.")
    events = student_model.recent_events(student_id, limit=60)
    for event in events:
        if "lessonId" in event:
            event["topicTitle"], event["lessonTitle"] = topics.lesson_title(event["lessonId"])
    return {"student": auth.public_user(user), "insights": student_model.insights(user), "events": events}


@app.get("/api/teacher/overview")
def teacher_overview(teacher: dict = Depends(auth.current_teacher)) -> dict:
    students = _students()
    concept_totals: dict[str, list[float]] = defaultdict(list)
    misconception_totals: dict[str, int] = defaultdict(int)
    strategy_totals = {s: {"success": 0, "attempts": 0} for s in student_model.STRATEGIES}
    masteries, completed, needs_support, active = [], 0, 0, 0
    for user in students:
        model = store.get_model(user["id"], student_model._new_model)
        completed += sum(1 for p in user.get("progress", {}).values() if p.get("complete"))
        if not model or not model["behaviour"]["answers"]:
            continue
        active += 1
        practised = [c for c in model["concepts"].values() if c["attempts"]]
        for lesson_id, item in model["concepts"].items():
            if item["attempts"]:
                concept_totals[lesson_id].append(item["mastery"])
        for label, entry in model["misconceptions"].items():
            misconception_totals[label] += entry["count"]
        for name, stats in model["strategies"].items():
            strategy_totals[name]["success"] += stats["success"]
            strategy_totals[name]["attempts"] += stats["success"] + stats["fail"] + stats["confused"]
        if practised:
            mastery = sum(c["mastery"] for c in practised) / len(practised)
            masteries.append(mastery)
            needs_support += int(mastery < 0.45)
    concepts = []
    for lesson_id, values in concept_totals.items():
        topic_title, title = topics.lesson_title(lesson_id)
        concepts.append({"lessonId": lesson_id, "lessonTitle": title, "topicTitle": topic_title,
                         "mastery": round(100 * sum(values) / len(values)), "students": len(values)})
    concepts.sort(key=lambda c: c["mastery"])
    total_mistakes = sum(misconception_totals.values()) or 1
    return {
        "studentCount": len(students),
        "activeStudents": active,
        "lessonsCompleted": completed,
        "averageMastery": round(100 * sum(masteries) / len(masteries)) if masteries else None,
        "needSupport": needs_support,
        "concepts": concepts,
        "misconceptions": [{"label": label, "count": count, "share": round(100 * count / total_mistakes)}
                           for label, count in sorted(misconception_totals.items(), key=lambda kv: -kv[1])[:6]],
        "strategies": [{"strategy": name, "label": student_model.STRATEGY_LABELS[name], "attempts": totals["attempts"],
                        "successRate": round(100 * totals["success"] / totals["attempts"]) if totals["attempts"] else None}
                       for name, totals in strategy_totals.items()],
    }


FRONTEND_DIR = Path("/app/frontend-dist")

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
