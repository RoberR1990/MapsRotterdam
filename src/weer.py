"""Uurlijks weer voor Rotterdam, als covariaat bij de NDW-metingen.

Waarom dit erbij hoort: regen verandert de reistijd, en als het toevallig
regende tijdens de drie avondspitsen die we gemeten hebben, bakken we dat
permanent in de matrix. Net als bij wegwerkzaamheden willen we het kunnen
markeren, niet weggooien -- dan kun je later kiezen: eruit filteren voor een
schone basismatrix, of er juist een opslagfactor uit rekenen.

Bron: Open-Meteo. Gratis, geen sleutel, en `past_days` levert de afgelopen week
opnieuw mee. Dat laatste maakt dit zelfherstellend: een gemiste dag wordt bij de
volgende run gewoon aangevuld, dus dit hoeft niet bij elke meting te draaien en
een storing van een paar uur kost niets.

Eén punt (het centrum) voor de hele stad. Een bui kan lokaal zijn, dus op
uurbasis over 15 km stad is dit een benadering -- maar wel een die voor
"regende het toen" ruim voldoende is.
"""
import csv
import json
import os
import sys
import urllib.parse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from net import haal as haal_url  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
TZ = ZoneInfo("Europe/Amsterdam")

# Rotterdam centrum. Zie de docstring: één punt voor de hele stad.
LAT, LON = 51.9225, 4.47917
API = "https://api.open-meteo.com/v1/forecast"
VELDEN = ["uur", "neerslag_mm", "wind_kmh", "windstoot_kmh", "temp_c", "zicht_m",
          "sneeuw_cm", "is_dag"]
METINGEN = ["precipitation", "wind_speed_10m", "wind_gusts_10m",
            "temperature_2m", "visibility", "snowfall", "is_day"]

BESTAND = Path(os.environ.get("WEER_BESTAND") or OUT / "weer" / "rotterdam.csv")


def haal(dagen=7):
    """De afgelopen `dagen` plus vandaag, per uur, in lokale tijd."""
    vraag = urllib.parse.urlencode({
        "latitude": LAT, "longitude": LON,
        "hourly": ",".join(METINGEN),
        "past_days": dagen, "forecast_days": 1,
        "timezone": "Europe/Amsterdam",
    })
    h = json.loads(haal_url(f"{API}?{vraag}"))["hourly"]
    uit = {}
    for i, t in enumerate(h["time"]):
        rij = [h[m][i] for m in METINGEN]
        if all(v is None for v in rij):
            continue          # een uur dat nog niet bestaat
        uit[t] = dict(zip(VELDEN[1:], rij))
    return uit


def lees(pad=None):
    """Uren uit een eerder weggeschreven bestand.

    `.get(k, "")` in plaats van `r[k]`: na een schemawijziging (zoals het
    toevoegen van sneeuw en dag/nacht) missen oudere regels de nieuwe kolom.
    Leeg is dan het eerlijke antwoord -- onbekend, niet nul.
    """
    pad = Path(pad or BESTAND)
    if not pad.exists():
        return {}
    with open(pad, newline="") as f:
        return {r["uur"]: {k: r.get(k, "") for k in VELDEN[1:]}
                for r in csv.DictReader(f)}


def schrijf(rijen, pad=None):
    pad = Path(pad or BESTAND)
    pad.parent.mkdir(parents=True, exist_ok=True)
    with open(pad, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(VELDEN)
        for uur in sorted(rijen):
            w.writerow([uur] + [rijen[uur].get(k, "") for k in VELDEN[1:]])


def bij(rijen, moment):
    """Het weer op een meetmoment: het uur waar dat moment in valt.

    Open-Meteo's uurwaarden gelden voor het uur dát begint op dat tijdstip, dus
    een meting van 16:49 hoort bij 16:00. Afronden naar beneden dus.
    """
    if isinstance(moment, str):
        moment = datetime.fromisoformat(moment)
    return rijen.get(moment.astimezone(TZ).strftime("%Y-%m-%dT%H:00"))


def main():
    dagen = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    bestaand = lees()
    nieuw = haal(dagen)
    # Verse waarden winnen: Open-Meteo herziet de afgelopen uren nog.
    samen = {**bestaand, **nieuw}
    schrijf(samen)
    erbij = len(samen) - len(bestaand)
    print(f"weer: {len(samen)} uren in {BESTAND.name} "
          f"({erbij} nieuw, {len(nieuw) - erbij} herzien)")


if __name__ == "__main__":
    main()
