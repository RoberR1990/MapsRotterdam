"""Vrije-doorstroommatrix (geen congestie) via self-hosted OSRM.

Snapt de kandidaat-punten per zone op het wegennet, houdt er per zone maximaal
K over, vraagt één /table op en aggregeert de punt-matrix naar een zone-matrix.
"""
import csv
import json
import statistics
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
# welke zone-set: "zones" (buurten) of "parkzones" (RDW-parkeergebieden)
STEM = sys.argv[1] if len(sys.argv) > 1 else "zones"
OSRM = "http://127.0.0.1:5000"
MAX_SNAP_M = 250   # verder dan dit betekent: punt lag in water/haven/park
K_PER_ZONE = 3


def snap(points):
    """Snap punten op het wegennet; geeft (zone_id, lon, lat, snap_m) terug."""
    kept = []
    for p in points:
        r = requests.get(f"{OSRM}/nearest/v1/driving/{p['lon']},{p['lat']}",
                         params={"number": 1}, timeout=30).json()
        if r.get("code") != "Ok" or not r.get("waypoints"):
            continue
        w = r["waypoints"][0]
        if w["distance"] <= MAX_SNAP_M:
            kept.append({**p, "snap_lon": w["location"][0],
                         "snap_lat": w["location"][1],
                         "snap_m": round(w["distance"], 1)})
    return kept


def table(coords):
    """OSRM /table voor een lijst (lon, lat); geeft duur- en afstandmatrix."""
    s = ";".join(f"{lon},{lat}" for lon, lat in coords)
    r = requests.get(f"{OSRM}/table/v1/driving/{s}",
                     params={"annotations": "duration,distance"}, timeout=600).json()
    if r.get("code") != "Ok":
        raise RuntimeError(r)
    return r["durations"], r["distances"]


def main():
    zones = json.loads((OUT / f"{STEM}.geojson").read_text())["features"]
    meta = {z["properties"]["zone_id"]: z["properties"] for z in zones}
    cands = json.loads((OUT / f"{STEM}_candidates.json").read_text())

    kept = snap(cands)
    by_zone = {}
    for p in kept:
        by_zone.setdefault(p["zone_id"], []).append(p)
    chosen, idx = [], {}
    for zid in meta:
        pts = sorted(by_zone.get(zid, []), key=lambda p: p["cand"])[:K_PER_ZONE]
        if not pts:
            print(f"  !! geen berijdbaar punt voor {zid} {meta[zid]['naam']}")
            continue
        idx[zid] = list(range(len(chosen), len(chosen) + len(pts)))
        chosen.extend(pts)

    zids = [z for z in meta if z in idx]
    print(f"{len(zids)} zones, {len(chosen)} gesnapte punten "
          f"(mediane snap-afstand {statistics.median(p['snap_m'] for p in chosen):.0f} m)")

    dur, dist = table([(p["snap_lon"], p["snap_lat"]) for p in chosen])

    rows = []
    for a in zids:
        for b in zids:
            if a == b:
                rows.append({"from_zone": a, "to_zone": b,
                             "from_naam": meta[a]["naam"], "to_naam": meta[b]["naam"],
                             "freeflow_s": meta[a]["intrazonal_s"], "meters": 0})
                continue
            ds = [dur[i][j] for i in idx[a] for j in idx[b] if dur[i][j] is not None]
            ms = [dist[i][j] for i in idx[a] for j in idx[b] if dist[i][j] is not None]
            if not ds:
                print(f"  !! onbereikbaar: {a}->{b}")
                continue
            rows.append({"from_zone": a, "to_zone": b,
                         "from_naam": meta[a]["naam"], "to_naam": meta[b]["naam"],
                         "freeflow_s": round(statistics.median(ds)),
                         "meters": round(statistics.median(ms))})

    with open(OUT / f"matrix_freeflow_{STEM}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    json.dump([{k: p[k] for k in ("zone_id", "cand", "snap_lon", "snap_lat", "snap_m")}
               for p in chosen], open(OUT / f"{STEM}_points.json", "w"))

    od = [r for r in rows if r["from_zone"] != r["to_zone"]]
    mins = sorted(r["freeflow_s"] / 60 for r in od)
    print(f"{len(rows)} cellen weggeschreven -> out/matrix_freeflow_{STEM}.csv")
    print(f"  reistijd min/mediaan/p90/max: {mins[0]:.1f} / "
          f"{mins[len(mins)//2]:.1f} / {mins[int(len(mins)*.9)]:.1f} / {mins[-1]:.1f} min")


if __name__ == "__main__":
    main()
