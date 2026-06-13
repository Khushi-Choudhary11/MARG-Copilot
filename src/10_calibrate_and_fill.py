"""
Step: Calibrate synthetic delays against REAL scraped averages, fill
cancelled-service gaps via lag/rolling imputation, and add calendar
features (weekend / special day).

1. CALIBRATION: for every (train_number, station_code) pair where
   real_station_delay_stats.csv has a real "last year" average delay
   (scraped from etrain.info), shift that pair's synthetic delay series
   by a constant offset so its mean matches the real average. This
   anchors the synthetic data to ground truth wherever ground truth is
   known.

2. GAP FILLING: historical_running_status.csv only has rows for services
   that actually ran (~2% of train/date combos were "cancelled" by the
   generator and are simply absent). This script reindexes to the full
   (train, station, date) grid, then fills missing delay_minutes using:
     lag_1 -> rolling_mean_7 (past 7 days) -> rolling_mean_30 -> train's
     overall mean -> 0
   Filled rows are flagged is_imputed=1 and get scheduled times from
   train_routes.csv + actual times = scheduled + imputed delay.

3. LAG/ROLLING FEATURES (final, post-fill, leak-safe i.e. computed only
   from PAST days for each (train, station)):
     delay_lag_1, delay_lag_7, delay_rolling_mean_7, delay_rolling_mean_30

4. CALENDAR FEATURES: is_weekend (Sat/Sun), is_special_day (from
   special_days.csv, the Indian festival/holiday calendar).

Reads historical_running_status.csv (synthetic baseline, never modified) and
writes new_historical_running_status.csv (calibrated + gap-filled +
lag/rolling/calendar features + calibration_source provenance column) as a
separate file - the synthetic baseline is preserved untouched.
"""
import numpy as np
import pandas as pd
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PROC = BASE / "data" / "processed"


def parse_hms(t):
    if pd.isna(t) or t == "":
        return None
    h, m, _ = str(t).split(":")
    return int(h), int(m)


def main():
    hist = pd.read_csv(PROC / "historical_running_status.csv", dtype={"train_number": str})
    routes = pd.read_csv(PROC / "train_routes.csv", dtype={"train_number": str})
    real_stats = pd.read_csv(PROC / "real_station_delay_stats.csv", dtype={"train_number": str})
    special_days = pd.read_csv(PROC / "special_days.csv")

    hist["date"] = pd.to_datetime(hist["date"])
    all_dates = sorted(hist["date"].unique())
    special_dates = set(pd.to_datetime(special_days["date"]).dt.date)

    # --- 1. CALIBRATION ---
    cur_mean = hist.groupby(["train_number", "station_code"])["delay_minutes"].mean().rename("cur_mean")
    real = real_stats.set_index(["train_number", "station_code"])["avg_delay_minutes_last_year"].rename("real_mean")
    offsets = pd.concat([cur_mean, real], axis=1).dropna()
    offsets["offset"] = offsets["real_mean"] - offsets["cur_mean"]
    offsets = offsets["offset"]

    calibrated_pairs = set(offsets.index)

    hist = hist.merge(offsets.reset_index(), on=["train_number", "station_code"], how="left")
    hist["offset"] = hist["offset"].fillna(0.0)
    hist["delay_minutes"] = (hist["delay_minutes"] + hist["offset"]).clip(-10, 600)
    n_calibrated = (hist["offset"] != 0).sum()
    print(f"Calibrated {n_calibrated} rows across {len(offsets)} (train,station) pairs "
          f"using real etrain.info averages")
    hist = hist.drop(columns=["offset"])

    # --- 2. FULL GRID + GAP DETECTION ---
    route_template = routes[["train_number", "station_code", "station_sequence",
                              "scheduled_arrival", "scheduled_departure", "halt_minutes"]]
    frames = []
    for tn, g in route_template.groupby("train_number"):
        grid = g.assign(key=1).merge(pd.DataFrame({"date": all_dates, "key": 1}), on="key").drop(columns="key")
        frames.append(grid)
    full_grid = pd.concat(frames, ignore_index=True)

    merged = full_grid.merge(
        hist[["train_number", "station_code", "station_sequence", "date",
              "delay_minutes", "is_synthetic"]],
        on=["train_number", "station_code", "station_sequence", "date"], how="left"
    )
    merged["is_cancelled"] = merged["delay_minutes"].isna()
    print(f"Full grid: {len(merged)} rows, {merged['is_cancelled'].sum()} cancelled-service gaps")

    merged = merged.sort_values(["train_number", "station_code", "date"]).reset_index(drop=True)

    # --- 3a. lag/rolling computed on the (gappy) calibrated series, for imputation ---
    grp = merged.groupby(["train_number", "station_code"], sort=False)["delay_minutes"]
    roll7 = grp.transform(lambda s: s.shift(1).rolling(7, min_periods=1).mean())
    roll30 = grp.transform(lambda s: s.shift(1).rolling(30, min_periods=1).mean())
    lag1 = grp.transform(lambda s: s.shift(1))
    train_mean = merged.groupby("train_number")["delay_minutes"].transform("mean")

    fill_value = lag1.fillna(roll7).fillna(roll30).fillna(train_mean).fillna(0.0)
    merged["delay_minutes"] = merged["delay_minutes"].fillna(fill_value)
    merged["is_imputed"] = merged["is_cancelled"].astype(int)
    merged["is_synthetic"] = merged["is_synthetic"].fillna(1).astype(int)
    merged = merged.drop(columns=["is_cancelled"])

    # --- recompute scheduled/actual timestamps for imputed rows ---
    def build_timestamp(row, col):
        t = parse_hms(row[col])
        if t is None:
            return pd.NaT
        h, m = t
        return row["date"] + pd.Timedelta(hours=h, minutes=m)

    needs_sched = merged["is_imputed"] == 1
    merged["sched_arr_dt"] = pd.Series(pd.NaT, index=merged.index, dtype="datetime64[ns]")
    merged["sched_dep_dt"] = pd.Series(pd.NaT, index=merged.index, dtype="datetime64[ns]")
    if needs_sched.any():
        merged.loc[needs_sched, "sched_arr_dt"] = merged.loc[needs_sched].apply(
            lambda r: build_timestamp(r, "scheduled_arrival"), axis=1)
        merged.loc[needs_sched, "sched_dep_dt"] = merged.loc[needs_sched].apply(
            lambda r: build_timestamp(r, "scheduled_departure"), axis=1)

    merged["scheduled_arrival_dt"] = pd.NaT
    merged["actual_arrival_dt"] = pd.NaT
    merged["scheduled_departure_dt"] = pd.NaT
    merged["actual_departure_dt"] = pd.NaT
    merged.loc[needs_sched, "scheduled_arrival_dt"] = merged.loc[needs_sched, "sched_arr_dt"]
    merged.loc[needs_sched, "scheduled_departure_dt"] = merged.loc[needs_sched, "sched_dep_dt"]
    merged.loc[needs_sched, "actual_arrival_dt"] = (
        merged.loc[needs_sched, "sched_arr_dt"]
        + pd.to_timedelta(merged.loc[needs_sched, "delay_minutes"], unit="m")
    )
    merged.loc[needs_sched, "actual_departure_dt"] = (
        merged.loc[needs_sched, "sched_dep_dt"]
        + pd.to_timedelta(merged.loc[needs_sched, "delay_minutes"], unit="m")
    )
    merged = merged.drop(columns=["sched_arr_dt", "sched_dep_dt"])

    # for non-imputed rows, parse existing string timestamps
    not_imputed = merged["is_imputed"] == 0
    orig = hist.set_index(["train_number", "station_code", "station_sequence", "date"])
    for col_str, col_dt in [
        ("scheduled_arrival", "scheduled_arrival_dt"), ("actual_arrival", "actual_arrival_dt"),
        ("scheduled_departure", "scheduled_departure_dt"), ("actual_departure", "actual_departure_dt"),
    ]:
        vals = merged.set_index(["train_number", "station_code", "station_sequence", "date"]).index.map(
            orig[col_str].to_dict())
        parsed = pd.to_datetime(pd.Series(vals, index=merged.index), format="ISO8601", errors="coerce")
        merged.loc[not_imputed, col_dt] = parsed[not_imputed]

    # --- 3b. FINAL leak-safe lag/rolling features (computed on filled series) ---
    grp2 = merged.groupby(["train_number", "station_code"], sort=False)["delay_minutes"]
    merged["delay_lag_1"] = grp2.transform(lambda s: s.shift(1))
    merged["delay_lag_7"] = grp2.transform(lambda s: s.shift(7))
    merged["delay_rolling_mean_7"] = grp2.transform(lambda s: s.shift(1).rolling(7, min_periods=1).mean())
    merged["delay_rolling_mean_30"] = grp2.transform(lambda s: s.shift(1).rolling(30, min_periods=1).mean())
    # first day of each series has no lag/rolling history -> fill with the value itself
    for c in ["delay_lag_1", "delay_lag_7", "delay_rolling_mean_7", "delay_rolling_mean_30"]:
        merged[c] = merged[c].fillna(merged["delay_minutes"])

    # --- 4. CALENDAR FEATURES ---
    merged["is_weekend"] = merged["date"].dt.dayofweek.isin([5, 6]).astype(int)
    merged["is_special_day"] = merged["date"].dt.date.isin(special_dates).astype(int)

    # --- calibration provenance: which (train, station) pairs were anchored to real etrain.info data ---
    pair_keys = pd.Series(list(zip(merged["train_number"], merged["station_code"])), index=merged.index)
    merged["calibration_source"] = np.where(
        pair_keys.isin(calibrated_pairs), "real_etrain_calibrated", "synthetic_only"
    )

    # --- finalize output columns ---
    for col in ["scheduled_arrival_dt", "actual_arrival_dt", "scheduled_departure_dt", "actual_departure_dt"]:
        merged[col] = merged[col].astype("datetime64[ns]")

    out = pd.DataFrame({
        "date": merged["date"].dt.strftime("%Y-%m-%d"),
        "train_number": merged["train_number"],
        "station_code": merged["station_code"],
        "station_sequence": merged["station_sequence"],
        "scheduled_arrival": merged["scheduled_arrival_dt"].dt.strftime("%Y-%m-%dT%H:%M:%S"),
        "actual_arrival": merged["actual_arrival_dt"].dt.strftime("%Y-%m-%dT%H:%M:%S"),
        "scheduled_departure": merged["scheduled_departure_dt"].dt.strftime("%Y-%m-%dT%H:%M:%S"),
        "actual_departure": merged["actual_departure_dt"].dt.strftime("%Y-%m-%dT%H:%M:%S"),
        "delay_minutes": merged["delay_minutes"].round(1),
        "delay_lag_1": merged["delay_lag_1"].round(1),
        "delay_lag_7": merged["delay_lag_7"].round(1),
        "delay_rolling_mean_7": merged["delay_rolling_mean_7"].round(2),
        "delay_rolling_mean_30": merged["delay_rolling_mean_30"].round(2),
        "is_weekend": merged["is_weekend"],
        "is_special_day": merged["is_special_day"],
        "is_imputed": merged["is_imputed"],
        "is_synthetic": merged["is_synthetic"],
        "calibration_source": merged["calibration_source"],
    })
    out = out.sort_values(["train_number", "date", "station_sequence"]).reset_index(drop=True)
    out.to_csv(PROC / "new_historical_running_status.csv", index=False)
    print(f"Wrote {len(out)} rows to new_historical_running_status.csv "
          f"({out['is_imputed'].sum()} imputed rows, "
          f"{(out['calibration_source']=='real_etrain_calibrated').sum()} rows from real-calibrated pairs)")


if __name__ == "__main__":
    main()
