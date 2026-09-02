"""Bouw de gepubliceerde pagina uit site/ plus de laatste gegevens.

De bron stond eerst alleen in een tijdelijke map; die is weg zodra de container
opnieuw start, en dan is de pagina niet meer bij te werken. Nu staat hij in de
repo en zet dit script de gegevens erin.

Het uitvoerpad ligt vast: publiceren naar een ander pad maakt een nieuwe artifact
in plaats van dat het de bestaande bijwerkt. Overschrijf desnoods met PAGE_OUT.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
OUT = ROOT / "out"
DOEL = Path(os.environ.get("PAGE_OUT") or
            "/tmp/claude-0/-home-user-MapsRotterdam/"
            "a1e0fc08-33ff-55b5-9add-532e3474ee62/scratchpad/"
            "rotterdam-reistijdmatrix.html")

GEGEVENS = {
    "__DATA__": "matrix_web_parkzones.json",
    "__PROGRESS__": "progress.json",
    "__COVERAGE__": "ndw_coverage.json",
    "__HISTORY__": "matrix_history_parkzones.json",
}


def main():
    js = (SITE / "app.js").read_text()
    for sleutel, bestand in GEGEVENS.items():
        p = OUT / bestand
        if not p.exists():
            sys.exit(f"{bestand} ontbreekt -- draai eerst het script dat hem maakt")
        js = js.replace(sleutel, p.read_text())
        if sleutel in js:
            sys.exit(f"plaatshouder {sleutel} kwam meer dan een keer voor")

    html = (SITE / "head.html").read_text() + "\n" \
         + (SITE / "body.html").read_text() + "\n" + js
    DOEL.parent.mkdir(parents=True, exist_ok=True)
    DOEL.write_text(html)

    prog = json.loads((OUT / "progress.json").read_text())
    print(f"{DOEL.name}: {len(html)//1024} kB")
    print(f"   stand: {prog['momenten_totaal']} meetmomenten, "
          f"{sum(1 for s in prog['slots'] if s['momenten'] > 0)}/{len(prog['slots'])} "
          f"tijdvakken gestart ({prog['gegenereerd']})")


if __name__ == "__main__":
    main()
