"""Backend tests in offline (mock) mode: accounts, roles, teacher topics, the event log and the student model."""

from app import auth, store as store_module  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app import blocks, curriculum, student_model, tutor  # noqa: E402
from app.answers import interpret, matches  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)
PROFILE = {"grade": 7, "mathConfidence": 3, "fractionsComfort": "some", "learningStyle": "visual",
           "pace": "steady", "interests": ["football"], "voiceEnabled": True}


def signup(email: str, role: str = "student") -> dict:
    res = client.post("/api/auth/signup", json={"name": f"{role.title()} Test", "email": email, "password": "secret123", "role": role})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}


def turn(headers, lesson_id, action, text=None, meta=None):
    res = client.post("/api/tutor/turn", headers=headers, json={"lessonId": lesson_id, "action": action, "text": text, "meta": meta})
    assert res.status_code == 200, res.text
    return res.json()


def test_answer_extraction():
    q = {"options": ["1/4", "1/6"], "acceptableAnswers": ["1/4"]}
    assert matches("umm I think it's one quarter", q)
    assert matches("the first one", q)
    assert not matches("one sixth", q)
    assert matches("3 over 8", {"options": [], "acceptableAnswers": ["3/8"]})
    assert interpret("can I get a hint", q)["intent"] == "hint"
    assert interpret("okay next", None)["intent"] == "continue"


def test_step_blocks_keep_order_and_drop_what_cannot_be_drawn():
    flow = {"type": "flow", "caption": "Steps", "items": [{"label": "First", "detail": "Do this"}]}
    raw = {"kind": "teach", "speech": "Let's look.", "blocks": [
        {"type": "text", "text": "Begin"},
        flow,
        {"type": "bar-chart", "caption": "Votes", "yLabel": "Votes",
         "data": [{"label": "Apples", "value": 4}, {"label": "Pears", "value": "2.5"}, {"label": "Bad", "value": "lots"}]},
        {"type": "callout", "caption": "", "text": "Longer bars mean more votes."},
        {"type": "table", "caption": "Halves", "columns": ["Fraction", "Equal to"], "rows": [["1/2", "2/4", "extra"], ["3/6"]]},
        {"type": "line-graph", "caption": "Growth", "points": [{"x": 2, "y": 4}, {"x": 1, "y": 2}]},
        {"type": "bar-chart", "caption": "Empty", "data": []},
        {"type": "pie-chart", "caption": "Unknown component"},
        flow,
        {"type": "text", "text": "Then continue"},
    ]}
    step, _, _ = tutor._clean_step(raw)
    assert [block["type"] for block in step["content"]] == ["text", "visual", "visual", "callout", "visual", "visual", "text"]
    flow_step, bars, callout, table, graph = step["content"][1:6]
    assert flow_step["visual"]["items"] == [{"label": "First", "detail": "Do this"}]
    assert bars["visual"]["data"] == [{"label": "Apples", "value": 4.0}, {"label": "Pears", "value": 2.5}]
    assert callout == {"type": "callout", "label": "Remember", "text": "Longer bars mean more votes."}
    assert table["visual"]["rows"] == [["1/2", "2/4"], ["3/6", ""]]
    assert [point["x"] for point in graph["visual"]["points"]] == [1, 2]
    assert step["paragraphs"] == ["Begin", "Longer bars mean more votes.", "Then continue"]
    assert tutor._clean_step({**raw, "kind": "visual"})[0]["kind"] == "teach"
    assert tutor._clean_step({"kind": "teach", "blocks": []})[0]["content"] == [{"type": "text", "text": "Let's keep going."}]


def test_scripted_lesson_blocks_are_all_drawable():
    rich = [item for lesson in curriculum.LESSONS.values() for item in lesson["script"] if item.get("blocks")]
    assert rich
    for item in rich:
        assert len(blocks.to_content(item["blocks"])) == len(item["blocks"]), item["title"]
    types = {block["type"] for item in rich for block in item["blocks"]}
    assert {"text", "callout", "table", "bar-chart", "line-graph", "flow"} <= types


def test_block_schema_has_no_nested_limits():
    # Vertex AI answered every lesson turn with 400 INVALID_ARGUMENT when block fields carried these limits.
    def keywords(node):
        if isinstance(node, dict):
            return set(node) | set().union(*map(keywords, node.values()))
        return set().union(*map(keywords, node)) if isinstance(node, list) else set()
    assert not keywords(blocks.BLOCK_SCHEMA) & {"minItems", "maxItems", "minimum", "maximum"}


def test_bkt_and_strategy_policy():
    model = student_model._new_model()
    before = student_model.concept(model, "x", 0.3)["mastery"]
    up = student_model.record_answer(model, "x", 0.3, correct=True, used_hint=False, response_ms=5000,
                                     strategy="visual", input_mode="typed", misconception=None)["mastery"]
    down = student_model.record_answer(model, "x", 0.3, correct=False, used_hint=False, response_ms=30000,
                                       strategy="visual", input_mode="voice", misconception="bigger denominator means bigger")["mastery"]
    assert up > before and down < up
    assert model["misconceptions"]["bigger denominator means bigger"]["count"] == 1
    assert model["behaviour"]["slowAnswers"] == 1 and model["behaviour"]["voiceAnswers"] == 1

    fresh = student_model._new_model()
    assert student_model.choose_strategy(fresh, "visual") == "visual"
    for _ in range(3):
        fresh["strategies"]["visual"]["fail"] += 1
    assert student_model.choose_strategy(fresh, "visual") != "visual"
    for _ in range(4):
        fresh["strategies"]["real-world"]["success"] += 1
    assert student_model.best_strategy(fresh, "visual") == "real-world"


def test_student_flow_logs_events_and_updates_model():
    headers = signup("maya@example.com")
    assert client.post("/api/auth/login", json={"email": "maya@example.com", "password": "wrong-pass"}).status_code == 401
    assert client.post("/api/tutor/turn", headers=headers, json={"lessonId": "comparing-fractions", "action": "start"}).status_code == 409
    assert client.put("/api/profile", headers=headers, json=PROFILE).status_code == 200

    subjects = client.get("/api/curriculum", headers=headers).json()["subjects"]
    assert subjects[0]["topics"][0]["id"] == "fractions"

    lesson = "comparing-fractions"
    first = turn(headers, lesson, "start")["history"][-1]["step"]
    assert first["kind"] == "teach" and first["strategy"] == "visual"
    second = turn(headers, lesson, "continue", meta={"responseMs": 9000})["history"][-1]["step"]
    assert {"bar-chart", "fraction-circles"} <= {block["visual"]["type"] for block in second["content"] if block["type"] == "visual"}
    step = turn(headers, lesson, "continue")["history"][-1]["step"]
    assert step["kind"] == "question" and "expectedAnswer" not in step["question"]

    wrong = turn(headers, lesson, "answer", "1/6", meta={"responseMs": 26000, "inputMode": "voice"})
    assert wrong["history"][-1]["step"]["feedback"]["correct"] is False
    assert wrong["learner"]["lastResponseSec"] == 26.0
    turn(headers, lesson, "hint", meta={"responseMs": 4000})
    right = turn(headers, lesson, "answer", "one quarter", meta={"responseMs": 6000, "inputMode": "typed"})
    assert right["state"]["correct"] == 1

    insights = client.get("/api/me/insights", headers=headers).json()
    assert insights["behaviour"]["answers"] == 2 and insights["behaviour"]["slowAnswers"] == 1
    assert insights["behaviour"]["voiceShare"] == 50
    assert insights["concepts"][0]["lessonId"] == lesson
    visual = next(s for s in insights["strategies"] if s["strategy"] == "visual")
    assert visual["success"] == 1 and visual["fail"] == 1

    events = [e for e in store_module.store.data["events"] if e["type"] == "answer"]
    assert [e["responseMs"] for e in events] == [26000, 6000]
    assert events[1]["usedHint"] is True and events[0]["slow"] is True


def test_teacher_topics_and_insights():
    teacher = signup("teacher@example.com", role="teacher")
    student = signup("leo@example.com")
    client.put("/api/profile", headers=student, json={**PROFILE, "learningStyle": "real-world"})

    assert client.get("/api/teacher/students", headers=student).status_code == 403
    assert client.put("/api/profile", headers=teacher, json=PROFILE).status_code == 403
    assert client.post("/api/tutor/turn", headers=teacher, json={"lessonId": "comparing-fractions", "action": "start"}).status_code == 403

    draft = client.post("/api/teacher/topics/draft", headers=teacher, json={
        "subject": "Science", "title": "Photosynthesis", "gradeLevel": 7,
        "description": "Plants make their own food using sunlight. Chlorophyll in leaves captures light energy. "
                       "Plants take in carbon dioxide and water and release oxygen."}).json()
    assert draft["source"] == "outline" and draft["lessons"]

    topic = client.post("/api/teacher/topics", headers=teacher, json={
        "subject": "Science", "title": "Photosynthesis", "gradeLevel": 7, "description": "How plants make food.", "published": True,
        "lessons": [{"title": "How plants make food", "summary": "Inputs and outputs",
                     "objectives": ["Name the inputs and outputs of photosynthesis"],
                     "keyIdeas": ["Plants use sunlight, water and carbon dioxide to make glucose.", "Photosynthesis releases oxygen."],
                     "misconceptions": ["Plants get their food from the soil.", "Plants take in oxygen to make food."]}],
    }).json()
    lesson_id = topic["lessons"][0]["id"]
    topic_ids = [t["id"] for s in client.get("/api/curriculum", headers=student).json()["subjects"] for t in s["topics"]]
    assert topic["id"] in topic_ids

    step = turn(student, lesson_id, "start")["history"][-1]["step"]
    assert step["kind"] == "teach"
    question = turn(student, lesson_id, "continue")["history"][-1]["step"]["question"]
    assert question["options"] == ["True", "False"]
    assert turn(student, lesson_id, "answer", "True", meta={"responseMs": 7000, "inputMode": "choice"})["state"]["correct"] == 1

    overview = client.get("/api/teacher/overview", headers=teacher).json()
    assert overview["studentCount"] == 2 and overview["activeStudents"] == 2
    assert any(c["lessonId"] == lesson_id for c in overview["concepts"])
    rows = client.get("/api/teacher/students", headers=teacher).json()["students"]
    leo = next(r for r in rows if r["email"] == "leo@example.com")
    detail = client.get(f"/api/teacher/students/{leo['id']}", headers=teacher).json()
    assert detail["insights"]["behaviour"]["answers"] == 1
    assert detail["events"][0]["lessonTitle"] == "How plants make food"
    assert "lessonTitle" not in store_module.store.data["events"][-1]

    updated = {**{k: topic[k] for k in ("subject", "title", "gradeLevel", "description", "lessons")}, "published": False}
    assert client.put(f"/api/teacher/topics/{topic['id']}", headers=teacher, json=updated).status_code == 200
    topic_ids = [t["id"] for s in client.get("/api/curriculum", headers=student).json()["subjects"] for t in s["topics"]]
    assert topic["id"] not in topic_ids
    other = signup("other-teacher@example.com", role="teacher")
    assert client.delete(f"/api/teacher/topics/{topic['id']}", headers=other).status_code == 403
    assert client.delete(f"/api/teacher/topics/{topic['id']}", headers=teacher).status_code == 200


def test_teacher_invite_code():
    auth.TEACHER_INVITE_CODE = "school-42"
    try:
        body = {"name": "T", "email": "code@example.com", "password": "secret123", "role": "teacher"}
        assert client.post("/api/auth/signup", json={**body, "inviteCode": "nope"}).status_code == 403
        assert client.post("/api/auth/signup", json={**body, "inviteCode": "school-42"}).status_code == 200
    finally:
        auth.TEACHER_INVITE_CODE = ""


def test_chat_shows_only_what_the_student_said():
    headers = signup("cara@example.com")
    client.put("/api/profile", headers=headers, json=PROFILE)
    turn(headers, "fraction-basics", "start")
    history = turn(headers, "fraction-basics", "continue")["history"]
    assert [item["role"] for item in history] == ["tutor", "tutor"]
    history = turn(headers, "fraction-basics", "continue", "Yeah, thanks.", meta={"inputMode": "voice"})["history"]
    assert history[-2] == {"role": "student", "action": "continue", "text": "Yeah, thanks."}
