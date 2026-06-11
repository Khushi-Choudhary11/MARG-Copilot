# MARG Control Tower — Frontend

React + TypeScript + Tailwind + Leaflet dashboard for the MARG railway AI co-pilot.

## Quick start

```bash
# 1. Install dependencies
cd frontend
npm install

# 2. Start backend (separate terminal)
cd ../backend
uvicorn main:app --port 8000 --reload

# 3. Start frontend dev server
npm run dev        # → http://localhost:5173
```

The frontend auto-proxies `/api` and `/ws` to `localhost:8000` (see `vite.config.ts`).

## Build for production

```bash
npm run build      # output in dist/
npm run preview    # preview the production build locally
```

## Features

| Panel | Description |
|---|---|
| **Corridor Map** | Dark Leaflet map — NDLS→CNB, trains animated, sections coloured by congestion |
| **Disruption Panel** | 3 one-click demo buttons: Fog, Track Block, Signal Fail |
| **Congestion + Delays** | Live section risk bars + per-train delay sorted by worst |
| **Recommendations** | CP-SAT optimizer decisions with Accept / Override / Explain |
| **Explainability** | Per-card Claude API justification (template fallback if no key) |
| **Impact Counter** | Cumulative delay-minutes saved vs. no-intervention baseline |
| **Status Bar** | WS connection, tick counter, sim controls |

## Architecture

```
src/
  api/          — axios client + typed endpoint wrappers
  store/        — Zustand store (simulation · prediction · optimization · toasts)
  hooks/        — useWebSocket (live tick feed) · useSimulationControls (API actions)
  data/         — hardcoded NDLS-CNB corridor GeoJSON + helpers
  types/        — shared TypeScript interfaces
  components/
    map/        — CorridorMap · TrainMarker · CongestionLayer
    panels/     — DisruptionPanel · RecommendationsPanel · DelayPanel · ToastContainer
    ImpactCounter · StatusBar
```

## Environment variables (optional)

Create `.env.local` to override the API base URL:

```env
VITE_API_URL=http://your-backend-host:8000
```
