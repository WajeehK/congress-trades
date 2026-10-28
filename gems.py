"""'Hidden gems': recent purchases of lesser-known listed companies (shared by the static export).

A stock qualifies when it is US-listed (NYSE/Nasdaq/AMEX, per Nasdaq's public screener), its market cap is
between $300M and $20B (so no S&P 500-style giants and no penny/OTC junk), it isn't a fund/bond/option
(most_bought.kind) and it isn't on a short household-name list. Grouped by ticker over the last 90 days of
trade dates, buys only; ranked by distinct buyers, then most recent disclosure.
"""
import json
import re
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import most_bought

CAPS_FILE = Path(__file__).resolve().parent / "market_caps.json"
MIN_CAP, MAX_CAP, DAYS = 300e6, 20e9, 90
HOUSEHOLD = {"GME", "AMC", "PTON", "BBWI", "M", "KSS", "JWN", "GPS", "GAP", "MAT", "HAS", "WEN", "JACK", "SHAK", "PZZA",
             "DPZ", "CROX", "SKX", "UAA", "UA", "VFC", "LEVI", "HOG", "PLNT", "BYND", "SIRI", "LYFT", "SNAP", "PINS",
             "RBLX", "ETSY", "CHWY", "W", "BBY", "DKS", "FL", "AAL", "JBLU", "LUV", "ALK", "UAL", "NCLH", "CCL", "RCL",
             "HRB", "ZM", "GIS", "KHC", "TAP", "MKC", "TTWO", "EA", "LULU", "DECK", "TPR", "RL", "PVH", "WING", "TXRH", "CMG", "DRI", "YUM", "QSR", "DPZ", "DBX", "BMBL", "MTCH", "PARA", "WBD", "NYT", "FOXA", "FOX", "TRIP", "EXPE", "HLT", "WH", "H",
             "POST", "CPB", "SJM", "HRL", "CAG", "K", "HSY", "CLX", "CHD", "TSN", "SAM", "COTY", "ELF", "ULTA", "WSM",
             "RH", "ANF", "AEO", "URBN", "BURL", "FIVE", "OLLI", "BJ", "DLTR", "DG", "AAP", "AZO", "KMX", "CVNA", "RIVN",
             "LCID", "NIO", "GRAB", "SOFI", "HOOD", "AFRM", "UPST", "DKNG", "PENN", "MGM", "WYNN", "CZR", "LVS"}
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"


def _clean_name(n):
    n = re.sub(r"\s+(Class [A-Z]\s+)?(Common Stock|Ordinary Shares|American Depositary Shares?|Depositary Shares?|Common Shares|Shares)\b.*$", "", n or "", flags=re.I)
    return n.strip(" ,") or None


def fetch_caps():
    """{ticker: [market_cap, name, industry]} for US-listed stocks in the gem cap band, from Nasdaq's public screener."""
    req = urllib.request.Request("https://api.nasdaq.com/api/screener/stocks?tableonly=true&download=true",
                                 headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        rows = json.load(r)["data"]["rows"]
    out = {}
    for x in rows:
        try:
            cap = float(x.get("marketCap") or 0)
        except ValueError:
            continue
        tk = (x.get("symbol") or "").strip().upper().replace("/", ".").replace("^", ".")
        if tk and MIN_CAP <= cap < MAX_CAP:
            out[tk] = [round(cap), _clean_name(x.get("name")), (x.get("industry") or "").strip() or None]
    if len(out) < 1000:
        raise ValueError(f"only {len(out)} rows")
    return out


def load_caps(refresh=True):
    if refresh:
        try:
            caps = fetch_caps()
            CAPS_FILE.write_text(json.dumps(caps, separators=(",", ":"), sort_keys=True))
            return caps, "live"
        except Exception as e:
            print(f"gems: market caps refresh failed ({e}); using committed snapshot")
    return json.loads(CAPS_FILE.read_text()), "snapshot"


def build(rows, sectors=None, refresh=True, today=None, limit=60):
    caps, src = load_caps(refresh)
    sectors = sectors or {}
    since = ((today or date.today()) - timedelta(days=DAYS)).isoformat()
    g = {}
    for r in rows:
        if r["side"] != "buy" or (r["tx_date"] or "") < since or most_bought.kind(r) != "stock":
            continue
        tk = r["ticker"].upper().replace("-", ".")
        if tk not in caps or tk in HOUSEHOLD:
            continue
        e = g.get(tk)
        if e is None:
            cap, nm, ind = caps[tk]
            s = sectors.get(tk) or {}
            e = g[tk] = {"ticker": tk, "name": r["company"] or nm, "cap": cap, "industry": s.get("industry") or ind,
                         "sector": s.get("sector"), "n_buys": 0, "est_total": 0.0, "pols": {}, "latest": "", "disclosed": "", "last": None}
        e["n_buys"] += 1
        e["est_total"] += most_bought.mid(r)
        e["name"] = e["name"] or r["company"]
        e["latest"] = max(e["latest"], r["tx_date"] or "")
        d = r["disclosure_date"] or ""
        if d >= e["disclosed"]:
            e["disclosed"] = d
            e["last"] = {"name": r["politician"], "bioguide": r["bioguide"], "party": r["party"], "tx": r["tx_date"]}
        p = e["pols"].setdefault(r["politician"], {"name": r["politician"], "bioguide": r["bioguide"]})
        p["bioguide"] = p["bioguide"] or r["bioguide"]
    out = []
    for e in g.values():
        pols = list(e["pols"].values())
        out.append({**{k: e[k] for k in ("ticker", "name", "cap", "industry", "sector", "n_buys", "latest", "disclosed", "last")},
                    "est_total": round(e["est_total"]), "n_pols": len(pols), "pols": pols[:4]})
    out.sort(key=lambda x: (x["n_pols"], x["est_total"], x["disclosed"]), reverse=True)
    return {"days": DAYS, "since": since, "caps": src, "items": out[:limit]}
