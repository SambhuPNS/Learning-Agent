import json
import os
import threading
from datetime import datetime, timezone
from typing import Any

from .config import DATA_DIR, STORE_PATH
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


store = JsonStore()
