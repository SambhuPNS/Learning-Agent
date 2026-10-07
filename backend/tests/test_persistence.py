import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest

from app import student_model, topics, tutor
from app import store as store_module
from app.store import ConcurrentUpdateError, LocalStore, bounded_session


@pytest.fixture
def local_store(tmp_path, monkeypatch):
    monkeypatch.setattr(store_module, "STORE_PATH", tmp_path / "store.json")
    return LocalStore()


def learner(user_id="learner"):
    return {"id": user_id, "name": "Learner", "email": f"{user_id}@example.com", "role": "student",
            "profile": {"grade": 7, "mathConfidence": 3, "fractionsComfort": "some", "learningStyle": "visual"},
            "progress": {}}


def setup_turn(store):
    user = learner()
    assert store.create_user(user, "token")
    user, model, _, version = store.get_learning_state(user["id"], "learner:lesson", student_model._new_model)
    session = tutor._new_session("lesson", "topic")
    event = {"id": "event-1", "userId": user["id"], "type": "answer", "ts": "2026-01-01"}
    return user, model, session, version, [event]


def test_snapshot_changes_do_not_leak(local_store):
    user, model, session, version, _ = setup_turn(local_store)
    user["profile"]["grade"] = 12
    model["behaviour"]["answers"] = 99
    assert local_store.get_user(user["id"])["profile"]["grade"] == 7
    assert local_store.get_model(user["id"], student_model._new_model)["behaviour"]["answers"] == 0
    assert local_store.get_session("learner:lesson") is None


def test_turn_commit_is_persisted_together(local_store):
    user, model, session, version, events = setup_turn(local_store)
    progress = {"mastery": 66, "complete": False, "started": True}
    model["behaviour"]["answers"] = 1
    local_store.commit_learning_turn(user["id"], "learner:lesson", version, model, session, progress, events)
    persisted = json.loads(store_module.STORE_PATH.read_text())
    assert persisted["users"][user["id"]]["progress"]["lesson"] == progress
    assert persisted["studentModels"][user["id"]]["behaviour"]["answers"] == 1
    assert persisted["sessions"]["learner:lesson"]["lessonId"] == "lesson"
    assert persisted["events"] == events


def test_stale_turn_cannot_overwrite_another_lesson(local_store):
    user, model, session, version, events = setup_turn(local_store)
    local_store.commit_learning_turn(user["id"], "learner:lesson", version, model, session, {"mastery": 66}, events)
    stale_session = tutor._new_session("another-lesson", "topic")
    with pytest.raises(ConcurrentUpdateError):
        local_store.commit_learning_turn(user["id"], "learner:another-lesson", version, model, stale_session, {}, [])
    assert local_store.get_session("learner:another-lesson") is None
    assert local_store.get_user(user["id"])["progress"] == {"lesson": {"mastery": 66}}
    assert len(local_store.recent_events(user["id"], 10)) == 1


def test_profile_update_invalidates_in_flight_turn(local_store):
    user, model, session, version, events = setup_turn(local_store)
    local_store.save_profile(user["id"], {"grade": 9})
    with pytest.raises(ConcurrentUpdateError):
        local_store.commit_learning_turn(user["id"], "learner:lesson", version, model, session, {}, events)
    assert local_store.get_user(user["id"])["profile"] == {"grade": 9}
    assert local_store.get_session("learner:lesson") is None


def test_failed_save_does_not_leave_partial_state(local_store, monkeypatch):
    user, model, session, version, events = setup_turn(local_store)
    previous = deepcopy(local_store.data)
    def fail_save():
        raise OSError("disk full")
    monkeypatch.setattr(local_store, "save", fail_save)
    with pytest.raises(OSError, match="disk full"):
        local_store.commit_learning_turn(user["id"], "learner:lesson", version, model, session, {}, events)
    assert local_store.data == previous
    assert json.loads(store_module.STORE_PATH.read_text()) == previous


def test_duplicate_email_registration_is_atomic(local_store):
    def register(index):
        user = {**learner(str(index)), "email": "same@example.com"}
        return local_store.create_user(user, f"token-{index}")
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(register, range(8)))
    assert sum(results) == 1
    assert len(local_store.all_users()) == 1
    assert len(local_store.data["tokens"]) == 1


def test_turn_response_uses_updated_detached_model(local_store, monkeypatch):
    user = learner()
    local_store.create_user(user, "token")
    monkeypatch.setattr(tutor, "store", local_store)
    monkeypatch.setattr(topics, "store", local_store)
    monkeypatch.setattr(student_model, "store", local_store)
    def turn(action, text=None):
        return asyncio.run(tutor.take_turn(user, "comparing-fractions", action, text))
    turn("start")
    turn("continue")
    turn("continue")
    response = turn("answer", "1/4")
    model = local_store.get_model(user["id"], student_model._new_model)
    mastery = round(model["concepts"]["comparing-fractions"]["mastery"] * 100)
    assert mastery > 30
    assert response["state"]["mastery"] == response["learner"]["mastery"] == mastery
    assert local_store.get_user(user["id"])["progress"]["comparing-fractions"]["mastery"] == mastery


def test_turn_conflict_is_explicit_and_has_no_side_effects(local_store, monkeypatch):
    from fastapi import HTTPException

    user = learner()
    local_store.create_user(user, "token")
    monkeypatch.setattr(tutor, "store", local_store)
    monkeypatch.setattr(topics, "store", local_store)
    before = deepcopy(local_store.data)
    def conflict(*args):
        raise ConcurrentUpdateError("stale")
    monkeypatch.setattr(local_store, "commit_learning_turn", conflict)
    with pytest.raises(HTTPException) as raised:
        asyncio.run(tutor.take_turn(user, "comparing-fractions", "start", None))
    assert raised.value.status_code == 409
    assert local_store.data == before


def test_history_is_bounded_without_resetting_step_count():
    session = tutor._new_session("lesson", "topic")
    session["history"] = [{"role": "tutor", "step": {"id": str(index)}} for index in range(100)]
    trimmed = bounded_session(session)
    assert len(trimmed["history"]) == store_module.MAX_SESSION_HISTORY
    assert trimmed["tutorSteps"] == 100
    assert trimmed["history"][-1]["step"]["id"] == "99"
    assert len(session["history"]) == 100


def test_history_byte_limit_preserves_current_step():
    session = tutor._new_session("lesson", "topic")
    session["history"] = [{"role": "tutor", "step": {"text": "x" * 100_000}} for _ in range(12)]
    trimmed = bounded_session(session)
    assert len(json.dumps(trimmed).encode()) <= store_module.MAX_SESSION_BYTES
    assert trimmed["tutorSteps"] == 12
    session["history"] = [{"role": "tutor", "step": {"text": "x" * store_module.MAX_SESSION_BYTES}}]
    with pytest.raises(ValueError, match="storage limit"):
        bounded_session(session)


def test_oversized_legacy_session_can_be_restarted(local_store, monkeypatch):
    from fastapi import HTTPException

    user = learner()
    local_store.create_user(user, "token")
    monkeypatch.setattr(tutor, "store", local_store)
    monkeypatch.setattr(topics, "store", local_store)
    key = "learner:comparing-fractions"
    session = tutor._new_session("comparing-fractions", "fractions")
    session["history"] = [{"role": "tutor", "step": {"text": "x" * store_module.MAX_SESSION_BYTES}}]
    local_store.data["sessions"][key] = session
    with pytest.raises(HTTPException) as raised:
        asyncio.run(tutor.take_turn(user, "comparing-fractions", "start", None))
    assert raised.value.status_code == 413
    response = asyncio.run(tutor.take_turn(user, "comparing-fractions", "restart", None))
    assert response["state"]["step"] == 1
    assert len(response["history"]) == 1
    assert len(json.dumps(local_store.get_session(key)).encode()) < store_module.MAX_SESSION_BYTES


def test_prompt_uses_working_model_without_reloading(local_store, monkeypatch):
    user = learner()
    topic, lesson = topics.find_lesson("comparing-fractions")
    session = tutor._new_session(lesson["id"], topic["id"])
    model = student_model._new_model()
    model["behaviour"]["hints"] = 4
    def unexpected_read(*args):
        pytest.fail("Prompt generation must not reload a stale model.")
    monkeypatch.setattr(student_model, "get_model", unexpected_read)
    prompt = tutor._prompt(user, topic, lesson, session, "start", None, None, "visual", model)
    assert "relies on hints often" in prompt
