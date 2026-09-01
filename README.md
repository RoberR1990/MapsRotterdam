# Reistijdmatrix Rotterdamse parkeerzones

Zone-naar-zone rijtijden voor meerdere momenten in de week, gebouwd op
uitsluitend gratis en open componenten. Prototype op 73 buurten; schaalt
ongewijzigd door naar de 100 parkeerzones.

## Resultaat

99 echte parkeerzones uit het Nationaal Parkeer Register, 9.801 cellen per tijdvak,
6 tijdvakken -> `out/matrix_all_parkzones.csv`. Dezelfde pijplijn draait ook op 73
buurten (`out/matrix_all_zones.csv`) als bredere referentie.

### Zones

De 124 betaald-parkeergebieden (`usageid=BETAALDP`) van gemeente Rotterdam
(`areamanagerid=599`) uit de RDW-datasets PARKEERGEBIED, GEOMETRIE GEBIED en
SPECIFICATIES -- gratis open data, geen sleutel. Met een ondergrens van 1 ha blijven
er **99** over; daaronder is een gebied een enkel straatblok en wordt bemonsteren met
meerdere punten zinloos. Wil je je eigen lijst gebruiken: vervang `src/parkzones.py`,
de rest van de pijplijn hangt alleen aan `out/parkzones.geojson`.

### Reistijden (99 parkeerzones)

| tijdvak | mediane rit | p90 |
|---|---|---|
| vrije doorstroom (referentie) | 9,4 min | 14,5 min |
| werkdag ochtendspits | 13,8 min | 22,3 min |
| werkdag dal | 10,7 min | 16,4 min |
| werkdag avondspits | 14,6 min | 23,8 min |
| werkdag avond | 9,4 min | 14,5 min |
| weekendmiddag | 11,8 min | 18,2 min |

Spitsopslag x1,15 tot x1,94 per zonepaar (mediaan x1,56).

<details><summary>73 buurtzones, ter vergelijking</summary>

| tijdvak | mediane rit | p90 |
|---|---|---|
| vrije doorstroom (referentie) | 12,3 min | 19,2 min |
| werkdag ochtendspits | 18,4 min | 30,1 min |
| werkdag dal | 13,8 min | 21,5 min |
| werkdag avondspits | 19,5 min | 32,4 min |
| werkdag avond | 12,2 min | 19,2 min |
| weekendmiddag | 15,3 min | 23,9 min |

De spitsopslag loopt van x1,16 tot x1,93 per zonepaar (mediaan x1,60).

</details>

Die spreiding is het punt: korte ritten binnen een wijk lopen nauwelijks op, ritten
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

## Waar draait de sampler?

Niet in een chat-sessie en niet op je laptop: `.github/workflows/ndw-sampler.yml`
draait op **GitHub Actions**. Deze repo is publiek, dus Actions-minuten zijn gratis
en ongelimiteerd. Elke 15 minuten haalt de workflow het NDW-beeld op en schrijft de
meting naar een aparte branch `ndw-data`, zodat de geschiedenis van `main` schoon
blijft.

- **Cadans** — NDW publiceert elke minuut; 15 minuten is dus ruim binnen wat netjes
  is en levert alsnog 18 metingen per week per meetlocatie in de ochtendspits.
- **Buiten de tijdvakken doet de run niets.** Dat scheelt ~40% van de schrijfacties.
  Ongeveer 150 kB per dag, dus na drie weken zo'n 3 MB.
- **Tijdzone.** De tijdvakken zijn Rotterdamse kloktijd, expliciet vastgelegd met
  `ZoneInfo("Europe/Amsterdam")`. Een CI-runner staat op UTC en zou anders alles een
  of twee uur verschuiven -- in de zomer belandt de avondspits dan in het dal.
- **Kanttekening.** GitHub schakelt geplande workflows uit na 60 dagen zonder
  repo-activiteit, en geplande runs kunnen bij drukte een paar minuten later komen.
  Voor een weekprofiel maakt dat niets uit. Wil je het strakker, draai dan dezelfde
  `sample_ndw.py collect` in een gewone crontab op een machine die altijd aanstaat.

## Pijplijn

```
src/zones.py           subbuurten -> buurtzones + kandidaatpunten
src/parkzones.py       RDW-parkeergebieden -> 99 zones + kandidaatpunten
src/osrm_build.sh      OSRM-graaf uit het OSM-extract
src/matrix.py          vrije-doorstroommatrix (referentie)
src/timeslots.py       tijdvakken + congestiefactoren   <- hier kalibreer je
src/build_slots.py     per tijdvak een eigen OSRM-dataset + router
src/build_matrices.py  alle matrices -> out/matrix_all.csv
src/ndw.py             NDW-meetlocaties en -snelheden
src/sample_ndw.py      collect (CI) / aggregate -> gemeten factoren
.github/workflows/     de sampler, elke 15 min op GitHub Actions
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
python3 src/parkzones.py            # of src/zones.py voor de buurtvariant
python3 src/matrix.py parkzones
python3 src/build_slots.py
python3 src/build_matrices.py parkzones
```

Afhankelijkheden: Docker, `pip install pyproj shapely requests`.
De OSM- en NDW-downloads staan niet in git (`data/`).
