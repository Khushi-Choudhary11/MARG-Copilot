"""
MARG Railway Operations Dataset Generator v4
=============================================
Schedule-relative delay model: sched_travel is the ground truth.
Disruptions add bounded absolute minutes on top — no speed/distance mismatch.

Target distribution (matches Indian Railways historical data):
  ~65% on-time  (≤5 min late)
  ~15% minor    (5-15 min)
  ~12% moderate (15-30 min)
  ~8%  severe   (>30 min)
  Mean: 5-12 min
"""

import argparse, csv, random
from pathlib import Path

# ── Corridor ──────────────────────────────────────────────────────────────────

STATIONS = [
    ("NDLS","New Delhi",0), ("TKJ","Tilak Bridge",5), ("SZM","Sahibabad",15),
    ("GZB","Ghaziabad",28), ("DDN","Dadri",47), ("KRJ","Khurja",90),
    ("SKR","Sikandra Rao",109), ("HRS","Hathras",118), ("ALJN","Aligarh",132),
    ("BSWA","Bharthana",148), ("MRA","Mathura",160), ("TDL","Tundla",184),
    ("FZD","Firozabad",197), ("SKB","Shikohabad",220), ("JSN","Jasrana",232),
    ("BRN","Barhan",244), ("ETW","Etawah",266), ("PFD","Phaphund",283),
    ("SFI","Saifai",296), ("KNJ","Kannauj",312), ("GSJ","Gursahaiganj",328),
    ("ALJP","Allahabad City",342), ("PNK","Panki",358), ("RRL","Rawatpur",374),
    ("CNB","Kanpur Central",441),
]
STN_IDX  = {s[0]: i for i, s in enumerate(STATIONS)}
STN_KM   = {s[0]: s[2] for s in STATIONS}
STN_NAME = {s[0]: s[1] for s in STATIONS}

SECTIONS_UP = []
for i in range(len(STATIONS)-1):
    a, b = STATIONS[i], STATIONS[i+1]
    dist = b[2]-a[2]
    SECTIONS_UP.append({
        "id": f"{a[0]}_{b[0]}_UP", "from": a[0], "to": b[0], "len_km": dist,
        "pax_spd": 130 if dist>20 else (110 if dist>8 else 100),
        "frt_spd": 75  if dist>20 else (70  if dist>8 else 65),
        "cap": 4 if dist>20 else (5 if dist>8 else 6),
        "single": i in {5,6,8,9,11,12,13,14,17,18,19,20,21,22},
    })

SECTIONS_DOWN = []
for i in range(len(STATIONS)-1, 0, -1):
    a, b = STATIONS[i], STATIONS[i-1]
    dist = a[2]-b[2]
    SECTIONS_DOWN.append({
        "id": f"{a[0]}_{b[0]}_DOWN", "from": a[0], "to": b[0], "len_km": dist,
        "pax_spd": 130 if dist>20 else (110 if dist>8 else 100),
        "frt_spd": 75  if dist>20 else (70  if dist>8 else 65),
        "cap": 4 if dist>20 else (5 if dist>8 else 6),
        "single": i in {6,7,9,10,12,13,14,15,18,19,20,21,22,23},
    })

ALL_SECTIONS = {s["id"]: s for s in SECTIONS_UP + SECTIONS_DOWN}

def hm(h, m=0): return h*60+m

TIMETABLE = [
    ("12301","Howrah Rajdhani","superfast",0,"UP",640,130,
     [("NDLS",0,hm(6,0)),("GZB",hm(6,20),hm(6,22)),("ALJN",hm(7,18),hm(7,20)),
      ("TDL",hm(8,12),hm(8,14)),("ETW",hm(9,5),hm(9,7)),("CNB",hm(10,15),0)]),
    ("12309","Rajendra Nagar Rajdhani","superfast",0,"UP",620,130,
     [("NDLS",0,hm(7,30)),("GZB",hm(7,50),hm(7,52)),("ALJN",hm(8,48),hm(8,50)),
      ("TDL",hm(9,42),hm(9,44)),("ETW",hm(10,35),hm(10,37)),("CNB",hm(11,45),0)]),
    ("12311","Kalka Mail","mail",1,"UP",580,110,
     [("NDLS",0,hm(6,45)),("SZM",hm(7,0),hm(7,2)),("GZB",hm(7,15),hm(7,18)),
      ("KRJ",hm(8,5),hm(8,8)),("ALJN",hm(8,55),hm(8,58)),("TDL",hm(9,50),hm(9,53)),
      ("FZD",hm(10,22),hm(10,25)),("ETW",hm(11,15),hm(11,18)),
      ("KNJ",hm(12,5),hm(12,7)),("CNB",hm(13,0),0)]),
    ("14015","Shramjeevi Express","express",2,"UP",560,100,
     [("NDLS",0,hm(8,15)),("GZB",hm(8,40),hm(8,43)),("HRS",hm(9,50),hm(9,53)),
      ("ALJN",hm(10,25),hm(10,28)),("TDL",hm(11,22),hm(11,25)),
      ("SKB",hm(12,20),hm(12,23)),("ETW",hm(13,10),hm(13,13)),
      ("KNJ",hm(14,5),hm(14,8)),("CNB",hm(15,0),0)]),
    ("14311","Ala Hazrat Express","express",2,"UP",540,100,
     [("NDLS",0,hm(9,0)),("GZB",hm(9,25),hm(9,28)),("DDN",hm(10,5),hm(10,8)),
      ("ALJN",hm(11,15),hm(11,18)),("TDL",hm(12,12),hm(12,15)),
      ("FZD",hm(12,50),hm(12,53)),("ETW",hm(13,42),hm(13,45)),("CNB",hm(15,30),0)]),
    ("12107","Lucknow Mail","mail",1,"UP",560,110,
     [("NDLS",0,hm(10,0)),("GZB",hm(10,22),hm(10,25)),("ALJN",hm(11,30),hm(11,33)),
      ("TDL",hm(12,25),hm(12,28)),("ETW",hm(13,22),hm(13,25)),
      ("KNJ",hm(14,20),hm(14,22)),("CNB",hm(15,15),0)]),
    ("70501","NDLS-CNB Goods","goods",4,"UP",720,75,
     [("NDLS",0,hm(11,30)),("GZB",hm(12,10),hm(12,20)),("ALJN",hm(13,50),hm(14,5)),
      ("TDL",hm(15,30),hm(15,45)),("FZD",hm(16,45),hm(17,0)),
      ("ETW",hm(18,30),hm(18,45)),("CNB",hm(21,0),0)]),
    ("70503","GZB-CNB Freight","goods",4,"UP",750,70,
     [("GZB",0,hm(13,0)),("DDN",hm(13,45),hm(14,0)),("KRJ",hm(15,0),hm(15,15)),
      ("ALJN",hm(16,20),hm(16,35)),("TDL",hm(18,0),hm(18,15)),
      ("SKB",hm(19,30),hm(19,45)),("ETW",hm(21,15),hm(21,30)),("CNB",hm(23,0),0)]),
    ("12302","Howrah Rajdhani Down","superfast",0,"DOWN",640,130,
     [("CNB",0,hm(7,0)),("ETW",hm(8,10),hm(8,12)),("TDL",hm(9,5),hm(9,7)),
      ("ALJN",hm(10,0),hm(10,2)),("GZB",hm(10,58),hm(11,0)),("NDLS",hm(11,20),0)]),
    ("12310","Rajendra Nagar Down","superfast",0,"DOWN",620,130,
     [("CNB",0,hm(8,30)),("ETW",hm(9,40),hm(9,42)),("TDL",hm(10,35),hm(10,37)),
      ("ALJN",hm(11,30),hm(11,32)),("GZB",hm(12,28),hm(12,30)),("NDLS",hm(12,50),0)]),
    ("12312","Kalka Mail Down","mail",1,"DOWN",580,110,
     [("CNB",0,hm(9,15)),("KNJ",hm(10,15),hm(10,17)),("ETW",hm(11,5),hm(11,8)),
      ("FZD",hm(11,58),hm(12,1)),("TDL",hm(12,30),hm(12,33)),
      ("ALJN",hm(13,28),hm(13,31)),("GZB",hm(14,28),hm(14,31)),("NDLS",hm(14,52),0)]),
    ("14016","Shramjeevi Down","express",2,"DOWN",560,100,
     [("CNB",0,hm(10,30)),("KNJ",hm(11,25),hm(11,28)),("ETW",hm(12,20),hm(12,23)),
      ("SKB",hm(13,15),hm(13,18)),("TDL",hm(14,10),hm(14,13)),
      ("ALJN",hm(15,5),hm(15,8)),("GZB",hm(16,5),hm(16,8)),("NDLS",hm(16,30),0)]),
    ("70502","CNB-NDLS Goods","goods",4,"DOWN",720,75,
     [("CNB",0,hm(6,0)),("ETW",hm(7,45),hm(8,0)),("FZD",hm(9,30),hm(9,45)),
      ("TDL",hm(10,45),hm(11,0)),("ALJN",hm(12,30),hm(12,45)),
      ("GZB",hm(14,30),hm(14,45)),("NDLS",hm(15,30),0)]),
    ("70504","CNB-GZB Freight","goods",4,"DOWN",750,70,
     [("CNB",0,hm(14,0)),("ETW",hm(15,45),hm(16,0)),("SKB",hm(17,30),hm(17,45)),
      ("TDL",hm(19,0),hm(19,15)),("ALJN",hm(20,45),hm(21,0)),
      ("GZB",hm(22,45),hm(23,0)),("NDLS",hm(23,55),0)]),
]

# ── Weather ────────────────────────────────────────────────────────────────────

MONTHLY_WEATHER = {
    1:(0.40,0.05,0.01),2:(0.30,0.08,0.01),3:(0.08,0.10,0.02),
    4:(0.02,0.08,0.05),5:(0.01,0.06,0.08),6:(0.01,0.35,0.15),
    7:(0.01,0.55,0.20),8:(0.01,0.50,0.18),9:(0.01,0.35,0.10),
    10:(0.05,0.12,0.03),11:(0.15,0.05,0.01),12:(0.35,0.04,0.01),
}
WEATHER_SPEED = {
    "CLEAR":1.00,"LIGHT_FOG":0.80,"MODERATE_FOG":0.55,
    "DENSE_FOG":0.15,"LIGHT_RAIN":0.90,"HEAVY_RAIN":0.70,"STORM":0.50,
}
# Extra minutes added per section hop for each weather condition
# Based on realistic IR operational data (per-section, NOT proportional to travel time)
WEATHER_EXTRA_MIN = {
    "CLEAR":       (0.0, 0.5),    # (mean, std) — tiny jitter only
    "LIGHT_FOG":   (0.5, 1.0),
    "MODERATE_FOG":(2.0, 2.0),
    "DENSE_FOG":   (7.0, 4.0),   # ~7 min per section average in dense fog
    "LIGHT_RAIN":  (0.3, 0.8),
    "HEAVY_RAIN":  (2.0, 1.5),
    "STORM":       (4.0, 2.5),
}

def sample_weather(month, hour, rng):
    fog_p, rain_p, storm_p = MONTHLY_WEATHER[month]
    if hour in (4,5,6,7,8):   fog_p = min(1.0, fog_p*1.8)
    elif hour in (9,10):       fog_p = min(1.0, fog_p*1.2)
    else:                       fog_p *= 0.3
    r = rng.random()
    if r < storm_p: return "STORM"
    r -= storm_p
    if r < rain_p*0.4: return "HEAVY_RAIN"
    r -= rain_p*0.4
    if r < rain_p*0.6: return "LIGHT_RAIN"
    r -= rain_p*0.6
    if r < fog_p*0.2: return "DENSE_FOG"
    r -= fog_p*0.2
    if r < fog_p*0.4: return "MODERATE_FOG"
    r -= fog_p*0.4
    if r < fog_p*0.4: return "LIGHT_FOG"
    return "CLEAR"

def month_to_season(m):
    return ("WINTER" if m in (12,1,2) else "SPRING" if m in (3,4,5)
            else "MONSOON" if m in (6,7,8,9) else "AUTUMN")

# ── Time-windowed disruptions ──────────────────────────────────────────────────

def sample_signal_failures(sections, rng):
    n = rng.choices([0,1,2,3], weights=[0.25,0.40,0.25,0.10])[0]
    result = []
    for sid in rng.sample(sections, min(n, len(sections))):
        start = rng.uniform(360, 1200)
        dur   = rng.uniform(20, 90)
        result.append((sid, start, start+dur))
    return result

def sample_blockages(sections, rng):
    if rng.random() > 0.30: return []
    n = rng.choices([1,2], weights=[0.85,0.15])[0]
    result = []
    for sid in rng.sample(sections, min(n, len(sections))):
        start = rng.uniform(360, 1080)
        dur   = rng.uniform(30, 120)
        result.append((sid, start, start+dur))
    return result

def is_active(disruptions, sec_id, t):
    return any(sid==sec_id and s<=t<=e for (sid,s,e) in disruptions)

# ── Stop expansion ────────────────────────────────────────────────────────────

def expand_stops(stops):
    hops = []
    for i in range(len(stops)-1):
        fa, _, dep = stops[i]
        tb, arr, _ = stops[i+1]
        ia, ib = STN_IDX[fa], STN_IDX[tb]
        if ia==ib: continue
        step = 1 if ib>ia else -1
        chain = list(range(ia, ib, step))
        total_dist = abs(STN_KM[tb]-STN_KM[fa])
        total_time = arr - dep
        elapsed = 0.0
        for ci in chain:
            a, b = STATIONS[ci][0], STATIONS[ci+step][0]
            frac = abs(STN_KM[b]-STN_KM[a]) / max(total_dist,1)
            seg  = total_time * frac
            hops.append((a, b, dep+elapsed, dep+elapsed+seg))
            elapsed += seg
    return hops

# ── Congestion ────────────────────────────────────────────────────────────────

def build_congestion_map(all_hops, rng):
    wc = {}
    for h in all_hops:
        sid = h["section_id"]; hr = int(h["sched_depart_min"]/60)%24
        wc.setdefault(sid,{}); wc[sid][hr] = wc[sid].get(hr,0)+1
    scores = {}
    for sid, windows in wc.items():
        cap = ALL_SECTIONS[sid]["cap"]
        score = min(1.0, max(windows.values())/max(cap,1)) + rng.gauss(0,0.03)
        scores[sid] = max(0.0, min(1.0, score))
    return scores

# ── Delay model ───────────────────────────────────────────────────────────────
#
# Per-section extra delay (minutes added on top of scheduled travel time):
#   weather_extra  ~ gauss(mean, std) from WEATHER_EXTRA_MIN  [bounded ≥0]
#   signal_wait    ~ uniform(15, 40) if signal failed           [one-time wait]
#   blockage_wait  ~ uniform(20, 90) if track blocked           [one-time wait]
#   congestion_add ~ uniform(0,3)*score if single-line          [headway creep]
#   cascade_delay  = min(upstream, 20) * cascade_factor
#
# cumulative_delay carries forward per train (capped by category).
# arrive_delay = cumulative + per-section extras – any schedule buffer.
# (Schedule buffer: many sections have extra slack built in; the "base" jitter
#  is centred at 0 so trains run on time in clear/undisrupted conditions.)

CAT_MAX_CUM = {"superfast":25, "mail":35, "express":45, "goods":75}

def section_delay_components(
    weather, signal_failed, track_blocked, cong_score,
    is_single, cat, rng
):
    """Returns (weather_extra, signal_wait, blk_wait, cong_add) in minutes."""
    mu, sigma = WEATHER_EXTRA_MIN[weather]
    # Goods trains more sensitive to weather
    scale = 1.3 if cat == "goods" else 1.0
    # Gaussian centred at mean; negative = train running early (valid)
    weather_extra = rng.gauss(mu * scale, sigma)

    signal_wait = rng.uniform(15, 40) if signal_failed else 0.0
    blk_wait    = rng.uniform(20, 90) if track_blocked  else 0.0

    cong_add = 0.0
    if is_single and cong_score > 0.4:
        # gauss centred near 0; positive = headway wait, negative = buffer
        cong_add = max(0.0, rng.gauss(0.5 * cong_score, 1.0))

    return weather_extra, signal_wait, blk_wait, cong_add

# ── CSV schema ────────────────────────────────────────────────────────────────

CSV_FIELDS = [
    "record_id","date","day_of_year","day_of_week","is_weekend","month","season",
    "train_id","train_name","category","priority","direction","length_m","max_speed_kmh",
    "from_station","from_station_name","to_station","to_station_name","section_id",
    "section_length_km","section_max_speed_kmh","section_capacity_per_hr",
    "section_is_single_line","from_station_chainage_km","to_station_chainage_km",
    "sched_depart_min","sched_arrive_min","sched_travel_min","hour_of_day",
    "weather_condition","weather_speed_factor","congestion_score",
    "signal_failed","track_blocked",
    "upstream_delay_min","cascade_factor",
    "actual_depart_min","actual_arrive_min","actual_travel_min","headway_wait_min",
    "depart_delay_min","arrive_delay_min","cumulative_delay_min","on_time","delay_bucket",
]

def delay_bucket(d):
    if d<=5: return 0
    if d<=15: return 1
    if d<=30: return 2
    return 3

# ── Main generator ────────────────────────────────────────────────────────────

def generate_dataset(target, seed=42, start_date="2023-01-01"):
    import datetime
    rng = random.Random(seed)
    records, record_id = [], 0
    y,mo,d = map(int,start_date.split("-"))
    cur = datetime.date(y,mo,d)

    up_ids   = [s["id"] for s in SECTIONS_UP]
    down_ids = [s["id"] for s in SECTIONS_DOWN]
    upstream: dict = {}   # {sec_id: delay_min} — section-level, reset daily

    while len(records) < target:
        ds = cur.isoformat()
        doy = cur.timetuple().tm_yday
        dow = cur.weekday()
        isw = int(dow>=5)
        mon = cur.month
        sea = month_to_season(mon)

        sig_up   = sample_signal_failures(up_ids,   rng)
        sig_down = sample_signal_failures(down_ids, rng)
        blk_up   = sample_blockages(up_ids,   rng)
        blk_down = sample_blockages(down_ids, rng)

        # Congestion map
        all_day = []
        for (_,_,cat,_,dirn,_,_,stops) in TIMETABLE:
            sfx = "UP" if dirn=="UP" else "DOWN"
            for (fa,tb,sd,sa) in expand_stops(stops):
                sid = f"{fa}_{tb}_{sfx}"
                if sid in ALL_SECTIONS:
                    all_day.append({"section_id":sid,"sched_depart_min":sd})
        cong_map = build_congestion_map(all_day, rng)

        upstream = {}

        for (tid,tname,cat,pri,dirn,length_m,max_spd,stops) in TIMETABLE:
            sfx    = "UP" if dirn=="UP" else "DOWN"
            sigs   = sig_up   if dirn=="UP" else sig_down
            blks   = blk_up   if dirn=="UP" else blk_down
            max_cum = CAT_MAX_CUM.get(cat, 45)
            cumul  = 0.0

            for (fa, tb, sched_dep, sched_arr) in expand_stops(stops):
                sec_id = f"{fa}_{tb}_{sfx}"
                if sec_id not in ALL_SECTIONS: continue
                sec = ALL_SECTIONS[sec_id]
                sched_travel = sched_arr - sched_dep

                # Actual passage time (with cumulative delay so far)
                passage_t = sched_dep + cumul
                hour = int((sched_dep % 1440) / 60)
                weather = sample_weather(mon, hour, rng)

                sig_active = is_active(sigs, sec_id, passage_t)
                blk_active = is_active(blks, sec_id, passage_t)
                cong_score = cong_map.get(sec_id, 0.0)

                # Upstream cascade
                upstream_d  = min(upstream.get(sec_id, 0.0), 20.0)
                base_cas    = 0.18 if sec["single"] else 0.09
                cascade_f   = max(0.0, base_cas * (1.0 - pri * 0.04))
                cascade_d   = upstream_d * cascade_f

                # Per-section delay components
                wex, sig_wait, blk_wait, cong_add = section_delay_components(
                    weather, sig_active, blk_active, cong_score,
                    sec["single"], cat, rng
                )
                hw_wait = cong_add  # headway_wait_min field

                # Total section extra delay
                section_extra = wex + sig_wait + blk_wait + cong_add + cascade_d

                # Actual times — use PRE-UPDATE cumul for actual_dep so we
                # don't double-count this section's delay in arrive_delay.
                old_cumul = cumul
                hop_delay = max(0.0, section_extra)
                cumul     = min(cumul + hop_delay, max_cum)

                actual_dep = sched_dep + old_cumul          # departs with PREVIOUS delay
                actual_travel = sched_travel + wex + (sig_wait * 0.3 if sig_active else 0)
                actual_arr = actual_dep + actual_travel + blk_wait + cong_add + cascade_d

                depart_delay = actual_dep - sched_dep       # = old_cumul
                arrive_delay = actual_arr - sched_arr       # ≈ cumul (new)

                # Upstream: store only weather+signal component (not cumulative)
                upstream[sec_id] = min(wex + (sig_wait*0.2 if sig_active else 0), 20.0)

                record_id += 1
                records.append({
                    "record_id": record_id, "date": ds,
                    "day_of_year": doy, "day_of_week": dow,
                    "is_weekend": isw, "month": mon, "season": sea,
                    "train_id": tid, "train_name": tname,
                    "category": cat, "priority": pri, "direction": dirn,
                    "length_m": length_m, "max_speed_kmh": max_spd,
                    "from_station": fa, "from_station_name": STN_NAME[fa],
                    "to_station": tb, "to_station_name": STN_NAME[tb],
                    "section_id": sec_id,
                    "section_length_km": sec["len_km"],
                    "section_max_speed_kmh": sec["pax_spd"] if cat!="goods" else sec["frt_spd"],
                    "section_capacity_per_hr": sec["cap"],
                    "section_is_single_line": int(sec["single"]),
                    "from_station_chainage_km": STN_KM[fa],
                    "to_station_chainage_km": STN_KM[tb],
                    "sched_depart_min": round(sched_dep,2),
                    "sched_arrive_min": round(sched_arr,2),
                    "sched_travel_min": round(sched_travel,2),
                    "hour_of_day": hour,
                    "weather_condition": weather,
                    "weather_speed_factor": WEATHER_SPEED[weather],
                    "congestion_score": round(cong_score,4),
                    "signal_failed": int(sig_active),
                    "track_blocked": int(blk_active),
                    "upstream_delay_min": round(upstream_d,2),
                    "cascade_factor": round(cascade_f,3),
                    "actual_depart_min": round(actual_dep,2),
                    "actual_arrive_min": round(actual_arr,2),
                    "actual_travel_min": round(actual_travel,2),
                    "headway_wait_min": round(hw_wait,2),
                    "depart_delay_min": round(depart_delay,2),
                    "arrive_delay_min": round(arrive_delay,2),
                    "cumulative_delay_min": round(cumul,2),
                    "on_time": int(arrive_delay<=5.0),
                    "delay_bucket": delay_bucket(arrive_delay),
                })

        cur += __import__("datetime").timedelta(days=1)

    return records[:target]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", type=int, default=120_000)
    ap.add_argument("--seed",    type=int, default=42)
    ap.add_argument("--out",     type=str, default="railway_ops.csv")
    ap.add_argument("--start",   type=str, default="2023-01-01")
    a = ap.parse_args()

    print(f"Generating {a.records:,} records (seed={a.seed}) …", flush=True)
    recs = generate_dataset(a.records, a.seed, a.start)

    out = Path(a.out)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader(); w.writerows(recs)

    print(f"Written {len(recs):,} → {out} ({out.stat().st_size/1e6:.1f} MB)")

    delays = [r["arrive_delay_min"] for r in recs]
    sd = sorted(delays)
    n  = len(delays)
    print(f"\nDelay summary:")
    print(f"  Mean   : {sum(delays)/n:.2f} min")
    print(f"  Median : {sd[n//2]:.2f} min")
    print(f"  P90    : {sd[int(n*0.9)]:.2f} min")
    print(f"  Max    : {max(delays):.1f} min")
    print(f"  On-time: {100*sum(1 for d in delays if d<=5)/n:.1f}%")

    bk = [0,0,0,0]
    for r in recs: bk[r["delay_bucket"]] += 1
    for lbl,c in zip(["on-time(≤5)","minor(5-15)","moderate(15-30)","severe(>30)"],bk):
        print(f"  {lbl:20s}: {c:7,}  ({100*c/n:.1f}%)")

    cats = {}
    for r in recs: cats.setdefault(r["category"],[]).append(r["arrive_delay_min"])
    print(f"\nMean delay by category:")
    for cat,ds in sorted(cats.items()): print(f"  {cat:12s}: {sum(ds)/len(ds):.2f} min")

    print(f"\nMean delay by weather (expect: CLEAR < FOG < RAIN < STORM):")
    for w in ["CLEAR","LIGHT_FOG","MODERATE_FOG","DENSE_FOG","LIGHT_RAIN","HEAVY_RAIN","STORM"]:
        ws = [r["arrive_delay_min"] for r in recs if r["weather_condition"]==w]
        if ws: print(f"  {w:14s}: {sum(ws)/len(ws):.2f} min  (n={len(ws):,})")

    sigs = [r for r in recs if r["signal_failed"]]
    blks = [r for r in recs if r["track_blocked"]]
    print(f"\nDisruptions:")
    print(f"  Signal failures: {len(sigs):,}  mean={sum(r['arrive_delay_min'] for r in sigs)/max(len(sigs),1):.1f}min")
    print(f"  Track blockages: {len(blks):,}  mean={sum(r['arrive_delay_min'] for r in blks)/max(len(blks),1):.1f}min")
    print(f"\nSchema: {len(CSV_FIELDS)} columns")

if __name__ == "__main__":
    main()
