"""Verzamel NDW-snelheden en bouw er een weekprofiel van op.

NDW publiceert alleen het *actuele* beeld gratis en zonder sleutel; historie zit
achter een (gratis) Dexter-account. Door dit script elke 5 minuten te draaien
bouw je je eigen historie op:

    */5 * * * * cd /pad/naar/MapsRotterdam && python3 src/sample_ndw.py collect

Na 2-3 weken heb je per meetlocatie een echt profiel over de week heen.
`aggregate` zet dat om in congestiefactoren voor src/timeslots.py.
"""
import csv
import gzip
import json
import os
import statistics
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ndw import parse_speeds, OUT  # noqa: E402

# CI zet dit naar de losse databranch-worktree; lokaal blijft het out/ndw_history
HIST = Path(os.environ.get("NDW_HISTORY_DIR") or OUT / "ndw_history")
# vensters waarin er vlakbij een meetlocatie gewerkt wordt; wordt dagelijks
# ververst door src/disruptions.py blackouts
BLACKOUTS = Path(os.environ.get("NDW_BLACKOUTS") or OUT / "ndw_site_blackouts.json")
FEED = "https://opendata.ndw.nu/trafficspeed.xml.gz"
# Tijdvakken zijn Rotterdamse kloktijd. Expliciet vastleggen, want een
# CI-runner staat op UTC en zou alles een of twee uur verschuiven.
TZ = ZoneInfo("Europe/Amsterdam")

# Welk tijdvak hoort bij een moment? (lokale Rotterdamse tijd)
def slot_of(dt):
    wd, h = dt.weekday(), dt.hour + dt.minute / 60
    if wd >= 5:
        return "weekend_middag" if 12 <= h < 17 else None
    if wd == 0 or wd == 4:      # ma en vr wijken af van een 'typische' werkdag
        return None
    if 7.5 <= h < 9.0:
        return "werkdag_ochtendspits"
    if 10 <= h < 15:
        return "werkdag_dal"
    if 16 <= h < 18.5:
        return "werkdag_avondspits"
    if 20 <= h < 23:
        # smalle referentievensters: dit tijdvak levert alleen de
        # vrije-doorstroomreferentie, daar zijn drie uur per dag genoeg voor
        return "werkdag_avond"
    return None


def sites_in_region():
    """Meetlocaties in de regio, uit het meegeleverde out/ndw_sites.json.

    Dat bestand staat in git, zodat een CI-run niet elke keer de 11 MB grote
    locatietabel hoeft te downloaden. Ververs het af en toe met src/ndw.py.
    """

    return {r["id"]: r for r in json.loads((OUT / "ndw_sites.json").read_text())}


def verstoorde_locaties(moment):
    """Meetlocaties waar op dit moment vlakbij gewerkt wordt.

    Die metingen zijn echt, maar ze zeggen iets over een wegopbreking en niet
    over het normale weekpatroon. We gooien ze niet weg -- we markeren ze, zodat
    aggregate ze overslaat en je later alsnog anders kunt kiezen.
    """
    if not BLACKOUTS.exists():
        return set()
    black = json.loads(BLACKOUTS.read_text())
    hit = set()
    for sid, vensters in black.items():
        for a, b in vensters:
            try:
                s0 = datetime.fromisoformat(a.replace("Z", "+00:00"))
                s1 = datetime.fromisoformat(b.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                continue
            if s0 <= moment <= s1:
                hit.add(sid)
                break
    return hit


def collect():
    now_local = datetime.now(TZ)
    if slot_of(now_local) is None:
        # buiten elk tijdvak: niets te meten, dus ook niets wegschrijven
        print(f"{now_local:%Y-%m-%d %H:%M} valt in geen tijdvak - overgeslagen")
        return
    HIST.mkdir(parents=True, exist_ok=True)
    # naar een tijdelijk bestand: data/ staat niet in git, dus in een verse
    # checkout bestaat die map niet
    with tempfile.NamedTemporaryFile(suffix=".xml.gz") as tmp:
        tmp.write(requests.get(FEED, timeout=120).content)
        tmp.flush()
        speeds = parse_speeds(tmp.name)
    region = sites_in_region()
    now = now_local

    verstoord = verstoorde_locaties(now)
    path = HIST / f"{now:%Y-%m-%d}.csv.gz"
    new = not path.exists()
    with gzip.open(path, "at", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["ts", "site_id", "speed_kmh", "n", "verstoord"])
        k = v = 0
        for sid, m in speeds.items():
            if sid in region:
                vs = int(sid in verstoord)
                w.writerow([now.isoformat(timespec="minutes"), sid,
                            m["speed_kmh"], m["n"], vs])
                k += 1
                v += vs
    print(f"{now:%Y-%m-%d %H:%M} slot={slot_of(now)} -> {k} metingen bijgeschreven"
          f" ({v} bij werkzaamheden, worden bij aggregate overgeslagen)")


def aggregate():
    """Vrije-doorstroomreferentie per meetlocatie = p85 in de nachtelijke uren."""
    per_site = defaultdict(lambda: defaultdict(list))
    rows = overgeslagen = 0
    for path in sorted(HIST.glob("*.csv.gz")):
        with gzip.open(path, "rt", newline="") as f:
            for r in csv.DictReader(f):
                slot = slot_of(datetime.fromisoformat(r["ts"]).astimezone(TZ))
                if r.get("verstoord") == "1":
                    overgeslagen += 1
                    continue
                if slot and int(r["n"]) > 0:
                    per_site[r["site_id"]][slot].append(float(r["speed_kmh"]))
                    rows += 1

    region = sites_in_region()
    per_class = defaultdict(list)
    out = []
    for sid, slots in per_site.items():
        ref = slots.get("werkdag_avond")
        if not ref or len(ref) < 5:      # zonder rustige referentie geen factor
            continue
        free = sorted(ref)[int(len(ref) * 0.85)]
        if free < 5:
            continue
        klasse = road_class(region.get(sid, {}).get("naam", ""))
        for slot, vals in slots.items():
            if len(vals) < 5:
                continue
            f = round(statistics.median(vals) / free, 3)
            out.append({"site_id": sid, "klasse": klasse, "slot": slot,
                        "n_metingen": len(vals), "factor": f})
            per_class[(klasse, slot)].append(f)

    if not out:
        print(f"Nog te weinig historie ({rows} metingen, {overgeslagen} overgeslagen "
              f"wegens werkzaamheden). Laat de collect-cron een paar weken draaien.")
        return
    with open(OUT / "ndw_factors.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    print(f"{rows} metingen -> {len(out)} locatie/tijdvak-factoren "
          f"({overgeslagen} overgeslagen wegens werkzaamheden vlakbij)")
    for (klasse, slot), vals in sorted(per_class.items()):
        print(f"  {klasse:<10} {slot:<22} factor {statistics.median(vals):.2f} "
              f"(n={len(vals)} locaties)")


def road_class(naam):
    """Grove wegklasse uit de NDW-locatienaam (A12, N470, stedelijk)."""
    n = naam.upper()
    if n.startswith("A") and n[1:2].isdigit():
        return "motorway"
    if n.startswith("N") and n[1:2].isdigit():
        return "trunk"
    return "urban"


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "collect"
    {"collect": collect, "aggregate": aggregate}[cmd]()
