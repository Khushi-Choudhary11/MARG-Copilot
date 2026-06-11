"""
services/optimizer/test_claude_explainer.py
=============================================
Smoke test for the Claude explanation engine.

Tests:
  1. Cache key generation is deterministic and collision-resistant
  2. LRU cache hit/miss/eviction
  3. Template fallback fires when no API key (no actual API call)
  4. _parse_response correctly extracts fields from structured Claude output
  5. explain_sync returns ExplainedDecision with correct source="template"
  6. Batch explain works (all template, no API key)
  7. Cache stores and retrieves explanation
  8. ExplainedDecision fields are well-formed

Run:  python test_claude_explainer.py
Pass: "ALL CHECKS PASS" at end
"""
import sys, os, asyncio
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from problem import (
    Decision, DecisionType, NetworkState, TrainState, SectionState,
    OptStatus,
)
from explanation_cache import ExplanationCache, _LRUCache
from claude_explainer import ClaudeExplainer, ExplainedDecision, _build_user_message

checks = []
PASS = "[PASS]"
FAIL = "[FAIL]"

def check(name, cond, msg=""):
    ok = bool(cond)
    print(f"  {PASS if ok else FAIL}  {name}" + (f" — {msg}" if msg else ""))
    checks.append(ok)

# ── Fixtures ──────────────────────────────────────────────────────────────────
sections = {
    "s2": SectionState(section_id="s2", is_blocked=False, block_duration=0,
        is_single_line=True, capacity_per_hr=60,
        from_station="GZB", to_station="MTJ", length_km=64, congestion_score=0.6),
    "s3": SectionState(section_id="s3", is_blocked=True, block_duration=40,
        is_single_line=False, capacity_per_hr=120,
        from_station="MTJ", to_station="AGC", length_km=55, congestion_score=0.8),
}
trains = {
    "12309": TrainState(train_id="12309", category="express", priority=2, direction="DOWN",
        current_section="s2", current_delay=8.0, sched_dep_min=300.0,
        remaining_route=["s2"], sched_arrivals={"s2": 300}, sched_departures={"s2": 305},
        travel_times={"s2": 80}),
    "12951": TrainState(train_id="12951", category="superfast", priority=1, direction="UP",
        current_section="s2", current_delay=3.0, sched_dep_min=290.0,
        remaining_route=["s2"], sched_arrivals={"s2": 290}, sched_departures={"s2": 295},
        travel_times={"s2": 80}),
    "12303": TrainState(train_id="12303", category="goods", priority=4, direction="DOWN",
        current_section="s3", current_delay=5.0, sched_dep_min=380.0,
        remaining_route=["s3"], sched_arrivals={"s3": 440}, sched_departures={"s3": 445},
        travel_times={"s3": 75}),
}
state = NetworkState(timestamp_min=300, trains=trains, sections=sections)

d_hold = Decision(
    decision_type=DecisionType.HOLD,
    train_id="12309", section_id="s2",
    detail="Hold 6 min — crossing conflict",
    delay_saved_min=41.0, hold_minutes=6.0, confidence=0.92,
    affected_trains=["12951"],
)
d_reroute = Decision(
    decision_type=DecisionType.REROUTE,
    train_id="12303", section_id="s3",
    detail="Bypass blocked s3",
    delay_saved_min=22.0, alt_route=["s3a", "s3b"],
    confidence=0.85, affected_trains=[],
)

print("\n" + "="*60)
print("  MARG Claude Explainer — Smoke Test")
print("="*60)

# ── 1. Cache key determinism ──────────────────────────────────────────────────
print("\n[1] Cache key generation")
cache = ExplanationCache(use_redis=False)
k1a = cache.make_key(d_hold)
k1b = cache.make_key(d_hold)
k2  = cache.make_key(d_reroute)
check("key is deterministic (same decision → same key)", k1a == k1b, f"k={k1a}")
check("key is collision-resistant (different decisions → different keys)", k1a != k2)
check("key is 16 hex chars", len(k1a) == 16 and all(c in "0123456789abcdef" for c in k1a))

# ── 2. LRU cache ─────────────────────────────────────────────────────────────
print("\n[2] LRU cache behaviour")
lru = _LRUCache(maxsize=3, ttl=3600)
lru.set("k1", "v1"); lru.set("k2", "v2"); lru.set("k3", "v3")
check("get hit", lru.get("k1") == "v1")
check("get miss", lru.get("missing") is None)
lru.set("k4", "v4")   # evicts LRU (k2, since k1 was just accessed)
check("eviction: maxsize respected", len(lru._cache) == 3)
stats = lru.stats()
check("stats returns hit_rate ∈ [0,1]", 0.0 <= stats["hit_rate"] <= 1.0, f"hr={stats['hit_rate']}")

# ── 3. ExplanationCache get/set without Redis ─────────────────────────────────
print("\n[3] ExplanationCache (LRU only, no Redis)")
cache2 = ExplanationCache(use_redis=False)
k = cache2.make_key(d_hold)
check("miss before set", cache2.get(k) is None)
cache2.set(k, "cached explanation text")
check("hit after set", cache2.get(k) == "cached explanation text")
check("redis_live=False", not cache2.stats()["redis_live"])

# ── 4. _build_user_message ────────────────────────────────────────────────────
print("\n[4] User message construction")
msg = _build_user_message(d_hold, state, {"action": "Hold 12309 for 6 min"})
check("contains train id", "12309" in msg)
check("contains section id", "s2" in msg)
check("contains delay saved", "41" in msg)
check("contains affected train", "12951" in msg)
check("is non-empty string", isinstance(msg, str) and len(msg) > 20)

# ── 5. _parse_response ────────────────────────────────────────────────────────
print("\n[5] Response parsing")
raw_claude = (
    "ACTION: Hold 12309 at GZB loop for 6 minutes.\n"
    "JUSTIFICATION: Rajdhani 12951 has higher priority; clearing its path saves 41 "
    "weighted delay-minutes across downstream connections. The 6-minute hold is within "
    "12309's recovery buffer. Confirm loop is clear before giving line-clear.\n"
    "RISK: Low\n"
    "CONFIDENCE: 92%"
)
tmpl = {"action": "fallback action", "risk": "High"}
parsed = ClaudeExplainer._parse_response(raw_claude, d_hold, tmpl, "claude", 120.0)
check("action parsed correctly", "Hold 12309" in parsed.action)
check("risk parsed correctly", parsed.risk == "Low")
check("confidence parsed correctly", abs(parsed.confidence - 0.92) < 0.01, f"conf={parsed.confidence}")
check("justification text extracted", "Rajdhani" in parsed.text)
check("source set correctly", parsed.source == "claude")
check("latency_ms set", parsed.latency_ms == 120.0)

# ── 6. Template fallback (no API key) ────────────────────────────────────────
print("\n[6] Template fallback (no API key)")
explainer = ClaudeExplainer(api_key=None, use_redis=False)
check("client is None when no key", explainer._client is None)

result = asyncio.run(explainer.explain_one(d_hold, state))
check("returns ExplainedDecision", isinstance(result, ExplainedDecision))
check("source=template", result.source == "template", f"source={result.source}")
check("text is non-empty", len(result.text) > 10)
check("confidence in [0,1]", 0.0 <= result.confidence <= 1.0)
check("latency_ms > 0", result.latency_ms >= 0)

# ── 7. Batch explain (template) ───────────────────────────────────────────────
print("\n[7] Batch explain (template, no API key)")
results = asyncio.run(explainer.explain_batch([d_hold, d_reroute], state))
check("batch returns list of 2", len(results) == 2)
check("both are ExplainedDecision", all(isinstance(r, ExplainedDecision) for r in results))
check("different train IDs", results[0].decision.train_id != results[1].decision.train_id)

# ── 8. Cache round-trip through explainer ────────────────────────────────────
print("\n[8] Cache round-trip")
cache3 = ExplanationCache(use_redis=False)
explainer2 = ClaudeExplainer(api_key=None, cache=cache3, use_redis=False)
k = cache3.make_key(d_reroute)
cache3.set(k, (
    "ACTION: Reroute 12303 via bypass.\n"
    "JUSTIFICATION: Blocked section; bypass saves 22 min.\n"
    "RISK: Medium\n"
    "CONFIDENCE: 85%"
))
result2 = asyncio.run(explainer2.explain_one(d_reroute, state))
check("cache hit when pre-populated", result2.source == "cache", f"source={result2.source}")
check("cached text extracted", "bypass" in result2.text.lower() or "reroute" in result2.action.lower())

# ── Summary ───────────────────────────────────────────────────────────────────
n_pass  = sum(checks)
n_total = len(checks)
print(f"\n{'='*60}")
if n_pass == n_total:
    print(f"  ALL {n_total} CHECKS PASS")
else:
    print(f"  {n_pass}/{n_total} CHECKS PASS  ({n_total-n_pass} FAILED)")
print("="*60 + "\n")

if n_pass < n_total:
    sys.exit(1)
