"""Adaptive lesson engine.

Each turn: log the interaction -> update the student model -> pick a teaching strategy from evidence ->
ask Gemini for the next step using profile + student model + topic data + conversation -> return UI-safe JSON.
"""

import json
import logging
import time
import uuid

from fastapi import HTTPException

from . import answers, gemini, student_model, topics
from .config import gemini_enabled
from .store import store

log = logging.getLogger("tutor.engine")

TARGET_CORRECT = 3
ESTIMATED_STEPS = 8
HISTORY_WINDOW = 16
ACTION_LABELS = {
    "continue": "I'm ready, let's continue.",
    "hint": "Can I have a hint?",
    "explain_again": "Can you explain that another way?",
}
VISUAL_TYPES = ["fraction-circles", "fraction-bars", "number-line", "flow", "comparison"]

FRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "numerator": {"type": "integer", "minimum": 0, "maximum": 24},
        "denominator": {"type": "integer", "minimum": 1, "maximum": 12},
        "label": {"type": "string"},
    },
    "required": ["numerator", "denominator", "label"],
}

STEP_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["teach", "question", "feedback", "summary"]},
        "title": {"type": "string", "description": "Short heading, at most 6 words."},
        "strategy": {"type": "string", "enum": student_model.STRATEGIES + ["none"],
                     "description": "The teaching strategy used for the explanation in this step, or none for a bare question."},
        "paragraphs": {
            "type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 4,
            "description": "What appears on screen. Short, friendly sentences. Use digits like 3/4 for fractions.",
        },
        "speech": {
            "type": "string",
            "description": "What the tutor says aloud: the explanation plus the question if one is asked. Natural spoken English under 80 words. Write fractions and symbols as words.",
        },
        "visual": {
            "type": ["object", "null"],
            "description": "fraction-circles/fraction-bars/number-line use 'fractions'. flow (ordered steps or a process) and comparison (2-3 columns contrasting ideas) use 'items'.",
            "properties": {
                "type": {"type": "string", "enum": VISUAL_TYPES},
                "caption": {"type": "string"},
                "fractions": {"type": "array", "items": FRACTION_SCHEMA, "maxItems": 4},
                "items": {
                    "type": "array", "maxItems": 6,
                    "items": {"type": "object", "properties": {"label": {"type": "string"}, "detail": {"type": "string"}},
                              "required": ["label", "detail"]},
                },
            },
            "required": ["type", "caption", "fractions", "items"],
        },
        "feedback": {
            "type": ["object", "null"],
            "properties": {
                "correct": {"type": "boolean"},
                "message": {"type": "string"},
                "misconception": {"type": "string", "description": "If incorrect: the specific misconception shown, ideally one from the topic list. Empty if correct."},
            },
            "required": ["correct", "message", "misconception"],
        },
        "question": {
            "type": ["object", "null"],
            "properties": {
                "prompt": {"type": "string"},
                "format": {"type": "string", "enum": ["choice", "text"]},
                "options": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
                "expectedAnswer": {"type": "string", "description": "Canonical answer. Fractions as a/b. For choice questions, the exact option text."},
                "acceptableAnswers": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "hint": {"type": "string"},
            },
            "required": ["prompt", "format", "options", "expectedAnswer", "acceptableAnswers", "hint"],
        },
    },
    "required": ["kind", "title", "strategy", "paragraphs", "speech", "visual", "feedback", "question"],
}

SYSTEM_PROMPT = """You are Brightpath, a warm, patient one-to-one tutor for school students. You can teach any subject.
You teach one lesson step by step and return exactly one lesson step as JSON.

Teaching rules:
- Always TEACH before you test. Each new key idea gets a short 'teach' step (2-3 short paragraphs) before any question on it.
- Pattern: teach -> question -> feedback -> (teach next idea or another question) ... -> summary.
- Ask one question at a time, answerable with a short answer or by choosing an option. Prefer multiple choice for younger students.
- Never reveal the answer to a pending question unless the student has already answered it.
- Follow the TEACHING STRATEGY you are given for any explanation, and report it in the 'strategy' field.
- Adapt to the STUDENT MODEL: its evidence about mastery, misconceptions and behaviour is more reliable than the sign-up answers.
- Use the student's interests in examples, and keep language right for their grade.
- Visuals: fraction visuals only for fractions; number-line for numbers; flow for processes or ordered steps; comparison to contrast ideas. A visual must never give away the answer to the question on the same step.
- 'teach' and 'summary' steps have question = null. 'question' steps must include a question. 'feedback' has feedback set.
- Stay within the topic. If the student asks something off-topic or inappropriate, kindly steer back to the lesson.
"""


def _session_key(user_id: str, lesson_id: str) -> str:
    return f"{user_id}:{lesson_id}"


def _new_session(lesson_id: str, topic_id: str) -> dict:
    return {"lessonId": lesson_id, "topicId": topic_id, "history": [], "pending": None, "correct": 0, "wrong": 0,
            "complete": False, "mockIndex": 0, "lastStrategy": None, "hintUsed": False, "attempts": 0,
            "pendingSince": None}


def _public_question(question: dict | None) -> dict | None:
    if not question:
        return None
    return {"prompt": question["prompt"], "format": question["format"], "options": question.get("options", [])}


def _learner_view(user: dict, topic: dict, lesson: dict, session: dict, last_response_ms: int | None = None) -> dict:
    model = student_model.get_model(user)
    prior = student_model.prior_mastery(user, topic)
    item = student_model.concept(model, lesson["id"], prior)
    self_reported = (user.get("profile") or {}).get("learningStyle")
    lesson_misconceptions = [label for label, entry in model["misconceptions"].items() if entry["lessonId"] == lesson["id"]]
    return {
        "mastery": round(item["mastery"] * 100),
        "difficulty": student_model.difficulty_for(item["mastery"]),
        "currentStrategy": session.get("lastStrategy"),
        "bestStrategy": student_model.best_strategy(model, self_reported),
        "avgResponseSec": round(model["behaviour"]["avgResponseMs"] / 1000, 1) if model["behaviour"]["avgResponseMs"] else None,
        "lastResponseSec": round(last_response_ms / 1000, 1) if last_response_ms is not None else None,
        "watchFor": lesson_misconceptions[-1] if lesson_misconceptions else None,
    }


def _state(user: dict, topic: dict, lesson: dict, session: dict) -> dict:
    tutor_steps = sum(1 for item in session["history"] if item["role"] == "tutor")
    learner = _learner_view(user, topic, lesson, session)
    return {
        "lessonId": session["lessonId"],
        "correct": session["correct"],
        "target": TARGET_CORRECT,
        "mastery": learner["mastery"],
        "step": tutor_steps,
        "estimatedSteps": max(ESTIMATED_STEPS, tutor_steps),
        "complete": session["complete"],
        "awaitingAnswer": session["pending"] is not None,
    }


def _transcript(session: dict) -> str:
    lines = []
    for item in session["history"][-HISTORY_WINDOW:]:
        if item["role"] == "student":
            lines.append(f"STUDENT ({item['action']}): {item['text']}")
            continue
        step = item["step"]
        style = f" [{step['strategy']}]" if step.get("strategy") else ""
        line = f"TUTOR [{step['kind']}]{style} {step['title']}: {' '.join(step['paragraphs'])}"
        if step.get("feedback"):
            line += f" (feedback: {'correct' if step['feedback']['correct'] else 'incorrect'})"
        if step.get("question"):
            line += f" QUESTION: {step['question']['prompt']}"
        lines.append(line)
    return "\n".join(lines) or "(lesson has not started yet)"


def _instruction(action: str, text: str | None, session: dict, graded: bool | None) -> str:
    pending = session["pending"]
    pending_json = json.dumps(pending) if pending else "none"
    finishing = session["correct"] >= TARGET_CORRECT
    if action == "start":
        return "Start the lesson. Return a 'teach' step that warmly greets the student by name and introduces the FIRST key idea. No question yet."
    if action == "continue":
        if finishing:
            return "The student has met the mastery target. Return a 'summary' step recapping the key ideas and praising specific progress. question = null."
        return ("The student is ready to continue. If the most recent idea has been taught but not yet checked, return a 'question' step about it "
                "(pitched at the difficulty in the student model). Otherwise teach the next key idea not yet covered (a 'teach' step). "
                "If every key idea is covered, ask another varied practice question, ideally targeting a known misconception.")
    if action == "answer":
        verdict = "MATCHES" if graded else "does NOT match"
        last = session["correct"] + (1 if graded else 0) >= TARGET_CORRECT
        follow_up = ("This correct answer reaches the mastery target, so set question = null; the next step will be the summary."
                     if graded and last else
                     "If correct: briefly explain why it is right and set question = null so the student can continue. "
                     "If incorrect: name the misconception in feedback.misconception, re-explain briefly using the TEACHING STRATEGY, "
                     "and ask a NEW similar question (question not null).")
        return (f"The student answered the pending question {pending_json}. Student answer: \"{text}\". "
                f"A deterministic check says the answer {verdict} the acceptable answers; trust it unless the answer is clearly an equivalent correct form. "
                f"Return a 'feedback' step with feedback.correct and a specific, encouraging message. {follow_up}")
    if action == "hint":
        return (f"The student asked for a hint on the pending question {pending_json}. Return a 'question' step with a helpful hint in the paragraphs "
                "(do not reveal the answer) and repeat the SAME question with the same expectedAnswer.")
    repeat = f"Then repeat the pending question {pending_json} unchanged (kind 'question')." if pending else "Set question = null (kind 'teach')."
    if action == "explain_again":
        return f"The student did not understand the last explanation. Re-explain the most recent idea in a completely different way using the TEACHING STRATEGY. {repeat}"
    return f"The student asked their own question: \"{text}\". Answer it clearly at their level using the TEACHING STRATEGY and link it back to the lesson. {repeat}"


def _prompt(user: dict, topic: dict, lesson: dict, session: dict, action: str, text: str | None, graded: bool | None, strategy: str | None) -> str:
    profile = user.get("profile") or {}
    model = student_model.get_model(user)
    prior = student_model.prior_mastery(user, topic)
    student = {
        "name": user["name"].split()[0],
        "grade": profile.get("grade"),
        "mathConfidence(1-5)": profile.get("mathConfidence"),
        "learningStyleChosenAtSignup": profile.get("learningStyle"),
        "pace": profile.get("pace"),
        "interests": profile.get("interests", []),
        "correctAnswersThisLesson": session["correct"],
        "incorrectAnswersThisLesson": session["wrong"],
        "masteryTarget": TARGET_CORRECT,
    }
    topic_data = {
        "subject": topic["subject"],
        "topic": topic["title"],
        "topicGrade": topic.get("gradeLevel"),
        "teacherDescription": topic.get("description", "")[:1500],
        "lesson": lesson["title"],
        "objectives": lesson.get("objectives", []),
        "keyIdeas": lesson["keyIdeas"],
        "commonMisconceptions": lesson.get("misconceptions", []),
    }
    model_view = student_model.prompt_summary(model, user, lesson["id"], prior)
    strategy_line = (f"TEACHING STRATEGY FOR THIS STEP: {strategy}. {student_model.STRATEGY_GUIDES[strategy]}"
                     if strategy else "TEACHING STRATEGY FOR THIS STEP: none needed unless you explain something.")
    return (f"STUDENT PROFILE (from sign-up):\n{json.dumps(student, indent=2)}\n\n"
            f"STUDENT MODEL (learned from behaviour):\n{json.dumps(model_view, indent=2)}\n"
            f"Difficulty guidance: {student_model.DIFFICULTY_GUIDES[model_view['difficulty']]}\n\n"
            f"TOPIC DATA (written by the teacher):\n{json.dumps(topic_data, indent=2)}\n\n"
            f"CONVERSATION SO FAR:\n{_transcript(session)}\n\n"
            f"{strategy_line}\n\n"
            f"YOUR TASK NOW:\n{_instruction(action, text, session, graded)}")


def _clean_visual(visual: dict | None) -> dict | None:
    if not visual or visual.get("type") not in VISUAL_TYPES:
        return None
    fractions = [
        {"numerator": max(0, min(24, int(f["numerator"]))), "denominator": max(1, min(12, int(f["denominator"]))),
         "label": str(f.get("label") or f"{f['numerator']}/{f['denominator']}")}
        for f in (visual.get("fractions") or [])[:4]
    ]
    items = [{"label": str(i.get("label", ""))[:60], "detail": str(i.get("detail", ""))[:240]} for i in (visual.get("items") or [])[:6]]
    uses_fractions = visual["type"] in ("fraction-circles", "fraction-bars", "number-line")
    if (uses_fractions and not fractions) or (not uses_fractions and not items):
        return None
    return {"type": visual["type"], "caption": str(visual.get("caption", "")), "fractions": fractions if uses_fractions else [],
            "items": [] if uses_fractions else items}


def _clean_step(raw: dict) -> tuple[dict, dict | None, str | None]:
    question = raw.get("question")
    hidden = None
    if question and question.get("prompt"):
        options = [str(option) for option in question.get("options") or []][:4]
        hidden = {
            "prompt": str(question["prompt"]),
            "format": "choice" if options else "text",
            "options": options,
            "expectedAnswer": str(question.get("expectedAnswer", "")),
            "acceptableAnswers": [str(a) for a in question.get("acceptableAnswers") or []] or [str(question.get("expectedAnswer", ""))],
            "hint": str(question.get("hint", "")),
        }
    feedback = raw.get("feedback")
    misconception = str(feedback.get("misconception", "")).strip() if feedback else ""
    kind = raw.get("kind", "teach")
    if kind == "question" and not hidden:
        kind = "teach"
    strategy = raw.get("strategy") if raw.get("strategy") in student_model.STRATEGIES else None
    step = {
        "kind": kind,
        "title": str(raw.get("title") or "Let's keep going"),
        "paragraphs": [str(p) for p in raw.get("paragraphs") or []][:4] or ["Let's keep going."],
        "speech": str(raw.get("speech") or " ".join(raw.get("paragraphs") or [])),
        "visual": _clean_visual(raw.get("visual")),
        "feedback": {"correct": bool(feedback.get("correct")), "message": str(feedback.get("message", ""))} if feedback else None,
        "strategy": strategy,
    }
    return step, hidden, misconception or None


def _render_script_item(item: dict) -> tuple[dict, dict | None]:
    step = {key: item.get(key) for key in ("kind", "title", "paragraphs", "speech", "visual")}
    step["feedback"] = None
    step["strategy"] = item.get("strategy") if item["kind"] in ("teach", "summary") else None
    return step, item.get("question")


def _mock_step(user: dict, lesson: dict, session: dict, action: str, graded: bool | None) -> tuple[dict, dict | None]:
    script = topics.fallback_script(lesson)
    pending = session["pending"]
    name = user["name"].split()[0]
    index = min(session["mockIndex"], len(script) - 1)

    if action == "start":
        session["mockIndex"] = 0
        step, hidden = _render_script_item(script[0])
        step["paragraphs"] = [f"Hi {name}! Let's learn together."] + step["paragraphs"]
        step["speech"] = f"Hi {name}! Let's learn together. {step['speech']}"
        return step, hidden

    if action == "continue":
        session["mockIndex"] = min(index + 1, len(script) - 1)
        return _render_script_item(script[session["mockIndex"]])

    item = script[index]
    scripted = item.get("question") and pending and item["question"]["prompt"] == pending["prompt"]

    if action == "answer":
        if graded:
            message = item["correctMessage"] if scripted else f"Great job, {name}! That's correct."
            return {"kind": "feedback", "title": "Nice work!", "paragraphs": [message], "speech": message, "visual": None,
                    "feedback": {"correct": True, "message": message}, "strategy": None}, None
        wrong = item["wrongMessage"] if scripted else "Not quite yet."
        hint = pending.get("hint", "")
        paragraphs = [wrong, f"Hint: {hint}" if hint else "Have another go.", "Try again."]
        return {"kind": "feedback", "title": "Let's look again", "paragraphs": paragraphs, "speech": f"{wrong} {hint} Try again.",
                "visual": item.get("visual") if scripted else None, "feedback": {"correct": False, "message": wrong},
                "strategy": None}, pending

    if action == "hint" and pending:
        hint = pending.get("hint") or "Read the question slowly and look for the key words."
        return {"kind": "question", "title": "Here's a hint", "paragraphs": [hint], "speech": hint,
                "visual": item.get("visual") if scripted else None, "feedback": None, "strategy": None}, pending

    ideas = lesson["keyIdeas"]
    if action == "explain_again":
        paragraphs = item.get("explainAgain") or [f"Let's say it another way. {ideas[min(index // 2, len(ideas) - 1)]}"]
        return {"kind": "question" if pending else "teach", "title": "Another way to see it", "paragraphs": paragraphs,
                "speech": " ".join(paragraphs), "visual": item.get("visual"), "feedback": None, "strategy": None}, pending

    paragraphs = [f"Good question! Here's how I think about it: {ideas[0]}",
                  "Gemini answers free questions in detail when it is available."]
    return {"kind": "question" if pending else "teach", "title": "Your question", "paragraphs": paragraphs,
            "speech": paragraphs[0], "visual": None, "feedback": None, "strategy": None}, pending


def _choose_strategy(user: dict, model: dict, session: dict, action: str, graded: bool | None) -> str | None:
    if action == "hint" or (action == "answer" and graded):
        return None
    self_reported = (user.get("profile") or {}).get("learningStyle")
    failed_strategy = session.get("lastStrategy") if action == "explain_again" or (action == "answer" and not graded) else None
    return student_model.choose_strategy(model, self_reported, exclude=failed_strategy)


async def take_turn(user: dict, lesson_id: str, action: str, text: str | None, meta: dict | None = None) -> dict:
    topic, lesson = topics.find_lesson(lesson_id)
    if not user.get("profile"):
        raise HTTPException(409, "Please finish your learning profile first.")
    meta = meta or {}

    key = _session_key(user["id"], lesson_id)
    session = store.get_session(key)
    if session:
        for field, default in _new_session(lesson_id, topic["id"]).items():
            session.setdefault(field, default)
    if action == "start" and session and session["history"]:
        return _response(user, topic, lesson, session, notice=None)
    if action in ("start", "restart") or not session:
        session = _new_session(lesson_id, topic["id"])
        action = "start"
    if session["complete"]:
        raise HTTPException(409, "This lesson is complete. Restart it to practise again.")

    text = (text or "").strip() or None
    pending = session["pending"]
    if action == "answer" and not pending:
        action = "ask"
    if action == "hint" and not pending:
        action = "explain_again"
    if action in ("answer", "ask") and not text:
        raise HTTPException(400, "Please type or say something first.")

    model = student_model.get_model(user)
    prior = student_model.prior_mastery(user, topic)
    student_model.concept(model, lesson_id, prior)
    attributed_strategy = session.get("lastStrategy")
    response_ms = meta.get("responseMs")
    if response_ms is None and action == "answer" and session.get("pendingSince"):
        response_ms = int((time.time() - session["pendingSince"]) * 1000)
    input_mode = meta.get("inputMode")
    base_event = {"lessonId": lesson_id, "topicId": topic["id"]}

    graded = answers.matches(text, pending) if action == "answer" else None
    if action == "start":
        student_model.log_event(user["id"], "lesson_started", **base_event)
    else:
        session["history"].append({"role": "student", "action": action, "text": text or ACTION_LABELS[action]})
    if action == "continue":
        student_model.log_event(user["id"], "continue", dwellMs=response_ms, **base_event)
    elif action == "hint":
        session["hintUsed"] = True
        student_model.record_signal(model, "hint")
        student_model.log_event(user["id"], "hint", question=pending["prompt"], waitedMs=response_ms, **base_event)
    elif action == "explain_again":
        student_model.record_signal(model, "explain_again", strategy=attributed_strategy)
        student_model.log_event(user["id"], "explain_again", strategy=attributed_strategy, inputMode=input_mode, **base_event)
    elif action == "ask":
        student_model.record_signal(model, "ask")
        student_model.log_event(user["id"], "question_asked", text=text, inputMode=input_mode, **base_event)

    strategy = _choose_strategy(user, model, session, action, graded)
    notice = None
    source = "mock"
    step = hidden = misconception = None
    if gemini_enabled():
        try:
            prompt = _prompt(user, topic, lesson, session, action, text, graded, strategy)
            raw = await gemini.generate_json(SYSTEM_PROMPT, [{"text": prompt}], STEP_SCHEMA)
            step, hidden, misconception = _clean_step(raw)
            source = "gemini"
        except gemini.GeminiError as exc:
            log.warning("Falling back to scripted tutor: %s", exc)
            notice = "Gemini was busy for this step, so the offline tutor answered."
    if step is None:
        step, hidden = _mock_step(user, lesson, session, action, graded)

    explained = step["kind"] == "teach" or action in ("explain_again", "ask") or (action == "answer" and not graded)
    # Offline steps keep their scripted style only, so the model learns from real strategy choices.
    if explained and not step.get("strategy") and source == "gemini":
        step["strategy"] = strategy
    if step.get("strategy") and step["kind"] != "summary":
        student_model.record_strategy_use(model, step["strategy"])
        session["lastStrategy"] = step["strategy"]

    if action == "answer":
        correct = bool(graded) or (source == "gemini" and bool(step.get("feedback") and step["feedback"]["correct"]))
        step["kind"] = "feedback"
        message = (step.get("feedback") or {}).get("message") or step["paragraphs"][0]
        step["feedback"] = {"correct": correct, "message": message}
        session["attempts"] += 1
        result = student_model.record_answer(
            model, lesson_id, prior, correct=correct, used_hint=session["hintUsed"], response_ms=response_ms,
            strategy=attributed_strategy, input_mode=input_mode, misconception=None if correct else misconception,
        )
        student_model.log_event(
            user["id"], "answer", question=pending["prompt"], answer=text, correct=correct, responseMs=response_ms,
            slow=result["slow"], inputMode=input_mode, usedHint=session["hintUsed"], attempt=session["attempts"],
            strategy=attributed_strategy, misconception=None if correct else misconception, mastery=result["mastery"], **base_event,
        )
        if correct:
            session["correct"] += 1
            if source == "gemini" and session["correct"] >= TARGET_CORRECT:
                hidden = None
        else:
            session["wrong"] += 1
            hidden = hidden or pending
    elif action in ("hint", "explain_again", "ask") and pending and not hidden:
        hidden = pending

    if hidden and (not pending or hidden["prompt"] != pending["prompt"]):
        session.update(hintUsed=False, attempts=0, pendingSince=time.time())
    session["pending"] = hidden
    if step["kind"] == "summary":
        session["complete"] = True
        session["pending"] = None
    step.update(id=uuid.uuid4().hex, question=_public_question(session["pending"]), source=source)
    session["history"].append({"role": "tutor", "step": step})
    student_model.log_event(user["id"], "tutor_step", kind=step["kind"], title=step["title"], strategy=step.get("strategy"),
                            source=source, hasQuestion=step["question"] is not None, **base_event)

    state = _state(user, topic, lesson, session)
    if session["complete"]:
        student_model.log_event(user["id"], "lesson_completed", mastery=state["mastery"], **base_event)
    user.setdefault("progress", {})[lesson_id] = {"mastery": state["mastery"], "complete": session["complete"], "started": True}
    store.save_model(user["id"], model)
    store.save_session(key, session)
    store.save_user(user)
    return _response(user, topic, lesson, session, notice, response_ms if action == "answer" else None)


def _response(user: dict, topic: dict, lesson: dict, session: dict, notice: str | None, last_response_ms: int | None = None) -> dict:
    return {
        "history": session["history"],
        "state": _state(user, topic, lesson, session),
        "learner": _learner_view(user, topic, lesson, session, last_response_ms),
        "notice": notice,
    }


def pending_question(user: dict, lesson_id: str) -> dict | None:
    session = store.get_session(_session_key(user["id"], lesson_id))
    return session["pending"] if session else None
