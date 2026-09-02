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

### Wanneer is een tijdvak bruikbaar?

Niet bij genoeg metingen, maar bij genoeg **losse dagen**. Nagerekend op de eerste
dag data (363 meetpunten met 7 momenten in `werkdag_avond`):

| momenten per meetpunt | afwijking per punt | afwijking klassemediaan |
|---|---|---|
| 1 | 4,5% (p90 16,5%) | 1,3% |
| 3 | 2,4% (p90 10,3%) | 1,1% |
| 5 | 1,5% (p90 7,2%) | 1,1% |

De klassemediaan -- het getal dat werkelijk in `timeslots.py` belandt -- is een
mediaan over honderden meetpunten en zit al na één moment binnen ~1%. Ruis binnen
een moment is dus het probleem niet. Wat we niet weten is hoe dinsdag van donderdag
verschilt, en die week van de volgende: daar helpen tien metingen op dezelfde avond
niets tegen. Vandaar `MIN_DAGEN = 3` naast `MIN_METINGEN = 5`.

Gevolg voor het tempo: di-do haalt 3 dagen per week en is na een week rond, weekend
na anderhalve week, maar **maandag en vrijdag worden maar 1x per week gemeten en
hebben dus 3 weken nodig**. Die bepalen wanneer alles klaar is.

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
willekeurige zoneparen.

Op alleen de snelheidsfeed was dat **21%**, met de snelweg vrijwel onbedekt. Er
blijkt echter een tweede open feed te zijn, `traveltime.xml.gz`, met reistijden per
traject -- en die dekt de snelwegen wél. Met beide samen:

| wegklasse | aandeel van de rit | alleen snelheden | beide feeds |
|---|---|---|---|
| stadsroute (S100-S123) | 44% | 26% | **68%** |
| gewone straat | 41% | 13% | **48%** |
| snelweg (A16, A20) | 14% | 27% | **94%** |
| **totaal** | | **21%** | **64%** |

Meldende meetpunten: 465 -> ruim 3.000.

Twee dingen die dit blootlegde:

- De snelheidsfeed bevat in deze regio **alleen inductielussen**; van de 440
  snelwegpunten meldde er acht. De feeds vullen elkaar aan en je hebt ze allebei
  nodig -- op één ervan bouwen geeft een vertekend beeld.
- Het `naam`-veld van NDW is **niet de wegnaam** maar het soort meetapparaat
  (`lus`, `fcd`, `anpr`, meer smaken zijn er niet). `road_class()` keek daarnaar en
  gaf dus altijd "urban" terug; het wegnummer zit wél in de meetpunt-id.

Reistijden worden omgekeerd genomen (1/duur) zodat ze net als een snelheid
meestijgen; er worden alleen verhoudingen gebruikt, dus de eenheid doet er niet
toe. Ze gaan in een eigen dagbestand `ndw_traveltime/`, niet in het
snelheidsbestand -- seconden en km/u door elkaar mengen vraagt om ongelukken.

## Wat de eerste dag meten liet zien

`src/dagprofiel.py` deelt elke gemeten reistijd door de snelste waarneming van
diezelfde dag op datzelfde traject, zodat de lengte van het traject niet meetelt.
2.625 trajecten, woensdag 2 september, 14:48-22:48:

| tijd | snelweg | provinciaal | stedelijk |
|---|---|---|---|
| 14:48 | x1,11 | x1,15 | x1,13 |
| **16:49** | **x1,41** | x1,19 | x1,25 |
| 17:49 | x1,17 | x1,16 | x1,16 |
| 20:49 | x1,04 | x1,06 | x1,05 |
| 22:48 | x1,02 | x1,01 | x1,01 |

Op het drukste moment, met de plaatshouder ernaast:

| wegklasse | mediaan | p75 | p90 | plaatshouder |
|---|---|---|---|---|
| snelweg | x1,41 | x2,34 | x3,78 | x2,00 |
| provinciaal | x1,19 | x1,41 | x1,95 | x2,00 |
| stedelijk | x1,25 | x1,71 | x2,83 | x1,61 |

**Congestie is geen enkel getal.** Het model rekent met een factor per wegklasse,
en dat vangt de middenmoot maar mist de staart volledig: op de snelweg loopt de
helft x1,41 uit, een kwart meer dan x2,3, een tiende meer dan x3,8. De
plaatshouder zit te hoog voor de gewone rit en veel te laag voor de slechte. Wie
op deze matrix plant heeft naast de mediaan een p90-variant nodig -- dat is een
tweede set factoren uit dezelfde metingen, geen tweede meetopzet.

Twee dingen die ik hierbij fout had. De extremen (tot x22 op de verbindingen bij
het Terbregseplein) leken een artefact van korte trajecten, maar korte trajecten
zijn maar 5% van het totale tijdverlies en juist de *lange* trajecten hebben de
hoogste mediaan (x1,42 boven 120 s vrije duur tegen x1,18 eronder). En uit één dag
is een normale spits niet van een incident te onderscheiden; dat 47% van de
snelwegtrajecten om 16:49 boven x1,5 zat wijst op een brede spits, maar zeker is
dat pas na meer dagen.

## Van schatting naar meting

`src/matrix_history.py` legt bij elke factorwijziging een versie vast: mediaan en
p90 per tijdvak, plus of de factoren geschat of gemeten waren. Een vingerafdruk van
de factortabel voorkomt dubbele versies. Zo blijft zichtbaar wat de kalibratie
precies verschoven heeft.

## De gepubliceerde pagina

De bron staat in `site/` (head.html, body.html, app.js). `src/build_page.py` zet de
laatste gegevens erin en schrijft het bestand naar het vaste pad waar de artifact
op gepubliceerd is -- publiceren naar een ander pad maakt een nieuwe pagina in
plaats van dat het de bestaande bijwerkt.

    NDW_HISTORY_DIR=/pad/naar/ndw_history python3 src/progress.py
    python3 src/build_page.py

De pagina is een **momentopname**: hij haalt zelf niets op. Een dagelijkse routine
draait deze twee stappen en publiceert opnieuw.

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
site/ + build_page.py  bron van de gepubliceerde pagina, met de data erin
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
