"""Beweegt de gemeten factor nog, of staat hij stil?

De vraag die dit beantwoordt is niet "klopt het" maar "zijn we klaar met meten".
Dat zijn twee verschillende dingen en ze worden makkelijk verward: een schatting
die niet meer beweegt is *uitgeconvergeerd*, niet *juist*. Als de meetmethode
scheef staat, convergeert hij netjes naar het verkeerde getal. Voor de vraag of
de reistijden kloppen is een externe bron nodig; dit gaat alleen over de vraag of
langer doormeten nog iets oplevert.

De rekenwijze: reken de factoren opnieuw alsof het elke dag opnieuw was, met
alleen de data tot en met die dag, en kijk hoe het antwoord zich verplaatst. Zit
de laatste stap onder de drempel, dan voegt een dag extra niets meer toe.

Wat je moet zien is een reeks die uitdempt. Blijft hij springen, dan is drie
losse dagen te weinig voor dat tijdvak en moet de drempel in sample_ndw.py
omhoog -- ook dat is een uitkomst.
"""
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sample_ndw as S  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"

# Onder deze relatieve verandering noemen we een factor stil. 2% op een
# congestiefactor is ruim binnen de ruis van het onderliggende verkeer en ver
# onder wat je in een reistijd van een kwartier zou merken.
DREMPEL = 0.02
MIN_PEILINGEN = 3      # minder dan drie punten is geen reeks


def meetdagen():
    """De dagen waarop gemeten is, oplopend."""
    dagen = set()
    for d in (S.HIST, S.HIST_TT):
        for p in sorted(d.glob("*.csv.gz")):
            dagen.add(p.name.split(".")[0])
    return sorted(dagen)


def reeksen():
    """Per (wegklasse, tijdvak) de factor zoals hij op elke dag zou zijn.

    Een dag telt alleen als peiling als de factor daadwerkelijk verschoof. Reden:
    op een vrijdag komt er niets bij in de di-do-tijdvakken, dus de "peiling" van
    die dag is een herhaling van gisteren. Zulke herhalingen meetellen zou een
    reeks stil laten lijken terwijl er alleen niets gemeten is -- precies de
    verkeerde conclusie.

    De toets is of het getal exact gelijk bleef (op vier decimalen). Dat is een
    benadering: het kan dat er wel data bijkwam en de mediaan toevallig niet
    bewoog. Dan tellen we een echte peiling niet mee, en vragen we dus iets meer
    bewijs dan strikt nodig -- de veilige kant.
    """
    reeks = defaultdict(list)      # sleutel -> [(dag, factor)]
    for dag in meetdagen():
        d = datetime.fromisoformat(dag).date()
        for sleutel, factor in (S.aggregate(tot=d, stil=True) or {}).items():
            if reeks[sleutel] and reeks[sleutel][-1][1] == factor:
                continue
            reeks[sleutel].append((dag, factor))
    return reeks


def oordeel(punten):
    """Staat deze reeks stil? Geeft (staat, laatste stap, totale beweging)."""
    if len(punten) < MIN_PEILINGEN:
        return "te kort", None, None
    waarden = [f for _, f in punten]
    stappen = [abs(waarden[i + 1] - waarden[i]) / waarden[i]
               for i in range(len(waarden) - 1)]
    totaal = abs(waarden[-1] - waarden[0]) / waarden[0]
    staat = "stil" if stappen[-1] < DREMPEL else "beweegt"
    return staat, stappen[-1], totaal


def main():
    reeks = reeksen()
    rijen = []
    for (klasse, slot), punten in sorted(reeks.items()):
        staat, laatste, totaal = oordeel(punten)
        rijen.append({
            "klasse": klasse, "slot": slot, "staat": staat,
            "peilingen": len(punten),
            "laatste_stap": None if laatste is None else round(laatste, 4),
            "totale_beweging": None if totaal is None else round(totaal, 4),
            "reeks": [{"dag": d, "factor": f} for d, f in punten],
        })
    OUT.mkdir(exist_ok=True)
    (OUT / "convergentie.json").write_text(json.dumps(
        {"gegenereerd": datetime.now(S.TZ).isoformat(timespec="minutes"),
         "drempel": DREMPEL, "min_peilingen": MIN_PEILINGEN,
         "reeksen": rijen}, ensure_ascii=False, separators=(",", ":")))

    stil = sum(1 for r in rijen if r["staat"] == "stil")
    print(f"{len(rijen)} reeksen -> out/convergentie.json ({stil} stil)")
    if not rijen:
        print("  nog geen enkele factor bruikbaar -- niets om te volgen")
        return
    print(f"\n{'klasse':<12}{'tijdvak':<24}{'peil':>5}{'laatste':>9}"
          f"{'totaal':>8}  staat")
    for r in rijen:
        laatste = "-" if r["laatste_stap"] is None else f"{r['laatste_stap']:.1%}"
        totaal = "-" if r["totale_beweging"] is None else f"{r['totale_beweging']:.1%}"
        print(f"  {r['klasse']:<10}{r['slot']:<24}{r['peilingen']:>5}"
              f"{laatste:>9}{totaal:>8}  {r['staat']}")
    print(f"\nStil = de laatste dag verschoof de factor minder dan "
          f"{DREMPEL:.0%}. Dat zegt dat langer meten niets meer toevoegt, "
          f"niet dat het getal klopt.")


if __name__ == "__main__":
    main()
