"""
Step 3 (Dataset 3): historical_running_status.csv

REALITY CHECK: NTES / RailYatri / ConfirmTkt / Trainman do not expose a
public bulk-download of 1 year of per-train, per-station actual running
times. Real historical running data is only obtainable by polling NTES
live-status continuously going forward (see 06b_ntes_live_collector.py).

To unblock schema/ML-pipeline development now, this script generates a
SYNTHETIC but statistically-grounded historical_running_status.csv for
the past 365 days, covering every (train, station) pair in
train_routes.csv. Delay is modeled as a function of:
  - train priority (from train_master.csv / priority_mapping.csv)
  - delay propagation along the route (AR(1)-style with noise)
  - halt-time recovery (padding absorbs some delay)
  - real weather (fog/rain) at that station/date/hour, joined from
    weather_history.csv produced by 05_collect_weather.py
  - a small probability of "major disruption" events

ASSUMPTIONS (documented in data_quality_report.md):
  - All trains assumed to run daily (operating_days mostly UNKNOWN).
  - delay_minutes = actual_arrival - scheduled_arrival, in minutes,
    clipped to [-10, +600].
  - This dataset is clearly marked is_synthetic=1 in every row so it can
    be swapped out once real NTES history accumulates.
"""
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import date, timedelta, datetime

BASE = Path(__file__).resolve().parent.parent
PROC = BASE / "data" / "processed"
OUT_CSV = PROC / "historical_running_status.csv"

SEED = 42
N_DAYS = 365

PRIORITY_PARAMS = {
    1: {"origin_mean": 3, "origin_std": 4, "noise_std": 2.5, "ar": 0.7},
    2: {"origin_mean": 5, "origin_std": 7, "noise_std": 4.0, "ar": 0.75},
    3: {"origin_mean": 8, "origin_std": 10, "noise_std": 6.0, "ar": 0.8},
    4: {"origin_mean": 10, "origin_std": 12, "noise_std": 7.0, "ar": 0.8},
    5: {"origin_mean": 20, "origin_std": 20, "noise_std": 10.0, "ar": 0.85},
}


def parse_hms(t):
    try:
        h, m, _ = str(t).split(":")
        return int(h), int(m)
    except Exception:
        return 0, 0


def main():
    rng = np.random.default_rng(SEED)

    routes = pd.read_csv(PROC / "train_routes.csv", dtype={"train_number": str})
    master = pd.read_csv(PROC / "train_master.csv", dtype={"train_number": str})
    weather = pd.read_csv(PROC / "weather_history.csv", parse_dates=["timestamp"])

    prio_lookup = dict(zip(master["train_number"], master["train_category_priority"]))

    # weather lookup: (station_code, date, hour) -> (fog_indicator, rainfall_mm)
    weather["w_date"] = weather["timestamp"].dt.date
    weather["w_hour"] = weather["timestamp"].dt.hour
    weather_idx = weather.set_index(["station_code", "w_date", "w_hour"])[["fog_indicator", "rainfall_mm"]]
    weather_dict = weather_idx.to_dict("index")

    end_date = date.today() - timedelta(days=3)
    start_date = end_date - timedelta(days=N_DAYS - 1)
    all_dates = [start_date + timedelta(days=i) for i in range(N_DAYS)]

    out_rows = []
    for train_number, g in routes.groupby("train_number"):
        g = g.sort_values("station_sequence").reset_index(drop=True)
        priority = prio_lookup.get(train_number, 3)
        params = PRIORITY_PARAMS.get(priority, PRIORITY_PARAMS[3])

        for d in all_dates:
            prev_delay = 0.0
            # 2% chance this service is cancelled for the day
            if rng.random() < 0.02:
                continue
            for _, row in g.iterrows():
                seq = row["station_sequence"]
                station = row["station_code"]
                sched_arr_h, sched_arr_m = parse_hms(row["scheduled_arrival"])
                sched_dep_h, sched_dep_m = parse_hms(row["scheduled_departure"])
                halt = row["halt_minutes"]

                if seq == 1:
                    # origin: small positive bias, occasional early departure
                    delay = max(rng.normal(params["origin_mean"], params["origin_std"]), -5)
                else:
                    noise = rng.normal(0, params["noise_std"])
                    delay = params["ar"] * prev_delay + noise

                    # recovery from halt padding
                    if halt > 0:
                        recovery = min(halt * 0.3, max(delay, 0) * 0.25)
                        delay -= recovery

                    # weather effect using scheduled arrival hour
                    key = (station, d, sched_arr_h)
                    w = weather_dict.get(key)
                    if w:
                        if w["fog_indicator"] == 1:
                            delay += rng.uniform(10, 45) if priority >= 3 else rng.uniform(5, 20)
                        if w["rainfall_mm"] and w["rainfall_mm"] > 5:
                            delay += rng.uniform(5, 20)

                    # rare major disruption, persists/propagates
                    if rng.random() < 0.01:
                        delay += rng.uniform(30, 120)

                delay = float(np.clip(delay, -10, 600))
                prev_delay = delay

                is_origin = (row["scheduled_arrival"] == "00:00:00" and seq == 1)
                is_terminus = (row["scheduled_departure"] == "00:00:00" and seq == len(g))

                sched_arr_dt = datetime.combine(d, datetime.min.time()).replace(hour=sched_arr_h, minute=sched_arr_m)
                sched_dep_dt = datetime.combine(d, datetime.min.time()).replace(hour=sched_dep_h, minute=sched_dep_m)

                actual_arr_dt = None if is_origin else sched_arr_dt + timedelta(minutes=delay)
                # departure delay roughly tracks arrival delay minus any recovered halt time
                dep_delay = max(delay - rng.uniform(0, max(halt, 0)), -5) if seq > 1 else delay
                actual_dep_dt = None if is_terminus else sched_dep_dt + timedelta(minutes=dep_delay)

                out_rows.append({
                    "date": d.isoformat(),
                    "train_number": train_number,
                    "station_code": station,
                    "station_sequence": seq,
                    "scheduled_arrival": None if is_origin else sched_arr_dt.isoformat(),
                    "actual_arrival": None if is_origin else actual_arr_dt.isoformat(),
                    "scheduled_departure": None if is_terminus else sched_dep_dt.isoformat(),
                    "actual_departure": None if is_terminus else actual_dep_dt.isoformat(),
                    "delay_minutes": round(delay, 1) if seq > 1 else round(max(delay, 0), 1),
                    "is_synthetic": 1,
                })

    df = pd.DataFrame(out_rows)
    df.to_csv(OUT_CSV, index=False)
    print(f"Wrote {len(df)} rows to historical_running_status.csv "
          f"({df['train_number'].nunique()} trains x ~{N_DAYS} days)")


if __name__ == "__main__":
    main()
