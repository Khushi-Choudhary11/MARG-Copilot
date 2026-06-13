"""
Step 9 (partial): priority_mapping.csv

Maps train_type (as produced by 01_build_train_master_routes.py) to a
numeric precedence priority used by the future precedence recommendation
engine. Lower number = higher priority (runs first / less likely to be held).
"""
import pandas as pd
from pathlib import Path

OUT_CSV = Path(__file__).resolve().parent.parent / "data" / "processed" / "priority_mapping.csv"

PRIORITY_MAP = [
    {"train_type": "Rajdhani", "priority": 1, "description": "Premium fully air-conditioned long-distance, highest precedence"},
    {"train_type": "Vande Bharat", "priority": 1, "description": "Premium semi-high-speed train, highest precedence"},
    {"train_type": "Shatabdi", "priority": 1, "description": "Premium day AC intercity, highest precedence"},
    {"train_type": "Duronto", "priority": 2, "description": "Non-stop long-distance superfast"},
    {"train_type": "Garib Rath", "priority": 2, "description": "Budget fully AC superfast"},
    {"train_type": "AC Express", "priority": 2, "description": "Fully air-conditioned express"},
    {"train_type": "Superfast Express", "priority": 2, "description": "Superfast mail/express (avg speed >= 55 km/h)"},
    {"train_type": "Mail/Express", "priority": 3, "description": "Standard mail/express trains"},
    {"train_type": "Passenger", "priority": 4, "description": "Slow passenger trains, all-stop"},
    {"train_type": "EMU/DEMU", "priority": 4, "description": "Suburban electric/diesel multiple units"},
    {"train_type": "Goods", "priority": 5, "description": "Freight trains, lowest precedence"},
]


def main():
    df = pd.DataFrame(PRIORITY_MAP)
    df.to_csv(OUT_CSV, index=False)
    print(f"Wrote {len(df)} rows to priority_mapping.csv")


if __name__ == "__main__":
    main()
