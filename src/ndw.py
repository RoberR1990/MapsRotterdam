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
    """Per meetlocatie de gemeten snelheid (km/u) en de intensiteit (vtg/uur).

    De feed levert per rijstrook eerst een blok TrafficFlow en daarna een blok
    TrafficSpeed. De stroken worden niet aan elkaar gekoppeld -- dat hoeft ook
    niet: de snelheid wordt gewogen naar het aantal metingen, de intensiteit
    wordt over de stroken opgeteld.

    Waarom de intensiteit erbij hoort: uit een snelheid alleen kun je een lege
    weg niet van een kapotte lus onderscheiden. 's Nachts melden veel stedelijke
    lussen een handvol voertuigen, en een "snelheid" uit twee auto's is ruis --
    juist in het tijdvak dat als vrije-doorstroomreferentie dient.
    """
    out = {}
    with gzip.open(path, "rb") as fh:
        for _, el in iterparse(fh, events=("end",)):
            if tag(el) != "siteMeasurements":
                continue
            ref = find(el, "measurementSiteReference")
            sid = ref.get("id") if ref is not None else None
            num, den, flow = 0.0, 0.0, 0.0
            for c in el.iter():
                naam = tag(c)
                if naam == "vehicleFlowRate" and c.text:
                    v = float(c.text)
                    if v >= 0:     # -1 = geen geldige meting
                        flow += v
                elif naam == "averageVehicleSpeed":
                    sp = find(c, "speed")
                    n = int(c.get("numberOfInputValuesUsed") or 0)
                    if sp is None or n <= 0:
                        continue
                    v = float(sp.text)
                    if v < 0:
                        continue
                    num += v * n
                    den += n
            if sid and den > 0:
                out[sid] = {"speed_kmh": round(num / den, 1), "n": int(den),
                            "flow_vh": int(flow)}
            el.clear()
    return out


def parse_traveltimes(path):
    """Gemeten reistijd per traject, plus de statische referentiewaarde.

    Deze feed dekt wél de snelwegen: de snelheidsfeed bevat vrijwel alleen
    inductielussen in de stad, terwijl hier ook de A16 en A20 in zitten. De
    reistijd is omgekeerd evenredig met de snelheid, dus 1/duur werkt als
    snelheidsmaat -- en omdat we alleen verhoudingen gebruiken maakt de schaal
    niet uit.
    """
    out = {}
    with gzip.open(path, "rb") as fh:
        for _, el in iterparse(fh, events=("end",)):
            if tag(el) != "siteMeasurements":
                continue
            sid = None
            duren, n = [], 0
            for c in el.iter():
                if tag(c) == "measurementSiteReference":
                    sid = c.get("id")
                elif tag(c) == "travelTime":
                    n = max(n, int(c.get("numberOfInputValuesUsed") or 0))
                elif tag(c) == "duration" and c.text:
                    duren.append(float(c.text))
            # eerste duur = gemeten, tweede = statische referentie
            if sid and duren and duren[0] > 0 and n > 0:
                out[sid] = {"duur_s": round(duren[0], 1),
                            "ref_s": round(duren[1], 1) if len(duren) > 1 else None,
                            "n": n}
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
