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

## Docker (API + Worker + DB)

1. Create env file:

```bash
cp backend/.env.example backend/.env
```

2. Start everything (Postgres + migration + API + worker):

```bash
docker compose up --build -d
```

3. Check services:

```bash
docker compose ps
docker compose logs -f api worker
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

Supported assistant intents:

- `average_age_by_office`
- `ticket_count_by_city`
- `ticket_type_distribution`
- `sentiment_distribution`
- `avg_priority_by_office`
- `workload_by_manager`
- `custom_filtered_summary`

Example queries:

- `показать средний возраст клиентов, чьи обращения попали в офисы Астаны и Алматы`
- `распределение тональности обращений за 2026-02-01 2026-02-21`
- `нагрузка по менеджерам в офисе Астана`
- `count tickets by city for VIP segment`

Response shape:

- `intent`: resolved allowlisted intent
- `title`: chart title
- `chart_type`: `bar | line | pie | table`
- `data`: `{ labels: string[], values: number[] }`
- `table`: tabular rows for UI
- `explanation`: business-readable explanation
- `filters`: sanitized filters extracted from NL query

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
- Worker claims jobs with `FOR UPDATE SKIP LOCKED`, processes them, and updates run/job status.
- Retry policy uses exponential backoff (`WORKER_RETRY_BASE_SECONDS`, `WORKER_RETRY_MAX_SECONDS`) up to `WORKER_MAX_ATTEMPTS`.

Idempotency:

- Send `Idempotency-Key` header on async enqueue endpoints.
- If the key already exists, API returns the previously created job/run instead of creating duplicates.

Run worker:

```bash
python -m backend.worker
```

One-shot processing (useful in local dev/CI):

```bash
python -m backend.worker --once
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

## Run Tests

```bash
pytest backend/tests -q
```
