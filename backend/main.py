import json
import os
import uuid
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from backend import db
from backend.backboard import BackboardClient, DEFAULT_API_BASE_URL


load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL", DEFAULT_API_BASE_URL)
BACKBOARD_API_KEY = os.getenv("BACKBOARD_API_KEY")


app = FastAPI(title="Enterprise Memory Copilot Backend")


class SessionResponse(BaseModel):
    session_id: str
    assistant_id: str
    thread_id: str


class IngestRequest(BaseModel):
    context: str = Field(..., description="Context or documents to store in Backboard")


class IngestResponse(BaseModel):
    ok: bool
    backboard_response: Optional[Dict[str, Any]] = None


class ChatRequest(BaseModel):
    message: str = Field(..., description="User message to send to the assistant")


class ChatResponse(BaseModel):
    assistant_text: str
    raw_response: Optional[Dict[str, Any]] = None


def get_db_conn():
    conn = db.get_connection()
    try:
        yield conn
    finally:
        conn.close()


async def get_backboard_client(request: Request) -> BackboardClient:
    client: Optional[BackboardClient] = getattr(request.app.state, "bb_client", None)
    if not client:
        raise HTTPException(status_code=500, detail="Backboard client not initialized.")
    if not client.api_key:
        raise HTTPException(
            status_code=500,
            detail="BACKBOARD_API_KEY is not configured. Set it in the environment or .env file.",
        )
    return client


@app.on_event("startup")
async def startup_event() -> None:
    db.init_db()
    app.state.bb_client = BackboardClient(BACKBOARD_API_KEY, API_BASE_URL)


@app.on_event("shutdown")
async def shutdown_event() -> None:
    client: BackboardClient = app.state.bb_client
    await client.aclose()


@app.get("/healthz")
async def healthz() -> Dict[str, bool]:
    return {"ok": True}


@app.post("/sessions", response_model=SessionResponse, status_code=201)
async def create_session(
    client: BackboardClient = Depends(get_backboard_client), conn=Depends(get_db_conn)
) -> SessionResponse:
    session_id = str(uuid.uuid4())
    assistant_name = f"Enterprise Memory Session {session_id}"

    assistant_id = await client.create_assistant(assistant_name)
    thread_id = await client.create_thread(assistant_id)

    try:
        db.create_session(conn, session_id, assistant_id, thread_id)
    except Exception as exc:  # pragma: no cover - defensive error surface
        raise HTTPException(status_code=500, detail=f"Failed to persist session: {exc}") from exc

    return SessionResponse(session_id=session_id, assistant_id=assistant_id, thread_id=thread_id)


def _get_session_or_404(conn, session_id: str) -> Dict[str, str]:
    session = db.get_session(conn, session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return session


@app.post("/sessions/{session_id}/ingest", response_model=IngestResponse)
async def ingest_context(
    session_id: str,
    payload: IngestRequest,
    client: BackboardClient = Depends(get_backboard_client),
    conn=Depends(get_db_conn),
) -> IngestResponse:
    session = _get_session_or_404(conn, session_id)

    response = await client.send_message(
        thread_id=session["thread_id"],
        message=payload.context,
        send_to_llm=False,
        memory="Auto",
        assistant_id=session["assistant_id"],
    )

    try:
        db.add_audit_log(
            conn=conn,
            session_id=session_id,
            user_prompt=payload.context,
            assistant_text=None,
            raw_response_json=json.dumps(response, default=str),
        )
    except Exception:
        # Non-blocking log failure
        pass

    return IngestResponse(ok=True, backboard_response=response)


@app.post("/sessions/{session_id}/chat", response_model=ChatResponse)
async def chat(
    session_id: str,
    payload: ChatRequest,
    client: BackboardClient = Depends(get_backboard_client),
    conn=Depends(get_db_conn),
) -> ChatResponse:
    session = _get_session_or_404(conn, session_id)

    response = await client.send_message(
        thread_id=session["thread_id"],
        message=payload.message,
        send_to_llm=True,
        memory="Auto",
        assistant_id=session["assistant_id"],
    )

    assistant_text = await client.extract_assistant_text(response)
    if not assistant_text:
        raise HTTPException(
            status_code=502,
            detail="Backboard did not return assistant text. Check raw_response for details.",
        )

    try:
        db.add_audit_log(
            conn=conn,
            session_id=session_id,
            user_prompt=payload.message,
            assistant_text=assistant_text,
            raw_response_json=json.dumps(response, default=str),
        )
    except Exception:
        pass

    return ChatResponse(assistant_text=assistant_text, raw_response=response)
