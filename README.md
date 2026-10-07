# Brightpath Tutor

React/Vite frontend and FastAPI backend, packaged as one Cloud Run service. The backend serves `/api/*` and the built frontend at `/`. Gemini generates structured lesson steps; React renders the content and predefined visuals.

## Local development

Create a Python virtual environment in `backend/.venv`, install `backend/requirements.txt`, and copy `backend/.env.example` to `backend/.env`. Keep `FIRESTORE_ENABLED=false` for local JSON storage. Use one Uvicorn worker; local JSON storage is not shared across processes.

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

## Cloud Run deployment

Use a GCP project with billing enabled. Enable Cloud Run, Cloud Build, Artifact Registry, Firestore, and Secret Manager APIs. Create a **Firestore Native mode `(default)` database** in the desired location; the application does not select a named database. Set `GOOGLE_CLOUD_PROJECT` to that project's ID and `FIRESTORE_ENABLED=true`. Do not use local JSON storage in production: Cloud Run's writable filesystem is temporary.

Create a dedicated runtime service account with `roles/datastore.user`. Create `gemini-api-key` and `teacher-invite-code` secrets in Secret Manager, then grant that account `roles/secretmanager.secretAccessor` on those two secrets only. Supply a nonempty teacher invite code to prevent unrestricted teacher registration. Never put secret values in Docker build arguments, the frontend bundle, or source control.

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
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/brightpath:DEPLOYMENT_TAG"

gcloud builds submit --project "$PROJECT_ID" --tag "$IMAGE" .
gcloud run deploy brightpath \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --image "$IMAGE" \
  --service-account "$RUNTIME_SERVICE_ACCOUNT" \
  --set-env-vars "FIRESTORE_ENABLED=true,GOOGLE_CLOUD_PROJECT=$PROJECT_ID" \
  --set-secrets "GEMINI_API_KEY=gemini-api-key:latest,TEACHER_INVITE_CODE=teacher-invite-code:latest" \
  --allow-unauthenticated
```

Use a unique deployment tag. Verify the Gemini text/fallback/TTS model IDs are available to your key; configure them as backend environment variables when necessary. Public Cloud Run invocation allows the browser to reach the login page; protected API endpoints still require application authentication. Choose service memory, timeouts, concurrency, and maximum instances for your workload and budget.

The container listens on `0.0.0.0:$PORT` (default 8080). Verify `/`, frontend assets, `/api/health`, signup/login, a lesson, voice, and teacher dashboards after deploying. Check that learning state survives a new container revision.

### Consistent learning writes

Each turn reads a consistent learner/model/session snapshot. Model, session, lesson progress, and interaction events are then committed in one transaction. A learner version protects against concurrent turns, including turns in different lessons, and profile changes. LLM requests run **outside** Firestore transactions and are never repeated by transaction retries.

If another request changes the learner during generation, the stale turn returns HTTP 409 without committing any of its events or state. Reopen the lesson to load the latest state before submitting again; do not automatically resubmit an old answer to a potentially different question.

Sessions retain the most recent 64 history entries, with an additional 750 KB UTF-8 JSON budget below Firestore's 1 MiB document limit. Total tutor-step counts, pending questions, and accumulated mastery are retained. Older cards are no longer returned in lesson history; event records remain separate. An individually oversized step is rejected with HTTP 413 rather than losing the pending activity.

## Migrating local data

Back up `backend/data/store.json` and the destination database first. Use local Application Default Credentials with database-write access. Stop local writes and perform the import before starting Cloud Run: startup seeds starter topics into an empty database.

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
