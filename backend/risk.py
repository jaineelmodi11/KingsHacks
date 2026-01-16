from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class Personalization:
    current_country: Optional[str] = None
    trip_countries: List[str] = field(default_factory=list)
    sms_available: Optional[bool] = None
    preferred_verification: Optional[str] = None  # PASSKEY | SMS
    daily_budget: Optional[float] = None

    typical_amount_min: Optional[float] = None
    typical_amount_max: Optional[float] = None

    trusted_high: Set[str] = field(default_factory=set)
    trusted_med: Set[str] = field(default_factory=set)
    trusted_low: Set[str] = field(default_factory=set)

    merchant_facts: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # merchant_norm -> facts


def _safe_json_loads(s: str) -> Optional[Dict[str, Any]]:
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _norm_merchant(name: str) -> str:
    return (name or "").strip().lower()


def extract_personalization(retrieved_memories: List[Dict[str, Any]]) -> Personalization:
    p = Personalization()

    for m in (retrieved_memories or []):
        mem = (m.get("memory") or "").strip()
        if not mem:
            continue

        if mem.startswith("TP_PROFILE"):
            payload = mem[len("TP_PROFILE"):].strip()
            obj = _safe_json_loads(payload)
            if obj:
                if obj.get("current_country"):
                    p.current_country = str(obj["current_country"]).upper().strip()
                if isinstance(obj.get("trip_countries"), list):
                    p.trip_countries = [str(x).upper().strip() for x in obj["trip_countries"] if str(x).strip()]
                if obj.get("sms_available") is not None:
                    p.sms_available = bool(obj["sms_available"])
                if obj.get("preferred_verification"):
                    p.preferred_verification = str(obj["preferred_verification"]).upper().strip()
                if obj.get("daily_budget") is not None:
                    try:
                        p.daily_budget = float(obj["daily_budget"])
                    except Exception:
                        pass

        elif mem.startswith("TP_BASELINE"):
            payload = mem[len("TP_BASELINE"):].strip()
            obj = _safe_json_loads(payload)
            if obj:
                if obj.get("typical_amount_min") is not None:
                    try:
                        p.typical_amount_min = float(obj["typical_amount_min"])
                    except Exception:
                        pass
                if obj.get("typical_amount_max") is not None:
                    try:
                        p.typical_amount_max = float(obj["typical_amount_max"])
                    except Exception:
                        pass

        elif mem.startswith("TP_TRUSTED_MERCHANT_HIGH"):
            merchant = mem[len("TP_TRUSTED_MERCHANT_HIGH"):].strip()
            if merchant:
                p.trusted_high.add(_norm_merchant(merchant))

        elif mem.startswith("TP_TRUSTED_MERCHANT_MED"):
            merchant = mem[len("TP_TRUSTED_MERCHANT_MED"):].strip()
            if merchant:
                p.trusted_med.add(_norm_merchant(merchant))

        elif mem.startswith("TP_TRUSTED_MERCHANT_LOW"):
            merchant = mem[len("TP_TRUSTED_MERCHANT_LOW"):].strip()
            if merchant:
                p.trusted_low.add(_norm_merchant(merchant))

        elif mem.startswith("TP_TRUSTED_MERCHANT"):
            # Back-compat: treat as HIGH
            merchant = mem[len("TP_TRUSTED_MERCHANT"):].strip()
            if merchant:
                p.trusted_high.add(_norm_merchant(merchant))

        elif mem.startswith("TP_MERCHANT_FACTS"):
            payload = mem[len("TP_MERCHANT_FACTS"):].strip()
            obj = _safe_json_loads(payload)
            if obj and obj.get("merchant"):
                key = _norm_merchant(str(obj["merchant"]))
                p.merchant_facts[key] = obj

    return p


@dataclass
class Purchase:
    merchant: str
    amount: float
    currency: str
    country: str
    dcc_offered: bool = False
    channel: str = "CNP"  # CNP (online) | CARD_PRESENT
    item_description: Optional[str] = None
    shipping_country: Optional[str] = None


@dataclass
class RiskResult:
    decision: str                 # APPROVE | CHALLENGE
    challenge_method: str         # NONE | PASSKEY
    risk_score: int               # 0..100
    risk_level: str               # LOW | MEDIUM | HIGH
    merchant_trust_tier: str      # HIGH | MEDIUM | LOW
    reasons: List[str]
    explain: str
    user_message: str
    personalization_used: Dict[str, Any]


def _clamp_int(x: float, lo: int = 0, hi: int = 100) -> int:
    return int(max(lo, min(hi, round(x))))


def _risk_level(score: int) -> str:
    if score >= 60:
        return "HIGH"
    if score >= 30:
        return "MEDIUM"
    return "LOW"


def _merchant_tier(merchant_norm: str, p: Personalization) -> str:
    if merchant_norm in p.trusted_high:
        return "HIGH"
    if merchant_norm in p.trusted_med:
        return "MEDIUM"
    if merchant_norm in p.trusted_low:
        return "LOW"
    return "LOW"


def _looks_like_gift_card(item_desc: Optional[str]) -> bool:
    if not item_desc:
        return False
    s = item_desc.lower()
    return any(k in s for k in ["gift card", "giftcard", "voucher", "steam card", "apple gift", "google play"])


def score_purchase(purchase: Purchase, personalization: Personalization, trust_score: int = 50) -> RiskResult:
    reasons: List[str] = []
    score = 0.0

    merchant_norm = _norm_merchant(purchase.merchant)
    purchase_country = (purchase.country or "").strip().upper()
    tier = _merchant_tier(merchant_norm, personalization)

    facts = personalization.merchant_facts.get(merchant_norm, {})
    category = (facts.get("category") or "").strip().upper()
    restricted = bool(facts.get("restricted"))

    # Channel risk (CNP is the big bucket for card fraud value; we reflect that as a risk prior)
    channel = (purchase.channel or "CNP").strip().upper()
    if channel == "CNP":
        score += 12
        reasons.append("Online (card-not-present) purchase")

    # Country mismatch
    if personalization.current_country and purchase_country and purchase_country != personalization.current_country:
        score += 30
        reasons.append("Country mismatch vs travel mode")

    # Trip country reduces risk
    if personalization.trip_countries and purchase_country in personalization.trip_countries:
        score -= 10
        reasons.append("Purchase is in your declared trip country")

    # Shipping mismatch (light realism)
    if purchase.shipping_country and personalization.current_country:
        if purchase.shipping_country.strip().upper() != personalization.current_country:
            score += 12
            reasons.append("Shipping country differs from your current travel country")

    # Category hint
    if category == "GROCERY":
        score -= 5
        reasons.append("Grocery purchase (low fraud profile)")
    elif category == "TRANSIT":
        score -= 3
        reasons.append("Transit purchase (common while traveling)")
    elif category == "APPAREL":
        score += 2
        reasons.append("Retail apparel purchase")
    elif category == "FURNITURE":
        score += 8
        reasons.append("Large-ticket retail category")
    elif category == "ALCOHOL":
        score += 5
        reasons.append("Restricted category purchase")

    # Item-level “high scam” prior (gift cards)
    gift_card_like = _looks_like_gift_card(purchase.item_description)
    if gift_card_like:
        score += 40
        reasons.append("Item resembles a gift card / voucher (high scam risk)")

    # Amount vs baseline
    if personalization.typical_amount_max is not None:
        if purchase.amount > 2.0 * personalization.typical_amount_max:
            score += 25
            reasons.append("Amount is much higher than your typical spending")
        elif purchase.amount > 1.2 * personalization.typical_amount_max:
            score += 10
            reasons.append("Amount is above your typical range")

    # DCC offered
    if purchase.dcc_offered:
        score += 5
        reasons.append("Merchant offered DCC (extra fee risk)")

    # Trust tier influence
    if tier == "HIGH":
        score -= 25
        reasons.append("High-trust merchant")
    elif tier == "MEDIUM":
        score += 5
        reasons.append("Medium-trust merchant")
    else:
        score += 15
        reasons.append("Low/unknown merchant")

    # Trust score adjustment
    score -= (trust_score - 50) * 0.4

    risk_score = _clamp_int(score)
    risk_level = _risk_level(risk_score)

    # YOUR POLICY:
    # - HIGH trust: no passkey (approve), except restricted/giftcard-like
    # - MEDIUM: passkey
    # - LOW: passkey
    if restricted or gift_card_like:
        decision = "CHALLENGE"
        challenge_method = "PASSKEY"
        user_message = "Quick passkey approval required for this type of purchase while traveling."
    elif tier == "HIGH":
        decision = "APPROVE"
        challenge_method = "NONE"
        user_message = "Trusted merchant — approved with no extra steps."
    elif tier == "MEDIUM":
        decision = "CHALLENGE"
        challenge_method = "PASSKEY"
        user_message = "Quick passkey check to confirm it’s you."
    else:
        decision = "CHALLENGE"
        challenge_method = "PASSKEY"
        user_message = "Unrecognized merchant — approve with passkey or decline."

    top_reasons = reasons[:3]
    explain = (
        f"Risk score {risk_score}/100 ({risk_level}). "
        + ("Approved. " if decision == "APPROVE" else "Verification required. ")
        + "Key factors: "
        + "; ".join(top_reasons)
        + "."
    )

    personalization_used = {
        "current_country": personalization.current_country,
        "trip_countries": personalization.trip_countries,
        "sms_available": personalization.sms_available,
        "preferred_verification": personalization.preferred_verification,
        "typical_amount_max": personalization.typical_amount_max,
        "trusted_high_count": len(personalization.trusted_high),
        "trusted_med_count": len(personalization.trusted_med),
        "trusted_low_count": len(personalization.trusted_low),
    }

    return RiskResult(
        decision=decision,
        challenge_method=challenge_method,
        risk_score=risk_score,
        risk_level=risk_level,
        merchant_trust_tier=tier,
        reasons=top_reasons,
        explain=explain,
        user_message=user_message,
        personalization_used=personalization_used,
    )
