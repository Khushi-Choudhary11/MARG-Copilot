from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.data_store import data_store
from app.predictor import predictor
from app.schemas import StopOut, TrainDetail, TrainSummary
from app.simulation import get_sim_time

router = APIRouter(prefix="/api/trains", tags=["trains"])


@router.get("", response_model=list[TrainSummary])
def list_trains(direction: str | None = None, q: str | None = None):
    out = data_store.all_trains_summary()
    if direction:
        out = [t for t in out if t["corridor_direction"] == direction]
    if q:
        ql = q.lower()
        out = [
            t
            for t in out
            if ql in t["train_number"].lower() or ql in str(t["train_name"]).lower()
        ]
    return out


@router.get("/{train_number}", response_model=TrainDetail)
def get_train(train_number: str):
    train = data_store.get_train(train_number)
    if not train:
        raise HTTPException(status_code=404, detail="Train not found for the demo date")

    sim_time = get_sim_time()
    route_stops: list[StopOut] = []
    for idx, stop in enumerate(train["stops"]):
        if stop["ref_time"] < sim_time:
            status = "done"
        elif idx > 0 and train["stops"][idx - 1]["ref_time"] <= sim_time:
            status = "current"
        else:
            status = "upcoming"

        pred = predictor.predict(stop["feature_row"])
        route_stops.append(
            StopOut(
                station_code=stop["station_code"],
                station_sequence=stop["station_sequence"],
                scheduled_arrival=stop["scheduled_arrival"].isoformat() if stop["scheduled_arrival"] else None,
                scheduled_departure=stop["scheduled_departure"].isoformat() if stop["scheduled_departure"] else None,
                current_delay=stop["current_delay"],
                predicted_delay_next=pred.delay_minutes,
                prediction_source=pred.source,
                status=status,
            )
        )

    return TrainDetail(
        train_number=train["train_number"],
        train_name=train["train_name"],
        train_type=train["train_type"],
        priority=train["priority"],
        corridor_direction=train["corridor_direction"],
        source_station_code=train["source_station_code"],
        destination_station_code=train["destination_station_code"],
        stops=[s["station_code"] for s in train["stops"]],
        operating_days=train["operating_days"],
        total_distance_km=train["total_distance_km"],
        route_stops=route_stops,
    )
