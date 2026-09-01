#!/usr/bin/env bash
# Bouwt de OSRM MLD-graaf voor het Rotterdam-extract. Volledig gratis/offline.
set -euo pipefail
DATA="$(cd "$(dirname "$0")/../data/osm" && pwd)"
IMG=ghcr.io/project-osrm/osrm-backend:latest
PBF="${1:-Rotterdam.osm.pbf}"
BASE="${PBF%.osm.pbf}"
run() { docker run --rm -t -v "$DATA:/data" "$IMG" "$@"; }
run osrm-extract -p /opt/car.lua "/data/$PBF"
run osrm-partition "/data/$BASE.osrm"
run osrm-customize "/data/$BASE.osrm"
echo "OSRM_BUILD_DONE"
