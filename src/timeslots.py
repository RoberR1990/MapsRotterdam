"""Tijdvak-definities en congestieparameters.

De kern van het ontwerp: in plaats van de vrije-doorstroommatrix met één getal
te vermenigvuldigen, krijgt elk tijdvak een eigen OSRM-snelheidsprofiel. Dat
verandert ook de *routekeuze* -- in de spits wordt de ring onaantrekkelijk en
kiest het model binnendoor, precies zoals echte bestuurders doen. Een vlakke
vermenigvuldiging kan dat per definitie niet.

LET OP: de factoren hieronder zijn PLAATSHOUDERS, geen metingen. Ze zijn het
kleine parameterblok dat je later kalibreert -- met opgebouwde NDW-data
(src/sample_ndw.py) of met een kleine betaalde steekproef. Alleen deze tabel
verandert dan; de rest van de pijplijn blijft staan.
"""

# per tijdvak: snelheidsfactor per OSM-wegklasse + factor op de kruispuntstraf.
# Stedelijke vertraging zit vooral in wachten bij verkeerslichten, vandaar dat
# turn_penalty apart en sterker schaalt dan de wegsnelheden.
SLOTS = {
    "werkdag_ochtendspits": {  # di-do 07:30-09:00
        "label": "Werkdag ochtendspits (di-do 08:15)",
        "speed": {"motorway": 0.55, "motorway_link": 0.60, "trunk": 0.55,
                  "trunk_link": 0.60, "primary": 0.60, "primary_link": 0.65,
                  "secondary": 0.65, "secondary_link": 0.70, "tertiary": 0.75,
                  "tertiary_link": 0.80, "unclassified": 0.90,
                  "residential": 0.95, "living_street": 1.0, "service": 1.0},
        "turn": 2.6,
    },
    "werkdag_dal": {           # di-do 10:00-15:00
        "label": "Werkdag dal (di-do 11:00)",
        "speed": {"motorway": 0.95, "motorway_link": 0.95, "trunk": 0.92,
                  "trunk_link": 0.92, "primary": 0.85, "primary_link": 0.88,
                  "secondary": 0.85, "secondary_link": 0.88, "tertiary": 0.88,
                  "tertiary_link": 0.90, "unclassified": 0.95,
                  "residential": 0.98, "living_street": 1.0, "service": 1.0},
        "turn": 1.4,
    },
    "werkdag_avondspits": {    # di-do 16:00-18:30
        "label": "Werkdag avondspits (di-do 17:15)",
        "speed": {"motorway": 0.50, "motorway_link": 0.55, "trunk": 0.50,
                  "trunk_link": 0.55, "primary": 0.55, "primary_link": 0.60,
                  "secondary": 0.62, "secondary_link": 0.66, "tertiary": 0.72,
                  "tertiary_link": 0.78, "unclassified": 0.88,
                  "residential": 0.94, "living_street": 1.0, "service": 1.0},
        "turn": 3.0,
    },
    "werkdag_avond": {         # ma-do na 20:00
        "label": "Werkdag avond (21:00)",
        "speed": {k: 1.0 for k in ("motorway", "motorway_link", "trunk",
                                   "trunk_link", "primary", "primary_link",
                                   "secondary", "secondary_link", "tertiary",
                                   "tertiary_link", "unclassified",
                                   "residential", "living_street", "service")},
        "turn": 0.9,
    },
    "weekend_middag": {        # za 12:00-17:00
        "label": "Weekendmiddag (za 14:00)",
        "speed": {"motorway": 0.85, "motorway_link": 0.88, "trunk": 0.82,
                  "trunk_link": 0.85, "primary": 0.75, "primary_link": 0.80,
                  "secondary": 0.75, "secondary_link": 0.80, "tertiary": 0.80,
                  "tertiary_link": 0.85, "unclassified": 0.92,
                  "residential": 0.96, "living_street": 1.0, "service": 1.0},
        "turn": 1.8,
    },
}

# Waar de factoren hieronder vandaan komen. matrix_history.py legt dit vast bij
# elke matrixversie, zodat later terug te zien is welke cijfers geschat waren en
# welke gemeten. Zet bron op "meting" zodra aggregate ze heeft vervangen.
KALIBRATIE = {"bron": "schatting", "datum": None, "metingen": 0,
              "toelichting": "vuistregels voor stadsverkeer, niet voor Rotterdam"}

BASE_PORT = 5001
PORTS = {slot: BASE_PORT + i for i, slot in enumerate(SLOTS)}
