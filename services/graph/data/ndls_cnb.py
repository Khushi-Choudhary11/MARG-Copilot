"""
NDLS–CNB Corridor Data — Hard-coded ground truth.

New Delhi (NDLS) → Kanpur Central (CNB), ~441 km.
One of India's busiest rail corridors, carrying ~23 M passengers daily
across the broader Delhi–Howrah main line of which this is the western segment.

All chainage values are in kilometres from NDLS (datum = 0.0).
Coordinates are WGS-84 (latitude, longitude).
Speed limits are sourced from the IR Working Timetable for this section.

Data is intentionally defined as plain Python (not JSON/YAML) so that
the compiler catches typos at import time and IDEs provide autocomplete.
"""

from __future__ import annotations
from typing import Sequence

from ..models.enums import (
    Direction,
    ElectrificationType,
    LineType,
    LoopLineType,
    StationClass,
)
from ..models.loop_line import LoopLine
from ..models.section import SignalBlock, TrackSection
from ..models.station import Platform, Station


# ── Stations ──────────────────────────────────────────────────────────────────

def _make_platforms(station_id: str, count: int,
                    length_m: float = 700.0) -> tuple[Platform, ...]:
    return tuple(
        Platform(
            platform_id=f"{station_id}_P{i}",
            platform_number=i,
            length_meters=length_m,
        )
        for i in range(1, count + 1)
    )


def _loop(station_id: str, idx: int, length_m: float,
          loop_type: LoopLineType = LoopLineType.CROSSING,
          electrified: bool = True) -> LoopLine:
    elec = (
        ElectrificationType.AC_25KV if electrified
        else ElectrificationType.DIESEL
    )
    return LoopLine(
        loop_id=f"{station_id}_L{idx}",
        station_id=station_id,
        loop_type=loop_type,
        length_meters=length_m,
        electrification=elec,
    )


STATIONS: tuple[Station, ...] = (

    Station(
        station_id="NDLS",
        name="New Delhi",
        chainage_km=0.0,
        station_class=StationClass.A1,
        latitude=28.6419,
        longitude=77.2194,
        platforms=_make_platforms("NDLS", 16, 750),
        loop_lines=(),                        # terminus — no crossing loops
        main_lines=16,
        is_terminus=True,
        is_crew_change_point=True,
        is_loco_change_point=True,
        elevation_m=216.0,
        notes="Origin terminus. Major crew/loco change depot.",
    ),

    Station(
        station_id="TKJ",
        name="Tilak Bridge",
        chainage_km=5.0,
        station_class=StationClass.D,
        latitude=28.6440,
        longitude=77.2498,
        platforms=_make_platforms("TKJ", 2, 400),
        loop_lines=(),
        main_lines=4,
        elevation_m=213.0,
    ),

    Station(
        station_id="SZM",
        name="Sahibabad",
        chainage_km=15.0,
        station_class=StationClass.C,
        latitude=28.6692,
        longitude=77.3494,
        platforms=_make_platforms("SZM", 2, 500),
        loop_lines=(_loop("SZM", 1, 580, LoopLineType.CROSSING),),
        main_lines=2,
        elevation_m=208.0,
    ),

    Station(
        station_id="GZB",
        name="Ghaziabad Junction",
        chainage_km=28.0,
        station_class=StationClass.A,
        latitude=28.6668,
        longitude=77.4168,
        platforms=_make_platforms("GZB", 6, 720),
        loop_lines=(
            _loop("GZB", 1, 750, LoopLineType.CROSSING),
            _loop("GZB", 2, 750, LoopLineType.CROSSING),
            _loop("GZB", 3, 680, LoopLineType.GOODS),
        ),
        main_lines=4,
        is_junction=True,
        is_crew_change_point=True,
        elevation_m=205.0,
        notes="Major junction. Delhi–Howrah + Delhi–Moradabad diverge here.",
    ),

    Station(
        station_id="DDN",
        name="Dadri",
        chainage_km=47.0,
        station_class=StationClass.C,
        latitude=28.5536,
        longitude=77.5537,
        platforms=_make_platforms("DDN", 3, 600),
        loop_lines=(
            _loop("DDN", 1, 680, LoopLineType.CROSSING),
            _loop("DDN", 2, 640, LoopLineType.CROSSING),
        ),
        main_lines=2,
        elevation_m=198.0,
    ),

    Station(
        station_id="KRJ",
        name="Khurja Junction",
        chainage_km=90.0,
        station_class=StationClass.B,
        latitude=28.2561,
        longitude=77.8592,
        platforms=_make_platforms("KRJ", 5, 700),
        loop_lines=(
            _loop("KRJ", 1, 760, LoopLineType.CROSSING),
            _loop("KRJ", 2, 760, LoopLineType.CROSSING),
            _loop("KRJ", 3, 700, LoopLineType.OVERTAKING),
            _loop("KRJ", 4, 650, LoopLineType.GOODS),
        ),
        main_lines=3,
        is_junction=True,
        is_crew_change_point=True,
        elevation_m=194.0,
        notes="Crew change point. Junction with Khurja–Hapur line.",
    ),

    Station(
        station_id="SKR",
        name="Sikandra Rao",
        chainage_km=109.0,
        station_class=StationClass.C,
        latitude=27.9998,
        longitude=78.0003,
        platforms=_make_platforms("SKR", 3, 600),
        loop_lines=(
            _loop("SKR", 1, 660, LoopLineType.CROSSING),
            _loop("SKR", 2, 620, LoopLineType.CROSSING),
        ),
        main_lines=2,
        elevation_m=192.0,
    ),

    Station(
        station_id="HRS",
        name="Hathras Junction",
        chainage_km=118.0,
        station_class=StationClass.B,
        latitude=27.5945,
        longitude=78.0538,
        platforms=_make_platforms("HRS", 4, 650),
        loop_lines=(
            _loop("HRS", 1, 700, LoopLineType.CROSSING),
            _loop("HRS", 2, 680, LoopLineType.CROSSING),
        ),
        main_lines=2,
        is_junction=True,
        elevation_m=188.0,
        notes="Junction with Hathras–Mathura branch.",
    ),

    Station(
        station_id="ALJN",
        name="Aligarh Junction",
        chainage_km=132.0,
        station_class=StationClass.A,
        latitude=27.8974,
        longitude=78.0880,
        platforms=_make_platforms("ALJN", 7, 730),
        loop_lines=(
            _loop("ALJN", 1, 740, LoopLineType.CROSSING),
            _loop("ALJN", 2, 720, LoopLineType.CROSSING),
            _loop("ALJN", 3, 700, LoopLineType.OVERTAKING),
            _loop("ALJN", 4, 680, LoopLineType.GOODS),
            _loop("ALJN", 5, 650, LoopLineType.GOODS),
        ),
        main_lines=3,
        is_junction=True,
        is_crew_change_point=True,
        elevation_m=185.0,
        notes="Major junction. Chronic congestion hotspot. Loop L2 has steep departure gradient.",
    ),

    Station(
        station_id="BSWA",
        name="Beswan",
        chainage_km=148.0,
        station_class=StationClass.D,
        latitude=27.7012,
        longitude=78.1867,
        platforms=_make_platforms("BSWA", 2, 550),
        loop_lines=(_loop("BSWA", 1, 620, LoopLineType.CROSSING),),
        main_lines=2,
        elevation_m=182.0,
    ),

    Station(
        station_id="MRA",
        name="Mursan",
        chainage_km=160.0,
        station_class=StationClass.D,
        latitude=27.5667,
        longitude=78.2431,
        platforms=_make_platforms("MRA", 2, 540),
        loop_lines=(_loop("MRA", 1, 600, LoopLineType.CROSSING),),
        main_lines=2,
        elevation_m=180.0,
    ),

    Station(
        station_id="TDL",
        name="Tundla Junction",
        chainage_km=184.0,
        station_class=StationClass.A,
        latitude=27.2100,
        longitude=78.2440,
        platforms=_make_platforms("TDL", 6, 750),
        loop_lines=(
            _loop("TDL", 1, 800, LoopLineType.CROSSING),
            _loop("TDL", 2, 780, LoopLineType.CROSSING),
            _loop("TDL", 3, 760, LoopLineType.OVERTAKING),
            _loop("TDL", 4, 730, LoopLineType.GOODS),
            _loop("TDL", 5, 700, LoopLineType.GOODS),
        ),
        main_lines=4,
        is_junction=True,
        is_crew_change_point=True,
        is_loco_change_point=True,
        elevation_m=177.0,
        notes="Key junction. Loco change depot. Trains from AGC direction converge here.",
    ),

    Station(
        station_id="FZD",
        name="Firozabad",
        chainage_km=197.0,
        station_class=StationClass.C,
        latitude=27.1500,
        longitude=78.3950,
        platforms=_make_platforms("FZD", 4, 660),
        loop_lines=(
            _loop("FZD", 1, 640, LoopLineType.CROSSING),
            _loop("FZD", 2, 610, LoopLineType.CROSSING),
        ),
        main_lines=2,
        elevation_m=174.0,
        notes="Known for frequent signal relay failures in summer heat (Apr–Jun).",
    ),

    Station(
        station_id="SKB",
        name="Shikohabad Junction",
        chainage_km=220.0,
        station_class=StationClass.C,
        latitude=27.1009,
        longitude=78.5883,
        platforms=_make_platforms("SKB", 4, 660),
        loop_lines=(
            _loop("SKB", 1, 680, LoopLineType.CROSSING),
            _loop("SKB", 2, 650, LoopLineType.CROSSING),
            _loop("SKB", 3, 620, LoopLineType.GOODS),
        ),
        main_lines=2,
        is_junction=True,
        elevation_m=170.0,
        notes="Junction with Mainpuri branch. Alternative crossing point for TDL-blocked goods trains.",
    ),

    Station(
        station_id="JSN",
        name="Jasrana",
        chainage_km=232.0,
        station_class=StationClass.D,
        latitude=27.0501,
        longitude=78.6820,
        platforms=_make_platforms("JSN", 2, 560),
        loop_lines=(_loop("JSN", 1, 620, LoopLineType.CROSSING),),
        main_lines=2,
        elevation_m=168.0,
    ),

    Station(
        station_id="BRN",
        name="Bharthana",
        chainage_km=244.0,
        station_class=StationClass.D,
        latitude=26.9980,
        longitude=78.7812,
        platforms=_make_platforms("BRN", 2, 580),
        loop_lines=(
            _loop("BRN", 1, 660, LoopLineType.CROSSING),
            _loop("BRN", 2, 640, LoopLineType.CROSSING),
        ),
        main_lines=2,
        elevation_m=165.0,
        notes="Preferred crossing point for long goods trains due to generous loop lengths.",
    ),

    Station(
        station_id="ETW",
        name="Etawah",
        chainage_km=266.0,
        station_class=StationClass.B,
        latitude=26.7773,
        longitude=79.0199,
        platforms=_make_platforms("ETW", 5, 680),
        loop_lines=(
            _loop("ETW", 1, 680, LoopLineType.CROSSING),
            _loop("ETW", 2, 650, LoopLineType.CROSSING),
            _loop("ETW", 3, 640, LoopLineType.OVERTAKING),
            _loop("ETW", 4, 700, LoopLineType.GOODS),
        ),
        main_lines=2,
        is_crew_change_point=True,
        elevation_m=157.0,
        notes="Crew change point. Loop L1 marginally short for 24-coach passenger (needs 640m).",
    ),

    Station(
        station_id="PFD",
        name="Phaphund",
        chainage_km=283.0,
        station_class=StationClass.D,
        latitude=26.5998,
        longitude=79.1501,
        platforms=_make_platforms("PFD", 2, 560),
        loop_lines=(_loop("PFD", 1, 620, LoopLineType.CROSSING),),
        main_lines=2,
        elevation_m=152.0,
    ),

    Station(
        station_id="SFI",
        name="Saifai",
        chainage_km=296.0,
        station_class=StationClass.D,
        latitude=26.5011,
        longitude=79.2198,
        platforms=_make_platforms("SFI", 2, 560),
        loop_lines=(_loop("SFI", 1, 600, LoopLineType.CROSSING),),
        main_lines=2,
        elevation_m=148.0,
    ),

    Station(
        station_id="KNJ",
        name="Kannauj",
        chainage_km=312.0,
        station_class=StationClass.C,
        latitude=27.0601,
        longitude=79.9201,
        platforms=_make_platforms("KNJ", 3, 620),
        loop_lines=(
            _loop("KNJ", 1, 660, LoopLineType.CROSSING),
            _loop("KNJ", 2, 640, LoopLineType.CROSSING),
        ),
        main_lines=2,
        elevation_m=141.0,
    ),

    Station(
        station_id="GSJ",
        name="Gursahaiganj",
        chainage_km=328.0,
        station_class=StationClass.D,
        latitude=27.1201,
        longitude=80.0512,
        platforms=_make_platforms("GSJ", 2, 540),
        loop_lines=(_loop("GSJ", 1, 600, LoopLineType.CROSSING),),
        main_lines=2,
        elevation_m=136.0,
    ),

    Station(
        station_id="ALJP",
        name="Ajiganj",
        chainage_km=342.0,
        station_class=StationClass.D,
        latitude=27.1801,
        longitude=80.1200,
        platforms=_make_platforms("ALJP", 2, 530),
        loop_lines=(_loop("ALJP", 1, 590, LoopLineType.CROSSING),),
        main_lines=2,
        elevation_m=132.0,
    ),

    Station(
        station_id="PNK",
        name="Panka",
        chainage_km=358.0,
        station_class=StationClass.D,
        latitude=27.2001,
        longitude=80.2014,
        platforms=_make_platforms("PNK", 2, 530),
        loop_lines=(_loop("PNK", 1, 590, LoopLineType.CROSSING),),
        main_lines=2,
        elevation_m=129.0,
    ),

    Station(
        station_id="RRL",
        name="Rura",
        chainage_km=374.0,
        station_class=StationClass.C,
        latitude=26.5001,
        longitude=80.2512,
        platforms=_make_platforms("RRL", 3, 600),
        loop_lines=(
            _loop("RRL", 1, 640, LoopLineType.CROSSING),
            _loop("RRL", 2, 620, LoopLineType.CROSSING),
        ),
        main_lines=2,
        elevation_m=126.0,
    ),

    Station(
        station_id="CNB",
        name="Kanpur Central",
        chainage_km=441.0,
        station_class=StationClass.A1,
        latitude=26.4499,
        longitude=80.3319,
        platforms=_make_platforms("CNB", 10, 760),
        loop_lines=(
            _loop("CNB", 1, 800, LoopLineType.GOODS),
            _loop("CNB", 2, 800, LoopLineType.GOODS),
            _loop("CNB", 3, 760, LoopLineType.STABLING),
        ),
        main_lines=8,
        is_terminus=True,
        is_crew_change_point=True,
        is_loco_change_point=True,
        elevation_m=126.0,
        notes="Destination terminus. Major yard for goods trains.",
    ),
)

# Index for fast lookup
STATION_INDEX: dict[str, Station] = {s.station_id: s for s in STATIONS}

# Ordered station list (UP direction, increasing chainage)
STATION_ORDER_UP: tuple[str, ...] = tuple(s.station_id for s in STATIONS)


# ── Track Sections ─────────────────────────────────────────────────────────────

def _blocks(section_id: str, n: int,
            length_km: float, headway_s: int = 300) -> tuple[SignalBlock, ...]:
    """Generate `n` equal-length signal blocks for a section."""
    block_len = length_km / n
    return tuple(
        SignalBlock(
            block_id=f"{section_id}_B{i}",
            length_km=round(block_len, 3),
            min_headway_seconds=headway_s,
        )
        for i in range(1, n + 1)
    )


def _section(
    from_s: str, to_s: str,
    length_km: float,
    line_type: LineType,
    pax_kmh: float,
    frt_kmh: float,
    gradient_pct: float = 0.0,
    num_blocks: int = 3,
    headway_s: int = 300,
    notes: str = "",
) -> tuple[TrackSection, TrackSection]:
    """
    Create a pair of UP and DOWN TrackSection objects for a given pair
    of adjacent stations. Both directions share the same physical attributes.
    """
    sid_up   = f"{from_s}_{to_s}_UP"
    sid_down = f"{to_s}_{from_s}_DN"

    blocks_up   = _blocks(sid_up,   num_blocks, length_km, headway_s)
    blocks_down = _blocks(sid_down, num_blocks, length_km, headway_s)

    up = TrackSection(
        section_id=sid_up,
        from_station_id=from_s,
        to_station_id=to_s,
        direction=Direction.UP,
        length_km=length_km,
        line_type=line_type,
        max_speed_passenger_kmh=pax_kmh,
        max_speed_freight_kmh=frt_kmh,
        ruling_gradient_pct=gradient_pct,
        signal_blocks=blocks_up,
        notes=notes,
    )
    down = TrackSection(
        section_id=sid_down,
        from_station_id=to_s,
        to_station_id=from_s,
        direction=Direction.DOWN,
        length_km=length_km,
        line_type=line_type,
        max_speed_passenger_kmh=pax_kmh,
        max_speed_freight_kmh=frt_kmh,
        ruling_gradient_pct=-gradient_pct,   # reversed for opposite direction
        signal_blocks=blocks_down,
        notes=notes,
    )
    return up, down


# All section pairs (UP, DOWN) between adjacent stations.
# Speed limits sourced from IR WTT for Delhi Division / Allahabad Division.
_RAW_SECTIONS: list[tuple[TrackSection, TrackSection]] = [
    _section("NDLS", "TKJ",  5.0,  LineType.DOUBLE, 130, 75, 0.0,  2, 240),
    _section("TKJ",  "SZM", 10.0,  LineType.DOUBLE, 130, 75, 0.0,  2, 240),
    _section("SZM",  "GZB", 13.0,  LineType.DOUBLE, 130, 75, 0.0,  3, 240),
    _section("GZB",  "DDN", 19.0,  LineType.DOUBLE, 130, 75, 0.0,  4, 300),
    _section("DDN",  "KRJ", 43.0,  LineType.DOUBLE, 120, 75, 0.1,  6, 300,
             "Gradual descent towards Yamuna plain."),
    _section("KRJ",  "SKR", 19.0,  LineType.DOUBLE, 120, 75, 0.0,  3, 300),
    _section("SKR",  "HRS",  9.0,  LineType.DOUBLE, 110, 70, 0.0,  2, 300),
    _section("HRS",  "ALJN",14.0,  LineType.DOUBLE, 110, 70, 0.0,  3, 300,
             "Approaches Aligarh — frequent signal congestion at peak."),
    _section("ALJN", "BSWA",16.0,  LineType.DOUBLE, 110, 70, 0.2,  3, 300),
    _section("BSWA", "MRA", 12.0,  LineType.DOUBLE, 110, 70, 0.1,  2, 300),
    _section("MRA",  "TDL", 24.0,  LineType.DOUBLE, 110, 70, 0.1,  4, 300,
             "Double line. Convergence from AGC adds pressure near TDL."),
    _section("TDL",  "FZD", 13.0,  LineType.DOUBLE, 120, 75, 0.0,  3, 300,
             "Signal relay failures reported in summer. CAUTION."),
    _section("FZD",  "SKB", 23.0,  LineType.SINGLE, 100, 65, 0.0,  4, 360,
             "SINGLE LINE section — crossing mandatory."),
    _section("SKB",  "JSN", 12.0,  LineType.SINGLE,  90, 65, 0.0,  3, 360),
    _section("JSN",  "BRN", 12.0,  LineType.SINGLE,  90, 60, 0.0,  3, 360),
    _section("BRN",  "ETW", 22.0,  LineType.DOUBLE, 110, 70, 0.0,  4, 300,
             "Returns to double line. Flood risk Jul–Sep near Yamuna bridge."),
    _section("ETW",  "PFD", 17.0,  LineType.DOUBLE, 110, 70, 0.0,  3, 300),
    _section("PFD",  "SFI", 13.0,  LineType.DOUBLE, 110, 70, 0.0,  3, 300),
    _section("SFI",  "KNJ", 16.0,  LineType.DOUBLE, 100, 65, 0.3,  3, 300,
             "Slight adverse gradient for UP direction."),
    _section("KNJ",  "GSJ", 16.0,  LineType.DOUBLE, 100, 65, 0.0,  3, 300),
    _section("GSJ",  "ALJP",14.0,  LineType.DOUBLE, 100, 65, 0.0,  3, 300),
    _section("ALJP", "PNK", 16.0,  LineType.DOUBLE, 100, 65, 0.0,  3, 300),
    _section("PNK",  "RRL", 16.0,  LineType.DOUBLE, 100, 65, 0.2,  3, 300),
    _section("RRL",  "CNB", 67.0,  LineType.DOUBLE, 120, 75, 0.0, 10, 300,
             "Long section approaching CNB yard. Heavy goods traffic."),
]

# Flatten into individual TrackSection objects
SECTIONS: tuple[TrackSection, ...] = tuple(
    sec for pair in _RAW_SECTIONS for sec in pair
)

# Index: section_id → TrackSection
SECTION_INDEX: dict[str, TrackSection] = {s.section_id: s for s in SECTIONS}

# Single-line sections (require crossing management)
SINGLE_LINE_SECTIONS: tuple[str, ...] = tuple(
    s.section_id for s in SECTIONS if s.is_single_line
)


def get_station(station_id: str) -> Station:
    """Retrieve a station by ID; raise KeyError with a helpful message."""
    if station_id not in STATION_INDEX:
        raise KeyError(
            f"Unknown station '{station_id}'. "
            f"Valid IDs: {sorted(STATION_INDEX.keys())}"
        )
    return STATION_INDEX[station_id]


def get_section(section_id: str) -> TrackSection:
    """Retrieve a section by ID; raise KeyError with a helpful message."""
    if section_id not in SECTION_INDEX:
        raise KeyError(
            f"Unknown section '{section_id}'. "
            f"Valid IDs: {sorted(SECTION_INDEX.keys())}"
        )
    return SECTION_INDEX[section_id]
