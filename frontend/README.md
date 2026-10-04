# brightpath Student Frontend

React + TypeScript client for the personalised AI tutor. It talks only to the Python backend in `../backend` (proxied at `/api`).

## Run locally

Start the backend first (from `../backend`):

```bash
cp .env.example .env              # paste GEMINI_API_KEY to enable Gemini; leave empty for the scripted mock tutor
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Then the frontend:

```bash
npm install
npm run dev
```

Open `http://localhost:5173`.

## Flow

- **Student:** sign up → learning-profile onboarding → pick any published topic → lesson. Each lesson teaches first, then asks questions, gives feedback, hints and alternative explanations, and finishes after three correct checks.
- **Teacher:** sign up as a teacher → create a topic from a description or uploaded notes (PDF/TXT/MD) → Gemini drafts lessons (key ideas, objectives, misconceptions) → edit and publish. The Overview and Students tabs show class and per-student insights.

## Personalisation

Every turn is logged with a timestamp, response time and input mode. The backend keeps a student model per learner: Bayesian Knowledge Tracing mastery per lesson, misconceptions tagged by Gemini, behaviour (answer time, hints, re-explanations, voice use) and which teaching strategy (visual, step-by-step, real-life, worked example) is followed by correct answers. Before each explanation the backend picks a strategy from that evidence and sends the student model to Gemini with the teacher's topic data.

## Tutor step contract

`POST /api/tutor/turn` with `{ lessonId, action, text }` (`start | restart | continue | answer | hint | explain_again | ask`) returns the full conversation history. Each tutor step is structured data rendered by trusted components (no generated code):

```json
{
  "kind": "teach | question | feedback | summary",
  "title": "When the tops match",
  "paragraphs": ["..."],
  "speech": "Spoken version of the step",
  "visual": { "type": "fraction-circles | fraction-bars | number-line", "fractions": [{ "numerator": 1, "denominator": 2, "label": "1/2" }], "caption": "..." },
  "feedback": { "correct": true, "message": "..." },
  "question": { "prompt": "...", "format": "choice | text", "options": ["1/4", "1/6"] }
}
```

Correct answers stay on the server.

## Voice

- With a Gemini key: the mic records until you pause, sends 16 kHz WAV to `/api/speech/understand`, and Gemini returns the transcript plus the extracted intent and answer. Tutor speech uses Gemini TTS via `/api/speech/synthesize`.
- Without a key: browser speech recognition plus rule-based extraction (`/api/speech/interpret`), and the best available local voice.
