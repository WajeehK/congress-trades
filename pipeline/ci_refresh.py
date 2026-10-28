"""Hourly data refresh for GitHub Actions.

Fetches House Clerk, Senate (Bargo), OGE and Yahoo prices into the SQLite state (DB_PATH), and sends Web Push
alerts for new trades -- unless another sender is active, so subscribers never get the same alert twice.

NTFY_SENDER:
  actions -> this workflow always sends
  box     -> never send here (the box server sends)
  auto    -> (default) send only when the box server at BOX_STATUS_URL is down or hasn't refreshed in 3 hours
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("NO_SCHEDULER", "1")
import app  # noqa: E402


def box_alive():
    url = os.environ.get("BOX_STATUS_URL", "").strip()
    if not url:
        return False, "no BOX_STATUS_URL"
    try:
        r = requests.get(url, headers={"User-Agent": "congress-trades-actions/1.0", "ngrok-skip-browser-warning": "1"}, timeout=20)
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}"
        last = r.json().get("last_refresh")
        if not last:
            return False, "box never refreshed"
        age = datetime.now(timezone.utc) - datetime.fromisoformat(last)
        return age < timedelta(hours=3), f"box last refresh {int(age.total_seconds() // 60)} min ago"
    except Exception as e:
        return False, f"unreachable ({type(e).__name__})"


def senate_feed():
    """Senate trades relayed by the box (Bargo blocks GitHub's IP ranges). The workflow decrypts the
    `senate-feed` branch to data/senate_feed.json; raw records never leave the encrypted state."""
    f = app.DATA / "senate_feed.json"
    if os.environ.get("SENATE_VIA", "feed") != "feed" or not f.exists():
        return None
    d = json.loads(f.read_text())
    return d.get("trades", []), d.get("exported_at")


def main():
    mode = os.environ.get("NTFY_SENDER", "auto").strip().lower() or "auto"
    if mode == "actions":
        send, why = True, "NTFY_SENDER=actions"
    elif mode == "box":
        send, why = False, "NTFY_SENDER=box"
    else:
        alive, why = box_alive()
        send = not alive
    app._startup()
    before = app.status()
    feed = senate_feed()
    extra = []
    if feed is not None:
        app.fetch_senate = lambda force=False: []  # direct Bargo calls from Actions get HTTP 403
        extra = app.ingest_bargo(feed[0])
        app.note(f"Senate (Bargo via box feed, exported {feed[1]}): {len(extra)} new transactions")
    app.refresh(force_senate=False, do_notify=send)
    if send and extra:
        app.notify(extra)
    try:  # daily 18:00 / weekly Sunday 18:00 UK recaps: first run at or after the time sends once
        import recap
        with app.db() as c:
            rows = c.execute(f"{app.TRADE_SELECT} WHERE t.first_seen >= ?", ((datetime.now(timezone.utc) - timedelta(days=8)).isoformat(),)).fetchall()
        try:
            sec = json.loads((ROOT / "ticker_sectors.json").read_text())
        except Exception:
            sec = {}
        recap.maybe_send(rows, app.meta_get, app.meta_set, app.note, sec)
    except Exception as e:
        app.note(f"recap failed: {type(e).__name__}: {e}")
    st = app.status()
    n0 = sum(s["n"] for s in before["sources"])
    n1 = sum(s["n"] for s in st["sources"])
    lines = [f"### The Insider House refresh",
             f"- trades: {n0} -> {n1} (+{n1 - n0})",
             f"- notifications: {'sent by this run' if send else 'skipped'} ({why})",
             f"- prices: {json.dumps(st['prices'])}",
             f"- last error: {st['last_error']}", "", "```", *st["log"], "```"]
    print("\n".join(lines))
    summ = os.environ.get("GITHUB_STEP_SUMMARY")
    if summ:
        with open(summ, "a") as f:
            f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
