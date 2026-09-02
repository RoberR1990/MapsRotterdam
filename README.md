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

## Tijdvakken

Dinsdag t/m donderdag houdt smalle vensters aan (ochtendspits 07:30-09:00, dal
10:00-15:00, avondspits 16:00-18:30, avond 20:00-23:00) -- schoudertijd erbij
zou het spitsbeeld verdunnen.

Maandag en vrijdag krijgen **eigen** tijdvakken over de volle dag, 06:00-23:00
zonder gaten: `maandag_vroeg` / `_ochtendspits` / `_dal` / `_avondspits` /
`_avond`, en idem voor vrijdag. Die dagen wijken af van een doordeweekse di-do
-- de maandagochtend is rustiger, de vrijdagmiddag drukker -- en door ze apart
te labelen houd je beide opties open: uit aparte reeksen kun je later alsnog een
gecombineerd ma-vr cijfer rekenen, andersom niet.

### Voortgang bekijken

    NDW_HISTORY_DIR=/pad/naar/ndw-data/ndw_history python3 src/progress.py

Leidt het meetrooster af uit `slot_of` -- afgetast in plaats van overgetypt, dus
rooster en code kunnen niet uit elkaar lopen -- en zet dat samen met de stand van
de historie in `out/progress.json` voor de webweergave.

De dunne tijdvakken bepalen het tempo: `maandag_vroeg` en `vrijdag_vroeg` krijgen
maar een meting per week en hebben dus vijf weken nodig voor de ondergrens van
vijf, terwijl `werkdag_dal` er vijftien per week binnenhaalt.

## Waar draait de sampler?

Niet in een chat-sessie en niet op je laptop: `.github/workflows/ndw-sampler.yml`
draait op **GitHub Actions**. Deze repo is publiek, dus Actions-minuten zijn gratis
en ongelimiteerd. Elk half uur haalt de workflow het NDW-beeld op en schrijft de
meting naar een aparte branch `ndw-data`, zodat de geschiedenis van `main` schoon
blijft.

- **Cadans** — elk half uur. Op elk kwartier begonnen, maar GitHub voerde die
  planning anderhalf uur lang geen enkele keer uit; korte intervallen worden bij
  drukte als eerste overgeslagen. Een half uur levert nog 9 metingen per week per
  meetlocatie in de ochtendspits, en `aggregate` heeft er 5 nodig. De tijdvakken
  blijven dus even smal -- ze verbreden zou de spits juist verdunnen.
- **Buiten de tijdvakken doet de run niets.** Dat scheelt ~40% van de schrijfacties.
  Ongeveer 150 kB per dag, dus na drie weken zo'n 3 MB.
- **Tijdzone.** De tijdvakken zijn Rotterdamse kloktijd, expliciet vastgelegd met
  `ZoneInfo("Europe/Amsterdam")`. Een CI-runner staat op UTC en zou anders alles een
  of twee uur verschuiven -- in de zomer belandt de avondspits dan in het dal.
- **De GitHub-scheduler doet het hier niet.** Drie cron-varianten geprobeerd
  (`*/15`, `*/30` en `7,37` -- die laatste juist weg van het drukke hele uur),
  over 3,5 uur geen enkele run met `event=schedule`, terwijl handmatig dispatchen
  elke keer werkt. De workflow staat op `active` en op de default branch, dus aan
  de opzet ligt het niet. De cron blijft staan voor het geval GitHub alsnog
  aanslaat -- dubbele metingen zijn onschadelijk.

- **Voorlopige oplossing: `src/collect_standalone.sh`.** Doet hetzelfde werk
  zonder Actions -- databranch als worktree, meten, committen, pushen -- vanaf
  elke machine die de repo kan pushen. Wordt aangeroepen door twee
  Claude-routines, met een cron die alleen op de uren vuurt die een tijdvak
  raken (80 van de 168 uren in een week; de rest was pure verspilling):

      di-do      48 5,6,8,9,10,11,12,14,15,18,19,20 * * 2-4   (UTC)
      ma en vr   48 4-20 * * 1,5                              (UTC)
      weekend    48 10,11,12,13,14 * * 0,6                    (UTC)

  ⚠️ Die uren zijn UTC en gaan uit van zomertijd. Na de overgang naar wintertijd
  (25 oktober) schuiven ze een uur ten opzichte van de tijdvakken, die in
  `Europe/Amsterdam` staan. Loopt het verzamelen dan nog, trek er een uur af.

- **Beter: een crontab-regel.** Elk uur via een routine is duur en levert maar
  drie metingen per week in de ochtendspits. Eén regel op een machine die toch
  aanstaat is goedkoper en dichter:

      */30 * * * * /pad/naar/MapsRotterdam/src/collect_standalone.sh

  Zet die neer en de routine kan uit.

## Hoe representatief zijn de meetpunten?

`src/ndw_coverage.py` meet niet hoeveel meetpunten er zijn maar **welk deel van de
werkelijk gereden meters** een meldend meetpunt binnen 150 m heeft, over 400
willekeurige zoneparen. Uitkomst: **21%**.

| wegklasse | aandeel van de rit | dekking |
|---|---|---|
| stadsroute (S100-S123) | 44% | 26% |
| gewone straat | 41% | 13% |
| snelweg (A16, A20) | 14% | 27% |

Twee dingen die dit blootlegt:

- Van de 5.969 meetpunten in de regio melden er maar **465** een snelheid in de
  open feed, en dat zijn **allemaal inductielussen**. De punten die met floating
  car data werken -- vooral langs de snelwegen -- publiceren daar niets. Van de 440
  snelwegpunten melden er acht.
- Het `naam`-veld van NDW is **niet de wegnaam** maar het soort meetapparaat
  (`lus`, `fcd`, `anpr`, meer smaken zijn er niet). `road_class()` keek daarnaar en
  gaf dus altijd "urban" terug; het wegnummer zit wél in de meetpunt-id.

Gevolg: de stedelijke factoren zijn te kalibreren, de snelwegfactoren niet. Wil je
die ook gemeten hebben, dan is een tweede bron nodig.

## Van schatting naar meting

`src/matrix_history.py` legt bij elke factorwijziging een versie vast: mediaan en
p90 per tijdvak, plus of de factoren geschat of gemeten waren. Een vingerafdruk van
de factortabel voorkomt dubbele versies. Zo blijft zichtbaar wat de kalibratie
precies verschoven heeft.

## Verstoringen: werkzaamheden en afsluitingen

NDW publiceert ook de geplande wegwerkzaamheden, evenementen en afsluitingen
(DATEX II, gratis). Voor de regio Rotterdam zitten daar ~2.300 records in, samen
1.463 unieke maatregelen, met locatie, geldigheidsvensters, oorzaak en de
vertraging die de wegbeheerder zelf verwacht. Drie toepassingen, alle drie
ingebouwd:

1. **Kalibratie schoonhouden.** 1.472 van de 5.969 meetlocaties liggen binnen
   250 m van een kortlopende verstoring. Zonder filter bak je een straat die drie
   weken openligt in als structurele congestie. `disruptions.py blackouts` maakt
   per meetlocatie de vensters; de sampler zet er een kolom `verstoord` bij en
   `aggregate` slaat die rijen over. In een losse meting ging het om 47 van de
   442 metingen.

   Alleen werk korter dan 90 dagen telt mee. 11% van de vensters loopt langer,
   tot 1.946 dagen -- dat is geen verstoring meer maar de nieuwe normaal, en die
   snelheden eruit filteren zou de kalibratie juist te optimistisch maken.
2. **Scenariomatrix "zoals het nu is".** `build_scenario.py` bouwt een
   OSRM-dataset waarin wegvakken vlak bij een afsluiting onbegaanbaar duur zijn,
   via een eigen `process_segment`-handler. Op 1 september (150 afsluitingen)
   verschilt 35% van de zoneparen noemenswaardig van het normale beeld, en 128
   paren hebben geen redelijk alternatief.
3. **Vooruitkijken.** Dezelfde aanroep met een datum in de toekomst; de
   planningsfeed loopt maanden vooruit. Voor 15 oktober: 80 afsluitingen, 28%
   van de paren anders.

```bash
python3 src/ndw_events.py                    # feeds ophalen en plat slaan
python3 src/disruptions.py blackouts         # -> out/ndw_site_blackouts.json
python3 src/build_scenario.py 2026-10-15T08:15 werkdag_ochtendspits
```

Twee dingen om te weten. **De helft van de records landelijk heeft geen
coordinaten** (30.520 van 59.208) en gebruikt alleen een RIS-index- of
AlertC-locatiecode; het Rotterdamse aantal is dus een ondergrens. Op te lossen
met de VILD-locatietabel, ook gratis. En **de afname over de tijd in de feed is
geen seizoenspatroon** maar een planningshorizon: verder weg is nog niet
geregistreerd.

De brugopeningenfeed is voor Rotterdam onbruikbaar -- die is Amsterdam, Alkmaar,
Haarlem en Zaanstad, met precies een punt in de Rotterdam-bbox.

## Pijplijn

```
src/zones.py           subbuurten -> buurtzones + kandidaatpunten
src/parkzones.py       RDW-parkeergebieden -> 99 zones + kandidaatpunten
src/osrm_build.sh      OSRM-graaf uit het OSM-extract
src/matrix.py          vrije-doorstroommatrix (referentie)
src/timeslots.py       tijdvakken + congestiefactoren   <- hier kalibreer je
src/build_slots.py     per tijdvak een eigen OSRM-dataset + router
src/build_matrices.py  alle matrices -> out/matrix_all_<set>.csv + webexport
src/ndw.py             NDW-meetlocaties en -snelheden
src/progress.py        meetrooster en voortgang -> out/progress.json
src/ndw_coverage.py    dekking van de meetpunten over de echte routes
src/matrix_history.py  matrixversies vastleggen -> out/matrix_history_*.json
src/ndw_events.py      NDW-situatiefeeds (werkzaamheden, afsluitingen, bruggen)
src/disruptions.py     blackouts voor de sampler / punten voor een scenario
src/build_scenario.py  scenariomatrix voor een moment, met afsluitingen
src/sample_ndw.py      collect (CI) / aggregate -> gemeten factoren
.github/workflows/     sampler (elk half uur) + verstoringen (dagelijks)
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

Beide zone-sets lopen door dezelfde code; het argument kiest welke:
`zones` (73 buurten) of `parkzones` (99 RDW-parkeergebieden). Uitvoer krijgt de
set als achtervoegsel, dus `out/matrix_all_parkzones.csv`.

Afhankelijkheden: Docker, `pip install pyproj shapely requests`.
De OSM-, RDW- en NDW-downloads staan niet in git (`data/`).
