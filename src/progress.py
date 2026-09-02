"""Stand van het verzamelen: wanneer meten we, en hoever zijn we?

Leest de verzamelde historie en het meetrooster dat uit slot_of volgt, en
schrijft out/progress.json voor de webweergave. Het rooster wordt niet
overgetypt maar afgeleid: slot_of een hele week aflopen op de minuut waarop de
routines vuren, zodat rooster en code niet uit elkaar kunnen lopen.
"""
import csv
import glob
import gzip
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sample_ndw import slot_of, TZ, HIST  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
MINUUT = 48          # de minuut waarop de routines vuren
DOEL_MOMENTEN = 20   # per tijdvak; aggregate heeft er minstens 5 nodig

LABELS = {
    "vroeg": "Vroege ochtend", "ochtendspits": "Ochtendspits", "dal": "Dal",
    "avondspits": "Avondspits", "avond": "Avond", "middag": "Middag",
}
DAGEN = ["ma", "di", "wo", "do", "vr", "za", "zo"]


def rooster():
    """Welke (dag, uur) in lokale tijd raakt een tijdvak? Afgeleid uit slot_of."""
    # een willekeurige maandag; DST doet er niet toe binnen deze week
    start = datetime(2026, 9, 7, 0, MINUUT, tzinfo=TZ)
    uit = []
    for h in range(24 * 7):
        t = start + timedelta(hours=h)
        s = slot_of(t)
        if s:
            uit.append({"dag": t.weekday(), "uur": t.hour, "slot": s})
    return uit


def vensters():
    """De echte tijdvakgrenzen per dag, in decimale uren.

    Het rooster geeft de momenten waarop we meten; dit geeft het venster
    waarbinnen die momenten vallen. Afgetast op vijf minuten in plaats van
    overgetypt, zodat het niet uit de pas kan lopen met slot_of.
    """
    start = datetime(2026, 9, 7, 0, 0, tzinfo=TZ)
    uit, lopend = [], None
    for i in range(7 * 24 * 12):
        t = start + timedelta(minutes=5 * i)
        s = slot_of(t)
        h = t.hour + t.minute / 60
        if lopend and (lopend["slot"] != s or lopend["dag"] != t.weekday()):
            uit.append(lopend)
            lopend = None
        if s and not lopend:
            lopend = {"dag": t.weekday(), "slot": s, "van": h, "tot": h}
        if s and lopend:
            lopend["tot"] = h + 5 / 60
    if lopend:
        uit.append(lopend)
    return uit


def historie():
    momenten = defaultdict(set)
    per_site = defaultdict(lambda: defaultdict(set))
    gezien = set()
    stats = {"bruikbaar": 0, "dubbel": 0, "verstoord": 0}
    eerste = laatste = None
    for p in sorted(glob.glob(str(HIST / "*.csv.gz"))):
        with gzip.open(p, "rt", newline="") as f:
            for r in csv.DictReader(f):
                k = (r["ts"], r["site_id"])
                if k in gezien:
                    stats["dubbel"] += 1
                    continue
                gezien.add(k)
                if r.get("verstoord") == "1":
                    stats["verstoord"] += 1
                    continue
                s = slot_of(datetime.fromisoformat(r["ts"]).astimezone(TZ))
                if not s:
                    continue
                stats["bruikbaar"] += 1
                momenten[s].add(r["ts"])
                per_site[r["site_id"]][s].add(r["ts"])
                eerste = min(eerste or r["ts"], r["ts"])
                laatste = max(laatste or r["ts"], r["ts"])
    return momenten, per_site, stats, eerste, laatste


def main():
    rst = rooster()
    per_week = defaultdict(int)
    for c in rst:
        per_week[c["slot"]] += 1

    momenten, per_site, stats, eerste, laatste = historie()
    slots = []
    for key in sorted(per_week):
        soort = key.split("_", 1)[1]
        groep = key.split("_", 1)[0]
        klaar = sum(1 for s in per_site if len(per_site[s].get(key, ())) >= 5)
        slots.append({
            "key": key,
            "groep": {"werkdag": "di–do", "maandag": "maandag",
                      "vrijdag": "vrijdag", "weekend": "weekend"}[groep],
            "soort": LABELS.get(soort, soort),
            "per_week": per_week[key],
            "momenten": len(momenten.get(key, ())),
            "doel": DOEL_MOMENTEN,
            "locaties_klaar": klaar,
        })

    alle_momenten = {t for v in momenten.values() for t in v}
    data = {
        "momenten_totaal": len(alle_momenten),
        "gegenereerd": datetime.now(TZ).isoformat(timespec="minutes"),
        "eerste_meting": eerste, "laatste_meting": laatste,
        "rooster": rst, "vensters": vensters(), "minuut": MINUUT,
        "dagen": DAGEN, "slots": slots, "stats": stats,
        "vuringen_per_week": len(rst),
        "soorten": list(dict.fromkeys(s["soort"] for s in slots)),
    }
    OUT.mkdir(exist_ok=True)
    (OUT / "progress.json").write_text(json.dumps(data, separators=(",", ":")))

    print(f"{len(rst)} vuringen per week over {len(slots)} tijdvakken")
    print(f"historie: {stats['bruikbaar']} bruikbaar, {stats['dubbel']} dubbel, "
          f"{stats['verstoord']} verstoord")
    for s in slots:
        bal = "#" * min(20, round(s["momenten"] / s["doel"] * 20))
        print(f"  {s['groep']:<8} {s['soort']:<16} {s['momenten']:>3}/{s['doel']}"
              f"  {s['per_week']:>2}/week  {bal}")


if __name__ == "__main__":
    main()
