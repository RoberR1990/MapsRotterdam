"""Hoe representatief zijn de NDW-meetpunten voor onze zone-naar-zone ritten?

Aantal meetpunten zegt weinig: ze liggen vooral langs snelwegen, terwijl onze
ritten grotendeels over stadsstraten gaan. Deze analyse meet daarom niet hoeveel
punten er zijn maar **welk deel van de werkelijk gereden route** een meetpunt
in de buurt heeft. Dat is het getal dat telt voor de kalibratie.
"""
import csv
import glob
import os
import gzip
import json
import math
import random
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import re  # noqa: E402
from sample_ndw import road_class  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
OSRM = "http://127.0.0.1:5000"
NABIJ_M = 150       # tot hoever telt een meetpunt als "dekt dit wegvak"
STAP_M = 50         # om de hoeveel meter we de route aftasten
N_PAREN = 400
CEL = 0.004         # rastercel ~280 m


def meters(lat1, lon1, lat2, lon2):
    kx = math.cos(math.radians((lat1 + lat2) / 2)) * 111_320
    return math.hypot((lon2 - lon1) * kx, (lat2 - lat1) * 110_540)


def live_sites(histdir):
    """Meetpunten die in onze eigen historie ooit iets meldden.

    Beide feeds tellen mee: de snelheidsfeed (inductielussen, vooral stedelijk)
    en de reistijdfeed (trajecten, inclusief de A16 en A20). Alleen de eerste
    nemen geeft een veel te somber beeld van de dekking.
    """
    live = set()
    mappen = [Path(histdir), Path(histdir).parent / "ndw_traveltime"]
    if os.environ.get("NDW_TT_DIR"):
        mappen.append(Path(os.environ["NDW_TT_DIR"]))
    for d in mappen:
        for p in sorted(glob.glob(str(d / "*.csv.gz"))):
            with gzip.open(p, "rt", newline="") as f:
                for r in csv.DictReader(f):
                    live.add(r["site_id"])
    return live


def route_stappen(a, b):
    """Route als losse stappen, elk met het wegnummer erbij.

    Zo weten we van elke gereden meter over wat voor weg hij loopt -- nodig om
    te zien of de meetpunten juist op de wegen liggen die wij gebruiken.
    """
    u = f"{OSRM}/route/v1/driving/{a[0]},{a[1]};{b[0]},{b[1]}"
    r = requests.get(u, params={"overview": "full", "geometries": "geojson",
                                "steps": "true"}, timeout=30).json()
    if r.get("code") != "Ok":
        return None
    uit = []
    for leg in r["routes"][0]["legs"]:
        for st in leg["steps"]:
            ref = (st.get("ref") or "")
            # S100-S123 zijn de Rotterdamse stadsroutes: de hoofdaders van de
            # stad, geen provinciale wegen. Ze dragen bijna de helft van onze
            # meters, dus ze verdienen een eigen klasse.
            if re.search(r"A\d{1,3}", ref):
                k = "snelweg"
            elif re.search(r"S\d{2,3}", ref):
                k = "stadsroute"
            elif re.search(r"N\d{1,3}", ref):
                k = "provinciale weg"
            else:
                k = "gewone straat"
            uit.append((k, st["geometry"]["coordinates"]))
    return uit


def main():
    histdir = sys.argv[1] if len(sys.argv) > 1 else str(OUT / "ndw_history")
    sites = json.loads((OUT / "ndw_sites.json").read_text())
    live = live_sites(histdir)

    for s in sites:
        s["klasse"] = road_class(s["id"])
        s["live"] = s["id"] in live

    grid = {}
    for s in sites:
        if s["live"]:
            grid.setdefault((round(s["lon"] / CEL), round(s["lat"] / CEL)), []).append(s)

    pts = json.loads((OUT / "parkzones_points.json").read_text())
    per_zone = {}
    for p in pts:
        per_zone.setdefault(p["zone_id"], p)
    zids = list(per_zone)
    random.seed(7)
    paren = [(a, b) for a in zids for b in zids if a != b]
    random.shuffle(paren)

    def gedekt_punt(lon, lat):
        gx, gy = round(lon / CEL), round(lat / CEL)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for s in grid.get((gx + dx, gy + dy), ()):
                    if meters(lat, lon, s["lat"], s["lon"]) <= NABIJ_M:
                        return True
        return False

    from collections import defaultdict
    gedekt = totaal = 0
    per_klasse = defaultdict(lambda: [0, 0])   # klasse -> [gedekt, totaal]
    per_paar = []
    for a, b in paren[:N_PAREN]:
        A, B = per_zone[a], per_zone[b]
        stps = route_stappen((A["snap_lon"], A["snap_lat"]),
                             (B["snap_lon"], B["snap_lat"]))
        if not stps:
            continue
        hit = stappen = 0
        for klasse, geo in stps:
            rest = 0.0
            for i in range(len(geo) - 1):
                (x0, y0), (x1, y1) = geo[i], geo[i + 1]
                d = meters(y0, x0, y1, x1)
                rest += d
                while rest >= STAP_M:
                    rest -= STAP_M
                    t = 1 - rest / max(d, 1e-9)
                    dicht = gedekt_punt(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
                    stappen += 1
                    hit += dicht
                    per_klasse[klasse][1] += 1
                    per_klasse[klasse][0] += dicht
        if stappen:
            totaal += stappen
            gedekt += hit
            per_paar.append(hit / stappen)

    per_paar.sort()
    q = lambda p: per_paar[int(len(per_paar) * p)] if per_paar else 0
    from collections import Counter
    tel = Counter((s["klasse"], s["live"]) for s in sites)

    data = {
        "sites": [{"lon": round(s["lon"], 5), "lat": round(s["lat"], 5),
                   "k": s["klasse"][0], "live": int(s["live"])} for s in sites],
        "n_totaal": len(sites), "n_live": sum(1 for s in sites if s["live"]),
        "per_klasse": {f"{k}_{'live' if l else 'stil'}": v for (k, l), v in tel.items()},
        "dekking": {
            "paren": len(per_paar), "nabij_m": NABIJ_M,
            "gemiddeld": round(gedekt / totaal, 3) if totaal else 0,
            "p10": round(q(.1), 3), "mediaan": round(q(.5), 3), "p90": round(q(.9), 3),
            "per_klasse": {k: {"dekking": round(v[0] / max(v[1], 1), 3),
                               "aandeel_route": round(v[1] / max(totaal, 1), 3)}
                           for k, v in per_klasse.items()},
        },
    }
    (OUT / "ndw_coverage.json").write_text(json.dumps(data, separators=(",", ":")))

    print(f"{len(sites)} meetpunten in de regio, {data['n_live']} melden ook echt snelheid")
    for k, v in sorted(tel.items()):
        print(f"   {k[0]:<9} {'meldend' if k[1] else 'stil':<8} {v:>5}")
    d = data["dekking"]
    print(f"\nroutedekking over {d['paren']} zoneparen (meetpunt binnen {NABIJ_M} m):")
    print(f"   gemiddeld {d['gemiddeld']*100:.0f}% van de gereden meters")
    print(f"   p10 {d['p10']*100:.0f}%   mediaan {d['mediaan']*100:.0f}%   p90 {d['p90']*100:.0f}%")
    print("\nper wegklasse van de route:")
    for k, v in sorted(d["per_klasse"].items(), key=lambda x: -x[1]["aandeel_route"]):
        print(f"   {k:<13} {v['aandeel_route']*100:5.1f}% van de meters, "
              f"daarvan {v['dekking']*100:5.1f}% met een meetpunt in de buurt")


if __name__ == "__main__":
    main()
