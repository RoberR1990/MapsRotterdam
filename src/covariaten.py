"""Metingen naast weer, kalender en evenementen leggen -- en er een opslagfactor uit rekenen.

Twee dingen, en het is belangrijk ze uit elkaar te houden:

**Schoonmaken.** De basismatrix hoort een *typisch* tijdvak te beschrijven. Als
het toevallig regende tijdens twee van de drie avondspitsen die we gemeten
hebben, zit die regen er permanent in. `tabel` markeert elk meetmoment, zodat
`aggregate` verstoorde momenten kan overslaan -- net zoals het nu al doet bij
wegwerkzaamheden.

**Opslagfactor.** Los daarvan wil je weten *hoeveel* regen kost, zodat je op een
natte dag de matrix kunt opplussen. Dat is `effect`.

De rekenwijze voor beide is dezelfde en bewust simpel: vergelijk een meetlocatie
met **zichzelf** in **hetzelfde tijdvak**. Dus niet "hoe snel rijdt het in de
regen" (dan meet je vooral welke wegen toevallig nat waren), maar "hoeveel
langzamer rijdt dit meetpunt in dit tijdvak als het regent dan als het droog
is". Alle vaste verschillen tussen wegen en tussen tijdvakken vallen zo weg.

Wat je hiermee *niet* kunt: een aparte matrix per weertype. Maandag en vrijdag
leveren één meting per tijdvak per week; die opsplitsen naar nat en droog houdt
niets over. Eén factor gepoold over alle tijdvakken is wel te schatten.
"""
import csv
import gzip
import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evenementen as EV  # noqa: E402
import kalender as KAL  # noqa: E402
import matrixborden as MB  # noqa: E402
import weer as WEER  # noqa: E402
from sample_ndw import HIST, HIST_TT, TZ, road_class, slot_of  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"

# Vanaf hoeveel millimeter in een uur noemen we het nat? Open-Meteo geeft de som
# over het uur. 0,1 mm is een spat die niets doet met de doorstroming; vanaf een
# halve millimeter zetten mensen de ruitenwissers aan en gaan ze langzamer rijden.
NAT_MM = 0.5
# Wat is de steekproef? Niet het aantal meetpunten, maar het aantal MOMENTEN.
# Duizend inductielussen tijdens dezelfde bui zijn duizend metingen van één bui:
# ze zeggen samen niet meer over "wat doet regen" dan die ene bui. Op paren
# tellen zou een schatting uit twee buien er statistisch degelijk laten uitzien.
MIN_MOMENTEN = 8
MIN_PAREN = 30


def metingen():
    """Alle metingen als (moment, site, slot, snelheidsmaat), ontdubbeld.

    Beide feeds leveren iets dat met de snelheid meestijgt; voor reistijden is
    dat 1/duur. Alleen verhoudingen binnen één meetlocatie worden gebruikt, dus
    de eenheid doet er niet toe.
    """
    gezien = set()
    for paden, waarde in ((sorted(HIST.glob("*.csv.gz")),
                           lambda r: float(r["speed_kmh"]) if int(r["n"]) > 0 else None),
                          (sorted(HIST_TT.glob("*.csv.gz")),
                           lambda r: (3600 / float(r["duur_s"])
                                      if int(r["n"]) > 0 and float(r["duur_s"]) > 0
                                      else None))):
        for p in paden:
            with gzip.open(p, "rt", newline="") as f:
                for r in csv.DictReader(f):
                    k = (r["ts"], r["site_id"])
                    if k in gezien or r.get("verstoord") == "1":
                        continue
                    gezien.add(k)
                    dt = datetime.fromisoformat(r["ts"]).astimezone(TZ)
                    slot = slot_of(dt)
                    v = waarde(r)
                    if slot and v is not None:
                        yield dt, r["site_id"], slot, v


def per_moment():
    """Eén rij per meetmoment, met de covariaten erbij."""
    w = WEER.lees()
    ev = EV.lees()
    tellen = defaultdict(int)
    for dt, _sid, slot, _v in metingen():
        tellen[(dt, slot)] += 1
    rijen = []
    for (dt, slot), n in sorted(tellen.items()):
        weer_nu = WEER.bij(w, dt) or {}
        kal = KAL.bij(dt.date())
        evn = EV.bij(ev, dt) if ev else {"evenementen": "", "evenement_dicht": ""}
        neerslag = weer_nu.get("neerslag_mm")
        rijen.append({
            "ts": dt.isoformat(timespec="minutes"),
            "slot": slot,
            "metingen": n,
            "neerslag_mm": neerslag if neerslag is not None else "",
            "nat": ("" if neerslag is None
                    else int(float(neerslag) >= NAT_MM)),
            "wind_kmh": weer_nu.get("wind_kmh", ""),
            "windstoot_kmh": weer_nu.get("windstoot_kmh", ""),
            "zicht_m": weer_nu.get("zicht_m", ""),
            "temp_c": weer_nu.get("temp_c", ""),
            "vakantie": kal["vakantie"],
            "feestdag": kal["feestdag"],
            "schooldag": KAL.schooldagen_sinds_zomer(dt.date()) or "",
            **evn,
        })
    return rijen


def effect(kenmerk):
    """Hoeveel langzamer rijdt het als `kenmerk` waar is?

    Per (meetlocatie, tijdvak) is de referentie de mediaan over de momenten
    waarop het kenmerk *niet* waar was. Elke meting waarop het wél waar was
    levert dan een verhouding op. De mediaan daarvan is de opslagfactor.

    Teruggegeven als vertragingsfactor: 1,15 betekent 15% meer reistijd.
    """
    w, ev = WEER.lees(), EV.lees()
    sites = plaatsen()
    heen = defaultdict(list)      # (site, slot) -> waarden zonder het kenmerk
    met = defaultdict(list)       # (site, slot) -> waarden met het kenmerk
    momenten_met, momenten_zonder = set(), set()
    for dt, sid, slot, v in metingen():
        k = waar(kenmerk, dt, w, ev, sites.get(sid), sid)
        if k is None:
            continue
        (met if k else heen)[(sid, slot)].append(v)
        (momenten_met if k else momenten_zonder).add(dt)

    ratios, per_klasse = [], defaultdict(list)
    for sleutel, waarden in met.items():
        basis = heen.get(sleutel)
        if not basis:
            continue
        ref = statistics.median(basis)
        if ref <= 0:
            continue
        for v in waarden:
            r = ref / v          # snelheid omlaag = reistijd omhoog
            ratios.append(r)
            per_klasse[road_class(sleutel[0])].append(r)
    return ratios, per_klasse, momenten_met, momenten_zonder


def plaatsen():
    """Coordinaten per meetlocatie, voor kenmerken die plaatsgebonden zijn."""
    p = OUT / "ndw_sites.json"
    if not p.exists():
        return {}
    return {r["id"]: (r["lat"], r["lon"]) for r in json.loads(p.read_text())
            if r.get("lat") is not None}


_borden_cache = {}


def _borden():
    if not _borden_cache:
        _borden_cache.update(MB.lees() or {"": []})
    return _borden_cache


def waar(kenmerk, dt, w, ev, plaats=None, site=None):
    """Is dit kenmerk waar voor deze meting? None als we het niet weten.

    `plaats` is (lat, lon) van de meetlocatie, voor kenmerken die plaatsgebonden
    zijn. Weer en kalender gelden voor de hele stad; een evenement niet -- een
    markt in Hoogvliet doet niets met de Maastunnel. Op stadsniveau kijken zou
    "er is ergens een evenement" bijna altijd waar maken en het effect uitsmeren
    tot nul.
    """
    if kenmerk == "nat":
        n = (WEER.bij(w, dt) or {}).get("neerslag_mm")
        return None if n is None else float(n) >= NAT_MM
    if kenmerk == "vakantie":
        return bool(KAL.bij(dt.date())["vakantie"])
    if kenmerk == "feestdag":
        return bool(KAL.bij(dt.date())["feestdag"])
    if kenmerk == "evenement":
        if not ev:
            return None
        if plaats is None:
            return None          # zonder coordinaat geen uitspraak
        dicht = EV.dichtstbij(ev, dt, *plaats)
        return dicht is not None and dicht <= EV.SITE_RADIUS_M
    if kenmerk == "matrixbord":
        # Alleen te beantwoorden voor snelwegtrajecten met weg+hectometer in
        # hun id. Voor een inductielus in de stad blijft het onbekend, en dat
        # is beter dan hem stilzwijgend als "geen bord" te tellen.
        borden = _borden().get(dt.isoformat(timespec="minutes"))
        if borden is None or site is None:
            return None
        return MB.hindert_traject(borden, site)
    if kenmerk == "wind":
        s = (WEER.bij(w, dt) or {}).get("windstoot_kmh")
        return None if s is None else float(s) >= 60
    raise SystemExit(f"onbekend kenmerk: {kenmerk}")


def toon_effect(kenmerk):
    ratios, per_klasse, m_met, m_zonder = effect(kenmerk)
    print(f"\n{kenmerk}: {len(m_met)} momenten met, {len(m_zonder)} zonder")
    if min(len(m_met), len(m_zonder)) < MIN_MOMENTEN:
        print(f"  nog geen uitspraak: {MIN_MOMENTEN} momenten aan beide kanten "
              f"nodig. Meetpunten helpen hier niet -- duizend lussen tijdens "
              f"dezelfde bui blijven één bui.")
        return
    if len(ratios) < MIN_PAREN:
        print(f"  te weinig om iets te zeggen ({len(ratios)} paren, "
              f"{MIN_PAREN} nodig)")
        return
    ratios.sort()
    print(f"  vertragingsfactor mediaan {statistics.median(ratios):.3f}  "
          f"(p25 {ratios[len(ratios)//4]:.3f}, p75 {ratios[3*len(ratios)//4]:.3f}, "
          f"n={len(ratios)})")
    for kl, vals in sorted(per_klasse.items()):
        if len(vals) >= MIN_PAREN:
            print(f"    {kl:<12} {statistics.median(vals):.3f} (n={len(vals)})")


def verstoorde_momenten(kenmerken=("nat",)):
    """Meetmomenten die je uit een schone basismatrix wilt houden.

    Bewust apart van het verzamelen: bij het meten weet je nog niet wat je later
    wilt uitsluiten, dus alles wordt bewaard en pas hier gefilterd. Standaard
    alleen regen -- evenementen zijn plaatsgebonden en een moment schrappen zou
    de hele stad straffen voor een markt in Hoogvliet.
    """
    w, ev = WEER.lees(), EV.lees()
    uit = set()
    for dt, _sid, _slot, _v in metingen():
        if dt in uit:
            continue
        if any(waar(k, dt, w, ev) for k in kenmerken):
            uit.add(dt)
    return uit


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "tabel"
    if cmd == "verstoord":
        m = sorted(verstoorde_momenten())
        print(f"{len(m)} verstoorde meetmomenten")
        for dt in m:
            print(" ", dt.isoformat(timespec="minutes"))
        return
    if cmd == "tabel":
        rijen = per_moment()
        OUT.mkdir(exist_ok=True)
        with open(OUT / "covariaten.csv", "w", newline="") as f:
            wtr = csv.DictWriter(f, fieldnames=list(rijen[0]))
            wtr.writeheader()
            wtr.writerows(rijen)
        (OUT / "covariaten.json").write_text(
            json.dumps(rijen, separators=(",", ":")))
        nat = sum(1 for r in rijen if r["nat"] == 1)
        print(f"{len(rijen)} meetmomenten -> out/covariaten.csv "
              f"({nat} nat, "
              f"{sum(1 for r in rijen if r['vakantie'])} in een vakantie, "
              f"{sum(1 for r in rijen if r.get('evenementen') not in ('', 0))} "
              f"met een evenement)")
        return
    for kenmerk in (sys.argv[2:] or ["nat", "wind", "evenement", "vakantie"]):
        toon_effect(kenmerk)


if __name__ == "__main__":
    main()
