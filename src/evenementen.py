"""Evenementen als covariaat bij de NDW-metingen.

De NDW-planningsfeed die we al elke dag ophalen bevat naast wegwerkzaamheden
ook `publicEvent`-records: festivals, concerten, markten, wedstrijden, met
locatie, periode en verkeersgevolg. Vandaag 122 stuks voor de regio, waarvan 20
met "weg dicht in beide richtingen". Die zaten er dus al in en werden niet
gebruikt.

Eén ding om te weten: het is een **plannings**feed. Hij kijkt vooruit, en een
evenement dat voorbij is verdwijnt eruit. Een momentopname van vandaag zegt dus
niets over wat er vorige week speelde. Daarom houdt dit een archief bij dat bij
elke run wordt aangevuld: wat we eenmaal gezien hebben bewaren we. Gevolg: voor
metingen van vóór de eerste archiefrun weten we het niet, en dat is eerlijker
dan doen alsof er niets was.

Anders dan wegwerkzaamheden markeren we evenementen niet meteen als "overslaan".
Een festival hoort bij het normale stadsleven, en of je het uit de basismatrix
wilt filteren of er juist een opslagfactor uit wilt rekenen is een keuze die je
achteraf wilt kunnen maken -- niet één die je bij het verzamelen al vastlegt.
"""
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from disruptions import meters, ts  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
TZ = ZoneInfo("Europe/Amsterdam")

ARCHIEF = Path(os.environ.get("EVENEMENTEN_BESTAND")
               or OUT / "evenementen" / "rotterdam.json")
SITE_RADIUS_M = 500      # ruimer dan bij wegwerk: een evenement trekt verkeer aan
                         # over een groter gebied dan de afzetting zelf beslaat
GEEN_GEVOLG = "Geen gevolgen voor verkeer"
# Een record loopt vaak maanden ("weekmarkt tot juli 2028"), maar de echte
# tijden staan in `perioden`. Een periode die zelf dagen duurt is geen moment
# maar een staande mededeling -- De Kuip heeft er zo een die het hele seizoen
# beslaat. Die zegt niets over wanneer er gevoetbald wordt, dus als covariaat
# is hij waardeloos: hij staat altijd aan.
MAX_PERIODE_UREN = 48


def uit_feed():
    """De publicEvent-records uit de laatst opgehaalde planningsfeed."""
    p = OUT / "ndw_events_rotterdam.json"
    if not p.exists():
        sys.exit("out/ndw_events_rotterdam.json ontbreekt -- draai eerst "
                 "src/ndw_events.py")
    rows = json.loads(p.read_text())["wegwerk_evenementen"]
    return [r for r in rows
            if r.get("oorzaak_type") == "publicEvent"
            and r.get("lat") is not None
            and ts(r.get("start")) and ts(r.get("eind"))]


def sleutel(r):
    return f"{r.get('situatie')}/{r.get('record')}"


def lees(pad=None):
    pad = Path(pad or ARCHIEF)
    if not pad.exists():
        return {}
    return json.loads(pad.read_text())


def schrijf(rijen, pad=None):
    pad = Path(pad or ARCHIEF)
    pad.parent.mkdir(parents=True, exist_ok=True)
    pad.write_text(json.dumps(rijen, ensure_ascii=False, separators=(",", ":")))


def archiveer():
    """Nieuwe evenementen bij het archief zetten. Bestaande worden bijgewerkt --
    een organisator kan de tijden nog verschuiven -- maar nooit weggegooid."""
    bestaand = lees()
    vers = {sleutel(r): r for r in uit_feed()}
    nieuw = [k for k in vers if k not in bestaand]
    samen = {**bestaand, **vers}
    for k in nieuw:
        samen[k]["gezien"] = datetime.now(TZ).isoformat(timespec="minutes")
    schrijf(samen)
    print(f"evenementen: {len(samen)} in archief ({len(nieuw)} nieuw, "
          f"{len(vers) - len(nieuw)} bijgewerkt)")
    return samen


def hindert(r):
    """Heeft dit evenement verkeersgevolgen? NDW zegt het er zelf bij."""
    return (r.get("omschrijving") or "").strip() not in ("", GEEN_GEVOLG)


def perioden(r):
    """De echte tijdvakken van dit evenement, blanket-mededelingen eruit."""
    uit = []
    for paar in r.get("perioden") or []:
        van, tot = ts(paar[0]), ts(paar[1])
        if van and tot and (tot - van) <= timedelta(hours=MAX_PERIODE_UREN):
            uit.append((van, tot))
    return uit


def actief(rijen, moment, alleen_hinder=True):
    """Welke evenementen lopen op dit moment?

    Op `perioden` en niet op start/eind: die laatste twee zijn de omhulling van
    een reeks. Een weekmarkt staat in de feed als één record van september 2026
    tot juli 2028 met honderd losse perioden erin. Op start/eind kijken zou hem
    twee jaar lang onafgebroken "actief" maken.

    Ontdubbeld op situatie-id: NDW splitst één situatie in meerdere records
    (dezelfde De Kuip-melding komt achttien keer terug) en die zouden anders
    allemaal apart meetellen.
    """
    if isinstance(moment, str):
        moment = datetime.fromisoformat(moment)
    gezien, uit = set(), []
    for r in rijen.values():
        if alleen_hinder and not hindert(r):
            continue
        if r.get("situatie") in gezien:
            continue
        if any(van <= moment <= tot for van, tot in perioden(r)):
            gezien.add(r.get("situatie"))
            uit.append(r)
    return uit


def dichtstbij(rijen, moment, lat, lon):
    """Afstand tot het dichtstbijzijnde lopende evenement, of None."""
    afstanden = [meters(lat, lon, r["lat"], r["lon"])
                 for r in actief(rijen, moment)]
    return min(afstanden) if afstanden else None


def bij(rijen, moment):
    """Covariaat op stadsniveau: hoeveel hinderlijke evenementen lopen er nu?"""
    lopend = actief(rijen, moment)
    return {"evenementen": len(lopend),
            "evenement_dicht": sum(1 for r in lopend
                                   if "dicht" in (r.get("omschrijving") or ""))}


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "archiveer"
    if cmd == "archiveer":
        archiveer()
        return
    rijen = lees()
    moment = (datetime.fromisoformat(sys.argv[2]) if len(sys.argv) > 2
              else datetime.now(TZ))
    lopend = actief(rijen, moment)
    print(f"{moment:%Y-%m-%d %H:%M}: {len(lopend)} evenement(en) met "
          f"verkeersgevolg, van {len(rijen)} in archief")
    for r in sorted(lopend, key=lambda r: r["start"])[:15]:
        print(f"  {r['start'][:16]} -> {r['eind'][:16]}  "
              f"{(r.get('oorzaak') or '?').strip(', '):<12} "
              f"{r.get('omschrijving') or ''}")


if __name__ == "__main__":
    main()
