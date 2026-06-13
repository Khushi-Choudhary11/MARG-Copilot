"""
AI Controller Assistant service.

If ANTHROPIC_API_KEY is configured, calls the Claude API for natural-language
explanations/answers grounded in the current twin snapshot + recommendations.
Otherwise returns a deterministic template-based response (source="template")
so the feature still works end-to-end - the frontend additionally offers a
puter.js client-side fallback when this backend has no key configured at all.
"""
from __future__ import annotations

import logging

import httpx

from app.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL

logger = logging.getLogger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

SYSTEM_PROMPT = (
    "You are the AI controller assistant for the NDLS<->CNB railway digital twin. "
    "You explain delay predictions and recommend section-control actions (holds, "
    "loop-line assignments, priority passes) in plain, concise language for a "
    "train traffic controller. Keep responses under 120 words."
)


def is_configured() -> bool:
    return bool(ANTHROPIC_API_KEY)


async def ask(question: str, context: dict) -> dict:
    if not ANTHROPIC_API_KEY:
        return {"answer": _template_answer(question, context), "source": "template"}

    user_content = (
        f"Context (JSON): {context}\n\nController question: {question}"
    )
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                ANTHROPIC_URL,
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": ANTHROPIC_MODEL,
                    "max_tokens": 400,
                    "system": SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": user_content}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            text = "".join(block.get("text", "") for block in data.get("content", []))
            return {"answer": text.strip(), "source": "claude"}
    except Exception:
        logger.exception("Claude API call failed, using template fallback")
        return {"answer": _template_answer(question, context), "source": "template"}


def _template_answer(question: str, context: dict) -> str:
    recs = context.get("recommendations", [])
    if not recs:
        return (
            "All trains on the NDLS<->CNB corridor are currently within normal "
            "delay tolerances. No controller intervention is recommended at this time."
        )
    top = recs[0]
    return (
        f"Highest-priority issue: train {top.get('train_number')} "
        f"({top.get('train_name', 'unknown')}) is predicted to arrive at "
        f"{top.get('station_code')} with a delay of ~{top.get('predicted_delay', 0):.0f} "
        f"minutes (severity: {top.get('severity')}). Suggested action: "
        f"{top.get('suggested_action')} "
        f"There are {len(recs)} active recommendation(s) in total. "
        f"(Note: this is a template response - configure ANTHROPIC_API_KEY for "
        f"AI-generated explanations.)"
    )
