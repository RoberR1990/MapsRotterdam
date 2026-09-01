"""Bouwt per tijdvak een eigen OSRM-dataset en start er een router voor.

Per tijdvak wordt car.lua gekopieerd met geschaalde wegsnelheden en
kruispuntstraf, waarna extract/partition/customize draait. Kosten: nul.
Duur: ~40 s per tijdvak op dit extract.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from timeslots import SLOTS, PORTS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OSM = ROOT / "data" / "osm"
PROF = ROOT / "profiles"
IMG = "ghcr.io/project-osrm/osrm-backend:latest"
PBF = "Rotterdam.osm.pbf"


def write_profile(slot, cfg):
    """Kopieer het car-profiel met een congestie-handler voor dit tijdvak.

    De snelheden in de `speeds`-tabel schalen werkt in Nederland nauwelijks:
    WayHandlers.maxspeed draait daarna en overschrijft ze met de OSM-tag. We
    hangen de factor daarom achteraan de handler-keten, vlak voor `weights`,
    zodat hij op de *uiteindelijke* snelheid werkt -- ongeacht waar die vandaan
    komt -- en de routegewichten er meteen uit volgen.
    """
    d = PROF / slot
    if d.exists():
        shutil.rmtree(d)
    shutil.copytree(PROF / "base", d)
    lua = (d / "car.lua").read_text()

    tbl = "\n".join(f'        ["{k}"] = {v},' for k, v in cfg["speed"].items())
    lua = lua.replace(
        "    speed_reduction           = 0.8,",
        "    speed_reduction           = 0.8,\n"
        "    congestion_default        = 0.95,\n"
        "    congestion = {\n" + tbl + "\n    },", 1)

    lua = re.sub(r"^(\s+turn_penalty\s+=\s+)([\d.]+)(,)",
                 lambda m: f"{m.group(1)}{float(m.group(2)) * cfg['turn']:.2f}{m.group(3)}",
                 lua, count=1, flags=re.M)

    handler = """
-- Tijdvak-congestie: schaal de definitieve wegsnelheid per OSM-wegklasse.
function apply_congestion(profile, way, result, data, relations)
  local hw = way:get_value_by_key("highway")
  local f = (hw and profile.congestion[hw]) or profile.congestion_default
  if result.forward_speed and result.forward_speed > 0 then
    result.forward_speed = math.max(3, result.forward_speed * f)
  end
  if result.backward_speed and result.backward_speed > 0 then
    result.backward_speed = math.max(3, result.backward_speed * f)
  end
end

"""
    lua = lua.replace("function process_way(", handler + "function process_way(", 1)
    lua = lua.replace("    WayHandlers.weights,",
                      "    apply_congestion,\n\n    WayHandlers.weights,", 1)
    (d / "car.lua").write_text(lua)
    return d


def run(*args, **kw):
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, **kw)


def build(slot):
    d = OSM / "slots" / slot
    d.mkdir(parents=True, exist_ok=True)
    tgt = d / PBF
    if not tgt.exists():                      # hardlink: kost geen schijfruimte
        tgt.hardlink_to(OSM / PBF)
    mounts = ["-v", f"{d}:/data", "-v", f"{PROF / slot}:/profile"]
    run("docker", "run", "--rm", *mounts, IMG,
        "osrm-extract", "-p", "/profile/car.lua", f"/data/{PBF}")
    base = f"/data/{PBF[:-8]}.osrm"
    run("docker", "run", "--rm", *mounts, IMG, "osrm-partition", base)
    run("docker", "run", "--rm", *mounts, IMG, "osrm-customize", base)

    name = f"osrm-{slot}"
    subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)
    run("docker", "run", "-d", "--name", name, "-p", f"{PORTS[slot]}:5000",
        "-v", f"{d}:/data", IMG, "osrm-routed", "--algorithm", "mld",
        "--max-table-size", "4000", base)


def main():
    for slot, cfg in SLOTS.items():
        print(f"-> {slot}", flush=True)
        write_profile(slot, cfg)
        build(slot)
        print(f"   klaar, router op poort {PORTS[slot]}", flush=True)
    print("BUILD_SLOTS_DONE")


if __name__ == "__main__":
    main()
