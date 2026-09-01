"""Reistijdmatrix voor een concreet moment, mét de dan geldende afsluitingen.

Zelfde truc als de tijdvakken, één laag erbovenop: een process_segment-handler
die wegvakken vlak bij een afsluitingspunt onbegaanbaar duur maakt. Daarmee
krijg je zowel "zoals het nu is" als "zoals het er over een maand uitziet",
want de planningsfeed loopt maanden vooruit.

    python3 src/build_scenario.py 2026-09-01T17:00            # nu
    python3 src/build_scenario.py 2026-10-15T08:15 werkdag_ochtendspits
"""
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import disruptions  # noqa: E402
from build_slots import write_profile, OSM, IMG, PBF  # noqa: E402
from build_matrices import load_points, zone_matrix  # noqa: E402
from timeslots import SLOTS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
PORT = 5010
CELL = 0.004                 # rastercel ~280 m, zodat 3x3 cellen de straal dekken
BLOK_FACTOR = 500            # praktisch dicht, zonder de graaf op te knippen
VERTRAAG_FACTOR = 1.6

LUA = '''
-- Scenariolaag: wegvakken vlak bij een afsluitingspunt worden onbegaanbaar
-- duur. Een grote factor in plaats van verwijderen, zodat de graaf heel blijft
-- en een zonepaar zonder alternatief nog steeds een route houdt (die we in de
-- rapportage als "geen alternatief" markeren in plaats van als reistijd).
local BLOCK_CELL = %(cell)s
local BLOCK_RADIUS = %(radius)s
local BLOCKS = %(blocks)s

local function cellkey(lon, lat)
  return math.floor(lon / BLOCK_CELL) .. ":" .. math.floor(lat / BLOCK_CELL)
end

function process_segment(profile, segment)
  local mlon = (segment.source.lon + segment.target.lon) * 0.5
  local mlat = (segment.source.lat + segment.target.lat) * 0.5
  local gx = math.floor(mlon / BLOCK_CELL)
  local gy = math.floor(mlat / BLOCK_CELL)
  local kx = math.cos(mlat * math.pi / 180) * 111320
  for dx = -1, 1 do
    for dy = -1, 1 do
      local bucket = BLOCKS[(gx + dx) .. ":" .. (gy + dy)]
      if bucket then
        for i = 1, #bucket do
          local p = bucket[i]
          local ddx = (p[1] - mlon) * kx
          local ddy = (p[2] - mlat) * 110540
          if ddx * ddx + ddy * ddy <= BLOCK_RADIUS * BLOCK_RADIUS then
            segment.weight = segment.weight * p[3]
            segment.duration = segment.duration * p[3]
            return
          end
        end
      end
    end
  end
end
'''


def lua_blocks(punten):
    """Punten in rastercellen, als Lua-tabel."""
    grid = {}
    for p in punten:
        f = BLOK_FACTOR if p["soort"] == "blokkerend" else VERTRAAG_FACTOR
        key = f'{int(p["lon"] // CELL)}:{int(p["lat"] // CELL)}'
        grid.setdefault(key, []).append((p["lon"], p["lat"], f))
    body = ",\n".join(
        f'  ["{k}"] = {{' + ",".join(f"{{{a},{b},{c}}}" for a, b, c in v) + "}"
        for k, v in grid.items())
    return "{\n" + body + "\n}", len(grid)


def build(moment, slot, punten):
    d = write_profile("scenario", SLOTS[slot])          # congestie van het tijdvak
    lua = (d / "car.lua").read_text()
    blocks, ncel = lua_blocks(punten)
    lua = lua.replace("function process_way(",
                      LUA % {"cell": CELL, "radius": disruptions.BLOCK_RADIUS_M,
                             "blocks": blocks} + "\nfunction process_way(", 1)
    lua = lua.replace("  process_turn = process_turn",
                      "  process_segment = process_segment,\n  process_turn = process_turn", 1)
    (d / "car.lua").write_text(lua)
    print(f"   {len(punten)} punten over {ncel} rastercellen in het profiel")

    dd = OSM / "slots" / "scenario"
    dd.mkdir(parents=True, exist_ok=True)
    if not (dd / PBF).exists():
        (dd / PBF).hardlink_to(OSM / PBF)
    m = ["-v", f"{dd}:/data", "-v", f"{d}:/profile"]
    run = lambda *a: subprocess.run(["docker", "run", "--rm", *m, IMG, *a],
                                    check=True, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
    run("osrm-extract", "-p", "/profile/car.lua", f"/data/{PBF}")
    base = f"/data/{PBF[:-8]}.osrm"
    run("osrm-partition", base)
    run("osrm-customize", base)
    subprocess.run(["docker", "rm", "-f", "osrm-scenario"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["docker", "run", "-d", "--name", "osrm-scenario",
                    "-p", f"{PORT}:5000", "-v", f"{dd}:/data", IMG,
                    "osrm-routed", "--algorithm", "mld",
                    "--max-table-size", "4000", base],
                   check=True, stdout=subprocess.DEVNULL)


def main():
    moment_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now(timezone.utc).isoformat()
    slot = sys.argv[2] if len(sys.argv) > 2 else "werkdag_avondspits"
    moment = datetime.fromisoformat(moment_str).replace(tzinfo=timezone.utc)

    rows = disruptions.load()
    blok = disruptions.actief_op(rows, moment, ("blokkerend",))
    vert = disruptions.actief_op(rows, moment, ("vertragend",))
    punten = [{"lon": r["lon"], "lat": r["lat"], "soort": disruptions.impact(r)}
              for r in blok + vert]
    print(f"{moment:%d-%m-%Y %H:%M} / {slot}: {len(blok)} afsluitingen, "
          f"{len(vert)} vertragende maatregelen")
    if not punten:
        sys.exit("geen actieve maatregelen op dat moment")
    build(moment, slot, punten)
    vergelijk(moment, slot)


def vergelijk(moment, slot, stem="parkzones"):
    """Scenario naast het gewone tijdvak leggen."""
    import csv
    import time
    meta, coords, idx, zids = load_points(stem)
    for _ in range(20):                       # router heeft even nodig
        try:
            scen = zone_matrix(PORT, meta, coords, idx, zids)
            break
        except Exception:
            time.sleep(2)
    else:
        sys.exit(f"scenario-router op poort {PORT} kwam niet op")

    basis = {}
    with open(OUT / f"matrix_all_{stem}.csv") as f:
        for r in csv.DictReader(f):
            basis[(r["from_zone"], r["to_zone"])] = int(r[f"{slot}_s"])

    rows, erger, geen_alt = [], [], 0
    for k, (t, _m) in scen.items():
        if k[0] == k[1] or t is None or k not in basis:
            continue
        b = basis[k]
        d = t - b
        rows.append(d)
        if t > b * 2.5:
            geen_alt += 1
        elif d > 0:
            erger.append((d, k, b, t))

    rows.sort()
    veranderd = sum(1 for d in rows if abs(d) >= 30)
    print(f"\n{len(rows)} zoneparen vergeleken met {slot}")
    print(f"   noemenswaardig anders (>= 30 s): {veranderd} "
          f"({veranderd / len(rows) * 100:.1f}%)")
    print(f"   mediaan verschil: {rows[len(rows)//2]/60:+.1f} min   "
          f"p95 {rows[int(len(rows)*.95)]/60:+.1f} min")
    print(f"   geen redelijk alternatief (>2,5x): {geen_alt} paren")

    erger.sort(reverse=True)
    print("\nsterkst geraakte zoneparen:")
    for d, (a, b), t0, t1 in erger[:8]:
        print(f"   {meta[a]['naam'][:26]:<26} -> {meta[b]['naam'][:26]:<26} "
              f"{t0/60:5.1f} -> {t1/60:5.1f} min  ({d/60:+.1f})")

    naam = OUT / f"matrix_scenario_{moment:%Y%m%d-%H%M}_{slot}.csv"
    with open(naam, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["from_zone", "from_naam", "to_zone", "to_naam",
                    f"{slot}_s", "scenario_s", "verschil_s"])
        for k, (t, _m) in scen.items():
            if k in basis and t is not None:
                w.writerow([k[0], meta[k[0]]["naam"], k[1], meta[k[1]]["naam"],
                            basis[k], t, t - basis[k]])
    print(f"\n-> {naam.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
