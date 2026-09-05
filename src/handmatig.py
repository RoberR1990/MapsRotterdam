"""Verstoringen die geen enkele NDW-feed meldt.

De planningsfeed kent alleen wat een wegbeheerder zelf aanlevert: wegwerk,
afsluitingen, `publicEvent`-records met een vergunning erachter. Een groot
evenement als Wereldhavendagen -- kades langs de Maas dagenlang vol, geen
weg dicht maar wel drukte en omleidingen voor voetgangers en fietsers over de
rijbaan -- komt daar niet in voor: nagezocht in `evenementen.py` voor dit
weekend en nul treffers.

Dit is dus een handmatig bijgehouden lijst, geen automatisch verzamelde bron.
Elke regel is een gebied (punt + straal) en een reeks vensters waarin het
telt als bezig. Voed het net als de andere bronnen: bewust breder dan het
officiële programma, want opbouw en afbraak trekken ook verkeer.

Twee toepassingen, dezelfde tabel:
  - `disruptions.py blackouts` neemt deze mee in dezelfde vensters die het
    voor wegwerkzaamheden bouwt, zodat geraakte meetlocaties net als bij een
    opbroken straat automatisch `verstoord=1` krijgen.
  - `covariaten.py` gebruikt hem apart als kenmerk `grootevenement`, zodat er
    ook een effectgrootte uit te schatten is in plaats van alleen een filter.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from disruptions import meters  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BESTAND = ROOT / "config" / "verstoringen_handmatig.json"


def lees():
    if not BESTAND.exists():
        return []
    return json.loads(BESTAND.read_text())


def _ts(t):
    return datetime.fromisoformat(t) if isinstance(t, str) else t


def vensters(r):
    return [(_ts(a), _ts(b)) for a, b in r.get("vensters", [])]


def actief(rijen, moment):
    """De handmatige verstoringen die op dit moment lopen."""
    if isinstance(moment, str):
        moment = datetime.fromisoformat(moment)
    return [r for r in rijen
            if any(a <= moment <= b for a, b in vensters(r))]


def dichtstbij(rijen, moment, lat, lon):
    """Afstand tot de dichtstbijzijnde lopende handmatige verstoring, of None."""
    lopend = actief(rijen, moment)
    if not lopend:
        return None
    return min(meters(lat, lon, r["lat"], r["lon"]) for r in lopend)


def binnen(rijen, moment, lat, lon):
    """Ligt (lat, lon) binnen de straal van een lopende verstoring?"""
    for r in actief(rijen, moment):
        if meters(lat, lon, r["lat"], r["lon"]) <= r["straal_m"]:
            return True
    return False


def main():
    rijen = lees()
    moment = (datetime.fromisoformat(sys.argv[1]) if len(sys.argv) > 1
              else datetime.now().astimezone())
    lopend = actief(rijen, moment)
    print(f"{moment:%Y-%m-%d %H:%M}: {len(lopend)} van {len(rijen)} "
          f"handmatige verstoringen actief")
    for r in lopend:
        print(f"  {r['naam']}  ({r['lat']}, {r['lon']}) straal {r['straal_m']} m")


if __name__ == "__main__":
    main()
