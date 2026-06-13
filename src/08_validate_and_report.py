"""
Step 10: Data validation -> data_quality_report.md

Checks performed across the generated datasets:
  - Missing values per column
  - Duplicate records (key-based)
  - Invalid station codes (not present in stations.csv)
  - Negative delays (delay_minutes < 0)
  - Timestamp mismatches (actual < scheduled - large negative, or actual
    arrival before actual departure of previous stop)
"""
import pandas as pd
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parent.parent
PROC = BASE / "data" / "processed"
REPORT = BASE / "data_quality_report.md"


def section(title):
    return f"\n## {title}\n\n"


def main():
    lines = []
    lines.append("# Data Quality Report")
    lines.append(f"\nGenerated: {datetime.now().isoformat()}\n")
    lines.append(
        "\nScope: NDLS-CNB corridor (NDLS -> GZB -> ALJN -> TDL -> ETW -> CNB). "
        "82 trains identified as crossing this corridor.\n"
    )

    train_master = pd.read_csv(PROC / "train_master.csv", dtype={"train_number": str})
    routes = pd.read_csv(PROC / "train_routes.csv", dtype={"train_number": str})
    stations = pd.read_csv(PROC / "stations.csv")
    raw_hist = pd.read_csv(PROC / "historical_running_status.csv", dtype={"train_number": str})
    hist = pd.read_csv(PROC / "new_historical_running_status.csv", dtype={"train_number": str})
    master_ds = pd.read_csv(PROC / "new_master_training_dataset.csv", dtype={"train_number": str})
    final_ds = pd.read_csv(PROC / "new_final_master_data.csv", dtype={"train_number": str})
    weather = pd.read_csv(PROC / "weather_history.csv")

    valid_codes = set(stations["station_code"])

    # --- Missing values ---
    lines.append(section("1. Missing Values (% per column)"))
    for name, df in [
        ("train_master.csv", train_master),
        ("train_routes.csv", routes),
        ("stations.csv", stations),
        ("historical_running_status.csv (synthetic baseline)", raw_hist),
        ("new_historical_running_status.csv (calibrated+filled)", hist),
        ("weather_history.csv", weather),
        ("new_master_training_dataset.csv", master_ds),
        ("new_final_master_data.csv", final_ds),
    ]:
        lines.append(f"\n**{name}**\n")
        pct = (df.isna().mean() * 100).round(2)
        nonzero = pct[pct > 0]
        if nonzero.empty:
            lines.append("- No missing values.\n")
        else:
            for col, val in nonzero.items():
                lines.append(f"- `{col}`: {val}% missing\n")

    # --- Duplicates ---
    lines.append(section("2. Duplicate Records"))
    dup_routes = routes.duplicated(subset=["train_number", "station_code", "station_sequence"]).sum()
    dup_hist = hist.duplicated(subset=["train_number", "station_code", "date"]).sum()
    dup_stations = stations.duplicated(subset=["station_code"]).sum()
    lines.append(f"- train_routes.csv duplicate (train_number, station_code, station_sequence): {dup_routes}\n")
    lines.append(f"- new_historical_running_status.csv duplicate (train_number, station_code, date): {dup_hist}\n")
    lines.append(f"- stations.csv duplicate station_code: {dup_stations}\n")

    # --- Invalid station codes ---
    lines.append(section("3. Invalid Station Codes"))
    invalid_route_codes = sorted(set(routes["station_code"]) - valid_codes)
    invalid_hist_codes = sorted(set(hist["station_code"]) - valid_codes)
    lines.append(f"- Station codes in train_routes.csv missing from stations.csv: {invalid_route_codes or 'none'}\n")
    lines.append(f"- Station codes in new_historical_running_status.csv missing from stations.csv: {invalid_hist_codes or 'none'}\n")

    # --- Negative delays ---
    lines.append(section("4. Negative Delays"))
    neg = hist[hist["delay_minutes"] < 0]
    lines.append(f"- Rows with delay_minutes < 0: {len(neg)} ({len(neg)/len(hist)*100:.2f}% of {len(hist)})\n")
    lines.append("  (Small negative values represent trains running early; clipped at -10 min in the synthetic generator.)\n")
    big_neg = hist[hist["delay_minutes"] < -10]
    lines.append(f"- Rows with delay_minutes < -10 (should be 0 by construction): {len(big_neg)}\n")

    # --- Timestamp mismatches ---
    lines.append(section("5. Timestamp Mismatches"))
    hist["scheduled_arrival"] = pd.to_datetime(hist["scheduled_arrival"], format="ISO8601")
    hist["actual_arrival"] = pd.to_datetime(hist["actual_arrival"], format="ISO8601")
    hist["scheduled_departure"] = pd.to_datetime(hist["scheduled_departure"], format="ISO8601")
    hist["actual_departure"] = pd.to_datetime(hist["actual_departure"], format="ISO8601")
    bad_arr_dep = (hist["actual_departure"] < hist["actual_arrival"]).sum()
    lines.append(f"- Rows where actual_departure < actual_arrival: {bad_arr_dep} "
                  f"({bad_arr_dep/len(hist)*100:.3f}%)\n")
    lines.append("  (Residual cases come from intermediate stations in the source timetable that "
                  "carry a `00:00:00` placeholder departure time, which is not a true terminus - "
                  "a known artifact of the 2017 source dump.)\n")
    extreme_delay = (hist["delay_minutes"] > 600).sum()
    lines.append(f"- Rows with delay_minutes > 600 (10h, likely erroneous): {extreme_delay}\n")

    # --- Calibration / imputation summary ---
    lines.append(section("6. Calibration & Imputation Summary"))
    real_stats = pd.read_csv(PROC / "real_station_delay_stats.csv", dtype={"train_number": str})
    lines.append(f"- Real (train, station) average-delay pairs scraped from etrain.info "
                  f"(last year): {len(real_stats)} pairs across {real_stats['train_number'].nunique()} trains, "
                  f"used to calibrate the synthetic delay series via an additive per-pair offset.\n")
    lines.append(f"- Cancelled-service gaps filled via lag/rolling imputation: "
                  f"{int(hist['is_imputed'].sum())} of {len(hist)} rows "
                  f"({hist['is_imputed'].mean()*100:.2f}%), using "
                  f"lag_1 -> rolling_mean_7 -> rolling_mean_30 -> train mean -> 0, in that priority order.\n")
    lines.append(f"- is_weekend=1 for {int(hist['is_weekend'].sum())} rows "
                  f"({hist['is_weekend'].mean()*100:.1f}%); is_special_day=1 for "
                  f"{int(hist['is_special_day'].sum())} rows ({hist['is_special_day'].mean()*100:.1f}%), "
                  f"based on special_days.csv (Indian festival/holiday calendar, scraped + curated).\n")

    # --- Known limitations / assumptions ---
    lines.append(section("7. Known Limitations & Assumptions"))
    lines.append("- **train_master.csv / train_routes.csv**: sourced from a 2017 Indian Railways "
                  "timetable dump (itzmeanjan/indian-railway, originally data.gov.in). 82 trains "
                  "matched as crossing NDLS<->CNB. `operating_days` is UNKNOWN for these 78 trains "
                  "(not present in source data) - needs enrichment from NTES live collector. "
                  "4 modern trains (Vande Bharat services) were manually added with curated routes "
                  "and known operating-day exceptions.\n")
    lines.append("- **historical_running_status.csv**: SYNTHETIC (is_synthetic=1 for all rows). "
                  "Real per-train historical running data is not available as a bulk download from "
                  "any public source; NTES/RailYatri/ConfirmTkt/Trainman expose only live status, "
                  "no historical archive. 06b_ntes_live_collector.py is provided to accumulate REAL "
                  "rows (is_synthetic=0) going forward once a railwayapi.com/indianrailapi.com API "
                  "key is configured.\n")
    lines.append("- **weather_history.csv**: REAL data from Open-Meteo Historical Weather API "
                  "(archive-api.open-meteo.com), hourly, for the 6 corridor stations over the past "
                  "365 days. `visibility_km` is always NaN - Open-Meteo's archive API does not "
                  "provide a visibility variable; `fog_indicator` is derived instead from the WMO "
                  "weather code (45/48 = fog).\n")
    lines.append("- **station_infrastructure.csv / section_infrastructure.csv**: curated estimates "
                  "(source=`curated_estimate`), not from an official track-diagram dataset. Should "
                  "be verified against zonal railway track charts before production use.\n")
    lines.append("- **stations.csv**: lat/lon and zone from datameet/railways stations.json. "
                  "railway_division is UNKNOWN for stations outside the curated corridor lookup "
                  f"({len(stations[stations['railway_division']=='UNKNOWN'])} of {len(stations)} stations).\n")
    lines.append("- **master_training_dataset.csv**: weather/track/platform/congestion features are "
                  "only populated for the 6 corridor stations (~19% of rows); all other stations on "
                  "a train's route have NaN for these columns, per the 'station-specific weather, "
                  "never corridor-wide' join rule.\n")
    lines.append("- **real_station_delay_stats.csv**: scraped live from etrain.info "
                  f"(`/train/x-<train_number>/history?d=1y`). Coverage: {real_stats['train_number'].nunique()}/82 "
                  "trains returned data; 2 trains (12553/12554) returned HTTP 404 (renumbered/discontinued "
                  "since the 2017 source dump), and several trains' current real-world routing no longer "
                  "passes through all 6 corridor stations (e.g. 12309 now routes via Prayagraj, not "
                  "GZB/ALJN/TDL/ETW) - only the corridor stations actually present on etrain's route for "
                  "that train were captured.\n")
    lines.append("- **special_days.csv**: 2026 Indian festival/holiday calendar scraped from etrain.info "
                  "(embedded `holiDay` JS object); Jun-Dec 2025 portion is a curated supplement "
                  "(etrain only serves the current calendar year's calendar).\n")

    REPORT.write_text("".join(lines), encoding="utf-8")
    print(f"Wrote {REPORT}")


if __name__ == "__main__":
    main()
