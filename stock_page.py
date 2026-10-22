"""Stock page data: compact daily-close series plus estimated current holders (shared by box API and static export)."""
from datetime import date, timedelta

MAX_YEARS = 6


def _sig(x):
    if x is None:
        return None
    return float(f"{x:.5g}")


def series(c, ticker, first_tx=None):
    """{d0, dd, c}: first date, day deltas, closes. Covers the ticker's trades (60 days before the first one) up to
    MAX_YEARS back, and at least 3 years."""
    floor = date.today() - timedelta(days=365 * MAX_YEARS)
    start = date.today() - timedelta(days=365 * 3)
    if first_tx:
        try:
            start = min(start, date.fromisoformat(first_tx) - timedelta(days=60))
        except ValueError:
            pass
    start = max(start, floor)
    rows = c.execute("SELECT d, close FROM prices WHERE ticker=? AND d>=? AND close>0 ORDER BY d", (ticker, start.isoformat())).fetchall()
    if not rows:
        return None
    d0 = date.fromisoformat(rows[0][0])
    dd, cl, prev = [], [], d0
    for d, cv in rows:
        dt = date.fromisoformat(d)
        dd.append((dt - prev).days)
        prev = dt
        cl.append(_sig(cv))
    dd[0] = 0
    return {"d0": d0.isoformat(), "dd": dd, "c": cl}


def holder_rows(ticker, name, pf, meta):
    out = []
    for h in pf.get("holdings") or []:
        if h.get("ticker") == ticker and (h.get("value") or 0) > 0:
            out.append({"politician": name, "bioguide": meta.get("bioguide"), "party": meta.get("party"),
                        "chamber": meta.get("chamber"), "value": round(h["value"]), "shares": round(h.get("shares") or 0, 2),
                        "gain_pct": h.get("gain_pct"), "weight": h.get("weight")})
    return out
