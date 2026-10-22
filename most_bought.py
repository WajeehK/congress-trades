"""'Most bought' ranking shared by the box app and the static GitHub Pages export.

Ranks tickers by purchases whose trade date falls in the last N days:
  1. distinct politicians who bought (so one heavy trader, e.g. Trump's ~30k OGE rows, counts once)
  2. number of buy transactions
  3. estimated $ bought (sum of amount-range midpoints)
Stocks only by default: rows without a ticker, options, bonds/notes/treasuries/munis/preferreds and
funds/ETFs are dropped; ETFs can be included with include_etf=True.
"""
import re
from datetime import date, timedelta

WINDOWS = {"30": 30, "90": 90, "365": 365}
FUND_RE = re.compile(r"\bETFs?\b|\bETN\b|\bFUNDS?\b|ISHARES|\bSPDR\b|VANGUARD|PROSHARES|DIREXION|INVESCO QQQ|"
                     r"SELECT SECTOR|\bINDEX\b|\bPORTFOLIO\b|GRAYSCALE|\bWISDOMTREE\b|\bSCHWAB (US|U\.S\.)|ARK \w+ INNOVATION", re.I)
BOND_RE = re.compile(r"\d+(\.\d+)?\s*%|\bDUE\b|\bNOTES?\b|\bBONDS?\b|\bBDS\b|\bDEBS?\b|TREASUR|\bT-?BILL|\bMUNI|"
                     r"\bMUN\b|\bRFDG\b|\bREV\b|\bPFD\b|\bPREFERRED\b|\bPERP\b|\bCD\b|CERTIFICATE OF DEPOSIT", re.I)
STOCK_TYPES = {None, "", "ST"}
FUND_TYPES = {"EF", "ET", "MF"}


def kind(r):
    """'stock', 'etf' or None (excluded)."""
    t = (r["ticker"] or "").strip()
    if not t or not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", t.upper()) or t.startswith("$"):
        return None
    at = r["asset_type"] or None
    asset, comp = r["asset"] or "", r["company"] or ""
    if at in FUND_TYPES or FUND_RE.search(comp) or (not comp and FUND_RE.search(asset)):
        return "etf"
    if at not in STOCK_TYPES:
        return None
    if BOND_RE.search(asset) and not comp:  # unmatched debt line items
        return None
    if re.search(r"\d+(\.\d+)?\s*%|\bDUE\b|\bNOTES?\b|\bBONDS?\b|TREASUR|\bPFD\b|\bPREFERRED\b", asset, re.I):
        return None  # e.g. "Apple Inc 3.45% notes due 2029": the issuer has a ticker, the asset is debt
    return "stock"


def mid(r):
    lo = r["amount_low"] or 0
    hi = r["amount_high"] or lo
    return (lo + hi) / 2.0


def rank(rows, days, include_etf=False, limit=50, today=None):
    """rows: dict-like trade rows with ticker, asset, asset_type, company, side, tx_date, politician, bioguide,
    amount_low, amount_high, cur_price, pct_since."""
    since = ((today or date.today()) - timedelta(days=days)).isoformat()
    g = {}
    for r in rows:
        if r["side"] != "buy" or (r["tx_date"] or "") < since:
            continue
        k = kind(r)
        if k is None or (k == "etf" and not include_etf):
            continue
        tk = r["ticker"].upper().replace("-", ".")
        e = g.get(tk)
        if e is None:
            e = g[tk] = {"ticker": tk, "name": None, "kind": k, "n_buys": 0, "est_total": 0.0, "pols": {},
                         "cur_price": None, "_w": 0.0, "_wp": 0.0, "latest": ""}
        m = mid(r)
        e["n_buys"] += 1
        e["est_total"] += m
        e["name"] = e["name"] or r["company"]
        e["_asset"] = e.get("_asset") or r["asset"]
        if r["cur_price"]:
            e["cur_price"] = r["cur_price"]
        if r["pct_since"] is not None:
            w = max(m, 1.0)
            e["_w"] += w
            e["_wp"] += w * r["pct_since"]
        e["latest"] = max(e["latest"], r["tx_date"] or "")
        p = e["pols"].setdefault(r["politician"], {"name": r["politician"], "bioguide": r["bioguide"], "n": 0, "amt": 0.0})
        p["n"] += 1
        p["amt"] += m
        p["bioguide"] = p["bioguide"] or r["bioguide"]
    out = []
    for e in g.values():
        pols = sorted(e["pols"].values(), key=lambda p: (-p["amt"], -p["n"], p["name"]))
        out.append({
            "ticker": e["ticker"], "name": e["name"] or _clean(e.get("_asset")), "kind": e["kind"],
            "n_pols": len(pols), "n_buys": e["n_buys"], "est_total": round(e["est_total"]),
            "chg": round(e["_wp"] / e["_w"], 2) if e["_w"] else None, "cur_price": e["cur_price"], "latest": e["latest"],
            "pols": [{"name": p["name"], "bioguide": p["bioguide"], "n": p["n"]} for p in pols[:4]],
        })
    out.sort(key=lambda x: (-x["n_pols"], -x["n_buys"], -x["est_total"], x["ticker"]))
    return out[:limit]


def _clean(a):
    return re.sub(r"\s*\[[A-Z]{2}\]\s*$|\s*\([A-Z0-9.\-/$]{1,10}\)\s*$", "", a or "").strip() or None


def build(rows, limit=50, today=None):
    """Precomputed payload for every window, stocks-only and with ETFs."""
    rows = list(rows)
    since = ((today or date.today()) - timedelta(days=max(WINDOWS.values()))).isoformat()
    rows = [r for r in rows if r["side"] == "buy" and (r["tx_date"] or "") >= since]
    return {"windows": {w: {"days": d, "since": ((today or date.today()) - timedelta(days=d)).isoformat(),
                            "stocks": rank(rows, d, False, limit, today), "all": rank(rows, d, True, limit, today)}
                        for w, d in WINDOWS.items()}}
