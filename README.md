# NDLS-CNB Railway Delay/Congestion Data Pipeline

Data acquisition pipeline for a delay/ETA/congestion/precedence ML system,
scoped to the **New Delhi (NDLS) -> Kanpur Central (CNB)** corridor via
Ghaziabad (GZB), Aligarh (ALJN), Tundla (TDL), Etawah (ETW).

No model training happens here - this repo only discovers, collects,
validates and normalizes data, and produces a unified
`master_training_dataset.csv`.

## Directory structure

```
data/
  raw/            cached, never-overwritten raw source files
    routes/       2017 IR timetable dump (itzmeanjan/indian-railway)
    stations.json datameet/railways station geodata
    status/       raw NTES live-status JSON (populated by 06b collector)
    weather/      raw Open-Meteo archive JSON per station
    infrastructure/ (reserved for future raw infra sources)
  processed/      final CSV outputs (see docs/SCHEMA.md)
  features/       (reserved for future feature-store exports)
  models/         (reserved for saved trained models)
  logs/           collector logs
src/              pipeline scripts, run in numeric order
notebooks/        train_delay_model.ipynb - Colab notebook for model training
docs/             schema documentation
data_quality_report.md  validation report
```

## Model training

[notebooks/train_delay_model.ipynb](notebooks/train_delay_model.ipynb) is a
Colab-ready notebook that trains and compares multiple regression models
(Ridge, Random Forest, Gradient Boosting, XGBoost, LightGBM, and an optional
LSTM sequence model) to predict `delay_next_station` from
`new_final_master_data.csv`, using a chronological (time-based) train/test
split appropriate for time-series data. It evaluates each model with
MAE/RMSE/R² and saves the best-performing model as `best_delay_model.pkl`.

## Pipeline (run in order)

```bash
python3 src/01_build_train_master_routes.py   # filter corridor trains -> train_master.csv, train_routes.csv
python3 src/01b_add_modern_trains.py          # add curated Vande Bharat services (post-2017)
python3 src/02_build_stations.py              # stations.csv (lat/lon/zone)
python3 src/03_build_priority_mapping.py      # priority_mapping.csv
python3 src/04_build_infrastructure.py        # station_infrastructure.csv, section_infrastructure.csv
python3 src/05_collect_weather.py             # weather_history.csv (Open-Meteo, real data)
python3 src/06_generate_historical_status.py  # historical_running_status.csv (SYNTHETIC BASELINE, never overwritten again)
python3 src/06b_ntes_live_collector.py        # OPTIONAL: requires RAILWAY_API_KEY, appends real rows
python3 src/09_scrape_etrain_history.py       # real_station_delay_stats.csv, special_days.csv (real, scraped)
python3 src/10_calibrate_and_fill.py          # -> new_historical_running_status.csv (calibrated vs real stats, gaps filled, lag/rolling/calendar features)
python3 src/07_build_master_dataset.py        # -> new_master_training_dataset.csv (feature engineering)
python3 src/11_build_final_master_data.py     # -> new_final_master_data.csv (fully-mapped FINAL training table)
python3 src/08_validate_and_report.py         # data_quality_report.md
```

Outputs prefixed `new_` are the current, calibrated/feature-complete datasets and
the recommended files for modeling. `historical_running_status.csv` (no prefix)
is the untouched synthetic baseline produced by step 06 and is never
overwritten by later steps - it is kept for comparison/reproducibility.

## Key data sources

| Dataset | Source | Type |
|---|---|---|
| train_master, train_routes | [itzmeanjan/indian-railway](https://github.com/itzmeanjan/indian-railway) (2017 dump, originally data.gov.in) | Real, static |
| stations (lat/lon/zone) | [datameet/railways](https://github.com/datameet/railways) stations.json | Real, static |
| weather_history | [Open-Meteo Historical Weather API](https://open-meteo.com/) | Real, live-fetched |
| historical_running_status | Synthetic generator, calibrated against real etrain.info averages, gaps filled via lag/rolling | Hybrid (synthetic + real-calibrated) |
| real_station_delay_stats | [etrain.info](https://etrain.info) running-history pages (scraped) | Real |
| special_days (festival calendar) | etrain.info (2026) + curated (H2 2025) | Real + curated |
| station/section infrastructure | platforms/tracks from Wikipedia infoboxes; loop lines/category curated | Real (partial) + curated estimate |
| priority_mapping | Curated per spec | Curated |

Sources investigated but not usable without registration/keys or with no
public API: NTES (no public JSON API), RailYatri, ConfirmTkt, Trainman
(scraping-hostile, no historical archive), Indian Rail API /
railwayapi.com (require a registered API key - supported via
`06b_ntes_live_collector.py`).

See [docs/SCHEMA.md](docs/SCHEMA.md) and
[data_quality_report.md](data_quality_report.md) for full details,
including known limitations and assumptions.

## Web app: Railway Digital Twin (backend + frontend)

A live digital-twin web app simulates the NDLS<->CNB corridor on top of
`new_final_master_data.csv`, predicting per-train delays (LightGBM model if
`backend/models/best_delay_model.pkl` + metadata are present, otherwise a
deterministic `0.5*station_avg_delay + 0.5*train_avg_delay` fallback) and
exposing a REST + WebSocket API consumed by a React frontend. No Redis/Celery
is required - background simulation runs as an in-process asyncio loop.

### Run the backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Optional: set `ANTHROPIC_API_KEY` (and optionally `ANTHROPIC_MODEL`) to enable
the Claude-powered AI controller assistant at `/api/ai/ask`. Without it, the
assistant falls back to a deterministic template answer on the backend, and
the frontend additionally tries client-side `puter.js` (loaded via
`index.html`) for a richer answer.

The live simulation is driven by `data/processed/demo_day_master_data.csv`, a
small (~350KB, ~1.3k row) extract of `new_final_master_data.csv` containing
only the demo day's (`DEMO_DATE`) corridor rows. This file is committed to git
so the app is deployable without the full ~130MB training dataset. To use a
different/larger dataset, set `MASTER_DATA_URL` to a direct CSV URL (e.g. a
Google Sheets "Publish to web -> CSV" link, NOT an `/edit` link).

### Run the frontend

```bash
cd frontend
npm install
npm run dev
```

Visit the printed local URL (e.g. http://localhost:5173) and sign in with one
of the demo accounts:

| Role | Username | Password | Notes |
|---|---|---|---|
| Admin | `admin` | `admin123` | Full access incl. Controller console |
| Controller | `controller` | `controller123` | Can apply recommendations & toggle Auto-Controller mode |
| Viewer | `viewer` | `viewer123` | Read-only dashboards/analytics |

### Features

- **Dashboard / Digital Twin**: live corridor map with train-type icons,
  click a station to see platform/track infrastructure and trains
  currently in that section.
- **Trains / Train Detail / Analytics**: search, per-stop delay timeline,
  corridor-wide KPI and delay-distribution charts.
- **AI Controller Recommendations**: auto-generated per-train suggestions
  based on predicted delay severity; admins/controllers can "Apply" them.
- **Controller console** (`/controller`, admin/controller only): toggle
  Auto-Controller mode (auto-applies critical recommendations) and view the
  action log.
- **AI Controller Assistant**: floating chat widget, Claude API -> template
  -> puter.js fallback chain.
