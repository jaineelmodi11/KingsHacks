# backend/main.py
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from backend import db
from backend.backboard import BackboardClient, DEFAULT_API_BASE_URL
from backend.risk import Purchase, extract_personalization, score_purchase

# Make .env loading robust whether you run uvicorn from repo root or backend/
load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

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


# -------------------------
# NEW: TravelProof endpoints
# -------------------------

class TravelModeRequest(BaseModel):
    current_country: str = Field(..., description="User current country code (e.g., IT)")
    trip_countries: list[str] = Field(default_factory=list, description="Countries for the trip (e.g., ['IT','FR'])")
    sms_available: bool = Field(False, description="Can user receive SMS abroad?")
    preferred_verification: str = Field("PASSKEY", description="PASSKEY or SMS")
    daily_budget: Optional[float] = None


class PurchaseAttemptRequest(BaseModel):
    merchant: str = Field(..., min_length=1)
    amount: float = Field(..., gt=0)
    currency: str = Field(..., min_length=1)
    country: str = Field(..., min_length=2)
    dcc_offered: bool = False


class PurchaseAttemptResponse(BaseModel):
    decision: str
    challenge_method: str
    risk_score: int
    reasons: list[str]
    explain: str
    personalization_used: dict
    retrieved_memories: Optional[list[dict]] = None


class DemoSeedResponse(BaseModel):
    ok: bool


def get_db_conn():
    conn = db.get_connection()
    try:
        yield conn
    finally:
        conn.close()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_audit_log(
    *,
    conn,
    session_id: str,
    user_prompt: str,
    assistant_text: Optional[str],
    raw_response: Any,
) -> None:
    """
    Writes audit logs using whatever DB function exists.
    - Prefers db.add_audit_log if present (older versions).
    - Falls back to db.insert_audit (current db.py in your paste).
    Never raises.
    """
    try:
        raw_json = json.dumps(raw_response, default=str)

        if hasattr(db, "add_audit_log"):
            db.add_audit_log(
                conn=conn,
                session_id=session_id,
                user_prompt=user_prompt,
                assistant_text=assistant_text,
                raw_response_json=raw_json,
            )
            return

        if hasattr(db, "insert_audit"):
            db.insert_audit(
                conn=conn,
                session_id=session_id,
                timestamp=_utc_now_iso(),
                user_prompt=user_prompt,
                assistant_text=assistant_text or "",
                raw_json=raw_json,
            )
            return
    except Exception:
        pass


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
    except Exception as exc:
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

    _safe_audit_log(
        conn=conn,
        session_id=session_id,
        user_prompt=payload.context,
        assistant_text=None,
        raw_response=response,
    )

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

    _safe_audit_log(
        conn=conn,
        session_id=session_id,
        user_prompt=payload.message,
        assistant_text=assistant_text,
        raw_response=response,
    )

    return ChatResponse(assistant_text=assistant_text, raw_response=response)


# -------------------------
# TravelProof endpoints
# -------------------------

@app.post("/sessions/{session_id}/profile/travel-mode")
async def set_travel_mode(
    session_id: str,
    payload: TravelModeRequest,
    client: BackboardClient = Depends(get_backboard_client),
    conn=Depends(get_db_conn),
):
    session = _get_session_or_404(conn, session_id)

    mem = {
        "current_country": payload.current_country.upper().strip(),
        "trip_countries": [c.upper().strip() for c in payload.trip_countries],
        "sms_available": bool(payload.sms_available),
        "preferred_verification": payload.preferred_verification.upper().strip(),
        "daily_budget": payload.daily_budget,
    }
    memory_str = f"TP_PROFILE {json.dumps(mem)}"

    # Store as an explicit memory so retrieval/listing works reliably
    resp = await client.add_memory(
        assistant_id=session["assistant_id"],
        content=memory_str,
        metadata={"tp": "profile"},
    )

    _safe_audit_log(
        conn=conn,
        session_id=session_id,
        user_prompt=memory_str,
        assistant_text=None,
        raw_response=resp,
    )

    return {"ok": True}


@app.post("/sessions/{session_id}/demo/seed", response_model=DemoSeedResponse)
async def demo_seed(
    session_id: str,
    client: BackboardClient = Depends(get_backboard_client),
    conn=Depends(get_db_conn),
) -> DemoSeedResponse:
    session = _get_session_or_404(conn, session_id)

    seed_messages = [
        'TP_PROFILE {"current_country":"IT","trip_countries":["IT"],"sms_available":false,"preferred_verification":"PASSKEY","daily_budget":80}',
        'TP_BASELINE {"typical_amount_min":8,"typical_amount_max":60}',
        "TP_TRUSTED_MERCHANT Trenitalia",
        "TP_TRUSTED_MERCHANT Coop",
    ]

    # Store as explicit memories (not just messages)
    for msg in seed_messages:
        await client.add_memory(
            assistant_id=session["assistant_id"],
            content=msg,
            metadata={"tp": "seed"},
        )

    return DemoSeedResponse(ok=True)


@app.post("/sessions/{session_id}/purchase/attempt", response_model=PurchaseAttemptResponse)
async def purchase_attempt(
    session_id: str,
    payload: PurchaseAttemptRequest,
    client: BackboardClient = Depends(get_backboard_client),
    conn=Depends(get_db_conn),
) -> PurchaseAttemptResponse:
    session = _get_session_or_404(conn, session_id)

    query = (
        "TravelProof memory lookup: "
        f"merchant={payload.merchant}, amount={payload.amount}, country={payload.country}. "
        "Return relevant TP_PROFILE / TP_BASELINE / TP_TRUSTED_MERCHANT memories."
    )

    retrieved = await client.query_memories(
        thread_id=session["thread_id"],
        assistant_id=session["assistant_id"],
        query=query,
        top_k=10,
    )

    personalization = extract_personalization(retrieved)

    # MVP: fixed trust score. (Later store/update in DB)
    trust_score = 50

    result = score_purchase(
        Purchase(
            merchant=payload.merchant,
            amount=float(payload.amount),
            currency=payload.currency,
            country=payload.country,
            dcc_offered=payload.dcc_offered,
        ),
        personalization=personalization,
        trust_score=trust_score,
    )

    _safe_audit_log(
        conn=conn,
        session_id=session_id,
        user_prompt=f"PURCHASE_ATTEMPT {payload.merchant} {payload.amount} {payload.currency} {payload.country}",
        assistant_text=result.explain,
        raw_response={
            "purchase": payload.model_dump(),
            "retrieved_memories": retrieved,
            "personalization_used": result.personalization_used,
            "risk_result": {
                "decision": result.decision,
                "challenge_method": result.challenge_method,
                "risk_score": result.risk_score,
                "reasons": result.reasons,
            },
        },
    )

    return PurchaseAttemptResponse(
        decision=result.decision,
        challenge_method=result.challenge_method,
        risk_score=result.risk_score,
        reasons=result.reasons,
        explain=result.explain,
        personalization_used=result.personalization_used,
        retrieved_memories=retrieved,
    )
