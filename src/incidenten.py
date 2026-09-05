"""Het actuele beeld (ongevallen, pech, obstakels, brugopeningen) als covariaat.

`actueel_beeld.xml.gz` is de NDW-feed die verkeerscentrales zelf gebruiken:
wat er nu op de weg gebeurt, zonder vooraankondiging. Dat vult precies het gat
dat de matrixborden laten liggen -- die verklaren alleen snelwegstroken, dit
verklaart een uitschieter op een willekeurige stadsweg. En het is de enige
plek waar een echte brugopening (`bridgeSwingInOperation`) live gemeld wordt;
de planningsfeed voor bruggen bleek voor Rotterdam leeg.

Net als bij de matrixborden is dit een momentopname zonder geheugen: wat er
een uur geleden speelde staat nergens meer. Vandaar een eigen dagbestand, en
vandaar dat dit bij elke run vers wordt opgehaald in plaats van hergebruikt --
anders dan de planningsfeeds in ndw_events.py, die weken vooruitkijken en dus
niet elk uur hoeven te verversen.
"""
import csv
import gzip
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from xml.etree.ElementTree import iterparse
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from net import haal as haal_url  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
TZ = ZoneInfo("Europe/Amsterdam")

FEED = "https://opendata.ndw.nu/actueel_beeld.xml.gz"
HIST = Path(os.environ.get("INCIDENT_DIR") or OUT / "incidenten")
VELDEN = ["ts", "soort", "lat", "lon"]
ROTTERDAM_BBOX = (4.28, 51.83, 4.65, 52.00)

# Wat telt als iets dat de doorstroming raakt. `ReroutingManagement` (een
# omleiding is al ingesteld) en `GeneralObstruction` horen daar ook bij;
# een aangekondigde maar nog niet actieve maatregel niet.
SOORTEN = {"Accident", "VehicleObstruction", "GeneralObstruction",
           "ReroutingManagement"}
BRUG = "bridgeSwingInOperation"


def tag(e):
    return e.tag.rsplit("}", 1)[-1]


def in_bbox(lat, lon):
    lo_x, lo_y, hi_x, hi_y = ROTTERDAM_BBOX
    return lo_x <= lon <= hi_x and lo_y <= lat <= hi_y


def parse(path):
    """Records met verkeersgevolg of een brugopening, in de regio Rotterdam."""
    uit = []
    with gzip.open(path, "rb") as fh:
        for _, el in iterparse(fh, events=("end",)):
            if tag(el) != "situationRecord":
                continue
            xsi = next((v for k, v in el.attrib.items() if k.endswith("}type")), "")
            soort = xsi.rsplit(":", 1)[-1]
            lat = lon = netwerk = None
            for c in el.iter():
                naam, tekst = tag(c), (c.text or "").strip()
                if naam == "latitude" and tekst:
                    lat = float(tekst)
                elif naam == "longitude" and tekst:
                    lon = float(tekst)
                elif naam == "generalNetworkManagementType":
                    netwerk = tekst
            brug = netwerk == BRUG
            if lat is None or lon is None or not in_bbox(lat, lon):
                el.clear()
                continue
            if soort in SOORTEN or brug:
                uit.append({"soort": "Brugopening" if brug else soort,
                            "lat": lat, "lon": lon})
            el.clear()
    return uit


def lees(dag=None):
    """Incidenten per moment, uit de dagbestanden."""
    paden = ([HIST / f"{dag}.csv"] if dag else sorted(HIST.glob("*.csv")))
    per_moment = {}
    for p in paden:
        if not p.exists():
            continue
        with open(p, newline="") as f:
            for r in csv.DictReader(f):
                per_moment.setdefault(r["ts"], []).append(r)
    return per_moment


def meters(lat1, lon1, lat2, lon2):
    import math
    kx = math.cos(math.radians((lat1 + lat2) / 2)) * 111_320
    return math.hypot((lon2 - lon1) * kx, (lat2 - lat1) * 110_540)


def dichtstbij(rijen, lat, lon, soorten=None):
    """Afstand tot het dichtstbijzijnde incident op dit moment, of None.

    `rijen` is de lijst voor één moment (uit `lees()[ts]`), niet het hele
    archief -- de aanroeper kiest het moment, net als bij matrixborden en
    evenementen.
    """
    kandidaten = [r for r in (rijen or [])
                  if soorten is None or r["soort"] in soorten]
    if not kandidaten:
        return None
    afstanden = [meters(lat, lon, float(r["lat"]), float(r["lon"]))
                 for r in kandidaten]
    return min(afstanden)


def collect():
    now = datetime.now(TZ)
    with tempfile.NamedTemporaryFile(suffix=".xml.gz") as tmp:
        tmp.write(haal_url(FEED, timeout=120))
        tmp.flush()
        rijen = parse(tmp.name)
    HIST.mkdir(parents=True, exist_ok=True)
    pad = HIST / f"{now:%Y-%m-%d}.csv"
    nieuw = not pad.exists()
    with open(pad, "a", newline="") as f:
        w = csv.writer(f)
        if nieuw:
            w.writerow(VELDEN)
        for r in rijen:
            w.writerow([now.isoformat(timespec="minutes"), r["soort"],
                        r["lat"], r["lon"]])
    soorten = {}
    for r in rijen:
        soorten[r["soort"]] = soorten.get(r["soort"], 0) + 1
    print(f"incidenten: {len(rijen)} in de regio "
          + (", ".join(f"{k} {v}" for k, v in sorted(soorten.items())) or "-"))


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "collect"
    if cmd == "collect":
        collect()
        return
    per_moment = lees()
    print(f"{len(per_moment)} momenten in {HIST}")
    for ts in sorted(per_moment)[-5:]:
        rijen = per_moment[ts]
        soorten = {}
        for r in rijen:
            soorten[r["soort"]] = soorten.get(r["soort"], 0) + 1
        print(f"  {ts}  {len(rijen):>3} incident(en)  "
              + ", ".join(f"{k} {v}" for k, v in sorted(soorten.items())))


if __name__ == "__main__":
    main()
