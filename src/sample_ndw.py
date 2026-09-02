"""Verzamel NDW-snelheden en bouw er een weekprofiel van op.

NDW publiceert alleen het *actuele* beeld gratis en zonder sleutel; historie zit
achter een (gratis) Dexter-account. Door dit periodiek te draaien bouw je je
eigen historie op. Gebruik daarvoor src/collect_standalone.sh -- dat regelt de
databranch en de push eromheen:

    */30 * * * * /pad/naar/MapsRotterdam/src/collect_standalone.sh

Na 2-3 weken heb je per meetlocatie een echt profiel over de week heen.
`aggregate` zet dat om in congestiefactoren voor src/timeslots.py.
"""
import csv
import gzip
import json
import os
import re
import statistics
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ndw import parse_speeds, parse_traveltimes, OUT  # noqa: E402

# CI zet dit naar de losse databranch-worktree; lokaal blijft het out/ndw_history
HIST = Path(os.environ.get("NDW_HISTORY_DIR") or OUT / "ndw_history")
# vensters waarin er vlakbij een meetlocatie gewerkt wordt; wordt dagelijks
# ververst door src/disruptions.py blackouts
BLACKOUTS = Path(os.environ.get("NDW_BLACKOUTS") or OUT / "ndw_site_blackouts.json")
FEED = "https://opendata.ndw.nu/trafficspeed.xml.gz"
# Tweede feed, met reistijden per traject. Onmisbaar: de snelheidsfeed bevat in
# onze regio vrijwel alleen stedelijke inductielussen, terwijl hier ook de A16
# en A20 in zitten. Met beide samen ligt er op 66% van de gereden meters een
# meetpunt in plaats van op 21%, en op de snelweg op 99%.
FEED_TT = "https://opendata.ndw.nu/traveltime.xml.gz"
# Tijdvakken zijn Rotterdamse kloktijd. Expliciet vastleggen, want een
# CI-runner staat op UTC en zou alles een of twee uur verschuiven.
TZ = ZoneInfo("Europe/Amsterdam")

VELDEN = ["ts", "site_id", "speed_kmh", "n", "verstoord"]
VELDEN_TT = ["ts", "site_id", "duur_s", "ref_s", "n", "verstoord"]
HIST_TT = Path(os.environ.get("NDW_TT_DIR") or HIST.parent / "ndw_traveltime")

# Welk tijdvak hoort bij een moment? (lokale Rotterdamse tijd)
def slot_of(dt):
    wd, h = dt.weekday(), dt.hour + dt.minute / 60
    if wd >= 5:
        return "weekend_middag" if 12 <= h < 17 else None

    if wd in (0, 4):
        # Maandag en vrijdag wijken af van een doordeweekse di-do: de
        # maandagochtend is rustiger, de vrijdagmiddag drukker. Ze krijgen eigen
        # tijdvakken in plaats van dat ze het werkdagbeeld verdunnen -- uit
        # aparte reeksen kun je later alsnog een gecombineerd ma-vr cijfer
        # rekenen, andersom niet. Op deze dagen meten we de hele dag door, van
        # 6 tot 23 uur, dus zonder de gaten die di-do wel heeft.
        dag = "maandag" if wd == 0 else "vrijdag"
        if 6 <= h < 7.5:
            return f"{dag}_vroeg"
        if 7.5 <= h < 9:
            return f"{dag}_ochtendspits"
        if 9 <= h < 16:
            return f"{dag}_dal"
        if 16 <= h < 18.5:
            return f"{dag}_avondspits"
        if 18.5 <= h < 23:
            return f"{dag}_avond"
        return None

    # Dinsdag t/m donderdag: de smalle vensters blijven smal, anders verdunt
    # schoudertijd het spitsbeeld.
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


def zet_kolommen_klaar(path):
    """Zorg dat het dagbestand de huidige kolommen heeft.

    Zonder dit worden na een schemawijziging bredere rijen achter een oudere
    header geplakt. csv.DictReader stopt die extra waarde dan onder de sleutel
    None, en een filter op r["verstoord"] doet stilzwijgend niets meer.
    """
    if not path.exists():
        with gzip.open(path, "wt", newline="") as f:
            csv.writer(f).writerow(VELDEN)
        return
    with gzip.open(path, "rt", newline="") as f:
        rijen = list(csv.reader(f))
    if not rijen or rijen[0] == VELDEN:
        return
    oud = rijen[0]
    with gzip.open(path, "wt", newline="") as f:
        w = csv.writer(f)
        w.writerow(VELDEN)
        for r in rijen[1:]:
            # rijen die al de nieuwe breedte hebben zijn positioneel te lezen
            d = dict(zip(VELDEN if len(r) == len(VELDEN) else oud, r))
            w.writerow([d.get(k, "0") for k in VELDEN])
    print(f"   dagbestand omgezet: {oud} -> {VELDEN}")


def schrijf_reistijden(now, region, verstoord):
    """Tweede feed: reistijd per traject, in een eigen dagbestand.

    Apart houden en niet in het snelheidsbestand mengen -- het zijn seconden en
    geen km/u, en een schemawijziging aan het bestaande bestand heeft eerder al
    stilletjes een filter uitgeschakeld.
    """
    with tempfile.NamedTemporaryFile(suffix=".xml.gz") as tmp:
        tmp.write(requests.get(FEED_TT, timeout=180).content)
        tmp.flush()
        tt = parse_traveltimes(tmp.name)
    HIST_TT.mkdir(parents=True, exist_ok=True)
    path = HIST_TT / f"{now:%Y-%m-%d}.csv.gz"
    if not path.exists():
        with gzip.open(path, "wt", newline="") as f:
            csv.writer(f).writerow(VELDEN_TT)
    k = 0
    with gzip.open(path, "at", newline="") as f:
        w = csv.writer(f)
        for sid, m in tt.items():
            if sid in region:
                w.writerow([now.isoformat(timespec="minutes"), sid, m["duur_s"],
                            m["ref_s"] if m["ref_s"] is not None else "",
                            m["n"], int(sid in verstoord)])
                k += 1
    print(f"   reistijdfeed: {k} trajecten in de regio bijgeschreven")


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
    schrijf_reistijden(now, region, verstoord)
    path = HIST / f"{now:%Y-%m-%d}.csv.gz"
    zet_kolommen_klaar(path)
    with gzip.open(path, "at", newline="") as f:
        w = csv.writer(f)
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
    # Dezelfde meetlocatie op hetzelfde tijdstip mag maar een keer meetellen.
    # Twee triggers naast elkaar, of een handmatige run, leveren anders
    # dubbele rijen die dat ene moment zwaarder laten wegen.
    gezien = set()
    rows = overgeslagen = dubbel = 0
    def lees(paden, waarde):
        """Beide feeds leveren hetzelfde soort getal: iets dat met de snelheid
        meestijgt. Alleen verhoudingen worden gebruikt, dus de eenheid doet er
        niet toe -- voor reistijden is 1/duur daarom bruikbaar als snelheidsmaat."""
        nonlocal rows, overgeslagen, dubbel
        for path in sorted(paden):
            with gzip.open(path, "rt", newline="") as f:
                for r in csv.DictReader(f):
                    slot = slot_of(datetime.fromisoformat(r["ts"]).astimezone(TZ))
                    sleutel = (r["ts"], r["site_id"])
                    if sleutel in gezien:
                        dubbel += 1
                        continue
                    gezien.add(sleutel)
                    if r.get("verstoord") == "1":
                        overgeslagen += 1
                        continue
                    v = waarde(r)
                    if slot and v is not None:
                        per_site[r["site_id"]][slot].append(v)
                        rows += 1

    lees(HIST.glob("*.csv.gz"),
         lambda r: float(r["speed_kmh"]) if int(r["n"]) > 0 else None)
    lees(HIST_TT.glob("*.csv.gz"),
         lambda r: (3600 / float(r["duur_s"])
                    if int(r["n"]) > 0 and float(r["duur_s"]) > 0 else None))

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
        klasse = road_class(sid)
        for slot, vals in slots.items():
            if len(vals) < 5:
                continue
            f = round(statistics.median(vals) / free, 3)
            out.append({"site_id": sid, "klasse": klasse, "slot": slot,
                        "n_metingen": len(vals), "factor": f})
            per_class[(klasse, slot)].append(f)

    if not out:
        print(f"Nog te weinig historie ({rows} metingen, {overgeslagen} overgeslagen "
              f"wegens werkzaamheden, {dubbel} dubbel). Laat de sampler een paar "
              f"weken draaien.")
        return
    with open(OUT / "ndw_factors.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    print(f"{rows} metingen -> {len(out)} locatie/tijdvak-factoren "
          f"({overgeslagen} overgeslagen wegens werkzaamheden vlakbij, "
          f"{dubbel} dubbele rijen genegeerd)")
    for (klasse, slot), vals in sorted(per_class.items()):
        print(f"  {klasse:<10} {slot:<22} factor {statistics.median(vals):.2f} "
              f"(n={len(vals)} locaties)")


def road_class(site_id):
    """Grove wegklasse uit het wegnummer in de meetpunt-id.

    Let op: het naam-veld van NDW is NIET de wegnaam maar het soort meetapparaat
    ('lus', 'fcd', 'anpr') -- daar zijn er maar drie van. Het wegnummer zit wel
    in de id, bijvoorbeeld RWS09_A16R_hm23.2 of PZH03_N219_h-1.
    """
    if re.search(r"(^|[_-])A\d{1,3}([_-]|$|[A-Za-z])", site_id):
        return "snelweg"
    if re.search(r"(^|[_-])N\d{1,3}([_-]|$|[A-Za-z])", site_id):
        return "provinciaal"
    return "stedelijk"


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "collect"
    {"collect": collect, "aggregate": aggregate}[cmd]()
