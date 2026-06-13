"""
Live running-status collector for the NDLS-CNB corridor.

There is no free/keyless public NTES JSON API. Community APIs
(railwayapi.com, indianrailapi.com) wrap NTES but require a free
registered API key. This script is a ready-to-run collector against
railwayapi.com's "live train status" endpoint:

    https://api.railwayapi.com/v2/live/train/{train_number}/date/{ddmmyyyy}/apikey/{key}/

USAGE:
  1. Register a free API key at https://railwayapi.com/api
  2. set RAILWAY_API_KEY=<your key>   (PowerShell: $env:RAILWAY_API_KEY="...")
  3. Run this script daily (e.g. via a scheduled task / cron). Each run
     polls every corridor train (from train_master.csv) for "today" and
     appends new (train, station, date) rows to historical_running_status.csv,
     with raw JSON cached under data/raw/status/.

FEATURES:
  - Request caching: raw JSON saved to data/raw/status/<train>_<date>.json,
    never overwritten -> re-running the same day is a no-op (no duplicate
    API calls).
  - Retry with exponential backoff (3 attempts).
  - Rate limiting: configurable delay between requests (default 1.5s)
    to stay within free-tier limits.
  - Duplicate detection: rows already present in historical_running_status.csv
    for the same (train_number, station_code, date) are skipped on append.

This script intentionally does NOT run automatically as part of the
pipeline (no API key configured in this environment) - it is provided as
the production collection mechanism to accumulate REAL data over time,
which should eventually replace the synthetic rows from
06_generate_historical_status.py (is_synthetic=0 vs 1).
"""
import os
import json
import time
import logging
import requests
import pandas as pd
from pathlib import Path
from datetime import date

BASE = Path(__file__).resolve().parent.parent
RAW_DIR = BASE / "data" / "raw" / "status"
PROC = BASE / "data" / "processed"
LOG_DIR = BASE / "data" / "logs"
RAW_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=LOG_DIR / "ntes_collector.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

API_KEY = os.environ.get("RAILWAY_API_KEY")
RATE_LIMIT_SECONDS = float(os.environ.get("RAILWAY_API_RATE_LIMIT", "1.5"))
CORRIDOR_STATIONS = {"NDLS", "GZB", "ALJN", "TDL", "ETW", "CNB"}


def fetch_live_status(train_number: str, day: date, retries: int = 3):
    """Fetch + cache raw live-status JSON for a train on a given date."""
    cache_file = RAW_DIR / f"{train_number}_{day.isoformat()}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())

    if not API_KEY:
        logging.warning("RAILWAY_API_KEY not set - skipping %s", train_number)
        return None

    url = (
        f"https://api.railwayapi.com/v2/live/train/{train_number}"
        f"/date/{day.strftime('%d%m%Y')}/apikey/{API_KEY}/"
    )
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            cache_file.write_text(json.dumps(data))
            logging.info("Fetched %s for %s", train_number, day)
            return data
        except Exception as e:
            logging.warning("Attempt %d/%d failed for %s: %s", attempt, retries, train_number, e)
            time.sleep(2 ** attempt)
    logging.error("Giving up on %s for %s", train_number, day)
    return None


def parse_response(data, train_number, day):
    """Map railwayapi.com live response -> historical_running_status rows
    (corridor stations only)."""
    rows = []
    if not data or "stations" not in data:
        return rows
    for st in data["stations"]:
        code = st.get("station", {}).get("code")
        if code not in CORRIDOR_STATIONS:
            continue
        rows.append({
            "date": day.isoformat(),
            "train_number": train_number,
            "station_code": code,
            "station_sequence": st.get("no"),
            "scheduled_arrival": st.get("scharrival"),
            "actual_arrival": st.get("actarrival"),
            "scheduled_departure": st.get("schdeparture"),
            "actual_departure": st.get("actdeparture"),
            "delay_minutes": st.get("delayarrival"),
            "is_synthetic": 0,
        })
    return rows


def main():
    master = pd.read_csv(PROC / "train_master.csv", dtype={"train_number": str})
    today = date.today()

    hist_path = PROC / "historical_running_status.csv"
    existing = pd.read_csv(hist_path, dtype={"train_number": str})
    existing_keys = set(zip(existing["train_number"], existing["station_code"], existing["date"]))

    new_rows = []
    for train_number in master["train_number"]:
        data = fetch_live_status(train_number, today)
        for row in parse_response(data, train_number, today):
            key = (row["train_number"], row["station_code"], row["date"])
            if key in existing_keys:
                continue
            new_rows.append(row)
            existing_keys.add(key)
        time.sleep(RATE_LIMIT_SECONDS)

    if new_rows:
        out = pd.concat([existing, pd.DataFrame(new_rows)], ignore_index=True)
        out.to_csv(hist_path, index=False)
        logging.info("Appended %d new real rows", len(new_rows))
        print(f"Appended {len(new_rows)} new rows from live collection")
    else:
        print("No new rows (no API key configured, or all cached/duplicate)")


if __name__ == "__main__":
    main()
