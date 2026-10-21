"""Estimated portfolios rebuilt from disclosed trades.

Disclosures give a dollar range per trade, not shares or prices, so everything here is an ESTIMATE:

* trade size   = midpoint of the disclosed range
* shares       = trade size / split-adjusted daily close on the trade date (Yahoo)
* sells        = House "Sale" (full) sells the whole estimated position; partial / other sales sell
                 midpoint / close shares, never more than the estimated position
* holdings     = only positions built from disclosed buys; stock held before the disclosure window is unknown
* value        = shares x latest split-adjusted close, forward-filled over market holidays and gaps
* performance  = time-weighted return (daily returns with buys/sells removed as cash flows), so a large new
                 purchase doesn't look like a gain; P&L $ = change in value minus net money put in
* win rate     = share of priced buys whose price was higher WIN_DAYS later, and sells whose price was lower
* avg delay    = mean days between trade date and disclosure date (all trades, priced or not)
"""
import bisect
from datetime import date, timedelta

WIN_DAYS = 30
TRADABLE = "(t.asset_type IS NULL OR t.asset_type IN ('ST','EF'))"


def _load(c, name):
    trades = c.execute(f"""SELECT t.ticker, t.side, t.tx_type, t.source, t.tx_date, t.amount_low, t.amount_high, t.est_adj
        FROM trades t WHERE t.politician=? AND t.ticker IS NOT NULL AND t.est_adj > 0 AND t.side IN ('buy','sell')
        AND {TRADABLE} ORDER BY t.tx_date, t.side""", (name,)).fetchall()
    return [dict(r) for r in trades]


def _prices(c, tickers, start):
    px = {}
    for i in range(0, len(tickers), 400):
        chunk = tickers[i:i + 400]
        q = ",".join("?" * len(chunk))
        for r in c.execute(f"SELECT ticker, d, adjclose FROM prices WHERE ticker IN ({q}) AND d >= ? AND adjclose > 0 ORDER BY d",
                           (*chunk, start)):
            px.setdefault(r["ticker"], ([], []))
            px[r["ticker"]][0].append(r["d"])
            px[r["ticker"]][1].append(r["adjclose"])
    return px


def _mid(t):
    lo = t["amount_low"] or 0
    hi = t["amount_high"] or lo
    return (lo + hi) / 2.0


def compute(c, name, today=None):
    today = today or date.today().isoformat()
    tr = _load(c, name)
    lag = c.execute("""SELECT AVG(julianday(disclosure_date) - julianday(tx_date)) a, COUNT(*) n FROM trades
        WHERE politician=? AND tx_date IS NOT NULL AND disclosure_date >= tx_date""", (name,)).fetchone()
    out = {"name": name, "avg_delay": round(lag["a"], 1) if lag["a"] is not None else None, "n_priced": len(tr),
           "value": 0.0, "pnl": 0.0, "invested": 0.0, "holdings": [], "series": {"d": [], "v": [], "p": [], "i": []},
           "win_rate": None, "win_n": 0, "edge": None}
    if not tr:
        return out
    tickers = sorted({t["ticker"] for t in tr})
    start = tr[0]["tx_date"]
    px = _prices(c, tickers, (date.fromisoformat(start) - timedelta(days=7)).isoformat())

    def price_on(tk, d, after=False):
        s = px.get(tk)
        if not s:
            return None
        if after:
            j = bisect.bisect_left(s[0], d)
            return s[1][j] if j < len(s[0]) else None
        j = bisect.bisect_right(s[0], d) - 1
        return s[1][j] if j >= 0 else None

    # --- win rate: did the price move the trader's way within WIN_DAYS?
    cutoff = (date.fromisoformat(today) - timedelta(days=WIN_DAYS)).isoformat()
    wins = n = 0
    edge = 0.0
    for t in tr:
        if t["tx_date"] > cutoff:
            continue
        later = price_on(t["ticker"], (date.fromisoformat(t["tx_date"]) + timedelta(days=WIN_DAYS)).isoformat(), after=True)
        if not later:
            continue
        r = later / t["est_adj"] - 1
        if abs(r) > 3:  # bad print / unhandled corporate action
            continue
        s = r if t["side"] == "buy" else -r
        n += 1
        wins += s > 0
        edge += s
    if n:
        out.update(win_rate=round(100 * wins / n, 1), win_n=n, edge=round(100 * edge / n, 2))

    # --- replay trades over every trading day
    days = sorted({d for s in px.values() for d in s[0] if start <= d <= today})
    if not days or days[-1] < today:
        days.append(today)
    sh, cost, last = {}, {}, {}
    ptr = {tk: 0 for tk in px}
    invested = 0.0
    idx, prev_v = 1.0, 0.0
    ser_d, ser_v, ser_p, ser_i = [], [], [], []
    ti = 0
    for d in days:
        for tk, s in px.items():  # advance forward-filled prices
            p = ptr[tk]
            while p < len(s[0]) and s[0][p] <= d:
                last[tk] = s[1][p]
                p += 1
            ptr[tk] = p
        flow = 0.0
        while ti < len(tr) and tr[ti]["tx_date"] <= d:
            t = tr[ti]
            ti += 1
            tk, price = t["ticker"], t["est_adj"]
            last.setdefault(tk, price)
            if t["side"] == "buy":
                q = _mid(t) / price
                sh[tk] = sh.get(tk, 0) + q
                cost[tk] = cost.get(tk, 0) + q * price
                flow += q * last[tk]
                invested += q * price
            else:
                held = sh.get(tk, 0)
                if held <= 0:
                    continue
                full = t["source"] == "house_clerk" and (t["tx_type"] or "") == "Sale"
                q = held if full else min(held, _mid(t) / price)
                cost[tk] = cost.get(tk, 0) * (1 - q / held)
                sh[tk] = held - q
                flow -= q * last[tk]
                invested -= q * price
        v = sum(q * last.get(tk, 0) for tk, q in sh.items() if q > 1e-9)
        if prev_v > 0:
            r = (v - flow) / prev_v - 1
            idx *= 1 + max(-0.5, min(1.0, r))
        prev_v = v
        ser_d.append(d)
        ser_v.append(round(v, 2))
        ser_p.append(round(v - invested, 2))
        ser_i.append(round(idx, 6))
    hold = []
    for tk, q in sh.items():
        if q <= 1e-6 or tk not in last:
            continue
        val = q * last[tk]
        hold.append({"ticker": tk, "shares": round(q, 4), "value": round(val, 2), "cost": round(cost.get(tk, 0), 2),
                     "price": last[tk], "gain_pct": round(100 * (val / cost[tk] - 1), 2) if cost.get(tk) else None})
    total = sum(h["value"] for h in hold)
    for h in hold:
        h["weight"] = round(100 * h["value"] / total, 2) if total else 0
    hold.sort(key=lambda h: -h["value"])
    out.update(value=round(total, 2), pnl=round(total - invested, 2), invested=round(invested, 2), holdings=hold,
               series={"d": ser_d, "v": ser_v, "p": ser_p, "i": ser_i}, first=start)
    return out


PERIODS = {"1W": 7, "1M": 30, "3M": 91, "YTD": None, "1Y": 365, "5Y": 1826, "ALL": 36500}


def period_stats(s, key, today=None):
    """Return (pnl $, twr %) for a period over a computed series."""
    d = s["d"]
    if not d:
        return None, None
    today = today or d[-1]
    if key == "YTD":
        since = today[:4] + "-01-01"
    else:
        since = (date.fromisoformat(today) - timedelta(days=PERIODS[key])).isoformat()
    j = max(0, bisect.bisect_left(d, since) - 1)
    if since <= d[0]:
        j = 0
        base_i, base_p = 1.0, 0.0
    else:
        base_i, base_p = s["i"][j], s["p"][j]
    return round(s["p"][-1] - base_p, 2), round(100 * (s["i"][-1] / base_i - 1), 2) if base_i else None


def spark(s, n=40, days=365):
    d = s["d"]
    if not d:
        return []
    since = (date.fromisoformat(d[-1]) - timedelta(days=days)).isoformat()
    j = bisect.bisect_left(d, since)
    v = s["v"][j:]
    if len(v) <= n:
        return v
    step = (len(v) - 1) / (n - 1)
    return [v[round(k * step)] for k in range(n)]
