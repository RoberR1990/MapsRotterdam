"""Leg vast hoe de matrix er bij elke versie uitzag.

Zonder dit is niet terug te zien wat de kalibratie veranderd heeft. Elke keer
dat de matrices herbouwd worden voegt dit script een regel toe: welke tijdvakken,
welke mediaan en p90, en of de onderliggende factoren geschat of gemeten waren.
"""
import csv
import hashlib
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from timeslots import SLOTS, KALIBRATIE  # noqa: E402
from sample_ndw import TZ  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"


def vingerafdruk():
    """Korte hash van de factortabel, zodat identieke versies herkenbaar zijn."""
    ruw = json.dumps({k: (v["speed"], v["turn"]) for k, v in SLOTS.items()},
                     sort_keys=True)
    return hashlib.sha256(ruw.encode()).hexdigest()[:10]


def main():
    stem = sys.argv[1] if len(sys.argv) > 1 else "parkzones"
    label = sys.argv[2] if len(sys.argv) > 2 else None
    pad = OUT / f"matrix_all_{stem}.csv"
    if not pad.exists():
        sys.exit(f"{pad.name} ontbreekt -- draai eerst build_matrices.py")

    kolommen = ["freeflow"] + list(SLOTS)
    waarden = {k: [] for k in kolommen}
    for r in csv.DictReader(open(pad)):
        if r["from_zone"] == r["to_zone"]:
            continue
        for k in kolommen:
            waarden[k].append(int(r[f"{k}_s"]) / 60)

    versies_pad = OUT / f"matrix_history_{stem}.json"
    versies = json.loads(versies_pad.read_text()) if versies_pad.exists() else []
    vf = vingerafdruk()
    if versies and versies[-1]["vingerafdruk"] == vf:
        print(f"factoren ongewijzigd ({vf}) -- geen nieuwe versie toegevoegd")
        return

    q = lambda v, p: sorted(v)[int(len(v) * p)]
    versies.append({
        "versie": len(versies),
        "label": label or f"v{len(versies)} · {KALIBRATIE['bron']}",
        "datum": datetime.now(TZ).isoformat(timespec="minutes"),
        "vingerafdruk": vf,
        "bron": KALIBRATIE["bron"],
        "metingen": KALIBRATIE["metingen"],
        "toelichting": KALIBRATIE["toelichting"],
        "paren": len(waarden["freeflow"]),
        "slots": {k: {"mediaan": round(statistics.median(waarden[k]), 2),
                      "p90": round(q(waarden[k], .9), 2)} for k in kolommen},
    })
    versies_pad.write_text(json.dumps(versies, separators=(",", ":")))
    print(f"versie {versies[-1]['versie']} vastgelegd ({vf}, bron: {KALIBRATIE['bron']})")
    for k in kolommen:
        print(f"   {k:<24} mediaan {versies[-1]['slots'][k]['mediaan']:5.1f} min"
              f"   p90 {versies[-1]['slots'][k]['p90']:5.1f}")


if __name__ == "__main__":
    main()
