from __future__ import annotations

from fastapi import APIRouter

from app.config import CORRIDOR_STATIONS
from app.data_store import data_store
from app.predictor import predictor
from app.schemas import KpiSummary
from app.simulation import build_snapshot

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/kpis", response_model=KpiSummary)
def get_kpis():
    snapshot = build_snapshot()
    running = [t for t in snapshot.trains if t.status == "running"]
    total = len(snapshot.trains)

    avg_current = sum(t.current_delay for t in running) / len(running) if running else 0.0
    preds = [t.predicted_delay_next for t in running if t.predicted_delay_next is not None]
    avg_pred = sum(preds) / len(preds) if preds else 0.0

    on_time = sum(1 for t in running if t.current_delay <= 5)
    delayed = sum(1 for t in running if t.current_delay > 15)
    on_time_pct = (on_time / len(running) * 100) if running else 0.0
    delayed_pct = (delayed / len(running) * 100) if running else 0.0

    return KpiSummary(
        sim_time=snapshot.sim_time,
        demo_date=snapshot.demo_date,
        total_trains=total,
        running_trains=len(running),
        avg_current_delay=round(avg_current, 2),
        avg_predicted_delay=round(avg_pred, 2),
        on_time_pct=round(on_time_pct, 1),
        delayed_pct=round(delayed_pct, 1),
        model_active=predictor.is_model_loaded,
        model_name=predictor.model_name,
    )


@router.get("/station-delays")
def get_station_delay_history():
    """Average delay per corridor station, from the full historical dataset
    (not just the demo day) - used for the analytics charts."""
    master = data_store.demo_rows  # demo day only for MVP responsiveness
    out = []
    for code in CORRIDOR_STATIONS:
        rows = master[master["station_code"] == code]
        if rows.empty:
            continue
        out.append(
            {
                "station_code": code,
                "avg_current_delay": round(float(rows["current_delay"].mean()), 2),
                "avg_station_historical_delay": round(float(rows["station_average_delay"].mean()), 2),
                "train_count": int(len(rows)),
            }
        )
    return out


@router.get("/train-type-delays")
def get_train_type_delays():
    master = data_store.demo_rows
    grouped = master.groupby("train_type")["current_delay"].mean().round(2)
    return [{"train_type": k, "avg_delay": v} for k, v in grouped.items()]
