"""
Step 4b: Enrich station_infrastructure.csv and section_infrastructure.csv with
additional real, well-documented properties of the NDLS-CNB corridor (part of
the Delhi-Howrah main line, Indian Railways' busiest trunk route):

  - electrified: the entire NDLS-GZB-ALJN-TDL-ETW-CNB stretch has been under
    25kV AC electric traction since the 1980s-90s (Howrah-Delhi electrification).
  - gauge: Broad Gauge (1676mm) throughout, as for all of this trunk route.
  - max_speed_kmh: sanctioned maximum speed per section (curated from CRS
    speed-raise notifications / Rajdhani-Shatabdi timetable speeds).
  - electrified / gauge added to station_infrastructure.csv for the same reason.

Overwrites station_infrastructure.csv and section_infrastructure.csv (derived
processed artifacts; not raw data).
"""
import pandas as pd
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PROC = BASE / "data" / "processed"

# Sanctioned max speed (km/h) per corridor section, curated from public
# CRS speed-raise notifications and Rajdhani/Shatabdi/Vande Bharat schedules.
SECTION_SPEED = {
    ("NDLS", "GZB"): 130,
    ("GZB", "ALJN"): 130,
    ("ALJN", "TDL"): 130,
    ("TDL", "ETW"): 120,
    ("ETW", "CNB"): 120,
}


def main():
    station_infra = pd.read_csv(PROC / "station_infrastructure.csv")
    section_infra = pd.read_csv(PROC / "section_infrastructure.csv")

    station_infra["electrified"] = 1
    station_infra["traction_type"] = "25kV AC (electrified)"
    station_infra["gauge"] = "Broad Gauge (1676mm)"
    station_infra["source"] = station_infra["source"] + "+enriched"

    section_infra["electrified"] = 1
    section_infra["traction_type"] = "25kV AC (electrified)"
    section_infra["gauge"] = "Broad Gauge (1676mm)"
    section_infra["max_speed_kmh"] = section_infra.apply(
        lambda r: SECTION_SPEED[(r["from_station"], r["to_station"])], axis=1
    )
    section_infra["source"] = section_infra["source"] + "+enriched"

    station_infra.to_csv(PROC / "station_infrastructure.csv", index=False)
    section_infra.to_csv(PROC / "section_infrastructure.csv", index=False)
    print(f"Enriched station_infrastructure.csv ({len(station_infra)} rows) "
          f"and section_infrastructure.csv ({len(section_infra)} rows) "
          f"with electrified/gauge/max_speed_kmh.")


if __name__ == "__main__":
    main()
