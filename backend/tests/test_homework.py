"""Homework: drafting, one graded attempt per student, hidden answer keys, results and the student model."""

import asyncio

from fastapi.testclient import TestClient

from app import homework, student_model
from app.main import app
from app.store import store

client = TestClient(app)
LESSON = "comparing-fractions"


def account(email: str, role: str = "student") -> dict:
    res = client.post("/api/auth/signup", json={"name": f"{email.split('@')[0].title()}", "email": email,
                                                "password": "secret123", "role": role})
    if res.status_code != 200:
        res = client.post("/api/auth/login", json={"email": email, "password": "secret123"})
    return {"Authorization": f"Bearer {res.json()['token']}"}


def question(prompt="Which is bigger?", options=("1/2", "1/3"), answer="1/2", **extra):
    return {"prompt": prompt, "format": "choice", "options": list(options), "expectedAnswer": answer,
            "acceptableAnswers": [], "explanation": "Halves are bigger than thirds.", "misconception": "bigger denominator = bigger", **extra}


def create(teacher, questions=None, due="2099-01-01T00:00:00Z", published=True, title="Fractions practice"):
    res = client.post("/api/teacher/homework", headers=teacher, json={
        "title": title, "instructions": "Do your best", "lessonId": LESSON, "dueAt": due, "published": published,
        "questions": questions or [question(), question("Is 2/4 equal to 1/2?", ("True", "False"), "True",
                                                         misconception="")]})
    assert res.status_code == 200, res.text
    return res.json()


def test_teacher_drafts_edits_and_publishes():
    teacher = account("hw.teacher@example.com", "teacher")
    drafted = client.post("/api/teacher/homework/draft", headers=teacher, json={"lessonId": LESSON, "count": 4}).json()
    assert drafted["source"] == "outline" and drafted["questions"]
    first = drafted["questions"][0]
    assert first["format"] == "choice" and first["expectedAnswer"] in first["options"]

    created = create(teacher, drafted["questions"])
    assert created["published"] and len(created["questions"]) == len(drafted["questions"])
    listing = client.get("/api/teacher/homework", headers=teacher).json()["homework"]
    assert any(item["id"] == created["id"] and item["submitted"] == 0 for item in listing)


def test_bad_questions_are_rejected_with_a_clear_message():
    teacher = account("hw.teacher@example.com", "teacher")
    bad = question(answer="not an option")
    res = client.post("/api/teacher/homework", headers=teacher, json={
        "title": "x", "lessonId": LESSON, "dueAt": "2099-01-01T00:00:00Z", "questions": [bad]})
    assert res.status_code == 422 and "Question 1" in res.json()["detail"]
    res = client.post("/api/teacher/homework", headers=teacher, json={
        "title": "x", "lessonId": LESSON, "dueAt": "tomorrow", "questions": [question()]})
    assert res.status_code == 422


def test_student_flow_hides_answers_grades_once_and_updates_the_model():
    teacher = account("hw.teacher@example.com", "teacher")
    student = account("hw.student@example.com")
    created = create(teacher)
    hw_id, q1, q2 = created["id"], created["questions"][0], created["questions"][1]

    todo = client.get("/api/homework", headers=student).json()["homework"]
    assert any(item["id"] == hw_id and item["status"] == "todo" for item in todo)

    started = client.post(f"/api/homework/{hw_id}/start", headers=student).json()
    assert started["submitted"] is False
    for public in started["homework"]["questions"]:
        assert "expectedAnswer" not in public and "acceptableAnswers" not in public and "explanation" not in public

    assert client.put(f"/api/homework/{hw_id}/answer", headers=student, json={"questionId": q1["id"], "answer": "1/3"}).status_code == 200
    assert client.put(f"/api/homework/{hw_id}/answer", headers=student, json={"questionId": q1["id"], "answer": "banana"}).status_code == 422
    assert client.post(f"/api/homework/{hw_id}/start", headers=student).json()["answers"] == {q1["id"]: "1/3"}
    assert client.get(f"/api/homework/{hw_id}/result", headers=student).status_code == 404
    assert client.post(f"/api/homework/{hw_id}/submit", headers=student, json={"answers": {}}).status_code == 422

    before = student_model.get_model(store.find_user_by_email("hw.student@example.com"))["concepts"].get(LESSON, {}).get("attempts", 0)
    done = client.post(f"/api/homework/{hw_id}/submit", headers=student, json={"answers": {q1["id"]: "1/2", q2["id"]: "True"}})
    assert done.status_code == 200, done.text
    result = done.json()
    assert result["score"] == 2 and result["total"] == 2 and result["late"] is False
    assert result["review"][0]["correctAnswer"] == "1/2" and result["review"][0]["explanation"]

    model = student_model.get_model(store.find_user_by_email("hw.student@example.com"))
    assert model["concepts"][LESSON]["attempts"] == before + 2

    assert client.post(f"/api/homework/{hw_id}/submit", headers=student, json={"answers": {q1["id"]: "1/3", q2["id"]: "False"}}).status_code == 409
    assert client.put(f"/api/homework/{hw_id}/answer", headers=student, json={"questionId": q1["id"], "answer": "1/3"}).status_code == 409
    assert client.get(f"/api/homework/{hw_id}/result", headers=student).json()["score"] == 2
    assert client.post(f"/api/homework/{hw_id}/start", headers=student).json()["submitted"] is True


def test_wrong_answers_feed_misconceptions_and_teacher_results():
    teacher = account("hw.teacher@example.com", "teacher")
    student = account("hw.weak@example.com")
    created = create(teacher, title="Results check")
    hw_id, q1, q2 = created["id"], created["questions"][0], created["questions"][1]
    res = client.post(f"/api/homework/{hw_id}/submit", headers=student, json={"answers": {q1["id"]: "1/3", q2["id"]: "True"}})
    assert res.json()["score"] == 1
    assert "bigger denominator = bigger" in student_model.get_model(store.find_user_by_email("hw.weak@example.com"))["misconceptions"]

    results = client.get(f"/api/teacher/homework/{hw_id}/results", headers=teacher).json()
    row = next(item for item in results["students"] if item["email"] == "hw.weak@example.com")
    assert row["status"] == "submitted" and row["score"] == 1 and row["total"] == 2
    assert results["questions"][0]["percentCorrect"] == 0 and results["questions"][1]["percentCorrect"] == 100
    assert results["misconceptions"][0]["label"] == "bigger denominator = bigger"


def test_late_work_is_accepted_and_flagged():
    teacher = account("hw.teacher@example.com", "teacher")
    student = account("hw.late@example.com")
    created = create(teacher, due="2020-01-01T00:00:00Z", title="Overdue")
    listed = next(i for i in client.get("/api/homework", headers=student).json()["homework"] if i["id"] == created["id"])
    assert listed["overdue"] is True
    q1, q2 = created["questions"]
    res = client.post(f"/api/homework/{created['id']}/submit", headers=student, json={"answers": {q1["id"]: "1/2", q2["id"]: "True"}}).json()
    assert res["late"] is True
    row = next(i for i in client.get(f"/api/teacher/homework/{created['id']}/results", headers=teacher).json()["students"]
               if i["email"] == "hw.late@example.com")
    assert row["status"] == "late"


def test_unpublished_homework_is_hidden_and_roles_are_enforced():
    teacher = account("hw.teacher@example.com", "teacher")
    other_teacher = account("hw.other@example.com", "teacher")
    student = account("hw.student@example.com")
    hidden = create(teacher, published=False, title="Hidden")
    assert all(i["id"] != hidden["id"] for i in client.get("/api/homework", headers=student).json()["homework"])
    assert client.post(f"/api/homework/{hidden['id']}/start", headers=student).status_code == 404
    assert client.get("/api/teacher/homework", headers=student).status_code == 403
    assert client.get("/api/homework", headers=teacher).status_code == 403
    assert client.get(f"/api/teacher/homework/{hidden['id']}", headers=other_teacher).status_code == 403
    assert all(i["id"] != hidden["id"] for i in client.get("/api/teacher/homework", headers=other_teacher).json()["homework"])


def test_questions_lock_after_students_start_and_delete_is_blocked():
    teacher = account("hw.teacher@example.com", "teacher")
    student = account("hw.lock@example.com")
    created = create(teacher, title="Lock me")
    hw_id = created["id"]
    assert client.get(f"/api/teacher/homework/{hw_id}", headers=teacher).json()["locked"] is False
    client.put(f"/api/homework/{hw_id}/answer", headers=student, json={"questionId": created["questions"][0]["id"], "answer": "1/2"})

    detail = client.get(f"/api/teacher/homework/{hw_id}", headers=teacher).json()
    assert detail["locked"] is True
    body = {"title": "Renamed", "instructions": "", "lessonId": LESSON, "dueAt": "2099-06-01T00:00:00Z", "published": True,
            "questions": detail["questions"]}
    assert client.put(f"/api/teacher/homework/{hw_id}", headers=teacher, json=body).status_code == 200
    body["questions"] = [{**detail["questions"][0], "prompt": "Changed?"}] + detail["questions"][1:]
    assert client.put(f"/api/teacher/homework/{hw_id}", headers=teacher, json=body).status_code == 409
    assert client.delete(f"/api/teacher/homework/{hw_id}", headers=teacher).status_code == 409

    fresh = create(teacher, title="Delete me")
    assert client.delete(f"/api/teacher/homework/{fresh['id']}", headers=teacher).status_code == 200


def test_clean_questions_normalises_text_and_dedupes_options():
    cleaned = homework.clean_questions([
        {"prompt": "Name it", "format": "text", "expectedAnswer": "Quarter", "acceptableAnswers": ["a quarter"], "options": ["x"]},
        {"prompt": "Pick", "format": "choice", "options": ["A", "a", "B"], "expectedAnswer": "b"},
        {"prompt": "", "format": "text", "expectedAnswer": "x"},
    ], strict=False)
    assert len(cleaned) == 2
    assert cleaned[0]["options"] == [] and cleaned[0]["acceptableAnswers"] == ["Quarter", "a quarter"]
    assert cleaned[1]["options"] == ["A", "B"] and cleaned[1]["expectedAnswer"] == "B"
    assert asyncio.run(homework.draft_questions(LESSON, 3))["questions"]


# ---------- Tutor-style examples and option order ----------

def _gemini_example(monkeypatch, blocks=None, leaks=False, calls=None):
    async def fake_generate(system, parts, schema, **kwargs):
        if calls is not None:
            calls.append(parts[0]["text"])
        return {"title": "Sharing a pizza", "blocks": blocks or [
            {"type": "text", "text": "Imagine 3 friends sharing a pizza cut into 8 equal slices."},
            {"type": "callout", "label": "Remember", "text": "Equal parts matter."}]}

    async def fake_leak(step, question):
        return leaks

    monkeypatch.setattr(homework, "gemini_enabled", lambda: True)
    monkeypatch.setattr(homework.gemini, "generate_json", fake_generate)
    monkeypatch.setattr(homework.tutor, "_reveals_answer", fake_leak)
    homework._examples_done.clear()


def _ask_example(student, hw_id, question_id):
    return client.post(f"/api/homework/{hw_id}/example", headers=student, json={"questionId": question_id})


def test_example_is_built_from_the_student_model_without_the_answer_key(monkeypatch):
    teacher = account("hw.teacher@example.com", "teacher")
    student = account("hw.example@example.com")
    client.put("/api/profile", headers=student, json={**{"grade": 6, "mathConfidence": 3, "fractionsComfort": "some",
               "learningStyle": "real-world", "pace": "steady", "voiceEnabled": False}, "interests": ["football"]})
    created = create(teacher, [question(explanation="SECRET-EXPLANATION", misconception="SECRET-MISTAKE")] * 2, title="Example")
    prompts = []
    _gemini_example(monkeypatch, calls=prompts)

    res = _ask_example(student, created["id"], created["questions"][0]["id"])
    assert res.status_code == 200, res.text
    shown = res.json()["example"]
    assert shown["title"] == "Sharing a pizza" and shown["strategy"] == "real-world"
    assert [block["type"] for block in shown["content"]] == ["text", "callout"]
    assert "football" in prompts[0] and "real-world" in prompts[0] and "Which is bigger?" in prompts[0]
    assert "SECRET-EXPLANATION" not in prompts[0] and "SECRET-MISTAKE" not in prompts[0] and "expectedAnswer" not in prompts[0]

    again = _ask_example(student, created["id"], created["questions"][0]["id"]).json()["example"]
    assert again == shown and len(prompts) == 1


def test_example_is_withheld_when_it_could_give_the_answer_away(monkeypatch):
    teacher = account("hw.teacher@example.com", "teacher")
    student = account("hw.leak@example.com")
    created = create(teacher, title="Leaky")
    _gemini_example(monkeypatch, leaks=True)
    assert _ask_example(student, created["id"], created["questions"][0]["id"]).json() == {"example": None}


def test_example_is_skipped_without_gemini_or_on_bad_output(monkeypatch):
    teacher = account("hw.teacher@example.com", "teacher")
    student = account("hw.offline@example.com")
    created = create(teacher, title="Offline")
    q_id = created["questions"][0]["id"]
    homework._examples_done.clear()
    assert _ask_example(student, created["id"], q_id).json() == {"example": None}

    _gemini_example(monkeypatch, blocks=[{"type": "mystery"}])
    assert _ask_example(student, created["id"], q_id).json() == {"example": None}


def test_example_access_rules(monkeypatch):
    teacher = account("hw.teacher@example.com", "teacher")
    student = account("hw.rules@example.com")
    created = create(teacher, title="Rules")
    hidden = create(teacher, published=False, title="Hidden rules")
    q1, q2 = created["questions"]
    _gemini_example(monkeypatch)
    assert _ask_example(student, created["id"], "nope1234").status_code == 404
    assert _ask_example(student, hidden["id"], hidden["questions"][0]["id"]).status_code == 404
    assert client.post(f"/api/homework/{created['id']}/example", json={"questionId": q1["id"]}).status_code == 401
    assert client.post(f"/api/homework/{created['id']}/example", headers=teacher, json={"questionId": q1["id"]}).status_code == 403
    client.post(f"/api/homework/{created['id']}/submit", headers=student, json={"answers": {q1["id"]: "1/2", q2["id"]: "True"}})
    assert _ask_example(student, created["id"], q1["id"]).status_code == 409


def test_each_student_sees_their_own_stable_option_order():
    teacher = account("hw.teacher@example.com", "teacher")
    options = ("12", "15", "18", "21")
    created = create(teacher, [question("Pick one", options, "12")], title="Shuffle")
    orders = set()
    for number in range(8):
        student = account(f"hw.shuffle{number}@example.com")
        first = client.post(f"/api/homework/{created['id']}/start", headers=student).json()["homework"]["questions"][0]["options"]
        second = client.post(f"/api/homework/{created['id']}/start", headers=student).json()["homework"]["questions"][0]["options"]
        assert first == second and sorted(first) == sorted(options)
        orders.add(tuple(first))
        res = client.post(f"/api/homework/{created['id']}/submit", headers=student, json={"answers": {created["questions"][0]["id"]: "12"}})
        assert res.json()["score"] == 1
    assert len(orders) > 1
    assert homework._public_question(question() | {"id": "abc12345", "options": ["True", "False"]}, "u1")["options"] == ["True", "False"]
