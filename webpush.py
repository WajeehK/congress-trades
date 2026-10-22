"""Native Web Push for The Black House PWA (replaces the ntfy app for people who install the site).

Subscriptions: the browser publishes its PushSubscription (+ "all trades" flag and follow list) as a JSON message to a
dedicated ntfy.sh topic (SUB_TOPIC; anonymous, free, no account). Every refresh (GitHub Actions hourly and the box)
polls that topic and merges the messages into the `meta` table (key push_subs) of its own SQLite DB, so there is no
single server that must be up when someone subscribes. The app re-publishes its subscription whenever it is opened
(at most every 20 h) and on any follow change, which keeps every store current despite ntfy's ~12 h message cache.
Subscription endpoints are useless without the VAPID private key, which lives only in the Actions secret
VAPID_PRIVATE_KEY and in data/vapid_private.pem on the box (mode 600).

Sending: send() is called from app.notify() with the same rows ntfy gets (already deduped and backfill-filtered).
Each subscriber gets one notification covering the trades they asked for. 404/410 responses drop the subscription.
"""
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import quote

import requests

SUB_TOPIC = "bh-subs-0ddc01105a955b4f"
NTFY = "https://ntfy.sh"
VAPID_PUBLIC = "BFR_8mhNgGoPpD-5cQIyJmoyC5dCsW3gk38_4cUh0h9MJhxZ7_bn9Hj3uwKVALUsrX1j80doKWHMJmZ3cVivd9Y"
APP_URL = os.environ.get("PUSH_APP_URL", "https://wajeehk.github.io/congress-trades/")
CLAIM = "mailto:WajeehK@users.noreply.github.com"
# only ever POST to real push services (the topic is public, so never trust an arbitrary endpoint)
PUSH_HOSTS = re.compile(r"^https://([a-z0-9.-]+\.)?(fcm\.googleapis\.com|push\.services\.mozilla\.com|"
                        r"notify\.windows\.com|push\.apple\.com|web\.push\.apple\.com)(/|$)")
MAX_SUBS = 200


def _vapid():
    from py_vapid import Vapid01
    pem = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
    if pem:
        return Vapid01.from_pem(pem.encode())
    f = Path(os.environ.get("VAPID_PRIVATE_FILE", Path(__file__).resolve().parent / "data" / "vapid_private.pem"))
    return Vapid01.from_file(str(f)) if f.exists() else None


def _load(meta_get):
    try:
        return json.loads(meta_get("push_subs") or "{}")
    except Exception:
        return {}


def _valid(sub):
    k = (sub or {}).get("keys") or {}
    ep = (sub or {}).get("endpoint") or ""
    return bool(PUSH_HOSTS.match(ep) and isinstance(k.get("p256dh"), str) and isinstance(k.get("auth"), str)
                and len(ep) < 1000 and len(k["p256dh"]) < 200 and len(k["auth"]) < 100)


def sync(meta_get, meta_set, note=print):
    """Merge newly published subscription messages from the ntfy topic into meta.push_subs."""
    since = meta_get("push_since") or "24h"
    try:
        r = requests.get(f"{NTFY}/{SUB_TOPIC}/json", params={"poll": "1", "since": since}, timeout=20)
        r.raise_for_status()
    except Exception as e:
        note(f"push: subscription sync failed: {e}")
        return None
    subs, last, changed = _load(meta_get), None, 0
    for line in r.text.splitlines():
        try:
            m = json.loads(line)
            if m.get("event") != "message":
                continue
            last = max(last or 0, int(m["time"]))
            b = json.loads(m.get("message") or "{}")
            sub = b.get("sub") or {}
            if not _valid(sub):
                continue
            ep = sub["endpoint"]
            prev = subs.get(ep)
            if prev and prev.get("ts", 0) > m["time"]:
                continue
            if b.get("off"):
                changed += subs.pop(ep, None) is not None
                continue
            fol = [str(x)[:80] for x in (b.get("follows") or [])][:300]
            subs[ep] = {"sub": {"endpoint": ep, "keys": {"p256dh": sub["keys"]["p256dh"], "auth": sub["keys"]["auth"]}},
                        "all": bool(b.get("all")), "follows": fol, "ts": int(m["time"])}
            changed += 1
        except Exception:
            continue
    if len(subs) > MAX_SUBS:  # keep the most recently refreshed
        subs = dict(sorted(subs.items(), key=lambda kv: -kv[1].get("ts", 0))[:MAX_SUBS])
    meta_set("push_subs", json.dumps(subs))
    if last:
        meta_set("push_since", str(last))  # ntfy 'since' is inclusive-ish; re-merging is idempotent
    if changed:
        note(f"push: {changed} subscription update(s), {len(subs)} active")
    return subs


def _clean(n):
    return re.sub(r"\s+", " ", n or "").strip()


def _line(r):
    side = "Buy" if r["side"] == "buy" else "Sell" if r["side"] == "sell" else (r["tx_type"] or "Trade")
    return f"{side} {r['ticker'] or (r['asset'] or '')[:28]} ({r['amount'] or '?'})"


def message(rows):
    by = {}
    for r in rows:
        by.setdefault(r["politician"], []).append(r)
    if len(by) == 1:
        pol, rs = next(iter(by.items()))
        body = "; ".join(_line(r) for r in rs[:5]) + (f" +{len(rs) - 5} more" if len(rs) > 5 else "")
        return {"title": f"{pol} disclosed new trades.", "body": body, "url": f"{APP_URL}#p={quote(pol)}",
                "tag": "pol-" + re.sub(r"[^a-z0-9]+", "-", pol.lower())[:40]}
    parts = sorted(by.items(), key=lambda kv: -len(kv[1]))
    body = "\n".join(f"{p}: " + "; ".join(_line(r) for r in rs[:2]) + (f" +{len(rs) - 2}" if len(rs) > 2 else "")
                     for p, rs in parts[:4])
    if len(parts) > 4:
        body += f"\n…and {len(parts) - 4} more politicians"
    n = len(rows)
    return {"title": f"{n} new trade{'s' if n != 1 else ''} disclosed", "body": body, "url": f"{APP_URL}#trades", "tag": "all"}


def deliver(sub, payload, vapid):
    """Returns 'ok', 'gone' (drop it) or an error string."""
    from pywebpush import webpush, WebPushException
    try:
        webpush(subscription_info=sub, data=json.dumps(payload)[:3500], vapid_private_key=vapid,
                vapid_claims={"sub": CLAIM}, ttl=86400, timeout=20)
        return "ok"
    except WebPushException as e:
        code = getattr(e.response, "status_code", None)
        return "gone" if code in (404, 410) else f"HTTP {code}: {str(e)[:120]}"
    except Exception as e:
        return str(e)[:160]


def send(new_rows, meta_get, meta_set, note=print):
    if not new_rows:
        return 0
    subs = _load(meta_get)
    if not subs:
        return 0
    vapid = _vapid()
    if vapid is None:
        note("push: no VAPID private key configured; skipped")
        return 0
    sent, dead = 0, []
    for ep, s in list(subs.items()):
        fol = set(s.get("follows") or [])
        rows = list(new_rows) if s.get("all") else [r for r in new_rows if r["politician"] in fol]
        if not rows:
            continue
        res = deliver(s["sub"], message(rows), vapid)
        if res == "ok":
            sent += 1
        elif res == "gone":
            dead.append(ep)
        else:
            note(f"push: delivery failed ({res})")
    if dead:
        subs = _load(meta_get)
        for ep in dead:
            subs.pop(ep, None)
        meta_set("push_subs", json.dumps(subs))
    note(f"push: sent to {sent} device(s){f', removed {len(dead)} expired' if dead else ''}")
    return sent


if __name__ == "__main__":  # python webpush.py test  -> test notification to every stored subscription
    import sys
    os.environ.setdefault("NO_SCHEDULER", "1")
    import app
    app.init_db()
    sync(app.meta_get, app.meta_set)
    if sys.argv[1:] == ["test"]:
        subs, v = _load(app.meta_get), _vapid()
        for ep, s in subs.items():
            print(ep[:40], deliver(s["sub"], {"title": "The Black House", "body": "Test notification: push is working.",
                                              "url": APP_URL, "tag": "test"}, v))
    else:
        print(len(_load(app.meta_get)), "subscriptions")
