from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.config import CORRIDOR_STATIONS
from app.data_store import data_store
from app.schemas import StationOut

router = APIRouter(prefix="/api/stations", tags=["stations"])


@router.get("", response_model=list[StationOut])
def list_stations():
    return [
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


@router.get("/{station_code}", response_model=StationOut)
def get_station(station_code: str):
    info = data_store.station_info.get(station_code.upper())
    if not info:
        raise HTTPException(status_code=404, detail="Station not found")
    return StationOut(
        station_code=info["station_code"],
        station_name=info["station_name"],
        latitude=info["latitude"],
        longitude=info["longitude"],
        platforms=info.get("platforms"),
        main_tracks=info.get("main_tracks"),
        loop_lines=info.get("loop_lines"),
        station_category=info.get("station_category"),
    )
