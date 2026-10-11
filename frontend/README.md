# brightpath Student Frontend

React + TypeScript client for the personalised AI tutor. It talks only to the Python backend in `../backend` (proxied at `/api`).

## Run locally

Start the backend first (from `../backend`):

```bash
cp .env.example .env              # set GOOGLE_CLOUD_PROJECT to use Gemini on Vertex AI; leave empty for the scripted mock tutor
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
  "content": [
    { "type": "text", "text": "..." },
    { "type": "visual", "visual": { "type": "bar-chart", "caption": "...", "fractions": [], "data": [{ "label": "1/2", "value": 60 }], "yLabel": "cm" } },
    { "type": "callout", "label": "Remember", "text": "..." }
  ],
  "paragraphs": ["..."],
  "speech": "Spoken version of the step",
  "feedback": { "correct": true, "message": "..." },
  "question": { "prompt": "...", "format": "choice | text", "options": ["1/4", "1/6"] }
}
```

`content` is the ordered list of blocks to render: text, callout, or a visual (`fraction-circles`, `fraction-bars`, `number-line`, `flow`, `comparison`, `bar-chart`, `line-graph`, `table`). Older saved steps without `content` fall back to `paragraphs` and `visual`. Correct answers stay on the server.

## Voice

- With Vertex AI configured: the mic records until you pause, sends 16 kHz WAV to `/api/speech/understand`, and Gemini returns the transcript plus the extracted intent and answer. Tutor speech uses Gemini TTS via `/api/speech/synthesize`.
- Without it: browser speech recognition plus rule-based extraction (`/api/speech/interpret`), and the best available local voice.
