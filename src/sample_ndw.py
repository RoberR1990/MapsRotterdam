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
from collections import Counter, defaultdict
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

# Wanneer is een tijdvak bruikbaar? Niet bij genoeg metingen, maar bij genoeg
# LOSSE DAGEN. Zeven metingen op een avond zijn zeven keer dezelfde avond: ze
# halen de ruis binnen dat moment omlaag, maar zeggen niets over hoe de dinsdag
# van de donderdag verschilt. Nagerekend op de eerste dag data: de klassemediaan
# zat al na een enkel moment binnen ~1% van de waarde uit zeven momenten, dus
# ruis is het probleem niet -- spreiding over dagen wel.
MIN_DAGEN = 3
MIN_METINGEN = 5
HIST_TT = Path(os.environ.get("NDW_TT_DIR") or HIST.parent / "ndw_traveltime")

# Welk tijdvak hoort bij een moment? (lokale Rotterdamse tijd)
def slot_of(dt):
    wd, h = dt.weekday(), dt.hour + dt.minute / 60

    # De vrije-doorstroomreferentie. Alle factoren delen hierdoor, dus dit is
    # het enige tijdvak dat elke dag meet: hoe eerder het vol is, hoe eerder de
    # rest bruikbaar wordt. 1-5 uur en niet 0-5, zodat het uitgaansverkeer van
    # vrijdag- en zaterdagnacht er grotendeels buiten valt.
    if 1 <= h < 5:
        return "nacht_referentie"

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


def aggregate(ref_keuze="auto"):
    """Congestiefactor per meetlocatie en tijdvak: gemeten / vrije doorstroom.

    Voor de vrije doorstroom zijn er twee soorten referentie, en ze zijn geen
    van beide vanzelfsprekend de juiste:

    * `ndw` -- de statische referentiereistijd die NDW zelf per traject
      meelevert in de reistijdfeed. Meteen beschikbaar, geen wachttijd, en
      onafhankelijk van ons eigen meetrooster. Nadeel: we weten niet precies
      hoe NDW hem afleidt, en hij bestaat alleen voor trajecten (dus niet voor
      de losse inductielussen uit de snelheidsfeed).
    * een tijdvak uit onze eigen historie (`nacht_referentie`, of `werkdag_avond`
      zolang de nachten nog niet binnen zijn) -- zelf gemeten en dus navolgbaar,
      maar het kost dagen voor het bruikbaar is en 's nachts melden veel
      stedelijke lussen niets.

    Nagerekend op 2.500 trajecten waar allebei bestaat: NDW's statische
    referentie is *langzamer* dan wat wij 's avonds meten (mediaan 0,90). Op de
    snelweg levert hij factoren boven 1 op -- avondverkeer rijdt dan harder dan
    de "referentie". Hij is dus geen vrije doorstroom, eerder een typische
    reistijd. Daarom is hij hier een **toetssteen en geen productiereferentie**:
    `auto` blijft bij onze eigen tijdvakken, en `ndw` is er om tegenaan te
    houden. Ze door elkaar gebruiken zou locaties met een NDW-referentie een
    systematisch ~11% hogere factor geven dan hun buren.
    """
    per_site = defaultdict(lambda: defaultdict(list))
    ndw_vrij = defaultdict(list)   # site -> statische referentie als snelheidsmaat
    # Dezelfde meetlocatie op hetzelfde tijdstip mag maar een keer meetellen.
    # Twee triggers naast elkaar, of een handmatige run, leveren anders
    # dubbele rijen die dat ene moment zwaarder laten wegen.
    gezien = set()
    rows = overgeslagen = dubbel = weer_weg = 0
    # Schoonmaken is opt-in: standaard rekent aggregate met alles, en met
    # NDW_SCHOON=1 blijven momenten met regen erbuiten. Opt-in omdat filteren
    # data kost, en met een handvol natte momenten is dat een slechte ruil --
    # zie src/covariaten.py.
    slecht = set()
    if os.environ.get("NDW_SCHOON") == "1":
        from covariaten import verstoorde_momenten
        slecht = verstoorde_momenten()

    def lees(paden, waarde, vrij=None):
        """Beide feeds leveren hetzelfde soort getal: iets dat met de snelheid
        meestijgt. Alleen verhoudingen worden gebruikt, dus de eenheid doet er
        niet toe -- voor reistijden is 1/duur daarom bruikbaar als snelheidsmaat."""
        nonlocal rows, overgeslagen, dubbel, weer_weg
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
                    if slecht and datetime.fromisoformat(
                            r["ts"]).astimezone(TZ) in slecht:
                        weer_weg += 1
                        continue
                    if vrij:
                        v0 = vrij(r)
                        if v0 is not None:
                            ndw_vrij[r["site_id"]].append(v0)
                    v = waarde(r)
                    if slot and v is not None:
                        dag = datetime.fromisoformat(r["ts"]).astimezone(TZ).date()
                        per_site[r["site_id"]][slot].append((dag, v))
                        rows += 1

    def getal(r, veld):
        try:
            x = float(r[veld])
        except (KeyError, TypeError, ValueError):
            return None
        return x if x > 0 else None

    lees(HIST.glob("*.csv.gz"),
         lambda r: float(r["speed_kmh"]) if int(r["n"]) > 0 else None)
    lees(HIST_TT.glob("*.csv.gz"),
         lambda r: (3600 / float(r["duur_s"])
                    if int(r["n"]) > 0 and float(r["duur_s"]) > 0 else None),
         vrij=lambda r: (3600 / getal(r, "ref_s")
                         if getal(r, "ref_s") else None))

    per_class = defaultdict(list)
    out = []
    def bruikbaar(paren):
        return (len(paren) >= MIN_METINGEN
                and len({d for d, _ in paren}) >= MIN_DAGEN)

    # De nacht is de enige echt vrije doorstroom die we zelf meten; werkdag_avond
    # was een noodgreep uit de tijd dat we 's nachts niets ophaalden. Zodra de
    # nacht meer locaties dekt schakelen we vanzelf over -- geen drempel om met
    # de hand bij te stellen.
    def dekking(slot):
        return sum(1 for sl in per_site.values() if bruikbaar(sl.get(slot, [])))

    ref_slot = max(("nacht_referentie", "werkdag_avond"), key=dekking)

    def vrije_doorstroom(sid, slots):
        """(waarde, naam) van de referentie voor deze locatie, of (None, None)."""
        if ref_keuze == "ndw":
            if not ndw_vrij.get(sid):
                return None, None
            return statistics.median(ndw_vrij[sid]), "ndw_statisch"
        ref = slots.get(ref_keuze if ref_keuze != "auto" else ref_slot)
        if not ref or not bruikbaar(ref):
            return None, None
        rw = sorted(v for _, v in ref)
        return rw[int(len(rw) * 0.85)], (ref_keuze if ref_keuze != "auto"
                                         else ref_slot)

    for sid, slots in per_site.items():
        free, ref_naam = vrije_doorstroom(sid, slots)
        if not free or free <= 0:
            continue
        klasse = road_class(sid)
        for slot, paren in slots.items():
            if not bruikbaar(paren):
                continue
            f = round(statistics.median(v for _, v in paren) / free, 3)
            out.append({"site_id": sid, "klasse": klasse, "slot": slot,
                        "n_metingen": len(paren),
                        "n_dagen": len({d for d, _ in paren}), "factor": f,
                        "referentie": ref_naam})
            per_class[(klasse, slot)].append(f)

    if not out:
        dagen = {d for sl in per_site.values() for pr in sl.values() for d, _ in pr}
        print(f"Nog niet bruikbaar: {rows} metingen over {len(dagen)} dag(en), "
              f"{overgeslagen} overgeslagen wegens werkzaamheden, {dubbel} dubbel. "
              f"Een tijdvak telt mee vanaf {MIN_DAGEN} losse dagen en "
              f"{MIN_METINGEN} metingen.")
        return
    with open(OUT / "ndw_factors.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    print(f"{rows} metingen -> {len(out)} locatie/tijdvak-factoren "
          f"({overgeslagen} overgeslagen wegens werkzaamheden vlakbij, "
          f"{dubbel} dubbele rijen genegeerd"
          + (f", {weer_weg} wegens weer" if weer_weg else "") + ")")
    gebruikt = Counter(r["referentie"] for r in out)
    print("  referentie: " + ", ".join(f"{k} ({v} rijen)"
                                       for k, v in gebruikt.most_common()))
    vergelijk_referenties(per_site, ndw_vrij, ref_slot, bruikbaar)
    for (klasse, slot), vals in sorted(per_class.items()):
        print(f"  {klasse:<10} {slot:<22} factor {statistics.median(vals):.2f} "
              f"(n={len(vals)} locaties)")


def vergelijk_referenties(per_site, ndw_vrij, ref_slot, bruikbaar):
    """Zijn de twee vrije-doorstroomreferenties het met elkaar eens?

    Alleen te beantwoorden op locaties waar ze allebei bestaan. Een verhouding
    boven 1 betekent dat NDW's statische referentie sneller is dan wat wij
    's nachts meten -- dan onderschat onze eigen referentie de vrije doorstroom,
    en daarmee de congestie.
    """
    paren = []
    for sid, slots in per_site.items():
        if not ndw_vrij.get(sid):
            continue
        eigen = slots.get(ref_slot)
        if not eigen or not bruikbaar(eigen):
            continue
        rw = sorted(v for _, v in eigen)
        p85 = rw[int(len(rw) * 0.85)]
        if p85 > 0:
            paren.append(statistics.median(ndw_vrij[sid]) / p85)
    if len(paren) < 10:
        print(f"  vergelijking referenties: nog te weinig overlap "
              f"({len(paren)} locaties met allebei)")
        return
    paren.sort()
    print(f"  ndw_statisch / {ref_slot}: mediaan "
          f"{statistics.median(paren):.2f} (p10 {paren[len(paren)//10]:.2f}, "
          f"p90 {paren[9*len(paren)//10]:.2f}, n={len(paren)})")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "collect"
    if cmd == "aggregate":
        # optioneel: auto (standaard) | ndw | nacht_referentie | werkdag_avond
        aggregate(sys.argv[2] if len(sys.argv) > 2 else "auto")
    else:
        {"collect": collect}[cmd]()
