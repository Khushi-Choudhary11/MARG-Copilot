# Data Quality Report
Generated: 2026-06-13T20:02:57.467792

Scope: NDLS-CNB corridor (NDLS -> GZB -> ALJN -> TDL -> ETW -> CNB). 82 trains identified as crossing this corridor.

## 1. Missing Values (% per column)


**train_master.csv**
- No missing values.

**train_routes.csv**
- No missing values.

**stations.csv**
- `latitude`: 1.22% missing
- `longitude`: 1.22% missing

**historical_running_status.csv (synthetic baseline)**
- `scheduled_arrival`: 0.63% missing
- `actual_arrival`: 0.63% missing
- `scheduled_departure`: 0.63% missing
- `actual_departure`: 0.63% missing

**new_historical_running_status.csv (calibrated+filled)**
- `scheduled_arrival`: 0.62% missing
- `actual_arrival`: 0.62% missing
- `scheduled_departure`: 0.62% missing
- `actual_departure`: 0.62% missing

**weather_history.csv**
- `visibility_km`: 100.0% missing

**new_master_training_dataset.csv**
- `previous_station_delay`: 6.47% missing
- `visibility`: 100.0% missing
- `rainfall`: 80.66% missing
- `temperature`: 80.66% missing
- `humidity`: 80.66% missing
- `track_count`: 80.66% missing
- `platform_count`: 80.66% missing
- `electrified`: 80.66% missing
- `max_speed_kmh`: 80.66% missing
- `congestion_score`: 80.66% missing
- `delay_next_station`: 6.47% missing

**new_final_master_data.csv**
- `scheduled_arrival`: 0.62% missing
- `actual_arrival`: 0.62% missing
- `scheduled_departure`: 0.62% missing
- `actual_departure`: 0.62% missing
- `previous_station_delay`: 6.47% missing
- `delay_next_station`: 6.47% missing
- `temperature`: 80.66% missing
- `humidity`: 80.66% missing
- `rainfall`: 80.66% missing
- `visibility`: 100.0% missing
- `track_count`: 80.66% missing
- `platform_count`: 80.66% missing
- `electrified`: 80.66% missing
- `max_speed_kmh`: 80.66% missing
- `congestion_score`: 80.66% missing

## 2. Duplicate Records

- train_routes.csv duplicate (train_number, station_code, station_sequence): 0
- new_historical_running_status.csv duplicate (train_number, station_code, date): 0
- stations.csv duplicate station_code: 0

## 3. Invalid Station Codes

- Station codes in train_routes.csv missing from stations.csv: none
- Station codes in new_historical_running_status.csv missing from stations.csv: none

## 4. Negative Delays

- Rows with delay_minutes < 0: 168365 (36.41% of 462455)
  (Small negative values represent trains running early; clipped at -10 min in the synthetic generator.)
- Rows with delay_minutes < -10 (should be 0 by construction): 0

## 5. Timestamp Mismatches

- Rows where actual_departure < actual_arrival: 420 (0.091%)
  (Residual cases come from intermediate stations in the source timetable that carry a `00:00:00` placeholder departure time, which is not a true terminus - a known artifact of the 2017 source dump.)
- Rows with delay_minutes > 600 (10h, likely erroneous): 0

## 6. Calibration & Imputation Summary

- Real (train, station) average-delay pairs scraped from etrain.info (last year): 187 pairs across 73 trains, used to calibrate the synthetic delay series via an additive per-pair offset.
- Cancelled-service gaps filled via lag/rolling imputation: 9532 of 462455 rows (2.06%), using lag_1 -> rolling_mean_7 -> rolling_mean_30 -> train mean -> 0, in that priority order.
- is_weekend=1 for 131768 rows (28.5%); is_special_day=1 for 40544 rows (8.8%), based on special_days.csv (Indian festival/holiday calendar, scraped + curated).

## 7. Known Limitations & Assumptions

- **train_master.csv / train_routes.csv**: sourced from a 2017 Indian Railways timetable dump (itzmeanjan/indian-railway, originally data.gov.in). 82 trains matched as crossing NDLS<->CNB. `operating_days` is UNKNOWN for these 78 trains (not present in source data) - needs enrichment from NTES live collector. 4 modern trains (Vande Bharat services) were manually added with curated routes and known operating-day exceptions.
- **historical_running_status.csv**: SYNTHETIC (is_synthetic=1 for all rows). Real per-train historical running data is not available as a bulk download from any public source; NTES/RailYatri/ConfirmTkt/Trainman expose only live status, no historical archive. 06b_ntes_live_collector.py is provided to accumulate REAL rows (is_synthetic=0) going forward once a railwayapi.com/indianrailapi.com API key is configured.
- **weather_history.csv**: REAL data from Open-Meteo Historical Weather API (archive-api.open-meteo.com), hourly, for the 6 corridor stations over the past 365 days. `visibility_km` is always NaN - Open-Meteo's archive API does not provide a visibility variable; `fog_indicator` is derived instead from the WMO weather code (45/48 = fog).
- **station_infrastructure.csv / section_infrastructure.csv**: curated estimates (source=`curated_estimate`), not from an official track-diagram dataset. Should be verified against zonal railway track charts before production use.
- **stations.csv**: lat/lon and zone from datameet/railways stations.json. railway_division is UNKNOWN for stations outside the curated corridor lookup (238 of 245 stations).
- **master_training_dataset.csv**: weather/track/platform/congestion features are only populated for the 6 corridor stations (~19% of rows); all other stations on a train's route have NaN for these columns, per the 'station-specific weather, never corridor-wide' join rule.
- **real_station_delay_stats.csv**: scraped live from etrain.info (`/train/x-<train_number>/history?d=1y`). Coverage: 73/82 trains returned data; 2 trains (12553/12554) returned HTTP 404 (renumbered/discontinued since the 2017 source dump), and several trains' current real-world routing no longer passes through all 6 corridor stations (e.g. 12309 now routes via Prayagraj, not GZB/ALJN/TDL/ETW) - only the corridor stations actually present on etrain's route for that train were captured.
- **special_days.csv**: 2026 Indian festival/holiday calendar scraped from etrain.info (embedded `holiDay` JS object); Jun-Dec 2025 portion is a curated supplement (etrain only serves the current calendar year's calendar).
