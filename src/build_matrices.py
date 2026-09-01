"""Vraag per tijdvak de zone-matrix op bij de bijbehorende OSRM-router."""
import csv
import json
import statistics
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from timeslots import SLOTS, PORTS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"


def table(port, coords):
    s = ";".join(f"{lon},{lat}" for lon, lat in coords)
    r = requests.get(f"http://127.0.0.1:{port}/table/v1/driving/{s}",
                     params={"annotations": "duration,distance"}, timeout=600).json()
    if r.get("code") != "Ok":
        raise RuntimeError(f"poort {port}: {r}")
    return r["durations"], r["distances"]


def main():
    meta = {z["properties"]["zone_id"]: z["properties"]
            for z in json.loads((OUT / "zones.geojson").read_text())["features"]}
    pts = json.loads((OUT / "zone_points.json").read_text())
    coords = [(p["snap_lon"], p["snap_lat"]) for p in pts]
    idx = {}
    for i, p in enumerate(pts):
        idx.setdefault(p["zone_id"], []).append(i)
    zids = [z for z in meta if z in idx]

    runs = {"freeflow": 5000, **PORTS}
    matrices = {}
    for name, port in runs.items():
        dur, dist = table(port, coords)
        m = {}
        for a in zids:
            for b in zids:
                if a == b:
                    m[(a, b)] = (meta[a]["intrazonal_s"], 0)
                    continue
                ds = [dur[i][j] for i in idx[a] for j in idx[b] if dur[i][j] is not None]
                ms = [dist[i][j] for i in idx[a] for j in idx[b] if dist[i][j] is not None]
                m[(a, b)] = (round(statistics.median(ds)), round(statistics.median(ms))) if ds else (None, None)
        matrices[name] = m
        od = [v[0] / 60 for k, v in m.items() if k[0] != k[1] and v[0]]
        print(f"{name:<24} mediaan {statistics.median(od):5.1f} min   "
              f"p90 {sorted(od)[int(len(od)*.9)]:5.1f} min")

    names = list(runs)
    with open(OUT / "matrix_all.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["from_zone", "from_naam", "to_zone", "to_naam", "meters"]
                   + [f"{n}_s" for n in names])
        for a in zids:
            for b in zids:
                row = [a, meta[a]["naam"], b, meta[b]["naam"],
                       matrices["freeflow"][(a, b)][1]]
                w.writerow(row + [matrices[n][(a, b)][0] for n in names])
    print(f"\n{len(zids)**2} cellen x {len(names)} tijdvakken -> out/matrix_all.csv")

    # Waar doet het tijdvak er het meest toe?
    ff, pk = matrices["freeflow"], matrices["werkdag_avondspits"]
    ratios = sorted(((pk[k][0] / ff[k][0], k) for k in ff
                     if k[0] != k[1] and ff[k][0] and ff[k][0] > 300),
                    reverse=True)
    print("\nSterkste spitseffect (avondspits / vrije doorstroom):")
    for r, (a, b) in ratios[:6]:
        print(f"  {meta[a]['naam'][:22]:<22} -> {meta[b]['naam'][:22]:<22} "
              f"{ff[(a,b)][0]/60:4.1f} -> {pk[(a,b)][0]/60:4.1f} min  (x{r:.2f})")
    print(f"\nSpreiding van de spitsratio over alle paren: "
          f"x{ratios[-1][0]:.2f} tot x{ratios[0][0]:.2f} "
          f"(mediaan x{ratios[len(ratios)//2][0]:.2f})")


if __name__ == "__main__":
    main()
