"""
Step 6: Collect historical weather for the 6 corridor stations using the
Open-Meteo Historical Weather (Archive) API - free, no API key required.

Source: https://archive-api.open-meteo.com/v1/archive

Raw JSON responses are cached under data/raw/weather/<code>.json and never
overwritten (re-run skips stations whose cache file already exists).

NOTE: The archive API does not provide "visibility" as an hourly variable
(returns unit "undefined"). We derive a fog_indicator from the WMO
weathercode (45 = fog, 48 = depositing rime fog) and leave visibility_km
as NaN, documented as a known gap in data_quality_report.md.
"""
import json
import time
import requests
import pandas as pd
from pathlib import Path
from datetime import date, timedelta

BASE = Path(__file__).resolve().parent.parent
RAW_DIR = BASE / "data" / "raw" / "weather"
OUT_CSV = BASE / "data" / "processed" / "weather_history.csv"
RAW_DIR.mkdir(parents=True, exist_ok=True)

CORRIDOR_STATIONS = {
    "NDLS": (28.642314, 77.220004),
    "GZB": (28.649702, 77.431099),
    "ALJN": (27.889584, 78.074559),
    "TDL": (27.207747, 78.233285),
    "ETW": (26.785970, 79.021502),
    "CNB": (26.454240, 80.350966),
}

HOURLY_VARS = "temperature_2m,relative_humidity_2m,precipitation,windspeed_10m,weathercode,cloudcover"

FOG_CODES = {45, 48}
RAIN_CODES = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}

WEATHER_CODE_DESC = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
}


def fetch_station(code, lat, lon, start_date, end_date, retries=3):
    cache_file = RAW_DIR / f"{code}.json"
    if cache_file.exists():
        print(f"[cache] {code}: using cached {cache_file.name}")
        return json.loads(cache_file.read_text())

    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat, "longitude": lon,
        "start_date": start_date, "end_date": end_date,
        "hourly": HOURLY_VARS, "timezone": "Asia/Kolkata",
    }
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, params=params, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            cache_file.write_text(json.dumps(data))
            print(f"[fetched] {code}: {len(data['hourly']['time'])} hourly records")
            return data
        except Exception as e:
            print(f"[retry {attempt}/{retries}] {code}: {e}")
            time.sleep(2 * attempt)
    raise RuntimeError(f"Failed to fetch weather for {code}")


def main():
    end_date = date.today() - timedelta(days=3)
    start_date = end_date - timedelta(days=365)

    rows = []
    for code, (lat, lon) in CORRIDOR_STATIONS.items():
        data = fetch_station(code, lat, lon, start_date.isoformat(), end_date.isoformat())
        h = data["hourly"]
        n = len(h["time"])
        for i in range(n):
            wcode = h["weathercode"][i]
            rows.append({
                "station_code": code,
                "timestamp": h["time"][i],
                "temperature_c": h["temperature_2m"][i],
                "humidity_pct": h["relative_humidity_2m"][i],
                "visibility_km": None,
                "rainfall_mm": h["precipitation"][i],
                "wind_speed_kmh": h["windspeed_10m"][i],
                "cloudcover_pct": h["cloudcover"][i],
                "weather_condition": WEATHER_CODE_DESC.get(wcode, f"code_{wcode}"),
                "fog_indicator": 1 if wcode in FOG_CODES else 0,
            })
        # be polite between requests (only matters when not cached)
        time.sleep(1)

    df = pd.DataFrame(rows)
    df.to_csv(OUT_CSV, index=False)
    print(f"Wrote {len(df)} rows to weather_history.csv covering {start_date} to {end_date}")


if __name__ == "__main__":
    main()
