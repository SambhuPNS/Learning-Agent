import json
import os
import threading
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Callable

from .config import FIRESTORE_ENABLED, STORE_PATH
from .curriculum import seed_topics

MAX_EVENTS = 20_000
MAX_SESSION_HISTORY = 64
MAX_SESSION_BYTES = 750_000


class ConcurrentUpdateError(RuntimeError):
    pass


def bounded_session(session: dict) -> dict:
    session = deepcopy(session)
    history = session["history"]
    session.setdefault("tutorSteps", sum(item["role"] == "tutor" for item in history))
    session["history"] = history[-MAX_SESSION_HISTORY:]
    while len(json.dumps(session, ensure_ascii=False).encode("utf-8")) > MAX_SESSION_BYTES:
        if len(session["history"]) <= 1:
            raise ValueError("The current lesson step exceeds the session storage limit.")
        session["history"].pop(0)
    return session


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class JsonStore:
    """Tiny file-backed store standing in for Firestore during local development."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if STORE_PATH.exists():
            with STORE_PATH.open(encoding="utf-8") as handle:
                data = json.load(handle)
        else:
            data = {}
        return self.migrate(data)

    @staticmethod
    def migrate(data: dict[str, Any]) -> dict[str, Any]:
        for key in ("users", "tokens", "sessions", "studentModels"):
            data.setdefault(key, {})
        data.setdefault("events", [])
        topics = data.setdefault("topics", {})
        for topic in seed_topics(now_iso()):
            topics.setdefault(topic["id"], topic)
        for user in data["users"].values():
            user.setdefault("role", "student")
        return data

    def save(self) -> None:
        with self.lock:
            if len(self.data["events"]) > MAX_EVENTS:
                self.data["events"] = self.data["events"][-MAX_EVENTS:]
            STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = STORE_PATH.with_suffix(".tmp")
            with tmp_path.open("w", encoding="utf-8") as handle:
                json.dump(self.data, handle, indent=2)
            os.replace(tmp_path, STORE_PATH)


class FirestoreStore:
    """Firestore persistence used by Cloud Run; documents are never kept in container storage."""

    def __init__(self, db=None) -> None:
        if db is None:
            from .firestore_db import db

        self.db = db
        self._seed_topics()

    @staticmethod
    def _email_id(email: str) -> str:
        return sha256(email.encode()).hexdigest()

    def _seed_topics(self) -> None:
        """Adds any starter topic that is missing; existing topics, including edited ones, are left alone."""
        from google.cloud import firestore

        topics = seed_topics(now_iso())
        refs = [self.db.collection("topics").document(topic["id"]) for topic in topics]
        if all(snapshot.exists for snapshot in self.db.get_all(refs)):
            return

        @firestore.transactional
        def seed(transaction):
            snapshots = [next(transaction.get(ref)) for ref in refs]
            for ref, snapshot, topic in zip(refs, snapshots, topics):
                if not snapshot.exists:
                    transaction.set(ref, topic)

        seed(self.db.transaction())

    def create_user(self, user: dict, token_hash: str) -> bool:
        from google.cloud import firestore

        email_ref = self.db.collection("userEmails").document(self._email_id(user["email"]))
        user_ref = self.db.collection("users").document(user["id"])
        token_ref = self.db.collection("tokens").document(token_hash)
        transaction = self.db.transaction()

        @firestore.transactional
        def create(transaction):
            email_snapshot = next(transaction.get(email_ref))
            if email_snapshot.exists:
                return False
            transaction.set(user_ref, user)
            transaction.set(email_ref, {"userId": user["id"]})
            transaction.set(token_ref, {"userId": user["id"]})
            return True

        return bool(create(transaction))

    def get_user(self, user_id: str) -> dict | None:
        snapshot = self.db.collection("users").document(user_id).get()
        return snapshot.to_dict() if snapshot.exists else None

    def find_user_by_email(self, email: str) -> dict | None:
        email_snapshot = self.db.collection("userEmails").document(self._email_id(email)).get()
        if not email_snapshot.exists:
            return None
        return self.get_user(email_snapshot.to_dict()["userId"])

    def save_profile(self, user_id: str, profile: dict) -> None:
        from google.cloud import firestore

        self.db.collection("users").document(user_id).update({
            "profile": profile,
            "_learningVersion": firestore.Increment(1),
        })

    def all_users(self) -> list[dict]:
        return [snapshot.to_dict() for snapshot in self.db.collection("users").stream()]

    def save_token(self, token_hash: str, user_id: str) -> None:
        self.db.collection("tokens").document(token_hash).set({"userId": user_id})

    def get_token_user_id(self, token_hash: str) -> str | None:
        snapshot = self.db.collection("tokens").document(token_hash).get()
        return snapshot.to_dict()["userId"] if snapshot.exists else None

    def delete_token(self, token_hash: str) -> None:
        self.db.collection("tokens").document(token_hash).delete()

    def link_google_account(self, user_id: str, google_id: str) -> None:
        """Attach a Google identity, removing the password and signing out every existing session."""
        from google.cloud import firestore
        from google.cloud.firestore_v1.base_query import FieldFilter

        for snapshot in self.db.collection("tokens").where(filter=FieldFilter("userId", "==", user_id)).stream():
            snapshot.reference.delete()
        self.db.collection("users").document(user_id).update({
            "googleId": google_id, "salt": firestore.DELETE_FIELD, "passwordHash": firestore.DELETE_FIELD,
        })

    def all_topics(self) -> list[dict]:
        return [snapshot.to_dict() for snapshot in self.db.collection("topics").stream()]

    def get_topic(self, topic_id: str) -> dict | None:
        snapshot = self.db.collection("topics").document(topic_id).get()
        return snapshot.to_dict() if snapshot.exists else None

    def save_topic(self, topic: dict) -> None:
        self.db.collection("topics").document(topic["id"]).set(topic)

    def delete_topic(self, topic_id: str) -> None:
        self.db.collection("topics").document(topic_id).delete()

    def get_session(self, key: str) -> dict | None:
        snapshot = self.db.collection("sessions").document(key).get()
        return snapshot.to_dict() if snapshot.exists else None

    def get_model(self, user_id: str, factory: Callable[[], dict]) -> dict:
        snapshot = self.db.collection("studentModels").document(user_id).get()
        return snapshot.to_dict() if snapshot.exists else factory()

    def get_learning_state(self, user_id: str, key: str, factory: Callable[[], dict]) -> tuple[dict, dict, dict | None, int]:
        from google.cloud import firestore

        @firestore.transactional
        def read(transaction):
            user = next(transaction.get(self.db.collection("users").document(user_id))).to_dict()
            if user is None:
                raise ConcurrentUpdateError("The learner account no longer exists.")
            model = next(transaction.get(self.db.collection("studentModels").document(user_id))).to_dict()
            session = next(transaction.get(self.db.collection("sessions").document(key))).to_dict()
            return user, model if model is not None else factory(), session, user.get("_learningVersion", 0)

        return read(self.db.transaction())

    def commit_learning_turn(self, user_id: str, key: str, version: int, model: dict,
                             session: dict, progress: dict, events: list[dict]) -> None:
        from google.cloud import firestore

        session = bounded_session(session)
        user_ref = self.db.collection("users").document(user_id)

        @firestore.transactional
        def commit(transaction):
            user = next(transaction.get(user_ref)).to_dict()
            if user is None or user.get("_learningVersion", 0) != version:
                raise ConcurrentUpdateError("Another request changed this learner's progress.")
            updated_progress = {**user.get("progress", {}), session["lessonId"]: progress}
            transaction.update(user_ref, {"progress": updated_progress, "_learningVersion": version + 1})
            transaction.set(self.db.collection("studentModels").document(user_id), model)
            transaction.set(self.db.collection("sessions").document(key), session)
            for event in events:
                transaction.set(self.db.collection("events").document(event["id"]), event)

        commit(self.db.transaction())

    def recent_events(self, user_id: str, limit: int) -> list[dict]:
        from google.cloud import firestore
        from google.cloud.firestore_v1.base_query import FieldFilter

        query = (
            self.db.collection("events")
            .where(filter=FieldFilter("userId", "==", user_id))
            .order_by("ts", direction=firestore.Query.DESCENDING)
            .limit(limit)
        )
        return [snapshot.to_dict() for snapshot in query.stream()]

    def last_active(self, user_id: str) -> str | None:
        events = self.recent_events(user_id, 1)
        return events[0]["ts"] if events else None


class LocalStore(JsonStore):
    """JSON-backed implementation with the same operations as FirestoreStore."""

    def create_user(self, user: dict, token_hash: str) -> bool:
        with self.lock:
            if any(item["email"] == user["email"] for item in self.data["users"].values()):
                return False
            self.data["users"][user["id"]] = deepcopy(user)
            self.data["tokens"][token_hash] = user["id"]
            self.save()
            return True

    def get_user(self, user_id: str) -> dict | None:
        with self.lock:
            return deepcopy(self.data["users"].get(user_id))

    def find_user_by_email(self, email: str) -> dict | None:
        with self.lock:
            return deepcopy(next((user for user in self.data["users"].values() if user["email"] == email), None))

    def save_profile(self, user_id: str, profile: dict) -> None:
        with self.lock:
            user = self.data["users"][user_id]
            user["profile"] = deepcopy(profile)
            user["_learningVersion"] = user.get("_learningVersion", 0) + 1
            self.save()

    def all_users(self) -> list[dict]:
        with self.lock:
            return deepcopy(list(self.data["users"].values()))

    def save_token(self, token_hash: str, user_id: str) -> None:
        with self.lock:
            self.data["tokens"][token_hash] = user_id
            self.save()

    def get_token_user_id(self, token_hash: str) -> str | None:
        with self.lock:
            return self.data["tokens"].get(token_hash)

    def delete_token(self, token_hash: str) -> None:
        with self.lock:
            self.data["tokens"].pop(token_hash, None)
            self.save()

    def link_google_account(self, user_id: str, google_id: str) -> None:
        with self.lock:
            user = self.data["users"][user_id]
            user["googleId"] = google_id
            user.pop("salt", None)
            user.pop("passwordHash", None)
            self.data["tokens"] = {token: owner for token, owner in self.data["tokens"].items() if owner != user_id}
            self.save()

    def all_topics(self) -> list[dict]:
        with self.lock:
            return deepcopy(list(self.data["topics"].values()))

    def get_topic(self, topic_id: str) -> dict | None:
        with self.lock:
            return deepcopy(self.data["topics"].get(topic_id))

    def save_topic(self, topic: dict) -> None:
        with self.lock:
            self.data["topics"][topic["id"]] = deepcopy(topic)
            self.save()

    def delete_topic(self, topic_id: str) -> None:
        with self.lock:
            del self.data["topics"][topic_id]
            self.save()

    def get_session(self, key: str) -> dict | None:
        with self.lock:
            return deepcopy(self.data["sessions"].get(key))

    def get_model(self, user_id: str, factory: Callable[[], dict]) -> dict:
        with self.lock:
            model = self.data["studentModels"].get(user_id)
            return deepcopy(model) if model is not None else factory()

    def get_learning_state(self, user_id: str, key: str, factory: Callable[[], dict]) -> tuple[dict, dict, dict | None, int]:
        with self.lock:
            user = self.get_user(user_id)
            if user is None:
                raise ConcurrentUpdateError("The learner account no longer exists.")
            return user, self.get_model(user_id, factory), self.get_session(key), user.get("_learningVersion", 0)

    def commit_learning_turn(self, user_id: str, key: str, version: int, model: dict,
                             session: dict, progress: dict, events: list[dict]) -> None:
        session = bounded_session(session)
        with self.lock:
            user = self.data["users"].get(user_id)
            if user is None or user.get("_learningVersion", 0) != version:
                raise ConcurrentUpdateError("Another request changed this learner's progress.")
            previous = self.data
            updated = deepcopy(previous)
            updated["users"][user_id].setdefault("progress", {})[session["lessonId"]] = deepcopy(progress)
            updated["users"][user_id]["_learningVersion"] = version + 1
            updated["studentModels"][user_id] = deepcopy(model)
            updated["sessions"][key] = session
            updated["events"].extend(deepcopy(events))
            self.data = updated
            try:
                self.save()
            except (OSError, TypeError, ValueError):
                self.data = previous
                raise

    def recent_events(self, user_id: str, limit: int) -> list[dict]:
        with self.lock:
            return deepcopy([event for event in reversed(self.data["events"]) if event["userId"] == user_id][:limit])

    def last_active(self, user_id: str) -> str | None:
        events = self.recent_events(user_id, 1)
        return events[0]["ts"] if events else None


store = FirestoreStore() if FIRESTORE_ENABLED else LocalStore()
