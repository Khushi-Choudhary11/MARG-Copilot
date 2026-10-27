# MARG — Machine-learning Assisted Railway Guidance
> *AI co-pilot for Indian Railways section controllers*
> Far Away 2026 · Railways Theme

---

## What it does

Section controllers on Indian Railways decide train precedence and crossings by experience. MARG is a decision-support "co-pilot" that replays a corridor as a **digital twin**, predicts delays, and recommends re-sequencing when something goes wrong.

- **Control tower UI:** live map, congestion heat, recommendations and a disruption injector (React, Leaflet, Tailwind)
- **Simulation:** replays official timetable data at 60x speed
- **Delay prediction:** PyTorch model with a heuristic fallback (30, 60 and 120 minute horizons)
- **Optimisation:** OR-Tools CP-SAT proposes train sequencing that reduces delay
- **Explanations:** Claude API gives plain-language reasons, with a template fallback
- **Auth and transport:** JWT-secured REST and WebSocket APIs

**Stack:** FastAPI, Python, React, TypeScript, Vite, OR-Tools, PyTorch.

---

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| Python | 3.10+ | [python.org](https://python.org) |
| Node.js | 18+ | [nodejs.org](https://nodejs.org) |
| npm | 9+ | bundled with Node |
| Git | any | [git-scm.com](https://git-scm.com) |

---

## Project Structure

```
MARG-Copilot/
├── backend/              ← FastAPI backend (Python)
│   ├── main.py
│   ├── config.py
│   ├── api/v1/           ← REST + WebSocket routers
│   ├── auth/             ← JWT authentication
│   ├── core/             ← errors, logging, DI
│   ├── models/           ← Pydantic schemas
│   └── services/         ← simulation, prediction, optimization, explanation
├── services/             ← shared Python packages
│   ├── simulation/       ← DES digital twin engine
│   ├── ml/               ← PyTorch delay predictor
│   └── optimizer/        ← CP-SAT + rerouter + Claude explainer
├── frontend/             ← React + Vite + Tailwind dashboard
│   └── src/
│       ├── components/   ← map, panels, status bar
│       ├── store/        ← Zustand state
│       ├── api/          ← axios API client
│       └── hooks/        ← WebSocket + sim controls
└── DEMO_SCRIPT.md        ← second-by-second demo guide
```

---

## 1. Clone & Enter

```bash
git clone <your-repo-url>
cd MARG-Copilot
```

---

## 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv .venv

# Activate it
# macOS / Linux:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

# Install dependencies
pip install fastapi uvicorn[standard] pydantic pydantic-settings \
            python-jose[cryptography] passlib structlog \
            httpx ortools anthropic
```

### Optional: ML prediction (skip for demo — heuristic fallback works fine)
```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

### Environment variables (optional)

Create `backend/.env`:
```env
# Required only for live Claude explanations
ANTHROPIC_API_KEY=sk-ant-...

# Demo credentials (defaults shown — change in production)
DEMO_USERNAME=controller
DEMO_PASSWORD=marg2026

# Server
HOST=0.0.0.0
PORT=8000
DEBUG=true
```

Without `ANTHROPIC_API_KEY`, the explainer uses template-based fallback — **demo still works fully**.

### Start the backend

```bash
cd backend
uvicorn main:app --port 8000 --reload
```

You should see:
```
INFO  MARG backend starting  version=0.1.0
INFO  All services initialised
INFO  Application startup complete.
```

API docs: [http://localhost:8000/docs](http://localhost:8000/docs)
Health:   [http://localhost:8000/health](http://localhost:8000/health)

---

## 3. Frontend Setup

```bash
cd frontend

# Install dependencies (~30 seconds)
npm install

# Start dev server
npm run dev
```

Open: [http://localhost:5173](http://localhost:5173)

The frontend auto-proxies `/api` and `/ws` to `localhost:8000`.

### Optional: set a different backend URL

Create `frontend/.env.local`:
```env
VITE_API_URL=http://your-server:8000
```

---

## 4. Full Stack — Run Both Together

Open **two terminals**:

```bash
# Terminal 1 — Backend
cd MARG-Copilot/backend
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
uvicorn main:app --port 8000 --reload

# Terminal 2 — Frontend
cd MARG-Copilot/frontend
npm run dev
```

Then open [http://localhost:5173](http://localhost:5173).

The dashboard will:
1. Auto-login with demo credentials (`controller` / `marg2026`)
2. Start the NDLS–CNB digital twin simulation
3. Show five trains moving on the corridor map
4. Run congestion predictions every 15 seconds
5. Run the optimizer every 30 seconds

---

## 5. Demo Walkthrough

Follow **`DEMO_SCRIPT.md`** for the full second-by-second guide.

**Quick version:**

1. Open the dashboard — trains moving, all green
2. Click **"Dense Fog · NDLS→GZB"** → watch S1 turn orange
3. Click **"Signal Failure · TDL→ETW"** → second disruption stacks
4. Click **"Block Track · ALJN→TDL"** → S3 goes red, reroute recommendation appears
5. Click **"Explain"** on the REROUTE card → Claude justification appears
6. Click **"Accept"** on all recommendations → impact counter climbs
7. Point at the delay-minutes saved number

---

## 6. Running the Smoke Tests

### Backend integration test (22 checks)

The server must be running first. In a separate terminal:
```bash
cd backend
uvicorn main:app --port 8000
```

Then in another terminal:
```bash
cd backend
python smoke_test.py
```

### Optimizer unit test (35/35 checks)
```bash
cd services/optimizer
python smoke_test.py
```

---

## 7. Production Build

```bash
# Frontend
cd frontend
npm run build        # output in frontend/dist/

# Backend
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2
```

### Free hosting (for the submission link)
- **Frontend** → [Vercel](https://vercel.com) — connect GitHub, set `VITE_API_URL`
- **Backend** → [Render](https://render.com) — Docker or Python runtime, set env vars

---

## 8. Architecture

```
┌─────────────────────────────────────────────────────┐
│  React + Leaflet Control Tower  (Vite / Vercel)     │
│  live map · congestion heat · recommendations ·     │
│  disruption injection · impact counter              │
└──────────────▲──────────────────────────────────────┘
               │ WebSocket + REST (JWT auth)
┌──────────────┴──────────────────────────────────────┐
│  FastAPI backend  (uvicorn / Render)                │
│  ├─ Simulation Service  — daemon thread, 60x speed  │
│  ├─ Prediction Service  — PyTorch / heuristic       │
│  ├─ Optimization Service — OR-Tools CP-SAT          │
│  └─ Explanation Service  — Claude API + cache       │
└─────────────────────────────────────────────────────┘
Data: data.gov.in timetable · Kaggle IR datasets · OpenWeatherMap
```

---

## 9. Key Technical Decisions

| Decision | Why |
|---|---|
| Digital twin (not live NTES) | Live feeds require railway board auth; honest framing > fake demo |
| Daemon thread for sim loop | `asyncio.create_task` fails from sync FastAPI handlers; threading works universally |
| Bash heredoc for large file writes | NTFS mount truncates files >8KB via Python Write tools |
| CP-SAT + template explainer fallback | Demo works without Anthropic key; Claude is additive |
| `pred_30/pred_60/pred_120` response fields | Separate horizons give the UI flexibility to show short/medium/long predictions |

---

## 10. Limitations (as submitted)

- Live NTES feed not connected — digital twin replays official timetable data
- ML model requires `pip install torch` and a training run; heuristic fallback active by default
- Claude explanations require `ANTHROPIC_API_KEY` — template fallback otherwise
- Single corridor (NDLS–CNB); multi-corridor support is roadmap

---

## Team

Built for Far Away 2026 · Railways Theme in 3 weeks.

*Ship daily. Demo everything. Explain honestly. See you in Tokyo. 🚄🌸*
