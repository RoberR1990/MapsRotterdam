"""Schoolvakanties en feestdagen als covariaat bij de NDW-metingen.

De goedkoopste correctie in het hele project. Vakantieverkeer is een ander
verkeersbeeld -- minder woon-werk, minder haal-en-brengverkeer rond scholen --
en als je daar niet voor markeert bak je toevallige vakantiedagen permanent in
de matrix.

Concreet voor dit project: Rotterdam valt onder **regio Midden**, en daar liep
de zomervakantie tot en met zondag 30 augustus 2026. Onze eerste meting is van
1 september, dus alles wat we tot nu toe hebben komt uit de *eerste schoolweek*.
Dat is geen normale week. Zonder deze markering zou dat er niet meer uit te
halen zijn.

Vakantiedata komen van rijksoverheid.nl en staan hier met de hand in: het zijn
vijf regels per schooljaar, ze worden jaren vooruit gepubliceerd en ze
veranderen nooit met terugwerkende kracht. Een API ervoor bestaat niet meer
(de oude opendata.rijksoverheid.nl-endpoint geeft 404). Vul bij een nieuw
schooljaar VAKANTIES aan.

Feestdagen worden wél gerekend, want ze hangen aan Pasen en dat is een formule.
"""
import sys
from datetime import date, timedelta

# Rotterdam = regio Midden. Zuid-Holland wordt niet gesplitst.
REGIO = "midden"

# (naam, eerste dag, laatste dag) -- beide dagen meegerekend.
# Bron: rijksoverheid.nl, overzicht schoolvakanties per schooljaar, regio Midden.
VAKANTIES = [
    ("zomer",      date(2026, 7, 18), date(2026, 8, 30)),
    ("herfst",     date(2026, 10, 17), date(2026, 10, 25)),
    ("kerst",      date(2026, 12, 19), date(2027, 1, 3)),
    ("voorjaar",   date(2027, 2, 20), date(2027, 2, 28)),
    ("mei",        date(2027, 4, 24), date(2027, 5, 2)),
    ("zomer",      date(2027, 7, 17), date(2027, 8, 29)),
]


def pasen(jaar):
    """Eerste paasdag volgens de gregoriaanse rekenwijze (Meeus/Jones/Butcher)."""
    a, b, c = jaar % 19, jaar // 100, jaar % 100
    d, e = b // 4, b % 4
    f, g = (b + 8) // 25, 0
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    maand = (h + l - 7 * m + 114) // 31
    dag = ((h + l - 7 * m + 114) % 31) + 1
    return date(jaar, maand, dag)


def feestdagen(jaar):
    """Landelijke feestdagen. Niet allemaal een vrije dag voor iedereen, maar
    allemaal een ander verkeersbeeld -- en dat is waar het hier om gaat."""
    p = pasen(jaar)
    kon = date(jaar, 4, 27)
    if kon.weekday() == 6:            # op zondag schuift Koningsdag een dag terug
        kon = date(jaar, 4, 26)
    return {
        date(jaar, 1, 1): "nieuwjaarsdag",
        p - timedelta(days=2): "goede vrijdag",
        p: "eerste paasdag",
        p + timedelta(days=1): "tweede paasdag",
        kon: "koningsdag",
        date(jaar, 5, 5): "bevrijdingsdag",
        p + timedelta(days=39): "hemelvaartsdag",
        p + timedelta(days=49): "eerste pinksterdag",
        p + timedelta(days=50): "tweede pinksterdag",
        date(jaar, 12, 25): "eerste kerstdag",
        date(jaar, 12, 26): "tweede kerstdag",
    }


def vakantie_op(d):
    for naam, van, tot in VAKANTIES:
        if van <= d <= tot:
            return naam
    return None


def bij(d):
    """Wat is er bijzonder aan deze dag? Lege waarden als er niets is."""
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    return {"vakantie": vakantie_op(d) or "",
            "feestdag": feestdagen(d.year).get(d, "")}


def schooldagen_sinds_zomer(d):
    """Hoeveelste dag van het schooljaar is dit? None buiten het schooljaar.

    Bedoeld om de aanloop na de zomervakantie zichtbaar te maken: het verkeer in
    de eerste week terug is niet het verkeer van eind september.
    """
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    einden = [tot for naam, _, tot in VAKANTIES if naam == "zomer" and tot < d]
    if not einden:
        return None
    return (d - max(einden)).days


def main():
    d = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
    print(f"{d} (regio {REGIO}): {bij(d)}, "
          f"dag {schooldagen_sinds_zomer(d)} van het schooljaar")


if __name__ == "__main__":
    main()
