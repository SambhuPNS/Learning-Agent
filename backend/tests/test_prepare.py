"""Preparing the next step while the student reads: Continue uses it only if nothing changed in between."""

import asyncio

import pytest

from app import gemini, student_model, topics, tutor
from app import store as store_module
from app.store import LocalStore

LESSON = "adding-fractions"
QUESTION = {"prompt": "What is 2/7 + 3/7?", "format": "text", "options": [], "expectedAnswer": "5/7",
            "acceptableAnswers": ["5/7"], "hint": "Add the tops."}


def step(kind: str, text: str, question: dict | None = None) -> dict:
    return {"kind": kind, "title": text, "strategy": "visual", "blocks": [{"type": "text", "text": text}],
            "speech": text, "feedback": None, "question": question}


class SlowFakeGemini:
    def __init__(self) -> None:
        self.steps: list[dict] = []
        self.calls = 0
        self.delay = 0.0

    async def __call__(self, system, parts, schema, timeout=60, thinking="low", **_options):
        self.calls += 1
        reply = self.steps.pop(0)
        await asyncio.sleep(self.delay)
        return reply


@pytest.fixture
def lesson(tmp_path, monkeypatch):
    monkeypatch.setattr(store_module, "STORE_PATH", tmp_path / "store.json")
    store = LocalStore()
    for module in (tutor, topics, student_model):
        monkeypatch.setattr(module, "store", store)
    fake = SlowFakeGemini()
    monkeypatch.setattr(tutor, "gemini_enabled", lambda: True)
    monkeypatch.setattr(gemini, "generate_json", fake)
    monkeypatch.setattr(tutor, "_prepared", {})
    user = {"id": "reader", "name": "Ana Lee", "email": "ana@example.com", "role": "student", "progress": {},
            "profile": {"grade": 7, "mathConfidence": 3, "fractionsComfort": "some", "learningStyle": "visual",
                        "pace": "steady", "interests": []}}
    store.create_user(user, "token")
    fake.steps.append(step("teach", "Same bottoms add easily."))
    asyncio.run(tutor.take_turn(user, LESSON, "start", None))
    return fake, user


def latest_text(response: dict) -> str:
    return response["history"][-1]["step"]["title"]


def test_continue_shows_the_prepared_step_without_asking_gemini_again(lesson):
    fake, user = lesson
    fake.steps.append(step("teach", "Prepared idea"))
    assert asyncio.run(tutor.prepare_continue(user, LESSON))["title"] == "Prepared idea"
    calls = fake.calls
    response = asyncio.run(tutor.take_turn(user, LESSON, "continue", None))
    assert latest_text(response) == "Prepared idea" and fake.calls == calls


def test_a_prepared_step_is_dropped_once_the_student_does_something_else(lesson):
    fake, user = lesson
    fake.steps.append(step("teach", "Prepared idea"))
    asyncio.run(tutor.prepare_continue(user, LESSON))
    fake.steps.append(step("teach", "Answer to your question"))
    asyncio.run(tutor.take_turn(user, LESSON, "ask", "Why keep the bottom?"))
    fake.steps.append(step("teach", "Fresh idea"))
    assert latest_text(asyncio.run(tutor.take_turn(user, LESSON, "continue", None))) == "Fresh idea"


def test_continue_waits_for_a_step_that_is_still_being_prepared(lesson):
    fake, user = lesson
    fake.delay = 0.2
    fake.steps.append(step("teach", "Prepared idea"))

    async def press_continue_early():
        preparing = asyncio.create_task(tutor.prepare_continue(user, LESSON))
        await asyncio.sleep(0.05)
        response = await tutor.take_turn(user, LESSON, "continue", None)
        await preparing
        return response

    calls = fake.calls
    assert latest_text(asyncio.run(press_continue_early())) == "Prepared idea"
    assert fake.calls == calls + 1


def test_nothing_is_prepared_while_a_question_waits_for_an_answer(lesson):
    fake, user = lesson
    fake.steps.append(step("question", "Try this one", QUESTION))
    asyncio.run(tutor.take_turn(user, LESSON, "continue", None))
    calls = fake.calls
    assert asyncio.run(tutor.prepare_continue(user, LESSON)) is None and fake.calls == calls


def test_two_requests_for_the_same_speech_share_one_synthesis(monkeypatch):
    from app import speech

    calls = []

    async def synthesize(text):
        calls.append(text)
        await asyncio.sleep(0.05)
        return b"RIFF" + text.encode()

    monkeypatch.setattr(gemini, "synthesize", synthesize)
    monkeypatch.setattr(speech, "audio_cache", speech.AudioCache())

    async def both():
        return await asyncio.gather(speech.cached_audio("Hello"), speech.cached_audio("Hello"))

    first, second = asyncio.run(both())
    assert first == second == b"RIFFHello" and calls == ["Hello"]
    assert asyncio.run(speech.cached_audio("Hello")) == first and calls == ["Hello"]
