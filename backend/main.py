# backend/main.py
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend import db
from backend.backboard import BackboardClient, DEFAULT_API_BASE_URL
from backend.risk import Purchase, extract_personalization, score_purchase

# Load env from repo root .env
load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

API_BASE_URL = os.getenv("API_BASE_URL", DEFAULT_API_BASE_URL)
BACKBOARD_API_KEY = os.getenv("BACKBOARD_API_KEY")

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")
_origins = ["*"] if CORS_ORIGINS.strip() == "*" else [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]

app = FastAPI(title="TravelProof Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------
# Models
# -------------------------

class SessionResponse(BaseModel):
    session_id: str
    assistant_id: str
    thread_id: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)


class ChatResponse(BaseModel):
    assistant_text: str
    raw_response: Optional[dict] = None


class TravelModeRequest(BaseModel):
    current_country: str
    trip_countries: list[str] = Field(default_factory=list)
    sms_available: bool = False
    preferred_verification: str = "PASSKEY"
    daily_budget: Optional[float] = None


class PurchaseAttemptRequest(BaseModel):
    merchant: str = Field(..., min_length=1)
    amount: float = Field(..., gt=0)
    currency: str = Field(..., min_length=1)
    country: str = Field(..., min_length=2)
    dcc_offered: bool = False
    channel: str = "CNP"
    item_description: Optional[str] = None
    shipping_country: Optional[str] = None


class PurchaseAttemptResponse(BaseModel):
    decision: str
    challenge_method: str
    risk_score: int
    risk_level: str
    merchant_trust_tier: str
    reasons: list[str]
    explain: str
    user_message: str
    personalization_used: dict
    retrieved_memories: Optional[list[dict]] = None


class PurchasePreviewRequest(BaseModel):
    purchases: list[PurchaseAttemptRequest]


class StoreRiskItem(BaseModel):
    merchant: str
    amount: float
    currency: str
    country: str
    dcc_offered: bool
    channel: str
    item_description: Optional[str] = None
    decision: str
    challenge_method: str
    risk_score: int
    risk_level: str
    merchant_trust_tier: str
    reasons: list[str]
    explain: str
    user_message: str


class PurchasePreviewResponse(BaseModel):
    personalization: dict
    store_risks: list[StoreRiskItem]
    retrieved_memories: Optional[list[dict]] = None


class DemoSeedResponse(BaseModel):
    ok: bool


class CardResponse(BaseModel):
    id: int
    nickname: Optional[str]
    network: str
    last4: str
    exp_month: Optional[int] = None
    exp_year: Optional[int] = None
    billing_country: Optional[str] = None
    created_at: str


class CardsResponse(BaseModel):
    cards: list[CardResponse]


class PaymentAuthorizeRequest(BaseModel):
    card_id: int
    merchant: str
    amount: float
    currency: str
    country: str
    dcc_offered: bool = False
    channel: str = "CNP"
    item_description: Optional[str] = None
    shipping_country: Optional[str] = None


class PaymentAuthorizeResponse(BaseModel):
    status: str  # APPROVED | CHALLENGE_REQUIRED
    decision: str
    challenge_method: str
    risk_score: int
    risk_level: str
    merchant_trust_tier: str
    reasons: list[str]
    explain: str
    user_message: str
    challenge_id: Optional[str] = None
    card: Optional[dict] = None
    personalization_used: dict
    retrieved_memories: Optional[list[dict]] = None


class ChallengeVerifyRequest(BaseModel):
    challenge_id: str
    action: str = Field(..., description="APPROVE or DENY")


class ChallengeVerifyResponse(BaseModel):
    status: str  # COMPLETED | DENIED | FAILED
    challenge_id: str
    method: str
    message: str


# -------------------------
# Helpers
# -------------------------

def get_db_conn():
    conn = db.get_connection()
    try:
        yield conn
    finally:
        conn.close()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_audit_log(*, conn, session_id: str, user_prompt: str, assistant_text: Optional[str], raw_response: Any) -> None:
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
        raise HTTPException(status_code=500, detail="BACKBOARD_API_KEY is not configured.")
    return client


def _get_session_or_404(conn, session_id: str) -> Dict[str, str]:
    s = db.get_session(conn, session_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return s


# -------------------------
# Lifecycle
# -------------------------

@app.on_event("startup")
async def startup_event() -> None:
    db.init_db()
    app.state.bb_client = BackboardClient(BACKBOARD_API_KEY, API_BASE_URL)


@app.on_event("shutdown")
async def shutdown_event() -> None:
    client: BackboardClient = app.state.bb_client
    await client.aclose()


# -------------------------
# Core endpoints
# -------------------------

@app.get("/healthz")
async def healthz() -> Dict[str, bool]:
    return {"ok": True}


@app.post("/sessions", response_model=SessionResponse, status_code=201)
async def create_session(
    client: BackboardClient = Depends(get_backboard_client),
    conn=Depends(get_db_conn),
) -> SessionResponse:
    session_id = str(uuid.uuid4())
    assistant_id = await client.create_assistant(f"TravelProof {session_id}")
    thread_id = await client.create_thread(assistant_id)

    try:
        if hasattr(db, "create_session"):
            db.create_session(conn, session_id, assistant_id, thread_id)
        else:
            db.upsert_session(conn, session_id, assistant_id, thread_id, _utc_now_iso())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to persist session: {exc}") from exc

    return SessionResponse(session_id=session_id, assistant_id=assistant_id, thread_id=thread_id)


# ✅ AI endpoint (Backboard LLM) — fixes your 404
@app.post("/sessions/{session_id}/chat", response_model=ChatResponse)
async def chat(
    session_id: str,
    payload: ChatRequest,
    client: BackboardClient = Depends(get_backboard_client),
    conn=Depends(get_db_conn),
) -> ChatResponse:
    session = _get_session_or_404(conn, session_id)

    # Keep it short + demo-friendly
    prompt = (
        "You are TravelProof, a demo issuer assistant.\n"
        "Explain decisions briefly and clearly.\n\n"
        f"User: {payload.message}"
    )

    # Try not to store this as memory; fallback if not supported
    try:
        resp = await client.send_message(
            thread_id=session["thread_id"],
            message=prompt,
            send_to_llm=True,
            memory="off",
            assistant_id=session["assistant_id"],
        )
    except HTTPException:
        resp = await client.send_message(
            thread_id=session["thread_id"],
            message=prompt,
            send_to_llm=True,
            memory="Auto",
            assistant_id=session["assistant_id"],
        )

    assistant_text = await client.extract_assistant_text(resp)
    if not assistant_text:
        raise HTTPException(status_code=502, detail="Backboard did not return assistant text.")

    _safe_audit_log(
        conn=conn,
        session_id=session_id,
        user_prompt=payload.message,
        assistant_text=assistant_text,
        raw_response=resp,
    )

    return ChatResponse(assistant_text=assistant_text, raw_response=resp)


# -------------------------
# Demo seed: Sweden + demo card
# -------------------------

@app.post("/sessions/{session_id}/demo/seed-sweden", response_model=DemoSeedResponse)
async def demo_seed_sweden(
    session_id: str,
    client: BackboardClient = Depends(get_backboard_client),
    conn=Depends(get_db_conn),
) -> DemoSeedResponse:
    session = _get_session_or_404(conn, session_id)

    seed_messages = [
        # Sweden travel mode
        'TP_PROFILE {"current_country":"SE","trip_countries":["SE"],"sms_available":false,"preferred_verification":"PASSKEY","daily_budget":900}',
        'TP_BASELINE {"typical_amount_min":50,"typical_amount_max":600}',

        # Trust tiers
        "TP_TRUSTED_MERCHANT_HIGH ICA",
        "TP_TRUSTED_MERCHANT_HIGH IKEA",
        "TP_TRUSTED_MERCHANT_MED SJ",
        "TP_TRUSTED_MERCHANT_MED H&M",
        "TP_TRUSTED_MERCHANT_HIGH Systembolaget",

        # Merchant facts with official sources
        'TP_MERCHANT_FACTS {"merchant":"ICA","category":"GROCERY","home_country":"SE","restricted":false,"source_url":"https://www.icagruppen.se/en/about-ica-gruppen/our-business/our-companies/ica-sweden/"}',
        'TP_MERCHANT_FACTS {"merchant":"Systembolaget","category":"ALCOHOL","home_country":"SE","restricted":true,"source_url":"https://www.omsystembolaget.se/english/systembolaget-explained/"}',
        'TP_MERCHANT_FACTS {"merchant":"SJ","category":"TRANSIT","home_country":"SE","restricted":false,"source_url":"https://www.sj.se/en/about-sj"}',
        'TP_MERCHANT_FACTS {"merchant":"H&M","category":"APPAREL","home_country":"SE","restricted":false,"source_url":"https://hmgroup.com/about-us/history/"}',
        'TP_MERCHANT_FACTS {"merchant":"IKEA","category":"FURNITURE","home_country":"SE","restricted":false,"source_url":"https://www.ikea.com/global/en/our-business/how-we-work/story-of-ikea/"}',
    ]

    for msg in seed_messages:
        await client.add_memory(
            assistant_id=session["assistant_id"],
            content=msg,
            metadata={"tp": "seed_sweden"},
        )

    # Auto-create demo card if none exists
    cards = db.list_cards(conn, session_id=session_id)
    if not cards:
        db.add_card(
            conn,
            session_id=session_id,
            nickname="Demo Visa",
            network="VISA",
            last4="4242",
            exp_month=12,
            exp_year=2030,
            billing_country="CA",
        )

    return DemoSeedResponse(ok=True)


@app.get("/sessions/{session_id}/cards", response_model=CardsResponse)
async def get_cards(session_id: str, conn=Depends(get_db_conn)) -> CardsResponse:
    _ = _get_session_or_404(conn, session_id)
    cards = db.list_cards(conn, session_id=session_id)
    return CardsResponse(cards=[CardResponse(**c) for c in cards])


# -------------------------
# Risk dashboard
# -------------------------

@app.post("/sessions/{session_id}/purchase/preview", response_model=PurchasePreviewResponse)
async def purchase_preview(
    session_id: str,
    payload: PurchasePreviewRequest,
    client: BackboardClient = Depends(get_backboard_client),
    conn=Depends(get_db_conn),
) -> PurchasePreviewResponse:
    session = _get_session_or_404(conn, session_id)

    retrieved = await client.query_memories(
        thread_id=session["thread_id"],
        assistant_id=session["assistant_id"],
        query="Return TP_PROFILE / TP_BASELINE / TP_TRUSTED_MERCHANT_* / TP_MERCHANT_FACTS for TravelProof UI.",
        top_k=80,
    )
    p = extract_personalization(retrieved)

    personalization_ui = {
        "current_country": p.current_country,
        "trip_countries": p.trip_countries,
        "sms_available": p.sms_available,
        "preferred_verification": p.preferred_verification,
        "daily_budget": p.daily_budget,
        "typical_amount_min": p.typical_amount_min,
        "typical_amount_max": p.typical_amount_max,
        "trusted_high": sorted(list(p.trusted_high)),
        "trusted_med": sorted(list(p.trusted_med)),
        "trusted_low": sorted(list(p.trusted_low)),
    }

    store_risks: list[StoreRiskItem] = []
    for x in payload.purchases:
        result = score_purchase(
            Purchase(
                merchant=x.merchant,
                amount=float(x.amount),
                currency=x.currency,
                country=x.country,
                dcc_offered=x.dcc_offered,
                channel=x.channel,
                item_description=x.item_description,
                shipping_country=x.shipping_country,
            ),
            personalization=p,
            trust_score=50,
        )

        store_risks.append(
            StoreRiskItem(
                merchant=x.merchant,
                amount=float(x.amount),
                currency=x.currency,
                country=x.country,
                dcc_offered=x.dcc_offered,
                channel=x.channel,
                item_description=x.item_description,
                decision=result.decision,
                challenge_method=result.challenge_method,
                risk_score=result.risk_score,
                risk_level=result.risk_level,
                merchant_trust_tier=result.merchant_trust_tier,
                reasons=result.reasons,
                explain=result.explain,
                user_message=result.user_message,
            )
        )

    return PurchasePreviewResponse(
        personalization=personalization_ui,
        store_risks=store_risks,
        retrieved_memories=retrieved,
    )


# -------------------------
# Payment pipeline (authorize + verify)
# -------------------------

@app.post("/sessions/{session_id}/payment/authorize", response_model=PaymentAuthorizeResponse)
async def payment_authorize(
    session_id: str,
    payload: PaymentAuthorizeRequest,
    client: BackboardClient = Depends(get_backboard_client),
    conn=Depends(get_db_conn),
) -> PaymentAuthorizeResponse:
    session = _get_session_or_404(conn, session_id)

    card = db.get_card(conn, session_id=session_id, card_id=int(payload.card_id))
    if not card:
        raise HTTPException(status_code=404, detail=f"Card {payload.card_id} not found for session")

    retrieved = await client.query_memories(
        thread_id=session["thread_id"],
        assistant_id=session["assistant_id"],
        query="Return TP_PROFILE / TP_BASELINE / TP_TRUSTED_MERCHANT_* / TP_MERCHANT_FACTS for authorization.",
        top_k=80,
    )
    p = extract_personalization(retrieved)

    result = score_purchase(
        Purchase(
            merchant=payload.merchant,
            amount=float(payload.amount),
            currency=payload.currency,
            country=payload.country,
            dcc_offered=payload.dcc_offered,
            channel=payload.channel,
            item_description=payload.item_description,
            shipping_country=payload.shipping_country,
        ),
        personalization=p,
        trust_score=50,
    )

    if result.decision == "APPROVE":
        status = "APPROVED"
        challenge_id = None
    else:
        status = "CHALLENGE_REQUIRED"
        challenge_id = str(uuid.uuid4())
        db.create_challenge(
            conn,
            challenge_id=challenge_id,
            session_id=session_id,
            method=result.challenge_method,
            status="PENDING",
        )

    raw = {
        "card": {"id": card["id"], "network": card["network"], "last4": card["last4"], "nickname": card["nickname"]},
        "purchase": payload.model_dump(),
        "risk": {
            "decision": result.decision,
            "challenge_method": result.challenge_method,
            "risk_score": result.risk_score,
            "risk_level": result.risk_level,
            "tier": result.merchant_trust_tier,
            "reasons": result.reasons,
            "user_message": result.user_message,
            "explain": result.explain,
        },
        "status": status,
        "challenge_id": challenge_id,
    }

    db.insert_payment_attempt(
        conn,
        session_id=session_id,
        card_id=int(payload.card_id),
        merchant=payload.merchant,
        amount=float(payload.amount),
        currency=payload.currency,
        country=payload.country,
        channel=payload.channel,
        item_description=payload.item_description,
        dcc_offered=bool(payload.dcc_offered),
        decision=result.decision,
        challenge_method=result.challenge_method,
        risk_score=result.risk_score,
        status=status,
        challenge_id=challenge_id,
        raw_json=json.dumps(raw, default=str),
    )

    return PaymentAuthorizeResponse(
        status=status,
        decision=result.decision,
        challenge_method=result.challenge_method,
        risk_score=result.risk_score,
        risk_level=result.risk_level,
        merchant_trust_tier=result.merchant_trust_tier,
        reasons=result.reasons,
        explain=result.explain,
        user_message=result.user_message,
        challenge_id=challenge_id,
        card={"id": card["id"], "nickname": card["nickname"], "network": card["network"], "last4": card["last4"]},
        personalization_used=result.personalization_used,
        retrieved_memories=retrieved,
    )


@app.post("/sessions/{session_id}/payment/challenge/verify", response_model=ChallengeVerifyResponse)
async def payment_challenge_verify(
    session_id: str,
    payload: ChallengeVerifyRequest,
    conn=Depends(get_db_conn),
) -> ChallengeVerifyResponse:
    _ = _get_session_or_404(conn, session_id)

    ch = db.get_challenge(conn, session_id=session_id, challenge_id=payload.challenge_id)
    if not ch:
        raise HTTPException(status_code=404, detail="Challenge not found")

    action = payload.action.strip().upper()
    if action not in ("APPROVE", "DENY"):
        raise HTTPException(status_code=400, detail="action must be APPROVE or DENY")

    if action == "DENY":
        db.resolve_challenge(conn, challenge_id=payload.challenge_id, session_id=session_id, status="DENIED")
        return ChallengeVerifyResponse(
            status="DENIED",
            challenge_id=payload.challenge_id,
            method=ch["method"],
            message="User denied the challenge.",
        )

    db.resolve_challenge(conn, challenge_id=payload.challenge_id, session_id=session_id, status="COMPLETED")
    return ChallengeVerifyResponse(
        status="COMPLETED",
        challenge_id=payload.challenge_id,
        method=ch["method"],
        message="Challenge approved. Payment completed.",
    )
