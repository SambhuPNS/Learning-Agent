"""The demo seed script: its sign-ins work, the synthetic class fills the dashboards, and running it again is harmless."""

import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app import store as store_module
from app.main import app
from app.store import JsonStore

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import seed_demo  # noqa: E402


def test_seed_demo_fills_dashboards_and_is_idempotent(monkeypatch):
    monkeypatch.setattr(store_module.store, "data", JsonStore.migrate({}))
    monkeypatch.setattr(sys, "argv", ["seed_demo.py", "--password", "demo-pass-123"])
    seed_demo.main()
    seed_demo.main()

    client = TestClient(app)

    def login(email: str) -> dict:
        token = client.post("/api/auth/login", json={"email": email, "password": "demo-pass-123"}).json()["token"]
        return {"Authorization": f"Bearer {token}"}

    overview = client.get("/api/teacher/overview", headers=login("priya.menon@lakeview.example")).json()
    assert overview["studentCount"] == 14 and overview["activeStudents"] == 13
    assert overview["needSupport"] >= 1 and overview["misconceptions"] and overview["lessonsCompleted"] > 10
    insights = client.get("/api/me/insights", headers=login("riya.sharma@lakeview.example")).json()
    assert insights["bestStrategy"] == "real-world" and insights["selfReportedStrategy"] == "visual"
    assert client.get("/api/me", headers=login("kiran.rao@lakeview.example")).json()["profile"] is None
