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
    # heavier scan damage: "DUn:hale", "oon:na■o", "PUICNISO", "ourcliao" (purchase); "ule", "aelo", "SDIO" (sale)
    if len(t) >= 5 and re.search(r"(unh|nha|nho|cun|pun|dun|oon|puic|cli|liao|haa|hao|hoa|hos|aao|oao|aso|ase)", t):
        return "Purchase"
    if len(t) <= 5 and re.fullmatch(r"[a-z]{0,3}[li][eoa]", t) and not (tok.isupper() and len(t) >= 5):
        return "Sale"
    return None


def _years(yr, lo, hi):
    """The scanned year, plus in-window years one misread digit away ("2028" for 2026, "2023" for 2025)."""
    out = [yr]
    for y in range(lo.year, hi.year + 1):
        if y != yr and sum(a != b for a, b in zip(str(y), str(yr))) == 1:
            out.append(y)
    return out


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
        for y in _years(yr, lo, hi):
            try:
                d = date(y, mo, dy)
            except ValueError:
                continue
            if lo <= d <= hi:
                out.add(d)
                break
    return out


DATE_RE = re.compile(r"(?<![\w$])([0-9lI|]{1,2}[/1lI|][0-9lI|]{1,3}[/1lI|]?[0-9]{2,4})(?![\w])")
YN_RE = re.compile(r"\b(y[eo0][sa5]|v[eoa0][sa5]|ves|vas|yos|yas|n[o0])\b", re.I)


# OCR/scan glyph confusions seen in the President's 278-T date column ("8l10h026" = 8/10/2026, "R/31/?026" = 8/31/2026)
_DATE_FIX = {"R": "8", "B": "8", "?": "2", "Z": "2", "z": "2", "D": "0", "O": "0", "o": "0", "Q": "0", "U": "0",
             "S": "5", "s": "5", "$": "5", "•": "/", '"': "/", "'": "/", ".": "/", ",": "/", ":": "/", ";": "/",
             "\\": "/", "!": "/", "*": "/", "~": "/", "^": "/", "-": "/", "_": "/", "(": "/", ")": "/"}
_DATE_AMBIG = {"l": ("/", "1"), "I": ("/", "1"), "i": ("/", "1"), "|": ("/", "1"), "1": ("1", "/"),
               "h": ("/1", "/2", "/"), "n": ("/1", "/", "1"), "J": ("/", "1", "4"), "t": ("/", "1", "4"), "f": ("/", "1")}


def fuzzy_dates(seg, lo, hi):
    """Every plausible date (inside lo..hi) for a badly scanned m/d/yyyy cell. Conservative: needs a recognisable
    year (or year tail) and a real calendar date; returns a set so callers can disambiguate with neighbouring rows."""
    s = "".join(_DATE_FIX.get(ch, ch) for ch in seg.replace(" ", ""))
    s = re.sub(r"[^0-9/lIi|hnJtf]", "", s)
    if not 5 <= len(s) <= 14:
        return set()
    variants = [""]
    for ch in s:
        opts = _DATE_AMBIG.get(ch, (ch,))
        variants = [v + o for v in variants for o in opts]
        if len(variants) > 512:
            return set()
    out = set()
    for v in set(variants):
        v = re.sub(r"/+", "/", v).strip("/")
        m = (re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4}|\d{2}|0\d\d)", v)  # "026": the "2" of 2026 was eaten by a slash
             or re.fullmatch(r"(\d{1,2})/(\d{1,2})/?(20\d{2})", v))
        if not m:
            continue
        mo, dy, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if yr < 100:
            yr += 2000
        for y in _years(yr, lo, hi):
            try:
                d = date(y, mo, dy)
            except ValueError:
                continue
            if lo <= d <= hi:
                out.add(d)
                break
    return out


ROWNUM_RE = re.compile(r"\s*[\[\(|]?\s*(\d{1,4})[.,]?\s+(?=\S)")


def _fuzzy_row(line, lo, hi):
    """Fallback for numbered rows whose date cell is too garbled for DATE_RE: locate the type word, then read the
    date cell (between the type and the Yes/No column) and the amount (after it)."""
    m = ROWNUM_RE.match(line)
    if not m:
        return None
    n = int(m.group(1))
    words = line[m.end():].split()
    for k in range(len(words) - 1, 0, -1):
        tx = _type(words[k])
        if not tx or not re.search(r"[a-z]{3}", words[k].lower()):
            continue
        rest = " ".join(words[k + 1:])
        yn = YN_RE.search(rest)
        if yn:
            dseg, aseg = rest[:yn.start()], rest[yn.end():]
        else:
            dm = re.search(r"[$S]\s?\d|\d[\d ,.]{2,}\s*[-•]\s*[$S]", rest)
            if not dm:
                continue
            dseg, aseg = rest[:dm.start()], rest[dm.start():]
        amt = _amount(aseg)
        if not amt or len(dseg) > 16:
            continue
        desc = " ".join(words[:k]).strip(" -~•.'\"`|[]")
        if len(desc) < 3:
            return None
        return {"n": n, "asset": re.sub(r"\s{2,}", " ", desc), "tx_type": tx, "dates": fuzzy_dates(dseg, lo, hi),
                "amount_low": amt[0], "amount_high": amt[1], "amount": band_text(*amt),
                "late": bool(yn and yn.group(1).lower()[0] in "yv")}
    return None


def _resolve_dates(rows):
    """Pick dates for fuzzy rows using neighbouring rows (filings list trades in date order, so a row's date almost
    always equals or sits between its neighbours'). Rows with no usable date and disagreeing neighbours are dropped."""
    exact = [i for i, r in enumerate(rows) if "tx_date" in r]
    out = []
    for i, r in enumerate(rows):
        if "tx_date" in r:
            out.append(r)
            continue
        prv = next((rows[j] for j in reversed(exact) if j < i and abs((rows[j].get("n") or 0) - (r["n"] or 0)) <= 6), None)
        nxt = next((rows[j] for j in exact if j > i and abs((rows[j].get("n") or 0) - (r["n"] or 0)) <= 6), None)
        nd = [date.fromisoformat(x["tx_date"]) for x in (prv, nxt) if x]
        ds = r.pop("dates")
        pick, how = None, "fuzzy"
        if len(nd) == 2 and nd[0] == nd[1]:  # sandwiched between two rows of the same day: that day
            pick, how = nd[0], ("fuzzy" if nd[0] in ds else "neighbours")
        elif ds:
            same = [d for d in ds if d in nd]
            if same:
                pick = same[0]
            elif len(ds) == 1:
                pick = next(iter(ds))
            elif nd:
                pick = min(ds, key=lambda d: min(abs((d - x).days) for x in nd))
            else:
                pick = max(ds)
        if pick:
            r["tx_date"], r["date_src"] = pick.isoformat(), how
            out.append(r)
    return out


def parse_lines(lines, filed):
    """lines: text lines (one transaction per line, layout mode or OCR). filed: date the filing was received."""
    lo, hi = filed - timedelta(days=200), filed + timedelta(days=3)
    rows = []
    prev_text = ""
    for raw in lines:
        line = raw.replace("\u2022", "•").replace("■", " ").replace("·", "-").strip()
        if not line:
            continue
        # find the right-most date token that parses
        best = None
        for m in DATE_RE.finditer(line):
            ds = _dates(m.group(1), lo, hi)
            if ds:
                best = (m, ds)
        row = None
        if best:
            m, ds = best
            before, after = line[:m.start()].rstrip(), line[m.end():]
            amt = _amount(after)
            words = before.split()
            tx = None
            cut = len(words)
            for k in range(len(words) - 1, max(-1, len(words) - 4), -1):
                tx = _type(words[k])
                if tx:
                    cut = k
                    break
            if amt and tx:
                desc_words = words[:cut]
                num = None
                if desc_words and re.fullmatch(r"\d{1,4}\.?", desc_words[0]):
                    num = int(desc_words[0].rstrip("."))
                    desc_words = desc_words[1:]
                desc = re.sub(r"\s{2,}", " ", " ".join(desc_words).strip(" -~•.'\"`|"))
                if len(desc) < 4 and prev_text:
                    desc = re.sub(r"^\d{1,4}\s+", "", prev_text).strip()
                if len(desc) >= 3:
                    yn = YN_RE.search(after)
                    row = {"n": num, "asset": desc, "tx_type": tx, "tx_date": max(ds).isoformat(), "date_src": "exact",
                           "amount_low": amt[0], "amount_high": amt[1], "amount": band_text(*amt),
                           "late": bool(yn and yn.group(1).lower()[0] in "yv")}
        if row is None:
            row = _fuzzy_row(line, lo, hi)
            if row is None:
                if not best and len(line) > 12 and not re.search(r"(OGE|Form|Page|Note|Filer|Transactions|Description|Notification|Received|Days Ago|Amount|instruct)", line, re.I):
                    prev_text = line
                continue
        prev_text = ""
        rows.append(row)
    return _resolve_dates(rows)


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
    ocr_by_n = {}
    for r in ocr_rows:
        if r.get("n") and r.get("date_src") == "exact":
            ocr_by_n.setdefault(r["n"], r)
    for r in out:
        o = ocr_by_n.get(r.get("n"))
        if r.get("date_src") != "exact" and o and o["tx_type"] == r["tx_type"] and o["amount_low"] == r["amount_low"]:
            r["tx_date"], r["date_src"] = o["tx_date"], "ocr"
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
        "NATL": "NATIONAL", "SOLTNS": "SOLUTIONS", "PRODS": "PRODUCTS", "COMMS": "COMMUNICATIONS", "TR": "TRUST",
        "RLTY": "REALTY", "MATLS": "MATERIALS", "BK": "BANK", "INDL": "INDUSTRIAL", "NTNL": "NATIONAL", "SVC": "SERVICE",
        "PPTY": "PROPERTY", "INSTRS": "INSTRUMENTS", "WHSL": "WHOLESALE", "WTR": "WATER", "WKS": "WORKS",
        "CMNTYS": "COMMUNITIES", "CMNTY": "COMMUNITY", "INVT": "INVESTMENT", "MTG": "MORTGAGE", "RESH": "RESEARCH",
        "PWR": "POWER", "MKTS": "MARKETS", "CTRS": "CENTERS", "MED": "MEDICAL", "PHARMS": "PHARMACEUTICALS",
        "BANCSHARES": "BANCSHARES", "SOLUTION": "SOLUTIONS", "AMERN": "AMERICAN", "TRANSN": "TRANSPORTATION"}
DROP = {"INC", "CORP", "CO", "LTD", "PLC", "THE", "CLASS", "CL", "A", "B", "C", "COM", "COMMON", "STOCK", "SHS", "NEW",
        "REIT", "SA", "NV", "AG", "SE", "LLC", "LP", "HOLDINGS", "HOLDING", "GROUP", "AND", "DE", "ADR", "ORD",
        "SPONSORED", "N", "V", "SH", "SHARES", "REGISTERED", "/DE/", "/MD/", "THE,"}
BOND_RE = re.compile(r"(\d+(\.\d+)?\s*%|\bDUE\b|\bDuo\b|\bREV\b|B/E|BIE|B1E|\bNOTES?\b|\bBDS?\b|\bDEBS?\b|\bSER\s+[A-Z]\b|"
                     r"\bRFDG\b|\bMUN\b|\bBOND\b|\bSCH\s+DIST\b|\bCNTY\b|\bAUTH\b|\bPFD\b|\bPERP\b|DISCRETION)", re.I)


def _toks(name):
    name = re.sub(r"\s*/\s*[A-Z]{2,3}/?\s*$", "", name.strip(), flags=re.I)
    s = re.sub(r"[^A-Z0-9& ]", " ", name.upper().replace(".", "").replace("'", ""))
    out = []
    for t in s.split():
        t = ABBR.get(t, t)
        if t not in DROP:
            out.append(t)
    return out


class TickerIndex:
    def __init__(self, sec_json):
        self.by_first, self.by_compact = {}, {}
        for i, v in enumerate(sec_json.values()):
            tk = _toks(v["title"])
            if not tk:
                continue
            self.by_first.setdefault(tk[0], []).append((i, tk, v["ticker"], v["title"]))
            if "-" not in v["ticker"]:
                self.by_compact.setdefault("".join(tk), (v["ticker"], v["title"]))

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
        if not hit and tk:  # spacing differs ("EXXON MOBIL" vs "ExxonMobil")
            hit = self.by_compact.get("".join(tk))
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


# ---------------------------------------------------------------- OGE Form 278e (annual / termination reports), Part 7
_E_TYPE = re.compile(r"\b(purchase|sale|exchange)(?:\s*\((?:partial|full)\))?(?=\s|$)", re.I)
_E_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b|\b(\d{1,2})-([A-Za-z]{3})-(\d{4})\b")
_MON = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_E_SKIP = ("OGE Form", "Instructions", "If you need", "Note:", "Filer's Name", "Filer’s Name", "Donald J. Trump", "Page ")


def parse_278e(text):
    """Transactions (Part 7) of an OGE 278e. These reports are typed forms (a clean text layer), with one row per
    numbered line; numbering restarts for each investment account, so rows carry their account index."""
    rows, cur, acct = [], None, 0

    def flush():
        if not cur:
            return
        n, parts = cur
        blob = re.sub(r"\s+", " ", " ".join(parts)).strip()
        tm = dm = None
        for m in _E_TYPE.finditer(blob):
            tm = m
        if not tm:
            return
        for m in _E_DATE.finditer(blob, tm.end()):
            dm = m
            break
        if not dm:
            return
        try:
            if dm.group(1):
                d = date(int(dm.group(3)), int(dm.group(1)), int(dm.group(2)))
            else:
                d = date(int(dm.group(6)), _MON[dm.group(5).lower()], int(dm.group(4)))
        except (ValueError, KeyError):
            return
        amt = _amount(blob[dm.end():])
        desc = blob[:tm.start()].strip(" -")
        if not amt or len(desc) < 2 or desc.upper() in ("N/A", "NONE"):
            return
        t = tm.group(1).lower()
        rows.append({"n": n, "acct": acct, "asset": desc, "tx_type": {"purchase": "Purchase", "sale": "Sale"}.get(t, "Exchange"),
                     "tx_date": d.isoformat(), "date_src": "exact", "amount_low": amt[0], "amount_high": amt[1],
                     "amount": band_text(*amt), "late": False})

    for page in text.split("\f"):
        if "Part 7: Transactions" not in page:
            continue
        for line in page.split("Part 7: Transactions", 1)[1].splitlines():
            s = line.strip()
            if not s or re.match(r"#\s+Description", s) or s.startswith(_E_SKIP):
                continue
            if re.match(r"Part \d+:", s):
                break
            m = re.match(r"(\d{1,5})\.?\s+(\S.*)", s)
            if re.match(r"(INVESTMENT )?ACCOUNT\b|.*\bACCOUNT #\d+\s*$", s, re.I) and not _E_TYPE.search(s):
                flush()
                cur, acct = None, acct + 1
            elif m:
                flush()
                cur = (int(m.group(1)), [m.group(2)])
            elif cur:
                cur[1].append(s)
        flush()
        cur = None
    return rows


def received_278e(text):
    """When OGE received a 278e: the 'OGE Received' stamp, else the reviewer's digital signature date."""
    m = re.search(r"OGE\s+Received:?\s*(\d{1,2})/(\d{1,2})/(\d{4})", text, re.I)
    if m:
        return date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
    m = re.search(r"Digitally signed by [A-Z .]+\s+Date:\s*(\d{4})\.(\d{2})\.(\d{2})", text)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def is_amendment_page(page):
    return bool(re.search(r"In place of line item|AMENDMENT TO EXECUTIVE BRANCH", page, re.I))


def parse_amendment(text):
    """'In place of line item #N, substitute the following' blocks of a 278-T amendment: {n: replacement row}."""
    out = {}
    blocks = re.split(r"In place of line item #\s*(\d{1,4})", text)
    for i in range(1, len(blocks) - 1, 2):
        n, body = int(blocks[i]), blocks[i + 1][:600]
        body = body.split("In place of", 1)[0]
        tm = re.search(r"\b(Purchase|Sale|Exchange)\b", body, re.I)
        dm = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b", body)
        if not tm or not dm:
            continue
        yr = int(dm.group(3)) + (2000 if len(dm.group(3)) == 2 else 0)
        try:
            d = date(yr, int(dm.group(1)), int(dm.group(2)))
        except ValueError:
            continue
        nums = [int(x.replace(",", "")) for x in re.findall(r"\d{1,3}(?:,\d{3})+", body[dm.end():])]
        band = next((LOWS[x] for x in nums if x in LOWS), None)
        if band:
            head = re.split(r"Over\s*30\s*days|Amount", body[:tm.start()], flags=re.I)[-1]
            desc = re.sub(r"\s+", " ", re.sub(rf"(^|\s){n}(\s|$)", " ", head)).strip(" |:-_—")
            out[n] = {"n": n, "asset": desc, "tx_type": tm.group(1).capitalize(), "tx_date": d.isoformat(),
                      "date_src": "exact", "amount_low": band[0], "amount_high": band[1], "amount": band_text(*band),
                      "late": False}
    return out
