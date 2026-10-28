"""Daily (18:00 UK) and weekly (Sunday 18:00 UK) recaps: biggest buys and sells and hidden gems among newly found trades.

build() makes the payload for the in-app recap page (data/recap.json) and the push text. maybe_send() is called by
the GitHub Actions refresh: the first run at/after the target time sends once (marker in the DB meta table, which
lives in the encrypted state), and only if there is something to report.
"""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import gems
import most_bought

UK = ZoneInfo("Europe/London")
SPAN = {"daily": (1, 5), "weekly": (7, 12)}  # (hours window in days, max disclosure age in days to skip backfills)
HOUR = 18


def _mid(r):
    return most_bought.mid(r)


def _t(r):
    return {"uid": r["uid"], "ticker": r["ticker"], "name": r["company"] or r["asset"], "politician": r["politician"],
            "bioguide": r["bioguide"], "party": r["party"], "side": r["side"], "amount": r["amount"],
            "amount_low": r["amount_low"], "amount_high": r["amount_high"], "tx_date": r["tx_date"], "disclosure_date": r["disclosure_date"]}


def build(rows, kind, now=None, sectors=None):
    now = now or datetime.now(timezone.utc)
    days, max_age = SPAN[kind]
    since = (now - timedelta(days=days)).isoformat(timespec="seconds")
    oldest = (now.date() - timedelta(days=max_age)).isoformat()
    new = [r for r in rows if (r["first_seen"] or "") >= since and (r["disclosure_date"] or "") >= oldest]
    buys = sorted([r for r in new if r["side"] == "buy" and most_bought.kind(r)], key=lambda r: -_mid(r))
    sells = sorted([r for r in new if r["side"] == "sell" and most_bought.kind(r)], key=lambda r: -_mid(r))
    uids = {r["uid"] for r in new}
    gm = [g for g in gems.build([r for r in new if r["uid"] in uids], sectors or {}, refresh=False)["items"]][:5]
    return {"kind": kind, "since": since, "generated_at": now.isoformat(timespec="seconds"), "n": len(new),
            "n_pols": len({r["politician"] for r in new}), "buys": [_t(r) for r in buys[:5]], "sells": [_t(r) for r in sells[:5]],
            "gems": [{k: g[k] for k in ("ticker", "name", "industry", "cap", "n_pols", "est_total")} | {"who": (g.get("last") or {}).get("name")} for g in gm]}


def message(rc, app_url):
    if not rc["n"]:
        return None
    label = "Daily recap" if rc["kind"] == "daily" else "Weekly recap"
    parts = []
    if rc["buys"]:
        b = rc["buys"][0]
        parts.append(f"Top buy: {b['ticker'] or (b['name'] or '')[:24]} {b['amount'] or ''} ({b['politician']})")
    if rc["sells"]:
        s = rc["sells"][0]
        parts.append(f"Top sell: {s['ticker'] or (s['name'] or '')[:24]} {s['amount'] or ''} ({s['politician']})")
    if rc["gems"]:
        parts.append("Hidden gems: " + ", ".join(g["ticker"] for g in rc["gems"][:3]))
    when = "today" if rc["kind"] == "daily" else "this week"
    return {"title": f"{label}: {rc['n']} new trade{'s' if rc['n'] != 1 else ''} {when}", "body": "\n".join(parts)[:300],
            "url": f"{app_url}#recap={rc['kind']}", "tag": "recap-" + rc["kind"]}


def due(kind, meta_get, now=None):
    uk = (now or datetime.now(timezone.utc)).astimezone(UK)
    if uk.hour < HOUR or (kind == "weekly" and uk.weekday() != 6):
        return None
    key = uk.date().isoformat()
    return None if meta_get(f"recap_{kind}_sent") == key else key


def maybe_send(rows, meta_get, meta_set, note=print, sectors=None, now=None):
    import webpush
    for kind in ("daily", "weekly"):
        key = due(kind, meta_get, now)
        if not key:
            continue
        rc = build(rows, kind, now, sectors)
        m = message(rc, webpush.APP_URL)
        n = webpush.send_recap(m, kind, meta_get, meta_set, note) if m else 0
        meta_set(f"recap_{kind}_sent", key)
        note(f"recap {kind} {key}: {rc['n']} trades, {n} push(es) sent" if m else f"recap {kind} {key}: nothing new, not sent")
