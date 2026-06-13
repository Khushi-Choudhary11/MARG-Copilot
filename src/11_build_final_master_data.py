"""
Step 11: Build final_master_data.csv

Final, fully-mapped training table for the NDLS<->CNB corridor delay
prediction model. Built on top of master_training_dataset.csv (numeric
feature matrix) by joining back human-readable identifiers (train name,
type, station name) and the raw scheduled/actual timestamps from
historical_running_status.csv, so every row is self-describing:

  "train X, at station Y, scheduled to arrive at time T, actually
   arrived at time T', was delayed by D minutes -> predict delay at
   the next station"

Column groups:
  - Identifiers: train_number, train_name, train_type, priority,
    station_code, station_name, station_sequence, date
  - Timing (ground truth for "scheduled vs actual"):
    scheduled_arrival, actual_arrival, scheduled_departure, actual_departure
  - Calendar features: hour_of_day, day_of_week, month, is_weekend, is_special_day
  - Delay target/propagation features: current_delay, previous_station_delay,
    delay_next_station (TARGET), train_average_delay, station_average_delay,
    delay_lag_1, delay_lag_7, delay_rolling_mean_7, delay_rolling_mean_30
  - Weather (station-specific, nearest-hour join): temperature, humidity,
    rainfall, visibility
  - Infrastructure / congestion: track_count, platform_count, congestion_score
  - Provenance: is_imputed, is_synthetic
"""
import pandas as pd
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PROC = BASE / "data" / "processed"
OUT_CSV = PROC / "new_final_master_data.csv"


def main():
    master = pd.read_csv(PROC / "new_master_training_dataset.csv", dtype={"train_number": str})
    hist = pd.read_csv(PROC / "new_historical_running_status.csv", dtype={"train_number": str})
    train_master = pd.read_csv(PROC / "train_master.csv", dtype={"train_number": str})
    stations = pd.read_csv(PROC / "stations.csv")

    # --- bring back scheduled/actual timestamps (scheduled time to reach vs actual arrival time) ---
    times = hist[["train_number", "station_code", "station_sequence", "date",
                   "scheduled_arrival", "actual_arrival",
                   "scheduled_departure", "actual_departure"]]
    out = master.merge(times, on=["train_number", "station_code", "station_sequence", "date"], how="left")

    # --- train identifiers ---
    train_info = train_master[["train_number", "train_name", "train_type",
                                 "source_station_code", "destination_station_code",
                                 "corridor_direction"]]
    out = out.merge(train_info, on="train_number", how="left")

    # --- station identifiers ---
    station_info = stations[["station_code", "station_name"]]
    out = out.merge(station_info, on="station_code", how="left")

    cols = [
        # identifiers
        "train_number", "train_name", "train_type", "priority",
        "source_station_code", "destination_station_code", "corridor_direction",
        "station_code", "station_name", "station_sequence", "date",
        # timing: scheduled vs actual
        "scheduled_arrival", "actual_arrival",
        "scheduled_departure", "actual_departure",
        # calendar features
        "hour_of_day", "day_of_week", "month", "is_weekend", "is_special_day",
        # delay propagation / target
        "current_delay", "previous_station_delay", "delay_next_station",
        "train_average_delay", "station_average_delay",
        "delay_lag_1", "delay_lag_7", "delay_rolling_mean_7", "delay_rolling_mean_30",
        # weather (station-specific)
        "temperature", "humidity", "rainfall", "visibility",
        # infrastructure / congestion
        "track_count", "platform_count", "electrified", "max_speed_kmh", "congestion_score",
        # provenance
        "is_imputed", "is_synthetic", "calibration_source",
    ]
    out = out[cols]
    out = out.sort_values(["train_number", "date", "station_sequence"]).reset_index(drop=True)
    out.to_csv(OUT_CSV, index=False)
    print(f"Wrote {len(out)} rows, {len(out.columns)} columns to {OUT_CSV.name}")
    print(out.isna().mean().round(3).to_string())


if __name__ == "__main__":
    main()
