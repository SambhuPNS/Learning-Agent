"""Teacher-authored topics: storage, Gemini lesson-plan drafting, and offline fallback scripts."""

import re
import uuid

from fastapi import HTTPException

from . import gemini
from .config import gemini_enabled
from .curriculum import SCRIPTS
from .store import now_iso, store

MAX_FILE_TEXT = 40_000

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "One-sentence overview of the topic for students."},
        "lessons": {
            "type": "array",
            "minItems": 2,
            "maxItems": 6,
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Short lesson title, at most 6 words."},
                    "summary": {"type": "string", "description": "One short sentence describing the lesson."},
                    "objectives": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 4},
                    "keyIdeas": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 5,
                                 "description": "The core ideas to teach, each one clear sentence a student could understand."},
                    "misconceptions": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 4,
                                       "description": "Common student mistakes or wrong beliefs about this lesson."},
                },
                "required": ["title", "summary", "objectives", "keyIdeas", "misconceptions"],
            },
        },
    },
    "required": ["summary", "lessons"],
}

PLAN_SYSTEM = """You are an expert curriculum designer helping a school teacher.
Turn the teacher's topic description (and any attached material) into a short sequence of lessons for a one-to-one AI tutor.
- Order lessons from foundational to advanced; each lesson covers one teachable concept.
- Key ideas must be accurate, age-appropriate for the given grade, and phrased as clear statements.
- Misconceptions should be realistic mistakes students of that grade actually make.
- Stay strictly within the teacher's material; do not invent unrelated content."""


def _short_id() -> str:
    return uuid.uuid4().hex[:8]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "topic"


def all_topics() -> list[dict]:
    return list(store.data["topics"].values())


def published_topics() -> list[dict]:
    return [topic for topic in all_topics() if topic.get("published")]


def find_lesson(lesson_id: str, require_published: bool = True) -> tuple[dict, dict]:
    for topic in all_topics():
        if require_published and not topic.get("published"):
            continue
        for lesson in topic["lessons"]:
            if lesson["id"] == lesson_id:
                return topic, lesson
    raise HTTPException(404, "Unknown lesson.")


def lesson_title(lesson_id: str) -> tuple[str, str]:
    try:
        topic, lesson = find_lesson(lesson_id, require_published=False)
        return topic["title"], lesson["title"]
    except HTTPException:
        return "Removed topic", lesson_id


def _clean_list(values, limit: int, length: int = 300) -> list[str]:
    return [str(v).strip()[:length] for v in (values or []) if str(v).strip()][:limit]


def normalise_lessons(lessons: list[dict], topic_id: str, existing_ids: set[str] | None = None) -> list[dict]:
    cleaned = []
    for lesson in lessons[:8]:
        lesson_id = lesson.get("id") if lesson.get("id") in (existing_ids or set()) else f"{topic_id}-{_short_id()}"
        key_ideas = _clean_list(lesson.get("keyIdeas"), 6)
        if not str(lesson.get("title", "")).strip() or not key_ideas:
            raise HTTPException(422, "Every lesson needs a title and at least one key idea.")
        cleaned.append({
            "id": lesson_id,
            "title": str(lesson["title"]).strip()[:80],
            "summary": str(lesson.get("summary", "")).strip()[:200],
            "objectives": _clean_list(lesson.get("objectives"), 5),
            "keyIdeas": key_ideas,
            "misconceptions": _clean_list(lesson.get("misconceptions"), 5),
        })
    if not cleaned:
        raise HTTPException(422, "A topic needs at least one lesson.")
    return cleaned


def create_topic(teacher: dict, data: dict) -> dict:
    topic_id = f"{_slug(data['title'])}-{_short_id()}"
    topic = {
        "id": topic_id,
        "subject": data["subject"].strip(),
        "title": data["title"].strip(),
        "gradeLevel": data["gradeLevel"],
        "description": data["description"].strip(),
        "createdBy": teacher["id"],
        "createdByName": teacher["name"],
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
        "published": bool(data.get("published")),
        "lessons": normalise_lessons(data["lessons"], topic_id),
    }
    with store.lock:
        store.data["topics"][topic_id] = topic
        store.save()
    return topic


def _owned_topic(teacher: dict, topic_id: str) -> dict:
    topic = store.data["topics"].get(topic_id)
    if not topic:
        raise HTTPException(404, "Topic not found.")
    if topic["createdBy"] not in (teacher["id"], "system"):
        raise HTTPException(403, "You can only change topics you created.")
    return topic


def update_topic(teacher: dict, topic_id: str, data: dict) -> dict:
    topic = _owned_topic(teacher, topic_id)
    existing = {lesson["id"] for lesson in topic["lessons"]}
    with store.lock:
        topic.update(
            subject=data["subject"].strip(),
            title=data["title"].strip(),
            gradeLevel=data["gradeLevel"],
            description=data["description"].strip(),
            published=bool(data.get("published")),
            lessons=normalise_lessons(data["lessons"], topic_id, existing),
            updatedAt=now_iso(),
        )
        store.save()
    return topic


def delete_topic(teacher: dict, topic_id: str) -> None:
    topic = _owned_topic(teacher, topic_id)
    if topic["createdBy"] == "system":
        raise HTTPException(403, "Starter content can be unpublished but not deleted.")
    with store.lock:
        del store.data["topics"][topic_id]
        store.save()


async def draft_plan(subject: str, title: str, grade: int, description: str, file: dict | None) -> dict:
    """Asks Gemini to turn the teacher's notes into lessons. Falls back to a simple outline offline."""
    file_text = ""
    file_part = None
    if file:
        if file["mimeType"] == "application/pdf":
            file_part = {"inlineData": {"mimeType": "application/pdf", "data": file["data"]}}
        else:
            file_text = file["text"][:MAX_FILE_TEXT]
    if gemini_enabled():
        prompt = (f"Subject: {subject}\nTopic: {title}\nGrade: {grade}\n\nTeacher's description:\n{description}\n"
                  + (f"\nAttached notes ({file['name']}):\n{file_text}\n" if file_text else "")
                  + ("\nThe attached PDF contains the teacher's material." if file_part else ""))
        parts = [{"text": prompt}] + ([file_part] if file_part else [])
        try:
            plan = await gemini.generate_json(PLAN_SYSTEM, parts, PLAN_SCHEMA, timeout=90, thinking="medium")
            return {"summary": plan.get("summary", ""), "lessons": plan.get("lessons", []), "source": "gemini"}
        except gemini.GeminiError as exc:
            if file_part:
                raise HTTPException(502, "Gemini could not read the PDF right now. Please try again.") from exc
    elif file_part:
        raise HTTPException(503, "Reading PDFs needs Gemini. Paste the text instead, or add a Gemini key.")
    return _outline_plan(title, description + "\n" + file_text)


def _outline_plan(title: str, text: str) -> dict:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if len(s.strip()) > 12]
    chunks = [sentences[i:i + 3] for i in range(0, min(len(sentences), 12), 3)] or [[f"{title} is the focus of this lesson."]]
    lessons = [
        {"title": f"{title}: part {index + 1}" if len(chunks) > 1 else f"Introduction to {title}",
         "summary": chunk[0][:160], "objectives": [f"Understand {title.lower()}"], "keyIdeas": chunk, "misconceptions": []}
        for index, chunk in enumerate(chunks)
    ]
    return {"summary": sentences[0] if sentences else title, "lessons": lessons, "source": "outline"}


def fallback_script(lesson: dict) -> list[dict]:
    """Scripted lesson used when Gemini is unavailable: hand-written for seed lessons, generated for teacher topics."""
    if lesson["id"] in SCRIPTS:
        return SCRIPTS[lesson["id"]]
    script = []
    misconceptions = lesson.get("misconceptions", [])
    ideas = lesson["keyIdeas"][:3]
    for index, idea in enumerate(ideas):
        script.append({
            "kind": "teach", "title": lesson["title"] if index == 0 else f"Key idea {index + 1}",
            "paragraphs": [idea] + ([lesson["objectives"][0]] if index == 0 and lesson.get("objectives") else []),
            "speech": idea, "visual": None, "strategy": "step-by-step",
        })
        use_misconception = index < len(misconceptions) and index % 2 == 1
        statement = misconceptions[index] if use_misconception else idea
        answer = "False" if use_misconception else "True"
        script.append({
            "kind": "question", "title": "Quick check", "paragraphs": ["Decide if this statement is true or false."],
            "speech": f"True or false? {statement}", "visual": None,
            "question": {"prompt": f"True or false: {statement}", "format": "choice", "options": ["True", "False"],
                         "expectedAnswer": answer, "acceptableAnswers": [answer], "hint": f"Think back to the idea: {idea}"},
            "explainAgain": [f"Let's look at it again: {idea}"],
            "correctMessage": f"Correct! {idea}",
            "wrongMessage": "Not quite." + (f" That is a common mistake: {statement}" if use_misconception else ""),
        })
    script.append({
        "kind": "summary", "title": "Lesson complete", "paragraphs": ["Great work! Here is what you learned:"] + ideas,
        "speech": "Great work! You finished this lesson.", "visual": None, "strategy": "step-by-step",
    })
    return script
