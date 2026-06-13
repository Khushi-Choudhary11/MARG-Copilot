"""
Step 5: Build station_infrastructure.csv and section_infrastructure.csv
for the NDLS-CNB corridor.

NOTE: No public API/dataset exposes platform counts, loop-line counts or
section line-counts at this granularity. These values are curated from
publicly available Indian Railways station information / track diagrams
and are best-effort estimates. They are flagged as "curated_estimate" in
the data_quality_report and should be verified against zonal railway
track-charts before production use.
"""
import pandas as pd
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"

# platforms/main_tracks sourced from Wikipedia station infoboxes (2026-06-13);
# loop_lines/junction_flag/station_category remain curated estimates where
# Wikipedia does not state them explicitly.
STATION_INFRA = [
    {"station_code": "NDLS", "station_name": "New Delhi", "platforms": 16, "main_tracks": 20,
     "loop_lines": 8, "junction_flag": 1, "station_category": "A1", "source": "wikipedia+curated"},
    {"station_code": "GZB", "station_name": "Ghaziabad Jn", "platforms": 6, "main_tracks": 13,
     "loop_lines": 6, "junction_flag": 1, "station_category": "A1", "source": "wikipedia+curated"},
    {"station_code": "ALJN", "station_name": "Aligarh Jn", "platforms": 7, "main_tracks": 4,
     "loop_lines": 4, "junction_flag": 1, "station_category": "NSG3", "source": "wikipedia+curated"},
    {"station_code": "TDL", "station_name": "Tundla Jn", "platforms": 7, "main_tracks": 4,
     "loop_lines": 4, "junction_flag": 1, "station_category": "A", "source": "wikipedia+curated"},
    {"station_code": "ETW", "station_name": "Etawah Jn", "platforms": 5, "main_tracks": 2,
     "loop_lines": 3, "junction_flag": 1, "station_category": "B", "source": "wikipedia+curated"},
    {"station_code": "CNB", "station_name": "Kanpur Central", "platforms": 10, "main_tracks": 28,
     "loop_lines": 6, "junction_flag": 1, "station_category": "A1", "source": "wikipedia+curated"},
]

SECTION_INFRA = [
    {"from_station": "NDLS", "to_station": "GZB", "num_tracks": 4, "line_type": "Multi (Quadruple)",
     "section_length_km": 25, "source": "curated_estimate"},
    {"from_station": "GZB", "to_station": "ALJN", "num_tracks": 3, "line_type": "Multi (Triple, partially quad near GZB)",
     "section_length_km": 124, "source": "curated_estimate"},
    {"from_station": "ALJN", "to_station": "TDL", "num_tracks": 2, "line_type": "Double",
     "section_length_km": 81, "source": "curated_estimate"},
    {"from_station": "TDL", "to_station": "ETW", "num_tracks": 2, "line_type": "Double",
     "section_length_km": 100, "source": "curated_estimate"},
    {"from_station": "ETW", "to_station": "CNB", "num_tracks": 2, "line_type": "Double",
     "section_length_km": 80, "source": "curated_estimate"},
]


def main():
    pd.DataFrame(STATION_INFRA).to_csv(OUT_DIR / "station_infrastructure.csv", index=False)
    pd.DataFrame(SECTION_INFRA).to_csv(OUT_DIR / "section_infrastructure.csv", index=False)
    print(f"Wrote {len(STATION_INFRA)} rows to station_infrastructure.csv")
    print(f"Wrote {len(SECTION_INFRA)} rows to section_infrastructure.csv")


if __name__ == "__main__":
    main()
