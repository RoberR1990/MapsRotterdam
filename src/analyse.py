"""Wat onderzoeken we, en hoe ver staat het?

Losse analyses staan verspreid over de modules -- weer in covariaten, dekking in
ndw_coverage, het dagprofiel in dagprofiel. Prima om mee te rekenen, maar niet
om iemand mee bij te praten: je kunt niet zien wat er loopt, wat eruit kwam en
wat het waard is.

Dit brengt ze onder één noemer: elke analyse is een **vraag** met een methode,
een stand en, als hij er is, een uitkomst. Ook de vragen die nog niets hebben
opgeleverd staan erin -- dat is het punt. "We weten het nog niet en dit is
waarom" is een uitkomst waar een stakeholder iets aan heeft; hem weglaten wekt
de indruk dat er alleen maar successen zijn.

Schrijft out/analyse.json voor de webpagina.
"""
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import covariaten as COV  # noqa: E402
from sample_ndw import MIN_DAGEN, TZ  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"

# Elke analyse: waarom hij er is, hoe hij gerekend wordt, en waar hij aan vastzit.
# De uitkomst komt uit de data; dit is alleen wat een getal betekent.
VRAGEN = [
    {
        "id": "nat",
        "kenmerk": "nat",
        "titel": "Hoeveel kost regen aan reistijd?",
        "waarom": "Regende het toevallig tijdens de spitsen die we gemeten hebben, "
                  "dan zit dat permanent in de matrix. En andersom: op een natte dag "
                  "wil je de matrix kunnen opplussen.",
        "methode": "Elke meetlocatie met zichzelf vergeleken, binnen hetzelfde "
                   "tijdvak: hoeveel langzamer bij ≥0,5 mm neerslag in het uur dan "
                   "bij droog. Vaste verschillen tussen wegen vallen zo weg.",
        "haak": "De steekproef is het aantal buien, niet het aantal meetlussen. "
                "Duizend lussen tijdens dezelfde bui blijven één bui.",
    },
    {
        "id": "evenement",
        "kenmerk": "evenement",
        "titel": "Wat doet een evenement met de omgeving?",
        "waarom": "Rotterdam heeft veel evenementen met wegafsluitingen. Als die in "
                  "de meetweek vallen kleuren ze het tijdvak, terwijl ze geen "
                  "structureel patroon zijn.",
        "methode": "Per meetlocatie: loopt er binnen 500 m een evenement met "
                   "verkeersgevolg? Zo ja, hoeveel langzamer dan diezelfde locatie "
                   "in hetzelfde tijdvak zonder evenement.",
        "haak": "Plaatsgebonden gerekend. Op stadsniveau („ergens loopt iets”) "
                "kwam er 1,00 uit -- een markt in Hoogvliet doet niets met de "
                "Maastunnel.",
    },
    {
        "id": "matrixbord",
        "kenmerk": "matrixbord",
        "titel": "Verklaren de matrixborden de uitschieters op de snelweg?",
        "waarom": "Een snelwegtraject dat ineens drie keer zo lang doet is meestal "
                  "geen structurele congestie maar een afgekruiste rijstrook. Die "
                  "hoort niet in het weekprofiel.",
        "methode": "Per snelwegtraject gekoppeld op weg, rijbaan en hectometer: "
                   "stond er op dat moment een verlaagde snelheid of een rood kruis "
                   "boven precies dat stuk?",
        "haak": "Alleen te beantwoorden voor de 445 trajecten met een hectometer in "
                "hun id. Voor stadswegen blijft het onbekend, en dat telt niet als "
                "„geen bord”.",
    },
    {
        "id": "wind",
        "kenmerk": "wind",
        "titel": "Doet harde wind iets?",
        "waarom": "Op de bruggen en de Van Brienenoord is windhinder een reden voor "
                  "snelheidsbeperking. De vraag is of het in het stadsbeeld terug te "
                  "zien is.",
        "methode": "Zelfde opzet als bij regen, met windstoten vanaf 60 km/u als "
                   "kenmerk.",
        "haak": "Verwachting is dat dit niets oplevert buiten de bruggen om; dan is "
                "dat ook het antwoord.",
    },
    {
        "id": "vakantie",
        "kenmerk": "vakantie",
        "titel": "Hoeveel rustiger is een schoolvakantie?",
        "waarom": "De zomervakantie in regio Midden liep tot en met 30 augustus. "
                  "Onze eerste meetweek is dus de eerste schoolweek -- geen normale "
                  "week. Zonder deze correctie bakken we die aanloop in de matrix.",
        "methode": "Zelfde opzet: dezelfde locatie in hetzelfde tijdvak, vakantie "
                   "tegen schoolweek.",
        "haak": "Vraagt een meetreeks die over een vakantie heen loopt. De eerste "
                "kans is de herfstvakantie, 17-25 oktober.",
    },
]


def stand(kenmerk):
    """De uitkomst van één analyse, of waarom hij er nog niet is."""
    ratios, per_klasse, m_met, m_zonder = COV.effect(kenmerk)
    uit = {"momenten_met": len(m_met), "momenten_zonder": len(m_zonder),
           "paren": len(ratios), "min_momenten": COV.MIN_MOMENTEN}
    if min(len(m_met), len(m_zonder)) < COV.MIN_MOMENTEN:
        uit["staat"] = "wacht"
        uit["stand"] = (f"{len(m_met)} van de {COV.MIN_MOMENTEN} benodigde momenten"
                        if len(m_met) < COV.MIN_MOMENTEN
                        else "te weinig vergelijkingsmomenten")
        return uit
    if len(ratios) < COV.MIN_PAREN:
        uit["staat"] = "wacht"
        uit["stand"] = f"{len(ratios)} paren, {COV.MIN_PAREN} nodig"
        return uit
    ratios.sort()
    uit["staat"] = "eerste uitkomst"
    uit["factor"] = round(statistics.median(ratios), 3)
    uit["p25"] = round(ratios[len(ratios) // 4], 3)
    uit["p75"] = round(ratios[3 * len(ratios) // 4], 3)
    uit["klassen"] = {k: round(statistics.median(v), 3)
                      for k, v in sorted(per_klasse.items())
                      if len(v) >= COV.MIN_PAREN}
    return uit


def main():
    rijen = []
    for v in VRAGEN:
        s = stand(v["kenmerk"])
        rijen.append({**{k: v[k] for k in
                         ("id", "titel", "waarom", "methode", "haak")}, **s})
    data = {
        "gegenereerd": datetime.now(TZ).isoformat(timespec="minutes"),
        "min_dagen": MIN_DAGEN,
        "analyses": rijen,
    }
    OUT.mkdir(exist_ok=True)
    (OUT / "analyse.json").write_text(json.dumps(data, ensure_ascii=False,
                                                 separators=(",", ":")))
    klaar = sum(1 for r in rijen if r["staat"] != "wacht")
    print(f"{len(rijen)} analyses -> out/analyse.json ({klaar} met een uitkomst)")
    for r in rijen:
        kern = (f"×{r['factor']:.3f} (p25 {r['p25']:.2f}, p75 {r['p75']:.2f})"
                if r["staat"] != "wacht" else r["stand"])
        print(f"  {r['staat']:<16} {r['id']:<12} {kern}")


if __name__ == "__main__":
    main()
