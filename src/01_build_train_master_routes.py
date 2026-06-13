"""
Step 1-2: Identify trains crossing the NDLS-CNB corridor and build
train_master.csv and train_routes.csv.

Source data: itzmeanjan/indian-railway "Train_details_22122017.csv"
(Govt. of India Open Data Platform timetable dump), cached at
data/raw/routes/Train_details_22122017.csv.

Corridor: NDLS -> GZB -> ALJN -> TDL -> ETW -> CNB (and reverse).
A train "crosses the corridor" if both NDLS and CNB appear on its route,
in either direction.
"""
import pandas as pd
import re
from pathlib import Path

RAW = Path(__file__).resolve().parent.parent / "data" / "raw" / "routes" / "Train_details_22122017.csv"
OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CORRIDOR_CODES = ["NDLS", "GZB", "ALJN", "TDL", "ETW", "CNB"]

# Train type/category classification rules based on name keywords.
# priority follows the project's priority_mapping convention.
TYPE_RULES = [
    (r"RAJDHANI|RAJDHA|RAJD\b", "Rajdhani", 1),
    (r"VANDE\s*BHARAT|VB EXP", "Vande Bharat", 1),
    (r"SHATABDI|\bSHA\b|\bSHT\b", "Shatabdi", 1),
    (r"DURONTO|\bDUR\b", "Duronto", 2),
    (r"GARIB\s*RATH|\bGBR\b", "Garib Rath", 2),
    (r"\bAC\b", "AC Express", 2),
    (r"SUPERFAST|\bSUP\b|\bSF\b|\bSUF\b", "Superfast Express", 2),
    (r"PASSENGER|\bPASS\b", "Passenger", 4),
    (r"MEMU|DEMU", "EMU/DEMU", 4),
    (r"GOODS|FRT|FREIGHT", "Goods", 5),
]
DEFAULT_TYPE = ("Mail/Express", 3)


def classify(train_name: str):
    name = (train_name or "").upper()
    for pattern, ttype, prio in TYPE_RULES:
        if re.search(pattern, name):
            return ttype, prio
    return DEFAULT_TYPE


def main():
    df = pd.read_csv(RAW, low_memory=False, dtype={"Train No": str})
    df.columns = [c.strip() for c in df.columns]

    # Normalize types
    df["Train No"] = df["Train No"].astype(str).str.strip()
    df["SEQ"] = pd.to_numeric(df["SEQ"], errors="coerce")
    df["Station Code"] = df["Station Code"].astype(str).str.strip()
    df["Distance"] = pd.to_numeric(df["Distance"], errors="coerce")

    # Find trains where both NDLS and CNB appear on the route
    trains_with_ndls = set(df.loc[df["Station Code"] == "NDLS", "Train No"])
    trains_with_cnb = set(df.loc[df["Station Code"] == "CNB", "Train No"])
    corridor_trains = trains_with_ndls & trains_with_cnb

    print(f"Trains with NDLS: {len(trains_with_ndls)}")
    print(f"Trains with CNB: {len(trains_with_cnb)}")
    print(f"Trains with both (candidate corridor trains): {len(corridor_trains)}")

    route_df = df[df["Train No"].isin(corridor_trains)].copy()
    route_df = route_df.sort_values(["Train No", "SEQ"])

    # Validate direction: NDLS seq vs CNB seq must differ (sanity)
    keep_trains = []
    direction = {}
    for tn, g in route_df.groupby("Train No"):
        ndls_seq = g.loc[g["Station Code"] == "NDLS", "SEQ"]
        cnb_seq = g.loc[g["Station Code"] == "CNB", "SEQ"]
        if ndls_seq.empty or cnb_seq.empty:
            continue
        ndls_seq = ndls_seq.iloc[0]
        cnb_seq = cnb_seq.iloc[0]
        if ndls_seq == cnb_seq:
            continue
        keep_trains.append(tn)
        direction[tn] = "DOWN (NDLS->CNB)" if ndls_seq < cnb_seq else "UP (CNB->NDLS)"

    route_df = route_df[route_df["Train No"].isin(keep_trains)].copy()
    route_df["corridor_direction"] = route_df["Train No"].map(direction)

    print(f"Valid corridor trains (NDLS and CNB in consistent order): {len(keep_trains)}")

    # --- train_routes.csv ---
    routes_out = route_df.rename(columns={
        "Train No": "train_number",
        "SEQ": "station_sequence",
        "Station Code": "station_code",
        "Station Name": "station_name",
        "Arrival time": "scheduled_arrival",
        "Departure Time": "scheduled_departure",
        "Distance": "distance_km",
    })

    # Halt duration in minutes (handle overnight wrap / missing times)
    def halt_minutes(row):
        arr, dep = row["scheduled_arrival"], row["scheduled_departure"]
        if pd.isna(arr) or pd.isna(dep):
            return 0
        try:
            ah, am, _ = str(arr).split(":")
            dh, dm, _ = str(dep).split(":")
            a_min = int(ah) * 60 + int(am)
            d_min = int(dh) * 60 + int(dm)
            diff = d_min - a_min
            if diff < 0:
                diff += 24 * 60
            return diff
        except Exception:
            return 0

    routes_out["halt_minutes"] = routes_out.apply(halt_minutes, axis=1)

    routes_cols = [
        "train_number", "station_code", "station_name", "station_sequence",
        "distance_km", "scheduled_arrival", "scheduled_departure",
        "halt_minutes", "corridor_direction",
    ]
    routes_out[routes_cols].to_csv(OUT_DIR / "train_routes.csv", index=False)
    print(f"Wrote {len(routes_out)} rows to train_routes.csv")

    # --- train_master.csv ---
    master_rows = []
    for tn, g in route_df.groupby("Train No"):
        g = g.sort_values("SEQ")
        first = g.iloc[0]
        last = g.iloc[-1]
        train_name = first["Train Name"]
        ttype, prio = classify(train_name)
        master_rows.append({
            "train_number": tn,
            "train_name": train_name,
            "train_type": ttype,
            "train_category_priority": prio,
            "source_station_code": first["Source Station"],
            "source_station_name": first["Source Station Name"],
            "destination_station_code": first["Destination Station"],
            "destination_station_name": first["Destination Station Name"],
            "corridor_direction": direction[tn],
            "total_distance_km": last["Distance"],
            "num_stops": len(g),
            # Operating days are not present in this static timetable dump.
            # Marked UNKNOWN; to be enriched via NTES live collector.
            "operating_days": "UNKNOWN",
        })

    master_df = pd.DataFrame(master_rows).sort_values("train_number")
    master_df.to_csv(OUT_DIR / "train_master.csv", index=False)
    print(f"Wrote {len(master_df)} rows to train_master.csv")


if __name__ == "__main__":
    main()
