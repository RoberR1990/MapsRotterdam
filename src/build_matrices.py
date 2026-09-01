"""Vraag per tijdvak de zone-matrix op bij de bijbehorende OSRM-router."""
import csv
import json
import statistics
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from timeslots import SLOTS, PORTS  # noqa: E402

LABELS = {"freeflow": "Vrije doorstroom (referentie)",
          **{k: v["label"] for k, v in SLOTS.items()}}

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
# welke zone-set: "zones" (buurten) of "parkzones" (RDW-parkeergebieden)
STEM = sys.argv[1] if len(sys.argv) > 1 else "zones"


def table(port, coords):
    s = ";".join(f"{lon},{lat}" for lon, lat in coords)
    r = requests.get(f"http://127.0.0.1:{port}/table/v1/driving/{s}",
                     params={"annotations": "duration,distance"}, timeout=600).json()
    if r.get("code") != "Ok":
        raise RuntimeError(f"poort {port}: {r}")
    return r["durations"], r["distances"]


def load_points(stem=None):
    """Zones, hun gesnapte punten en de index van zone -> puntindices."""
    stem = stem or STEM
    meta = {z["properties"]["zone_id"]: z["properties"]
            for z in json.loads((OUT / f"{stem}.geojson").read_text())["features"]}
    pts = json.loads((OUT / f"{stem}_points.json").read_text())
    coords = [(p["snap_lon"], p["snap_lat"]) for p in pts]
    idx = {}
    for i, p in enumerate(pts):
        idx.setdefault(p["zone_id"], []).append(i)
    return meta, coords, idx, [z for z in meta if z in idx]


def zone_matrix(port, meta, coords, idx, zids):
    """Puntmatrix van OSRM samenvatten naar (duur, meters) per zonepaar."""
    dur, dist = table(port, coords)
    m = {}
    for a in zids:
        for b in zids:
            if a == b:
                m[(a, b)] = (meta[a]["intrazonal_s"], 0)
                continue
            ds = [dur[i][j] for i in idx[a] for j in idx[b] if dur[i][j] is not None]
            ms = [dist[i][j] for i in idx[a] for j in idx[b] if dist[i][j] is not None]
            m[(a, b)] = ((round(statistics.median(ds)), round(statistics.median(ms)))
                         if ds else (None, None))
    return m


def main():
    meta, coords, idx, zids = load_points()

    runs = {"freeflow": 5000, **PORTS}
    matrices = {}
    for name, port in runs.items():
        m = zone_matrix(port, meta, coords, idx, zids)
        matrices[name] = m
        od = [v[0] / 60 for k, v in m.items() if k[0] != k[1] and v[0]]
        print(f"{name:<24} mediaan {statistics.median(od):5.1f} min   "
              f"p90 {sorted(od)[int(len(od)*.9)]:5.1f} min")

    names = list(runs)
    with open(OUT / f"matrix_all_{STEM}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["from_zone", "from_naam", "to_zone", "to_naam", "meters"]
                   + [f"{n}_s" for n in names])
        for a in zids:
            for b in zids:
                row = [a, meta[a]["naam"], b, meta[b]["naam"],
                       matrices["freeflow"][(a, b)][1]]
                w.writerow(row + [matrices[n][(a, b)][0] for n in names])
    print(f"\n{len(zids)**2} cellen x {len(names)} tijdvakken -> out/matrix_all_{STEM}.csv")

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

    write_web(zids, meta, matrices, names)


def write_web(zids, meta, matrices, names):
    """Compacte export voor de webweergave: zones gesorteerd op gebied, zodat de
    blokstructuur in een heatmap de geografie volgt."""
    order = sorted(zids, key=lambda z: (meta[z]["gebied"], meta[z]["naam"]))
    n = len(order)
    # vereenvoudigd tot ~3 m: op stadsniveau niet te zien, scheelt een factor vier
    from shapely.geometry import shape, mapping
    geo = {f["properties"]["zone_id"]:
           mapping(shape(f["geometry"]).simplify(0.00004, preserve_topology=True))
           for f in json.loads((OUT / f"{STEM}.geojson").read_text())["features"]}
    data = {
        "n": n,
        "zones": [{"id": z, "naam": meta[z]["naam"], "gebied": meta[z]["gebied"],
                   "km2": round(meta[z]["area_m2"] / 1e6, 2),
                   "geom": geo[z]} for z in order],
        "slots": [{"key": s, "label": LABELS[s]} for s in names],
        "m": {s: [matrices[s][(a, b)][0] for a in order for b in order] for s in names},
        "meters": [matrices["freeflow"][(a, b)][1] for a in order for b in order],
    }
    ctx = OUT / "zones.geojson"          # stadscontour als achtergrond op de kaart
    if ctx.exists():
        from shapely.ops import unary_union
        u = unary_union([shape(f["geometry"]).buffer(0)
                         for f in json.loads(ctx.read_text())["features"]])
        data["context"] = mapping(u.simplify(0.0004, preserve_topology=True))

    (OUT / f"matrix_web_{STEM}.json").write_text(json.dumps(data, separators=(",", ":")))
    print(f"webexport -> out/matrix_web_{STEM}.json "
          f"({(OUT / f'matrix_web_{STEM}.json').stat().st_size // 1024} kB)")


if __name__ == "__main__":
    main()
