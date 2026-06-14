"""
Loads static + demo-day data once at startup and exposes it as in-memory
pandas structures / lookup dicts. No database for the MVP.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from app.config import (
    CORRIDOR_STATIONS,
    DEMO_DATE,
    MASTER_DATA_PATH,
    MASTER_DATA_URL,
    SECTION_INFRA_PATH,
    STATION_INFRA_PATH,
    STATIONS_PATH,
    TRAIN_MASTER_PATH,
    TRAIN_ROUTES_PATH,
)

logger = logging.getLogger(__name__)


def _read_master_dataset() -> pd.DataFrame:
    if MASTER_DATA_URL:
        logger.info("Loading master dataset from URL: %s", MASTER_DATA_URL)
        return pd.read_csv(MASTER_DATA_URL)

    logger.info("Loading master dataset from local path: %s", MASTER_DATA_PATH)
    return pd.read_csv(MASTER_DATA_PATH)


def _parse_dt(value) -> datetime | None:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    if isinstance(value, str):
        if not value or value.lower() == "nan":
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


class DataStore:
    def __init__(self) -> None:
        logger.info("Loading static data...")
        self.stations = pd.read_csv(STATIONS_PATH)
        self.train_master = pd.read_csv(TRAIN_MASTER_PATH)
        self.train_routes = pd.read_csv(TRAIN_ROUTES_PATH)
        self.station_infra = pd.read_csv(STATION_INFRA_PATH)
        self.section_infra = pd.read_csv(SECTION_INFRA_PATH)

        logger.info("Loading master dataset for demo date %s...", DEMO_DATE)
        master = _read_master_dataset()
        self.demo_date = DEMO_DATE
        self.demo_rows = master[master["date"] == DEMO_DATE].copy()
        if self.demo_rows.empty:
            # Fall back to the most recent available date in the dataset.
            self.demo_date = master["date"].max()
            self.demo_rows = master[master["date"] == self.demo_date].copy()
            logger.warning("No data for %s, using %s instead", DEMO_DATE, self.demo_date)

        # Station coordinates for the corridor.
        self.station_coords: dict[str, tuple[float, float]] = {}
        for _, r in self.stations[self.stations["station_code"].isin(CORRIDOR_STATIONS)].iterrows():
            self.station_coords[r["station_code"]] = (float(r["latitude"]), float(r["longitude"]))

        self.station_info: dict[str, dict] = {
            r["station_code"]: {
                "station_code": r["station_code"],
                "station_name": r["station_name"],
                "latitude": float(r["latitude"]) if not pd.isna(r["latitude"]) else None,
                "longitude": float(r["longitude"]) if not pd.isna(r["longitude"]) else None,
            }
            for _, r in self.stations[self.stations["station_code"].isin(CORRIDOR_STATIONS)].iterrows()
        }
        infra_by_code = self.station_infra.set_index("station_code").to_dict("index")
        for code, info in self.station_info.items():
            infra = infra_by_code.get(code, {})
            info["platforms"] = infra.get("platforms")
            info["main_tracks"] = infra.get("main_tracks")
            info["loop_lines"] = infra.get("loop_lines")
            info["station_category"] = infra.get("station_category")

        self.train_timelines = self._build_train_timelines()
        logger.info(
            "Loaded %d trains with corridor timelines on demo date %s",
            len(self.train_timelines),
            self.demo_date,
        )

    def _build_train_timelines(self) -> dict[str, dict]:
        """For every train that touches the corridor on the demo date, build an
        ordered list of corridor stops with scheduled/actual times and the full
        feature row (for model prediction)."""
        corridor_rows = self.demo_rows[self.demo_rows["station_code"].isin(CORRIDOR_STATIONS)]
        timelines: dict[str, dict] = {}

        train_info = self.train_master.set_index("train_number").to_dict("index")

        for train_number, group in corridor_rows.groupby("train_number"):
            group = group.sort_values("station_sequence")
            stops = []
            for _, r in group.iterrows():
                sched_arr = _parse_dt(r.get("scheduled_arrival"))
                sched_dep = _parse_dt(r.get("scheduled_departure"))
                act_arr = _parse_dt(r.get("actual_arrival"))
                act_dep = _parse_dt(r.get("actual_departure"))
                # Reference time used to order/animate this stop along the day.
                ref_time = sched_arr or sched_dep
                if ref_time is None:
                    continue
                stops.append(
                    {
                        "station_code": r["station_code"],
                        "station_sequence": int(r["station_sequence"]),
                        "scheduled_arrival": sched_arr,
                        "scheduled_departure": sched_dep,
                        "actual_arrival": act_arr,
                        "actual_departure": act_dep,
                        "ref_time": ref_time,
                        "current_delay": float(r["current_delay"]) if not pd.isna(r["current_delay"]) else 0.0,
                        "delay_next_station": (
                            float(r["delay_next_station"]) if not pd.isna(r["delay_next_station"]) else None
                        ),
                        "feature_row": r.to_dict(),
                    }
                )
            if len(stops) < 2:
                continue
            stops.sort(key=lambda s: s["ref_time"])

            first_row = group.iloc[0]
            tnum = str(train_number)
            info = train_info.get(int(train_number) if str(train_number).isdigit() else train_number, {})
            timelines[tnum] = {
                "train_number": tnum,
                "train_name": first_row.get("train_name"),
                "train_type": first_row.get("train_type"),
                "priority": int(first_row["priority"]) if not pd.isna(first_row["priority"]) else 5,
                "corridor_direction": first_row.get("corridor_direction"),
                "source_station_code": first_row.get("source_station_code"),
                "destination_station_code": first_row.get("destination_station_code"),
                "operating_days": info.get("operating_days", "UNKNOWN"),
                "total_distance_km": info.get("total_distance_km"),
                "stops": stops,
                "start_time": stops[0]["ref_time"],
                "end_time": stops[-1]["ref_time"],
            }
        return timelines

    def get_train(self, train_number: str) -> dict | None:
        return self.train_timelines.get(str(train_number))

    def all_trains_summary(self) -> list[dict]:
        out = []
        for tnum, t in self.train_timelines.items():
            out.append(
                {
                    "train_number": tnum,
                    "train_name": t["train_name"],
                    "train_type": t["train_type"],
                    "priority": t["priority"],
                    "corridor_direction": t["corridor_direction"],
                    "source_station_code": t["source_station_code"],
                    "destination_station_code": t["destination_station_code"],
                    "stops": [s["station_code"] for s in t["stops"]],
                }
            )
        return out


# Module-level singleton, loaded once at app startup.
data_store = DataStore()
