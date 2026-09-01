"""Bouw prototype-zones uit Subbuurten_vlakken.json.

Dissolveert subbuurten naar buurten (BUURTNAAM), filtert haven-/industriegebied
weg, herprojecteert RD New (EPSG:28992) -> WGS84 en genereert per zone een set
kandidaat-punten die later op het wegennet gesnapt worden.
"""
import json
import math
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import shape, mapping, Point
from shapely.ops import unary_union, transform as shp_transform

ROOT = Path(__file__).resolve().parent.parent
SRC_FILE = ROOT / "Subbuurten_vlakken.json"
OUT_DIR = ROOT / "out"

# Havens, industrie en losse exclaves: geen parkeerzones, en ze rekken de
# matrix op met ritten van 30+ min die het beeld vertekenen.
EXCLUDE_GEBIED = {
    "Botlek-Europoort-Maasvlakte",
    "Waalhaven-Eemhaven",
    "Vondelingenplaat",
    "Spaanse Polder",
    "Nieuw Mathenesse",
    "Rivium",
    "Hoek van Holland",
    "Rozenburg",
    "Pernis",
}
MIN_AREA_M2 = 150_000  # ~15 ha; kleiner is geen zinnige parkeerzone

_to_wgs = Transformer.from_crs("EPSG:28992", "EPSG:4326", always_xy=True)


def rd_to_wgs(geom):
    return shp_transform(lambda x, y, z=None: _to_wgs.transform(x, y), geom)


def candidate_points(poly_rd, n_grid=4):
    """Kandidaat-punten binnen de zone, in RD-meters.

    Eerst een gegarandeerd-binnen punt, daarna een raster over de bounding box.
    OSRM bepaalt later welke daadwerkelijk bij een berijdbare weg liggen.
    """
    pts = [poly_rd.representative_point()]
    minx, miny, maxx, maxy = poly_rd.bounds
    for i in range(1, n_grid + 1):
        for j in range(1, n_grid + 1):
            p = Point(minx + (maxx - minx) * i / (n_grid + 1),
                      miny + (maxy - miny) * j / (n_grid + 1))
            if poly_rd.contains(p):
                pts.append(p)
    # centraalste eerst: kandidaten met de meeste ruimte om zich heen zijn het
    # meest representatief voor "ergens in deze zone parkeren"
    c = poly_rd.representative_point()
    pts.sort(key=lambda p: p.distance(c))
    return pts


def main():
    fc = json.loads(SRC_FILE.read_text())
    by_buurt = {}
    for feat in fc["features"]:
        p = feat["properties"]
        if p.get("GEBDNAAM") in EXCLUDE_GEBIED:
            continue
        name = p.get("BUURTNAAM")
        if not name:
            continue
        by_buurt.setdefault(name, {"gebied": p.get("GEBDNAAM"), "geoms": []})
        by_buurt[name]["geoms"].append(shape(feat["geometry"]).buffer(0))

    zones, points = [], []
    for name, rec in sorted(by_buurt.items()):
        poly_rd = unary_union(rec["geoms"])
        if poly_rd.area < MIN_AREA_M2:
            continue
        if poly_rd.geom_type == "MultiPolygon":  # exclaves: neem het hoofddeel
            poly_rd = max(poly_rd.geoms, key=lambda g: g.area)

        zid = f"Z{len(zones):02d}"
        cands = candidate_points(poly_rd)
        # intrazonale reistijd: halve karakteristieke maat / 25 km/u stadsrit
        intra_s = round(0.5 * math.sqrt(poly_rd.area) / (25 / 3.6))

        zones.append({
            "type": "Feature",
            "properties": {
                "zone_id": zid, "naam": name, "gebied": rec["gebied"],
                "area_m2": round(poly_rd.area), "intrazonal_s": intra_s,
            },
            "geometry": mapping(rd_to_wgs(poly_rd)),
        })
        for k, p in enumerate(cands[:8]):
            w = rd_to_wgs(p)
            points.append({"zone_id": zid, "naam": name, "cand": k,
                           "lon": round(w.x, 6), "lat": round(w.y, 6)})

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "zones.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": zones}))
    (OUT_DIR / "zone_candidates.json").write_text(json.dumps(points))
    print(f"{len(zones)} zones, {len(points)} kandidaat-punten")
    for z in zones[:6]:
        pr = z["properties"]
        print(f"  {pr['zone_id']}  {pr['naam']:<28} {pr['gebied']:<24}"
              f" {pr['area_m2']/1e6:5.2f} km2  intra {pr['intrazonal_s']}s")
    print("  ...")


if __name__ == "__main__":
    main()
