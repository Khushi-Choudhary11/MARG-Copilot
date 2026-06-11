# MARG — Production Architecture

> Machine-learning Assisted Railway Guidance  
> Complete system design for the Delhi–Kanpur AI co-pilot

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Folder Structure](#2-folder-structure)
3. [Frontend Architecture](#3-frontend-architecture)
4. [Backend Architecture](#4-backend-architecture)
5. [Database Schema](#5-database-schema)
6. [Redis Architecture](#6-redis-architecture)
7. [API Design](#7-api-design)
8. [WebSocket Architecture](#8-websocket-architecture)
9. [ML Service Architecture](#9-ml-service-architecture)
10. [Simulation Engine Architecture](#10-simulation-engine-architecture)
11. [Deployment Architecture](#11-deployment-architecture)

---

## 1. System Overview

### C4 Context Diagram

```mermaid
C4Context
    title MARG — System Context

    Person(controller, "Section Controller", "Railway traffic controller managing NDLS-CNB corridor")
    Person(admin, "Division Admin", "DRM office — views reports and system health")

    System(marg, "MARG Platform", "AI co-pilot: predicts delay propagation, recommends interventions, explains decisions")

    System_Ext(weather, "OpenWeatherMap API", "Real-time weather data for corridor stations")
    System_Ext(claude, "Claude API (Anthropic)", "Natural language explanation of recommendations")
    System_Ext(ntes, "NTES / Live Feed", "Future: live train position data (currently simulated)")

    Rel(controller, marg, "Monitors corridor, accepts/rejects recommendations", "HTTPS + WebSocket")
    Rel(admin, marg, "Views shift reports, delay analytics", "HTTPS")
    Rel(marg, weather, "Fetches weather every 10 min", "REST/HTTPS")
    Rel(marg, claude, "Generates recommendation explanations", "REST/HTTPS")
    Rel(marg, ntes, "Ingests train positions (future)", "REST/HTTPS")
```

### C4 Container Diagram

```mermaid
C4Container
    title MARG — Container View

    Person(controller, "Section Controller")

    Container(web, "Control Tower UI", "React + TypeScript + Leaflet", "Real-time corridor map, recommendation panel, disruption injection")
    Container(api, "API Gateway", "FastAPI", "REST endpoints, WebSocket hub, auth middleware")
    Container(sim, "Simulation Engine", "Python Service", "Digital twin of NDLS-CNB corridor, event-driven DES")
    Container(ml, "ML Prediction Service", "PyTorch + FastAPI", "LSTM+XGBoost ensemble, delay/cascade predictions")
    Container(opt, "Optimization Engine", "Python + OR-Tools", "Conflict resolution, precedence decisions, rerouting")
    Container(exp, "Explainer Service", "Python + Claude API", "NL justification for recommendations")
    ContainerDb(pg, "PostgreSQL", "PostgreSQL 15", "Schedules, events, shift logs, analytics")
    ContainerDb(redis, "Redis", "Redis 7", "Live sim state, WebSocket pub/sub, prediction cache")

    Rel(controller, web, "Uses", "HTTPS/WSS")
    Rel(web, api, "API calls + WebSocket", "HTTPS/WSS")
    Rel(api, sim, "Tick requests, disruption inject", "Internal HTTP")
    Rel(api, ml, "Prediction requests", "Internal HTTP")
    Rel(api, opt, "Optimization requests", "Internal HTTP")
    Rel(api, exp, "Explanation requests", "Internal HTTP")
    Rel(api, redis, "Pub/sub, state cache", "Redis protocol")
    Rel(api, pg, "Persist events, logs", "SQL/TCP")
    Rel(sim, redis, "Publish sim snapshots", "Redis pub/sub")
    Rel(ml, redis, "Cache predictions", "Redis GET/SET")
    Rel(opt, redis, "Cache recommendations", "Redis GET/SET")
    Rel(exp, claude, "Generate explanations", "HTTPS")
```

---

## 2. Folder Structure

```
marg/
├── apps/
│   ├── web/                          # React frontend
│   │   ├── public/
│   │   │   └── corridor-geojson/     # Station/track GeoJSON files
│   │   ├── src/
│   │   │   ├── components/
│   │   │   │   ├── map/
│   │   │   │   │   ├── CorridorMap.tsx
│   │   │   │   │   ├── TrainMarker.tsx
│   │   │   │   │   ├── SectionOverlay.tsx
│   │   │   │   │   ├── WeatherLayer.tsx
│   │   │   │   │   └── FogOverlay.tsx
│   │   │   │   ├── control/
│   │   │   │   │   ├── RecommendationCard.tsx
│   │   │   │   │   ├── RecommendationPanel.tsx
│   │   │   │   │   ├── DisruptionPanel.tsx
│   │   │   │   │   └── AcceptRejectButtons.tsx
│   │   │   │   ├── dashboard/
│   │   │   │   │   ├── ImpactCounter.tsx
│   │   │   │   │   ├── CascadeTree.tsx
│   │   │   │   │   ├── DelayBadge.tsx
│   │   │   │   │   ├── MetricsSidebar.tsx
│   │   │   │   │   └── ShiftSummary.tsx
│   │   │   │   ├── train/
│   │   │   │   │   ├── TrainDetailPanel.tsx
│   │   │   │   │   ├── TrainTimeline.tsx
│   │   │   │   │   └── CrewStatusBadge.tsx
│   │   │   │   └── shared/
│   │   │   │       ├── StatusPill.tsx
│   │   │   │       ├── CounterDisplay.tsx
│   │   │   │       ├── PredictionBar.tsx
│   │   │   │       └── LoadingOverlay.tsx
│   │   │   ├── hooks/
│   │   │   │   ├── useSimulationSocket.ts
│   │   │   │   ├── useTrainPositions.ts
│   │   │   │   ├── useCongestionOverlay.ts
│   │   │   │   ├── useRecommendations.ts
│   │   │   │   └── useImpactMetrics.ts
│   │   │   ├── store/
│   │   │   │   ├── index.ts              # Zustand root store
│   │   │   │   ├── simulationSlice.ts
│   │   │   │   ├── trainsSlice.ts
│   │   │   │   ├── recommendationsSlice.ts
│   │   │   │   └── metricsSlice.ts
│   │   │   ├── services/
│   │   │   │   ├── api.ts                # Axios client, base URL, interceptors
│   │   │   │   ├── websocket.ts          # WebSocket connection manager
│   │   │   │   ├── simulationApi.ts
│   │   │   │   ├── recommendationsApi.ts
│   │   │   │   └── disruptionsApi.ts
│   │   │   ├── types/
│   │   │   │   ├── train.ts
│   │   │   │   ├── station.ts
│   │   │   │   ├── simulation.ts
│   │   │   │   ├── recommendation.ts
│   │   │   │   └── websocket.ts
│   │   │   ├── utils/
│   │   │   │   ├── interpolation.ts      # Train position interpolation
│   │   │   │   ├── congestionColors.ts   # Score → color mapping
│   │   │   │   ├── timeFormat.ts
│   │   │   │   └── delayClassifier.ts
│   │   │   ├── pages/
│   │   │   │   ├── ControlTower.tsx      # Main controller view
│   │   │   │   ├── Analytics.tsx         # Shift reports
│   │   │   │   └── Settings.tsx
│   │   │   ├── App.tsx
│   │   │   └── main.tsx
│   │   ├── package.json
│   │   ├── tsconfig.json
│   │   └── vite.config.ts
│   │
│   └── api/                          # FastAPI backend monolith
│       ├── app/
│       │   ├── main.py               # FastAPI app, lifespan, CORS
│       │   ├── config.py             # Settings via pydantic-settings
│       │   ├── dependencies.py       # DB session, Redis, auth
│       │   ├── routers/
│       │   │   ├── simulation.py     # /simulation/*
│       │   │   ├── trains.py         # /trains/*
│       │   │   ├── disruptions.py    # /disruptions/*
│       │   │   ├── recommendations.py
│       │   │   └── analytics.py
│       │   ├── websocket/
│       │   │   ├── manager.py        # Connection registry
│       │   │   ├── broadcaster.py    # Redis → WS fan-out
│       │   │   └── handlers.py       # Inbound WS message routing
│       │   ├── schemas/
│       │   │   ├── train.py
│       │   │   ├── simulation.py
│       │   │   ├── recommendation.py
│       │   │   └── analytics.py
│       │   └── middleware/
│       │       ├── auth.py
│       │       └── request_id.py
│       ├── pyproject.toml
│       └── Dockerfile
│
├── services/
│   ├── simulation/                   # Simulation engine (internal service)
│   │   ├── engine/
│   │   │   ├── core.py               # SimulationEngine class
│   │   │   ├── entities.py           # Train, Station, Section dataclasses
│   │   │   ├── event_queue.py        # Priority queue, event dispatch
│   │   │   ├── event_handlers.py     # Handler per EventType
│   │   │   └── snapshot.py           # SimSnapshot builder
│   │   ├── corridor/
│   │   │   ├── ndls_cnb.py           # Hard-coded corridor definition
│   │   │   ├── schedule_loader.py    # WTT schedule → Train objects
│   │   │   └── graph.py              # NetworkX corridor graph
│   │   ├── physics/
│   │   │   ├── delay_generator.py
│   │   │   ├── weather_engine.py
│   │   │   └── crew_tracker.py
│   │   ├── api.py                    # FastAPI app exposing sim to gateway
│   │   └── Dockerfile
│   │
│   ├── ml/                           # ML prediction service
│   │   ├── models/
│   │   │   ├── lstm.py               # DelayLSTM definition
│   │   │   ├── xgboost_model.py      # XGBoost wrapper
│   │   │   └── ensemble.py           # MARGEnsemble
│   │   ├── pipeline/
│   │   │   ├── feature_extractor.py
│   │   │   ├── sequence_builder.py
│   │   │   └── scaler.py
│   │   ├── serving/
│   │   │   ├── predictor.py          # Inference entry point
│   │   │   └── cache.py              # Redis prediction cache
│   │   ├── training/                 # Offline — not deployed
│   │   │   ├── dataset_generator.py
│   │   │   ├── train_lstm.py
│   │   │   ├── train_xgb.py
│   │   │   └── evaluate.py
│   │   ├── artifacts/                # Tracked by DVC
│   │   │   ├── lstm_best.pt
│   │   │   ├── xgb_best.json
│   │   │   └── scaler.pkl
│   │   ├── api.py
│   │   └── Dockerfile
│   │
│   ├── optimization/                 # OR-Tools optimization service
│   │   ├── engine/
│   │   │   ├── conflict_detector.py
│   │   │   ├── cp_sat_resolver.py
│   │   │   ├── greedy_resolver.py
│   │   │   ├── priority_scorer.py
│   │   │   └── graph_algorithms.py
│   │   ├── recommendations/
│   │   │   ├── builder.py            # Decision → Recommendation
│   │   │   └── deduplicator.py
│   │   ├── api.py
│   │   └── Dockerfile
│   │
│   └── explainer/                    # Claude API wrapper service
│       ├── explainer.py              # Prompt builder + Claude call
│       ├── cache.py                  # Cache identical contexts
│       ├── api.py
│       └── Dockerfile
│
├── data/
│   ├── corridor/
│   │   ├── stations.json             # 28 stations, real coordinates
│   │   ├── sections.json             # Track sections with attributes
│   │   └── wtt_schedule.json         # Working Timetable for NDLS-CNB
│   ├── training/                     # Generated by dataset_generator
│   │   ├── train.parquet
│   │   ├── val.parquet
│   │   └── test.parquet
│   └── geojson/
│       ├── track_ndls_cnb.geojson
│       └── stations.geojson
│
├── infra/
│   ├── docker-compose.yml            # Local development
│   ├── docker-compose.prod.yml       # Production overrides
│   └── nginx/
│       └── nginx.conf                # Reverse proxy config
│
├── scripts/
│   ├── generate_dataset.py
│   ├── train_models.py
│   └── seed_db.py
│
├── notebooks/
│   ├── 01_eda_delay_patterns.ipynb
│   ├── 02_feature_engineering.ipynb
│   ├── 03_lstm_training.ipynb
│   └── 04_evaluation.ipynb
│
├── .env.example
├── .gitignore
├── README.md
└── ARCHITECTURE.md                   # This document
```

---

## 3. Frontend Architecture

### Component Hierarchy

```mermaid
graph TD
    App["App.tsx\nRouter + Providers"]
    App --> CT["ControlTower.tsx\nMain layout"]
    App --> AN["Analytics.tsx"]

    CT --> Map["CorridorMap\nLeaflet container"]
    CT --> RP["RecommendationPanel\nRight sidebar"]
    CT --> MS["MetricsSidebar\nLeft sidebar"]
    CT --> DP["DisruptionPanel\nBottom bar"]

    Map --> TM["TrainMarker × N\nAnimated dot per train"]
    Map --> SO["SectionOverlay\nCongestion heatmap polylines"]
    Map --> WL["WeatherLayer\nFog + rain overlay"]
    Map --> PP["PositionPopup\nClick-to-inspect train"]

    RP --> RC["RecommendationCard × 5\nAction + countdown + accept/reject"]
    RP --> CA["CascadeTree\nD3 force-directed"]
    RP --> IC["ImpactCounter\nWith/without MARG"]

    MS --> PB["PredictionBars\nDelay horizons t+30/60/120"]
    MS --> SS["ShiftSummary\nRunning totals"]
    MS --> DB["DelayBadge × N\nPer active train"]

    DP --> DI["DisruptionInjector\nScenario buttons"]
    DP --> SC["SimulationControls\nSpeed + reset"]

    style App fill:#1e293b,color:#fff
    style CT fill:#0f172a,color:#fff
```

### State Management (Zustand)

```mermaid
graph LR
    WS["WebSocket\nStream"]
    WS -->|snapshot| SS["simulationSlice\n- currentTime\n- speed\n- status"]
    WS -->|train_positions| TS["trainsSlice\n- positions Map\n- delays Map\n- states Map"]
    WS -->|recommendations| RS["recommendationsSlice\n- pending []\n- accepted []\n- rejected []\n- expired []"]
    WS -->|metrics| MS["metricsSlice\n- delayWithout\n- delayWith\n- saved\n- cascadeRisk"]

    SS -->|consumed by| SC["SimulationControls\nDisruptionPanel"]
    TS -->|consumed by| TM["TrainMarker\nTrainDetailPanel"]
    RS -->|consumed by| RP["RecommendationPanel\nRecommendationCard"]
    MS -->|consumed by| IC["ImpactCounter\nMetricsSidebar"]
```

### Data Flow — Render Loop

```mermaid
sequenceDiagram
    participant WS as WebSocket
    participant Store as Zustand Store
    participant Hook as useTrainPositions
    participant Map as CorridorMap
    participant RAF as requestAnimationFrame

    WS->>Store: dispatch(updatePositions(snapshot))
    Store->>Hook: selector fires (shallow compare)
    Hook->>Map: returns interpolated positions
    Map->>RAF: schedules re-render
    RAF->>Map: renders TrainMarkers at t_interpolated
    Note over Map,RAF: Interpolation between snapshots\ngives smooth animation at 60fps\neven with 1-second WS tick
```

---

## 4. Backend Architecture

### Service Interaction

```mermaid
graph TD
    GW["API Gateway\nFastAPI :8000"]

    GW -->|HTTP POST /sim/tick| SIM["Simulation Engine\n:8001"]
    GW -->|HTTP POST /ml/predict| ML["ML Service\n:8002"]
    GW -->|HTTP POST /opt/resolve| OPT["Optimization Engine\n:8003"]
    GW -->|HTTP POST /explain| EXP["Explainer Service\n:8004"]

    GW -->|read/write| PG[("PostgreSQL\n:5432")]
    GW -->|pub/sub + cache| RD[("Redis\n:6379")]

    SIM -->|PUBLISH sim:snapshot| RD
    ML -->|GET/SET ml:pred:*| RD
    OPT -->|GET/SET opt:rec:*| RD
    EXP -->|GET/SET exp:expl:*| RD

    EXP -->|HTTPS| CLAUDE["Claude API\nExternal"]
    SIM -->|HTTPS| OWM["OpenWeatherMap\nExternal"]

    style GW fill:#0ea5e9,color:#fff
    style RD fill:#dc2626,color:#fff
    style PG fill:#1d4ed8,color:#fff
```

### Request Lifecycle — Optimization Cycle

```mermaid
sequenceDiagram
    participant Timer as Tick Timer (1s)
    participant GW as API Gateway
    participant SIM as Simulation
    participant Redis as Redis
    participant ML as ML Service
    participant OPT as Optimizer
    participant EXP as Explainer
    participant WS as WebSocket Broadcaster

    Timer->>GW: trigger cycle
    GW->>SIM: POST /advance {minutes: 1}
    SIM-->>GW: SimSnapshot (train positions, section states)
    GW->>Redis: PUBLISH sim:snapshot {snapshot}

    par Parallel inference
        GW->>ML: POST /predict {snapshot}
        ML-->>GW: PredictionResult[]
    and
        GW->>Redis: GET opt:rec:latest
        Redis-->>GW: cached recs (if fresh < 5s)
    end

    GW->>OPT: POST /optimize {snapshot, predictions}
    OPT-->>GW: ResolutionPlan {decisions[], alerts[]}

    loop Top 3 decisions needing explanation
        GW->>EXP: POST /explain {context}
        EXP-->>GW: "Hold 22691 at Aligarh 12 min → saves 41 min. Risk: low."
    end

    GW->>Redis: PUBLISH ws:broadcast {snapshot, predictions, recommendations}
    Redis-->>WS: subscriber receives
    WS->>WS: fan-out to all connected clients
```

---

## 5. Database Schema

### Entity Relationship Diagram

```mermaid
erDiagram
    STATIONS {
        varchar station_id PK
        varchar name
        varchar short_code
        float chainage_km
        int station_class
        int num_platforms
        float max_loop_length_m
        bool is_crew_change_point
        bool is_loco_change_point
        bool is_junction
        float lat
        float lon
    }

    TRACK_SECTIONS {
        varchar section_id PK
        varchar from_station_id FK
        varchar to_station_id FK
        float length_km
        varchar line_type
        float max_speed_passenger_kmh
        float max_speed_freight_kmh
        float ruling_gradient_pct
        int num_signal_blocks
    }

    TRAIN_SCHEDULE {
        varchar train_id PK
        varchar train_name
        varchar category
        int priority
        varchar origin_station_id FK
        varchar dest_station_id FK
        varchar loco_type
        int total_coaches
        float max_speed_kmh
        time scheduled_departure
        bool runs_daily
        int[] runs_on_days
    }

    SCHEDULE_STOPS {
        uuid stop_id PK
        varchar train_id FK
        varchar station_id FK
        int stop_sequence
        time scheduled_arrival
        time scheduled_departure
        bool is_halt
    }

    SIMULATION_SESSIONS {
        uuid session_id PK
        timestamp started_at
        timestamp ended_at
        varchar scenario_name
        jsonb weather_config
        jsonb disruption_config
        float speed_factor
        varchar status
    }

    TRAIN_EVENTS {
        uuid event_id PK
        uuid session_id FK
        varchar train_id FK
        varchar station_id FK
        varchar event_type
        timestamp sim_time
        timestamp recorded_at
        float delay_minutes
        varchar rlr_code
        varchar reason
        bool is_primary_delay
        jsonb metadata
    }

    RECOMMENDATIONS {
        uuid rec_id PK
        uuid session_id FK
        varchar train_id FK
        varchar station_id FK
        varchar action_type
        timestamp created_at
        timestamp expires_at
        float additional_delay_minutes
        float downstream_delay_saved
        float cascade_risk
        float confidence
        text explanation
        jsonb context_snapshot
        varchar status
        timestamp acted_at
    }

    CONTROLLER_ACTIONS {
        uuid action_id PK
        uuid session_id FK
        uuid rec_id FK
        varchar decision
        timestamp decided_at
        float actual_delay_saved
        text override_reason
    }

    SHIFT_SUMMARIES {
        uuid shift_id PK
        uuid session_id FK
        timestamp shift_start
        timestamp shift_end
        float total_delay_minutes_without_marg
        float total_delay_minutes_with_marg
        float delay_saved_minutes
        int disruptions_detected
        int recommendations_issued
        int recommendations_accepted
        int recommendations_rejected
        float acceptance_rate
        jsonb delay_by_category
    }

    STATIONS ||--o{ TRACK_SECTIONS : "from"
    STATIONS ||--o{ TRACK_SECTIONS : "to"
    STATIONS ||--o{ SCHEDULE_STOPS : "at"
    TRAIN_SCHEDULE ||--o{ SCHEDULE_STOPS : "has"
    SIMULATION_SESSIONS ||--o{ TRAIN_EVENTS : "contains"
    SIMULATION_SESSIONS ||--o{ RECOMMENDATIONS : "generates"
    RECOMMENDATIONS ||--o| CONTROLLER_ACTIONS : "results in"
    SIMULATION_SESSIONS ||--o| SHIFT_SUMMARIES : "summarised by"
```

---

## 6. Redis Architecture

### Key Schema and TTL Policy

```mermaid
graph TD
    subgraph "Live State (TTL: 10s)"
        S1["sim:state:current\nLATEST SimSnapshot JSON\nGET/SET, overwritten each tick"]
        S2["sim:trains:positions\nHash: train_id → TrainPositionDTO JSON\nHSET/HGETALL"]
        S3["sim:sections:congestion\nHash: section_id → float\nHSET/HGETALL"]
    end

    subgraph "Pub/Sub Channels (no TTL)"
        P1["CHANNEL: sim:snapshot\nPublished each tick by SIM service\nSubscribed by WS Broadcaster"]
        P2["CHANNEL: ws:broadcast\nPublished by Gateway after enrichment\nSubscribed by WS Broadcaster"]
        P3["CHANNEL: alert:cascade\nPublished when cascade detected\nSubscribed by Gateway + Logger"]
    end

    subgraph "Prediction Cache (TTL: 30s)"
        C1["ml:pred:{train_id}:{snapshot_hash}\nPredictionResult JSON\nAvoids re-inference for identical state"]
        C2["opt:rec:{session_id}:latest\nRecommendation[] JSON\nTTL: 5s — recs expire fast"]
        C3["exp:expl:{context_hash}\nExplanation string\nTTL: 300s — same context, same explanation"]
    end

    subgraph "Session State (TTL: 8h)"
        T1["session:{session_id}:meta\nSession config, start time, status"]
        T2["session:{session_id}:metrics\nRunning impact counters\nINCRBY operations"]
        T3["ws:clients:{session_id}\nSet of connected client IDs\nSADD/SREM"]
    end

    subgraph "Rate Limiting (TTL: 60s)"
        R1["ratelimit:{client_ip}:{endpoint}\nCounter, INCR + EXPIRE\nMax 100 req/min"]
    end
```

### WebSocket Fan-Out via Redis Pub/Sub

```mermaid
graph LR
    SIM["Simulation\nService"]
    SIM -->|PUBLISH sim:snapshot| RD["Redis\nPub/Sub"]
    RD -->|subscriber| GW["Gateway\nBroadcaster\nprocess 1"]
    RD -->|subscriber| GW2["Gateway\nBroadcaster\nprocess 2"]

    GW -->|enrich + forward| C1["Client 1\nController A"]
    GW -->|enrich + forward| C2["Client 2\nController B"]
    GW2 -->|enrich + forward| C3["Client 3\nAdmin"]

    Note["Multiple Gateway instances\ncan subscribe to same channel.\nRedis fan-out handles multi-process\nhorizontal scaling automatically."]
```

---

## 7. API Design

### REST Endpoints

```
BASE URL: https://api.marg.railway.in/v1

SIMULATION
──────────────────────────────────────────────────────────────
POST   /simulation/start          Start a new simulation session
POST   /simulation/stop           Stop current session
POST   /simulation/reset          Reset to schedule state
PATCH  /simulation/speed          Set playback speed {factor: 1-100}
GET    /simulation/state          Current snapshot (polling fallback)
GET    /simulation/sessions       List past sessions
GET    /simulation/sessions/{id}  Session detail + summary

TRAINS
──────────────────────────────────────────────────────────────
GET    /trains                    All active trains + positions
GET    /trains/{train_id}         Single train detail, crew state
GET    /trains/{train_id}/history Delay history for current session

DISRUPTIONS
──────────────────────────────────────────────────────────────
POST   /disruptions               Inject a disruption
  Body: { type, location, severity, duration_minutes }
DELETE /disruptions/{id}          Cancel a disruption
GET    /disruptions               Active disruptions list

RECOMMENDATIONS
──────────────────────────────────────────────────────────────
GET    /recommendations           Current pending recommendations
POST   /recommendations/{id}/accept   Controller accepts
POST   /recommendations/{id}/reject   Controller rejects with reason
PATCH  /recommendations/{id}/modify   Modify parameters before accept

ANALYTICS
──────────────────────────────────────────────────────────────
GET    /analytics/shift/{session_id}   Shift summary report
GET    /analytics/delay-trends         Historical delay by category
GET    /analytics/cascade-events       Past cascade incidents
GET    /analytics/recommendation-accuracy  Accepted recs vs actual outcome

CORRIDOR (static, cached)
──────────────────────────────────────────────────────────────
GET    /corridor/stations          All stations
GET    /corridor/sections          All track sections
GET    /corridor/schedule          Full WTT schedule
```

### REST Response Envelope

```mermaid
graph LR
    A["All responses wrapped in\nconsistent envelope"] --> B["{
  success: boolean,
  data: T,
  error: {code, message} | null,
  meta: {
    request_id: string,
    timestamp: ISO8601,
    version: '1'
  }
}"]
```

### WebSocket Message Protocol

```
CONNECTION
  wss://api.marg.railway.in/v1/ws?session_id={id}&client_id={uuid}

INBOUND MESSAGES (client → server)
──────────────────────────────────
{ type: "ping" }
{ type: "subscribe_train", train_id: "12301" }
{ type: "unsubscribe_train", train_id: "12301" }
{ type: "accept_recommendation", rec_id: "uuid" }
{ type: "reject_recommendation", rec_id: "uuid", reason: "string" }
{ type: "inject_disruption", disruption: DisruptionDTO }
{ type: "set_speed", factor: 60 }

OUTBOUND MESSAGES (server → client)
──────────────────────────────────
{ type: "pong", server_time: ISO8601 }
{ type: "simulation_tick", payload: SimSnapshotDTO }
{ type: "train_update", payload: TrainPositionDTO[] }
{ type: "congestion_update", payload: SectionCongestionDTO[] }
{ type: "recommendation_issued", payload: RecommendationDTO }
{ type: "recommendation_expired", rec_id: "uuid" }
{ type: "cascade_alert", payload: CascadeAlertDTO }
{ type: "metrics_update", payload: MetricsDTO }
{ type: "disruption_ack", disruption_id: "uuid", status: "active" }
{ type: "error", code: string, message: string }
```

---

## 8. WebSocket Architecture

### Connection Management

```mermaid
graph TD
    subgraph "Client Side"
        WSH["useSimulationSocket.ts\nConnection manager hook"]
        WSH -->|reconnect on drop| WSC["WebSocket Client\nauto-reconnect, exponential backoff"]
        WSC -->|messages| MSG["Message dispatcher\ntype-based routing to store"]
    end

    subgraph "Server Side"
        WSD["WebSocket Manager\nPython class"]
        WSD --> CONN["ConnectionRegistry\nDict: client_id → WebSocket"]
        WSD --> AUTH["Token validator\non connection upgrade"]

        BCAST["Broadcaster\nBackground task"]
        BCAST -->|subscribe| RDSUB["Redis Subscriber\nws:broadcast channel"]
        RDSUB -->|message| BCAST
        BCAST -->|fan-out| CONN
    end

    WSC <-->|WSS| WSD
    WSD --> BCAST
```

### Message Flow Timing

```mermaid
gantt
    title WebSocket Cycle — 1 second tick
    dateFormat ss.SSS
    axisFormat %S.%L

    section Simulation
    Advance sim 1 minute     :00.000, 50ms
    Build SimSnapshot        :50ms, 30ms

    section ML
    Extract features         :00.000, 20ms
    LSTM inference           :20ms, 80ms
    XGBoost inference        :20ms, 30ms
    Ensemble combine         :100ms, 10ms

    section Optimization
    Detect conflicts         :80ms, 40ms
    CP-SAT resolve           :120ms, 150ms
    Build recommendations    :270ms, 30ms

    section Explainer
    Claude API call          :300ms, 150ms

    section Broadcast
    Compose WS message       :450ms, 20ms
    Redis PUBLISH            :470ms, 10ms
    Client receives          :490ms, 10ms
```

---

## 9. ML Service Architecture

### Training vs Serving Separation

```mermaid
graph TD
    subgraph "Offline Training (not deployed)"
        DG["DatasetGenerator\n5000 simulation episodes"]
        DG --> TP["train.parquet\nval.parquet\ntest.parquet"]
        TP --> TL["train_lstm.py\nPyTorch training loop"]
        TP --> TX["train_xgb.py\nXGBoost training"]
        TL --> LA["lstm_best.pt\nArtifact"]
        TX --> XA["xgb_best.json\nscaler.pkl\nArtifacts"]
        LA --> DVC["DVC artifact tracking\nVersion controlled"]
        XA --> DVC
    end

    subgraph "Online Serving (deployed)"
        DVC -->|pulled at deploy| LOAD["Model Loader\nLoads artifacts at startup"]
        LOAD --> ENS["MARGEnsemble\nLSTM 60% + XGBoost 40%"]
        
        REQ["POST /predict\n{snapshot: SimSnapshot}"] --> FE["FeatureExtractor\nFlat + sequence features"]
        FE --> ENS
        ENS --> PRED["PredictionResult\ndelay_30m, delay_60m,\ncascade_risk, confidence"]
        PRED --> CACHE["Redis Cache\nTTL: 30s per snapshot_hash"]
        CACHE --> RESP["Response"]
    end

    subgraph "Model Architecture"
        INPUT["Input\n(batch, 12 timesteps, 86 features)"]
        INPUT --> LSTM["LSTM\nhidden=128, layers=2, dropout=0.3"]
        LSTM --> HEAD1["Delay head t+30"]
        LSTM --> HEAD2["Delay head t+60"]
        LSTM --> HEAD3["Delay head t+120"]
        LSTM --> HEAD4["Cascade risk\n(sigmoid)"]
    end
```

### Prediction Caching Strategy

```mermaid
graph LR
    REQ["Predict Request\n{snapshot}"]
    REQ --> HASH["Hash snapshot state\nMD5 of key fields"]
    HASH --> CHK{"Redis\nCache hit?"}
    CHK -->|HIT| RET["Return cached\nPredictionResult"]
    CHK -->|MISS| INF["Run inference\n~110ms"]
    INF --> STORE["Cache result\nTTL: 30s"]
    STORE --> RET
```

---

## 10. Simulation Engine Architecture

### Event-Driven Architecture

```mermaid
graph TD
    subgraph "Event Queue (heapq)"
        EQ["Priority Queue\nOrdered by sim_time"]
    end

    subgraph "Event Handlers"
        EQ -->|TRAIN_DEPARTURE| HD["handle_departure\n→ schedules BLOCK_ENTER"]
        EQ -->|BLOCK_ENTER| HB["handle_block_enter\n→ marks block occupied\n→ updates upstream signals\n→ schedules BLOCK_CLEAR"]
        EQ -->|BLOCK_CLEAR| HC["handle_block_clear\n→ frees block\n→ cascades signal update\n→ schedules ARRIVAL if last block"]
        EQ -->|TRAIN_ARRIVAL| HA["handle_arrival\n→ computes delay delta\n→ schedules DEPARTURE after halt"]
        EQ -->|ENTER_LOOP| HL["handle_enter_loop\n→ marks loop occupied\n→ schedules EXIT_LOOP"]
        EQ -->|LOCO_FAILURE| HF["handle_loco_failure\n→ stops train\n→ schedules LOCO_RESTORE\n→ triggers OPT cycle"]
        EQ -->|WEATHER_UPDATE| HW["handle_weather\n→ updates speed limits\n→ recalculates transit times"]
        EQ -->|CREW_EXPIRY| HCE["handle_crew_expiry\n→ stops train\n→ schedules CREW_CHANGE"]
        EQ -->|CONTROLLER_ACTION| HCA["handle_controller_action\n→ applies recommendation\n→ injects resulting events"]
    end

    subgraph "State"
        STATE["Corridor State\n- train_positions Dict\n- block_occupation Dict\n- loop_occupation Dict\n- signal_aspects Dict\n- weather WeatherState"]
    end

    HD & HB & HC & HA & HL & HF & HW & HCE & HCA -->|mutate| STATE
    STATE -->|snapshot| SNAP["SimSnapshot\nPublished to Redis"]
```

### Simulation Speed Control

```mermaid
graph LR
    WALL["Wall Clock\n1 real second"] -->|drives| TICK["Tick Loop\nasyncio.sleep(1/speed_factor)"]
    TICK -->|advance| SIM["Sim Clock\n+speed_factor minutes per tick"]
    SIM -->|process events until| CUTOFF["sim_time <= wall_time × speed_factor"]
    CUTOFF --> SNAP["Emit Snapshot"]

    MODES["Speed Modes\n1× — real time\n60× — 1 min/sec\n∞ — training mode (no sleep)"]
```

---

## 11. Deployment Architecture

### Infrastructure Overview

```mermaid
graph TD
    subgraph "CDN + Edge"
        USER["Browser\nController"] -->|HTTPS| VERCEL["Vercel Edge\nReact SPA\nGlobal CDN"]
    end

    subgraph "Render.com (Backend)"
        VERCEL -->|API + WSS| NGINX["Nginx\nReverse Proxy\n+ TLS termination"]
        NGINX -->|/api/*| GW["API Gateway\nFastAPI\n(2 instances)"]
        NGINX -->|/ws| WSS["WebSocket Server\nFastAPI\n(2 instances)"]

        GW -->|internal| SIM_SVC["Simulation Service\n(1 instance, stateful)"]
        GW -->|internal| ML_SVC["ML Service\n(1 instance, GPU optional)"]
        GW -->|internal| OPT_SVC["Optimization Service\n(1 instance)"]
        GW -->|internal| EXP_SVC["Explainer Service\n(1 instance)"]
    end

    subgraph "Managed Services (Render)"
        GW & WSS & SIM_SVC & ML_SVC & OPT_SVC & EXP_SVC --> PG[("PostgreSQL\nRender Managed")]
        GW & WSS & SIM_SVC & ML_SVC & OPT_SVC & EXP_SVC --> RD[("Redis\nRender Managed")]
    end

    subgraph "External APIs"
        EXP_SVC -->|HTTPS| CLAUDE["Anthropic\nClaude API"]
        SIM_SVC -->|HTTPS| OWM["OpenWeatherMap"]
    end

    style VERCEL fill:#000,color:#fff
    style PG fill:#1d4ed8,color:#fff
    style RD fill:#dc2626,color:#fff
```

### CI/CD Pipeline

```mermaid
graph LR
    PUSH["git push\nmain branch"] --> GHA["GitHub Actions\nCI Pipeline"]

    GHA --> LINT["Lint + Type Check\nESLint, mypy, ruff"]
    LINT --> TEST["Unit Tests\nPytest + Vitest"]
    TEST --> BUILD["Docker Build\n4 service images"]
    BUILD --> PUSH_REG["Push to\nGitHub Container Registry"]

    PUSH_REG --> DEPLOY_WEB["Vercel Deploy\nFrontend"]
    PUSH_REG --> DEPLOY_API["Render Deploy\nBackend services\nBlue-green, zero downtime"]

    DEPLOY_API --> SMOKE["Smoke Tests\nHealth checks\non deployed instances"]
    SMOKE --> NOTIFY["Slack notify\nDeploy success/fail"]
```

### Environment Configuration

```mermaid
graph TD
    ENV["Environment Variables"]

    ENV --> LOCAL["Local (.env)\ndocker-compose"]
    ENV --> STAGING["Render Staging\nPR preview environments"]
    ENV --> PROD["Render Production\n+ Vercel Production"]

    subgraph "Required Variables"
        V1["DATABASE_URL"]
        V2["REDIS_URL"]
        V3["ANTHROPIC_API_KEY"]
        V4["OPENWEATHERMAP_API_KEY"]
        V5["JWT_SECRET"]
        V6["SIMULATION_SERVICE_URL"]
        V7["ML_SERVICE_URL"]
        V8["OPTIMIZATION_SERVICE_URL"]
        V9["EXPLAINER_SERVICE_URL"]
        V10["CORS_ORIGINS"]
    end
```

### Health Check and Observability

```mermaid
graph LR
    subgraph "Health Endpoints"
        H1["GET /health\nLiveness — is the process up?"]
        H2["GET /health/ready\nReadiness — DB + Redis connected?"]
        H3["GET /health/deep\nModel loaded? Sim initialized?"]
    end

    subgraph "Metrics (future)"
        M1["Prometheus scrape\n/metrics endpoint"]
        M1 --> M2["Grafana dashboard\nLatency, throughput,\nprediction accuracy"]
    end

    subgraph "Logging"
        L1["Structured JSON logs\nrequest_id, session_id,\nduration_ms, status"]
        L1 --> L2["Render log aggregation\nor external (Logtail)"]
    end
```

---

## Architectural Decisions — Rationale

| Decision | Chosen | Rejected | Reason |
|---|---|---|---|
| State management | Zustand | Redux | Simpler for real-time map state; no boilerplate |
| Backend framework | FastAPI | Django | Async-native; automatic OpenAPI docs; faster |
| Service communication | Internal HTTP | gRPC | Simpler for hackathon; gRPC for production v2 |
| Simulation isolation | Separate service | In-process | Stateful engine needs isolation from stateless API |
| ML serving | FastAPI wrapper | Triton | Triton overkill for 1 model; FastAPI sufficient |
| WS fan-out | Redis pub/sub | In-memory | Supports multiple API gateway instances |
| Explainer caching | Context hash | No cache | Claude API latency 150ms+ — cache identical contexts |
| DB for events | PostgreSQL | MongoDB | Structured schema, relational queries for analytics |
| Deployment | Vercel + Render | AWS | Free tier sufficient; zero-config TLS; fast setup |

---

*Architecture version 1.0 — MARG, FAR AWAY 2026*
