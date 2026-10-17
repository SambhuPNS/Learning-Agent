"""Starter topics: seeded once, added to existing stores when missing, and listed maths-first."""

from fastapi.testclient import TestClient

from app import curriculum, topics
from app.main import app
from app.store import JsonStore


def test_every_starter_lesson_has_a_unique_id_and_an_offline_script():
    seeded = curriculum.seed_topics("2026-01-01T00:00:00+00:00")
    lesson_ids = [lesson["id"] for topic in seeded for lesson in topic["lessons"]]
    assert len(lesson_ids) == len(set(lesson_ids))
    assert [topic["subject"] for topic in seeded] == ["Mathematics", "Mathematics", "Science", "Science", "English"]
    for topic in seeded:
        assert topic["published"] and topic["createdBy"] == "system"
        for lesson in topic["lessons"]:
            assert lesson["keyIdeas"] and lesson["title"]
            script = topics.fallback_script(lesson)
            assert script[0]["kind"] == "teach" and script[-1]["kind"] == "summary"


def test_missing_starter_topics_are_added_without_touching_existing_ones():
    edited = {**curriculum.seed_topics("2026-01-01T00:00:00+00:00")[0], "description": "Edited by a teacher"}
    data = JsonStore.migrate({"topics": {"fractions": edited}})
    assert data["topics"]["fractions"]["description"] == "Edited by a teacher"
    assert {"decimals-percentages", "photosynthesis", "water-cycle", "parts-of-speech"} <= set(data["topics"])


def test_curriculum_lists_starter_topics_maths_first():
    client = TestClient(app)
    token = client.post("/api/auth/signup", json={"name": "Order Test", "email": "order@example.com", "password": "secret123"}).json()["token"]
    subjects = client.get("/api/curriculum", headers={"Authorization": f"Bearer {token}"}).json()["subjects"]
    assert [s["title"] for s in subjects][:3] == ["Mathematics", "Science", "English"]
    assert [t["id"] for t in subjects[0]["topics"]][:2] == ["fractions", "decimals-percentages"]
