"""Unusual activity: buying clusters and unusually large trades (shared by box, Actions export and push).

* Cluster: 3+ distinct politicians buying the same ticker within 14 days (by trade date). One event per ticker and
  window; `seen` is when the cluster became visible (first_seen of the disclosure that brought it to 3 buyers).
* Large: a stock/fund trade with a low bound >= $250K, or in the top 1% of that person's own trades by size
  (people with 100+ trades, floor $50K).
Only listed stocks/funds count (rows without a ticker, bonds, options etc. are ignored; see most_bought.kind).
"""
from datetime import date, timedelta

import most_bought

CLUSTER_N, CLUSTER_DAYS = 3, 14
LARGE_LOW, P99_MIN_TRADES, P99_FLOOR = 250_000, 100, 50_000
LOOKBACK_DAYS = 120


def _p99(c):
    out = {}
    for pol, n in c.execute("SELECT politician, COUNT(*) FROM trades WHERE ticker IS NOT NULL GROUP BY politician "
                            "HAVING COUNT(*) >= ?", (P99_MIN_TRADES,)).fetchall():
        k = max(0, int(n * 0.01) - 1)
        r = c.execute("SELECT COALESCE(amount_low,0) FROM trades WHERE politician=? AND ticker IS NOT NULL "
                      "ORDER BY COALESCE(amount_low,0) DESC LIMIT 1 OFFSET ?", (pol, k)).fetchone()
        out[pol] = max(P99_FLOOR, r[0] if r else 0)
    return out


def events(c, rows, today=None):
    """rows: recent trade rows (TRADE_SELECT dicts). Returns events newest first."""
    today = today or date.today()
    since = (today - timedelta(days=LOOKBACK_DAYS)).isoformat()
    rows = [r for r in rows if (r["tx_date"] or "") >= since and r["ticker"] and most_bought.kind(r)]
    p99 = _p99(c)
    ev = []
    for r in rows:
        low = r["amount_low"] or 0
        why = None
        if low >= LARGE_LOW:
            why = f"{'Bought' if r['side'] == 'buy' else 'Sold' if r['side'] == 'sell' else 'Traded'} {r['amount']}"
        elif r["politician"] in p99 and low >= p99[r["politician"]] and low > 0:
            why = f"Top 1% of {r['politician'].split()[-1]}'s trades by size"
        if why and r["side"] in ("buy", "sell"):
            ev.append({"type": "large", "key": f"l:{r['uid']}", "uid": r["uid"], "ticker": r["ticker"],
                       "name": r["company"], "politician": r["politician"], "bioguide": r["bioguide"], "side": r["side"],
                       "amount": r["amount"], "amount_low": low, "amount_high": r["amount_high"], "tx_date": r["tx_date"], "why": why,
                       "seen": r["first_seen"] or r["disclosure_date"], "disclosed": r["disclosure_date"]})
    by = {}
    for r in rows:
        if r["side"] == "buy" and r["tx_date"]:
            by.setdefault(r["ticker"], []).append(r)
    for t, rs in by.items():
        if len({r["politician"] for r in rs}) < CLUSTER_N:
            continue
        rs.sort(key=lambda r: r["tx_date"])
        used_until = ""
        for i in range(len(rs)):
            if rs[i]["tx_date"] <= used_until:
                continue
            d0 = date.fromisoformat(rs[i]["tx_date"])
            end = (d0 + timedelta(days=CLUSTER_DAYS)).isoformat()
            win = [r for r in rs[i:] if r["tx_date"] <= end]
            pols = {}
            for r in win:
                pols.setdefault(r["politician"], r)
            if len(pols) < CLUSTER_N:
                continue
            # when did it become visible? sort by first_seen and find the 3rd distinct politician
            seen, got = None, set()
            for r in sorted(win, key=lambda r: r["first_seen"] or r["disclosure_date"] or ""):
                got.add(r["politician"])
                if len(got) >= CLUSTER_N:
                    seen = r["first_seen"] or r["disclosure_date"]
                    break
            ev.append({"type": "cluster", "key": f"c:{t}:{rs[i]['tx_date']}", "ticker": t, "name": win[0]["company"],
                       "n_pols": len(pols), "n_buys": len(win), "from": win[0]["tx_date"], "to": win[-1]["tx_date"],
                       "pols": [{"name": p, "bioguide": r["bioguide"]} for p, r in list(pols.items())[:6]],
                       "uids": [r["uid"] for r in win], "seen": seen,
                       "disclosed": max(r["disclosure_date"] or "" for r in win)})
            used_until = end
    ev.sort(key=lambda e: e["seen"] or "", reverse=True)
    return ev


def recent(c, rows, days=30, limit=80):
    cut = (date.today() - timedelta(days=days)).isoformat()
    ev = [e for e in events(c, rows) if (e["disclosed"] or "") >= cut]
    cl = [e for e in ev if e["type"] == "cluster"]
    return cl + [e for e in ev if e["type"] != "cluster"][:max(0, limit - len(cl))]


def for_new(c, rows, new_rows, sent):
    """Events that involve at least one of new_rows and haven't been alerted (keys in `sent`)."""
    new = {r["uid"] for r in new_rows}
    out = []
    for e in events(c, rows):
        if e["key"] in sent:
            continue
        if (e["type"] == "large" and e["uid"] in new) or (e["type"] == "cluster" and new & set(e["uids"])):
            out.append(e)
    return out
