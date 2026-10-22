"""Unusual activity (shared by the box API, the Actions export and Web Push).

Every event is built only from disclosed trades and Yahoo daily prices. Types:

  cluster_buy   3+ different politicians bought the same stock/fund within 14 days (by trade date)    [alerts]
  bipartisan    a cluster_buy with both Democrats and Republicans among the buyers                     [alerts]
  cluster_sell  3+ different politicians sold the same stock/fund within 14 days                       [alerts]
  large         a trade with a low bound of $250K+, or in the top 1% of that person's own trades       [alerts]
  committee     a $50K+ trade in a sector one of the member's current committees oversees ("possible overlap")
  first_buy     a heavy trader (100+ disclosed trades) buys $50K+ of a stock they never traded before
  options       an options trade (asset type OP)
  burst         a politician's trades in one week are far above their usual weekly pace
  late          disclosed more than the 45-day legal limit after the trade
  hindsight     the price moved 15%+ in the trade's favour within 30 days after it (hindsight, not a signal)

Only cluster_buy, bipartisan, cluster_sell and large are pushed (see for_new); the rest are context.
Each event has a stable `key` (alert dedupe) and a short `id` (link: #unusual=<id>).
"""
import hashlib
import math
import statistics
from datetime import date, timedelta

import most_bought

CLUSTER_N, CLUSTER_DAYS = 3, 14
LARGE_LOW, P99_MIN_TRADES, P99_FLOOR = 250_000, 100, 50_000
COMMITTEE_LOW, FIRST_LOW, FIRST_MIN_TRADES = 50_000, 50_000, 100
HINDSIGHT_MOVE, HINDSIGHT_DAYS, HINDSIGHT_LOW = 15.0, 30, 15_000
BURST_MIN, BURST_X = 10, 5.0
LATE_DAYS = 45
LOOKBACK_DAYS = 120          # trades (by trade date OR disclosure date) considered
WINDOW_DAYS = 90             # events kept for the app (by disclosure date)
TYPE_CAP = 40               # max events per type in the app (best scores first)
ALERT_TYPES = ("cluster_buy", "bipartisan", "cluster_sell", "large")
BASE = {"bipartisan": 70, "cluster_buy": 60, "cluster_sell": 52, "large": 45, "committee": 40, "first_buy": 30,
        "options": 30, "burst": 30, "hindsight": 22, "late": 15}

ROW_KEYS = ("uid", "politician", "bioguide", "party", "state", "district", "chamber", "owner", "ticker", "asset",
            "asset_type", "company", "side", "tx_type", "tx_date", "disclosure_date", "amount", "amount_low",
            "amount_high", "est_price", "cur_price", "pct_since", "lag_days", "first_seen")


def _g(r, k):
    try:
        return r[k]
    except (KeyError, IndexError):
        return None


def _mid(r):
    lo = _g(r, "amount_low") or 0
    return (lo + (_g(r, "amount_high") or lo)) / 2.0


def _money(v):
    if v >= 1e6:
        m = round(v / 1e6, 1)
        return f"${m:.0f}M" if m == int(m) else f"${m}M"
    return f"${round(v / 1e3):.0f}K" if v >= 1e3 else f"${v:.0f}"


def _rng(r):
    lo, hi = _g(r, "amount_low") or 0, _g(r, "amount_high")
    return f"{_money(lo)}–{_money(hi)}" if hi and hi > lo else f"{_money(lo)}+" if lo else (_g(r, "amount") or "?")


def _last(name):
    p = [w for w in (name or "").replace(",", " ").split() if w.rstrip(".") not in ("Jr", "Sr", "II", "III", "IV")]
    return p[-1] if p else name


def _compact(r):
    d = {k: _g(r, k) for k in ROW_KEYS}
    desc = _g(r, "description")
    if desc:
        d["description"] = desc[:140]
    return d


def _ev(type_, key, rows, title, why, extra=0.0, **kw):
    rows = sorted(rows, key=lambda r: (r["tx_date"] or "", r["uid"]))
    pols = {}
    for r in rows:
        pols.setdefault(r["politician"], {"name": r["politician"], "bioguide": _g(r, "bioguide"), "party": _g(r, "party")})
    tick = {r["ticker"] for r in rows if r["ticker"]}
    total = sum(_mid(r) for r in rows)
    e = {"id": hashlib.sha1(key.encode()).hexdigest()[:10], "key": key, "type": type_, "title": title, "why": why,
         "ticker": tick.pop() if len(tick) == 1 else None, "name": next((_g(r, "company") for r in rows if _g(r, "company")), None),
         "pols": list(pols.values()), "n_pols": len(pols), "n_trades": len(rows), "est_total": round(total),
         "from": rows[0]["tx_date"], "to": rows[-1]["tx_date"],
         "seen": max((_g(r, "first_seen") or r["disclosure_date"] or "") for r in rows),
         "disclosed": max((r["disclosure_date"] or "") for r in rows),
         "uids": [r["uid"] for r in rows], "trades": [_compact(r) for r in rows[:60]],
         "alert": type_ in ALERT_TYPES, "hindsight": type_ == "hindsight"}
    e["score"] = round(BASE[type_] + extra + 3 * math.log10(max(total, 1000) / 1000), 1)
    e.update(kw)
    return e


def _clusters(rows, side):
    out, by = [], {}
    for r in rows:
        if r["side"] == side and r["tx_date"]:
            by.setdefault(r["ticker"], []).append(r)
    for t, rs in by.items():
        if len({r["politician"] for r in rs}) < CLUSTER_N:
            continue
        rs.sort(key=lambda r: r["tx_date"])
        used_until = ""
        for i in range(len(rs)):
            if rs[i]["tx_date"] <= used_until:
                continue
            end = (date.fromisoformat(rs[i]["tx_date"]) + timedelta(days=CLUSTER_DAYS - 1)).isoformat()
            win = [r for r in rs[i:] if r["tx_date"] <= end]
            pols = {r["politician"] for r in win}
            if len(pols) < CLUSTER_N:
                continue
            seen, got = None, set()   # visible once the 3rd politician's trade was disclosed
            for r in sorted(win, key=lambda r: _g(r, "first_seen") or r["disclosure_date"] or ""):
                got.add(r["politician"])
                if len(got) >= CLUSTER_N:
                    seen = _g(r, "first_seen") or r["disclosure_date"]
                    break
            days = (date.fromisoformat(win[-1]["tx_date"]) - date.fromisoformat(win[0]["tx_date"])).days + 1
            parties = {_g(r, "party") for r in win}
            verb = "bought" if side == "buy" else "sold"
            if side == "buy" and {"D", "R"} <= parties:
                pp = {(r["politician"], _g(r, "party")) for r in win}
                nd, nr = sum(1 for p in pp if p[1] == "D"), sum(1 for p in pp if p[1] == "R")
                typ, why = "bipartisan", (f"{len(pols)} politicians from both parties bought {t} within {days} day{'s' if days > 1 else ''}"
                                         f" ({nd} Democrat{'s' if nd > 1 else ''}, {nr} Republican{'s' if nr > 1 else ''})")
            else:
                typ, why = ("cluster_buy" if side == "buy" else "cluster_sell"), f"{len(pols)} politicians {verb} {t} within {days} day{'s' if days > 1 else ''}"
            e = _ev(typ, f"{'c' if side == 'buy' else 's'}:{t}:{rs[i]['tx_date']}", win,
                    f"{t} · {len(pols)} {'buyers' if side == 'buy' else 'sellers'}", why, extra=8 * (len(pols) - CLUSTER_N))
            if seen:
                e["seen"] = seen
            out.append(e)
            used_until = end
    return out


def _person_stats(c):
    """Per politician: n trades, median trade size, top-1% threshold, first trade date."""
    st = {}
    for pol, lo, hi, tx in c.execute("SELECT politician, amount_low, amount_high, tx_date FROM trades WHERE ticker IS NOT NULL"):
        s = st.setdefault(pol, {"mids": [], "first": tx or "9999"})
        lo = lo or 0
        s["mids"].append((lo + (hi or lo)) / 2.0)
        if tx and tx < s["first"]:
            s["first"] = tx
    out = {}
    for pol, s in st.items():
        m = sorted(s["mids"], reverse=True)
        n = len(m)
        out[pol] = {"n": n, "median": statistics.median(m) if m else 0, "first": s["first"],
                    "p99": max(P99_FLOOR, m[max(0, int(n * 0.01) - 1)]) if n >= P99_MIN_TRADES else None}
    return out


def _large(rows, ps):
    groups = {}
    for r in rows:
        if r["side"] not in ("buy", "sell"):
            continue
        low, p = r["amount_low"] or 0, ps.get(r["politician"]) or {}
        if low >= LARGE_LOW or (p.get("p99") and low > 0 and low >= p["p99"]):
            groups.setdefault((r["politician"], r["disclosure_date"]), []).append(r)
    out = []
    yr = (date.today() - timedelta(days=365)).isoformat()
    for (pol, disc), rs in groups.items():
        rs.sort(key=lambda r: -_mid(r))
        top, p = rs[0], ps.get(pol) or {}
        ratio = _mid(top) / p["median"] if p.get("median") else None
        verb = "Bought" if top["side"] == "buy" else "Sold"
        why = f"{verb} {top['ticker']} for {_rng(top)}"
        if ratio and ratio >= 3:
            why += f", {ratio:.0f}x {_last(pol)}'s median trade"
        if len(rs) > 1:
            why += f" (+{len(rs) - 1} more large trade{'s' if len(rs) > 2 else ''} in this filing)"
        title = f"{pol} · {'large trade' if len(rs) == 1 else f'{len(rs)} large trades'}"
        out.append(_ev("large", f"L:{pol}:{disc}", rs, title, why,
                       extra=min(15, 4 * math.log2(ratio)) if ratio and ratio > 1 else 0, politician=pol))
    return out


def _yearmax(c, events):
    """Mark large events whose top trade is the person's biggest in the past year."""
    yr = (date.today() - timedelta(days=365)).isoformat()
    for e in events:
        if e["type"] != "large":
            continue
        top = max(e["trades"], key=_mid)
        best = c.execute("SELECT MAX((COALESCE(amount_low,0)+COALESCE(amount_high,amount_low,0))/2.0) FROM trades "
                         "WHERE politician=? AND ticker IS NOT NULL AND tx_date >= ?", (e["politician"], yr)).fetchone()[0]
        if best and _mid(top) >= best and e["why"].startswith(("Bought", "Sold")):
            e["why"] = e["why"].replace(f" for {_rng(top)}", f" for {_rng(top)}: {_last(e['politician'])}'s largest trade in the past year", 1)
            e["score"] = round(e["score"] + 5, 1)


def _committee(rows, ctx):
    if not ctx:
        return []
    out = []
    since, C, M, T, L = ctx["since"], ctx["c"], ctx["m"], ctx["t"], ctx.get("labels", {})
    groups = {}
    for r in rows:
        if (r["amount_low"] or 0) < COMMITTEE_LOW or (r["tx_date"] or "") < since or r["side"] not in ("buy", "sell"):
            continue
        cs, tk = M.get(_g(r, "bioguide") or ""), T.get((r["ticker"] or "").upper())
        if not cs or not tk:
            continue
        hit = []
        for k in cs:
            cm = C.get(k.rstrip("*"))
            tags = [x for x in (cm or {}).get("tags", []) if x in tk[1:]]
            if tags:
                hit.append((cm["n"], tags, k.endswith("*")))
        if hit:
            groups.setdefault((r["politician"], r["ticker"], r["disclosure_date"]), (hit, tk[0], []))[2].append(r)
    for (pol, t, disc), (hit, ind, rs) in groups.items():
        n, tags, lead = hit[0]
        why = (f"{_last(pol)} {'leads' if lead else 'sits on'} the {n.replace('House Committee on ', 'House ').replace('Senate Committee on ', 'Senate ')}"
               f" (oversees {' and '.join(L.get(x, x) for x in tags)}) and traded {t}, classed as {ind}. Possible overlap only.")
        out.append(_ev("committee", f"K:{pol}:{t}:{disc}", rs, f"{t} · {pol}", why, extra=5 if lead else 0, politician=pol))
    return out


def _first_buys(c, rows, ps):
    out = []
    heavy = {p for p, s in ps.items() if s["n"] >= FIRST_MIN_TRADES}
    cand = [r for r in rows if r["politician"] in heavy and r["side"] == "buy" and (r["amount_low"] or 0) >= FIRST_LOW]
    for r in cand:
        if (ps[r["politician"]]["first"] or "9999") > (date.fromisoformat(r["tx_date"]) - timedelta(days=365)).isoformat():
            continue   # their record is too short to call anything "first"
        prior = c.execute("SELECT 1 FROM trades WHERE politician=? AND ticker=? AND (tx_date < ? OR (tx_date = ? AND uid < ?)) LIMIT 1",
                          (r["politician"], r["ticker"], r["tx_date"], r["tx_date"], r["uid"])).fetchone()
        if prior:
            continue
        p = ps[r["politician"]]
        out.append(_ev("first_buy", f"F:{r['uid']}", [r], f"{r['ticker']} · first buy by {r['politician']}",
                       f"{r['politician']} bought {r['ticker']} ({_rng(r)}) for the first time in {p['n']:,} disclosed trades",
                       politician=r["politician"]))
    return out


def _options(rows):
    groups = {}
    for r in rows:
        if (_g(r, "asset_type") or "") == "OP":
            groups.setdefault((r["politician"], r["disclosure_date"]), []).append(r)
    out = []
    for (pol, disc), rs in groups.items():
        tk = sorted({r["ticker"] or "?" for r in rs})
        why = f"{_last(pol)} disclosed {len(rs)} options trade{'s' if len(rs) > 1 else ''} in {', '.join(tk[:4])}{'…' if len(tk) > 4 else ''}"
        out.append(_ev("options", f"O:{pol}:{disc}", rs, f"{pol} · options", why + ". Options are leveraged bets on a price move.",
                       politician=pol))
    return out


def _bursts(c, rows):
    out = []
    by = {}
    for r in rows:
        if r["tx_date"]:
            by.setdefault(r["politician"], []).append(r)
    for pol, rs in by.items():
        if len(rs) < BURST_MIN:
            continue
        rs.sort(key=lambda r: r["tx_date"])
        used = ""
        for i in range(len(rs)):
            if rs[i]["tx_date"] <= used:
                continue
            end = (date.fromisoformat(rs[i]["tx_date"]) + timedelta(days=6)).isoformat()
            win = [r for r in rs[i:] if r["tx_date"] <= end]
            if len(win) < BURST_MIN:
                continue
            y0 = (date.fromisoformat(rs[i]["tx_date"]) - timedelta(days=365)).isoformat()
            n_year = c.execute("SELECT COUNT(*) FROM trades WHERE politician=? AND tx_date >= ? AND tx_date < ?",
                               (pol, y0, rs[i]["tx_date"])).fetchone()[0]
            norm = max(n_year / 52.0, 0.5)
            x = len(win) / norm
            if x < BURST_X:
                continue
            out.append(_ev("burst", f"B:{pol}:{rs[i]['tx_date']}", win, f"{pol} · {len(win)} trades in a week",
                           f"{len(win)} trades in 7 days, about {x:.0f}x {_last(pol)}'s usual pace of {n_year / 52.0:.1f} a week",
                           extra=min(15, 5 * math.log2(x / BURST_X + 1)), politician=pol))
            used = end
    return out


def _late(rows):
    groups = {}
    for r in rows:
        lag = _g(r, "lag_days")
        if lag is None or lag <= LATE_DAYS or (_g(r, "description") or "").startswith("From the OGE 278e"):
            continue
        groups.setdefault((r["politician"], r["disclosure_date"]), []).append(r)
    out = []
    for (pol, disc), rs in groups.items():
        lag = max(_g(r, "lag_days") or 0 for r in rs)
        why = (f"Disclosed {lag} days after the trade{'s' if len(rs) > 1 else ''}, past the 45-day limit"
               + (f" ({len(rs)} trades in this filing)" if len(rs) > 1 else ""))
        out.append(_ev("late", f"T:{pol}:{disc}", rs, f"{pol} · filed {lag - LATE_DAYS} days late", why,
                       extra=min(20, (lag - LATE_DAYS) / 15), politician=pol, lag=lag))
    return out


def _hindsight(c, rows):
    groups = {}
    for r in rows:
        if r["side"] not in ("buy", "sell") or (r["amount_low"] or 0) < HINDSIGHT_LOW or not _g(r, "est_price"):
            continue
        groups.setdefault((r["politician"], r["ticker"], r["tx_date"], r["side"]), []).append(r)
    out = []
    for (pol, t, tx, side), rs in groups.items():
        r = rs[0]
        end = (date.fromisoformat(tx) + timedelta(days=HINDSIGHT_DAYS)).isoformat()
        base = c.execute("SELECT close FROM prices WHERE ticker=? AND d <= ? ORDER BY d DESC LIMIT 1", (t, tx)).fetchone()
        px = c.execute("SELECT d, close FROM prices WHERE ticker=? AND d > ? AND d <= ? ORDER BY d", (t, tx, end)).fetchall()
        if not base or not base[0] or len(px) < 5:
            continue
        b = base[0]
        best = max(px, key=lambda p: p[1]) if side == "buy" else min(px, key=lambda p: p[1])
        mv = (best[1] / b - 1) * 100
        if (side == "buy" and mv < HINDSIGHT_MOVE) or (side == "sell" and mv > -HINDSIGHT_MOVE):
            continue
        days = (date.fromisoformat(best[0]) - date.fromisoformat(tx)).days
        why = (f"{t} {'rose' if mv > 0 else 'fell'} {abs(mv):.0f}% within {days} days after {_last(pol)} "
               f"{'bought' if side == 'buy' else 'sold'}. Hindsight: shows timing, not intent.")
        out.append(_ev("hindsight", f"H:{pol}:{t}:{tx}:{side}", rs, f"{t} · {'+' if mv > 0 else ''}{mv:.0f}% after the trade", why,
                       extra=min(25, (abs(mv) - HINDSIGHT_MOVE) / 2), politician=pol, move=round(mv, 1), move_days=days))
    return out


def events(c, rows, ctx=None, today=None):
    """rows: TRADE_SELECT rows with tx_date or disclosure_date in the last LOOKBACK_DAYS. Returns all events."""
    today = today or date.today()
    since = (today - timedelta(days=LOOKBACK_DAYS)).isoformat()
    rows = [r for r in rows if max(r["tx_date"] or "", r["disclosure_date"] or "") >= since]
    listed = [r for r in rows if r["ticker"] and most_bought.kind(r)]
    recent_tx = [r for r in listed if (r["tx_date"] or "") >= since]
    ps = _person_stats(c)
    ev = _clusters(recent_tx, "buy") + _clusters(recent_tx, "sell") + _large(listed, ps)
    _yearmax(c, ev)
    ev += _committee(listed, ctx) + _first_buys(c, listed, ps) + _options(rows) + _bursts(c, [r for r in rows if (r["tx_date"] or "") >= since])
    ev += _late(rows) + _hindsight(c, listed)
    ev.sort(key=lambda e: e["seen"] or "", reverse=True)
    return ev


def rank_key(e, today=None):
    """Score with a gentle recency decay: a day of age costs one point."""
    today = today or date.today()
    try:
        age = (today - date.fromisoformat((e["disclosed"] or "")[:10])).days
    except ValueError:
        age = 99
    return e["score"] - max(0, age)


def summary(e):
    """The list view of an event (no trade rows)."""
    return {k: v for k, v in e.items() if k not in ("trades", "uids")} | {"pols": e["pols"][:5]}


def recent(c, rows, ctx=None, days=WINDOW_DAYS):
    """Events disclosed in the last `days`, capped per type, best first (full events, with trade rows)."""
    cut = (date.today() - timedelta(days=days)).isoformat()
    ev = [e for e in events(c, rows, ctx) if (e["disclosed"] or "") >= cut]
    out, per = [], {}
    for e in sorted(ev, key=lambda e: -e["score"]):
        if per.get(e["type"], 0) >= TYPE_CAP:
            continue
        per[e["type"]] = per.get(e["type"], 0) + 1
        e["rank"] = round(rank_key(e), 1)
        out.append(e)
    out.sort(key=lambda e: -e["rank"])
    return out


def for_new(c, rows, new_rows, sent, ctx=None):
    """Alertable events (ALERT_TYPES) that involve at least one of new_rows and haven't been alerted (keys in `sent`)."""
    new = {r["uid"] for r in new_rows}
    return [e for e in events(c, rows, ctx) if e["alert"] and e["key"] not in sent and new & set(e["uids"])]
