"""Pydantic response models for the MVP API."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class StationOut(BaseModel):
    station_code: str
    station_name: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    platforms: Optional[float] = None
    main_tracks: Optional[float] = None
    loop_lines: Optional[float] = None
    station_category: Optional[str] = None


class StopOut(BaseModel):
    station_code: str
    station_sequence: int
    scheduled_arrival: Optional[str] = None
    scheduled_departure: Optional[str] = None
    current_delay: float
    predicted_delay_next: Optional[float] = None
    prediction_source: Optional[str] = None
    status: str  # "done" | "current" | "upcoming"


class TrainSummary(BaseModel):
    train_number: str
    train_name: Optional[str] = None
    train_type: Optional[str] = None
    priority: int
    corridor_direction: Optional[str] = None
    source_station_code: Optional[str] = None
    destination_station_code: Optional[str] = None
    stops: list[str]


class TrainDetail(TrainSummary):
    operating_days: Optional[str] = None
    total_distance_km: Optional[float] = None
    route_stops: list[StopOut]


class LiveTrainPosition(BaseModel):
    train_number: str
    train_name: Optional[str] = None
    train_type: Optional[str] = None
    priority: int
    corridor_direction: Optional[str] = None
    status: str  # "scheduled" | "running" | "completed"
    from_station: Optional[str] = None
    to_station: Optional[str] = None
    progress: float  # 0..1 between from_station and to_station
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    current_delay: float = 0.0
    predicted_delay_next: Optional[float] = None
    prediction_source: Optional[str] = None
    next_station: Optional[str] = None
    eta_next: Optional[str] = None


class TwinSnapshot(BaseModel):
    sim_time: str
    demo_date: str
    sim_speed: float
    trains: list[LiveTrainPosition]
    stations: list[StationOut]


class Recommendation(BaseModel):
    id: str
    train_number: str
    train_name: Optional[str] = None
    station_code: str
    severity: str  # "info" | "warning" | "critical"
    predicted_delay: float
    prediction_source: str
    message: str
    suggested_action: str


class KpiSummary(BaseModel):
    sim_time: str
    demo_date: str
    total_trains: int
    running_trains: int
    avg_current_delay: float
    avg_predicted_delay: float
    on_time_pct: float
    delayed_pct: float
    model_active: bool
    model_name: str
