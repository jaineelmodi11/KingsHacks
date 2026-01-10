# Enterprise Memory Copilot Backend

FastAPI backend that wraps Backboard as a memory layer. It manages sessions, ingests context without generation, chats with memory enabled, and tracks everything in SQLite.

## Setup
- Requires Python 3.10+.
- Copy `.env.example` to `.env` and set `BACKBOARD_API_KEY`. Override `API_BASE_URL` if needed (defaults to `https://app.backboard.io/api`).
- Install deps and run the server:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

## Endpoints
- `GET /healthz` → `{"ok": true}`
- `POST /sessions` → creates a Backboard assistant + thread, stores `{session_id, assistant_id, thread_id}` in SQLite.
- `POST /sessions/{session_id}/ingest` → saves context to Backboard with `send_to_llm=false` (no generation).
- `POST /sessions/{session_id}/chat` → sends message with `send_to_llm=true`, `memory="auto"`, returns assistant text and raw response; logs to `audit_log`.

## Quick cURL Self-Check
```bash
# Health
curl -s http://localhost:8000/healthz

# Create a session (grab the IDs)
curl -s -X POST http://localhost:8000/sessions

# If you have jq installed, capture the session ID for reuse:
SESSION_ID=$(curl -s -X POST http://localhost:8000/sessions | jq -r '.session_id')

# Ingest context (no LLM call)
curl -s -X POST http://localhost:8000/sessions/$SESSION_ID/ingest \
  -H "Content-Type: application/json" \
  -d '{"context":"Key facts or docs to store for this copilot."}'

# Chat with memory and LLM enabled
curl -s -X POST http://localhost:8000/sessions/$SESSION_ID/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Summarize what you remember."}'
```

## Notes
- SQLite lives at `backend/data/sessions.db` with `sessions` and `audit_log` tables.
- Backboard calls use `httpx` with a small endpoint fallback strategy (`/v1/...` and non-versioned paths) to stay resilient to minor API shape changes.
- Errors from Backboard (401/403/5xx) bubble up as HTTP errors with details to aid debugging.
