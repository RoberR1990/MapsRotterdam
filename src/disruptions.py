"""Actieve verstoringen uit de NDW-planningsfeed, in twee smaken.

blackouts  -> per NDW-meetlocatie de vensters waarin er vlakbij gewerkt wordt.
              De sampler markeert die metingen, zodat een straat die drie weken
              openligt niet als structurele congestie in de kalibratie belandt.
scenario   -> de punten die op een gegeven moment echt dicht zijn, als invoer
              voor een OSRM-scenariodataset.
"""
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"

# Publieksomschrijvingen die verkeer daadwerkelijk raken. De feed kent ook
# "Geen gevolgen voor verkeer", "Beperking voor langzaam verkeer" en
# "Verboden te parkeren" -- die zeggen niets over autoreistijd.
BLOKKEREND = ("Weg dicht",)
VERTRAGEND = ("Verminderd aantal rijstroken", "Snelheidsbeperking",
              "Omleiding over onderliggend wegennet")

SITE_RADIUS_M = 250      # een meetlus meet een stuk weg, niet een punt
BLOCK_RADIUS_M = 50      # hoe ver rond een afsluitingspunt de weg dicht is

# Werk dat maanden of jaren duurt is voor de kalibratie geen verstoring maar de
# nieuwe normaal: die snelheden zijn precies wat bestuurders daar dagelijks
# ervaren. Alleen kortlopend werk telt als iets om uit te filteren. In de feed
# duurt 11% van de vensters langer dan 90 dagen, met uitschieters boven de vijf
# jaar; die er niet uit halen zou de kalibratie juist optimistisch maken.
MAX_VENSTER_DAGEN = 90


def load():
    p = OUT / "ndw_events_rotterdam.json"
    if not p.exists():
        sys.exit("out/ndw_events_rotterdam.json ontbreekt -- draai eerst src/ndw_events.py")
    return json.loads(p.read_text())["wegwerk_evenementen"]


def ts(t):
    try:
        return datetime.fromisoformat(t.replace("Z", "+00:00")) if t else None
    except ValueError:
        return None


def impact(r):
    o = (r.get("omschrijving") or "")
    if o.startswith(BLOKKEREND):
        return "blokkerend"
    if o.startswith(VERTRAGEND):
        return "vertragend"
    return None


def met_locatie(rows, soorten=("blokkerend", "vertragend"), max_dagen=None):
    uit = [r for r in rows
           if r["lat"] is not None and impact(r) in soorten
           and ts(r["start"]) and ts(r["eind"])]
    if max_dagen:
        uit = [r for r in uit
               if (ts(r["eind"]) - ts(r["start"])).days <= max_dagen]
    return uit


def actief_op(rows, moment, soorten=("blokkerend",)):
    return [r for r in met_locatie(rows, soorten)
            if ts(r["start"]) <= moment <= ts(r["eind"])]


def meters(lat1, lon1, lat2, lon2):
    """Equirectangulaire benadering; op stadsschaal ruim nauwkeurig genoeg."""
    kx = math.cos(math.radians((lat1 + lat2) / 2)) * 111_320
    return math.hypot((lon2 - lon1) * kx, (lat2 - lat1) * 110_540)


def cmd_blackouts():
    rows = met_locatie(load(), max_dagen=MAX_VENSTER_DAGEN)
    sites = json.loads((OUT / "ndw_sites.json").read_text())

    # grofmazig raster zodat we niet elke locatie tegen elke maatregel houden
    cel = 0.004
    grid = {}
    for r in rows:
        grid.setdefault((round(r["lon"] / cel), round(r["lat"] / cel)), []).append(r)

    black, geraakt = {}, 0
    for s in sites:
        gx, gy = round(s["lon"] / cel), round(s["lat"] / cel)
        vensters = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for r in grid.get((gx + dx, gy + dy), ()):
                    if meters(s["lat"], s["lon"], r["lat"], r["lon"]) <= SITE_RADIUS_M:
                        vensters.append([r["start"], r["eind"]])
        if vensters:
            black[s["id"]] = vensters
            geraakt += 1

    (OUT / "ndw_site_blackouts.json").write_text(json.dumps(black, separators=(",", ":")))
    print(f"{len(rows)} kortlopende verstoringen (<= {MAX_VENSTER_DAGEN} dagen) "
          f"met locatie -> {geraakt} van {len(sites)} meetlocaties hebben een venster")
    print(f"   mediaan aantal vensters per geraakte locatie: "
          f"{sorted(len(v) for v in black.values())[geraakt // 2] if geraakt else 0}")
    print("-> out/ndw_site_blackouts.json")


def cmd_scenario(moment_str):
    moment = datetime.fromisoformat(moment_str).replace(tzinfo=timezone.utc)
    rows = load()
    blok = actief_op(rows, moment, ("blokkerend",))
    vert = actief_op(rows, moment, ("vertragend",))
    punten = [{"lon": round(r["lon"], 6), "lat": round(r["lat"], 6),
               "soort": impact(r), "waarom": r["oorzaak"],
               "tot": r["eind"]} for r in blok + vert]
    (OUT / "scenario_punten.json").write_text(json.dumps(
        {"moment": moment.isoformat(), "punten": punten}, separators=(",", ":")))
    print(f"{moment:%d-%m-%Y %H:%M}: {len(blok)} afsluitingen, "
          f"{len(vert)} vertragende maatregelen")
    print("-> out/scenario_punten.json")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "blackouts"
    if cmd == "blackouts":
        cmd_blackouts()
    elif cmd == "scenario":
        cmd_scenario(sys.argv[2] if len(sys.argv) > 2 else datetime.now(timezone.utc).isoformat())
    else:
        sys.exit(f"onbekend commando: {cmd}")
