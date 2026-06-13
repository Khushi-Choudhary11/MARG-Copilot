"""
Compressed-time simulation engine.

There is no live data feed for the MVP. Instead we replay one real "demo day"
(new_final_master_data.csv, filtered to DEMO_DATE) on a compressed clock: every
wall-clock second advances the simulated clock by SIM_SPEED seconds, so a full
24h service day plays out in a few minutes and loops continuously.

For each train we know its scheduled corridor stops (with real scheduled times
and real current_delay values from that day). At any sim_time we interpolate
the train's position between the two bracketing stops, and run the delay
predictor (model or fallback) on the departing stop's feature row to produce a
"predicted delay at next station".
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta

from app.config import CORRIDOR_STATIONS, DEMO_DATE, SIM_SPEED
from app.data_store import data_store
from app.predictor import predictor
from app.schemas import LiveTrainPosition, StationOut, TwinSnapshot

_DAY_START = datetime.fromisoformat(f"{DEMO_DATE}T00:00:00")
_DAY_SECONDS = 24 * 3600

_SIM_EPOCH = time.monotonic()


def get_sim_time() -> datetime:
    elapsed_real = time.monotonic() - _SIM_EPOCH
    elapsed_sim_seconds = (elapsed_real * SIM_SPEED) % _DAY_SECONDS
    return _DAY_START + timedelta(seconds=elapsed_sim_seconds)


def _interpolate(coord_a: tuple[float, float], coord_b: tuple[float, float], frac: float) -> tuple[float, float]:
    lat = coord_a[0] + (coord_b[0] - coord_a[0]) * frac
    lon = coord_a[1] + (coord_b[1] - coord_a[1]) * frac
    return lat, lon


def _train_position(train: dict, sim_time: datetime) -> LiveTrainPosition | None:
    stops = train["stops"]
    start_time = stops[0]["ref_time"]
    end_time = stops[-1]["ref_time"]

    tnum = train["train_number"]
    base = dict(
        train_number=tnum,
        train_name=train["train_name"],
        train_type=train["train_type"],
        priority=train["priority"],
        corridor_direction=train["corridor_direction"],
    )

    if sim_time < start_time:
        first = stops[0]
        coord = data_store.station_coords.get(first["station_code"])
        return LiveTrainPosition(
            **base,
            status="scheduled",
            from_station=None,
            to_station=first["station_code"],
            progress=0.0,
            latitude=coord[0] if coord else None,
            longitude=coord[1] if coord else None,
            current_delay=0.0,
            predicted_delay_next=None,
            prediction_source=None,
            next_station=first["station_code"],
            eta_next=first["ref_time"].isoformat(),
        )

    if sim_time >= end_time:
        last = stops[-1]
        coord = data_store.station_coords.get(last["station_code"])
        return LiveTrainPosition(
            **base,
            status="completed",
            from_station=last["station_code"],
            to_station=last["station_code"],
            progress=1.0,
            latitude=coord[0] if coord else None,
            longitude=coord[1] if coord else None,
            current_delay=last["current_delay"],
            predicted_delay_next=None,
            prediction_source=None,
            next_station=None,
            eta_next=None,
        )

    # Find bracketing stops a (departed) -> b (approaching).
    for a, b in zip(stops[:-1], stops[1:]):
        if a["ref_time"] <= sim_time < b["ref_time"]:
            span = (b["ref_time"] - a["ref_time"]).total_seconds()
            frac = ((sim_time - a["ref_time"]).total_seconds() / span) if span > 0 else 0.0
            frac = max(0.0, min(1.0, frac))

            coord_a = data_store.station_coords.get(a["station_code"])
            coord_b = data_store.station_coords.get(b["station_code"])
            lat = lon = None
            if coord_a and coord_b:
                lat, lon = _interpolate(coord_a, coord_b, frac)
            elif coord_a:
                lat, lon = coord_a

            pred = predictor.predict(a["feature_row"])

            return LiveTrainPosition(
                **base,
                status="running",
                from_station=a["station_code"],
                to_station=b["station_code"],
                progress=round(frac, 3),
                latitude=lat,
                longitude=lon,
                current_delay=a["current_delay"],
                predicted_delay_next=pred.delay_minutes,
                prediction_source=pred.source,
                next_station=b["station_code"],
                eta_next=b["ref_time"].isoformat(),
            )

    return None


def build_snapshot() -> TwinSnapshot:
    sim_time = get_sim_time()
    trains: list[LiveTrainPosition] = []
    for train in data_store.train_timelines.values():
        pos = _train_position(train, sim_time)
        if pos is not None:
            trains.append(pos)

    stations = [
        StationOut(
            station_code=code,
            station_name=info["station_name"],
            latitude=info["latitude"],
            longitude=info["longitude"],
            platforms=info.get("platforms"),
            main_tracks=info.get("main_tracks"),
            loop_lines=info.get("loop_lines"),
            station_category=info.get("station_category"),
        )
        for code, info in data_store.station_info.items()
        if code in CORRIDOR_STATIONS
    ]

    return TwinSnapshot(
        sim_time=sim_time.isoformat(),
        demo_date=data_store.demo_date,
        sim_speed=SIM_SPEED,
        trains=trains,
        stations=stations,
    )
