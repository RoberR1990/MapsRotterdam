"""Matrixborden boven de snelweg als covariaat.

De signaalgevers boven de rijstroken (`Matrixsignaalinformatie.xml.gz`) melden
realtime wat er boven elke strook staat: een verlaagde snelheid, een rood kruis,
een pijl naar rechts. Dat is precies de verklaring die ontbreekt bij een
uitschieter op de snelweg -- een traject dat plotseling x3 doet omdat er een
strook dicht is, is geen structurele congestie en hoort niet in het weekprofiel.

Het koppelen kan preciezer dan bij de andere covariaten. De feed geeft weg,
rijbaan en hectometer, en de RWS-trajecten in de reistijdfeed hebben diezelfde
drie in hun id zitten:

    RWS04_ZWN_GD_A13_R_9.300_A13_R_11.160   -> A13, rijbaan R, hm 9,300-11,160
    RWS08_13_HRL_011.5                      -> A13, rijbaan L, hm 11,5

Zo is per traject te zeggen of er op dat moment iets boven díe strook stond, in
plaats van "er is ergens op de A13 wat aan de hand". Van de 2.926 trajecten zijn
er 451 op deze manier te plaatsen -- alle snelwegtrajecten dus, en dat is precies
waar matrixborden hangen.

Anders dan het weer is dit een momentopname zonder terugblik: wat er een uur
geleden boven de weg stond staat nergens meer. Vandaar een eigen dagbestand.
"""
import csv
import gzip
import os
import re
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

FEED = "https://opendata.ndw.nu/Matrixsignaalinformatie.xml.gz"
HIST = Path(os.environ.get("MATRIX_DIR") or OUT / "matrixborden")
VELDEN = ["ts", "weg", "richting", "km", "strook", "beeld"]

# Snelwegen door de regio Rotterdam. De rest van het land laten we vallen --
# de feed is landelijk en levert 18.429 borden per snapshot.
WEGEN = {"A4", "A13", "A15", "A16", "A20", "A29", "A24", "A38"}
# Welke beelden hinderen het verkeer? `blank` is een uit bord, `lane_open` en
# `restriction_end` zeggen juist dat het weer normaal is.
HINDER = {"speedlimit", "lane_closed", "lane_closed_ahead",
          "merge_left", "merge_right", "flashing_lights"}
MARGE_KM = 1.0   # hoe ver voor een traject een bord nog meetelt


def tag(e):
    return e.tag.rsplit("}", 1)[-1]


def parse(path):
    """Borden met een beeld dat hindert, op de wegen in de regio.

    De feed zet locatie en beeld in **aparte** records, allebei `<event>`, met
    de sign-uuid als enige verbinding: 18.429 records zeggen waar een bord hangt
    en 18.429 andere wat erop staat. Een record met een rood kruis bevat dus
    geen weg en geen hectometer. Twee doorgangen dus, en dan koppelen.
    """
    plaats, beelden = {}, {}
    with gzip.open(path, "rb") as fh:
        for _, el in iterparse(fh, events=("end",)):
            if tag(el) != "event":
                continue
            uuid = beeld = weg = richting = km = strook = None
            for c in el.iter():
                naam, tekst = tag(c), (c.text or "").strip()
                if naam == "uuid":
                    uuid = tekst
                elif naam == "road":
                    weg = tekst
                elif naam == "carriageway":
                    richting = tekst
                elif naam == "km":
                    km = float(tekst) if tekst else None
                elif naam == "lane":
                    strook = tekst
                elif naam == "display":
                    for k in c:
                        beeld = tag(k)
            if uuid and km is not None:
                plaats[uuid] = (weg, richting, km, strook)
            elif uuid and beeld:
                beelden[uuid] = beeld
            el.clear()

    uit = []
    for uuid, beeld in beelden.items():
        if beeld not in HINDER or uuid not in plaats:
            continue
        weg, richting, km, strook = plaats[uuid]
        if weg in WEGEN:
            uit.append({"weg": weg, "richting": richting, "km": km,
                        "strook": strook, "beeld": beeld})
    return uit


def bereik(site_id):
    """(weg, richting, km_van, km_tot) uit een traject-id, of None.

    Twee vormen komen voor: een traject tussen twee hectometerpunten, en een
    los punt. Bij een los punt is het bereik dat punt zelf.
    """
    # Beide uiteinden moeten op dezelfde weg en rijbaan liggen. Er zijn ook
    # trajecten die van de ene snelweg naar de andere lopen
    # (RWS04_ZWN_GD_A15_L_48.9_A4_L_75.6); daar zijn de twee hectometers niet
    # vergelijkbaar, en ze als bereik lezen zou 27 km A15 opleveren.
    m = re.search(r"_(A\d{1,3})_([LR])_(\d+(?:\.\d+)?)_\1_\2_(\d+(?:\.\d+)?)",
                  site_id)
    if m:
        a, b = float(m.group(3)), float(m.group(4))
        return m.group(1), m.group(2), min(a, b), max(a, b)
    m = re.match(r"^RWS\d\d_(\d{1,3})_HR([LR])_(\d+\.\d+)$", site_id)
    if m:
        km = float(m.group(3))
        return f"A{m.group(1)}", m.group(2), km, km
    return None


def lees(dag=None):
    """Borden per moment, uit de dagbestanden."""
    paden = ([HIST / f"{dag}.csv"] if dag else sorted(HIST.glob("*.csv")))
    per_moment = {}
    for p in paden:
        if not p.exists():
            continue
        with open(p, newline="") as f:
            for r in csv.DictReader(f):
                per_moment.setdefault(r["ts"], []).append(r)
    return per_moment


def hindert_traject(borden, site_id, marge_km=MARGE_KM):
    """Staat er op dit moment iets boven dit traject? None als onbekend."""
    b = bereik(site_id)
    if not b:
        return None
    weg, richting, van, tot = b
    for r in borden:
        # richting "n" komt voor en betekent niet-gespecificeerd; die telt voor
        # beide rijbanen mee in plaats van voor geen van beide
        if r["weg"] != weg:
            continue
        if r["richting"] not in (richting, "n", "", None):
            continue
        if van - marge_km <= float(r["km"]) <= tot + marge_km:
            return True
    return False


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
            w.writerow([now.isoformat(timespec="minutes"), r["weg"],
                        r["richting"], r["km"], r["strook"], r["beeld"]])
    soorten = {}
    for r in rijen:
        soorten[r["beeld"]] = soorten.get(r["beeld"], 0) + 1
    print(f"matrixborden: {len(rijen)} met hinder in de regio "
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
        wegen = sorted({r["weg"] for r in rijen})
        print(f"  {ts}  {len(rijen):>4} borden  {' '.join(wegen)}")


if __name__ == "__main__":
    main()
