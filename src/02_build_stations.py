"""
Step 4: Build stations.csv (station master) for every station appearing
in train_routes.csv, using lat/lon + zone from datameet/railways
stations.json. Railway Division is not present in that source, so it is
filled via a curated lookup for corridor stations and left UNKNOWN
otherwise (flagged in the data quality report).
"""
import json
import pandas as pd
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
STATIONS_JSON = BASE / "data" / "raw" / "stations.json"
ROUTES_CSV = BASE / "data" / "processed" / "train_routes.csv"
OUT_CSV = BASE / "data" / "processed" / "stations.csv"

# Curated division mapping for the corridor + nearby major stations
# (Northern Railway / North Central Railway divisions).
DIVISION_LOOKUP = {
    "NDLS": "Delhi",
    "GZB": "Delhi",
    "ALJN": "Allahabad",   # Aligarh falls under NCR Allahabad division
    "TDL": "Allahabad",    # Tundla falls under NCR Allahabad division
    "ETW": "Allahabad",
    "CNB": "Allahabad",
    "ANVT": "Delhi",
    "DLI": "Delhi",
    "NZM": "Delhi",
}

# Railway zone lookup for corridor stations (datameet source has zone=null for these)
ZONE_LOOKUP = {
    "NDLS": "NR",
    "GZB": "NR",
    "ALJN": "NCR",
    "TDL": "NCR",
    "ETW": "NCR",
    "CNB": "NCR",
    "ANVT": "NR",
    "DLI": "NR",
    "NZM": "NR",
}


def main():
    with open(STATIONS_JSON, encoding="utf-8") as f:
        geo = json.load(f)

    station_geo = {}
    for feat in geo["features"]:
        props = feat.get("properties", {})
        code = props.get("code")
        if not code:
            continue
        geom = feat.get("geometry")
        lon, lat = (None, None)
        if geom and geom.get("type") == "Point":
            lon, lat = geom["coordinates"][0], geom["coordinates"][1]
        station_geo[code] = {
            "station_name": props.get("name"),
            "latitude": lat,
            "longitude": lon,
            "railway_zone": props.get("zone"),
            "state": props.get("state"),
        }

    routes = pd.read_csv(ROUTES_CSV, dtype={"train_number": str})
    needed_codes = sorted(routes["station_code"].dropna().unique())

    rows = []
    missing = []
    for code in needed_codes:
        info = station_geo.get(code)
        # fall back to station name from routes file
        fallback_name = routes.loc[routes["station_code"] == code, "station_name"].iloc[0]
        if info is None:
            missing.append(code)
            rows.append({
                "station_code": code,
                "station_name": fallback_name,
                "latitude": None,
                "longitude": None,
                "railway_division": DIVISION_LOOKUP.get(code, "UNKNOWN"),
                "railway_zone": "UNKNOWN",
            })
        else:
            zone = info["railway_zone"] or ZONE_LOOKUP.get(code, "UNKNOWN")
            rows.append({
                "station_code": code,
                "station_name": info["station_name"] or fallback_name,
                "latitude": info["latitude"],
                "longitude": info["longitude"],
                "railway_division": DIVISION_LOOKUP.get(code, "UNKNOWN"),
                "railway_zone": zone,
            })

    out = pd.DataFrame(rows)
    out.to_csv(OUT_CSV, index=False)
    print(f"Wrote {len(out)} stations to stations.csv")
    if missing:
        print(f"{len(missing)} station codes not found in stations.json: {missing}")
    print(f"Missing coordinates: {out['latitude'].isna().sum()}")


if __name__ == "__main__":
    main()
