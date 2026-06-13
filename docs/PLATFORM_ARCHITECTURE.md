# NDLS↔CNB Railway Digital Twin Platform — Architecture

This document is the production architecture for the **Railway Operations
Platform / Digital Twin / AI Controller Assistant** built around the
already-trained `best_delay_model.pkl` (LightGBM) and the datasets in
`data/processed/` (notably `new_final_master_data.csv`,
`station_infrastructure.csv`, `section_infrastructure.csv`,
`new_historical_running_status.csv`, `weather_history.csv`).

Scope is fixed to the **NDLS → GZB → ALJN → TDL → ETW → CNB** corridor and its
intermediate stations. Nothing here is designed for an all-India rollout.

---

## 1. High-Level System Overview

```
                 ┌─────────────────────────────────────────────┐
                 │              React Frontend (Vite)           │
                 │  Dashboard / Controller / Admin / User views │
                 │  Digital Twin canvas (React Flow + Leaflet)  │
                 └──────────────┬───────────────┬───────────────┘
                                 │ REST (React Query)            │ WebSocket
                                 ▼                                ▼
                 ┌─────────────────────────────────────────────┐
                 │                FastAPI Backend               │
                 │  api/ (auth, trains, stations, predictions,  │
                 │        congestion, recommendations, twin)    │
                 │  services/ (lightgbm, claude, congestion,    │
                 │             precedence, tracking, weather)    │
                 └───────┬───────────┬────────────┬─────────────┘
                         │           │            │
                ┌────────▼───┐ ┌─────▼─────┐ ┌────▼─────┐
                │ PostgreSQL │ │   Redis   │ │  Celery   │
                │ (state,    │ │ (cache,   │ │ (60s tick,│
                │  history,  │ │  pub/sub  │ │  retrain  │
                │  users)    │ │  for WS)  │ │  jobs)    │
                └────────────┘ └───────────┘ └───────────┘
                         │
                ┌────────▼─────────────────────────────────┐
                │ best_delay_model.pkl (LightGBM) +          │
                │ new_final_master_data.csv (seed/training)  │
                │ Claude API (recommendation/explanation)    │
                └─────────────────────────────────────────────┘
```

**Core loop (every 60s, via Celery beat):**
1. Pull/refresh live train positions + delays (live feed or simulated replay
   of `new_historical_running_status.csv` if no live feed is configured).
2. Build the feature row per (train, next station) exactly as in
   `new_final_master_data.csv` (current_delay, lag/rolling features, weather,
   infra, congestion, calendar).
3. Call `lightgbm_service.predict()`. **Fallback**: if the model errors or a
   feature is unavailable, fall back to
   `0.5*station_average_delay + 0.5*train_average_delay` (configurable
   weights) — the system must always return a number.
4. Persist predictions to Postgres, push deltas via Redis pub/sub → WebSocket.
5. Recompute congestion scores per station/platform.
6. If AI Auto Mode is on, or a controller requests it, call
   `claude_service` to generate recommendations + explanations.

---

## 2. Folder Structure

```
frontend/
  src/
    api/                     # typed API client (axios/fetch wrappers per resource)
    auth/                    # login, token storage, route guards
    components/
      common/                # Button, Modal, Badge, Spinner, Toast, etc.
      layout/
        navbar/
        sidebar/
      cards/                 # StatCard, TrainCard, AlertCard
      charts/                # wrappers around Recharts (DelayTrend, Heatmap)
      maps/                  # Leaflet/Mapbox corridor map components
      digitalTwin/
        trainAnimation/      # animated train markers, position interpolation
        trackVisualization/  # SVG/React Flow track segments + color states
        platformVisualization/
        signals/             # signal aspect icons + state
        occupancy/            # track/platform occupancy overlays
      controller/
        recommendations/     # AI recommendation list + accept/reject UI
        decisionPanel/       # manual override controls
      user/
        trainSearch/
        trainTracking/
        delayForecast/
      admin/
        controllerManagement/
        analytics/
    pages/
      Dashboard/
      Controller/
      Admin/
      User/
      Login/
      Settings/
    hooks/                   # useTrainPositions, useWebSocket, usePredictions...
    store/                   # Zustand/Redux: session, twin state, ui state
    routes/                  # react-router route definitions + guards
    services/                # websocket client, notification service
    utils/                   # formatters, time/corridor helpers
    types/                   # shared TS types (mirrors backend Pydantic schemas)
    assets/
  public/

backend/
  app/
    api/
      auth/
      controllers/           # /controllers CRUD (admin-managed controller accounts)
      users/
      admin/
      trains/
      stations/
      tracks/
      platforms/
      predictions/
      congestion/
      recommendations/
      digital_twin/
    services/
      delay_prediction/
        lightgbm_service.py
        feature_builder.py   # builds the exact new_final_master_data.csv row
        fallback_service.py  # station/train average fallback
      congestion_service.py
      precedence_service.py
      claude_service.py
      tracking_service.py    # live position simulation/ingestion
      weather_service.py      # Open-Meteo refresh
    repositories/            # DB access layer (one per entity)
    models/                  # SQLAlchemy ORM models
    schemas/                 # Pydantic request/response schemas
    database/
      postgres/              # session, migrations (alembic)
      redis/                 # connection, pub/sub helpers
    tasks/                   # Celery tasks (tick, retrain, weather refresh)
    websocket/               # connection manager, channel definitions
    core/                    # settings, security, logging config
    middleware/
    config/
    logs/
  tests/
  data/                       # symlink or copy of data/processed for seeding
  models/                     # best_delay_model.pkl + metadata.pkl + lstm (optional)
```

---

## 3. PostgreSQL Schema

```sql
-- ── Reference / static corridor data (seeded from data/processed/*.csv) ──
CREATE TABLE stations (
    station_code        VARCHAR(8) PRIMARY KEY,
    station_name        TEXT NOT NULL,
    latitude            DOUBLE PRECISION,
    longitude           DOUBLE PRECISION,
    railway_division    TEXT,
    railway_zone        TEXT,
    sequence_on_corridor SMALLINT      -- 1=NDLS ... N=CNB, NULL if not on corridor
);

CREATE TABLE station_infrastructure (
    station_code     VARCHAR(8) PRIMARY KEY REFERENCES stations(station_code),
    platforms        SMALLINT,
    main_tracks      SMALLINT,
    loop_lines       SMALLINT,
    junction_flag    BOOLEAN,
    station_category TEXT,
    electrified      BOOLEAN,
    traction_type    TEXT,
    gauge            TEXT
);

CREATE TABLE section_infrastructure (
    id                 SERIAL PRIMARY KEY,
    from_station       VARCHAR(8) REFERENCES stations(station_code),
    to_station         VARCHAR(8) REFERENCES stations(station_code),
    num_tracks         SMALLINT,
    line_type          TEXT,
    section_length_km  DOUBLE PRECISION,
    electrified        BOOLEAN,
    max_speed_kmh      SMALLINT
);

CREATE TABLE trains (
    train_number             VARCHAR(6) PRIMARY KEY,
    train_name               TEXT,
    train_type               TEXT,
    priority                 SMALLINT,
    source_station_code      VARCHAR(8) REFERENCES stations(station_code),
    destination_station_code VARCHAR(8) REFERENCES stations(station_code),
    corridor_direction        TEXT          -- 'DOWN (NDLS->CNB)' / 'UP (CNB->NDLS)'
);

CREATE TABLE train_routes (
    id                  SERIAL PRIMARY KEY,
    train_number        VARCHAR(6) REFERENCES trains(train_number),
    station_code        VARCHAR(8) REFERENCES stations(station_code),
    station_sequence    SMALLINT,
    distance_km         DOUBLE PRECISION,
    scheduled_arrival   TIME,
    scheduled_departure TIME,
    halt_minutes        SMALLINT,
    UNIQUE (train_number, station_sequence)
);

CREATE TABLE priority_mapping (
    train_type  TEXT PRIMARY KEY,
    priority    SMALLINT,
    description TEXT
);

-- ── Historical / training data (loaded from new_final_master_data.csv) ──
CREATE TABLE historical_delays (
    id                     BIGSERIAL PRIMARY KEY,
    train_number           VARCHAR(6),
    station_code           VARCHAR(8),
    date                   DATE,
    station_sequence       SMALLINT,
    scheduled_arrival      TIMESTAMP,
    actual_arrival         TIMESTAMP,
    scheduled_departure    TIMESTAMP,
    actual_departure       TIMESTAMP,
    current_delay          REAL,
    delay_next_station     REAL,
    delay_lag_1            REAL,
    delay_lag_7            REAL,
    delay_rolling_mean_7   REAL,
    delay_rolling_mean_30  REAL,
    is_weekend             BOOLEAN,
    is_special_day         BOOLEAN,
    is_imputed             BOOLEAN,
    is_synthetic           BOOLEAN,
    calibration_source     TEXT,
    UNIQUE (train_number, station_code, date)
);
CREATE INDEX idx_hist_train_station_date ON historical_delays (train_number, station_code, date);

-- ── Live operational state (digital twin) ──
CREATE TABLE live_train_state (
    train_number        VARCHAR(6) PRIMARY KEY REFERENCES trains(train_number),
    current_station_code VARCHAR(8) REFERENCES stations(station_code),
    next_station_code    VARCHAR(8) REFERENCES stations(station_code),
    progress_pct          REAL,            -- 0-100 between current and next station
    current_delay_min     REAL,
    predicted_next_delay  REAL,
    predicted_at          TIMESTAMP,
    prediction_source      TEXT,            -- 'lightgbm' | 'fallback'
    speed_kmh              REAL,
    status                  TEXT,            -- 'running' | 'halted' | 'terminated'
    assigned_platform       SMALLINT,
    assigned_track_type     TEXT,            -- 'main' | 'loop' | 'siding'
    updated_at              TIMESTAMP DEFAULT now()
);

CREATE TABLE track_occupancy (
    id              BIGSERIAL PRIMARY KEY,
    section_id      INTEGER REFERENCES section_infrastructure(id),
    track_type      TEXT,                  -- main/loop/platform/siding
    occupied_by     VARCHAR(6) REFERENCES trains(train_number),
    state           TEXT,                  -- free/occupied/blocked/reserved
    updated_at      TIMESTAMP DEFAULT now()
);

CREATE TABLE platform_occupancy (
    id              BIGSERIAL PRIMARY KEY,
    station_code    VARCHAR(8) REFERENCES stations(station_code),
    platform_number SMALLINT,
    occupied_by     VARCHAR(6) REFERENCES trains(train_number),
    expected_arrival   TIMESTAMP,
    expected_departure TIMESTAMP,
    state              TEXT,               -- free/occupied/reserved
    updated_at         TIMESTAMP DEFAULT now()
);

CREATE TABLE signals (
    id            BIGSERIAL PRIMARY KEY,
    station_code  VARCHAR(8) REFERENCES stations(station_code),
    signal_code   TEXT,
    aspect        TEXT,                    -- red/yellow/green/double-yellow
    updated_at    TIMESTAMP DEFAULT now()
);

-- ── AI recommendations / decisions ──
CREATE TABLE recommendations (
    id                BIGSERIAL PRIMARY KEY,
    created_at        TIMESTAMP DEFAULT now(),
    train_number      VARCHAR(6),
    station_code      VARCHAR(8),
    action_type       TEXT,                -- precedence/hold/platform_change/crossing
    recommendation    TEXT,                -- human-readable text
    explanation       JSONB,               -- {reason, expected_delay_reduction, ...}
    confidence        REAL,
    risk_level        TEXT,                -- low/medium/high
    status            TEXT,                -- pending/accepted/rejected/auto_applied
    decided_by        INTEGER REFERENCES users(id),
    decided_at        TIMESTAMP
);

-- ── Users / RBAC ──
CREATE TABLE users (
    id            SERIAL PRIMARY KEY,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL,           -- admin/controller/user
    full_name     TEXT,
    created_at    TIMESTAMP DEFAULT now()
);

CREATE TABLE controller_assignments (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER REFERENCES users(id),
    station_codes   TEXT[],                -- stations/sections this controller manages
    assigned_by     INTEGER REFERENCES users(id),
    assigned_at     TIMESTAMP DEFAULT now()
);

CREATE TABLE audit_log (
    id          BIGSERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id),
    action      TEXT,
    target_type TEXT,
    target_id   TEXT,
    metadata    JSONB,
    created_at  TIMESTAMP DEFAULT now()
);

CREATE TABLE system_settings (
    key   TEXT PRIMARY KEY,                -- 'ai_auto_mode', 'prediction_interval_sec', ...
    value JSONB
);
```

---

## 4. API Endpoints (FastAPI)

All endpoints under `/api/v1`. JWT auth (`Authorization: Bearer <token>`).

### Auth
| Method | Path | Description |
|---|---|---|
| POST | `/auth/login` | Email+password → JWT |
| POST | `/auth/refresh` | Refresh access token |
| GET  | `/auth/me` | Current user profile |

### Stations / Tracks / Platforms (read-mostly, admin write)
| Method | Path | Description |
|---|---|---|
| GET | `/stations` | List corridor stations with infra |
| GET | `/stations/{code}` | Station detail (platforms, tracks, category) |
| GET | `/stations/{code}/platforms` | Platform occupancy snapshot |
| GET | `/tracks/sections` | Section infra (NDLS-GZB, GZB-ALJN, ...) |
| GET | `/tracks/occupancy` | Live occupancy per section/track |
| GET | `/signals` | Live signal states |

### Trains
| Method | Path | Description |
|---|---|---|
| GET | `/trains` | List corridor trains (filter by direction/type/priority) |
| GET | `/trains/{train_number}` | Train detail + route |
| GET | `/trains/{train_number}/live` | Live position, delay, predicted delay |
| GET | `/trains/{train_number}/history` | Historical delay series (for charts) |
| GET | `/trains/search?q=` | Search by number/name |

### Predictions
| Method | Path | Description |
|---|---|---|
| GET | `/predictions/{train_number}/next-station` | Predicted `delay_next_station` + source (model/fallback) |
| POST | `/predictions/batch` | Batch predict for all active trains (used by Celery tick) |
| GET | `/predictions/accuracy` | Rolling accuracy metrics (MAE/RMSE) for analytics |

### Congestion
| Method | Path | Description |
|---|---|---|
| GET | `/congestion/stations` | Per-station congestion score (current + predicted) |
| GET | `/congestion/heatmap` | Time x station matrix for heatmap chart |

### Recommendations / AI
| Method | Path | Description |
|---|---|---|
| GET | `/recommendations` | List pending/recent recommendations |
| POST | `/recommendations/{id}/accept` | Controller accepts |
| POST | `/recommendations/{id}/reject` | Controller rejects (with reason) |
| POST | `/recommendations/generate` | Force-generate for a given train/station (Claude) |
| GET | `/ai/settings` | Auto-mode status, model config |
| POST | `/ai/settings` | Admin: toggle auto mode, thresholds |

### Digital Twin
| Method | Path | Description |
|---|---|---|
| GET | `/digital-twin/snapshot` | Full current state: trains, occupancy, signals, congestion |
| WS  | `/ws/digital-twin` | Live push of state deltas (see §6) |

### Admin
| Method | Path | Description |
|---|---|---|
| GET/POST | `/admin/users` | List/create users |
| GET/POST | `/admin/controllers` | Manage controller assignments |
| GET | `/admin/analytics/*` | Delay-by-station, delay-by-train, AI acceptance rate, etc. |
| GET | `/admin/audit-log` | Audit trail |

---

## 5. LightGBM Integration

`services/delay_prediction/lightgbm_service.py`:

```python
import joblib

class LightGBMDelayService:
    def __init__(self, model_path="models/best_delay_model.pkl",
                 meta_path="models/best_delay_model_metadata.pkl"):
        self.pipeline = joblib.load(model_path)
        self.meta = joblib.load(meta_path)

    def predict(self, feature_row: dict) -> float:
        import pandas as pd
        df = pd.DataFrame([feature_row])[
            self.meta["numeric_features"] + self.meta["categorical_features"]
        ]
        return float(self.pipeline.predict(df)[0])
```

`feature_builder.py` assembles `feature_row` with **exactly** the columns
documented in `docs/SCHEMA.md` for `new_final_master_data.csv`
(`current_delay`, `previous_station_delay`, `train_average_delay`,
`station_average_delay`, `delay_lag_1/7`, `delay_rolling_mean_7/30`,
`priority`, `hour_of_day`, `day_of_week`, `month`, `is_weekend`,
`is_special_day`, weather, `track_count`, `platform_count`, `electrified`,
`max_speed_kmh`, `congestion_score`, `is_corridor_station`, `is_imputed`,
`station_code`, `train_type`, `corridor_direction`, `calibration_source`),
pulling live values where available and falling back to the most recent
historical value for that (train, station) for anything not yet observed
today (e.g. weather for the next station fetched via `weather_service`).

`fallback_service.py`:

```python
def fallback_delay(train_number, station_code, repo) -> float:
    station_avg = repo.get_station_average_delay(station_code)
    train_avg = repo.get_train_average_delay(train_number)
    return 0.5 * station_avg + 0.5 * train_avg
```

`lightgbm_service.predict()` is always wrapped in try/except in the API
layer; on any exception, `fallback_delay()` is used and
`prediction_source='fallback'` is recorded — the system never returns an
error for a prediction request.

Retraining: a Celery periodic task can re-run
`src/07_build_master_dataset.py` + `src/11_build_final_master_data.py`
equivalents against `historical_delays` (now augmented with live data) and
retrain via the same notebook logic, versioning models as
`best_delay_model_v{n}.pkl`.

---

## 6. WebSocket Architecture

Single endpoint `/ws/digital-twin`, channel-based using Redis pub/sub so
multiple FastAPI workers stay in sync:

- **Channels**: `twin:trains`, `twin:occupancy`, `twin:signals`,
  `twin:congestion`, `twin:recommendations`.
- Celery tick (every 60s) publishes deltas to these Redis channels.
- `websocket/connection_manager.py` subscribes once per worker and fans out
  to connected clients, optionally filtered by the client's role/assigned
  stations (controllers only get their assigned section's detail; user
  dashboard gets corridor-wide summary).
- Message envelope:
  ```json
  { "channel": "twin:trains", "type": "update", "ts": "...",
    "data": [ { "train_number": "12004", "station_code": "ALJN",
                 "progress_pct": 42.5, "current_delay": 7,
                 "predicted_next_delay": 9.3, "prediction_source": "lightgbm" } ] }
  ```
- Frontend `useWebSocket` hook reconnects with backoff and merges deltas into
  the `store/` twin slice; React Query handles the initial
  `/digital-twin/snapshot` REST fetch for first paint.

---

## 7. Digital Twin Architecture (Frontend)

- **Corridor map** (Leaflet): stations plotted by `latitude/longitude` from
  `stations.csv`, connected by section polylines colored by
  `track_occupancy.state` (free=green, occupied=blue, blocked=red,
  reserved=amber).
- **Schematic track view** (React Flow): nodes = stations (sized by
  `platforms`/`main_tracks`), edges = sections with parallel lines for
  main/loop/siding tracks, edge color = occupancy state, edge label = live
  train number when occupied.
- **Train markers**: positioned by interpolating `progress_pct` between
  `current_station_code` and `next_station_code` along the section polyline;
  re-interpolated client-side every second between 60s server updates for
  smooth animation (Framer Motion).
- **Platform panel**: per-station drawer showing `platform_occupancy` rows —
  platform number, occupant, ETA/ETD, queue.
- **Signal icons**: rendered at station boundaries, aspect from `signals`
  table, color-coded (red/yellow/double-yellow/green).
- **Congestion overlay**: station node glow/halo intensity driven by
  `congestion_score` (toggleable layer).

---

## 8. Claude AI Integration Architecture

`services/claude_service.py` calls the Claude API (Messages API,
`claude-sonnet-4-6` by default, configurable) with a structured prompt:

**Input payload** (assembled server-side, not sent raw to the model):
```json
{
  "train": {"number": "12004", "name": "...", "priority": 1, "current_delay": 7},
  "predicted_delay_next_station": 9.3,
  "station": {"code": "ALJN", "platforms": 7, "tracks_free": 2},
  "congestion": {"ALJN": 0.8, "TDL": 0.3},
  "weather": {"rainfall": 2.1, "visibility": null, "fog_indicator": 0},
  "nearby_trains": [ {"number": "14163", "priority": 4, "eta_minutes": 6} ]
}
```

**System prompt** instructs Claude to act as a railway traffic-control
advisor for this specific corridor, output a JSON object:
```json
{
  "recommendation": "Give precedence to Train 12004 at ALJN.",
  "action_type": "precedence",
  "reason": "Train 12004 is a Rajdhani (priority 1) running 7 min late; "
            "holding it behind 14163 (priority 4) would add ~5 more minutes.",
  "expected_delay_reduction_min": 5,
  "expected_congestion_reduction": "low",
  "alternatives": ["Hold 14163 on loop line for 3 minutes instead"],
  "confidence": 0.82,
  "risk_level": "low",
  "network_impact": "Minimal; 14163 has 12 min buffer to its next crossing."
}
```

The response is validated against a Pydantic schema, stored in
`recommendations`, and pushed via `twin:recommendations`. The **Explanation
Engine** is simply this structured response rendered in the
`controller/recommendations` panel — every field above maps 1:1 to a UI
element (reason, delay reduction, congestion impact, alternatives,
confidence badge, risk badge, network impact note).

**Auto Mode**: when `system_settings.ai_auto_mode = true` and
`confidence >= threshold` and `risk_level == 'low'`, the recommendation is
auto-applied (status=`auto_applied`, updates `live_train_state` /
`platform_occupancy` / `track_occupancy` directly) and logged to
`audit_log`. Controllers can revert any auto-applied action, which
re-opens it as a manual decision.

---

## 9. Screen-Wise UI Designs

### Login
Centered glass card, corridor map faint in background, email/password,
role-based redirect after login.

### Dashboard (landing, role-aware)
- Top stat cards: trains running, avg delay, on-time %, active alerts.
- Corridor mini-map with live train dots.
- Recent recommendations feed.
- Delay trend chart (last 24h, Recharts line).

### Controller (primary workspace — "Ops Center")
- **Center**: Digital Twin (map + schematic toggle).
- **Right panel**: AI Recommendations queue (accept/reject/explain).
- **Bottom drawer**: Decision History (timeline of accepted/rejected/auto).
- **Left panel**: assigned stations list, per-station occupancy/platform/signal mini-cards.
- Header: AI Auto Mode toggle (controller can enable for their section only
  if admin has globally allowed it), connection status indicator.

### Admin
- Tabs: Users, Controllers (assign sections), Corridor config (infra edits),
  AI Settings (global auto-mode, model thresholds, Claude prompt version),
  Analytics (delay/congestion/accuracy/acceptance-rate dashboards), Audit Log.

### User (passenger)
- Train search → Train Tracking page: corridor timeline (stations as a
  vertical/horizontal stepper), current position, current delay, predicted
  delay at next station, platform info, ETA per remaining station.
- Delay Forecast widget: simple bar chart of predicted delay at each
  upcoming station.

### Settings
- Theme (dark default/light), notification preferences, refresh interval.

---

## 10. Component Hierarchy (Frontend, abridged)

```
App
 ├─ AuthProvider
 ├─ Router
 │   ├─ Login
 │   ├─ DashboardLayout (Navbar + Sidebar)
 │   │   ├─ Dashboard (role-aware)
 │   │   ├─ Controller
 │   │   │   ├─ DigitalTwin
 │   │   │   │   ├─ CorridorMap (Leaflet)
 │   │   │   │   ├─ SchematicView (React Flow)
 │   │   │   │   │   ├─ StationNode → PlatformVisualization, Signals
 │   │   │   │   │   └─ SectionEdge → TrackVisualization, TrainAnimation
 │   │   │   │   └─ CongestionOverlay
 │   │   │   ├─ RecommendationsPanel
 │   │   │   │   └─ RecommendationCard (Explanation expandable)
 │   │   │   └─ DecisionPanel (manual override forms)
 │   │   ├─ Admin
 │   │   │   ├─ ControllerManagement
 │   │   │   └─ Analytics (charts grid)
 │   │   ├─ User
 │   │   │   ├─ TrainSearch
 │   │   │   ├─ TrainTracking
 │   │   │   └─ DelayForecast
 │   │   └─ Settings
 │   └─ NotFound
 └─ GlobalToastHost
```

State: `store/twinStore` (live trains/occupancy/signals via WS),
`store/sessionStore` (auth/role), `store/uiStore` (theme, layout). React
Query owns all REST-fetched reference data (stations, trains, history,
analytics).

---

## 11. Development Roadmap

**Phase 1 — Backend foundation (1-2 wks)**
- FastAPI skeleton, Postgres schema + Alembic migrations, seed scripts that
  load `data/processed/*.csv` into the reference tables.
- `lightgbm_service` + `feature_builder` + `fallback_service`, unit-tested
  against `new_final_master_data.csv` rows.
- Auth (JWT) + RBAC middleware.

**Phase 2 — Live state & predictions (1-2 wks)**
- `tracking_service`: replay `new_historical_running_status.csv` as a
  simulated "live feed" (configurable speed) so the twin has continuous data
  without a real NTES feed; designed to be swapped for `06b_ntes_live_collector.py`-style
  real feed later.
- Celery beat 60s tick: predictions, congestion recalculation, occupancy
  updates.
- Redis pub/sub + WebSocket connection manager.

**Phase 3 — Frontend core (2-3 wks)**
- Layout, auth, routing, Dashboard, Digital Twin (map + schematic, no
  animation yet), REST integration via React Query.
- Train animation (interpolation), occupancy/platform/signal visuals.

**Phase 4 — AI Assistant (1-2 wks)**
- `claude_service`, recommendations table/API, Recommendations panel,
  Explanation Engine UI, accept/reject flow + audit logging.

**Phase 5 — Auto Mode & Admin (1-2 wks)**
- Auto-apply logic + revert flow, Admin screens (users, controllers,
  AI settings), Analytics dashboards (delay, congestion heatmap, accuracy,
  acceptance rate, utilization).

**Phase 6 — User dashboard & polish (1 wk)**
- Train search/tracking/forecast, glassmorphism/dark-mode pass, animations,
  responsive/large-screen tuning.

**Phase 7 — Hardening & deployment (1 wk)**
- Load testing the 60s tick + WS fanout, model retraining job, deployment
  (below), monitoring/alerting.

---

## 12. Deployment Architecture

```
                ┌────────────────────────────────────────────┐
                │                  Reverse proxy               │
                │              (Nginx / Traefik, TLS)           │
                └───────┬───────────────────────┬──────────────┘
                        │                       │
              ┌─────────▼─────────┐   ┌─────────▼─────────┐
              │  frontend (static) │   │ backend (FastAPI,  │
              │  Vite build, CDN/  │   │ Uvicorn/Gunicorn,  │
              │  Nginx static      │   │ N workers)         │
              └────────────────────┘   └─────────┬──────────┘
                                                   │
                  ┌────────────────────┬──────────┼───────────────┐
                  ▼                    ▼          ▼               ▼
            ┌───────────┐       ┌────────────┐ ┌─────────┐  ┌────────────┐
            │ PostgreSQL │       │   Redis     │ │ Celery   │  │ Celery beat │
            │ (managed   │       │ (cache +    │ │ workers  │  │ (60s tick)  │
            │  instance) │       │  pub/sub)   │ │          │  │             │
            └───────────┘       └────────────┘ └─────────┘  └────────────┘
```

- Containerized (Docker Compose for dev; Kubernetes or a managed PaaS for
  prod) — services: `frontend`, `backend`, `worker`, `beat`, `postgres`,
  `redis`.
- `models/best_delay_model.pkl` mounted as a read-only volume; retraining job
  writes new versions to a `models/` volume and the service hot-reloads on a
  signal/flag.
- Secrets (DB creds, Claude API key, JWT secret) via env vars / secret
  manager — never committed.
- CI: lint+test backend (pytest) and frontend (vitest), build images, push,
  deploy.

---

## 13. Cross-References

- Dataset schemas: [docs/SCHEMA.md](SCHEMA.md)
- Data pipeline & provenance: [../README.md](../README.md),
  [../data_quality_report.md](../data_quality_report.md)
- Model training notebook: [../notebooks/train_delay_model.ipynb](../notebooks/train_delay_model.ipynb)

This document is the blueprint for implementation; the next step is
scaffolding the `frontend/` and `backend/` folder structures in §2 and
wiring Phase 1 of the roadmap.
