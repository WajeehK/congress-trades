#!/usr/bin/env bash
# Box -> GitHub Senate relay for WajeehK/congress-trades (Bargo returns HTTP 403 to GitHub Actions IPs).
# Scope, deliberately narrow:
#   - READS ONLY the box tracker's latest Bargo dump (data/bargo_senate_<date>_p*.json); makes no Bargo calls itself
#   - encrypts it with the repo's STATE_KEY (AES-256) so raw Bargo records are never public
#   - force-pushes ONE file to ONE branch (senate-feed) of ONE repo, only when the content changed
# Run:  ./senate_feed.sh loop   (hourly)   |   ./senate_feed.sh once
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC=/workspace/politician-trades-tracker/data
REPO=https://github.com/WajeehK/congress-trades.git
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
  echo "$(date -Is) pushed"
}
if [ "${1:-once}" = loop ]; then
  echo $$ > "$HERE/senate_feed.pid"
  while true; do push_once || echo "$(date -Is) push failed"; sleep 3600; done
else
  push_once
fi
