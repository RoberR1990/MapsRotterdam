"""Echte Rotterdamse parkeerzones uit het Nationaal Parkeer Register (RDW).

Gratis open data, geen sleutel. Drie datasets, gekoppeld op areaid:
  mz4f-59fw  PARKEERGEBIED     welk soort gebied (betaald, bezoek, garage, ...)
  nsk3-v9n7  GEOMETRIE GEBIED  polygoon in WGS84 als WKT
  b3us-f26s  SPECIFICATIES     capaciteit (alleen garages, andere areaid-reeks)

Levert hetzelfde formaat als src/zones.py, zodat de rest van de pijplijn
ongewijzigd blijft. Wil je een eigen zonelijst gebruiken, vervang dan alleen
dit script -- out/zones.geojson en out/zone_candidates.json zijn het contract.
"""
import json
import math
import re
import urllib.request
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import Polygon, MultiPolygon, mapping, Point
from shapely.ops import transform as shp_transform

ROOT = Path(__file__).resolve().parent.parent
RDW = ROOT / "data" / "rdw"
OUT = ROOT / "out"
GEMEENTE_ROTTERDAM = 599
USAGE = {"BETAALDP"}          # voeg "BEZOEKP" toe voor de bezoekersgebieden
MIN_AREA_M2 = 10_000    # 1 ha; daaronder is een "zone" een enkel straatblok en
                        # wordt bemonsteren met meerdere punten zinloos

_to_rd = Transformer.from_crs("EPSG:4326", "EPSG:28992", always_xy=True)


def fetch(rid, **q):
    q.setdefault("$limit", 5000)
    url = f"https://opendata.rdw.nl/resource/{rid}.json?" + "&".join(
        f"{k}={v}" for k, v in q.items())
    with urllib.request.urlopen(url, timeout=180) as r:
        return json.load(r)


def load(name, rid):
    """Cache de RDW-datasets lokaal; ze veranderen hooguit een paar keer per jaar."""
    p = RDW / f"{name}.json"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(fetch(rid, areamanagerid=GEMEENTE_ROTTERDAM)))
    return json.loads(p.read_text())


def parse_wkt(w):
    """POLYGON / MULTIPOLYGON uit WKT; alleen buitenringen (gaten komen niet voor)."""
    rings = [[tuple(map(float, pt.split()))
              for pt in ring.split(",")]
             for ring in re.findall(r"\(([-\d.\s,]+)\)", w)]
    polys = [Polygon(r).buffer(0) for r in rings if len(r) >= 4]
    polys = [p for p in polys if not p.is_empty]
    if not polys:
        return None
    return polys[0] if len(polys) == 1 else MultiPolygon(polys).buffer(0)


def candidate_points(poly_rd, n_grid=4):
    pts = [poly_rd.representative_point()]
    minx, miny, maxx, maxy = poly_rd.bounds
    for i in range(1, n_grid + 1):
        for j in range(1, n_grid + 1):
            p = Point(minx + (maxx - minx) * i / (n_grid + 1),
                      miny + (maxy - miny) * j / (n_grid + 1))
            if poly_rd.contains(p):
                pts.append(p)
    c = poly_rd.representative_point()
    pts.sort(key=lambda p: p.distance(c))
    return pts


def main():
    gebied = load("parkeergebied", "mz4f-59fw")
    geom = load("geometrie", "nsk3-v9n7")
    usage = {g["areaid"]: g["usageid"] for g in gebied}

    # per areaid de meest recente geometrie
    latest = {}
    for g in geom:
        if usage.get(g["areaid"]) not in USAGE:
            continue
        prev = latest.get(g["areaid"])
        if prev is None or g.get("startdatearea", "") > prev.get("startdatearea", ""):
            latest[g["areaid"]] = g

    # buurtnamen erbij, zodat de zones een herkenbaar label krijgen
    buurten = []
    for f in json.loads((OUT / "zones.geojson").read_text())["features"]:
        from shapely.geometry import shape
        buurten.append((shape(f["geometry"]), f["properties"]["naam"],
                        f["properties"]["gebied"]))

    zones, points, skipped = [], [], []
    for aid, g in sorted(latest.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0):
        poly = parse_wkt(g["areageometryastext"])
        if poly is None:
            skipped.append((aid, "onbruikbare geometrie"))
            continue
        poly_rd = shp_transform(lambda x, y, z=None: _to_rd.transform(x, y), poly)
        if poly_rd.area < MIN_AREA_M2:
            skipped.append((aid, f"te klein ({poly_rd.area/1e4:.1f} ha)"))
            continue
        if poly_rd.geom_type == "MultiPolygon":
            poly_rd = max(poly_rd.geoms, key=lambda p: p.area)
            poly = max(poly.geoms, key=lambda p: p.area)

        c = poly.representative_point()
        naam, gebiednaam = "Onbekend", "Onbekend"
        for b, n, gb in buurten:
            if b.contains(c):
                naam, gebiednaam = n, gb
                break

        zid = f"P{aid}"
        zones.append({
            "type": "Feature",
            "properties": {
                "zone_id": zid, "areaid": aid, "naam": f"{naam} ({aid})",
                "buurt": naam, "gebied": gebiednaam,
                "area_m2": round(poly_rd.area),
                "intrazonal_s": round(0.5 * math.sqrt(poly_rd.area) / (25 / 3.6)),
            },
            "geometry": mapping(poly),
        })
        for k, p in enumerate(candidate_points(poly_rd)[:8]):
            w = shp_transform(lambda x, y, z=None: _to_rd.transform(x, y, direction="INVERSE"), p)
            points.append({"zone_id": zid, "naam": zones[-1]["properties"]["naam"],
                           "cand": k, "lon": round(w.x, 6), "lat": round(w.y, 6)})

    (OUT / "parkzones.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": zones}))
    (OUT / "parkzones_candidates.json").write_text(json.dumps(points))
    print(f"{len(latest)} betaald-parkeergebieden met geometrie")
    print(f"{len(zones)} zones behouden, {len(skipped)} overgeslagen, "
          f"{len(points)} kandidaat-punten")
    from collections import Counter
    for gb, n in Counter(z["properties"]["gebied"] for z in zones).most_common(8):
        print(f"  {gb:<26} {n:>3}")


if __name__ == "__main__":
    main()
