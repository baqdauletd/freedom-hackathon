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
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
```

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
- `POST /tickets/process`
- `POST /tickets/batch` (returns run metadata + results)
- `GET /results` (paged/filterable result browsing)
- `GET /tickets/{id}` (ticket drill-down + explainability trace)
- `GET /managers` (manager load + assigned counts)
- `GET /analytics/summary` (supports `run_id`, `office`, `date_from`, `date_to`)
- `POST /assistant/query`

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

## Frontend Env

Frontend reads API base URL from:

- `VITE_API_BASE_URL` (preferred)
- `VITE_API_BASE` (supported fallback)

## Run Tests

```bash
pytest backend/tests -q
```
