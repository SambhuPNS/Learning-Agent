"""Student model: everything the tutor learns about a student from their behaviour.

- Mastery per lesson uses Bayesian Knowledge Tracing (BKT), a standard intelligent-tutoring model.
- Strategy effectiveness tracks which explanation style is followed by correct answers for this student.
- Behaviour tracks response time, hints, re-explanations and voice use.
Every interaction is also appended to an event log with a timestamp.
"""

import math
import uuid

from .store import now_iso, store
from .topics import lesson_title

STRATEGIES = ["visual", "step-by-step", "real-world", "practice"]
STRATEGY_LABELS = {
    "visual": "Visual explanations",
    "step-by-step": "Step-by-step reasoning",
    "real-world": "Real-life examples",
    "practice": "Worked examples & practice",
}
STRATEGY_GUIDES = {
    "visual": "Lead with a diagram, chart or table block and tell the student exactly what to look at in it.",
    "step-by-step": "Explain as short numbered steps in order, one operation or idea per step.",
    "real-world": "Explain through a short, concrete story or example from the student's interests.",
    "practice": "Give a very brief explanation, then a fully worked example the student can copy.",
}
COMFORT_PRIOR = {"new": 0.1, "some": 0.3, "confident": 0.5}
SLIP, GUESS, GUESS_AFTER_HINT, LEARN = 0.1, 0.2, 0.45, 0.12
SLOW_ANSWER_MS = 20_000
EXPLORATION = 0.35


def log_event(events: list[dict], user_id: str, event_type: str, **data) -> dict:
    event = {"id": uuid.uuid4().hex[:12], "ts": now_iso(), "userId": user_id, "type": event_type, **data}
    events.append(event)
    return event


def _new_model() -> dict:
    return {
        "concepts": {},
        "strategies": {s: {"uses": 0, "success": 0, "fail": 0, "confused": 0} for s in STRATEGIES},
        "misconceptions": {},
        "behaviour": {"answers": 0, "avgResponseMs": None, "slowAnswers": 0, "hints": 0, "explainAgain": 0,
                      "questionsAsked": 0, "voiceAnswers": 0},
        "updatedAt": now_iso(),
    }


def get_model(user: dict) -> dict:
    return store.get_model(user["id"], _new_model)


def prior_mastery(user: dict, topic: dict) -> float:
    profile = user.get("profile") or {}
    if topic["id"] == "fractions":
        return COMFORT_PRIOR.get(profile.get("fractionsComfort", "some"), 0.3)
    confidence = profile.get("mathConfidence", 3) if topic.get("subject", "").lower().startswith("math") else 3
    return 0.1 + 0.08 * (confidence - 1)


def concept(model: dict, lesson_id: str, prior: float) -> dict:
    return model["concepts"].setdefault(lesson_id, {
        "mastery": round(prior, 3), "attempts": 0, "correct": 0, "hintsUsed": 0, "slowAnswers": 0,
        "avgResponseMs": None, "lastSeen": now_iso(),
    })


def _ema(previous: float | None, value: float, alpha: float = 0.3) -> float:
    return value if previous is None else (1 - alpha) * previous + alpha * value


def record_answer(model: dict, lesson_id: str, prior: float, *, correct: bool, used_hint: bool, response_ms: int | None,
                  strategy: str | None, input_mode: str | None, misconception: str | None) -> dict:
    item = concept(model, lesson_id, prior)
    p = item["mastery"]
    guess = GUESS_AFTER_HINT if used_hint else GUESS
    if correct:
        posterior = p * (1 - SLIP) / (p * (1 - SLIP) + (1 - p) * guess)
    else:
        posterior = p * SLIP / (p * SLIP + (1 - p) * (1 - guess))
    item["mastery"] = round(posterior + (1 - posterior) * LEARN, 3)
    item["attempts"] += 1
    item["correct"] += int(correct)
    item["hintsUsed"] += int(used_hint)
    item["lastSeen"] = now_iso()

    behaviour = model["behaviour"]
    slow = False
    if response_ms is not None:
        baseline = behaviour["avgResponseMs"]
        slow = response_ms > max(SLOW_ANSWER_MS, 2 * baseline) if baseline else response_ms > SLOW_ANSWER_MS
        behaviour["avgResponseMs"] = round(_ema(baseline, response_ms))
        item["avgResponseMs"] = round(_ema(item["avgResponseMs"], response_ms))
    behaviour["answers"] += 1
    behaviour["slowAnswers"] += int(slow)
    behaviour["voiceAnswers"] += int(input_mode == "voice")
    item["slowAnswers"] += int(slow)

    if strategy in model["strategies"]:
        model["strategies"][strategy]["success" if correct else "fail"] += 1
    if not correct and misconception:
        label = misconception.strip()[:140]
        entry = model["misconceptions"].setdefault(label, {"count": 0, "lessonId": lesson_id, "lastSeen": None})
        entry["count"] += 1
        entry["lastSeen"] = now_iso()
    model["updatedAt"] = now_iso()
    return {"mastery": item["mastery"], "slow": slow}


def record_strategy_use(model: dict, strategy: str) -> None:
    if strategy in model["strategies"]:
        model["strategies"][strategy]["uses"] += 1


def record_signal(model: dict, signal: str, strategy: str | None = None) -> None:
    behaviour = model["behaviour"]
    if signal == "hint":
        behaviour["hints"] += 1
    elif signal == "explain_again":
        behaviour["explainAgain"] += 1
        if strategy in model["strategies"]:
            model["strategies"][strategy]["confused"] += 1
    elif signal == "ask":
        behaviour["questionsAsked"] += 1
    model["updatedAt"] = now_iso()


def strategy_scores(model: dict, self_reported: str | None) -> dict[str, dict]:
    scores = {}
    for name, stats in model["strategies"].items():
        alpha = 1 + stats["success"] + (1 if name == self_reported else 0)
        beta = 1 + stats["fail"] + stats["confused"]
        scores[name] = {**stats, "evidence": stats["success"] + stats["fail"] + stats["confused"],
                        "score": round(alpha / (alpha + beta), 3)}
    return scores


def choose_strategy(model: dict, self_reported: str | None, exclude: str | None = None) -> str:
    """Upper-confidence-bound choice: favour what works, but keep testing styles with little evidence."""
    scores = strategy_scores(model, self_reported)
    total = sum(s["evidence"] for s in scores.values()) + 1
    best, best_value = None, -1.0
    for name in STRATEGIES:
        if name == exclude:
            continue
        stats = scores[name]
        value = stats["score"] + EXPLORATION * math.sqrt(math.log(total + 1) / (stats["evidence"] + 1))
        if name == self_reported:
            value += 1e-6
        if value > best_value:
            best, best_value = name, value
    return best or (self_reported or "visual")


def best_strategy(model: dict, self_reported: str | None) -> str:
    scores = strategy_scores(model, self_reported)
    return max(STRATEGIES, key=lambda s: (scores[s]["score"], s == self_reported))


def difficulty_for(mastery: float) -> str:
    if mastery < 0.35:
        return "foundation"
    if mastery < 0.7:
        return "core"
    return "stretch"


DIFFICULTY_GUIDES = {
    "foundation": "Foundation level: tiny steps, concrete examples, easy numbers, lots of encouragement.",
    "core": "Core level: standard grade-level explanations and questions.",
    "stretch": "Stretch level: the student is doing well, so use harder questions and fewer hints.",
}


def prompt_summary(model: dict, user: dict, lesson_id: str, prior: float) -> dict:
    """Evidence-based view of the student that is sent to Gemini on every turn."""
    profile = user.get("profile") or {}
    item = concept(model, lesson_id, prior)
    scores = strategy_scores(model, profile.get("learningStyle"))
    behaviour = model["behaviour"]
    answers = max(1, behaviour["answers"])
    misconceptions = sorted(model["misconceptions"].items(), key=lambda kv: -kv[1]["count"])[:3]
    notes = []
    if behaviour["avgResponseMs"]:
        notes.append(f"usually answers in about {behaviour['avgResponseMs'] / 1000:.0f} seconds")
    if behaviour["slowAnswers"] / answers > 0.3:
        notes.append("often needs extra thinking time: keep steps short and calm")
    if behaviour["hints"] / answers > 0.4:
        notes.append("relies on hints often: build confidence with scaffolding")
    if behaviour["explainAgain"] >= 2:
        notes.append("has asked for re-explanations several times: check understanding more often")
    return {
        "masteryOfThisLesson": f"{round(item['mastery'] * 100)}%",
        "difficulty": difficulty_for(item["mastery"]),
        "explanationStylesThatWork": {
            name: f"{round(s['score'] * 100)}% success ({s['evidence']} observations)" for name, s in scores.items()
        },
        "knownMisconceptions": [label for label, _ in misconceptions],
        "behaviourNotes": notes,
    }


def insights(user: dict) -> dict:
    """Readable summary of the student model for the student and teacher dashboards."""
    model = get_model(user)
    profile = user.get("profile") or {}
    self_reported = profile.get("learningStyle")
    scores = strategy_scores(model, self_reported)
    best = best_strategy(model, self_reported)
    behaviour = model["behaviour"]
    answers = behaviour["answers"]
    concepts = []
    for lesson_id, item in model["concepts"].items():
        topic_title, title = lesson_title(lesson_id)
        concepts.append({"lessonId": lesson_id, "lessonTitle": title, "topicTitle": topic_title,
                         "mastery": round(item["mastery"] * 100), "attempts": item["attempts"], "correct": item["correct"],
                         "avgResponseSec": round(item["avgResponseMs"] / 1000, 1) if item["avgResponseMs"] else None,
                         "lastSeen": item["lastSeen"]})
    concepts.sort(key=lambda c: c["lastSeen"] or "", reverse=True)
    misconceptions = [{"label": label, "count": entry["count"], "lessonId": entry["lessonId"]}
                      for label, entry in sorted(model["misconceptions"].items(), key=lambda kv: -kv[1]["count"])][:5]
    practised = [c for c in concepts if c["attempts"]]
    recommendations = []
    evidence = scores[best]["evidence"]
    if evidence >= 2:
        recommendations.append(f"Learns best with {STRATEGY_LABELS[best].lower()} ({round(scores[best]['score'] * 100)}% success).")
    if self_reported and best != self_reported and evidence >= 3:
        recommendations.append(f"Chose '{STRATEGY_LABELS[self_reported]}' at sign-up, but the evidence favours {STRATEGY_LABELS[best].lower()}.")
    weak = [c for c in practised if c["mastery"] < 50]
    if weak:
        recommendations.append(f"Needs more practice on {weak[0]['lessonTitle']} ({weak[0]['mastery']}% mastery).")
    if answers and behaviour["slowAnswers"] / answers > 0.3:
        recommendations.append("Often takes extra time to answer; shorter steps help.")
    if misconceptions:
        recommendations.append(f"Watch for: {misconceptions[0]['label']}")
    return {
        "overallMastery": round(sum(c["mastery"] for c in practised) / len(practised)) if practised else None,
        "concepts": concepts,
        "strategies": [{"strategy": s, "label": STRATEGY_LABELS[s], "score": round(scores[s]["score"] * 100),
                        "evidence": scores[s]["evidence"], "uses": scores[s]["uses"], "success": scores[s]["success"],
                        "fail": scores[s]["fail"], "confused": scores[s]["confused"]} for s in STRATEGIES],
        "bestStrategy": best,
        "selfReportedStrategy": self_reported,
        "misconceptions": misconceptions,
        "behaviour": {
            "answers": answers,
            "avgResponseSec": round(behaviour["avgResponseMs"] / 1000, 1) if behaviour["avgResponseMs"] else None,
            "slowAnswers": behaviour["slowAnswers"],
            "hintRate": round(100 * behaviour["hints"] / answers) if answers else 0,
            "explainAgain": behaviour["explainAgain"],
            "questionsAsked": behaviour["questionsAsked"],
            "voiceShare": round(100 * behaviour["voiceAnswers"] / answers) if answers else 0,
        },
        "recommendations": recommendations,
        "updatedAt": model["updatedAt"],
    }


def recent_events(user_id: str, limit: int = 40) -> list[dict]:
    return store.recent_events(user_id, limit)
