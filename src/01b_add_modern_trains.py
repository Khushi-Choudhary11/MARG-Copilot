"""
The 2017 timetable dump predates Vande Bharat and several newer trains.
This script appends a small, manually curated set of well-known modern
trains that run on the NDLS-CNB corridor, so train_master.csv /
train_routes.csv aren't entirely frozen at 2017.

Source: manually curated from publicly known IR timetables (domain knowledge).
Times are approximate scheduled times for the corridor stations only.
"""
import pandas as pd
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"

MASTER_ADDITIONS = [
    {
        "train_number": "22417", "train_name": "NDLS VNS VB", "train_type": "Vande Bharat",
        "train_category_priority": 1, "source_station_code": "NDLS", "source_station_name": "NEW DELHI",
        "destination_station_code": "BSB", "destination_station_name": "VARANASI JN.",
        "corridor_direction": "DOWN (NDLS->CNB)", "total_distance_km": 759, "num_stops": 4,
        "operating_days": "DAILY EXCEPT TUE",
    },
    {
        "train_number": "22418", "train_name": "VNS NDLS VB", "train_type": "Vande Bharat",
        "train_category_priority": 1, "source_station_code": "BSB", "source_station_name": "VARANASI JN.",
        "destination_station_code": "NDLS", "destination_station_name": "NEW DELHI",
        "corridor_direction": "UP (CNB->NDLS)", "total_distance_km": 759, "num_stops": 4,
        "operating_days": "DAILY EXCEPT TUE",
    },
    {
        "train_number": "22439", "train_name": "LKO NDLS VB", "train_type": "Vande Bharat",
        "train_category_priority": 1, "source_station_code": "LKO", "source_station_name": "LUCKNOW NR",
        "destination_station_code": "NDLS", "destination_station_name": "NEW DELHI",
        "corridor_direction": "UP (CNB->NDLS)", "total_distance_km": 511, "num_stops": 3,
        "operating_days": "DAILY EXCEPT SUN",
    },
    {
        "train_number": "22440", "train_name": "NDLS LKO VB", "train_type": "Vande Bharat",
        "train_category_priority": 1, "source_station_code": "NDLS", "source_station_name": "NEW DELHI",
        "destination_station_code": "LKO", "destination_station_name": "LUCKNOW NR",
        "corridor_direction": "DOWN (NDLS->CNB)", "total_distance_km": 511, "num_stops": 3,
        "operating_days": "DAILY EXCEPT SUN",
    },
]

# Corridor-only route legs (approximate scheduled times, HH:MM:SS)
ROUTE_ADDITIONS = {
    "22417": [  # NDLS -> VNS, via corridor
        ("NDLS", "NEW DELHI", 1, 0, "00:00:00", "06:00:00", "DOWN (NDLS->CNB)"),
        ("GZB", "GHAZIABAD JN.", 2, 20, "06:21:00", "06:23:00", "DOWN (NDLS->CNB)"),
        ("CNB", "KANPUR CENTRAL JN.", 3, 440, "10:13:00", "10:18:00", "DOWN (NDLS->CNB)"),
    ],
    "22418": [  # VNS -> NDLS
        ("CNB", "KANPUR CENTRAL JN.", 1, 320, "16:35:00", "16:40:00", "UP (CNB->NDLS)"),
        ("GZB", "GHAZIABAD JN.", 2, 740, "20:30:00", "20:32:00", "UP (CNB->NDLS)"),
        ("NDLS", "NEW DELHI", 3, 759, "21:00:00", "00:00:00", "UP (CNB->NDLS)"),
    ],
    "22439": [  # LKO -> NDLS, via CNB, ETW, TDL, ALJN, GZB
        ("CNB", "KANPUR CENTRAL JN.", 1, 80, "07:15:00", "07:20:00", "UP (CNB->NDLS)"),
        ("ETW", "ETAWAH JN.", 2, 160, "08:08:00", "08:10:00", "UP (CNB->NDLS)"),
        ("TDL", "TUNDLA JN.", 3, 260, "09:00:00", "09:02:00", "UP (CNB->NDLS)"),
        ("ALJN", "ALIGARH JN.", 4, 340, "09:45:00", "09:47:00", "UP (CNB->NDLS)"),
        ("GZB", "GHAZIABAD JN.", 5, 470, "11:05:00", "11:07:00", "UP (CNB->NDLS)"),
        ("NDLS", "NEW DELHI", 6, 511, "11:42:00", "00:00:00", "UP (CNB->NDLS)"),
    ],
    "22440": [  # NDLS -> LKO
        ("NDLS", "NEW DELHI", 1, 0, "00:00:00", "15:00:00", "DOWN (NDLS->CNB)"),
        ("GZB", "GHAZIABAD JN.", 2, 41, "15:21:00", "15:23:00", "DOWN (NDLS->CNB)"),
        ("ALJN", "ALIGARH JN.", 3, 171, "16:18:00", "16:20:00", "DOWN (NDLS->CNB)"),
        ("TDL", "TUNDLA JN.", 4, 251, "17:00:00", "17:02:00", "DOWN (NDLS->CNB)"),
        ("ETW", "ETAWAH JN.", 5, 351, "17:50:00", "17:52:00", "DOWN (NDLS->CNB)"),
        ("CNB", "KANPUR CENTRAL JN.", 6, 431, "18:45:00", "18:50:00", "DOWN (NDLS->CNB)"),
    ],
}


def main():
    master_path = OUT_DIR / "train_master.csv"
    routes_path = OUT_DIR / "train_routes.csv"

    master = pd.read_csv(master_path, dtype={"train_number": str})
    routes = pd.read_csv(routes_path, dtype={"train_number": str})

    existing = set(master["train_number"])
    new_master_rows = [r for r in MASTER_ADDITIONS if r["train_number"] not in existing]

    if new_master_rows:
        master = pd.concat([master, pd.DataFrame(new_master_rows)], ignore_index=True)
        master.to_csv(master_path, index=False)
        print(f"Added {len(new_master_rows)} modern trains to train_master.csv")
    else:
        print("Modern trains already present in train_master.csv")

    new_route_rows = []
    for tn, legs in ROUTE_ADDITIONS.items():
        if tn in set(routes["train_number"]) :
            continue
        if tn not in {r["train_number"] for r in new_master_rows} and tn not in existing:
            continue
        for code, name, seq, dist, arr, dep, direction in legs:
            ah, am, _ = arr.split(":")
            dh, dm, _ = dep.split(":")
            halt = (int(dh) * 60 + int(dm)) - (int(ah) * 60 + int(am))
            if halt < 0:
                halt += 24 * 60
            if arr == "00:00:00" or dep == "00:00:00":
                halt = 0
            new_route_rows.append({
                "train_number": tn, "station_code": code, "station_name": name,
                "station_sequence": seq, "distance_km": dist,
                "scheduled_arrival": arr, "scheduled_departure": dep,
                "halt_minutes": halt, "corridor_direction": direction,
            })

    if new_route_rows:
        routes = pd.concat([routes, pd.DataFrame(new_route_rows)], ignore_index=True)
        routes.to_csv(routes_path, index=False)
        print(f"Added {len(new_route_rows)} route rows for modern trains to train_routes.csv")
    else:
        print("Modern train routes already present in train_routes.csv")


if __name__ == "__main__":
    main()
