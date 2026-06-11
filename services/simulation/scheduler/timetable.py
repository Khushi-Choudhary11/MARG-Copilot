"""
Timetable Data Model
=====================
Defines the Working Timetable (WTT) data structures and provides
realistic NDLS–CNB corridor sample data with 10 UP trains and 8 DOWN trains.

Time format: minutes-since-midnight (float).
e.g.  06:00 = 360.0,  14:30 = 870.0,  23:59 = 1439.0
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ScheduledStop:
    """One station call in a train's timetable."""
    station_id:       str
    arrive_min:       float          # min-since-midnight; use 0.0 for origin
    depart_min:       float          # min-since-midnight; use 0.0 for terminus
    is_origin:        bool = False
    is_terminus:      bool = False
    platform:         int  = 1


@dataclass(frozen=True)
class TrainSchedule:
    """Complete timetable entry for one train."""
    train_id:       str
    train_name:     str
    category:       str              # 'superfast' | 'mail' | 'express' | 'goods'
    priority:       int              # 0 (highest) … 4 (lowest)
    direction:      str              # 'up' | 'down'
    length_m:       float
    max_speed_kmh:  float
    requires_elec:  bool
    stops:          tuple[ScheduledStop, ...]

    @property
    def origin(self) -> ScheduledStop:
        return self.stops[0]

    @property
    def terminus(self) -> ScheduledStop:
        return self.stops[-1]

    @property
    def total_run_min(self) -> float:
        return self.terminus.arrive_min - self.origin.depart_min


# ── Helper ────────────────────────────────────────────────────────────────────

def hm(h: int, m: int) -> float:
    """Convert hours and minutes to float minutes-since-midnight."""
    return float(h * 60 + m)


# ── NDLS–CNB Corridor Timetable ───────────────────────────────────────────────
#
# Stations in UP direction (NDLS → CNB):
#   NDLS(0) → TKJ(5) → SZM(15) → GZB(28) → DDN(47) → KRJ(90) → SKR(109)
#   → HRS(118) → ALJN(132) → BSWA(148) → MRA(160) → TDL(184) → FZD(197)
#   → SKB(220) → JSN(232) → BRN(244) → ETW(266) → PFD(283) → SFI(296)
#   → KNJ(312) → GSJ(328) → ALJP(342) → PNK(358) → RRL(374) → CNB(441)
#
# Only a representative subset of stops is listed for each train.
# In production, load the full WTT from a database.

NDLS_CNB_TIMETABLE: list[TrainSchedule] = [

    # ── UP TRAINS (NDLS → CNB) ──────────────────────────────────────────────

    TrainSchedule(
        train_id="12301", train_name="Howrah Rajdhani", category="superfast",
        priority=0, direction="up", length_m=640, max_speed_kmh=130, requires_elec=True,
        stops=(
            ScheduledStop("NDLS", 0,          hm(6, 0),  is_origin=True),
            ScheduledStop("GZB",  hm(6, 20),  hm(6, 22)),
            ScheduledStop("ALJN", hm(7, 18),  hm(7, 20)),
            ScheduledStop("TDL",  hm(8, 12),  hm(8, 14)),
            ScheduledStop("ETW",  hm(9, 5),   hm(9, 7)),
            ScheduledStop("CNB",  hm(10, 15), 0,         is_terminus=True),
        ),
    ),

    TrainSchedule(
        train_id="12309", train_name="Rajendra Nagar Rajdhani", category="superfast",
        priority=0, direction="up", length_m=620, max_speed_kmh=130, requires_elec=True,
        stops=(
            ScheduledStop("NDLS", 0,          hm(7, 30),  is_origin=True),
            ScheduledStop("GZB",  hm(7, 50),  hm(7, 52)),
            ScheduledStop("ALJN", hm(8, 48),  hm(8, 50)),
            ScheduledStop("TDL",  hm(9, 42),  hm(9, 44)),
            ScheduledStop("ETW",  hm(10, 35), hm(10, 37)),
            ScheduledStop("CNB",  hm(11, 45), 0,          is_terminus=True),
        ),
    ),

    TrainSchedule(
        train_id="12311", train_name="Kalka Mail", category="mail",
        priority=1, direction="up", length_m=580, max_speed_kmh=110, requires_elec=True,
        stops=(
            ScheduledStop("NDLS", 0,          hm(6, 45),  is_origin=True),
            ScheduledStop("SZM",  hm(7, 0),   hm(7, 2)),
            ScheduledStop("GZB",  hm(7, 15),  hm(7, 18)),
            ScheduledStop("KRJ",  hm(8, 5),   hm(8, 8)),
            ScheduledStop("ALJN", hm(8, 55),  hm(8, 58)),
            ScheduledStop("TDL",  hm(9, 50),  hm(9, 53)),
            ScheduledStop("FZD",  hm(10, 22), hm(10, 25)),
            ScheduledStop("ETW",  hm(11, 15), hm(11, 18)),
            ScheduledStop("KNJ",  hm(12, 5),  hm(12, 7)),
            ScheduledStop("CNB",  hm(13, 0),  0,          is_terminus=True),
        ),
    ),

    TrainSchedule(
        train_id="14015", train_name="Shramjeevi Express", category="express",
        priority=2, direction="up", length_m=560, max_speed_kmh=100, requires_elec=True,
        stops=(
            ScheduledStop("NDLS", 0,           hm(8, 15),  is_origin=True),
            ScheduledStop("GZB",  hm(8, 40),   hm(8, 43)),
            ScheduledStop("HRS",  hm(9, 50),   hm(9, 53)),
            ScheduledStop("ALJN", hm(10, 25),  hm(10, 28)),
            ScheduledStop("TDL",  hm(11, 22),  hm(11, 25)),
            ScheduledStop("SKB",  hm(12, 20),  hm(12, 23)),
            ScheduledStop("ETW",  hm(13, 10),  hm(13, 13)),
            ScheduledStop("KNJ",  hm(14, 5),   hm(14, 8)),
            ScheduledStop("CNB",  hm(15, 0),   0,          is_terminus=True),
        ),
    ),

    TrainSchedule(
        train_id="14311", train_name="Ala Hazrat Express", category="express",
        priority=2, direction="up", length_m=540, max_speed_kmh=100, requires_elec=True,
        stops=(
            ScheduledStop("NDLS", 0,           hm(9, 0),   is_origin=True),
            ScheduledStop("GZB",  hm(9, 25),   hm(9, 28)),
            ScheduledStop("DDN",  hm(10, 5),   hm(10, 8)),
            ScheduledStop("ALJN", hm(11, 15),  hm(11, 18)),
            ScheduledStop("TDL",  hm(12, 12),  hm(12, 15)),
            ScheduledStop("FZD",  hm(12, 50),  hm(12, 53)),
            ScheduledStop("ETW",  hm(13, 42),  hm(13, 45)),
            ScheduledStop("CNB",  hm(15, 30),  0,          is_terminus=True),
        ),
    ),

    TrainSchedule(
        train_id="12107", train_name="Lucknow Mail", category="mail",
        priority=1, direction="up", length_m=560, max_speed_kmh=110, requires_elec=True,
        stops=(
            ScheduledStop("NDLS", 0,           hm(10, 0),  is_origin=True),
            ScheduledStop("GZB",  hm(10, 22),  hm(10, 25)),
            ScheduledStop("ALJN", hm(11, 30),  hm(11, 33)),
            ScheduledStop("TDL",  hm(12, 25),  hm(12, 28)),
            ScheduledStop("ETW",  hm(13, 22),  hm(13, 25)),
            ScheduledStop("KNJ",  hm(14, 20),  hm(14, 22)),
            ScheduledStop("CNB",  hm(15, 15),  0,          is_terminus=True),
        ),
    ),

    TrainSchedule(
        train_id="70501", train_name="NDLS-CNB Goods", category="goods",
        priority=4, direction="up", length_m=720, max_speed_kmh=75, requires_elec=False,
        stops=(
            ScheduledStop("NDLS", 0,           hm(11, 30),  is_origin=True),
            ScheduledStop("GZB",  hm(12, 10),  hm(12, 20)),
            ScheduledStop("ALJN", hm(13, 50),  hm(14, 5)),
            ScheduledStop("TDL",  hm(15, 30),  hm(15, 45)),
            ScheduledStop("FZD",  hm(16, 45),  hm(17, 0)),
            ScheduledStop("ETW",  hm(18, 30),  hm(18, 45)),
            ScheduledStop("CNB",  hm(21, 0),   0,           is_terminus=True),
        ),
    ),

    TrainSchedule(
        train_id="70503", train_name="GZB-CNB Freight", category="goods",
        priority=4, direction="up", length_m=750, max_speed_kmh=70, requires_elec=False,
        stops=(
            ScheduledStop("GZB",  0,           hm(13, 0),  is_origin=True),
            ScheduledStop("DDN",  hm(13, 45),  hm(14, 0)),
            ScheduledStop("KRJ",  hm(15, 0),   hm(15, 15)),
            ScheduledStop("ALJN", hm(16, 20),  hm(16, 35)),
            ScheduledStop("TDL",  hm(18, 0),   hm(18, 15)),
            ScheduledStop("SKB",  hm(19, 30),  hm(19, 45)),
            ScheduledStop("ETW",  hm(21, 15),  hm(21, 30)),
            ScheduledStop("CNB",  hm(23, 0),   0,          is_terminus=True),
        ),
    ),

    # ── DOWN TRAINS (CNB → NDLS) ─────────────────────────────────────────────

    TrainSchedule(
        train_id="12302", train_name="Howrah Rajdhani (Down)", category="superfast",
        priority=0, direction="down", length_m=640, max_speed_kmh=130, requires_elec=True,
        stops=(
            ScheduledStop("CNB",  0,           hm(7, 0),   is_origin=True),
            ScheduledStop("ETW",  hm(8, 10),   hm(8, 12)),
            ScheduledStop("TDL",  hm(9, 5),    hm(9, 7)),
            ScheduledStop("ALJN", hm(10, 0),   hm(10, 2)),
            ScheduledStop("GZB",  hm(10, 58),  hm(11, 0)),
            ScheduledStop("NDLS", hm(11, 20),  0,          is_terminus=True),
        ),
    ),

    TrainSchedule(
        train_id="12310", train_name="Rajendra Nagar Rajdhani (Down)", category="superfast",
        priority=0, direction="down", length_m=620, max_speed_kmh=130, requires_elec=True,
        stops=(
            ScheduledStop("CNB",  0,           hm(8, 30),  is_origin=True),
            ScheduledStop("ETW",  hm(9, 40),   hm(9, 42)),
            ScheduledStop("TDL",  hm(10, 35),  hm(10, 37)),
            ScheduledStop("ALJN", hm(11, 30),  hm(11, 32)),
            ScheduledStop("GZB",  hm(12, 28),  hm(12, 30)),
            ScheduledStop("NDLS", hm(12, 50),  0,          is_terminus=True),
        ),
    ),

    TrainSchedule(
        train_id="12312", train_name="Kalka Mail (Down)", category="mail",
        priority=1, direction="down", length_m=580, max_speed_kmh=110, requires_elec=True,
        stops=(
            ScheduledStop("CNB",  0,           hm(9, 15),  is_origin=True),
            ScheduledStop("KNJ",  hm(10, 15),  hm(10, 17)),
            ScheduledStop("ETW",  hm(11, 5),   hm(11, 8)),
            ScheduledStop("FZD",  hm(11, 58),  hm(12, 1)),
            ScheduledStop("TDL",  hm(12, 30),  hm(12, 33)),
            ScheduledStop("ALJN", hm(13, 28),  hm(13, 31)),
            ScheduledStop("GZB",  hm(14, 28),  hm(14, 31)),
            ScheduledStop("NDLS", hm(14, 52),  0,          is_terminus=True),
        ),
    ),

    TrainSchedule(
        train_id="14016", train_name="Shramjeevi Express (Down)", category="express",
        priority=2, direction="down", length_m=560, max_speed_kmh=100, requires_elec=True,
        stops=(
            ScheduledStop("CNB",  0,           hm(10, 30), is_origin=True),
            ScheduledStop("KNJ",  hm(11, 25),  hm(11, 28)),
            ScheduledStop("ETW",  hm(12, 20),  hm(12, 23)),
            ScheduledStop("SKB",  hm(13, 15),  hm(13, 18)),
            ScheduledStop("TDL",  hm(14, 10),  hm(14, 13)),
            ScheduledStop("ALJN", hm(15, 5),   hm(15, 8)),
            ScheduledStop("GZB",  hm(16, 5),   hm(16, 8)),
            ScheduledStop("NDLS", hm(16, 30),  0,          is_terminus=True),
        ),
    ),

    TrainSchedule(
        train_id="70502", train_name="CNB-NDLS Goods", category="goods",
        priority=4, direction="down", length_m=720, max_speed_kmh=75, requires_elec=False,
        stops=(
            ScheduledStop("CNB",  0,           hm(6, 0),   is_origin=True),
            ScheduledStop("ETW",  hm(7, 45),   hm(8, 0)),
            ScheduledStop("FZD",  hm(9, 30),   hm(9, 45)),
            ScheduledStop("TDL",  hm(10, 45),  hm(11, 0)),
            ScheduledStop("ALJN", hm(12, 30),  hm(12, 45)),
            ScheduledStop("GZB",  hm(14, 30),  hm(14, 45)),
            ScheduledStop("NDLS", hm(15, 30),  0,          is_terminus=True),
        ),
    ),

    TrainSchedule(
        train_id="70504", train_name="CNB-GZB Freight", category="goods",
        priority=4, direction="down", length_m=750, max_speed_kmh=70, requires_elec=False,
        stops=(
            ScheduledStop("CNB",  0,           hm(14, 0),  is_origin=True),
            ScheduledStop("ETW",  hm(15, 45),  hm(16, 0)),
            ScheduledStop("SKB",  hm(17, 30),  hm(17, 45)),
            ScheduledStop("TDL",  hm(19, 0),   hm(19, 15)),
            ScheduledStop("ALJN", hm(20, 45),  hm(21, 0)),
            ScheduledStop("GZB",  hm(22, 45),  hm(23, 0)),
            ScheduledStop("NDLS", hm(23, 55),  0,          is_terminus=True),
        ),
    ),
]


# Quick index lookups
SCHEDULE_BY_ID: dict[str, TrainSchedule] = {
    s.train_id: s for s in NDLS_CNB_TIMETABLE
}


def get_schedule(train_id: str) -> TrainSchedule:
    if train_id not in SCHEDULE_BY_ID:
        raise KeyError(f"Unknown train_id '{train_id}'. "
                       f"Known: {sorted(SCHEDULE_BY_ID.keys())}")
    return SCHEDULE_BY_ID[train_id]


def trains_active_between(start_min: float, end_min: float) -> list[TrainSchedule]:
    """Return schedules for trains that depart origin between start and end."""
    return [
        s for s in NDLS_CNB_TIMETABLE
        if start_min <= s.origin.depart_min <= end_min
    ]
