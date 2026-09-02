"""Wat laten de gemeten reistijden zien over het verloop van een dag?

De reistijdfeed geeft per traject een duur per moment. Door die te delen door de
snelste waarneming van diezelfde dag krijg je een vertragingsfactor die niet
afhangt van de lengte van het traject. Deze analyse zet die factoren per
wegklasse op een rij en vergelijkt ze met de plaatshouders in timeslots.py.

Belangrijk: dit is beschrijvend, geen kalibratie. Daarvoor zijn meer losse dagen
nodig -- uit een enkele dag is een normale spits niet van een incident te
onderscheiden.
"""
import csv
import glob
import gzip
import json
import os
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sample_ndw import road_class, HIST_TT  # noqa: E402
from timeslots import SLOTS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
MIN_WAARNEMINGEN = 4      # minder en de snelste waarneming zegt te weinig
KLASSEN = ("snelweg", "provinciaal", "stedelijk")


def q(vals, p):
    return sorted(vals)[min(len(vals) - 1, int(len(vals) * p))]


def main():
    ttdir = Path(sys.argv[1]) if len(sys.argv) > 1 else HIST_TT
    per = defaultdict(dict)
    for p in sorted(glob.glob(str(ttdir / "*.csv.gz"))):
        with gzip.open(p, "rt", newline="") as f:
            for r in csv.DictReader(f):
                if r["verstoord"] != "1":
                    per[r["site_id"]][r["ts"]] = float(r["duur_s"])
    if not per:
        sys.exit(f"geen reistijden gevonden in {ttdir}")

    # eigen vrije doorstroom per traject: de snelste waarneming van de reeks
    vrij = {s: min(v.values()) for s, v in per.items()
            if len(v) >= MIN_WAARNEMINGEN and min(v.values()) > 0}
    momenten = sorted({t for s in vrij for t in per[s]})

    profiel = []
    for t in momenten:
        rij = {"ts": t, "klassen": {}}
        for kl in KLASSEN:
            f = [per[s][t] / vrij[s] for s in vrij
                 if t in per[s] and road_class(s) == kl]
            if len(f) >= 20:
                rij["klassen"][kl] = {
                    "n": len(f), "mediaan": round(statistics.median(f), 3),
                    "p75": round(q(f, .75), 3), "p90": round(q(f, .9), 3),
                }
        profiel.append(rij)

    # het drukste moment, en hoe scheef de verdeling daar is
    piek = max(profiel, key=lambda r: r["klassen"].get("stedelijk", {}).get("mediaan", 0))

    # plaatshouders omrekenen: een snelheidsfactor 0,5 betekent twee keer zo lang
    ph = SLOTS["werkdag_avondspits"]["speed"]
    plaatshouder = {
        "snelweg": round(1 / ph["motorway"], 2),
        "provinciaal": round(1 / ph["trunk"], 2),
        "stedelijk": round(1 / ph["secondary"], 2),
    }

    data = {"momenten": momenten, "profiel": profiel, "piek": piek["ts"],
            "plaatshouder": plaatshouder, "trajecten": len(vrij),
            "klassen": list(KLASSEN)}
    (OUT / "dagprofiel.json").write_text(json.dumps(data, separators=(",", ":")))

    print(f"{len(vrij)} trajecten, {len(momenten)} momenten "
          f"({momenten[0][11:16]}-{momenten[-1][11:16]})\n")
    kop = "  tijd " + "".join(f"{k:>13}" for k in KLASSEN)
    print(kop + "\n  " + "-" * (len(kop) - 2))
    for r in profiel:
        s = f"  {r['ts'][11:16]}"
        for kl in KLASSEN:
            v = r["klassen"].get(kl)
            s += f"{('x%.2f' % v['mediaan']) if v else '-':>13}"
        print(s)

    print(f"\ndrukste moment: {piek['ts'][11:16]}")
    print(f"  {'klasse':<14}{'mediaan':>9}{'p75':>8}{'p90':>8}{'plaatshouder':>14}")
    for kl in KLASSEN:
        v = piek["klassen"].get(kl)
        if v:
            print(f"  {kl:<14}{('x%.2f'%v['mediaan']):>9}{('x%.2f'%v['p75']):>8}"
                  f"{('x%.2f'%v['p90']):>8}{('x%.2f'%plaatshouder[kl]):>14}")
    print("\n-> out/dagprofiel.json")


if __name__ == "__main__":
    main()
