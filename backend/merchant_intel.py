import json
import os
from typing import Any, Dict, Optional

import httpx


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.2")  # pick what you want


async def classify_merchant_and_item(
    *,
    merchant: str,
    country: str,
    item_description: Optional[str],
) -> Optional[Dict[str, Any]]:
    """
    Returns dict like:
      {"merchant":"...", "category":"GROCERY|TRANSIT|APPAREL|FURNITURE|ALCOHOL|OTHER",
       "restricted": bool, "home_country":"SE", "notes":"...", "confidence": 0..1}

    If OPENAI_API_KEY not set, returns None.
    """
    if not OPENAI_API_KEY:
        return None

    prompt = f"""
You are a fraud-risk enrichment assistant for a DEMO issuer.
Given a merchant name and an item description, classify the merchant category and whether it's restricted.

Return ONLY valid JSON with keys:
merchant, category, restricted, home_country, confidence, notes

Merchant: {merchant}
Country: {country}
Item: {item_description or ""}

Category must be one of: GROCERY, TRANSIT, APPAREL, FURNITURE, ALCOHOL, OTHER
restricted: true if alcohol/age-restricted/regulatory purchase type
confidence: float 0..1
""".strip()

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENAI_MODEL,
                "input": prompt,
            },
        )

    resp.raise_for_status()
    data = resp.json()

    # Try common response shapes
    text = None
    if isinstance(data, dict):
        text = data.get("output_text")
        if not text and isinstance(data.get("output"), list):
            # best-effort extraction
            for item in data["output"]:
                if isinstance(item, dict):
                    content = item.get("content")
                    if isinstance(content, list):
                        for c in content:
                            if isinstance(c, dict) and c.get("type") == "output_text":
                                text = c.get("text")
                                break
                if text:
                    break

    if not text:
        return None

    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and obj.get("merchant") and obj.get("category"):
            return obj
    except Exception:
        return None

    return None
