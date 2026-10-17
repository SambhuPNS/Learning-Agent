"""Demo data export and import: only the demo school leaves, without credentials, and comes back exactly."""

import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app import store as store_module
from app.main import app
from app.store import JsonStore

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import demo_data  # noqa: E402
import seed_demo  # noqa: E402

TEACHER = "priya.menon@lakeview.example"


def school_as_teacher(client: TestClient, password: str) -> list[dict]:
    token = client.post("/api/auth/login", json={"email": TEACHER, "password": password}).json()["token"]
    rows = client.get("/api/teacher/students", headers={"Authorization": f"Bearer {token}"}).json()["students"]
    return sorted((row for row in rows if row["email"].endswith("@lakeview.example")), key=lambda row: row["email"])


def without_time(data: dict) -> dict:
    return {key: value for key, value in data.items() if key != "exportedAt"}


def test_export_and_import_recreate_the_demo_school(tmp_path, monkeypatch):
    client = TestClient(app)
    monkeypatch.setattr(store_module.store, "data", JsonStore.migrate({}))
    monkeypatch.setattr(sys, "argv", ["seed_demo.py", "--password", "source-pass-1"])
    seed_demo.main()
    client.post("/api/auth/signup", json={"name": "Real Person", "email": "real.person@gmail.com", "password": "secret123"})
    before = school_as_teacher(client, "source-pass-1")

    snapshot = tmp_path / "demo.json"
    demo_data.main(["export", "--file", str(snapshot)])
    text = snapshot.read_text()
    assert "real.person@gmail.com" not in text and "passwordHash" not in text and '"salt"' not in text
    exported = json.loads(text)
    assert len(exported["people"]) == 15 and sum(p["canSignIn"] for p in exported["people"]) == 3

    monkeypatch.setattr(store_module.store, "data", JsonStore.migrate({}))
    demo_data.main(["import", "--file", str(snapshot), "--password", "friend-pass-2"])
    assert school_as_teacher(client, "friend-pass-2") == before
    assert client.post("/api/auth/login", json={"email": TEACHER, "password": "source-pass-1"}).status_code == 401

    events = len(store_module.store.data["events"])
    demo_data.main(["import", "--file", str(snapshot), "--password", "friend-pass-2"])
    assert len(store_module.store.data["events"]) == events

    again = tmp_path / "again.json"
    demo_data.main(["export", "--file", str(again)])
    assert without_time(json.loads(again.read_text())) == without_time(exported)


def test_an_interrupted_import_finishes_when_run_again(tmp_path, monkeypatch):
    monkeypatch.setattr(store_module.store, "data", JsonStore.migrate({}))
    monkeypatch.setattr(sys, "argv", ["seed_demo.py", "--password", "source-pass-1"])
    seed_demo.main()
    snapshot = tmp_path / "demo.json"
    demo_data.main(["export", "--file", str(snapshot)])
    exported = json.loads(snapshot.read_text())

    monkeypatch.setattr(store_module.store, "data", JsonStore.migrate({}))
    calls = {"count": 0}
    commit = store_module.store.commit_learning_turn

    def fail_after_some(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 7:
            raise ConnectionError("network dropped")
        return commit(*args, **kwargs)

    monkeypatch.setattr(store_module.store, "commit_learning_turn", fail_after_some)
    try:
        demo_data.main(["import", "--file", str(snapshot), "--password", "friend-pass-2"])
    except ConnectionError:
        pass
    monkeypatch.setattr(store_module.store, "commit_learning_turn", commit)
    demo_data.main(["import", "--file", str(snapshot), "--password", "friend-pass-2"])

    again = tmp_path / "again.json"
    demo_data.main(["export", "--file", str(again)])
    assert without_time(json.loads(again.read_text())) == without_time(exported)
