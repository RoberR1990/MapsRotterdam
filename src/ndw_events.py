"""NDW-situatiefeeds (DATEX II) plat slaan: wegwerkzaamheden, afsluitingen,
tijdelijke snelheden, brugopeningen en het actuele beeld.

Elke feed is een SituationPublication. Eén situatie bevat meerdere records --
bijvoorbeeld een afsluiting plus de bijbehorende omleiding. We plukken per
record de dingen eruit die voor een reistijdmatrix uitmaken: waar, wanneer,
hoe lang, waarom, en welke vertraging de wegbeheerder zelf verwacht.
"""
import gzip
import json
import sys
from pathlib import Path
from xml.etree.ElementTree import iterparse

ROOT = Path(__file__).resolve().parent.parent
NDW = ROOT / "data" / "ndw"
OUT = ROOT / "out"
ROTTERDAM_BBOX = (4.28, 51.83, 4.65, 52.00)

FEEDS = {
    "wegwerk_evenementen": "planningsfeed_wegwerkzaamheden_en_evenementen",
    "afsluitingen": "tijdelijke_verkeersmaatregelen_afsluitingen",
    "max_snelheden": "tijdelijke_verkeersmaatregelen_maximum_snelheden",
    "brugopeningen": "planningsfeed_brugopeningen",
    "actueel_beeld": "actueel_beeld",
}


def tag(e):
    return e.tag.rsplit("}", 1)[-1]


def first(el, name):
    for c in el.iter():
        if tag(c) == name:
            return (c.text or "").strip()
    return None


def nested_value(el, name):
    """De tekst onder <name><values><value lang="nl">...; het element zelf is leeg."""
    for c in el.iter():
        if tag(c) == name:
            return first(c, "value")
    return None


def parse(feed_file):
    """Eén record per situationRecord, met de situatie-id erbij."""
    out = []
    with gzip.open(NDW / f"{feed_file}.xml.gz", "rb") as fh:
        sit_id = None
        for ev, el in iterparse(fh, events=("start", "end")):
            if ev == "start" and tag(el) == "situation":
                sit_id = el.get("id")
                continue
            if ev != "end" or tag(el) != "situationRecord":
                continue
            xsi = next((v for k, v in el.attrib.items() if k.endswith("}type")), "")
            lat, lon = first(el, "latitude"), first(el, "longitude")

            # meerdere geldigheidsvensters: zo herken je terugkerende maatregelen
            periods = []
            for c in el.iter():
                if tag(c) == "validPeriod":
                    periods.append((first(c, "startOfPeriod"), first(c, "endOfPeriod")))

            # commentType 'warning' is de publieksomschrijving; de rest is ruis
            warn = ""
            for c in el.iter():
                if tag(c) == "generalPublicComment" and first(c, "commentType") == "warning":
                    warn = first(c, "value") or ""
                    break

            out.append({
                "situatie": sit_id,
                "record": el.get("id"),
                "soort": xsi.rsplit(":", 1)[-1],
                "start": first(el, "overallStartTime"),
                "eind": first(el, "overallEndTime"),
                "perioden": periods,
                "lat": float(lat) if lat else None,
                "lon": float(lon) if lon else None,
                "oorzaak": nested_value(el, "causeDescription") or first(el, "causeType"),
                "oorzaak_type": first(el, "causeType"),
                "vertraging": first(el, "delayBand"),
                "onderhoud": first(el, "roadMaintenanceType") or first(el, "subjectTypeOfWorks"),
                "netwerk": first(el, "generalNetworkManagementType"),
                "snelheid": first(el, "speedValue") or first(el, "temporarySpeedLimit"),
                "omschrijving": warn,
                "wegnummer": first(el, "roadNumber"),
                "plaats": nested_value(el, "supplementaryPositionalDescription"),
            })
            el.clear()
    return out


def in_rotterdam(r):
    lo_x, lo_y, hi_x, hi_y = ROTTERDAM_BBOX
    return (r["lat"] is not None
            and lo_x <= r["lon"] <= hi_x and lo_y <= r["lat"] <= hi_y)


def download(bestand):
    """Feeds staan niet in git; haal ze op als ze er niet zijn."""
    import urllib.request
    NDW.mkdir(parents=True, exist_ok=True)
    doel = NDW / f"{bestand}.xml.gz"
    with urllib.request.urlopen(f"https://opendata.ndw.nu/{bestand}.xml.gz",
                                timeout=300) as r:
        doel.write_bytes(r.read())
    return doel


def main(feeds=None):
    alles = {}
    for naam, bestand in (feeds or FEEDS).items():
        if not (NDW / f"{bestand}.xml.gz").exists():
            print(f"  {naam}: ophalen...")
            download(bestand)
        rows = parse(bestand)
        rot = [r for r in rows if in_rotterdam(r)]
        zonder = sum(1 for r in rows if r["lat"] is None)
        alles[naam] = rot
        print(f"  {naam:<22} {len(rows):>5} records landelijk, "
              f"{len(rot):>4} in de regio Rotterdam "
              f"({zonder} zonder coordinaten)")
    OUT.mkdir(exist_ok=True)
    (OUT / "ndw_events_rotterdam.json").write_text(json.dumps(alles, separators=(",", ":")))
    print(f"\n-> out/ndw_events_rotterdam.json")
    return alles


if __name__ == "__main__":
    main()
