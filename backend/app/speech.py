"""Speech understanding: transcribe the student's reply and extract their intent and answer."""

import hashlib
from collections import OrderedDict

from . import answers, gemini

INTENTS = ["answer", "hint", "explain_again", "continue", "ask", "unclear"]

UNDERSTAND_SCHEMA = {
    "type": "object",
    "properties": {
        "transcript": {"type": "string", "description": "Verbatim transcript of what the student said."},
        "intent": {"type": "string", "enum": INTENTS},
        "answer": {"type": "string", "description": "If intent is answer: the normalised answer. Fractions as a/b digits; for choice questions the exact option text. Otherwise empty."},
        "question": {"type": "string", "description": "If intent is ask: the student's question, cleaned up. Otherwise empty."},
    },
    "required": ["transcript", "intent", "answer", "question"],
}

UNDERSTAND_SYSTEM = """You listen to a school student speaking to their maths tutor app.
Transcribe exactly what they said, then work out what they want:
- answer: they are answering the current question (even casually, e.g. "umm I think it's a half")
- hint: they want a hint or are stuck
- explain_again: they did not understand and want it explained differently
- continue: they are ready to move on (e.g. "okay", "next", "got it")
- ask: they are asking their own question
- unclear: silence, noise, or nothing meaningful
Ignore filler words. Never invent an answer the student did not say."""


async def understand_audio(audio_b64: str, mime_type: str, question: dict | None) -> dict:
    context = "No question is waiting for an answer right now."
    if question:
        options = f" Options: {question['options']}." if question.get("options") else ""
        context = f"Current question: \"{question['prompt']}\".{options}"
    parts = [{"text": context}, {"inlineData": {"mimeType": mime_type, "data": audio_b64}}]
    result = await gemini.generate_json(UNDERSTAND_SYSTEM, parts, UNDERSTAND_SCHEMA, timeout=45)
    return _finalise(result, question)


def interpret_transcript(transcript: str, question: dict | None) -> dict:
    return _finalise(answers.interpret(transcript, question), question)


def _finalise(result: dict, question: dict | None) -> dict:
    intent = result.get("intent") if result.get("intent") in INTENTS else "unclear"
    transcript = str(result.get("transcript", "")).strip()
    answer = str(result.get("answer", "")).strip()
    asked = str(result.get("question", "")).strip()
    if intent == "answer" and not question:
        intent, asked = "ask", transcript
    if intent == "answer":
        answer = answers.normalise_answer(answer or transcript, question)
    if intent == "ask" and not asked:
        asked = transcript
    if not transcript:
        intent = "unclear"
    return {"transcript": transcript, "intent": intent, "answer": answer, "question": asked}


class AudioCache:
    def __init__(self, size: int = 64) -> None:
        self.size = size
        self.items: OrderedDict[str, bytes] = OrderedDict()

    @staticmethod
    def key(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    def get(self, text: str) -> bytes | None:
        key = self.key(text)
        if key in self.items:
            self.items.move_to_end(key)
            return self.items[key]
        return None

    def put(self, text: str, audio: bytes) -> None:
        self.items[self.key(text)] = audio
        if len(self.items) > self.size:
            self.items.popitem(last=False)


audio_cache = AudioCache()
