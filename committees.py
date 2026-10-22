"""Committee context: flag trades where a member's CURRENT committee oversees the stock's sector.

Conservative on purpose. It only says "possible overlap": committees come from the
unitedstates/congress-legislators project (current membership only, so it is applied to trades
made during the current Congress), and sectors come from Yahoo Finance's sector and industry
for the ticker. Funds, bonds and options never match.
"""
import json
import time
import urllib.parse

import requests

COMMITTEES = "https://unitedstates.github.io/congress-legislators/committees-current.json"
MEMBERSHIP = "https://unitedstates.github.io/congress-legislators/committee-membership-current.json"
CONGRESS_START = "2025-01-03"   # 119th Congress; current membership is only applied to trades from here on

# Sector tags, from Yahoo (sector, industry). Matching is exact on these strings.
INDUSTRY_TAGS = {
    "Aerospace & Defense": "defense",
    "Utilities - Regulated Electric": "energy", "Utilities - Regulated Gas": "energy",
    "Utilities - Diversified": "energy", "Utilities - Independent Power Producers": "energy",
    "Utilities - Renewable": "energy", "Solar": "energy", "Uranium": "energy",
    "Telecom Services": "telecom", "Communication Equipment": "telecom",
    "Farm Products": "ag", "Agricultural Inputs": "ag",
    "Airlines": "transport", "Railroads": "transport", "Trucking": "transport",
    "Integrated Freight & Logistics": "transport", "Marine Shipping": "transport",
    "Airports & Air Services": "transport",
    "Gold": "mining", "Silver": "mining", "Copper": "mining", "Other Industrial Metals & Mining": "mining",
    "Other Precious Metals & Mining": "mining", "Coking Coal": "mining", "Thermal Coal": "mining",
    "Lumber & Wood Production": "mining",
    "REIT - Residential": "housing", "Residential Construction": "housing", "Mortgage Finance": "financials",
}
SECTOR_TAGS = {"Energy": "energy", "Healthcare": "health", "Financial Services": "financials"}
TAG_LABEL = {"defense": "defense & aerospace", "energy": "energy & utilities", "health": "health care",
             "telecom": "telecom", "financials": "financial services", "ag": "agriculture",
             "transport": "transportation", "mining": "mining & natural resources", "housing": "housing"}

# Full committees only. Broad committees (Appropriations, Ways and Means, Finance, Budget,
# Judiciary, Oversight...) are left out on purpose: they touch everything, so "overlap" would mean nothing.
COMMITTEE_TAGS = {
    "HSAS": ["defense"], "SSAS": ["defense"], "HLIG": ["defense"], "SLIN": ["defense"],
    "HSIF": ["energy", "health", "telecom"],
    "HSBA": ["financials", "housing"], "SSBK": ["financials", "housing"],
    "HSAG": ["ag"], "SSAF": ["ag"],
    "HSII": ["energy", "mining"], "SSEG": ["energy", "mining"],
    "HSPW": ["transport"], "SSCM": ["telecom", "transport"],
    "SSHR": ["health"], "HSSY": ["defense"], "SSEV": ["transport"],
}


def _tags(sector, industry):
    t = set()
    if industry in INDUSTRY_TAGS:
        t.add(INDUSTRY_TAGS[industry])
    if sector in SECTOR_TAGS:
        t.add(SECTOR_TAGS[sector])
    return sorted(t)


def yahoo_profile(sym, ua):
    url = ("https://query2.finance.yahoo.com/v1/finance/search?quotesCount=3&newsCount=0&q="
           + urllib.parse.quote(sym))
    r = requests.get(url, headers=ua, timeout=20)
    r.raise_for_status()
    for q in r.json().get("quotes", []):
        if (q.get("symbol") or "").upper() == sym.upper():
            return {"qt": q.get("quoteType"), "sector": q.get("sector") or "", "industry": q.get("industry") or ""}
    return {"qt": None, "sector": "", "industry": ""}


def wanted_tickers(c, members):
    rows = c.execute("SELECT DISTINCT ticker FROM trades WHERE ticker IS NOT NULL AND ticker != '' "
                     "AND tx_date >= ? AND bioguide IN (%s)" % ",".join("?" * len(members)),
                     [CONGRESS_START, *members]).fetchall()
    return sorted({r[0].upper() for r in rows})


def refresh_sectors(c, meta_get, meta_set, note, ua, members, max_n=150, sym=lambda t: t):
    """Fetch Yahoo sector/industry for tickers we don't know yet (cached in meta.ticker_sector)."""
    cache = json.loads(meta_get("ticker_sector") or "{}")
    known = load_sectors(meta_get)
    todo = [t for t in wanted_tickers(c, members) if t not in known][:max_n]
    for t in todo:
        try:
            cache[t] = yahoo_profile(sym(t), ua)
        except Exception as e:
            note(f"sector {t}: {e}")
            break
        time.sleep(0.15)
    if todo:
        meta_set("ticker_sector", json.dumps(cache, separators=(",", ":")))
        note(f"sectors: +{len(todo)}")
    known.update(cache)
    return known


def load_committees(get_cached, data_dir):
    com = get_cached(COMMITTEES, data_dir / "committees-current.json", 7 * 86400) or []
    mem = get_cached(MEMBERSHIP, data_dir / "committee-membership-current.json", 86400) or {}
    return com, mem


def build(com, mem, sectors):
    """Compact client file: committees with tags, members' tagged committees, tickers' tags."""
    names = {x["thomas_id"]: x["name"].replace("Permanent Select ", "").replace("Select ", "") for x in com if x.get("thomas_id")}
    out_c = {k: {"n": names.get(k, k), "tags": v} for k, v in COMMITTEE_TAGS.items() if k in mem}
    out_m = {}
    for k in out_c:
        for p in mem.get(k, []):
            if p.get("bioguide"):
                out_m.setdefault(p["bioguide"], []).append(k + ("*" if p.get("title") in ("Chair", "Chairman", "Ranking Member", "Vice Chair", "Vice Chairman") else ""))
    out_t = {}
    for t, p in sectors.items():
        if (p.get("qt") or "") != "EQUITY":
            continue
        tg = _tags(p.get("sector"), p.get("industry"))
        if tg:
            out_t[t] = [p.get("industry") or p.get("sector"), *tg]
    return {"since": CONGRESS_START, "labels": TAG_LABEL, "c": out_c, "m": out_m, "t": out_t}


def load_sectors(meta_get):
    """Seed file shipped with the code (built once), overlaid with what refresh_sectors has fetched since."""
    import pathlib
    seed = pathlib.Path(__file__).with_name("ticker_sectors.json")
    out = json.loads(seed.read_text()) if seed.exists() else {}
    out.update(json.loads(meta_get("ticker_sector") or "{}"))
    return out
