"""Ticker corrections applied to every trade row (on insert and once per start-up over the stored rows).

Filers pick tickers from drop-downs or type them, and OCR mangles a few. Each fix keys on the reported ticker *and*
the asset text, so a correct use of the same symbol is left alone. A target of None means the asset has no
exchange ticker (private company or fund): the row keeps its name and the app shows a glyph instead of a logo.
"""
import re

# (reported ticker, asset-text regex) -> corrected ticker (None = not exchange-listed)
FIXES = [
    ("APPL", r"apple inc", "AAPL"),                         # typo; "Appell Pete Corp (APPL)" is a real OTC symbol and stays
    ("--", r"berry global.*exchanged.*amcor", "AMCR"),      # Berry Global shares exchanged into Amcor plc in the 2025 merger
    ("AMI", r"advanced machine intelligence", None),        # AMI Labs: private AI start-up, no listed shares
    ("ZOOM", r"zoom", "ZM"),                                # "Zoom Technologies (ZOOM)" is a stale drop-down entry; ZOOM has no 2025 quotes -> Zoom Communications
    ("ICAPITAL", r"partners.*fund|l\.?p\.?", None),         # iCapital feeder LP: private fund
]
_FIXES = [(t, re.compile(rx, re.I), new) for t, rx, new in FIXES]

# asset-text rules for rows whose ticker is missing or misread (e.g. OCR reading "CL C" as Citigroup "C")
_NOT_EQUITY = re.compile(r"\bnote\b|coupon|%|\bbond\b|depositary|preferred", re.I)
_ALPHA = re.compile(r"^\s*alphabet\s*inc", re.I)
_CLASS_C = re.compile(r"cl(?:ass)?[\s.-]*(?:class\s*)?c\b|cl-?c\b|clc\b|capital stock", re.I)


def _squash(s):
    return re.sub(r"[^a-z]", "", (s or "").lower())


def corrected(ticker, asset):
    """Return (ticker, changed?) for one row."""
    a = asset or ""
    for t, rx, new in _FIXES:
        if ticker == t and rx.search(a):
            return new, True
    if _ALPHA.match(a) or _squash(a).startswith("alphabetinc"):
        if _NOT_EQUITY.search(a) or ticker in ("GOOGM", "GOOGN"):
            return ticker, False
        sq = _squash(a)
        want = "GOOG" if (_CLASS_C.search(a) or re.search(r"alphabetinc(?:shs)?(?:cap(?:ital)?st[a-z]*)?(?:class|cl)c", sq)) else "GOOGL"
        if ticker != want and ticker in (None, "", "C", "GOOG", "GOOGL", "--"):
            # only class-C text overrides an existing GOOGL, and only missing/misread symbols are filled in
            if ticker in ("GOOG", "GOOGL") and want == "GOOGL":
                return ticker, False
            return want, True
    return ticker, False


def apply(row):
    t, changed = corrected(row.get("ticker"), row.get("asset"))
    if changed:
        row["ticker"] = t
    return row


def migrate(c):
    """Fix stored rows; returns [(old, new, asset, n)]."""
    done = {}
    cur = c.execute("SELECT rowid, ticker, asset FROM trades WHERE ticker IN (%s) OR ticker IS NULL OR ticker = '' OR asset LIKE 'alphabet%%'"
                    % ",".join("?" * len({f[0] for f in FIXES} | {"C", "GOOG", "GOOGL"})),
                    tuple({f[0] for f in FIXES} | {"C", "GOOG", "GOOGL"}))
    for tid, t, a in cur.fetchall():
        new, changed = corrected(t, a)
        if changed and new != t:
            c.execute("UPDATE trades SET ticker = ?, est_price = NULL, est_adj = NULL, est_date = NULL WHERE rowid = ?", (new, tid))
            k = (t, new, (a or "")[:60])
            done[k] = done.get(k, 0) + 1
    return [(*k, n) for k, n in done.items()]
