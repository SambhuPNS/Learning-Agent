import json
import os
import threading
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Callable

from .config import DATA_DIR, FIRESTORE_ENABLED, STORE_PATH
from .curriculum import seed_topics

MAX_EVENTS = 20_000


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
        if not data.get("topics"):
            data["topics"] = {topic["id"]: topic for topic in seed_topics(now_iso())}
        for user in data["users"].values():
            user.setdefault("role", "student")
        return data

    def save(self) -> None:
        with self.lock:
            if len(self.data["events"]) > MAX_EVENTS:
                self.data["events"] = self.data["events"][-MAX_EVENTS:]
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            tmp_path = STORE_PATH.with_suffix(".tmp")
            with tmp_path.open("w", encoding="utf-8") as handle:
                json.dump(self.data, handle, indent=2)
            os.replace(tmp_path, STORE_PATH)


class FirestoreStore:
    """Firestore persistence used by Cloud Run; documents are never kept in container storage."""

    def __init__(self) -> None:
        from .firestore_db import db

        self.db = db
        self._seed_topics()

    @staticmethod
    def _email_id(email: str) -> str:
        return sha256(email.encode()).hexdigest()

    def _seed_topics(self) -> None:
        if next(self.db.collection("topics").limit(1).stream(), None):
            return
        batch = self.db.batch()
        for topic in seed_topics(now_iso()):
            batch.set(self.db.collection("topics").document(topic["id"]), topic)
        batch.commit()

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

    def save_user(self, user: dict) -> None:
        self.db.collection("users").document(user["id"]).set(user)

    def all_users(self) -> list[dict]:
        return [snapshot.to_dict() for snapshot in self.db.collection("users").stream()]

    def save_token(self, token_hash: str, user_id: str) -> None:
        self.db.collection("tokens").document(token_hash).set({"userId": user_id})

    def get_token_user_id(self, token_hash: str) -> str | None:
        snapshot = self.db.collection("tokens").document(token_hash).get()
        return snapshot.to_dict()["userId"] if snapshot.exists else None

    def delete_token(self, token_hash: str) -> None:
        self.db.collection("tokens").document(token_hash).delete()

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

    def save_session(self, key: str, session: dict) -> None:
        self.db.collection("sessions").document(key).set(session)

    def get_model(self, user_id: str, factory: Callable[[], dict]) -> dict:
        snapshot = self.db.collection("studentModels").document(user_id).get()
        return snapshot.to_dict() if snapshot.exists else factory()

    def save_model(self, user_id: str, model: dict) -> None:
        self.db.collection("studentModels").document(user_id).set(model)

    def add_event(self, event: dict) -> None:
        self.db.collection("events").document(event["id"]).set(event)

    def recent_events(self, user_id: str, limit: int) -> list[dict]:
        from google.cloud import firestore

        query = (
            self.db.collection("events")
            .where("userId", "==", user_id)
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
        if any(item["email"] == user["email"] for item in self.data["users"].values()):
            return False
        self.data["users"][user["id"]] = user
        self.data["tokens"][token_hash] = user["id"]
        self.save()
        return True

    def get_user(self, user_id: str) -> dict | None:
        return self.data["users"].get(user_id)

    def find_user_by_email(self, email: str) -> dict | None:
        return next((user for user in self.data["users"].values() if user["email"] == email), None)

    def save_user(self, user: dict) -> None:
        self.data["users"][user["id"]] = user
        self.save()

    def all_users(self) -> list[dict]:
        return list(self.data["users"].values())

    def save_token(self, token_hash: str, user_id: str) -> None:
        self.data["tokens"][token_hash] = user_id
        self.save()

    def get_token_user_id(self, token_hash: str) -> str | None:
        return self.data["tokens"].get(token_hash)

    def delete_token(self, token_hash: str) -> None:
        self.data["tokens"].pop(token_hash, None)
        self.save()

    def all_topics(self) -> list[dict]:
        return list(self.data["topics"].values())

    def get_topic(self, topic_id: str) -> dict | None:
        return self.data["topics"].get(topic_id)

    def save_topic(self, topic: dict) -> None:
        self.data["topics"][topic["id"]] = topic
        self.save()

    def delete_topic(self, topic_id: str) -> None:
        del self.data["topics"][topic_id]
        self.save()

    def get_session(self, key: str) -> dict | None:
        return self.data["sessions"].get(key)

    def save_session(self, key: str, session: dict) -> None:
        self.data["sessions"][key] = session
        self.save()

    def get_model(self, user_id: str, factory: Callable[[], dict]) -> dict:
        return self.data["studentModels"].setdefault(user_id, factory())

    def save_model(self, user_id: str, model: dict) -> None:
        self.data["studentModels"][user_id] = model
        self.save()

    def add_event(self, event: dict) -> None:
        self.data["events"].append(event)

    def recent_events(self, user_id: str, limit: int) -> list[dict]:
        return [dict(event) for event in reversed(self.data["events"]) if event["userId"] == user_id][:limit]

    def last_active(self, user_id: str) -> str | None:
        events = self.recent_events(user_id, 1)
        return events[0]["ts"] if events else None


store = FirestoreStore() if FIRESTORE_ENABLED else LocalStore()
