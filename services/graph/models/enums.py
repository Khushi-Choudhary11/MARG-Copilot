"""
Enumerations for the MARG Railway Graph Engine.

All domain-specific categorical values are defined here so they are
imported from a single canonical location across the codebase.
"""

from enum import Enum, IntEnum


class LineType(str, Enum):
    """
    Whether a track section has dedicated tracks for each direction
    or a single shared track.
    """
    SINGLE = "single"   # One track, trains must cross at loops
    DOUBLE = "double"   # Separate up/down tracks — no crossing needed


class Direction(str, Enum):
    """Canonical train travel direction on the NDLS–CNB corridor."""
    UP = "up"     # Towards Kanpur (increasing chainage)
    DOWN = "down" # Towards Delhi  (decreasing chainage)
    BOTH = "both" # Used for infrastructure that serves both directions


class StationClass(IntEnum):
    """
    Indian Railways station classification.
    A1 > A > B > C > D > E > F (descending infrastructure level).
    Drives minimum halt times, crew-change eligibility, platform counts.
    """
    A1 = 1  # Major terminals: NDLS, CNB
    A  = 2  # Divisional HQ or major junction: GZB, ALJN, TDL
    B  = 3  # Important intermediate: ETW, KRJ
    C  = 4  # Medium stations: FZD, SKB
    D  = 5  # Small stations
    E  = 6  # Halt stations
    F  = 7  # Flag stations


class TrainCategory(str, Enum):
    """
    Indian Railways train categories, ordered roughly by commercial importance.
    Drives priority weights in the objective function.
    """
    RAJDHANI        = "rajdhani"
    SHATABDI        = "shatabdi"
    VANDE_BHARAT    = "vande_bharat"
    DURONTO         = "duronto"
    SUPERFAST       = "superfast"
    EXPRESS         = "express"
    PASSENGER       = "passenger"
    MEMU            = "memu"
    GOODS_EXPRESS   = "goods_express"
    GOODS_ORDINARY  = "goods_ordinary"


class TrainPriority(IntEnum):
    """
    Numerical priority class (lower = higher priority).
    Used in precedence decisions and objective function weighting.
    """
    P0 = 0  # Rajdhani, Shatabdi, Vande Bharat
    P1 = 1  # Duronto
    P2 = 2  # Superfast, Express
    P3 = 3  # Passenger, MEMU
    P4 = 4  # Goods


class ElectrificationType(str, Enum):
    """Traction system on a track section."""
    AC_25KV  = "25kv_ac"    # Most main lines including NDLS–CNB
    DC_1500V = "1500v_dc"   # Some suburban sections
    DIESEL   = "diesel"     # Non-electrified sections
    DUAL     = "dual"       # Both electric and diesel capable


class LoopLineType(str, Enum):
    """Operational role of a loop/siding."""
    CROSSING   = "crossing"   # Used for train crossings on single line
    OVERTAKING = "overtaking" # Used for overtaking manoeuvres
    GOODS      = "goods"      # Dedicated goods yard / shunting
    STABLING   = "stabling"   # Coaching depot stabling


class SectionStatus(str, Enum):
    """Real-time operational status of a track section."""
    CLEAR       = "clear"
    OCCUPIED    = "occupied"
    BLOCKED     = "blocked"          # Full blockage — no trains
    RESTRICTED  = "restricted"       # Speed restriction active
    MAINTENANCE = "maintenance"      # Engineering block


class SignalAspect(str, Enum):
    """Colour-light signal aspects used on IR main lines."""
    RED           = "red"
    YELLOW        = "yellow"
    DOUBLE_YELLOW = "double_yellow"
    GREEN         = "green"
    FAILED        = "failed"
