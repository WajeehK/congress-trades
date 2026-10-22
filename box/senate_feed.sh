#!/usr/bin/env bash
# Box -> GitHub Senate relay for WajeehK/congress-trades (Bargo returns HTTP 403 to GitHub Actions IPs).
# Scope, deliberately narrow:
#   - READS ONLY the box tracker's latest Bargo dump (data/bargo_senate_<date>_p*.json); makes no Bargo calls itself
#   - encrypts it with the repo's STATE_KEY (AES-256) so raw Bargo records are never public
#   - force-pushes ONE file to ONE branch (senate-feed) of ONE repo, only when the content changed
#   - dispatches the repo's "Refresh data and deploy" workflow: right after a feed push, and once an hour at ~:07
#     (GitHub's own cron is late or skipped for hours at a time; it stays as a backup and skips itself after our run)
# Run:  ./senate_feed.sh loop   (checks every 10 min)   |   ./senate_feed.sh once   |   ./senate_feed.sh dispatch
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC=/workspace/politician-trades-tracker/data
REPO=https://github.com/WajeehK/congress-trades.git
GH_REPO=WajeehK/congress-trades
WORKFLOW=pipeline.yml
PUSHED=0
KEY="$HERE/../state_key.txt"
push_once() {
  local work; work="$(mktemp -d)"; trap 'rm -rf "$work"' RETURN
  python3 - "$SRC" "$work/senate.json" <<'PY' || return 0
import glob, json, os, sys
from datetime import datetime, timezone
src, out = sys.argv[1], sys.argv[2]
files = sorted(glob.glob(os.path.join(src, "bargo_senate_20??-??-??_p*.json")))
if not files:
    sys.exit(1)
day = os.path.basename(files[-1])[13:23]
trades = []
for f in sorted(glob.glob(os.path.join(src, f"bargo_senate_{day}_p*.json"))):
    trades += json.load(open(f)).get("trades", [])
json.dump({"trades": trades, "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "source_day": day},
          open(out, "w"))
PY
  local sum; sum="$(python3 -c 'import json,sys,hashlib;print(hashlib.sha256(json.dumps(json.load(open(sys.argv[1]))["trades"],sort_keys=True).encode()).hexdigest())' "$work/senate.json")"
  if [ -f "$HERE/last.sha" ] && [ "$(cat "$HERE/last.sha")" = "$sum" ]; then echo "$(date -Is) unchanged"; return 0; fi
  mkdir "$work/g"
  gzip -9c "$work/senate.json" | STATE_KEY="$(cat "$KEY")" openssl enc -aes-256-cbc -salt -pbkdf2 -iter 200000 -pass env:STATE_KEY -out "$work/g/senate.json.gz.enc"
  printf 'Encrypted Senate trade feed relayed from the box (Bargo blocks GitHub IPs). Not public data.\n' > "$work/g/README.md"
  git -C "$work/g" init -q -b senate-feed
  git -C "$work/g" add -A
  git -C "$work/g" -c user.name=WajeehK -c user.email=WajeehK@users.noreply.github.com commit -qm "senate feed $(date -u +%FT%TZ)"
  git -C "$work/g" -c credential.helper= -c credential.helper='!gh auth git-credential' push -qf "$REPO" senate-feed:senate-feed
  echo "$sum" > "$HERE/last.sha"
  PUSHED=1
  echo "$(date -Is) pushed"
}

# Start the workflow unless one is already waiting to run (the concurrency group then picks it up after the
# current run, so it will see the newest feed anyway). $1 = reason, $2 = "hourly" also skips if a run started <30 min ago.
dispatch() {
  local waiting recent since
  waiting="$(gh run list -R "$GH_REPO" --workflow "$WORKFLOW" -L 10 --json status \
             -q '[.[] | select(.status == "queued" or .status == "pending" or .status == "waiting" or .status == "requested")] | length' 2>/dev/null || echo 0)"
  if [ "${waiting:-0}" -gt 0 ]; then echo "$(date -Is) dispatch ($1) skipped: a run is already queued"; return 0; fi
  if [ "${2:-}" = hourly ]; then
    since="$(date -u -d '-30 min' +%FT%TZ)"
    recent="$(gh run list -R "$GH_REPO" --workflow "$WORKFLOW" -L 10 --json createdAt,status,conclusion \
              -q "[.[] | select(.createdAt >= \"$since\" and (.status == \"in_progress\" or .conclusion == \"success\"))] | length" 2>/dev/null || echo 0)"
    if [ "${recent:-0}" -gt 0 ]; then echo "$(date -Is) dispatch ($1) skipped: a run started in the last 30 min"; return 0; fi
  fi
  if gh workflow run "$WORKFLOW" -R "$GH_REPO" >/dev/null 2>&1; then echo "$(date -Is) dispatched ($1)"
  else echo "$(date -Is) dispatch ($1) FAILED"; fi
}

# seconds until the next check at :07, :17, :27, :37, :47 or :57
sleep_to_next_slot() {
  local now m s
  now="$(date +%s)"; m=$(( 10#$(date +%M) )); s=$(( 10#$(date +%S) ))
  local into=$(( ((m - 7) % 10 + 10) % 10 * 60 + s ))
  sleep $(( 600 - into ))
}
if [ "${1:-once}" = loop ]; then
  echo $$ > "$HERE/senate_feed.pid"
  while true; do
    PUSHED=0
    push_once || echo "$(date -Is) push failed"
    [ "$PUSHED" = 1 ] && dispatch "new Senate feed"
    slot="$(date -u +%FT%H)"   # one hourly dispatch per UTC hour, remembered across restarts
    if [ "$(cat "$HERE/last_hourly" 2>/dev/null)" != "$slot" ] && [ $(( 10#$(date +%M) )) -ge 7 ]; then
      [ "$PUSHED" = 1 ] || dispatch "hourly" hourly
      echo "$slot" > "$HERE/last_hourly"
    fi
    sleep_to_next_slot
  done
elif [ "$1" = dispatch ]; then
  dispatch "manual"
else
  push_once
fi
