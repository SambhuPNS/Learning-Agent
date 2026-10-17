"""Personalisation across lessons and the reasons shown with each step."""

import asyncio

from app import curriculum, gemini, student_model, topics, tutor
from app import store as store_module
from app.store import LocalStore

FRACTIONS = curriculum.seed_topics("2026-01-01T00:00:00+00:00")[0]
USER = {"id": "u", "name": "Ana Lee", "profile": {"grade": 7, "mathConfidence": 3, "fractionsComfort": "some",
                                                  "learningStyle": "visual", "pace": "steady", "interests": []}}


def practised(mastery: float, attempts: int) -> dict:
    model = student_model._new_model()
    student_model.concept(model, "fraction-basics", 0.3).update(mastery=mastery, attempts=attempts)
    return model


def test_a_new_lesson_starts_from_earlier_lessons_in_the_topic():
    signup = student_model.prior_mastery(USER, FRACTIONS)
    assert signup == 0.3
    assert student_model.prior_mastery(USER, FRACTIONS, practised(0.95, 8)) > 0.5
    assert student_model.prior_mastery(USER, FRACTIONS, practised(0.1, 8)) < signup
    # One answer is weak evidence, so the sign-up answer still dominates.
    assert abs(student_model.prior_mastery(USER, FRACTIONS, practised(0.95, 1)) - signup) < 0.1
    other_topic = {"id": "photosynthesis", "subject": "Science", "lessons": [{"id": "photosynthesis-equation"}]}
    assert student_model.prior_mastery(USER, other_topic, practised(0.95, 8)) == student_model.prior_mastery(USER, other_topic)


def test_reasons_follow_the_evidence():
    model = student_model._new_model()
    student_model.concept(model, "fraction-basics", 0.3)
    why = lambda strategy, **kw: student_model.why_step(model, USER, FRACTIONS, "fraction-basics", strategy, **kw)
    assert why("visual") == "Using a picture, as you chose at sign-up."
    assert why("practice") == "Trying a worked example to see whether it suits you."
    assert why("real-world", replacing="visual") == "Trying a real-life example this time, since a picture didn't quite land."
    model["strategies"]["real-world"]["success"] = 4
    assert why("real-world").startswith("Real-life examples have helped you most so far (4 right answers)")
    model["concepts"]["fraction-basics"].update(mastery=0.9, attempts=5)
    assert why(None) == "You're doing well here, so the questions get harder."


def test_gemini_steps_explain_themselves(tmp_path, monkeypatch):
    monkeypatch.setattr(store_module, "STORE_PATH", tmp_path / "store.json")
    store = LocalStore()
    for module in (tutor, topics, student_model):
        monkeypatch.setattr(module, "store", store)
    monkeypatch.setattr(tutor, "gemini_enabled", lambda: True)

    async def fake(system, parts, schema, timeout=60, thinking="low", **_options):
        return {"kind": "teach", "title": "Hello", "strategy": "visual", "blocks": [{"type": "text", "text": "Hi"}],
                "speech": "Hi", "feedback": None, "question": None}

    monkeypatch.setattr(gemini, "generate_json", fake)
    user = {**USER, "id": "learner", "email": "ana@example.com", "role": "student", "progress": {}}
    store.create_user(user, "token")
    first = asyncio.run(tutor.take_turn(user, "fraction-basics", "start", None))["history"][-1]["step"]
    assert first["why"] == "Using a picture, as you chose at sign-up."


def test_tied_misconceptions_rank_the_same_whatever_order_storage_returns():
    entries = {
        "Swapping numerator and denominator": {"count": 2, "lessonId": "fraction-basics", "lastSeen": "2026-10-10T09:00:00+00:00"},
        "Adding the same number to top and bottom": {"count": 2, "lessonId": "fraction-basics", "lastSeen": "2026-10-12T09:00:00+00:00"},
        "Counting unequal pieces as fractions": {"count": 1, "lessonId": "fraction-basics", "lastSeen": "2026-10-13T09:00:00+00:00"},
    }
    tops = set()
    for order in (list(entries), list(reversed(entries))):
        model = student_model._new_model()
        model["misconceptions"] = {label: entries[label] for label in order}
        ranked = [label for label, _ in student_model.ranked_misconceptions(model)]
        tops.add(tuple(ranked))
        view = tutor._learner_view(USER, FRACTIONS, FRACTIONS["lessons"][0], {"lastStrategy": None}, model)
        assert view["watchFor"] == "Counting unequal pieces as fractions"
    assert tops == {("Adding the same number to top and bottom", "Swapping numerator and denominator", "Counting unequal pieces as fractions")}
