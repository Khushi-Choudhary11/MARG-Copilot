"""
services/optimizer/explanation_cache.py
========================================
Two-tier explanation cache:
  Tier 1 — in-process LRU (fast, zero latency, survives within one process).
  Tier 2 — Redis (optional; shared across replicas; persists across restarts).

Cache key is a deterministic hash of the decision's stable attributes:
  decision_type, train_id, section_id, round(delay_saved, 0), affected_trains

TTL defaults to 3600 s (1 hour) — long enough to be useful within a
controller shift, short enough that a changed network state won't serve
stale explanations.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import OrderedDict
from typing import Optional

log = logging.getLogger(__name__)

# ── Tier-1: in-process LRU ────────────────────────────────────────────────────

class _LRUCache:
    """Thread-unsafe LRU with TTL — suitable for single-threaded FastAPI worker."""

    def __init__(self, maxsize: int = 256, ttl: int = 3600):
        self._cache:   OrderedDict[str, tuple] = OrderedDict()  # key → (value, expires_at)
        self.maxsize   = maxsize
        self.ttl       = ttl
        self.hits      = 0
        self.misses    = 0

    def get(self, key: str) -> Optional[str]:
        if key not in self._cache:
            self.misses += 1
            return None
        value, exp = self._cache[key]
        if time.time() > exp:
            del self._cache[key]
            self.misses += 1
            return None
        self._cache.move_to_end(key)          # mark as recently used
        self.hits += 1
        return value

    def set(self, key: str, value: str) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = (value, time.time() + self.ttl)
        if len(self._cache) > self.maxsize:
            self._cache.popitem(last=False)   # evict LRU

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {
            "size":       len(self._cache),
            "maxsize":    self.maxsize,
            "hits":       self.hits,
            "misses":     self.misses,
            "hit_rate":   round(self.hits / total, 3) if total else 0.0,
        }

    def clear(self) -> None:
        self._cache.clear()
        self.hits = self.misses = 0


# ── Tier-2: Redis (optional) ───────────────────────────────────────────────────

class _RedisCache:
    """Thin wrapper around redis-py; gracefully no-ops when Redis is unavailable."""

    def __init__(self, url: str = "redis://localhost:6379/0", ttl: int = 3600):
        self.ttl = ttl
        self._client = None
        try:
            import redis
            self._client = redis.from_url(url, socket_connect_timeout=1, decode_responses=True)
            self._client.ping()
            log.info("Redis cache connected: %s", url)
        except Exception as exc:
            log.warning("Redis unavailable (%s) — falling back to LRU-only cache.", exc)
            self._client = None

    @property
    def available(self) -> bool:
        return self._client is not None

    def get(self, key: str) -> Optional[str]:
        if not self._client:
            return None
        try:
            return self._client.get(f"marg:expl:{key}")
        except Exception as exc:
            log.debug("Redis get failed: %s", exc)
            return None

    def set(self, key: str, value: str) -> None:
        if not self._client:
            return
        try:
            self._client.setex(f"marg:expl:{key}", self.ttl, value)
        except Exception as exc:
            log.debug("Redis set failed: %s", exc)


# ── Public ExplanationCache ───────────────────────────────────────────────────

class ExplanationCache:
    """
    Two-tier cache.  Call pattern:

        cache = ExplanationCache(redis_url="redis://localhost:6379")
        key   = cache.make_key(decision)
        hit   = cache.get(key)
        if hit is None:
            result = _call_claude(...)
            cache.set(key, result)
    """

    def __init__(
        self,
        lru_maxsize: int  = 256,
        ttl:         int  = 3600,
        redis_url:   str  = "redis://localhost:6379/0",
        use_redis:   bool = True,
    ):
        self._lru   = _LRUCache(maxsize=lru_maxsize, ttl=ttl)
        self._redis = _RedisCache(url=redis_url, ttl=ttl) if use_redis else _RedisCache.__new__(_RedisCache)
        if not use_redis:
            self._redis._client = None

    # ── Key construction ─────────────────────────────────────────────────

    @staticmethod
    def make_key(decision) -> str:
        """
        Stable hash from decision fields that govern the explanation content.
        Rounds delay_saved to nearest minute so near-identical decisions reuse
        the same cached explanation.
        """
        payload = {
            "type":     decision.decision_type.name,
            "train":    decision.train_id,
            "section":  decision.section_id,
            "saved":    round(decision.delay_saved_min),
            "affected": sorted(decision.affected_trains or []),
            "alt":      bool(decision.alt_route),
        }
        raw = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    # ── Get / Set ────────────────────────────────────────────────────────

    def get(self, key: str) -> Optional[str]:
        hit = self._lru.get(key)
        if hit:
            return hit
        hit = self._redis.get(key)
        if hit:
            self._lru.set(key, hit)   # promote to L1
        return hit

    def set(self, key: str, value: str) -> None:
        self._lru.set(key, value)
        self._redis.set(key, value)

    def stats(self) -> dict:
        return {
            "lru":         self._lru.stats(),
            "redis_live":  self._redis.available,
        }
