"""
backend/smoke_test.py
=====================
Integration smoke test — 22 checks covering all API endpoints.
Run from the backend/ directory:

    python smoke_test.py

The server must be running on localhost:8000 before you run this.
    uvicorn main:app --port 8000 --reload
"""
from __future__ import annotations

import sys
import time
import json
import http.client
import urllib.parse
from typing import Any

HOST = "localhost"
PORT = 8000

OK = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"

passed = 0
failed = 0


def req(method: str, path: str, body: dict | None = None,
        token: str | None = None,
        form: bool = False) -> tuple[int, Any]:
    conn = http.client.HTTPConnection(HOST, PORT, timeout=10)
    if form:
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        payload = urllib.parse.urlencode(body).encode() if body else None
    else:
        headers = {"Content-Type": "application/json"}
        payload = json.dumps(body).encode() if body else None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    conn.request(method, path, body=payload, headers=headers)
    resp = conn.getresponse()
    raw = resp.read()
    try:
        data = json.loads(raw)
    except Exception:
        data = raw.decode(errors="replace")
    conn.close()
    return resp.status, data


def check(label: str, cond: bool, detail: str = "") -> None:
    global passed, failed
    if cond:
        passed += 1
        print(f"  {OK} {label}")
    else:
        failed += 1
        print(f"  {FAIL} {label}" + (f"  ({detail})" if detail else ""))


def section(name: str) -> None:
    print(f"\n── {name} ──")


# ──────────────────────────────────────────────────────────────────────────────

section("Health")
status, data = req("GET", "/health")
check("GET /health → 200", status == 200, str(status))
check("health.status == 'ok'", isinstance(data, dict) and data.get("status") == "ok", str(data))

section("Auth")
# OAuth2 password flow uses form-encoded body, not JSON
status, data = req("POST", "/api/v1/auth/token",
                   {"username": "controller", "password": "marg2026"},
                   form=True)
check("POST /auth/token → 200", status == 200, str(status))
check("token returned", isinstance(data, dict) and "access_token" in data, str(data))
TOKEN = data.get("access_token", "") if isinstance(data, dict) else ""

status, data = req("GET", "/api/v1/auth/me", token=TOKEN)
check("GET /auth/me → 200", status == 200, str(status))

section("Simulation")
# Stop any running simulation first so start is always clean
req("POST", "/api/v1/simulation/stop", token=TOKEN)
status, data = req("POST", "/api/v1/simulation/start",
                   {"corridor": "NDLS-CNB", "speed_factor": 60.0, "seed": 42,
                    "disruptions": True},
                   token=TOKEN)
check("POST /simulation/start → 200", status == 200, str(data)[:120])
check("session_id returned", isinstance(data, dict) and "session_id" in data, str(data)[:80])

time.sleep(0.5)

status, data = req("GET", "/api/v1/simulation/status", token=TOKEN)
check("GET /simulation/status → 200", status == 200, str(status))

status, data = req("GET", "/api/v1/simulation/snapshot", token=TOKEN)
check("GET /simulation/snapshot → 200", status == 200, str(status))
check("snapshot has trains list", isinstance(data, dict) and "trains" in data, str(data)[:80])

status, data = req("POST", "/api/v1/simulation/disrupt",
                   {"type": "FOG", "section_id": "s1", "duration_min": 30.0,
                    "severity": 0.8},
                   token=TOKEN)
check("POST /simulation/disrupt → 200", status == 200, str(data)[:80])

status, data = req("GET", "/api/v1/simulation/disruptions", token=TOKEN)
check("GET /simulation/disruptions → 200", status == 200, str(status))

status, data = req("POST", "/api/v1/simulation/pause", token=TOKEN)
check("POST /simulation/pause → 200", status == 200, str(status))

status, data = req("POST", "/api/v1/simulation/resume", token=TOKEN)
check("POST /simulation/resume → 200", status == 200, str(data)[:80])

section("Prediction")
status, data = req("POST", "/api/v1/prediction/delay",
                   {"train_id": "12301", "section_id": "s1",
                    "current_delay_min": 5.0, "priority": 1,
                    "category": "superfast", "weather": "DENSE_FOG",
                    "congestion_score": 0.7, "section_is_single_line": False,
                    "signal_failed": False, "track_blocked": False,
                    "hour_of_day": 8.0, "month": 6.0, "day_of_week": 2.0,
                    "sched_depart_min": 480.0},
                   token=TOKEN)
check("POST /prediction/delay → 200", status == 200, str(data)[:120])
check("pred_30 in response", isinstance(data, dict) and "pred_30" in data, str(data)[:80])

status, data = req("POST", "/api/v1/prediction/congestion",
                   {"section_ids": ["s1", "s2", "s3"],
                    "horizon_hours": 1, "timestamp_min": 480.0},
                   token=TOKEN)
check("POST /prediction/congestion → 200", status == 200, str(data)[:120])
check("congestion has sections key", isinstance(data, dict) and "sections" in data, str(data)[:80])

section("Optimization")
trains = {
    "12301": {"train_id": "12301", "category": "superfast", "priority": 1,
              "direction": "DOWN", "current_section": "s1",
              "current_delay": 5.0, "sched_dep_min": 480.0,
              "remaining_route": ["s1", "s2", "s3"],
              "sched_arrivals": {}, "sched_departures": {}, "travel_times": {}},
    "12302": {"train_id": "12302", "category": "express", "priority": 2,
              "direction": "DOWN", "current_section": "s2",
              "current_delay": 0.0, "sched_dep_min": 510.0,
              "remaining_route": ["s2", "s3"],
              "sched_arrivals": {}, "sched_departures": {}, "travel_times": {}},
}
sections = {
    "s1": {"section_id": "s1", "from_station": "NDLS", "to_station": "GZB",
           "length_km": 30.0, "capacity_per_hr": 60, "is_single_line": False,
           "is_blocked": False, "block_duration": 0.0, "congestion_score": 0.3},
    "s2": {"section_id": "s2", "from_station": "GZB", "to_station": "ALJN",
           "length_km": 120.0, "capacity_per_hr": 40, "is_single_line": True,
           "is_blocked": False, "block_duration": 0.0, "congestion_score": 0.6},
    "s3": {"section_id": "s3", "from_station": "ALJN", "to_station": "TDL",
           "length_km": 85.0, "capacity_per_hr": 40, "is_single_line": True,
           "is_blocked": False, "block_duration": 0.0, "congestion_score": 0.4},
}
status, data = req("POST", "/api/v1/optimization/run",
                   {"timestamp_min": 480.0, "horizon_min": 120,
                    "trains": trains, "sections": sections, "min_headway": 3},
                   token=TOKEN)
check("POST /optimization/run → 200", status == 200, str(data)[:120])
check("optimization has decisions", isinstance(data, dict) and "decisions" in data, str(data)[:80])

section("Explainability")
status, data = req("POST", "/api/v1/explainability/explain",
                   {"decision_type": "HOLD", "train_id": "12301",
                    "section_id": "s1", "detail": "Hold at loop for crossing",
                    "delay_saved_min": 12.0, "hold_minutes": 6.0,
                    "confidence": 0.9, "timestamp_min": 480.0, "horizon_min": 120,
                    "trains": {}, "sections": {}},
                   token=TOKEN)
check("POST /explainability/explain → 200", status == 200, str(data)[:120])
check("explanation has text", isinstance(data, dict) and "text" in data, str(data)[:80])

# ── Summary ──────────────────────────────────────────────────────────────────

total = passed + failed
print(f"\n{'='*52}")
print(f"  {passed}/{total} checks passed", end="")
if failed == 0:
    print("  \033[32m— ALL PASS\033[0m")
else:
    print(f"  \033[31m— {failed} FAILED\033[0m")
print(f"{'='*52}")
sys.exit(0 if failed == 0 else 1)
