"""Parser for OGE Form 278-T (Executive Branch Periodic Transaction Report) PDFs.

The President's 278-T reports are scanned paper forms with an OCR text layer (Adobe Paper Capture), so the text is
noisy ("lourchoso" = purchase, "5122/2026" = 5/22/2026, "S1 ooo 001" = $1,000,001). This parser is deliberately
conservative: a row is kept only if it has a recognisable transaction type, a valid date inside the plausible window
for the filing, and an amount that maps onto one of the official OGE value bands. Everything else is dropped.
"""
import re
import subprocess
from datetime import date, timedelta

BANDS = [(1001, 15000), (15001, 50000), (50001, 100000), (100001, 250000), (250001, 500000), (500001, 1000000),
         (1000001, 5000000), (5000001, 25000000), (25000001, 50000000)]
LOWS = {lo: (lo, hi) for lo, hi in BANDS}
HIGHS = {hi: (lo, hi) for lo, hi in BANDS}


def band_text(lo, hi):
    if hi is None:
        return "Over $50,000,000"
    return f"${lo:,} - ${hi:,}"


def _amount(seg):
    if re.search(r"over\s*\$?\s*50", seg, re.I):
        return 50000001, None
    s = re.sub(r"[SsÂ¢<](?=[\d.,:oODnN ]{2})", "$", seg)
    s = re.sub(r"(?<=[\d$.,: ])[oODnNaQ](?=[\doODnNaQ.,: ]|$)", "0", s)
    s = re.sub(r"(?<=[\d$])[oODnNaQ]", "0", s)
    s = s.replace("l", "1").replace("I", "1").replace("(", "").replace(")", "")
    clusters = [c for c in re.findall(r"\d[\d ,.:]*\d|\d", s)]
    nums = [int(re.sub(r"[ ,.:]", "", c)) for c in clusters if re.sub(r"[ ,.:]", "", c)]
    for n in nums:
        if n in LOWS:
            return LOWS[n]
    for n in nums:
        if n in HIGHS:
            return HIGHS[n]
    for n in nums:
        st = str(n)
        for lo, hi in BANDS:
            if st == f"{lo}{hi}":
                return lo, hi
    # fuzzy: look at the first cluster's leading group and number of groups
    if not clusters:
        return None
    c = clusters[0].strip()
    groups = [g for g in re.split(r"[ ,.:]+", c) if g]
    if not groups:
        return None
    g0, ng = groups[0], len(groups)
    if len(groups) == 1 and len(g0) >= 4:  # separators lost: use digit count
        L = len(g0)
        g0, ng = g0[:L - 3 * ((L - 1) // 3)], 1 + (L - 1) // 3
    table2 = {"1": 1001, "15": 15001, "16": 15001, "18": 15001, "13": 15001, "50": 50001, "60": 50001, "5": 50001,
              "100": 100001, "190": 100001, "109": 100001, "250": 250001, "260": 250001, "280": 250001, "500": 500001,
              "600": 500001, "590": 500001, "509": 500001}
    table3 = {"1": 1000001, "5": 5000001, "6": 5000001, "25": 25000001, "26": 25000001}
    lo = (table3 if ng >= 3 else table2).get(g0)
    return LOWS[lo] if lo else None


def _type(tok):
    t = re.sub(r"[^a-z]", "", tok.lower())
    if not t:
        return None
    if "xch" in t or "exchan" in t:
        return "Exchange"
    if re.search(r"(ur|rc|rch|chas|cha|has|haso|hase|chs|ulso|chos|ase$|aso$|ose$|oso$)", t) and not t.startswith("sa"):
        return "Purchase"
    if re.search(r"^(sal|sa|al|so|ale|aie|salo|sele)", t) or t in ("sale", "salo", "sa1e"):
        return "Sale"
    return None


def _dates(tok, lo, hi):
    """All valid dates for an OCR'd m/d/y token, allowing '1' or 'l' to stand in for '/'."""
    s = re.sub(r"[^0-9/]", "", tok.replace("l", "1").replace("I", "1").replace("|", "/"))
    out = set()
    if not s or len(s) < 6:
        return out
    pos = [i for i, c in enumerate(s) if c == "1"]
    cands = {s}
    # try replacing up to two '1's with '/'
    for i in pos:
        cands.add(s[:i] + "/" + s[i + 1:])
        for j in pos:
            if j > i:
                cands.add(s[:i] + "/" + s[i + 1:j] + "/" + s[j + 1:])
    for c in cands:
        m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})", c)
        if not m:
            continue
        mo, dy, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if yr < 100:
            yr += 2000
        try:
            d = date(yr, mo, dy)
        except ValueError:
            continue
        if lo <= d <= hi:
            out.add(d)
    return out


DATE_RE = re.compile(r"(?<![\w$])([0-9lI|]{1,2}[/1lI|][0-9lI|]{1,3}[/1lI|]?[0-9]{2,4})(?![\w])")
YN_RE = re.compile(r"\b(y[eo0][sa5]|v[eoa0][sa5]|ves|vas|yos|yas|n[o0])\b", re.I)


def parse_lines(lines, filed):
    """lines: text lines (one transaction per line, layout mode or OCR). filed: date the filing was received."""
    lo, hi = filed - timedelta(days=200), filed + timedelta(days=3)
    rows = []
    prev_text = ""
    for raw in lines:
        line = raw.replace("\u2022", "-").replace("■", " ").replace("·", "-").strip()
        if not line:
            continue
        # find the right-most date token that parses
        best = None
        for m in DATE_RE.finditer(line):
            ds = _dates(m.group(1), lo, hi)
            if ds:
                best = (m, ds)
        if not best:
            if len(line) > 12 and not re.search(r"(OGE|Form|Page|Note|Filer|Transactions|Description|Notification|Received|Days Ago|Amount|instruct)", line, re.I):
                prev_text = line
            continue
        m, ds = best
        before, after = line[:m.start()].rstrip(), line[m.end():]
        amt = _amount(after)
        if not amt:
            continue
        # type = last word(s) before the date
        words = before.split()
        tx = None
        cut = len(words)
        for k in range(len(words) - 1, max(-1, len(words) - 4), -1):
            tx = _type(words[k])
            if tx:
                cut = k
                break
        if not tx:
            continue
        desc_words = words[:cut]
        num = None
        if desc_words and re.fullmatch(r"\d{1,4}\.?", desc_words[0]):
            num = int(desc_words[0].rstrip("."))
            desc_words = desc_words[1:]
        desc = " ".join(desc_words).strip(" -~•.'\"`|")
        desc = re.sub(r"\s{2,}", " ", desc)
        if len(desc) < 4 and prev_text:
            desc = re.sub(r"^\d{1,4}\s+", "", prev_text).strip()
        prev_text = ""
        if len(desc) < 3:
            continue
        d = max(ds)  # prefer later date if ambiguous
        yn = YN_RE.search(after)
        rows.append({"n": num, "asset": desc, "tx_type": tx, "tx_date": d.isoformat(), "amount_low": amt[0],
                     "amount_high": amt[1], "amount": band_text(*amt),
                     "late": bool(yn and yn.group(1).lower()[0] in "yv")})
    return rows


def pdf_lines(path):
    txt = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True).stdout
    return txt.splitlines()


def number_of(line):
    m = re.match(r"\s*\W{0,3}\s*(\d{1,4})[s.]?\s", line)
    return int(m.group(1)) if m else None


def clean_asset(a):
    """Trim OCR debris that bleeds into the asset column from the row-number column."""
    a = a.strip()
    if "|" in a[:10]:
        a = a[a.rindex("|", 0, 10) + 1:]
    toks = a.split()
    while len(toks) > 1 and toks[0] not in ("3M", "3D") and (re.fullmatch(r"[^A-Za-z]+|[a-z][a-z.'’]*|[A-Z]?\d+[A-Za-z]?|[_=—\-;:'‘°]+.*", toks[0])):
        toks.pop(0)
    a = " ".join(toks)
    return re.sub(r"^[^A-Za-z0-9]+", "", a).strip() or a


def merge(text_rows, ocr_rows):
    """Union two parses of the same filing, conservatively.

    The text-layer parse is kept whole (identical lots on the same day are real). An OCR row is added only
    when its row number was not parsed from the text layer AND no text-layer row has the same type, the same
    amount band and a similar asset name, whatever the date (OCR often misreads dates). This prefers
    missing a trade over counting one twice."""
    from difflib import SequenceMatcher

    def key(r):
        return re.sub(r"[^A-Z]", "", clean_asset(r["asset"]).upper())[:28]
    out = []
    for r in text_rows:
        if re.match(r"[^A-Z0-9]|\S+ \|", r["asset"]):
            r["asset"] = clean_asset(r["asset"])
        out.append(r)
    nums = {r["n"] for r in text_rows if r.get("n")}
    by_band = {}
    for r in text_rows:
        by_band.setdefault((r["tx_type"], r["amount_low"]), []).append(key(r))
    for r in ocr_rows:
        if r.get("n") and r["n"] in nums:
            continue
        k = key(r)
        if any(SequenceMatcher(None, k, k2).ratio() >= 0.6 for k2 in by_band.get((r["tx_type"], r["amount_low"]), [])):
            continue
        r["asset"] = clean_asset(r["asset"])
        out.append(r)
        if r.get("n"):
            nums.add(r["n"])
    out.sort(key=lambda r: (r.get("n") or 10**9))
    return out


# ---------------------------------------------------------------- name -> ticker (SEC company_tickers.json)
ABBR = {"MGMT": "MANAGEMENT", "ELEC": "ELECTRIC", "HLDGS": "HOLDINGS", "HLDG": "HOLDING", "SYS": "SYSTEMS",
        "TECH": "TECHNOLOGIES", "TECHS": "TECHNOLOGIES", "INTL": "INTERNATIONAL", "INTERNTNL": "INTERNATIONAL", "PHARM": "PHARMACEUTICALS",
        "FINL": "FINANCIAL", "CORPORATION": "CORP", "INCORPORATED": "INC", "COMPANY": "CO", "SVCS": "SERVICES",
        "COMMUNICATIONS": "COMMUNICATIONS", "BANCORPORATION": "BANCORP", "LABS": "LABORATORIES", "AMER": "AMERICA",
        "MTRS": "MOTORS", "PETE": "PETROLEUM", "ENTMT": "ENTERTAINMENT", "PPTYS": "PROPERTIES", "RES": "RESOURCES",
        "EXPL": "EXPLORATION", "INDS": "INDUSTRIES", "SCIENTIFIC": "SCIENTIFIC", "&": "AND",
        "COS": "COMPANIES", "MFG": "MANUFACTURING", "GRP": "GROUP", "BANCSHS": "BANCSHARES", "CHEM": "CHEMICAL",
        "NATL": "NATIONAL", "SOLTNS": "SOLUTIONS", "PRODS": "PRODUCTS", "COMMS": "COMMUNICATIONS", "TR": "TRUST"}
DROP = {"INC", "CORP", "CO", "LTD", "PLC", "THE", "CLASS", "CL", "A", "B", "C", "COM", "COMMON", "STOCK", "SHS", "NEW",
        "REIT", "SA", "NV", "AG", "SE", "LLC", "LP", "HOLDINGS", "HOLDING", "GROUP", "AND", "DE", "ADR", "ORD",
        "SPONSORED", "N", "V", "SH", "SHARES", "REGISTERED", "/DE/", "/MD/", "THE,"}
BOND_RE = re.compile(r"(\d+(\.\d+)?\s*%|\bDUE\b|\bDuo\b|\bREV\b|B/E|BIE|B1E|\bNOTES?\b|\bBDS?\b|\bDEBS?\b|\bSER\s+[A-Z]\b|"
                     r"\bRFDG\b|\bMUN\b|\bBOND\b|\bSCH\s+DIST\b|\bCNTY\b|\bAUTH\b|\bPFD\b|\bPERP\b|DISCRETION)", re.I)


def _toks(name):
    name = re.sub(r"\s*/[A-Z]{2,3}/?\s*$", "", name.strip(), flags=re.I)
    s = re.sub(r"[^A-Z0-9& ]", " ", name.upper().replace(".", "").replace("'", ""))
    out = []
    for t in s.split():
        t = ABBR.get(t, t)
        if t not in DROP:
            out.append(t)
    return out


class TickerIndex:
    def __init__(self, sec_json):
        self.by_first = {}
        for i, v in enumerate(sec_json.values()):
            tk = _toks(v["title"])
            if not tk:
                continue
            self.by_first.setdefault(tk[0], []).append((i, tk, v["ticker"], v["title"]))

    ALIAS = {"IBM CORP": "IBM", "INTERNATIONAL BUSINESS MACHS": "IBM", "GE AEROSPACE": "GE", "DISNEY WALT CO": "DIS",
             "GALLAGHER ARTHUR J & CO": "AJG", "ALPHABET INC CLASS A": "GOOGL", "ALPHABET INC CLASS C": "GOOG",
             "BERKSHIRE HATHAWAY INC CLASS B": "BRK-B", "META PLATFORMS INC CLASS A": "META"}
    JUNK_TAIL = {"F", "UNSOLICITED", "OH", "DEL", "IRELAND", "NEW", "I", "S", "PA", "MD", "NY", "NJ", "VA", "CA", "MN",
                 "TX", "IND", "WIS", "BERMUDA", "JERSEY", "SWITZERLAND", "NETHERLANDS", "COR", "CORPORAT", "IN"}

    def match(self, desc):
        if BOND_RE.search(desc) or re.search(r"\bETF\b|\bFUND\b|\bTRUST\b|\bINDEX\b", desc, re.I):
            return None
        d = re.sub(r"\s+", " ", desc.upper()).strip()
        for k, t in self.ALIAS.items():
            if d.startswith(k):
                return t, k
        d = d.replace(".COM", " COM")
        d = re.sub(r"\b([A-Z&]{3,}?)(?<!BAN)(INC|CORP)\b", r"\1 \2", d)  # OCR glued suffix: COPARTINC
        tk = _toks(d)
        while len(tk) > 1 and tk[-1] in self.JUNK_TAIL:
            tk = tk[:-1]
        hit = self._match_toks(tk)
        if not hit and len(tk) > 2:  # OCR-truncated tail ("VERIZON COMMUNICATIONS I")
            hit = self._match_toks(tk[:-1])
        return hit

    def _match_toks(self, tk):
        if not tk:
            return None
        best = None
        for rank, t2, ticker, title in self.by_first.get(tk[0], []):
            if len(t2) != len(tk):
                continue
            if all(b == a or (len(a) >= 3 and b.startswith(a)) for a, b in zip(tk, t2)):
                if "-" in ticker and best:
                    continue
                if best is None or rank < best[0]:
                    best = (rank, ticker, title)
        return (best[1], best[2]) if best else None


def asset_kind(desc):
    if re.search(r"\bETF\b|\bFUND\b|\bTRUST\b|ISHARES|SPDR|VANGUARD", desc, re.I) and not BOND_RE.search(desc.replace("BOND ETF", "")):
        return "EF"
    if BOND_RE.search(desc):
        return "BOND"
    return "ST"
