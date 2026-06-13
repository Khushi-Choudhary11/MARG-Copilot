"""
Step 8: Build master_training_dataset.csv

Joins historical_running_status (synthetic + any real rows appended by
06b_ntes_live_collector.py) with train_master, stations, infrastructure,
weather and priority_mapping, then derives the feature-engineering columns
required for delay/ETA/congestion modeling.

WEATHER JOIN LOGIC: weather is joined on (station_code, date, hour-of-
scheduled-arrival) - i.e. station-specific, nearest-hour. Weather is only
available for the 6 corridor stations (NDLS, GZB, ALJN, TDL, ETW, CNB);
for all other stations on a train's route, weather/track/platform/
congestion fields are left NaN (documented in data_quality_report.md).
"""
import numpy as np
import pandas as pd
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PROC = BASE / "data" / "processed"
OUT_CSV = PROC / "new_master_training_dataset.csv"


def main():
    hist = pd.read_csv(PROC / "new_historical_running_status.csv", dtype={"train_number": str})
    master = pd.read_csv(PROC / "train_master.csv", dtype={"train_number": str})
    routes = pd.read_csv(PROC / "train_routes.csv", dtype={"train_number": str})
    stations = pd.read_csv(PROC / "stations.csv")
    station_infra = pd.read_csv(PROC / "station_infrastructure.csv")
    section_infra = pd.read_csv(PROC / "section_infrastructure.csv")
    weather = pd.read_csv(PROC / "weather_history.csv", parse_dates=["timestamp"])

    hist["scheduled_arrival"] = pd.to_datetime(hist["scheduled_arrival"], format="ISO8601")
    hist["actual_arrival"] = pd.to_datetime(hist["actual_arrival"], format="ISO8601")
    hist["scheduled_departure"] = pd.to_datetime(hist["scheduled_departure"], format="ISO8601")
    # origin stations have no scheduled_arrival - fall back to scheduled_departure for time features
    hist["reference_time"] = hist["scheduled_arrival"].fillna(hist["scheduled_departure"])

    hist = hist.sort_values(["train_number", "date", "station_sequence"]).reset_index(drop=True)

    # --- delay propagation features (within each train+date service) ---
    grp = hist.groupby(["train_number", "date"])
    hist["current_delay"] = hist["delay_minutes"]
    hist["previous_station_delay"] = grp["delay_minutes"].shift(1)
    hist["delay_next_station"] = grp["delay_minutes"].shift(-1)

    # --- historical averages ---
    train_avg = hist.groupby("train_number")["delay_minutes"].mean().rename("train_average_delay")
    station_avg = hist.groupby("station_code")["delay_minutes"].mean().rename("station_average_delay")
    hist = hist.merge(train_avg, on="train_number", how="left")
    hist = hist.merge(station_avg, on="station_code", how="left")

    # --- priority ---
    prio = master[["train_number", "train_category_priority"]].rename(
        columns={"train_category_priority": "priority"})
    hist = hist.merge(prio, on="train_number", how="left")

    # --- time features ---
    hist["hour_of_day"] = hist["reference_time"].dt.hour
    hist["day_of_week"] = hist["reference_time"].dt.dayofweek  # 0=Monday
    hist["month"] = hist["reference_time"].dt.month

    # --- weather join: station_code + nearest hour ---
    weather["w_date"] = weather["timestamp"].dt.date.astype(str)
    weather["w_hour"] = weather["timestamp"].dt.hour
    weather_small = weather[["station_code", "w_date", "w_hour", "temperature_c",
                              "humidity_pct", "visibility_km", "rainfall_mm"]]

    hist["w_date"] = hist["date"]
    hist["w_hour"] = hist["hour_of_day"]
    hist = hist.merge(weather_small, on=["station_code", "w_date", "w_hour"], how="left")
    hist = hist.rename(columns={
        "temperature_c": "temperature",
        "humidity_pct": "humidity",
        "visibility_km": "visibility",
        "rainfall_mm": "rainfall",
    })
    hist = hist.drop(columns=["w_date", "w_hour"])

    # --- infrastructure: platform_count, track_count, electrification, speed (corridor stations only) ---
    infra = station_infra[["station_code", "platforms", "main_tracks", "electrified"]].rename(
        columns={"platforms": "platform_count", "main_tracks": "track_count"})
    hist = hist.merge(infra, on="station_code", how="left")

    # max_speed_kmh of the section departing this station (or arriving, for the last station)
    speed_from = section_infra.set_index("from_station")["max_speed_kmh"]
    speed_to = section_infra.set_index("to_station")["max_speed_kmh"]
    station_speed = speed_from.combine_first(speed_to).rename("max_speed_kmh")
    station_speed.index.name = "station_code"
    hist = hist.merge(station_speed.reset_index(), on="station_code", how="left")

    # --- congestion_score: scheduled arrivals in same (station, date, hour) / platform_count ---
    congestion = (
        hist.groupby(["station_code", "date", "hour_of_day"])
        .size()
        .rename("arrivals_in_hour")
        .reset_index()
    )
    hist = hist.merge(congestion, on=["station_code", "date", "hour_of_day"], how="left")
    hist["congestion_score"] = hist["arrivals_in_hour"] / hist["platform_count"]
    hist = hist.drop(columns=["arrivals_in_hour"])

    cols = [
        "train_number", "station_code", "date", "station_sequence",
        "current_delay", "previous_station_delay", "train_average_delay",
        "station_average_delay", "delay_lag_1", "delay_lag_7",
        "delay_rolling_mean_7", "delay_rolling_mean_30",
        "priority", "hour_of_day", "day_of_week", "month",
        "is_weekend", "is_special_day",
        "visibility", "rainfall", "temperature", "humidity",
        "track_count", "platform_count", "electrified", "max_speed_kmh", "congestion_score",
        "delay_next_station", "is_imputed", "is_synthetic", "calibration_source",
    ]
    out = hist[cols]
    out.to_csv(OUT_CSV, index=False)
    print(f"Wrote {len(out)} rows to new_master_training_dataset.csv")
    print(out.isna().mean().round(3).to_string())


if __name__ == "__main__":
    main()
