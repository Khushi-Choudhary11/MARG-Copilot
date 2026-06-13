"""
Step: Scrape REAL historical per-station average delay ("last year") for
every corridor train from etrain.info running-history pages.

Endpoint pattern (discovered via inspection - static server-rendered HTML,
no JS required for this data):

    https://etrain.info/train/x-{train_number}/history?d=1y

`x-{train_number}` 302-redirects to the train's canonical slug
(e.g. Rjpb-Rajdhani-12309); `?d=1y` selects the "last year" aggregation
window. The response embeds, per station on the route, a block like:

    <a href="#CNB" etitle=...>KANPUR CENTRAL (CNB) ... Avg. Delay: 18 Min's ...

We extract (station_code, avg_delay_minutes) for the 6 corridor stations
only, for each train.

Also extracts the `holiDay` JS object embedded in the page - a real
Indian-Railways-relevant festival/holiday calendar - into special_days.csv
(supplemented with a curated list for the back half of 2025, since the
site only serves the current calendar year).

Output:
  data/processed/real_station_delay_stats.csv
  data/processed/special_days.csv
Raw cache: data/raw/status/etrain_<train_number>.html (never overwritten)
"""
import re
import time
import requests
import pandas as pd
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
RAW_DIR = BASE / "data" / "raw" / "status"
PROC = BASE / "data" / "processed"
RAW_DIR.mkdir(parents=True, exist_ok=True)

CORRIDOR_CODES = {"NDLS", "GZB", "ALJN", "TDL", "ETW", "CNB"}
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
RATE_LIMIT = 1.0

ROW_RE = re.compile(
    r'<a href="#(\w+)" etitle=.*?>\s*[A-Z0-9 .()\-]+?\s*<div.*?Avg\. Delay:</b> (-?\d+) Min',
    re.S,
)
HOLIDAY_RE = re.compile(r"var holiDay = (\{.*?\});", re.S)

# Curated supplement for Jun-Dec 2025 (etrain.info only serves the current
# calendar year's holiday object; 2026 was scraped live).
CURATED_2025_H2_HOLIDAYS = {
    "20250706": "Eid-Ul-Adha",
    "20250809": "Raksha Bandhan",
    "20250815": "Independence Day",
    "20250816": "Janmashtami",
    "20250827": "Ganesh Chaturthi",
    "20250902": "Onam",
    "20251002": "Gandhi Jayanti",
    "20251002": "Dussehra (Maha Navami)",
    "20251020": "Diwali",
    "20251021": "Govardhan Puja",
    "20251022": "Bhai Dooj",
    "20251028": "Chhath Puja",
    "20251105": "Guru Nanak Jayanti",
    "20251225": "Christmas Day",
}


def fetch(train_number: str, retries: int = 3):
    cache_file = RAW_DIR / f"etrain_{train_number}.html"
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")

    url = f"https://etrain.info/train/x-{train_number}/history?d=1y"
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            if resp.status_code == 404:
                cache_file.write_text("", encoding="utf-8")
                return ""
            resp.raise_for_status()
            cache_file.write_text(resp.text, encoding="utf-8")
            return resp.text
        except Exception as e:
            print(f"[retry {attempt}/{retries}] {train_number}: {e}")
            time.sleep(2 * attempt)
    return ""


def main():
    master = pd.read_csv(PROC / "train_master.csv", dtype={"train_number": str})

    delay_rows = []
    holiday_dict = {}

    for i, train_number in enumerate(master["train_number"]):
        html = fetch(train_number)
        if not html:
            print(f"[{i+1}/{len(master)}] {train_number}: no data (404 or fetch failed)")
            time.sleep(RATE_LIMIT)
            continue

        matches = ROW_RE.findall(html)
        found = 0
        for code, delay in matches:
            if code in CORRIDOR_CODES:
                delay_rows.append({
                    "train_number": train_number,
                    "station_code": code,
                    "avg_delay_minutes_last_year": int(delay),
                    "period": "1y",
                    "source": "etrain.info",
                })
                found += 1

        if not holiday_dict:
            hm = HOLIDAY_RE.search(html)
            if hm:
                for entry in re.findall(r"(\d{8}):'([^']+)'", hm.group(1)):
                    holiday_dict[entry[0]] = entry[1]

        print(f"[{i+1}/{len(master)}] {train_number}: {found} corridor stations found")
        time.sleep(RATE_LIMIT)

    out = pd.DataFrame(delay_rows)
    out.to_csv(PROC / "real_station_delay_stats.csv", index=False)
    print(f"Wrote {len(out)} rows to real_station_delay_stats.csv "
          f"({out['train_number'].nunique()} trains)")

    holiday_dict.update(CURATED_2025_H2_HOLIDAYS)
    holidays = pd.DataFrame(
        [{"date": pd.to_datetime(k, format="%Y%m%d").date().isoformat(), "occasion": v,
          "source": "etrain.info" if k.startswith("2026") else "curated"}
         for k, v in holiday_dict.items()]
    ).sort_values("date")
    holidays.to_csv(PROC / "special_days.csv", index=False)
    print(f"Wrote {len(holidays)} rows to special_days.csv")


if __name__ == "__main__":
    main()
