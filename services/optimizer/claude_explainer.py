"""
services/optimizer/claude_explainer.py
========================================
Claude-powered recommendation explanation engine.

Takes an optimizer Decision + NetworkState and returns a controller-facing
plain-English justification that is richer than the template-based fallback
in explainer.py.

Architecture
------------
  ClaudeExplainer
    ├── _build_prompt(decision, state, template_ctx)
    │       Prompt engineering: system persona + few-shot + chain-of-thought
    ├── _call_api(prompt) → str
    │       Anthropic SDK call, async, with timeout + retry
    ├── ExplanationCache
    │       Tier-1 LRU + Tier-2 Redis; key = SHA-256 of stable decision attrs
    └── explain_one(decision, state) → ExplainedDecision
            Public API: cache → Claude → fallback template

Failure handling
----------------
  API timeout (>5 s)    → immediate fallback, log warning
  Rate limit (429)      → exponential backoff × 3, then fallback
  Any other exception   → fallback, log error (never raise to caller)
  Empty / junk response → fallback

Usage
-----
    explainer = ClaudeExplainer(api_key="sk-ant-...")
    result    = await explainer.explain_one(decision, state)
    print(result.text)          # full NL justification
    print(result.source)        # "claude" | "template" | "cache"
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

# ── Try importing Anthropic ───────────────────────────────────────────────────
try:
    import anthropic as _anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False
    log.warning("anthropic package not installed — Claude explainer will use templates only.")

# ── Local imports ─────────────────────────────────────────────────────────────
import sys, os as _os
sys.path.insert(0, _os.path.dirname(__file__))

from problem import Decision, DecisionType, NetworkState, PRIORITY_WEIGHT
from explainer import explain_decisions       # template fallback
from explanation_cache import ExplanationCache


# ═════════════════════════════════════════════════════════════════════════════
# Result dataclass
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class ExplainedDecision:
    """One fully-explained recommendation ready for the control tower UI."""
    decision:    Decision
    text:        str                    # one-paragraph controller-facing justification
    action:      str                    # short action label ("HOLD 12309 at ALJN 6 min")
    risk:        str                    # "Low" | "Medium" | "High"
    confidence:  float                  # 0–1
    source:      str = "claude"         # "claude" | "template" | "cache"
    latency_ms:  float = 0.0


# ═════════════════════════════════════════════════════════════════════════════
# Prompt engineering
# ═════════════════════════════════════════════════════════════════════════════

_SYSTEM_PROMPT = """\
You are MARG-Explain, an expert railway operations advisor embedded in the \
MARG AI co-pilot system for Indian Railways section controllers.

Your job: given an optimizer recommendation, produce a concise, confident \
justification that a section controller can read in under 10 seconds and \
immediately act on. The controller is experienced but time-pressured — speak \
like a trusted colleague, not a textbook.

Rules:
1. Lead with the concrete action and its PRIMARY benefit (delay saved, cascade prevented).
2. State the mechanism in one sentence (why this action achieves the benefit).
3. Flag any risk or thing to verify in one sentence.
4. End with confidence level: Low / Medium / High.
5. Total length: 3-5 sentences. No bullet points. No jargon undefined in IR operations.
6. Numbers are in minutes unless otherwise specified.
7. Train names use their number (e.g., "12309") not generic "the train".
8. Never say "I recommend" — the controller is deciding, you are informing.

Output format (plain text, no markdown):
ACTION: <one-line summary of what to do>
JUSTIFICATION: <3-5 sentence paragraph>
RISK: <Low | Medium | High>
CONFIDENCE: <0-100>%
"""

_FEW_SHOT = [
    {
        "role": "user",
        "content": (
            "Decision: HOLD 12309 at Aligarh loop for 6 minutes.\n"
            "Context: 12309 (Express, priority 2) is 8 min late. Rajdhani 12951 (Superfast, "
            "priority 1) is 3 min late approaching the same single-line section from opposite "
            "direction. Holding 12309 clears the loop for 12951. Downstream: 12309 connects "
            "to 3 trains at Kanpur; 12951 connects to 5. Delay saved: 41 weighted-min."
        ),
    },
    {
        "role": "assistant",
        "content": (
            "ACTION: Hold 12309 at Aligarh loop for 6 minutes, clearing section for Rajdhani 12951.\n"
            "JUSTIFICATION: Rajdhani 12951 holds higher priority and connects to 5 downstream "
            "services at Kanpur; letting it pass first saves 41 cumulative delay-minutes across "
            "the network versus holding 12951. The 6-minute hold keeps 12309 within its recovery "
            "buffer — it can make up time on the open stretch to Kanpur. Confirm the Aligarh loop "
            "is clear of any shunting movement before giving line-clear to 12951.\n"
            "RISK: Low\n"
            "CONFIDENCE: 92%"
        ),
    },
    {
        "role": "user",
        "content": (
            "Decision: REROUTE 12303 (Goods) via MTJ-ALW-AGC bypass, skipping blocked section MTJ-AGC.\n"
            "Context: Track fault at km 142 blocking MTJ-AGC section for estimated 40 min. "
            "Alternative route via Achhnera adds 18 min travel time but avoids the blockage. "
            "12303 has no time-sensitive connection. Delay saved vs. waiting: 22 min."
        ),
    },
    {
        "role": "assistant",
        "content": (
            "ACTION: Reroute 12303 via MTJ → ALW → AGC, bypassing the blocked MTJ-AGC section.\n"
            "JUSTIFICATION: The km 142 track fault gives an estimated 40-minute blockage; waiting "
            "costs 40 minutes while the bypass adds only 18, saving 22 minutes net. 12303 carries "
            "no time-critical connections at the destination, making it the lowest-cost train to "
            "absorb the detour. Issue revised line-clear for the ALW route and notify AGC station "
            "master of the updated arrival estimate.\n"
            "RISK: Medium\n"
            "CONFIDENCE: 85%"
        ),
    },
]


def _build_user_message(
    decision: Decision,
    state:    NetworkState,
    template: dict,
) -> str:
    """Serialize decision + relevant network context into the user turn."""
    train   = state.trains.get(decision.train_id)
    sec     = state.sections.get(decision.section_id)
    t_cat   = train.category.capitalize() if train else "Unknown"
    t_pri   = PRIORITY_WEIGHT.get(train.category, 1) if train else 1
    t_delay = train.current_delay if train else 0.0

    affected_desc = ""
    if decision.affected_trains:
        parts = []
        for tid in decision.affected_trains[:3]:
            t2 = state.trains.get(tid)
            if t2:
                parts.append(f"{tid} ({t2.category.capitalize()}, {t2.current_delay:.0f} min late)")
            else:
                parts.append(tid)
        affected_desc = "Affected trains: " + "; ".join(parts) + ". "

    reroute_desc = ""
    if decision.alt_route:
        reroute_desc = f"Alternative route: {' → '.join(decision.alt_route)}. "

    block_desc = ""
    if sec and sec.is_blocked:
        block_desc = f"Section {decision.section_id} is blocked (est. {sec.block_duration:.0f} min remaining). "

    single_line = ""
    if sec and sec.is_single_line:
        single_line = f"Section {decision.section_id} is single-line (one direction at a time). "

    lines = [
        f"Decision: {decision.decision_type.name} — {template.get('action', '')}",
        f"Train: {decision.train_id} ({t_cat}, priority weight {t_pri}, "
        f"currently {t_delay:.0f} min late).",
        f"Section: {decision.section_id}.",
        block_desc + single_line + affected_desc + reroute_desc,
        f"Estimated delay saved: {decision.delay_saved_min:.1f} weighted-minutes.",
        f"Current network time: {state.timestamp_min:.0f} min from midnight.",
    ]
    return "\n".join(l for l in lines if l.strip())


# ═════════════════════════════════════════════════════════════════════════════
# ClaudeExplainer
# ═════════════════════════════════════════════════════════════════════════════

class ClaudeExplainer:
    """
    Parameters
    ----------
    api_key      : Anthropic API key. Defaults to ANTHROPIC_API_KEY env var.
    model        : Claude model string. Default: claude-haiku-4-5-20251001 (fast + cheap).
    timeout_sec  : Per-call timeout. Falls back to template on breach.
    max_retries  : Retry count on 429 / 529 rate-limit responses.
    cache        : ExplanationCache instance. Pass None to disable caching.
    """

    _DEFAULT_MODEL = "claude-haiku-4-5-20251001"

    def __init__(
        self,
        api_key:     Optional[str] = None,
        model:       str  = _DEFAULT_MODEL,
        timeout_sec: float = 8.0,
        max_retries: int   = 3,
        cache:       Optional[ExplanationCache] = None,
        use_redis:   bool  = False,
    ):
        self.model       = model
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries
        self.cache       = cache or ExplanationCache(use_redis=use_redis)

        self._client: Optional[object] = None
        if _ANTHROPIC_AVAILABLE:
            key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
            if key:
                self._client = _anthropic.AsyncAnthropic(api_key=key)
            else:
                log.warning(
                    "ANTHROPIC_API_KEY not set — ClaudeExplainer will use templates only."
                )

    # ── Public API ────────────────────────────────────────────────────────────

    async def explain_one(
        self,
        decision: Decision,
        state:    NetworkState,
    ) -> ExplainedDecision:
        """
        Explain one decision.  Returns ExplainedDecision with source="claude"|"cache"|"template".
        Never raises — falls back to template on any error.
        """
        t0 = time.monotonic()

        # 1. Get template context (always computed — used as fallback + Claude context)
        from problem import OptResult, OptStatus
        stub = OptResult(
            status=OptStatus.OPTIMAL, decisions=[decision],
            objective_value=0, baseline_delay=0,
            delay_saved=decision.delay_saved_min,
            solve_time_sec=0, horizon_min=state.horizon_min,
            n_trains=len(state.trains), n_conflicts=0,
        )
        templates = explain_decisions(stub, state)
        tmpl = templates[0] if templates else {}

        # 2. Check cache
        key = self.cache.make_key(decision)
        cached = self.cache.get(key)
        if cached:
            return self._parse_response(
                cached, decision, tmpl,
                source="cache",
                latency_ms=(time.monotonic() - t0) * 1000,
            )

        # 3. Try Claude API
        if self._client:
            try:
                raw = await asyncio.wait_for(
                    self._call_api_with_retry(decision, state, tmpl),
                    timeout=self.timeout_sec,
                )
                self.cache.set(key, raw)
                return self._parse_response(
                    raw, decision, tmpl,
                    source="claude",
                    latency_ms=(time.monotonic() - t0) * 1000,
                )
            except asyncio.TimeoutError:
                log.warning("ClaudeExplainer: timeout for %s/%s — using template.",
                            decision.train_id, decision.section_id)
            except Exception as exc:
                log.error("ClaudeExplainer: API error (%s) — using template.", exc)

        # 4. Template fallback
        return self._template_fallback(decision, tmpl, t0)

    async def explain_batch(
        self,
        decisions: List[Decision],
        state:     NetworkState,
        max_concurrent: int = 4,
    ) -> List[ExplainedDecision]:
        """Explain multiple decisions concurrently (bounded by max_concurrent)."""
        sem = asyncio.Semaphore(max_concurrent)

        async def _bounded(d: Decision) -> ExplainedDecision:
            async with sem:
                return await self.explain_one(d, state)

        return await asyncio.gather(*[_bounded(d) for d in decisions])

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _call_api_with_retry(
        self,
        decision: Decision,
        state:    NetworkState,
        tmpl:     dict,
    ) -> str:
        """Call Claude API with exponential backoff on rate-limit errors."""
        user_msg = _build_user_message(decision, state, tmpl)
        messages = _FEW_SHOT + [{"role": "user", "content": user_msg}]

        delay = 1.0
        for attempt in range(self.max_retries):
            try:
                resp = await self._client.messages.create(
                    model=self.model,
                    max_tokens=300,
                    system=_SYSTEM_PROMPT,
                    messages=messages,
                )
                return resp.content[0].text.strip()
            except Exception as exc:
                # Rate-limit: 429 or 529
                is_rate = "429" in str(exc) or "529" in str(exc) or "rate" in str(exc).lower()
                if is_rate and attempt < self.max_retries - 1:
                    log.warning("Rate limit hit — retrying in %.1fs (attempt %d/%d)",
                                delay, attempt + 1, self.max_retries)
                    await asyncio.sleep(delay)
                    delay *= 2
                else:
                    raise

    @staticmethod
    def _parse_response(
        raw:     str,
        decision: Decision,
        tmpl:    dict,
        source:  str,
        latency_ms: float,
    ) -> ExplainedDecision:
        """Parse structured Claude output into ExplainedDecision."""
        action   = tmpl.get("action", f"{decision.decision_type.name} {decision.train_id}")
        risk     = tmpl.get("risk", "Medium")
        conf     = decision.confidence
        text     = raw

        for line in raw.splitlines():
            lup = line.upper()
            if lup.startswith("ACTION:"):
                action = line.split(":", 1)[1].strip()
            elif lup.startswith("RISK:"):
                risk = line.split(":", 1)[1].strip()
            elif lup.startswith("CONFIDENCE:"):
                try:
                    conf = float(line.split(":", 1)[1].strip().replace("%", "")) / 100
                except ValueError:
                    pass
            elif lup.startswith("JUSTIFICATION:"):
                text = line.split(":", 1)[1].strip()

        return ExplainedDecision(
            decision   = decision,
            text       = text,
            action     = action,
            risk       = risk,
            confidence = conf,
            source     = source,
            latency_ms = latency_ms,
        )

    @staticmethod
    def _template_fallback(
        decision: Decision,
        tmpl:     dict,
        t0:       float,
    ) -> ExplainedDecision:
        text = (
            tmpl.get("reason", "") + "  " +
            tmpl.get("impact", "") + "  " +
            tmpl.get("risk", "")
        ).strip()
        return ExplainedDecision(
            decision   = decision,
            text       = text or f"Optimizer recommends {decision.decision_type.name} for {decision.train_id}.",
            action     = tmpl.get("action", ""),
            risk       = tmpl.get("risk", "Medium"),
            confidence = decision.confidence,
            source     = "template",
            latency_ms = (time.monotonic() - t0) * 1000,
        )


# ═════════════════════════════════════════════════════════════════════════════
# Convenience sync wrapper (for non-async callers / tests)
# ═════════════════════════════════════════════════════════════════════════════

def explain_sync(
    decision:  Decision,
    state:     NetworkState,
    api_key:   Optional[str] = None,
    **kwargs,
) -> ExplainedDecision:
    """Synchronous wrapper around ClaudeExplainer.explain_one."""
    explainer = ClaudeExplainer(api_key=api_key, **kwargs)
    return asyncio.run(explainer.explain_one(decision, state))


def explain_batch_sync(
    decisions: List[Decision],
    state:     NetworkState,
    api_key:   Optional[str] = None,
    **kwargs,
) -> List[ExplainedDecision]:
    """Synchronous wrapper around ClaudeExplainer.explain_batch."""
    explainer = ClaudeExplainer(api_key=api_key, **kwargs)
    return asyncio.run(explainer.explain_batch(decisions, state))
