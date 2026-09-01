"""NDW open data (gratis, geen sleutel) -> gemeten snelheden per meetlocatie.

measurement_current.xml.gz  = DATEX II MeasurementSiteTable (locaties)
trafficspeed.xml.gz         = DATEX II MeasuredData (actuele snelheden, 1 min)

Eén snapshot zegt weinig; door dit periodiek te draaien bouw je zelf een
weekprofiel op. Dit script normaliseert één snapshot naar een platte tabel.
"""
import gzip
import json
import sys
from pathlib import Path
from xml.etree.ElementTree import iterparse

ROOT = Path(__file__).resolve().parent.parent
NDW = ROOT / "data" / "ndw"
OUT = ROOT / "out"
ROTTERDAM_BBOX = (4.28, 51.83, 4.65, 52.00)  # lon_min, lat_min, lon_max, lat_max


def tag(e):
    return e.tag.rsplit("}", 1)[-1]


def find(e, name):
    for c in e.iter():
        if tag(c) == name:
            return c
    return None


def parse_sites(path):
    sites = {}
    with gzip.open(path, "rb") as fh:
        for _, el in iterparse(fh, events=("end",)):
            if tag(el) != "measurementSiteRecord":
                continue
            lat, lon = find(el, "latitude"), find(el, "longitude")
            if lat is not None and lon is not None:
                name = find(el, "value")
                sites[el.get("id")] = {
                    "lat": float(lat.text), "lon": float(lon.text),
                    "naam": name.text if name is not None else "",
                }
            el.clear()
    return sites


def parse_speeds(path):
    """Per meetlocatie de gemeten snelheden (km/u), gewogen naar aantal metingen."""
    out = {}
    with gzip.open(path, "rb") as fh:
        for _, el in iterparse(fh, events=("end",)):
            if tag(el) != "siteMeasurements":
                continue
            ref = find(el, "measurementSiteReference")
            sid = ref.get("id") if ref is not None else None
            num, den = 0.0, 0.0
            for avs in el.iter():
                if tag(avs) != "averageVehicleSpeed":
                    continue
                sp = find(avs, "speed")
                n = int(avs.get("numberOfInputValuesUsed") or 0)
                if sp is None or n <= 0:
                    continue
                v = float(sp.text)
                if v < 0:          # -1 = geen geldige meting
                    continue
                num += v * n
                den += n
            if sid and den > 0:
                out[sid] = {"speed_kmh": round(num / den, 1), "n": int(den)}
            el.clear()
    return out


def main():
    sites = parse_sites(NDW / "measurement_current.xml.gz")
    speeds = parse_speeds(NDW / "trafficspeed.xml.gz")
    lo_x, lo_y, hi_x, hi_y = ROTTERDAM_BBOX

    rows = []
    for sid, s in sites.items():
        if not (lo_x <= s["lon"] <= hi_x and lo_y <= s["lat"] <= hi_y):
            continue
        m = speeds.get(sid)
        rows.append({"site_id": sid, **s,
                     "speed_kmh": m["speed_kmh"] if m else None,
                     "n": m["n"] if m else 0})

    OUT.mkdir(exist_ok=True)
    json.dump(rows, open(OUT / "ndw_snapshot.json", "w"))
    live = [r for r in rows if r["speed_kmh"] is not None]
    print(f"NDW landelijk: {len(sites)} meetlocaties, {len(speeds)} met snelheid")
    print(f"Regio Rotterdam: {len(rows)} meetlocaties, {len(live)} met actuele snelheid")
    if live:
        sp = sorted(r["speed_kmh"] for r in live)
        print(f"  snelheid p10/mediaan/p90: {sp[len(sp)//10]} / "
              f"{sp[len(sp)//2]} / {sp[int(len(sp)*.9)]} km/u")
        for r in live[:5]:
            print(f"  {r['site_id']:<22} {r['naam'][:38]:<38} {r['speed_kmh']:>5} km/u")


if __name__ == "__main__":
    sys.exit(main())
