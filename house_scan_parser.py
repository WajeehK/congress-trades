"""Transactions from scanned (paper) House PTRs, read from the cell OCR text made by box/house_ocr_box.py.

The OCR step stores, per transaction-grid row: owner, asset text, the two date cells, and the ink (ticks / X marks,
ruled lines removed) in each type and amount checkbox. This module turns that into trades, with the same lenience
as the OGE 278-T parser: OCR-damaged dates are repaired (missing separators, 2-digit years, letters read as digits),
a date that can't be recovered is inferred from its neighbours on the same form (paper PTRs list trades in blocks
that share dates), and the ticked box is chosen relative to each column's empty-box baseline.
"""
import re
from datetime import date, timedelta

AMOUNTS = [(1001, 15000), (15001, 50000), (50001, 100000), (100001, 250000), (250001, 500000), (500001, 1000000),
           (1000001, 5000000), (5000001, 25000000), (25000001, 50000000), (50000001, None), (1000001, None)]
TYPES = {2: ["Purchase", "Sale"], 3: ["Purchase", "Sale", "Exchange"], 4: ["Purchase", "Sale", "Sale (partial)", "Exchange"]}
OWNERS = {"SP": "Spouse", "JT": "Joint", "DC": "Dependent child"}
_DIG = str.maketrans({"O": "0", "o": "0", "D": "0", "Q": "0", "I": "1", "l": "1", "|": "1", "i": "1", "Z": "2", "z": "2",
                      "S": "5", "s": "5", "B": "8", "g": "9", "q": "9", "G": "6", "b": "6", "T": "7"})
SKIP_ASSET = re.compile(r"example|mega corp|provide full name|full asset name|ticker symbol", re.I)


def amount_text(lo, hi):
    if hi is None:
        return "Spouse/DC Over $1,000,000" if lo == 1000001 else f"Over ${lo - 1:,}"
    return f"${lo:,} - ${hi:,}"


def parse_date(s, lo, hi):
    """Lenient MM/DD/YY(YY) within [lo, hi]."""
    if not s:
        return None
    s = s.translate(_DIG)
    cands = []
    m = re.search(r"(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{2,4})", s)
    if m:
        cands.append(m.groups())
    d = re.sub(r"\D", "", s)
    if len(d) == 8:
        cands.append((d[:2], d[2:4], d[4:]))
    if len(d) == 6:
        cands.append((d[:2], d[2:4], d[4:]))
    if len(d) == 7:   # one separator read as a digit or a single-digit month
        cands += [(d[0], d[1:3], d[3:]), (d[:2], d[2], d[3:])]
    if len(d) == 5:
        cands += [(d[0], d[1:3], d[3:]), (d[:2], d[2], d[3:])]
    if len(d) == 4:   # 9/5/26
        cands.append((d[0], d[1], d[2:]))
    for mo, dd, yy in cands:
        try:
            y = int(yy)
            if len(yy) == 4 and not 2000 <= y <= 2099:
                y = 2000 + y % 100       # "2O26" -> 2026 after translation, "1026" -> 2026
            elif len(yy) == 3:
                y = 2000 + y % 100
            elif y < 100:
                y += 2000
            dt = date(y, int(mo), int(dd))
        except ValueError:
            continue
        if lo <= dt <= hi:
            return dt
        # year misread (6 <-> 5, 8): keep month/day, take the year that fits
        for y2 in (hi.year, hi.year - 1):
            try:
                d2 = date(y2, int(mo), int(dd))
            except ValueError:
                continue
            if lo <= d2 <= hi:
                return d2
    return None


def _pick(vals, base):
    d = [v - b for v, b in zip(vals, base)]
    if not d:
        return None
    order = sorted(range(len(d)), key=lambda i: -d[i])
    top = d[order[0]]
    second = d[order[1]] if len(order) > 1 else 0
    if top >= 0.025 and top >= 2.2 * max(second, 0) + 0.004:
        return order[0]
    return None


def clean_asset(a):
    a = re.sub(r"[“”‘’`~_=<>{}\[\]—–]+", " ", a or "")
    a = re.sub(r"\s+", " ", a).strip(" .,;:/\\-'\"|")
    a = re.sub(r"(\s+[a-z]{1,2}|\s+[^\w\s&().]+)+$", "", a)   # trailing OCR crumbs ("... LP Bn", "... ;")
    return a.strip(" .,;:/\\-'\"")


def match_name(a):
    """Asset text trimmed for company-name matching ("MASTERCARD INCORPORATED CLA" -> "MASTERCARD INCORPORATED")."""
    a = re.sub(r"[-\s]+(CL(ASS)?\s*-?[ABC]|COM(MON)?(\s*(STK|STOCK|SHS))?|COMCL[ABC]|SHS|ORD|NEW|ADR|SPONSORED ADR)\b.*$", "",
               a or "", flags=re.I)
    return re.sub(r"-CL[ABC]$", "", a.strip(), flags=re.I)


def asset_ok(a):
    letters = sum(ch.isalpha() for ch in a)
    words = [w for w in re.findall(r"[A-Za-z&]{2,}", a)]
    return letters >= 4 and letters >= 0.6 * len(a.replace(" ", "")) and len(words) >= 1 and not SKIP_ASSET.search(a)


def parse(text, filed, known_tickers=frozenset()):
    """-> list of trades (dict like ptr_parser's) from one filing's OCR cell text; filed = filing date."""
    hi, lo = filed, filed - timedelta(days=420)
    rows = []
    for ln in text.splitlines():
        if not ln.startswith("R|"):
            continue
        p = ln.split("|")
        if len(p) < 9:
            continue
        rows.append({"page": int(p[1]), "row": int(p[2]), "owner": p[3], "asset": p[4], "d1": p[5], "d2": p[6],
                     "ti": [float(x) for x in p[7].split(",") if x], "ai": [float(x) for x in p[8].split(",") if x]})
    if not rows:
        return []
    # empty-box baseline per column (layout = number of type/amount columns): residual noise only, capped
    base = {}
    for r in rows:
        k = (len(r["ti"]), len(r["ai"]))
        b = base.setdefault(k, [[], []])
        b[0].append(r["ti"]); b[1].append(r["ai"])
    for k, (ts, as_) in base.items():
        base[k] = ([min(min(c), 0.015) for c in zip(*ts)], [min(min(c), 0.015) for c in zip(*as_)])  # lines are already removed
    out = []
    for r in rows:
        k = (len(r["ti"]), len(r["ai"]))
        ti = _pick(r["ti"], base[k][0])
        ai = _pick(r["ai"], base[k][1])
        asset = clean_asset(r["asset"])
        r["tx"] = parse_date(r["d1"], lo, hi)
        r["nd"] = parse_date(r["d2"], lo, hi)
        if ti is None or ai is None or not asset_ok(asset) or k[0] not in TYPES:
            r["skip"] = True
            continue
        a_lo, a_hi = AMOUNTS[ai] if ai < len(AMOUNTS) else (None, None)
        if k[1] == 10 and ai == 9:   # older form without the spouse column: J = over $50M
            a_lo, a_hi = 50000001, None
        r.update(tx_type=TYPES[k[0]][ti], amount_low=a_lo, amount_high=a_hi, asset_clean=asset)
        out.append(r)
    # neighbour inference for unreadable trade dates: same form, nearest readable row (prefer the one above)
    for i, r in enumerate(out):
        if r["tx"]:
            continue
        prev = next((o for o in reversed(out[:i]) if o["tx"]), None)
        nxt = next((o for o in out[i + 1:] if o["tx"]), None)
        cand = prev if prev and (not nxt or prev["tx"] == nxt["tx"] or prev["page"] == r["page"]) else nxt
        if cand and (not r["nd"] or cand["tx"] <= r["nd"]):
            r["tx"], r["inferred"] = cand["tx"], True
    res = []
    for r in out:
        if not r["tx"]:
            continue
        asset = r["asset_clean"]
        tick = None
        m = re.search(r"\(([A-Z][A-Z.\-]{0,6})\)", asset)
        if m:
            tick = m.group(1)
        else:
            m = re.search(r"\s([A-Z]{1,5}(?:\.[AB])?)$", asset)
            if m and m.group(1) in known_tickers and len(asset.split()) >= 3:
                tick = m.group(1)
        own = re.sub(r"[^A-Z]", "", r["owner"].upper())
        own = next((v for k2, v in OWNERS.items() if own.startswith(k2) or own == k2[::-1]), "Self")
        etf = re.search(r"\bETF\b|ISHARES|SPDR|VANGUARD|INVESCO|PROSHARES|VANECK|\bFUND\b|\bTR\b", asset, re.I)
        bond = re.search(r"\b(BOND|BD|NOTE|NOTES|MUN|MTG|REV|GO|TREAS|MUNI|BILL|BILLS|CD)\b|%", asset, re.I)
        res.append({"owner": own, "ticker": tick, "asset": asset,
                    "asset_type": "EF" if etf and tick else ("BOND" if bond and not tick else ("ST" if tick else None)),
                    "tx_type": r["tx_type"], "tx_date": r["tx"].isoformat(),
                    "amount": amount_text(r["amount_low"], r["amount_high"]), "amount_low": r["amount_low"],
                    "amount_high": r["amount_high"],
                    "description": "Read from a scanned paper filing (OCR)" + ("; trade date inferred from neighbouring rows" if r.get("inferred") else "")})
    return res
