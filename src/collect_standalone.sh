#!/usr/bin/env bash
# Eén NDW-meting ophalen en naar de databranch pushen, zonder GitHub Actions.
#
# Waarom dit bestaat: GitHub voert de schedule-trigger van ndw-sampler.yml niet
# uit (drie cron-varianten, nul geplande runs), en de omgevingstoken mag niet
# dispatchen. Dit script doet hetzelfde werk vanaf een willekeurige machine die
# de repo kan pushen -- een crontab-regel, of de routine die dit aftrapt.
#
#     */30 * * * * /pad/naar/MapsRotterdam/src/collect_standalone.sh
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="${NDW_WORKTREE:-$REPO/../ndw-data}"
cd "$REPO"

python3 -c "import requests" 2>/dev/null || pip3 install --quiet requests

git config user.name  "ndw-sampler" 2>/dev/null || true
git config user.email "ndw-sampler@users.noreply.github.com" 2>/dev/null || true

# databranch als worktree; hij bestaat al, dus geen orphan-tak nodig
if [ ! -d "$WORK/.git" ] && [ ! -f "$WORK/.git" ]; then
  git fetch --depth=1 origin ndw-data:refs/heads/ndw-data 2>/dev/null || true
  git worktree add "$WORK" ndw-data
else
  git -C "$WORK" fetch --depth=1 origin ndw-data
  git -C "$WORK" reset --hard origin/ndw-data
fi

export NDW_HISTORY_DIR="$WORK/ndw_history"
export NDW_BLACKOUTS="$WORK/blackouts/ndw_site_blackouts.json"
python3 src/sample_ndw.py collect

cd "$WORK"
git add -A
if git diff --cached --quiet; then
  echo "Niets te pushen -- buiten de tijdvakken of geen nieuwe metingen."
  exit 0
fi
git commit -q -m "NDW-meting $(TZ=Europe/Amsterdam date '+%Y-%m-%d %H:%M')"
for i in 1 2 3 4; do
  git push origin HEAD:ndw-data && exit 0
  sleep $((2 ** i))
  git fetch origin ndw-data && git reset --hard origin/ndw-data || true
done
echo "push mislukt" >&2
exit 1
