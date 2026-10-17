import asyncio
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from app import student_model, topics, tutor
from app.store import ConcurrentUpdateError, FirestoreStore
from scripts.migrate_store_to_firestore import load_documents


@pytest.fixture
def firestore_store():
    host = os.environ.get("FIRESTORE_EMULATOR_HOST")
    if not host:
        pytest.skip("Start a local Firestore emulator to run transaction integration tests.")
    if host.rsplit(":", 1)[0] not in {"127.0.0.1", "localhost", "[::1]"}:
        pytest.fail("Firestore integration tests only allow a loopback emulator.")
    client = firestore.Client(project=f"demo-learning-{uuid.uuid4().hex[:12]}", credentials=AnonymousCredentials())
    yield FirestoreStore(client)
    client.close()


def user(user_id="learner"):
    return {"id": user_id, "name": "Learner", "email": f"{user_id}@example.com", "role": "student",
            "profile": {"grade": 7, "fractionsComfort": "some", "learningStyle": "visual"}, "progress": {}}


def test_firestore_registration_is_atomic(firestore_store):
    def register(index):
        learner = {**user(str(index)), "email": "same@example.com"}
        return firestore_store.create_user(learner, f"token-{index}")
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(register, range(4)))
    assert sum(results) == 1
    assert len(firestore_store.all_users()) == 1
    assert len(list(firestore_store.db.collection("tokens").stream())) == 1


def test_firestore_concurrent_turns_commit_only_one_snapshot(firestore_store):
    learner = user()
    firestore_store.create_user(learner, "token")
    _, model, _, version = firestore_store.get_learning_state(learner["id"], "learner:lesson", student_model._new_model)
    def commit(index):
        session = tutor._new_session(f"lesson-{index}", "topic")
        event = {"id": f"event-{index}", "userId": learner["id"], "ts": f"2026-01-0{index + 1}"}
        try:
            firestore_store.commit_learning_turn(learner["id"], f"learner:lesson-{index}", version,
                                                  {**model, "winner": index}, session, {"mastery": index}, [event])
            return index
        except ConcurrentUpdateError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(commit, range(2)))
    winners = [result for result in results if result is not None]
    assert len(winners) == 1
    winner = winners[0]
    assert firestore_store.get_user(learner["id"])["progress"] == {f"lesson-{winner}": {"mastery": winner}}
    assert firestore_store.get_model(learner["id"], student_model._new_model)["winner"] == winner
    assert firestore_store.get_session(f"learner:lesson-{winner}") is not None
    assert firestore_store.get_session(f"learner:lesson-{1 - winner}") is None
    assert [event["id"] for event in firestore_store.recent_events(learner["id"], 10)] == [f"event-{winner}"]
    other = 1 - winner
    _, next_model, _, next_version = firestore_store.get_learning_state(
        learner["id"], f"learner:lesson-{other}", student_model._new_model,
    )
    firestore_store.commit_learning_turn(learner["id"], f"learner:lesson-{other}", next_version, next_model,
                                          tutor._new_session(f"lesson-{other}", "topic"), {"mastery": 80}, [])
    assert firestore_store.get_user(learner["id"])["progress"] == {
        f"lesson-{winner}": {"mastery": winner}, f"lesson-{other}": {"mastery": 80},
    }


def test_firestore_invalid_write_cannot_partially_commit(firestore_store):
    learner = user()
    firestore_store.create_user(learner, "token")
    _, model, _, version = firestore_store.get_learning_state(learner["id"], "learner:lesson", student_model._new_model)
    with pytest.raises(TypeError):
        firestore_store.commit_learning_turn(learner["id"], "learner:lesson", version,
                                              {**model, "invalid": object()}, tutor._new_session("lesson", "topic"), {}, [])
    assert firestore_store.get_user(learner["id"])["progress"] == {}
    assert firestore_store.get_session("learner:lesson") is None
    assert not list(firestore_store.db.collection("studentModels").stream())


def test_firestore_profile_changes_preserve_progress_and_invalidate_turn(firestore_store):
    learner = user()
    learner["progress"] = {"previous": {"mastery": 80}}
    firestore_store.create_user(learner, "token")
    _, model, _, version = firestore_store.get_learning_state(learner["id"], "learner:lesson", student_model._new_model)
    firestore_store.save_profile(learner["id"], {"grade": 9})
    with pytest.raises(ConcurrentUpdateError):
        firestore_store.commit_learning_turn(learner["id"], "learner:lesson", version, model,
                                              tutor._new_session("lesson", "topic"), {}, [])
    persisted = firestore_store.get_user(learner["id"])
    assert persisted["profile"] == {"grade": 9}
    assert persisted["progress"] == {"previous": {"mastery": 80}}


def test_firestore_tutor_returns_current_mastery(firestore_store, monkeypatch):
    learner = user()
    firestore_store.create_user(learner, "token")
    monkeypatch.setattr(tutor, "store", firestore_store)
    monkeypatch.setattr(topics, "store", firestore_store)
    monkeypatch.setattr(student_model, "store", firestore_store)
    def turn(action, text=None):
        return asyncio.run(tutor.take_turn(learner, "comparing-fractions", action, text))
    turn("start")
    turn("continue")
    turn("continue")
    response = turn("answer", "1/4")
    persisted = firestore_store.get_model(learner["id"], student_model._new_model)
    mastery = round(persisted["concepts"]["comparing-fractions"]["mastery"] * 100)
    assert response["state"]["mastery"] == response["learner"]["mastery"] == mastery
    assert firestore_store.get_user(learner["id"])["progress"]["comparing-fractions"]["mastery"] == mastery
    assert persisted["behaviour"]["answers"] == 1
    assert len(firestore_store.recent_events(learner["id"], 20)) == 8


def test_migrated_tokens_support_lookup_and_logout(firestore_store):
    learner = user()
    batch = firestore_store.db.batch()
    for collection, document_id, payload in load_documents({
        "users": {learner["id"]: learner}, "tokens": {"hash": learner["id"]},
    }):
        batch.set(firestore_store.db.collection(collection).document(document_id), payload)
    batch.commit()
    assert firestore_store.get_token_user_id("hash") == learner["id"]
    assert firestore_store.find_user_by_email(learner["email"])["id"] == learner["id"]
    firestore_store.delete_token("hash")
    assert firestore_store.get_token_user_id("hash") is None


def test_firestore_homework_is_handed_in_once_and_updates_the_model_together(firestore_store):
    learner = user()
    firestore_store.create_user(learner, "token")
    homework = {"id": "hw1", "createdBy": "teacher", "title": "Practice", "lessonId": "comparing-fractions"}
    firestore_store.save_homework(homework)
    assert firestore_store.get_homework("hw1")["title"] == "Practice"
    assert [item["id"] for item in firestore_store.all_homework()] == ["hw1"]

    draft = {"homeworkId": "hw1", "userId": learner["id"], "answers": {"q1": "A"}, "submittedAt": None}
    assert firestore_store.save_submission(draft) is True
    assert firestore_store.submissions_for_user(learner["id"])[0]["answers"] == {"q1": "A"}
    assert [item["userId"] for item in firestore_store.submissions_for_homework("hw1")] == [learner["id"]]

    model = firestore_store.get_model(learner["id"], student_model._new_model)
    done = {**draft, "submittedAt": "2026-01-01T00:00:00+00:00", "score": 1, "total": 1, "graded": []}
    event = {"id": "event-1", "userId": learner["id"], "ts": "2026-01-01", "type": "homework_submitted"}
    with pytest.raises(ConcurrentUpdateError):
        firestore_store.commit_homework(learner["id"], 99, model, done, [event])
    assert firestore_store.commit_homework(learner["id"], 0, model, done, [event]) is True
    assert firestore_store.commit_homework(learner["id"], 1, model, done, [event]) is False
    assert firestore_store.save_submission({**draft, "answers": {"q1": "B"}}) is False
    assert firestore_store.get_submission("hw1", learner["id"])["score"] == 1
    assert firestore_store.get_user(learner["id"])["_learningVersion"] == 1
    assert len(firestore_store.recent_events(learner["id"], 5)) == 1

    firestore_store.delete_homework("hw1")
    assert firestore_store.get_homework("hw1") is None


def test_firestore_sessions_keep_table_rows(firestore_store):
    learner = user()
    firestore_store.create_user(learner, "token")
    _, model, _, version = firestore_store.get_learning_state(learner["id"], "learner:tables", student_model._new_model)
    session = tutor._new_session("comparing-fractions", "fractions")
    table = {"type": "visual", "visual": {"type": "table", "columns": ["a", "b"], "rows": [["1", "2"], ["3", "4"]]}}
    session["history"].append({"role": "tutor", "content": [table], "speech": "A table."})
    firestore_store.commit_learning_turn(learner["id"], "learner:tables", version, model, session, {"mastery": 0}, [])
    stored = firestore_store.get_session("learner:tables")
    assert stored["history"][-1]["content"][0]["visual"]["rows"] == [["1", "2"], ["3", "4"]]
    _, _, again, _ = firestore_store.get_learning_state(learner["id"], "learner:tables", student_model._new_model)
    assert again["history"][-1]["content"][0]["visual"]["rows"] == [["1", "2"], ["3", "4"]]


def test_firestore_usage_records_are_saved_newest_first_and_expire(firestore_store):
    from datetime import datetime, timedelta, timezone

    base = datetime.now(timezone.utc)
    for index in range(3):
        firestore_store.save_llm_call({"id": f"call{index}", "ts": (base - timedelta(minutes=index)).isoformat(), "userId": "u",
                                       "feature": "tutor.step", "model": "m", "totalTokens": 10 + index, "outcome": "ok"})
    firestore_store.save_llm_call({"id": "old", "ts": (base - timedelta(days=40)).isoformat(), "userId": "u",
                                   "feature": "tutor.step", "model": "m", "totalTokens": 1, "outcome": "ok"})
    rows, truncated = firestore_store.llm_calls_since((base - timedelta(days=7)).isoformat(), 10)
    assert [row["id"] for row in rows] == ["call0", "call1", "call2"] and truncated is False
    assert "expireAt" not in rows[0]
    raw = firestore_store.db.collection("llmCalls").document("call0").get().to_dict()
    assert raw["expireAt"] > base + timedelta(days=29)
    assert len(firestore_store.llm_calls_since((base - timedelta(days=7)).isoformat(), 2)[0]) == 2
