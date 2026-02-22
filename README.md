# Freedom Hackathon (FIRE)

Backend and frontend implement FIRE routing rules, a dashboard UI, analytics, and assistant endpoints.

## Backend Structure

```
backend/
  app.py
  api/
  core/
  db/
  schemas/
  services/
  tests/
```

## Frontend Structure

```
frontend/
  src/
    app/
    api/
    features/
    pages/
    state/
```

## Run Locally

1. Start PostgreSQL:

```bash
docker compose up -d postgres
```

2. Install backend deps:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

3. Configure env:

```bash
cp backend/.env.example backend/.env
# edit backend/.env
export $(grep -v '^#' backend/.env | xargs)
```

4. Run migrations:

```bash
alembic -c backend/alembic.ini upgrade head
```

5. Start API:

```bash
python -m uvicorn backend.app:app --reload --reload-dir backend --host 0.0.0.0 --port 8000
```

Run this command from the repository root (`freedom-hackathon/`), not from `backend/`.

6. Start frontend:

```bash
cd frontend
npm install
npm run dev
```

## Main Endpoints

- `GET /health`
- `GET /runs` (list recent processing runs for scope selector)
- `POST /route` (reads CSV paths from env)
- `POST /route/upload` (multipart CSV upload, returns `{run_id, summary, results}`; `?legacy=true` returns list)
- `POST /route/upload/async` (enqueue CSV processing job, returns `{run_id, run_status, job}`)
- `POST /tickets/process`
- `POST /tickets/batch` (returns run metadata + results)
- `POST /tickets/batch/async` (enqueue batch job)
- `GET /runs/{run_id}/status` (progress API: run + summary + linked job status)
- `GET /jobs/{job_id}` (job attempts/retry/error state)
- `GET /results` (paged/filterable result browsing)
- `GET /tickets/{id}` (ticket drill-down + explainability trace)
- `GET /managers` (manager load + assigned counts)
- `GET /analytics/summary` (supports `run_id`, `office`, `date_from`, `date_to`)
- `POST /assistant/query`

## Database + Migrations

- Alembic is configured to run from repository root and import the `backend` package correctly.
- Migration command:

```bash
alembic -c backend/alembic.ini upgrade head
```

- Current schema revisions include queue support and assignment status/reason fields.

## Backend Env Vars

Primary vars (see `backend/.env.example` for full list):

- `DATABASE_URL`
- `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_TIMEOUT_SECONDS`
- `FIRE_COMPLIANCE_MODE`, `ENABLE_GEOCODE`
- `GEOCODE_TIMEOUT_SECONDS`, `GEOCODE_RATE_LIMIT_SECONDS`, `GEOCODE_FAIL_STREAK_LIMIT`
- `PER_TICKET_BUDGET_MS`
- `WORKER_POLL_INTERVAL_SECONDS`, `WORKER_MAX_ATTEMPTS`, `WORKER_RETRY_BASE_SECONDS`, `WORKER_RETRY_MAX_SECONDS`
- `USE_CELERY`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`

## Docker (API + DB + Redis + Workers)

1. Create env file:

```bash
cp backend/.env.example backend/.env
```

2. Start everything (Postgres + migration + API + Redis + workers):

```bash
docker compose up --build -d
```

3. Check services:

```bash
docker compose ps
docker compose logs -f api worker worker-default worker-ai worker-geocode worker-routing
```

Optional Flower UI:

```bash
docker compose --profile observability up -d flower
# http://localhost:5555
```

4. Stop:

```bash
docker compose down
```

## Example: `/route/upload`

```bash
curl -X POST http://localhost:8000/route/upload \
  -F "tickets=@tickets.csv" \
  -F "managers=@managers.csv" \
  -F "business_units=@business_units.csv"
```

## Example: `/results`

```bash
curl "http://localhost:8000/results?run_id=RUN_ID&limit=25&offset=0&sort_by=priority&sort_order=desc"
```

## Example: `/tickets/{id}`

```bash
curl "http://localhost:8000/tickets/1"
```

## Example: `/managers`

```bash
curl "http://localhost:8000/managers?run_id=RUN_ID&office=Астана"
```

## Example: `/assistant/query`

```bash
curl -X POST http://localhost:8000/assistant/query \
  -H "Content-Type: application/json" \
  -d '{"query":"Покажи распределение типов обращений по городам"}'
```

Compatibility payload is also supported:

```bash
curl -X POST http://localhost:8000/assistant/query \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Show sentiment distribution"}'
```

## Assistant (Star Task)

Assistant now supports:

- Result and clarification responses (`kind: "result" | "clarification"`).
- Expanded hard-mapped analytics intents (distribution, VIP breakdown, unassigned, processing-time, trend).
- Scope intersection enforcement (`run_id`, `office`, `date_from`, `date_to`) to prevent prompt-based scope expansion.
- Deterministic fallback mode with chart-ready response schema.
- Provenance metadata (`computed_from`, `scope_applied`, `warnings`, `used_fallback`, `cache_hit`).

See full Star Task details and sample payloads in `docs/star-task.md`.

Security model:

- LLM is used only for intent classification + filter extraction.
- Intent must be from a strict allowlist.
- Filters are validated/sanitized against known offices/cities and allowed enums.
- Backend never executes arbitrary SQL from LLM output.
- Analytics queries are built with SQLAlchemy only.
- Assistant calls are logged with intent, filters, and latency.

## Background Worker Queue

Queue model:

- Upload async endpoint validates CSVs and enqueues a DB job (`processing_jobs`) linked to `processing_runs`.
- **DB is source of truth** for status/progress (`/jobs/{id}` reads only DB).
- `USE_CELERY=true`: API dispatches `process_run` Celery task; pipeline fan-out uses queues: `default`, `ai`, `geocode`, `routing`.
- `USE_CELERY=false`: legacy DB polling worker continues to work (`python -m backend.worker`).
- Retry policy:
  - AI/geocode transient failures retry with backoff+jitter.
  - Assignment retries only for deadlock/serialization DB errors (max 1-2 retries).
  - Deterministic validation failures are marked failed without retry.

Idempotency:

- Send `Idempotency-Key` header on async enqueue endpoints.
- If the key already exists, API returns the previously created job/run instead of creating duplicates.

Run legacy worker (non-Celery mode):

```bash
python -m backend.worker
```

One-shot processing (useful in local dev/CI):

```bash
python -m backend.worker --once

Run Celery workers (Celery mode):

```bash
export USE_CELERY=true
# or set USE_CELERY=true in backend/.env for API container/local API process
celery -A backend.celery_app.celery_app worker -Q default --loglevel=INFO
celery -A backend.celery_app.celery_app worker -Q ai --loglevel=INFO
celery -A backend.celery_app.celery_app worker -Q geocode --loglevel=INFO
celery -A backend.celery_app.celery_app worker -Q routing --loglevel=INFO
```
```

Async enqueue example:

```bash
curl -X POST http://localhost:8000/route/upload/async \
  -H "Idempotency-Key: run-2026-02-22-001" \
  -F "tickets=@tickets.csv" \
  -F "managers=@managers.csv" \
  -F "business_units=@business_units.csv"
```

Progress example:

```bash
curl "http://localhost:8000/runs/<RUN_ID>/status"
curl "http://localhost:8000/jobs/<JOB_ID>"
```

## Frontend Env

Frontend reads API base URL from:

- `VITE_API_BASE_URL` (preferred)
- `VITE_API_BASE` (supported fallback)

UI scope behavior:

- Scope selector (Run + optional date range) is shared across Results, Analytics, and Assistant.
- “Assigned tickets” charts use scope-based assignment counts.
- “Current load” is shown separately as manager state.

## Run Tests

```bash
pytest backend/tests -q
```
