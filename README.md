# Elevate Tutor

React/Vite frontend and FastAPI backend, packaged as one Cloud Run service. The backend serves `/api/*` and the built frontend at `/`. Gemini on Vertex AI generates structured lesson steps; React renders the content and predefined visuals.

## Local development

Create a Python virtual environment in `backend/.venv`, install `backend/requirements.txt`, and copy `backend/.env.example` to `backend/.env`. Keep `FIRESTORE_ENABLED=false` for local JSON storage. Use one Uvicorn worker; local JSON storage is not shared across processes.

To enable AI, set `GOOGLE_CLOUD_PROJECT` to your billing-enabled GCP project,
enable `aiplatform.googleapis.com`, and run `gcloud auth application-default login`.
Your ADC identity needs Vertex AI access, typically `roles/aiplatform.user`.
Set `VERTEX_AI_LOCATION` (default `global`) and the `GEMINI_MODEL`,
`GEMINI_FALLBACK_MODELS`, `GEMINI_FAST_MODEL`, `GEMINI_TTS_MODEL`, and `GEMINI_TTS_VOICE` selections to
values available in that project/location. The default text model is
`gemini-3.8-flash`; no fallback models are enabled by default. `GEMINI_FAST_MODEL`
(default `gemini-3.5-flash-lite`) understands spoken answers and runs the answer-leak
check, and is also asked for a lesson step when the main model has not answered within
8 seconds; whichever replies first is used. Leave
`GOOGLE_CLOUD_PROJECT` empty for the scripted mock tutor. `GEMINI_API_KEY` is no
longer used. The client refreshes ADC tokens automatically, outside the async
event loop. Existing `gemini` health/source fields and internal names are retained
because the model remains Gemini; the API transport and authentication are Vertex AI.

```sh
cd backend
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload --port 8000
```

In another terminal:

```sh
cd frontend
npm ci
npm run dev
```

The Vite development server proxies `/api` to port 8000. Production uses the same container for frontend and API, so a separate frontend host or CORS configuration is unnecessary. Frontend navigation currently uses application state; add an API-safe SPA fallback if URL-based routes are introduced.

## Google sign-in

Email/password accounts always work, so the app runs with no Google setup. Setting `GOOGLE_CLIENT_ID` adds **Continue with Google** alongside them; the backend checks each Google ID token's signature, audience, expiry, and verified email.

One-time setup in the Google Cloud Console (any project, for example the Vertex AI one):

1. Open **Google Auth Platform** (APIs & Services → OAuth consent screen). Enter an app name and support email and choose the **External** audience. While the app is in *Testing*, only Google accounts added as test users can sign in; publish it to allow anyone. Basic sign-in (name and email) needs no Google review.
2. Under **Clients**, create an OAuth client of type **Web application**. Add `http://localhost`, `http://localhost:5173`, and, once deployed, your Cloud Run URL as **Authorized JavaScript origins**. No redirect URIs are needed.
3. Put the client ID in `backend/.env` as `GOOGLE_CLIENT_ID=….apps.googleusercontent.com` and restart the backend. The frontend reads it from `/api/health`, so it needs no configuration or rebuild.

The client ID is public, not a secret: teammates can reuse it to sign in locally without their own setup. Open the app at exactly `http://localhost:5173`; Google rejects unregistered origins such as `127.0.0.1`.

A first Google sign-in from **Create account** uses the role (and invite code) chosen there; from **Sign in**, new accounts start as students. If a password account already uses that email, Google sign-in links to it and keeps its progress, but removes the password and signs out its other sessions, because anyone could have registered that email with a password.

## Guardrails

Learners are school students who can type anything, so the tutor is protected in layers:

- **Answers stay on the server.** The answer key reaches Gemini only after the student has submitted an answer; hint, question and "explain again" turns never include it, and Gemini cannot change the waiting question.
- **Grading cannot be argued with.** Answers are marked by deterministic rules against the answers fixed when the question was written; Gemini's opinion never changes the result.
- **Student text is data, not instructions.** It is escaped and wrapped in `<student>` tags, and the system prompt tells Gemini to ignore instructions inside it.
- **A second check before anything is shown.** When a question is still open after a student message, hint or re-explanation, a second Gemini call checks that the reply does not give the answer away. If it does, or the check fails, the student gets a hint instead.
- **Vertex AI safety filters** block sexual content at the lowest threshold and harassment, hate and dangerous content from medium. A blocked student message gets a calm redirect and is removed from the lesson history sent to Gemini.

## Cloud Run deployment

Use a GCP project with billing enabled. Enable Cloud Run, Cloud Build, Artifact Registry, Firestore, Secret Manager, and Vertex AI (`aiplatform.googleapis.com`) APIs. Create a **Firestore Native mode `(default)` database** in the desired location; the application does not select a named database. Set `GOOGLE_CLOUD_PROJECT` to that project's ID and `FIRESTORE_ENABLED=true`. Do not use local JSON storage in production: Cloud Run's writable filesystem is temporary.

Create a dedicated runtime service account with `roles/datastore.user` and `roles/aiplatform.user`. Vertex AI uses that account's attached credentials; no Gemini API key is needed. Create a `teacher-invite-code` secret in Secret Manager, then grant that account `roles/secretmanager.secretAccessor` on that secret only. Supply a nonempty teacher invite code to prevent unrestricted teacher registration. Never put secret values in Docker build arguments, the frontend bundle, or source control.

Deploy the indexes before using teacher dashboards (Firebase CLI required):

```sh
firebase deploy --only firestore:indexes --project YOUR_PROJECT_ID
```

Wait for the event index to become ready. `firestore.indexes.json` declares the `events` query index on `userId` ascending and `ts` descending, and excludes large unqueried maps/session history from indexing. This Firebase configuration manages Firestore indexes only, not frontend Hosting. Backend database access uses IAM; browser clients should not receive direct Firestore access.

Create a Docker Artifact Registry repository, then build and deploy from the repository root:

```sh
PROJECT_ID=YOUR_PROJECT_ID
REGION=YOUR_REGION
REPOSITORY=YOUR_ARTIFACT_REPOSITORY
RUNTIME_SERVICE_ACCOUNT=YOUR_RUNTIME_SERVICE_ACCOUNT_EMAIL
GOOGLE_CLIENT_ID=YOUR_OAUTH_CLIENT_ID
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/elevate:DEPLOYMENT_TAG"

gcloud builds submit --project "$PROJECT_ID" --tag "$IMAGE" .
gcloud run deploy elevate \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --image "$IMAGE" \
  --service-account "$RUNTIME_SERVICE_ACCOUNT" \
  --set-env-vars "FIRESTORE_ENABLED=true,GOOGLE_CLOUD_PROJECT=$PROJECT_ID,VERTEX_AI_LOCATION=global,GOOGLE_CLIENT_ID=$GOOGLE_CLIENT_ID" \
  --set-secrets "TEACHER_INVITE_CODE=teacher-invite-code:latest" \
  --session-affinity \
  --allow-unauthenticated
```

`--session-affinity` keeps each browser on the same instance where possible. While a student reads a step, that instance prepares the next step and its audio in memory (`POST /api/tutor/prepare`), so Continue is instant; on another instance the step is simply generated as usual.

Add the deployed service URL to the OAuth client's **Authorized JavaScript origins** (see [Google sign-in](#google-sign-in)). Use a unique deployment tag. Verify the Gemini text/fallback/TTS model IDs and voice are available through Vertex AI in your project/location; configure them as backend environment variables when necessary. Public Cloud Run invocation allows the browser to reach the login page; protected API endpoints still require application authentication. Choose service memory, timeouts, concurrency, and maximum instances for your workload and budget.

The container listens on `0.0.0.0:$PORT` (default 8080). Verify `/`, frontend assets, `/api/health`, signup/login, a lesson, voice, and teacher dashboards after deploying. Check that learning state survives a new container revision.

### Consistent learning writes

Each turn reads a consistent learner/model/session snapshot. Model, session, lesson progress, and interaction events are then committed in one transaction. A learner version protects against concurrent turns, including turns in different lessons, and profile changes. LLM requests run **outside** Firestore transactions and are never repeated by transaction retries.

If another request changes the learner during generation, the stale turn returns HTTP 409 without committing any of its events or state. Reopen the lesson to load the latest state before submitting again; do not automatically resubmit an old answer to a potentially different question.

Sessions retain the most recent 64 history entries, with an additional 750 KB UTF-8 JSON budget below Firestore's 1 MiB document limit. Total tutor-step counts, pending questions, and accumulated mastery are retained. Older cards are no longer returned in lesson history; event records remain separate. An individually oversized step is rejected with HTTP 413 rather than losing the pending activity.

## Starter topics and demo data

Elevate ships with five starter topics: Fractions and Decimals & percentages (Mathematics), Photosynthesis and The water cycle (Science), and Parts of speech (English). Each is a lesson plan of key ideas and common misconceptions that Gemini teaches from. On start-up the app adds any starter topic that is missing from storage, and leaves existing topics, including edited ones, alone.

`backend/scripts/seed_demo.py` adds sign-ins and a class with realistic history, so the teacher dashboards and student insights have something to show:

- `priya.menon@lakeview.example`: a teacher.
- `riya.sharma@lakeview.example`: a student with about a week of history. She chose visual explanations at sign-up, but her answers show that real-life examples work better.
- `kiran.rao@lakeview.example`: a new student who goes through the sign-up questions.
- 12 more students with two weeks of progress, mistakes and teaching-style results. Each simulated answer goes through the real student model. They cannot sign in.

The reserved `.example` domain means these addresses can never belong to a real person; pass `--email-domain` to use another. All three sign-ins use the password you pass. Share it privately, for example in the hackathon submission notes, never in this repository. The script only creates what is missing, so running it again is safe.

```sh
# Local JSON storage
cd backend && .venv/bin/python scripts/seed_demo.py --password 'choose-a-password'

# Firestore used by Cloud Run (needs Application Default Credentials, e.g. from Cloud Shell)
cd backend && FIRESTORE_ENABLED=true GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID \
  python scripts/seed_demo.py --password 'choose-a-password'
```

### Copying the demo school to another deployment

`backend/scripts/demo_data.json` is a snapshot of the demo school from the team's deployment: the 15 `@lakeview.example` accounts with their profiles, student models, lessons and activity history. It holds no passwords or sign-in tokens. To give another deployment exactly the same demo school, import it instead of running `seed_demo.py`:

```sh
cd backend && FIRESTORE_ENABLED=true GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID \
  python scripts/demo_data.py import --password 'choose-a-password'
```

The three accounts that can sign in get the password you pass. Accounts whose email already exists are skipped, so running it again is safe, and an interrupted import finishes when run again. The import takes about 30 seconds and makes no Gemini calls. To refresh the snapshot after changing the demo school, run `python scripts/demo_data.py export` with the same settings against the deployment that has the changes. Both commands also work with local JSON storage when `FIRESTORE_ENABLED` is not set.

## Migrating local data

Back up `backend/data/store.json` and the destination database first. Use local Application Default Credentials with database-write access. Stop local writes and perform the import before starting Cloud Run: startup adds the starter topics to the database.

```sh
gcloud auth application-default login
backend/.venv/bin/python backend/scripts/migrate_store_to_firestore.py \
  --source backend/data/store.json \
  --project YOUR_PROJECT_ID
```

The script preserves password hashes and token hashes, converts local token values into Firestore token documents, and creates normalized-email lookup records. It refuses a populated destination unless `--overwrite` is supplied. That flag replaces matching document IDs; it does **not** clear other documents. Review it carefully before use, particularly against a live deployment.

Imports use batches of 450 documents, not one database-wide transaction. Keep the destination offline until the import finishes; an interrupted import may need a reviewed rerun with `--overwrite`. Large legacy sessions may require shortening before import to meet Firestore document limits.

## Validation

Backend tests require `pytest` in the virtual environment:

```sh
backend/.venv/bin/python -m pytest backend/tests -q
cd frontend && npm run build && npm run lint
```

The test configuration forces Firestore/Gemini off before application imports and uses temporary JSON storage, even if `backend/.env` enables production services.

For actual Firestore transaction tests, install the Google Cloud CLI Firestore emulator component and a compatible Java runtime (Java 25 for current releases), then start the emulator in another terminal:

```sh
gcloud emulators firestore start --host-port=127.0.0.1:8899
```

Then run from the repository root:

```sh
FIRESTORE_EMULATOR_HOST=127.0.0.1:8899 \
  backend/.venv/bin/python -m pytest backend/tests -q
```

These integration tests use anonymous credentials, unique disposable emulator projects, and only accept loopback emulator addresses. Without an emulator, they are skipped. Emulator tests do not prove that production indexes have been deployed; verify index readiness separately.
