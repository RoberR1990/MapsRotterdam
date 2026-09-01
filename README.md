# Reistijdmatrix Rotterdamse parkeerzones

Zone-naar-zone rijtijden voor meerdere momenten in de week, gebouwd op
uitsluitend gratis en open componenten. Prototype op 73 buurten; schaalt
ongewijzigd door naar de 100 parkeerzones.

## Resultaat

73 zones, 5.329 cellen per tijdvak, 6 tijdvakken -> `out/matrix_all.csv`.

| tijdvak | mediane rit | p90 |
|---|---|---|
| vrije doorstroom (referentie) | 12,3 min | 19,2 min |
| werkdag ochtendspits | 18,4 min | 30,1 min |
| werkdag dal | 13,8 min | 21,5 min |
| werkdag avondspits | 19,5 min | 32,4 min |
| werkdag avond | 12,2 min | 19,2 min |
| weekendmiddag | 15,3 min | 23,9 min |

De spitsopslag loopt van x1,16 tot x1,93 per zonepaar (mediaan x1,60). Die
spreiding is het punt: korte ritten binnen Noord lopen nauwelijks op, ritten
die de ring of de Maas gebruiken verdubbelen bijna.

## Wat is gratis en werkt

- **Wegennet** — OSM-extract van Rotterdam (BBBike), self-hosted OSRM. Geen
  sleutel, geen limiet, geen kosten. De volledige 73x73 matrix duurt 2 seconden.
- **Zones** — `Subbuurten_vlakken.json`, gedissolveerd naar buurten,
  RD New (EPSG:28992) -> WGS84.
- **Representatiepunten** — 3 per zone, gesnapt op het wegennet
  (mediane snap-afstand 15 m). Zone-paar = mediaan over de 9 puntparen.
- **Verkeersdata** — NDW open data, gratis en zonder sleutel. 5.969
  meetlocaties in de regio Rotterdam.

## Wat gratis *niet* geeft

Historisch verkeer per moment van de week. NDW publiceert open alleen het
*actuele* beeld; historie zit achter een (gratis) Dexter-account. Daarom:
`src/sample_ndw.py collect` als cron elke 5 minuten, en na 2-3 weken heb je een
echt weekprofiel. De factoren in `src/timeslots.py` zijn tot dat moment
**plaatshouders, geen metingen**.

## Pijplijn

```
src/zones.py           polygonen -> zones + kandidaatpunten
src/osrm_build.sh      OSRM-graaf uit het OSM-extract
src/matrix.py          vrije-doorstroommatrix (referentie)
src/timeslots.py       tijdvakken + congestiefactoren   <- hier kalibreer je
src/build_slots.py     per tijdvak een eigen OSRM-dataset + router
src/build_matrices.py  alle matrices -> out/matrix_all.csv
src/ndw.py             NDW-meetlocaties en -snelheden
src/sample_ndw.py      collect (cron) / aggregate -> gemeten factoren
```

## Ontwerpkeuze: profiel per tijdvak, geen vermenigvuldiging

Elk tijdvak krijgt een eigen OSRM-dataset met geschaalde wegsnelheden, niet een
factor over de vrije-doorstroommatrix. Daardoor verandert ook de *routekeuze*:
bij congestie wordt de ring onaantrekkelijk en kiest het model binnendoor. Dat
gebeurt in dit prototype bij een deel van de zoneparen, niet bij alle -- met
gekalibreerde factoren die sterker per wegklasse verschillen wordt dat effect
groter.

Let op: `WayHandlers.maxspeed` in het car-profiel overschrijft de
klassesnelheden met de OSM-tag, en in Nederland is bijna elke weg getagd.
Het schalen van de `speeds`-tabel had daardoor vrijwel geen effect (x1,06 in de
spits). De congestiefactor hangt daarom als eigen handler achter de keten, vlak
voor `weights`, en werkt op de definitieve snelheid.

## Draaien

```bash
python3 src/zones.py
src/osrm_build.sh
docker run -d --name osrm-rtm -p 5000:5000 -v "$PWD/data/osm:/data" \
  ghcr.io/project-osrm/osrm-backend osrm-routed --algorithm mld \
  --max-table-size 4000 /data/Rotterdam.osrm
python3 src/matrix.py
python3 src/build_slots.py
python3 src/build_matrices.py
```

Afhankelijkheden: Docker, `pip install pyproj shapely requests`.
De OSM- en NDW-downloads staan niet in git (`data/`).
