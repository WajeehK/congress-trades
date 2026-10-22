"""Politician Trades Tracker - FastAPI backend.

Sources
  * House: official Clerk of the House financial disclosure index (yearly ZIP/XML) +
    electronically-filed Periodic Transaction Report PDFs (parsed with pdftotext).
  * Senate: Bargo free Congress trades API (keyless or free key; rolling ~3 months),
    because the official Senate eFD site (efdsearch.senate.gov) refuses this machine (HTTP 403).
  * Party / state / bioguide IDs: unitedstates/congress-legislators (public domain).
  * Prices: Yahoo Finance public chart endpoint (daily bars), cached in SQLite.
  * Notifications: native Web Push to the installed PWA (webpush.py).
"""
import functools
import hashlib
import html as htmllib
import io
import json
import logging
import os
import re
import secrets
import sqlite3
import subprocess
import threading
import time
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ptr_parser import parse_ptr_pdf
import oge_parser
import ticker_fixes
import portfolio as pf

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
PDFS = DATA / "pdfs"
DATA.mkdir(exist_ok=True)
PDFS.mkdir(exist_ok=True)


def _file_or_env(env, fname, default=""):
    v = os.environ.get(env, "").strip()
    if not v and (DATA / fname).exists():
        v = (DATA / fname).read_text().strip()
    return v or default


DB_PATH = Path(os.environ.get("DB_PATH", DATA / "trades.db"))
REFRESH_MINUTES = float(os.environ.get("REFRESH_MINUTES", "60"))
HOUSE_YEARS = [int(y) for y in os.environ.get("HOUSE_YEARS", "").split(",") if y.strip()] or [date.today().year - 1, date.today().year]
BARGO_KEY = _file_or_env("BARGO_API_KEY", "bargo_key.txt")
BARGO_MIN_HOURS = float(os.environ.get("BARGO_MIN_HOURS", "1" if BARGO_KEY else "3"))
NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
if not NTFY_TOPIC and os.environ.get("NTFY_DISABLE") != "1":
    _tf = DATA / "ntfy_topic.txt"
    if not _tf.exists():
        _tf.write_text("congress-trades-" + secrets.token_hex(5))
    NTFY_TOPIC = _tf.read_text().strip()
PUBLIC_URL_FILE = DATA / "public_url.txt"
NEW_WINDOW_DAYS = 14  # a trade disclosed more than this long ago is treated as backfill, not "new"

UA = {"User-Agent": "Mozilla/5.0 (politician-trades-tracker; personal research)"}
HOUSE_INDEX = "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{y}FD.zip"
HOUSE_PDF = "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{y}/{doc}.pdf"
BARGO = "https://www.bargo.ai/free-apis/congress/v1/trades"
LEGIS = "https://unitedstates.github.io/congress-legislators/legislators-current.json"
LEGIS_HIST = "https://unitedstates.github.io/congress-legislators/legislators-historical.json"
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}"

log = logging.getLogger("tracker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
_lock = threading.Lock()
_state = {"running": False, "last_error": None, "log": []}

TRADE_COLS = ["uid", "source", "filing_id", "chamber", "politician", "last_name", "party", "state", "district",
              "owner", "ticker", "asset", "asset_type", "tx_type", "side", "tx_date", "disclosure_date", "amount",
              "amount_low", "amount_high", "description", "url", "fetched_at", "bioguide", "first_seen"]


def db():
    c = sqlite3.connect(DB_PATH, timeout=60)
    c.row_factory = sqlite3.Row
    c.create_function("bh_match", 12, search_match, deterministic=True)
    return c


def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS filings(
          id TEXT PRIMARY KEY, source TEXT, chamber TEXT, politician TEXT, state_dst TEXT,
          filing_date TEXT, url TEXT, status TEXT, n_tx INTEGER, fetched_at TEXT);
        CREATE TABLE IF NOT EXISTS trades(
          uid TEXT PRIMARY KEY, source TEXT, filing_id TEXT, chamber TEXT, politician TEXT,
          last_name TEXT, party TEXT, state TEXT, district TEXT, owner TEXT, ticker TEXT,
          asset TEXT, asset_type TEXT, tx_type TEXT, side TEXT, tx_date TEXT, disclosure_date TEXT,
          amount TEXT, amount_low INTEGER, amount_high INTEGER, description TEXT, url TEXT,
          fetched_at TEXT);
        CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
        CREATE TABLE IF NOT EXISTS prices(ticker TEXT, d TEXT, open REAL, high REAL, low REAL, close REAL, adjclose REAL,
          PRIMARY KEY(ticker, d));
        CREATE TABLE IF NOT EXISTS quotes(ticker TEXT PRIMARY KEY, symbol TEXT, price REAL, as_of TEXT, name TEXT,
          status TEXT, hist_from TEXT, checked_at TEXT);
        """)
        cols = {r[1] for r in c.execute("PRAGMA table_info(trades)")}
        for col, typ in (("bioguide", "TEXT"), ("first_seen", "TEXT"), ("est_price", "REAL"), ("est_adj", "REAL"),
                         ("est_date", "TEXT")):
            if col not in cols:
                c.execute(f"ALTER TABLE trades ADD COLUMN {col} {typ}")
        c.execute("UPDATE trades SET first_seen = disclosure_date || 'T12:00:00+00:00' WHERE first_seen IS NULL")
        c.executescript("""
        CREATE INDEX IF NOT EXISTS ix_tr_disc ON trades(disclosure_date);
        CREATE INDEX IF NOT EXISTS ix_tr_tx ON trades(tx_date);
        CREATE INDEX IF NOT EXISTS ix_tr_pol ON trades(politician);
        CREATE INDEX IF NOT EXISTS ix_tr_tick ON trades(ticker);
        CREATE INDEX IF NOT EXISTS ix_tr_seen ON trades(first_seen);
        """)
        canonical_names(c)
        for old, new, asset, n in ticker_fixes.migrate(c):   # typo'd / misread tickers (see ticker_fixes.py)
            log.info("ticker fix: %s -> %s x%d (%s)", old, new, n, asset)


def meta_get(k, default=None):
    with db() as c:
        r = c.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
    return r["v"] if r else default


def meta_set(k, v):
    with db() as c:
        c.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", (k, v))


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def first_seen_for(disclosure_date):
    """Real 'first seen' time for fresh filings; the disclosure date for old (backfilled) ones."""
    if disclosure_date and disclosure_date < (date.today() - timedelta(days=NEW_WINDOW_DAYS)).isoformat():
        return disclosure_date + "T12:00:00+00:00"
    return now()


def iso(d):
    if not d:
        return None
    for f in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(d.strip(), f).date().isoformat()
        except ValueError:
            pass
    return None


def note(msg):
    log.info(msg)
    _state["log"] = (_state["log"] + [f"{now()} {msg}"])[-60:]


# ---------------------------------------------------------------- legislators
_leg = {"house": {}, "senate": {}, "house_name": {}}


def _get_cached(url, path, max_age):
    if not path.exists() or time.time() - path.stat().st_mtime > max_age:
        try:
            r = requests.get(url, headers=UA, timeout=120)
            r.raise_for_status()
            path.write_bytes(r.content)
        except Exception as e:
            note(f"{url} fetch failed: {e}")
    return json.loads(path.read_text()) if path.exists() else []


def _norm_last(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().strip().lower()
    return re.sub(r",?\s+(jr|sr|ii|iii|iv)\.?$", "", s)


def load_legislators():
    """(party, bioguide) lookup. Historical first (members who left since 2019), then current overrides."""
    hist = [p for p in _get_cached(LEGIS_HIST, DATA / "legislators-historical.json", 30 * 86400)
            if p["terms"][-1].get("end", "") >= "2019"]
    cur = _get_cached(LEGIS, DATA / "legislators-current.json", 86400)
    for is_hist, group in ((True, hist), (False, cur)):
        for p in group:
            bid = p["id"].get("bioguide")
            last = _norm_last(p["name"]["last"])
            for t in (p["terms"][-2:] if is_hist else p["terms"][-1:]):
                party = {"Democrat": "D", "Republican": "R", "Independent": "I"}.get(t.get("party"), t.get("party"))
                if t["type"] == "rep":
                    _leg["house"][(t["state"], int(t.get("district", 0)))] = (last, party, bid)
                    _leg["house_name"][(t["state"], last)] = (party, bid)
                else:
                    _leg["senate"][(t["state"], last)] = (party, bid)


def house_lookup(state_dst, last):
    m = re.match(r"([A-Z]{2})(\d+)", state_dst or "")
    if not m:
        return None, None
    st, dist = m.group(1), int(m.group(2))
    last = _norm_last(last)
    hit = _leg["house"].get((st, dist))
    if hit and (hit[0] == last or hit[0] in last or last in hit[0]):
        return hit[1], hit[2]
    return _leg["house_name"].get((st, last), (None, None))


def senate_lookup(state, name):
    toks = [_norm_last(t) for t in re.sub(r"[,.]", " ", name or "").split()]
    for t in reversed([t for t in toks if t not in ("jr", "sr", "ii", "iii", "iv")]):
        hit = _leg["senate"].get((state, t))
        if hit:
            return hit
    return None, None


_HONORIFICS = {"mr", "mrs", "ms", "miss", "dr", "hon", "rep", "sen", "honorable", "md", "facs", "phd", "dds", "dvm", "cpa", "esq"}


def clean_name(name):
    """Normalise a filer name: drop honorifics that some filers type into the First field ("John J Mr McGuire",
    "Mark Dr Green") and collapse doubled words ("Scott Scott Franklin" -> "Scott Franklin")."""
    out = []
    for w in (name or "").split():
        k = w.lower().strip(".,")
        if k in _HONORIFICS:
            continue
        if out and k == out[-1].lower().strip(".,"):
            continue
        out.append(w)
    return " ".join(out) or (name or "").strip()


def canonical_names(c):
    """One spelling per person: names already cleaned, then rows sharing a bioguide id but spelled differently
    across filings ("John McGuire" / "John J McGuire III") take the spelling used on most rows."""
    for tbl in ("trades", "filings"):
        for (n,) in c.execute(f"SELECT DISTINCT politician FROM {tbl}").fetchall():
            if n and clean_name(n) != n:
                c.execute(f"UPDATE {tbl} SET politician=? WHERE politician=?", (clean_name(n), n))
    rows = c.execute("SELECT bioguide, politician, COUNT(*) n FROM trades WHERE bioguide IS NOT NULL AND bioguide != '' "
                     "GROUP BY bioguide, politician ORDER BY bioguide, n DESC, LENGTH(politician)").fetchall()
    best = {}
    for b, n, _ in rows:
        if b not in best:
            best[b] = n
        elif n != best[b]:
            c.execute("UPDATE trades SET politician=? WHERE politician=? AND bioguide=?", (best[b], n, b))
            c.execute("UPDATE filings SET politician=? WHERE politician=?", (best[b], n))


def side_of(tx_type):
    t = (tx_type or "").lower()
    if "exchange" in t:
        return "exchange"
    if t.startswith("p") or "purchase" in t or t == "buy":
        return "buy"
    if t.startswith("s") or "sale" in t or "sell" in t:
        return "sell"
    return "other"


def insert_trade(c, row, ignore=False):
    if row.get("politician"):
        row["politician"] = clean_name(row["politician"])
    ticker_fixes.apply(row)
    vals = [row.get(k) for k in TRADE_COLS]
    verb = "INSERT OR IGNORE" if ignore else "INSERT OR REPLACE"
    return c.execute(f"{verb} INTO trades({','.join(TRADE_COLS)}) VALUES({','.join('?' * len(TRADE_COLS))})", vals)


# ---------------------------------------------------------------- House
def fetch_house_year(year):
    r = requests.get(HOUSE_INDEX.format(y=year), headers=UA, timeout=120)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    xml_name = next(n for n in z.namelist() if n.lower().endswith(".xml"))
    root = ET.fromstring(z.read(xml_name))
    ptrs = []
    for m in root.findall("Member"):
        if m.findtext("FilingType") != "P":
            continue
        first, last, suffix = ((m.findtext(k) or "").strip() for k in ("First", "Last", "Suffix"))
        ptrs.append({
            "doc": m.findtext("DocID").strip(), "year": int(m.findtext("Year") or year),
            "name": clean_name(" ".join(x for x in (first, last, suffix) if x)), "last": last,
            "state_dst": (m.findtext("StateDst") or "").strip(), "filing_date": iso(m.findtext("FilingDate")),
        })
    with db() as c:
        done = {r["id"] for r in c.execute(
            "SELECT id FROM filings WHERE source='house' AND status IN ('parsed','scanned','no_transactions','ocr')")}
        scanned = {r["id"] for r in c.execute("SELECT id FROM filings WHERE source='house' AND status='scanned'")}
    # scanned (paper) filings are redone once their OCR text exists (committed house_ocr/ or made here, see house_ocr())
    ocr_budget = [int(os.environ.get("HOUSE_OCR_MAX", "4"))]
    done -= {f"house:{p['doc']}" for p in ptrs if f"house:{p['doc']}" in scanned and _house_ocr_text(p["doc"], None) is not None}
    todo = [p for p in ptrs if f"house:{p['doc']}" not in done]
    note(f"House {year}: {len(ptrs)} PTRs in index, {len(todo)} new to process")

    def work(p):
        url = HOUSE_PDF.format(y=p["year"], doc=p["doc"])
        dest = PDFS / f"{p['year']}_{p['doc']}.pdf"
        try:
            if f"house:{p['doc']}" in scanned:   # known paper filing whose OCR text now exists: no need for the PDF
                text = _house_ocr_text(p["doc"], None)
                if text is not None:
                    import house_scan_parser
                    txs = house_scan_parser.parse(text, date.fromisoformat(p["filing_date"]), _known_tickers())
                    return p, url, ("ocr" if txs else "scanned"), txs
            if not dest.exists():
                rr = requests.get(url, headers=UA, timeout=60)
                if rr.status_code != 200:
                    return p, url, "failed", []
                dest.write_bytes(rr.content)
            txs = parse_ptr_pdf(str(dest))
            if txs is None:
                text = _house_ocr_text(p["doc"], dest, ocr_budget)
                if text is None:
                    return p, url, "scanned", []
                import house_scan_parser
                txs = house_scan_parser.parse(text, date.fromisoformat(p["filing_date"]), _known_tickers())
                return p, url, ("ocr" if txs else "scanned"), txs
            return p, url, ("parsed" if txs else "no_transactions"), txs
        except Exception as e:
            log.warning("PTR %s failed: %s", p["doc"], e)
            return p, url, "failed", []

    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(work, todo))
    new_rows = []
    with db() as c:
        for p, url, status, txs in results:
            fid = f"house:{p['doc']}"
            party, bid = house_lookup(p["state_dst"], p["last"])
            was_known = fid in scanned   # a paper filing we already listed: its OCR rows are history, not news
            c.execute("INSERT OR REPLACE INTO filings VALUES(?,?,?,?,?,?,?,?,?,?)",
                      (fid, "house", "House", p["name"], p["state_dst"], p["filing_date"], url, status, len(txs), now()))
            prev = {r["uid"]: r["first_seen"] for r in c.execute("SELECT uid, first_seen FROM trades WHERE filing_id=?", (fid,))}
            c.execute("DELETE FROM trades WHERE filing_id=?", (fid,))
            for i, t in enumerate(txs):
                uid = f"{fid}:{i}"
                row = {"uid": uid, "source": "house_clerk", "filing_id": fid, "chamber": "House",
                       "politician": p["name"], "last_name": p["last"], "party": party,
                       "state": p["state_dst"][:2] or None, "district": p["state_dst"], "owner": t["owner"],
                       "ticker": t["ticker"], "asset": t["asset"], "asset_type": t["asset_type"],
                       "tx_type": t["tx_type"], "side": side_of(t["tx_type"]), "tx_date": iso(t["tx_date"]),
                       "disclosure_date": p["filing_date"], "amount": t["amount"], "amount_low": t["amount_low"],
                       "amount_high": t["amount_high"], "description": t["description"], "url": url,
                       "fetched_at": now(), "bioguide": bid,
                       "first_seen": prev.get(uid) or (p["filing_date"] + "T12:00:00+00:00" if was_known
                                                       else first_seen_for(p["filing_date"]))}
                if status == "ocr" and not row["ticker"] and idx_ok():
                    import house_scan_parser
                    hit = next(filter(None, map(ticker_index().match, house_scan_parser.match_candidates(t["asset"]))), None)
                    if hit:
                        row.update(ticker=hit[0], asset_type="ST")
                insert_trade(c, row)
                if uid not in prev and not was_known:
                    new_rows.append(row)
    with db() as c:
        canonical_names(c)
    note(f"House {year}: {len(new_rows)} new transactions from {len(results)} filings")
    return new_rows


HOUSE_OCR_DIR = BASE / "house_ocr"   # committed cell OCR of scanned House PTRs (box/house_ocr_box.py)
HOUSE_OCR_CACHE = DB_PATH.parent / "house_ocr"   # OCR made by this deployment for newer scans (kept with the state)


def _house_ocr_text(doc, pdf, budget=None):
    """OCR cell text of a scanned House PTR: committed copy, else cached, else (budget permitting) OCR it now."""
    for d in (HOUSE_OCR_DIR, HOUSE_OCR_CACHE):
        f = d / f"{doc}.txt"
        if f.exists():
            return f.read_text()
    if pdf is None or not budget or budget[0] <= 0 or os.environ.get("HOUSE_OCR_DISABLE") == "1":
        return None
    budget[0] -= 1
    try:
        import sys as _sys
        _sys.path.insert(0, str(BASE / "box"))
        import house_ocr_box
        HOUSE_OCR_CACHE.mkdir(parents=True, exist_ok=True)
        dest, msg = house_ocr_box.run(str(pdf), str(HOUSE_OCR_CACHE))
        note(f"House OCR {doc}: {msg}")
        return Path(dest).read_text()
    except Exception as e:
        note(f"House OCR {doc} failed: {e}")
        return None


_kt = {}


def _known_tickers():
    """Tickers seen on e-filed rows: lets the scan parser accept a ticker written at the end of an asset name."""
    if "s" not in _kt:
        with db() as c:
            _kt["s"] = frozenset(r[0] for r in c.execute("SELECT DISTINCT UPPER(ticker) FROM trades WHERE ticker IS NOT NULL "
                                                         "AND source IN ('house_clerk','senate_efd','bargo')"))
    return _kt["s"]


def idx_ok():
    try:
        return ticker_index() is not None
    except Exception:
        return False


# ---------------------------------------------------------------- Senate (Bargo)
def ingest_bargo(trades):
    import senate_efd
    new_rows, seen = [], {}
    with db() as c:
        ek = senate_efd.efd_keys(c)   # trades the Senate's own eFD data already has: skip the Bargo copy
        for t in trades:
            if (t.get("chamber") or "").lower() != "senate":
                continue
            base = "|".join(str(t.get(k)) for k in ("member", "ticker", "asset", "type", "transaction_date",
                                                     "amount_range", "disclosure_date"))
            seen[base] = seen.get(base, 0) + 1
            uid = "senate:" + hashlib.sha1(f"{base}|{seen[base]}".encode()).hexdigest()[:20]
            name = re.sub(r"\s+", " ", t.get("member") or "").strip()
            if name.isupper():
                name = name.title()
            state = t.get("state")
            party, bid = senate_lookup(state, name)
            ty = (t.get("type") or "").replace("_", " ")
            ty = {"sale": "Sale", "purchase": "Purchase", "sale partial": "Sale (partial)", "sale full": "Sale",
                  "exchange": "Exchange"}.get(ty, ty.title())
            tick = t.get("ticker")
            row = {"uid": uid, "source": "bargo", "chamber": "Senate", "politician": name,
                   "last_name": name.split()[-1] if name else "", "party": party, "state": state, "district": state,
                   "ticker": tick if tick not in (None, "", "--") else None,
                   "asset": htmllib.unescape(t.get("asset") or ""),
                   "tx_type": ty, "side": side_of(ty), "tx_date": t.get("transaction_date"),
                   "disclosure_date": t.get("disclosure_date"), "amount": t.get("amount_range"),
                   "amount_low": t.get("amount_low"), "amount_high": t.get("amount_high"),
                   "url": t.get("filing_url") or t.get("filing_portal") or "https://efdsearch.senate.gov/search/",
                   "fetched_at": now(), "bioguide": bid, "first_seen": first_seen_for(t.get("disclosure_date"))}
            if ek and senate_efd.bargo_dupe(ek, row):
                continue
            if insert_trade(c, row, ignore=True).rowcount:
                new_rows.append(row)
        for r in c.execute("SELECT uid, politician, state FROM trades WHERE source='bargo' AND bioguide IS NULL").fetchall():
            party, bid = senate_lookup(r["state"], r["politician"])
            if bid:
                c.execute("UPDATE trades SET party=?, bioguide=? WHERE uid=?", (party, bid, r["uid"]))
    return new_rows


def fetch_senate(force=False):
    last = meta_get("bargo_last_fetch")
    if last and not force and time.time() - float(last) < BARGO_MIN_HOURS * 3600:
        return []
    headers = dict(UA)
    if BARGO_KEY:
        headers["X-Api-Key"] = BARGO_KEY
    new_rows = []
    lim = 250 if BARGO_KEY else 100
    for page in range(8 if BARGO_KEY else 1):
        r = requests.get(BARGO, params={"chamber": "senate", "limit": lim, "page": page}, headers=headers, timeout=60)
        meta_set("bargo_rate", json.dumps({k.lower(): v for k, v in r.headers.items() if "ratelimit" in k.lower()}))
        if r.status_code != 200:
            note(f"Senate (Bargo): HTTP {r.status_code} {r.text[:150]}")
            break
        trades = r.json().get("trades", [])
        (DATA / f"bargo_senate_{date.today().isoformat()}_p{page}.json").write_text(json.dumps(r.json()))
        new_rows += ingest_bargo(trades)
        if len(trades) < lim:
            break
    meta_set("bargo_last_fetch", str(time.time()))
    note(f"Senate (Bargo{' key' if BARGO_KEY else ', keyless'}): {len(new_rows)} new transactions")
    return new_rows



# ---------------------------------------------------------------- Executive branch (OGE 278-T and 278e, the President)
OGE_DIR = DATA / "oge"
OGE_DIR.mkdir(exist_ok=True)
OGE_TEXT_DIR = BASE / "oge_ocr"  # committed OCR text (pages split by \f) so GitHub Actions never has to re-OCR old scans
OGE_INDEX = "https://extapps2.oge.gov/201/Presiden.nsf/President%20and%20Vice%20President%20Index?OpenView&Count=1000"
OGE_BASE = "https://extapps2.oge.gov"
OGE_MIN_HOURS = float(os.environ.get("OGE_MIN_HOURS", "6"))
# bump when the OGE parsers change: every OGE filing is then re-parsed once, and rows found that way count as backfill
OGE_PARSER_VERSION = "3"
EXEC_PEOPLE = {"Trump": {"name": "Donald J. Trump", "last": "Trump", "party": "R", "state": "US", "role": "President"}}
_ticker_index = None


def ticker_index():
    global _ticker_index
    if _ticker_index is None:
        f = DATA / "sec_company_tickers.json"
        if not f.exists() or time.time() - f.stat().st_mtime > 30 * 86400:
            try:
                r = requests.get("https://www.sec.gov/files/company_tickers.json",
                                 headers={"User-Agent": "politician-trades-tracker personal research admin@example.com"},
                                 timeout=60)
                r.raise_for_status()
                f.write_bytes(r.content)
            except Exception as e:
                note(f"SEC ticker list fetch failed: {e}")
        _ticker_index = oge_parser.TickerIndex(json.loads(f.read_text())) if f.exists() else None
    return _ticker_index


def oge_filings():
    """The President's 278-T (periodic) and 278e (annual / termination) reports from OGE's public President & Vice
    President index (no OGE Form 201 needed)."""
    import urllib.parse
    r = requests.get(OGE_INDEX, headers=UA, timeout=60)
    r.raise_for_status()
    out = []
    for m in re.finditer(r"<a href='([^']+)'>((?:(?!</a>).)*?)</a>", r.text, re.S):
        label = re.sub("<[^>]+>", "", m.group(2)).strip()
        path = m.group(1)
        who = next((k for k in EXEC_PEOPLE if k in path), None)
        if not who:
            continue
        dm = re.search(r"278 Transaction \((\d\d)/(\d\d)/(\d{4})\)", label)
        am = re.match(r"(Annual|Termination)(?: \((\d{4})\))?", label)
        if dm:
            kind, received = "278t", f"{dm.group(3)}-{dm.group(1)}-{dm.group(2)}"
        elif am:
            ym = re.search(r"(20\d\d)", path)
            yr = am.group(2) or (ym.group(1) if ym else "2000")
            kind, received = "278e", f"{yr}-05-15"  # placeholder; the report's own OGE-received stamp wins
        else:
            continue
        docid = path.split("/")[-3] if "/$FILE/" in path else hashlib.sha1(path.encode()).hexdigest()[:16]
        out.append({"who": who, "docid": docid, "received": received, "kind": kind, "label": label,
                    "file_name": path.split("/")[-1], "amended": "AMEND" in path.upper(),
                    "url": OGE_BASE + urllib.parse.quote(path, safe="/+$")})
    return out


def _oge_ocr_text(pdf):
    """OCR text of a scanned 278-T, pages separated by \\f: committed copy if present, else tesseract (cached)."""
    committed = OGE_TEXT_DIR / f"{pdf.stem}.txt"
    if committed.exists():
        return committed.read_text()
    import oge_ocr
    all_txt = oge_ocr.ocr_pdf(pdf, workers=3)
    pages = sorted(pdf.with_suffix(".ocr").glob("p-*.txt"))
    return "\f".join(p.read_text() for p in pages) if pages else all_txt


def _parse_oge_pdf(pdf, received, amended=False):
    """278-T rows: the PDF's own text layer first, then tesseract OCR to fill rows the text layer lost.
    An amended report carries 'In place of line item #N' substitutions that override those rows."""
    filed = date.fromisoformat(received)
    text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True).stdout
    try:
        ocr = _oge_ocr_text(pdf)
    except Exception as e:
        log.warning("OCR %s failed: %s", pdf, e)
        ocr = ""
    subs = {}
    if amended:
        subs = {**oge_parser.parse_amendment(ocr), **oge_parser.parse_amendment(text)}

    def lines(t):
        return [ln for pg in t.split("\f") if not (amended and oge_parser.is_amendment_page(pg)) for ln in pg.splitlines()]
    rows = oge_parser.merge(oge_parser.parse_lines(lines(text), filed), oge_parser.parse_lines(lines(ocr), filed))
    seen = set()
    for r in rows:
        s = subs.get(r.get("n"))
        if s:
            r.update({k: s[k] for k in ("tx_type", "tx_date", "amount_low", "amount_high", "amount")}, amended=True)
            seen.add(r["n"])
    rows += [dict(s, amended=True) for n, s in sorted(subs.items()) if n not in seen and len(s["asset"]) >= 3]
    return rows


def _asset_key(a):
    return re.sub(r"[^A-Z]", "", oge_parser.clean_asset(a or "").upper())[:28]


def _dedupe_278e(c, politician, fid, txs):
    """Drop 278e rows already reported on a 278-T (same date, type, value band and a similar asset name);
    each 278-T row absorbs at most one annual row, so genuine repeat lots are kept."""
    from difflib import SequenceMatcher
    pool = {}
    for r in c.execute("SELECT tx_date, tx_type, amount_low, asset FROM trades WHERE source='oge' AND politician=? "
                       "AND filing_id IN (SELECT id FROM filings WHERE source='oge' AND id != ? AND url NOT LIKE '%278ANNUAL%' "
                       "AND url NOT LIKE '%Annual%' AND url NOT LIKE '%Termination%')", (politician, fid)):
        pool.setdefault((r["tx_date"], r["tx_type"], r["amount_low"]), []).append(_asset_key(r["asset"]))
    out, dropped = [], 0
    for t in txs:
        cands = pool.get((t["tx_date"], t["tx_type"], t["amount_low"]), [])
        k = _asset_key(t["asset"])
        hit = next((i for i, k2 in enumerate(cands) if SequenceMatcher(None, k, k2).ratio() >= 0.5), None)
        if hit is None:
            out.append(t)
        else:
            cands.pop(hit)
            dropped += 1
    return out, dropped


def fetch_oge(force=False):
    last = meta_get("oge_last_fetch")
    reparse = meta_get("oge_parser_version") != OGE_PARSER_VERSION
    cabinet_due = meta_get("oge_cabinet_seeded") != "1" and os.environ.get("OGE_CABINET_DISABLE") != "1"
    if last and not force and not reparse and not cabinet_due and time.time() - float(last) < OGE_MIN_HOURS * 3600:
        return []
    fl = oge_filings()
    cabinet_first = meta_get("oge_cabinet_seeded") != "1"   # first pass over the VP / Cabinet: history, no alerts
    if os.environ.get("OGE_CABINET_DISABLE") != "1":
        try:
            import exec_oge
            fl += exec_oge.filings(UA)
        except Exception as e:
            note(f"Executive (OGE cabinet index) failed: {e}")
            cabinet_first = False
            fl = [f for f in fl if not f.get("exec")]
    with db() as c:
        known = {r["id"] for r in c.execute("SELECT id FROM filings WHERE source='oge'")}
        done = set() if reparse else {r["id"] for r in c.execute(
            "SELECT id FROM filings WHERE source='oge' AND status IN ('parsed','no_transactions')")}
    # 278-Ts first, so annual reports can be de-duplicated against them
    todo = sorted([f for f in fl if f"oge:{f['docid']}" not in done], key=lambda f: (f["kind"] != "278t", f["received"]))
    note(f"Executive (OGE): {len(fl)} filings listed, {len(todo)} to process{' (parser update: re-parsing all)' if reparse else ''}")
    idx = ticker_index()
    new_rows, failed = [], 0
    for f in todo:
        fid = f"oge:{f['docid']}"
        if f.get("exec"):
            import exec_oge
            person = dict(exec_oge.PEOPLE[f["who"]], state="US")
        else:
            person = EXEC_PEOPLE[f["who"]]
        pdf = OGE_DIR / f"{f['docid']}.pdf"
        # a filing we had already processed, or any annual report, only adds history: never alert on those rows
        backfill = fid in known or f["kind"] == "278e" or (f.get("exec") and cabinet_first)
        received, note_txt, dropped = f["received"], None, 0
        try:
            if not pdf.exists():
                rr = requests.get(f["url"], headers=UA, timeout=600)
                rr.raise_for_status()
                pdf.write_bytes(rr.content)
            if f.get("exec"):   # Integrity.gov e-filed reports (text layer); scanned ones go through the OCR path
                import exec_oge
                text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True).stdout
                txs = exec_oge.parse_integrity(text)
                if not txs and f["kind"] == "278e":
                    txs = oge_parser.parse_278e(text)
                if not txs and f["kind"] == "278t" and len(text.strip()) < 400:
                    txs = _parse_oge_pdf(pdf, received, amended=f["amended"])
                if f["kind"] == "278e":
                    got = oge_parser.received_278e(text)
                    received = got.isoformat() if got else received
                    note_txt = f"From the OGE 278e {f['label'].lower()} report"
                txs = exec_oge.sane_dates(txs, received)
                for t in txs:
                    t.setdefault("ticker", exec_oge.ticker_of(t["asset"]))
            elif f["kind"] == "278e":
                text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True).stdout
                got = oge_parser.received_278e(text)
                received = got.isoformat() if got else received
                txs = oge_parser.parse_278e(text)
                what = "termination report" if f["label"].startswith("Termination") else \
                    f"annual report for {int(f['label'][-5:-1]) - 1}" if re.search(r"\(\d{4}\)$", f["label"]) else "annual report"
                note_txt = f"From the OGE 278e {what}"
            else:
                txs = _parse_oge_pdf(pdf, received, amended=f["amended"])
            status = "parsed" if txs else "no_transactions"
        except Exception as e:
            note(f"OGE {f['file_name']} failed: {e}")
            failed += 1
            continue
        with db() as c:
            if f["kind"] == "278e":
                txs, dropped = _dedupe_278e(c, person["name"], fid, txs)
            c.execute("INSERT OR REPLACE INTO filings VALUES(?,?,?,?,?,?,?,?,?,?)",
                      (fid, "oge", "Executive", person["name"], person["role"], received, f["url"], status,
                       len(txs), now()))
            prev = {r["uid"]: r["first_seen"] for r in c.execute("SELECT uid, first_seen FROM trades WHERE filing_id=?", (fid,))}
            c.execute("DELETE FROM trades WHERE filing_id=?", (fid,))
            used = set()
            for i, t in enumerate(txs):
                if f["kind"] == "278e":
                    uid = f"{fid}:e{i + 1}"
                else:
                    uid = f"{fid}:{t['n'] or 'x' + str(i)}"
                    k = 2
                    while uid in used:  # a misread row number must not silently overwrite another row
                        uid = f"{fid}:{t['n']}-{k}"
                        k += 1
                used.add(uid)
                hit = ((t["ticker"], None) if t.get("ticker") else None) or (idx.match(t["asset"]) if idx else None)
                kind = oge_parser.asset_kind(t["asset"])
                desc = note_txt or ("Amended by the filer (OGE 278-T amendment)" if t.get("amended") else
                                    "Reported more than 30 days after notification" if t.get("late") else None)
                row = {"uid": uid, "source": "oge", "filing_id": fid, "chamber": "Executive",
                       "politician": person["name"], "last_name": person["last"], "party": person["party"],
                       "state": person["state"], "district": person["role"], "owner": None,
                       "ticker": hit[0] if hit else None, "asset": t["asset"],
                       "asset_type": ("EF" if kind == "EF" else "ST") if hit else kind,
                       "tx_type": t["tx_type"], "side": side_of(t["tx_type"]), "tx_date": t["tx_date"],
                       "disclosure_date": received, "amount": t["amount"], "amount_low": t["amount_low"],
                       "amount_high": t["amount_high"], "description": desc,
                       "url": f["url"], "fetched_at": now(), "bioguide": person.get("bioguide"),
                       "first_seen": prev.get(uid) or (received + "T12:00:00+00:00" if backfill else first_seen_for(received))}
                insert_trade(c, row, ignore=True)
                if uid not in prev and not backfill:
                    new_rows.append(row)
            for (tk,) in c.execute("SELECT DISTINCT ticker FROM trades WHERE filing_id=? AND ticker IS NOT NULL", (fid,)).fetchall():
                c.execute(EST_SQL, (tk,))  # reuse cached daily prices for the trade-day estimate
        note(f"OGE {f['file_name']}: {status}, {len(txs)} transactions"
             + (f" ({dropped} already on a 278-T)" if dropped else "") + (" [backfill, no alerts]" if backfill else ""))
    meta_set("oge_last_fetch", str(time.time()))
    if cabinet_first and not failed:
        meta_set("oge_cabinet_seeded", "1")
    if reparse and not failed:
        meta_set("oge_parser_version", OGE_PARSER_VERSION)
    return new_rows


# ---------------------------------------------------------------- prices (Yahoo chart API)
def yahoo_symbol(t):
    if not t or "$" in t or len(t) > 8:
        return None
    return t.replace(".", "-").replace("/", "-")


def _fetch_chart(sym, start=None):
    params = {"interval": "1d", "includeAdjustedClose": "true"}
    if start:
        params.update({"period1": int(datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp()),
                       "period2": int(time.time()) + 86400})
    else:
        params["range"] = "5d"
    for attempt in range(3):
        r = requests.get(YAHOO.format(sym=sym), params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        if r.status_code == 429:
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code in (400, 404):
            return None
        r.raise_for_status()
        res = (r.json().get("chart") or {}).get("result")
        return res[0] if res else None
    raise RuntimeError("rate limited")


EST_SQL = """UPDATE trades SET
    est_price = (SELECT close FROM prices p WHERE p.ticker=trades.ticker AND p.d<=trades.tx_date
                 AND p.d >= date(trades.tx_date,'-4 days') ORDER BY p.d DESC LIMIT 1),
    est_adj = (SELECT adjclose FROM prices p WHERE p.ticker=trades.ticker AND p.d<=trades.tx_date
                 AND p.d >= date(trades.tx_date,'-4 days') ORDER BY p.d DESC LIMIT 1),
    est_date = (SELECT d FROM prices p WHERE p.ticker=trades.ticker AND p.d<=trades.tx_date
                 AND p.d >= date(trades.tx_date,'-4 days') ORDER BY p.d DESC LIMIT 1)
    WHERE ticker=? AND est_price IS NULL AND (asset_type IS NULL OR asset_type IN ('ST','EF'))"""


BENCH_TICKERS = ("SPY",)
BENCH_FROM = "2014-12-01"


def update_prices(max_tickers=None):
    """Fetch daily history for tickers lacking an estimated trade price, then refresh stale current quotes."""
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    with db() as c:
        need = c.execute("""SELECT ticker, MIN(tx_date) mind FROM trades
            WHERE ticker IS NOT NULL AND tx_date IS NOT NULL AND est_price IS NULL
              AND (asset_type IS NULL OR asset_type IN ('ST','EF'))
              AND ticker NOT IN (SELECT ticker FROM quotes WHERE status='nodata' AND checked_at > ?)
              AND ticker NOT IN (SELECT ticker FROM quotes WHERE status='ok' AND hist_from <= trades.tx_date
                                 AND checked_at > ?)
            GROUP BY ticker""", (week_ago, week_ago)).fetchall()
        stale = c.execute("""SELECT ticker FROM quotes WHERE status='ok' AND checked_at < ?
            AND ticker IN (SELECT ticker FROM trades WHERE disclosure_date >= ?)""",
                          ((datetime.now(timezone.utc) - timedelta(hours=6)).isoformat(),
                           (date.today() - timedelta(days=400)).isoformat())).fetchall()
    need = list(need)[:max_tickers] if max_tickers else list(need)
    need_set = {r["ticker"] for r in need}
    jobs = [(r["ticker"], (datetime.fromisoformat(r["mind"]) - timedelta(days=10)).date().isoformat()) for r in need]
    jobs += [(r["ticker"], None) for r in stale if r["ticker"] not in need_set]
    # benchmark(s) for the copy-trade simulator: full history once, then the usual recent refresh
    with db() as c:
        for b in BENCH_TICKERS:
            q = c.execute("SELECT hist_from, checked_at FROM quotes WHERE ticker=?", (b,)).fetchone()
            if not q or not q["hist_from"] or q["hist_from"] > BENCH_FROM:
                jobs.append((b, BENCH_FROM))
            elif (q["checked_at"] or "") < (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat():
                jobs.append((b, (date.today() - timedelta(days=10)).isoformat()))
    if not jobs:
        return 0

    def work(job):
        tick, start = job
        sym = yahoo_symbol(tick)
        if not sym:
            return tick, sym, start, None
        try:
            return tick, sym, start, _fetch_chart(sym, start)
        except Exception as e:
            log.warning("price %s: %s", tick, e)
            return tick, sym, start, "error"

    ok = 0
    with ThreadPoolExecutor(max_workers=4) as ex:
        for tick, sym, start, res in ex.map(work, jobs):
            if res == "error":
                continue
            with db() as c:
                if not res or not res.get("timestamp"):
                    c.execute("""INSERT INTO quotes(ticker,symbol,status,checked_at) VALUES(?,?,?,?)
                        ON CONFLICT(ticker) DO UPDATE SET checked_at=excluded.checked_at,
                        status=CASE WHEN quotes.price IS NULL THEN 'nodata' ELSE quotes.status END""",
                              (tick, sym, "nodata", now()))
                    continue
                m = res["meta"]
                q = res["indicators"]["quote"][0]
                adj = (res["indicators"].get("adjclose") or [{}])[0].get("adjclose") or q["close"]
                tz = m.get("gmtoffset", 0)
                for i, ts in enumerate(res["timestamp"]):
                    if q["close"][i] is None:
                        continue
                    d = datetime.fromtimestamp(ts + tz, timezone.utc).date().isoformat()
                    c.execute("INSERT OR REPLACE INTO prices VALUES(?,?,?,?,?,?,?)",
                              (tick, d, q["open"][i], q["high"][i], q["low"][i], q["close"][i], adj[i]))
                as_of = datetime.fromtimestamp(m.get("regularMarketTime", time.time()), timezone.utc).isoformat()
                c.execute("""INSERT INTO quotes(ticker,symbol,price,as_of,name,status,hist_from,checked_at)
                    VALUES(?,?,?,?,?,?,?,?)
                    ON CONFLICT(ticker) DO UPDATE SET symbol=excluded.symbol, price=excluded.price, as_of=excluded.as_of,
                    name=COALESCE(excluded.name, quotes.name), status='ok',
                    hist_from=COALESCE(MIN(quotes.hist_from, excluded.hist_from), quotes.hist_from, excluded.hist_from),
                    checked_at=excluded.checked_at""",
                          (tick, sym, m.get("regularMarketPrice"), as_of, m.get("longName") or m.get("shortName"),
                           "ok", start, now()))
                if start:
                    c.execute(EST_SQL, (tick,))
                ok += 1
    note(f"Prices: updated {ok} of {len(jobs)} tickers")
    return ok


# ---------------------------------------------------------------- notifications (Web Push, see webpush.py)
def follow_topic(name):
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40]
    return f"{NTFY_TOPIC}-{slug}" if NTFY_TOPIC else None


def notify(new_rows):
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    new_rows = [r for r in new_rows if r["first_seen"] >= cutoff]
    if new_rows:
        evs, sent = [], set()
        try:  # unusual activity that these new disclosures created (each event alerted once)
            import unusual
            since = (date.today() - timedelta(days=unusual.LOOKBACK_DAYS + 5)).isoformat()
            sent = set(json.loads(meta_get("unusual_sent") or "[]"))
            try:
                ctx = _committee_context()
            except Exception:
                ctx = None
            with db() as c:
                rows = c.execute(f"{TRADE_SELECT} WHERE t.tx_date >= ? OR t.disclosure_date >= ?", (since, since)).fetchall()
                evs = unusual.for_new(c, rows, new_rows, sent, ctx)
        except Exception as e:
            note(f"unusual check failed: {e}")
        try:  # native Web Push to installed PWAs (same rows, same dedupe/backfill rules as before)
            import webpush
            webpush.send(new_rows, meta_get, meta_set, note, unusual=evs)
        except Exception as e:
            note(f"push failed: {e}")
        if evs:
            meta_set("unusual_sent", json.dumps((sorted(sent) + [e["key"] for e in evs])[-5000:]))
    # ntfy alert topics were retired on 2026-10-22: alerts are native Web Push only (webpush.py).
    # ntfy.sh is still used internally as the free registration channel for push subscriptions.


# ---------------------------------------------------------------- refresh loop
def refresh(force_senate=False, do_notify=True):
    if not _lock.acquire(blocking=False):
        return False
    _state["running"] = True
    new_rows = []
    try:
        load_legislators()
        for y in HOUSE_YEARS:
            try:
                new_rows += fetch_house_year(y)
            except Exception as e:
                note(f"House {y} failed: {e}")
                _state["last_error"] = f"House {y}: {e}"
        try:
            new_rows += fetch_senate(force=force_senate)
        except Exception as e:
            note(f"Senate failed: {e}")
            _state["last_error"] = f"Senate: {e}"
        try:
            import senate_efd
            import sys as _sys
            new_rows += senate_efd.fetch(_sys.modules[__name__])
        except Exception as e:
            note(f"Senate eFD failed: {e}")
            _state["last_error"] = f"Senate eFD: {e}"
        if os.environ.get("OGE_DISABLE") != "1":
            try:
                new_rows += fetch_oge()
            except Exception as e:
                note(f"Executive (OGE) failed: {e}")
                _state["last_error"] = f"OGE: {e}"
        meta_set("last_refresh", now())
        try:
            import webpush
            webpush.sync(meta_get, meta_set, note)
        except Exception as e:
            note(f"push sync failed: {e}")
        if do_notify:
            notify(new_rows)
        try:
            update_prices()
        except Exception as e:
            note(f"Prices failed: {e}")
        try:
            _committee_context(fetch_missing=150)
        except Exception as e:
            note(f"Committee context failed: {e}")
        meta_set("last_refresh", now())
        _pf_cache.clear()
        threading.Thread(target=portfolio_summaries, daemon=True).start()
    finally:
        _state["running"] = False
        _lock.release()
    return True


def scheduler():
    while True:
        try:
            refresh()
        except Exception as e:
            log.exception("refresh failed: %s", e)
        time.sleep(REFRESH_MINUTES * 60)


# ---------------------------------------------------------------- API
app = FastAPI(title="The Black House")


@app.on_event("startup")
def _startup():
    init_db()
    load_legislators()
    seed = DATA / "bargo_senate_seed.json"
    if seed.exists() and not meta_get("bargo_seeded"):
        ingest_bargo(json.loads(seed.read_text()).get("trades", []))
        meta_set("bargo_seeded", "1")
        if not meta_get("bargo_last_fetch"):
            meta_set("bargo_last_fetch", str(seed.stat().st_mtime))
    with db() as c:  # fill bioguide/party for rows created before bioguide support
        for r in c.execute("""SELECT DISTINCT filing_id, district, last_name FROM trades
                              WHERE source='house_clerk' AND bioguide IS NULL""").fetchall():
            party, bid = house_lookup(r["district"], r["last_name"])
            if bid:
                c.execute("UPDATE trades SET bioguide=?, party=COALESCE(party, ?) WHERE filing_id=?",
                          (bid, party, r["filing_id"]))
    ingest_bargo([])
    threading.Thread(target=portfolio_summaries, daemon=True).start()
    if os.environ.get("NO_SCHEDULER") != "1":
        threading.Thread(target=scheduler, daemon=True).start()


TRADE_SELECT = """SELECT t.*, q.price AS cur_price, q.as_of AS cur_as_of, q.name AS company,
    CASE WHEN t.est_adj > 0 AND q.price > 0 THEN ROUND((q.price - t.est_adj) / t.est_adj * 100, 2) END AS pct_since,
    pd.low AS day_low, pd.high AS day_high, pd.open AS day_open,
    CAST(julianday(t.disclosure_date) - julianday(t.tx_date) AS INTEGER) AS lag_days
    FROM trades t LEFT JOIN quotes q ON q.ticker = t.ticker AND q.status='ok'
    LEFT JOIN prices pd ON pd.ticker = t.ticker AND pd.d = t.est_date"""
MID = "((COALESCE(t.amount_low,0) + COALESCE(t.amount_high, t.amount_low, 0)) / 2.0)"


# ---------------------------------------------------------------- smart search (mirrors web/static/search.js)
SEARCH_ALIASES = {'mp materials': (('MP',), ('mp matls',)), 'usa rare earth': (('USAR',), ()), 'google': (('GOOGL', 'GOOG', 'GOOGM', 'GOOGN'), ('alphabet',)), 'alphabet': (('GOOGL', 'GOOG', 'GOOGM', 'GOOGN'), ()), 'youtube': (('GOOGL', 'GOOG'), ('alphabet',)), 'waymo': (('GOOGL', 'GOOG'), ('alphabet',)), 'facebook': (('META', 'FB'), ('meta platforms',)), 'meta': (('META', 'FB'), ()), 'instagram': (('META', 'FB'), ('meta platforms',)), 'whatsapp': (('META', 'FB'), ('meta platforms',)), 'berkshire': (('BRK.B', 'BRK.A'), ()), 'berkshire hathaway': (('BRK.B', 'BRK.A'), ()), 'buffett': (('BRK.B', 'BRK.A'), ('berkshire',)), 'tesla': (('TSLA',), ()), 'amazon': (('AMZN',), ()), 'aws': (('AMZN',), ('amazon',)), 'microsoft': (('MSFT',), ()), 'apple': (('AAPL',), ()), 'iphone': (('AAPL',), ('apple inc',)), 'nvidia': (('NVDA',), ()), 'netflix': (('NFLX',), ()), 'disney': (('DIS',), ()), 'walmart': (('WMT',), ()), 'costco': (('COST',), ()), 'jpmorgan': (('JPM',), ()), 'jp morgan': (('JPM',), ()), 'chase': (('JPM',), ('jpmorgan',)), 'bank of america': (('BAC',), ()), 'bofa': (('BAC',), ()), 'goldman': (('GS',), ()), 'goldman sachs': (('GS',), ()), 'morgan stanley': (('MS',), ()), 'wells fargo': (('WFC',), ()), 'citi': (('C',), ()), 'citigroup': (('C',), ()), 'visa': (('V',), ()), 'mastercard': (('MA',), ()), 'paypal': (('PYPL',), ()), 'amex': (('AXP',), ()), 'american express': (('AXP',), ()), 'blackrock': (('BLK',), ()), 'coca cola': (('KO',), ()), 'coca-cola': (('KO',), ()), 'coke': (('KO',), ('coca-cola',)), 'pepsi': (('PEP',), ()), 'pepsico': (('PEP',), ()), 'mcdonalds': (('MCD',), ()), "mcdonald's": (('MCD',), ()), 'starbucks': (('SBUX',), ()), 'nike': (('NKE',), ()), 'boeing': (('BA',), ()), 'lockheed': (('LMT',), ()), 'lockheed martin': (('LMT',), ()), 'raytheon': (('RTX',), ()), 'northrop': (('NOC',), ()), 'general dynamics': (('GD',), ()), 'intel': (('INTC',), ()), 'amd': (('AMD',), ()), 'broadcom': (('AVGO',), ()), 'qualcomm': (('QCOM',), ()), 'oracle': (('ORCL',), ()), 'salesforce': (('CRM',), ()), 'adobe': (('ADBE',), ()), 'ibm': (('IBM',), ()), 'cisco': (('CSCO',), ()), 'palantir': (('PLTR',), ()), 'uber': (('UBER',), ()), 'airbnb': (('ABNB',), ()), 'exxon': (('XOM',), ()), 'exxonmobil': (('XOM',), ()), 'chevron': (('CVX',), ()), 'pfizer': (('PFE',), ()), 'moderna': (('MRNA',), ()), 'johnson & johnson': (('JNJ',), ()), 'johnson and johnson': (('JNJ',), ()), 'j&j': (('JNJ',), ()), 'unitedhealth': (('UNH',), ()), 'lilly': (('LLY',), ()), 'eli lilly': (('LLY',), ()), 'home depot': (('HD',), ()), 'at&t': (('T',), ()), 'verizon': (('VZ',), ()), 'comcast': (('CMCSA',), ()), 'tsmc': (('TSM',), ()), 'taiwan semiconductor': (('TSM',), ()), 'coinbase': (('COIN',), ()), 'microstrategy': (('MSTR',), ()), 'snowflake': (('SNOW',), ()), 'crowdstrike': (('CRWD',), ()), 'shopify': (('SHOP',), ()), 'spotify': (('SPOT',), ()), 's&p 500': (('SPY', 'VOO', 'IVV'), ()), 's&p': (('SPY', 'VOO', 'IVV'), ()), 'nasdaq': (('QQQ',), ()), 'trump media': (('DJT',), ()), 'truth social': (('DJT',), ('trump media',)), 'general electric': (('GE',), ()), 'general motors': (('GM',), ()), 'ford': (('F',), ()), 'target': (('TGT',), ()), 'dell': (('DELL',), ()), 'micron': (('MU',), ()), 'supermicro': (('SMCI',), ()), 'super micro': (('SMCI',), ()), 'robinhood': (('HOOD',), ()), 'bitcoin': (('IBIT', 'FBTC', 'GBTC', 'MSTR', 'COIN'), ()), 'gamestop': (('GME',), ()), 'amc': (('AMC',), ()), 'rivian': (('RIVN',), ()), 'lucid': (('LCID',), ()), 'ups': (('UPS',), ()), 'fedex': (('FDX',), ()), 'caterpillar': (('CAT',), ()), 'deere': (('DE',), ()), 'john deere': (('DE',), ()), '3m': (('MMM',), ()), 'procter': (('PG',), ()), 'procter & gamble': (('PG',), ()), 'p&g': (('PG',), ()), 'merck': (('MRK',), ()), 'abbvie': (('ABBV',), ()), 'amgen': (('AMGN',), ()), 'gilead': (('GILD',), ()), 'cvs': (('CVS',), ()), 'walgreens': (('WBA',), ()), 'servicenow': (('NOW',), ()), 'intuit': (('INTU',), ()), 'applied materials': (('AMAT',), ()), 'lam research': (('LRCX',), ()), 'asml': (('ASML',), ()), 'arm': (('ARM',), ()), 'zoom': (('ZM',), ()), 'salesforce.com': (('CRM',), ()), 'dupont': (('DD',), ()), 'dow': (('DOW',), ()), 'honeywell': (('HON',), ()), 'verisign': (('VRSN',), ())}
_STATES = {"AL":"alabama","AK":"alaska","AZ":"arizona","AR":"arkansas","CA":"california","CO":"colorado","CT":"connecticut","DE":"delaware","FL":"florida","GA":"georgia","HI":"hawaii","ID":"idaho","IL":"illinois","IN":"indiana","IA":"iowa","KS":"kansas","KY":"kentucky","LA":"louisiana","ME":"maine","MD":"maryland","MA":"massachusetts","MI":"michigan","MN":"minnesota","MS":"mississippi","MO":"missouri","MT":"montana","NE":"nebraska","NV":"nevada","NH":"new hampshire","NJ":"new jersey","NM":"new mexico","NY":"new york","NC":"north carolina","ND":"north dakota","OH":"ohio","OK":"oklahoma","OR":"oregon","PA":"pennsylvania","RI":"rhode island","SC":"south carolina","SD":"south dakota","TN":"tennessee","TX":"texas","UT":"utah","VT":"vermont","VA":"virginia","WA":"washington","WV":"west virginia","WI":"wisconsin","WY":"wyoming","DC":"district of columbia","PR":"puerto rico","GU":"guam","VI":"virgin islands","AS":"american samoa","MP":"northern mariana islands"}
_PARTY = {"D": "democrat democratic dem", "R": "republican gop rep", "I": "independent ind"}
_SIDE = {"buy": "buy bought purchase", "sell": "sell sold sale"}


def _snorm(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    return re.sub(r"\s+", " ", "".join(ch for ch in s if not unicodedata.combining(ch))).strip()


def _scompact(s):
    return re.sub(r"[^a-z0-9]", "", _snorm(s))


def _stick(s):
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())


_SKEYS = [(_snorm(k), {_stick(t) for t in v[0]}, v[1]) for k, v in SEARCH_ALIASES.items()]
_SMULTI = sorted([k for k, _, _ in _SKEYS if " " in k], key=len, reverse=True)


def _alias_tickers(text):
    out, names = set(), set()
    for k, ts, ns in _SKEYS:
        if k == text or (len(text) >= 3 and len(k) >= 4 and k.startswith(text)):
            out |= ts
            names |= set(ns)
    return out, tuple(sorted(names))


@functools.lru_cache(maxsize=256)
def _sparse(q):
    s = " " + _snorm(q).replace('"', "").replace("'", "") + " "
    terms = []
    for k in _SMULTI:
        if " " + k + " " in s:
            terms.append(k); s = s.replace(" " + k + " ", " ")
        elif len(s.strip()) >= 3 and " " in s.strip() and k.startswith(s.strip()):
            terms.append(s.strip()); s = " "
    terms += [w for w in s.split(" ") if w]
    return tuple((t, _scompact(t), _stick(t), frozenset(_alias_tickers(t)[0]), _alias_tickers(t)[1]) for t in terms)


def search_match(q, politician, ticker, asset, company, description, party, state, chamber, tx_type, side, owner):
    terms = _sparse(q or "")
    if not terms:
        return 1
    st = (state or "").upper()
    h = _snorm(" | ".join(x for x in [politician, ticker, asset, company, (description or "")[:200], _PARTY.get(party, party),
                                       f"{party}-{st}" if party and st else "", st, _STATES.get(st), chamber,
                                       "white house trump" if chamber == "President" else "", tx_type, _SIDE.get(side, side), owner] if x))
    hc, tk = re.sub(r"[^a-z0-9]", "", h), _stick(ticker)
    for text, c, ttk, alias, names in terms:
        if tk and (tk in alias or (ttk and tk.startswith(ttk))):
            continue
        if text in h or any(n in h for n in names) or (len(c) >= 3 and c in hc):
            continue
        return 0
    return 1


def _where(q=None, politician=None, ticker=None, chamber=None, party=None, side=None,
           date_from=None, date_to=None, date_field="disclosure_date", asset=None):
    w, a = [], []
    if asset == "stock":
        w.append("t.ticker IS NOT NULL AND (t.asset_type IS NULL OR t.asset_type IN ('ST','EF'))")
    elif asset == "other":
        w.append("NOT (t.ticker IS NOT NULL AND (t.asset_type IS NULL OR t.asset_type IN ('ST','EF')))")
    df = "t.tx_date" if date_field == "tx_date" else "t.disclosure_date"
    if q:
        w.append("bh_match(?, t.politician, t.ticker, t.asset, (SELECT name FROM quotes WHERE ticker = t.ticker), t.description, "
                 "t.party, t.state, t.chamber, t.tx_type, t.side, t.owner) = 1")
        a.append(q)
    if politician:
        w.append("t.politician = ?"); a.append(politician)
    if ticker:
        w.append("UPPER(t.ticker) = UPPER(?)"); a.append(ticker)
    if chamber:
        w.append("t.chamber = ?"); a.append(chamber)
    if party:
        w.append("t.party = ?"); a.append(party)
    if side:
        w.append("t.side = ?"); a.append(side)
    if date_from:
        w.append(f"{df} >= ?"); a.append(date_from)
    if date_to:
        w.append(f"{df} <= ?"); a.append(date_to)
    return (" WHERE " + " AND ".join(w)) if w else "", a


SORTS = {
    "disclosure_date": "t.disclosure_date DESC, t.first_seen DESC, t.tx_date DESC, t.uid",
    "tx_date": "t.tx_date DESC, t.disclosure_date DESC, t.uid",
    "amount": "(t.amount_low IS NULL), " + "((COALESCE(t.amount_low,0) + COALESCE(t.amount_high, t.amount_low, 0)) / 2.0)" + " DESC, t.disclosure_date DESC, t.uid",
    "amount_asc": "(t.amount_low IS NULL), " + "((COALESCE(t.amount_low,0) + COALESCE(t.amount_high, t.amount_low, 0)) / 2.0)" + " ASC, t.disclosure_date DESC, t.uid",
    "tx_oldest": "t.tx_date ASC, t.uid",
    "oldest": "t.disclosure_date ASC, t.tx_date ASC, t.uid",
    "move": "pct_since IS NULL, ABS(pct_since) DESC, t.disclosure_date DESC",
}


@app.get("/api/trades")
def trades(q: Optional[str] = None, politician: Optional[str] = None, ticker: Optional[str] = None,
           chamber: Optional[str] = None, party: Optional[str] = None, side: Optional[str] = None,
           date_from: Optional[str] = None, date_to: Optional[str] = None,
           date_field: str = "disclosure_date", sort: str = "disclosure_date", asset: Optional[str] = None,
           limit: int = Query(50, le=500), offset: int = 0):
    where, a = _where(q, politician, ticker, chamber, party, side, date_from, date_to, date_field, asset)
    with db() as c:
        total = c.execute(f"SELECT COUNT(*) FROM trades t{where}", a).fetchone()[0]
        rows = c.execute(f"{TRADE_SELECT}{where} ORDER BY {SORTS.get(sort, SORTS['disclosure_date'])} LIMIT ? OFFSET ?",
                         a + [limit, offset]).fetchall()
    return {"total": total, "trades": [dict(r) for r in rows]}


@app.get("/api/stats")
def stats(days: int = 30, chamber: Optional[str] = None, party: Optional[str] = None):
    since = (date.today() - timedelta(days=days)).isoformat()
    where, a = _where(chamber=chamber, party=party, date_from=since, date_field="disclosure_date")
    with db() as c:
        tick = c.execute(f"""SELECT t.ticker, MAX(t.asset) asset, MAX(q.name) company, COUNT(*) n,
                SUM(t.side='buy') buys, SUM(t.side='sell') sells, COUNT(DISTINCT t.politician) pols
                FROM trades t LEFT JOIN quotes q ON q.ticker=t.ticker {where}
                {'AND' if where else 'WHERE'} t.ticker IS NOT NULL
                GROUP BY t.ticker ORDER BY n DESC LIMIT 8""", a).fetchall()
        pols = c.execute(f"""SELECT t.politician, t.chamber, MAX(t.party) party, MAX(t.state) state,
                MAX(t.bioguide) bioguide, COUNT(*) n, SUM(t.side='buy') buys, SUM(t.side='sell') sells,
                MAX(t.disclosure_date) latest
                FROM trades t{where} GROUP BY t.politician, t.chamber ORDER BY n DESC LIMIT 8""", a).fetchall()
        tot = c.execute(f"""SELECT COUNT(*) n, SUM(t.side='buy') buys, SUM(t.side='sell') sells,
                COUNT(DISTINCT t.politician) pols, SUM(COALESCE(t.amount_low,0)) vol_low,
                SUM(COALESCE(t.amount_high,t.amount_low,0)) vol_high FROM trades t{where}""", a).fetchone()
    return {"days": days, "since": since, "totals": dict(tot), "top_tickers": [dict(r) for r in tick],
            "top_politicians": [dict(r) for r in pols]}


@app.get("/api/tickers")
def tickers(days: int = 30, chamber: Optional[str] = None):
    since = (date.today() - timedelta(days=days)).isoformat()
    where, a = _where(chamber=chamber, date_from=since, asset="stock")
    with db() as c:
        rows = c.execute(f"""SELECT UPPER(t.ticker) ticker, MAX(q.name) company, MAX(t.asset) asset, COUNT(*) n,
            SUM(t.side='buy') buys, SUM(t.side='sell') sells, COUNT(DISTINCT t.politician) people,
            MAX(t.disclosure_date) last, SUM({MID}) volume, MAX(q.price) price
            FROM trades t LEFT JOIN quotes q ON q.ticker=t.ticker AND q.status='ok'{where}
            GROUP BY UPPER(t.ticker) ORDER BY n DESC LIMIT 200""", a).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/politicians")
def politicians():
    with db() as c:
        rows = c.execute(f"""SELECT politician, chamber, MAX(party) party, MAX(state) state, MAX(district) district,
            MAX(bioguide) bioguide, COUNT(*) n, MAX(disclosure_date) latest, MAX(tx_date) latest_tx,
            SUM(side='buy') buys, SUM(side='sell') sells, SUM({MID}) volume,
            SUM(CASE WHEN disclosure_date >= date('now','-365 days') THEN 1 ELSE 0 END) n_1y
            FROM trades t GROUP BY politician, chamber ORDER BY politician""").fetchall()
    return [dict(r) for r in rows]


@app.get("/api/politician")
def politician(name: str):
    with db() as c:
        rows = c.execute(f"{TRADE_SELECT} WHERE t.politician=? ORDER BY {SORTS['disclosure_date']}", (name,)).fetchall()
        if not rows:
            raise HTTPException(404, "not found")
        tick = c.execute("""SELECT ticker, MAX(asset) asset, COUNT(*) n, SUM(side='buy') buys, SUM(side='sell') sells
            FROM trades WHERE politician=? AND ticker IS NOT NULL GROUP BY ticker ORDER BY n DESC LIMIT 20""",
                         (name,)).fetchall()
        fil = c.execute("SELECT * FROM filings WHERE politician=? ORDER BY filing_date DESC", (name,)).fetchall()
        mon = c.execute(f"""SELECT substr(tx_date,1,7) m, SUM(side='buy') buys, SUM(side='sell') sells,
            SUM(CASE WHEN side='buy' THEN {MID} ELSE 0 END) buy_vol, SUM(CASE WHEN side='sell' THEN {MID} ELSE 0 END) sell_vol
            FROM trades t WHERE politician=? AND tx_date >= date('now','-24 months') AND tx_date <= date('now')
            GROUP BY m ORDER BY m""", (name,)).fetchall()
    r0 = dict(rows[0])
    vol_lo = sum(r["amount_low"] or 0 for r in rows)
    vol_hi = sum(r["amount_high"] or r["amount_low"] or 0 for r in rows)
    lags = sorted(r["lag_days"] for r in rows if r["lag_days"] is not None and r["lag_days"] >= 0)
    txd = sorted(r["tx_date"] for r in rows if r["tx_date"])
    extra = {"vol_low": vol_lo, "vol_high": vol_hi, "median_lag": lags[len(lags) // 2] if lags else None,
             "first_tx": txd[0] if txd else None, "last_tx": txd[-1] if txd else None,
             "latest_disclosure": max((r["disclosure_date"] or "") for r in rows),
             "n_filings": len(fil), "priced": sum(r["est_price"] is not None for r in rows),
             "asset_mix": {k: sum(1 for r in rows if (r["asset_type"] or "") == k) for k in ("ST", "EF", "BOND")}}
    return {**extra, "politician": name, "chamber": r0["chamber"], "party": r0["party"], "state": r0["state"],
            "district": r0["district"], "bioguide": r0["bioguide"], "n": len(rows),
            "buys": sum(r["side"] == "buy" for r in rows), "sells": sum(r["side"] == "sell" for r in rows),
            "top_tickers": [dict(t) for t in tick], "filings": [dict(f) for f in fil],
            "monthly": [dict(m) for m in mon], "trades": [dict(r) for r in rows[:60]]}


# ---------------------------------------------------------------- estimated portfolios
_pf_cache = {}
_pf_lock = threading.Lock()


def _pf(name):
    r = _pf_cache.get(name)
    if r is None:
        with db() as c:
            r = pf.compute(c, name)
        _pf_cache[name] = r
    return r


def portfolio_summaries():
    with _pf_lock:
        if "__summary__" in _pf_cache:
            return _pf_cache["__summary__"]
        with db() as c:
            people = c.execute("""SELECT politician, chamber, MAX(party) party, MAX(state) state, MAX(district) district,
                MAX(bioguide) bioguide, COUNT(*) n, MAX(disclosure_date) latest FROM trades GROUP BY politician, chamber""").fetchall()
        out = []
        for p in people:
            r = _pf(p["politician"])
            if not r["series"]["d"]:
                continue
            per = {k: pf.period_stats(r["series"], k) for k in pf.PERIODS}
            out.append({**dict(p), "value": r["value"], "pnl": r["pnl"], "invested": r["invested"],
                        "periods": per, "spark": pf.spark(r["series"]), "n_holdings": len(r["holdings"]),
                        "n_priced": r["n_priced"], "win_rate": r["win_rate"], "avg_delay": r["avg_delay"],
                        "top": [h["ticker"] for h in r["holdings"][:3]]})
        _pf_cache["__summary__"] = out
        return out


@app.get("/api/intro")
def intro_api():
    """Live numbers for the Home intro. Every figure is computed here from the database:
    late = congressional trades disclosed in the last 12 months more than 45 days after the trade (STOCK Act limit;
    annual OGE 278e entries excluded, same rule as unusual.py 'late'); beat = portfolios with enough data
    (est. value >= $50K, 5+ priced trades, the same rule as Top performers) whose 1-year time-weighted return beat SPY's."""
    yr = (date.today() - timedelta(days=365)).isoformat()
    with db() as c:
        n_trades = c.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        late = c.execute("""SELECT COUNT(*), COUNT(DISTINCT politician),
                SUM(CASE WHEN julianday(disclosure_date) - julianday(tx_date) > 45 THEN 1 ELSE 0 END),
                COUNT(DISTINCT CASE WHEN julianday(disclosure_date) - julianday(tx_date) > 45 THEN politician END)
            FROM trades WHERE chamber IN ('House', 'Senate') AND disclosure_date >= ? AND tx_date IS NOT NULL
              AND tx_date <= disclosure_date AND COALESCE(description, '') NOT LIKE 'From the OGE 278e%'""", (yr,)).fetchone()
        a = c.execute("SELECT adjclose, d FROM prices WHERE ticker='SPY' AND adjclose > 0 ORDER BY d DESC LIMIT 1").fetchone()
        b = c.execute("SELECT adjclose, d FROM prices WHERE ticker='SPY' AND adjclose > 0 AND d <= ? ORDER BY d DESC LIMIT 1", (yr,)).fetchone()
    spy = round((a[0] / b[0] - 1) * 100, 1) if a and b else None
    S = portfolio_summaries()
    el = [p for p in S if p["value"] >= 50_000 and p["n_priced"] >= 5 and (p["periods"].get("1Y") or [None, None])[1] is not None]
    rets = [p["periods"]["1Y"][1] for p in el]
    return {"as_of": a[1] if a else None, "trades": n_trades, "portfolios": len(S),
            "politicians": len({p["politician"] for p in S}),
            "late": {"trades": late[2] or 0, "members": late[3] or 0, "of_trades": late[0], "of_members": late[1], "days": 365},
            "spy_1y": spy, "eligible": len(el), "beat": sum(1 for r in rets if spy is not None and r > spy),
            "best_1y": round(max(rets), 1) if rets else None}


_un_cache = {"t": 0.0, "v": None}


def _unusual_recent(max_age=600):
    """All unusual-activity events of the last 90 days (full, with trade rows); cached for 10 minutes."""
    import unusual
    if _un_cache["v"] is not None and time.time() - _un_cache["t"] < max_age:
        return _un_cache["v"]
    since = (date.today() - timedelta(days=unusual.LOOKBACK_DAYS + 5)).isoformat()
    try:
        ctx = _committee_context()
    except Exception:
        ctx = None
    with db() as c:
        rows = c.execute(f"{TRADE_SELECT} WHERE t.tx_date >= ? OR t.disclosure_date >= ?", (since, since)).fetchall()
        v = unusual.recent(c, rows, ctx)
    _un_cache.update(t=time.time(), v=v)
    return v


@app.get("/api/unusual")
def unusual_api():
    """Unusual activity (see unusual.py): every event of the last 90 days, best first, without trade rows."""
    import unusual
    return {"events": [unusual.summary(e) for e in _unusual_recent()], "alert_types": list(unusual.ALERT_TYPES)}


@app.get("/api/unusual_event")
def unusual_event_api(id: str):
    for e in _unusual_recent():
        if e["id"] == id:
            return e
    raise HTTPException(404, "event not found")


def _committee_context(fetch_missing=0):
    import committees
    com, mem = committees.load_committees(_get_cached, DATA)
    members = sorted({p["bioguide"] for k in committees.COMMITTEE_TAGS for p in mem.get(k, []) if p.get("bioguide")})
    with db() as c:
        cache = committees.load_sectors(meta_get)
        if fetch_missing and members:
            cache = committees.refresh_sectors(c, meta_get, meta_set, note, UA, members, max_n=fetch_missing,
                                               sym=lambda t: yahoo_symbol(t) or t)
    return committees.build(com, mem, cache)


@app.get("/api/context")
def context_api():
    """Committee context: members' current committees, committee -> sectors, ticker -> sector (Yahoo)."""
    return _committee_context()


@app.get("/api/bench")
def bench_api():
    """Benchmark daily closes (SPY) for the copy-trade simulator, same compact format as /api/stock."""
    import stock_page
    with db() as c:
        return {b: stock_page.series(c, b, BENCH_FROM, max_years=12) for b in BENCH_TICKERS}


@app.get("/api/stock")
def stock_api(ticker: str):
    """Stock page: daily closes since the first politician trade (compact) and estimated current holders."""
    import stock_page
    t = ticker.upper().strip()
    with db() as c:
        first = c.execute("SELECT MIN(tx_date) FROM trades WHERE ticker=?", (t,)).fetchone()[0]
        pols = c.execute("SELECT politician, MAX(bioguide) bioguide, MAX(party) party, MAX(chamber) chamber FROM trades "
                         "WHERE ticker=? GROUP BY politician", (t,)).fetchall()
        px = stock_page.series(c, t, first)
    holders = []
    for r in pols:
        try:
            holders += stock_page.holder_rows(t, r["politician"], _pf(r["politician"]), dict(r))
        except Exception:
            pass
    holders.sort(key=lambda h: -h["value"])
    return {"ticker": t, "px": px, "holders": holders}


_MB_CACHE = {}


@app.get("/api/most_bought")
def most_bought_api(days: int = 90, etf: int = 1):
    """Most-bought stocks by trade date window: distinct buyers, then # buys, then est. $ (see most_bought.py)."""
    import time
    import most_bought
    days = days if days in (30, 90, 365) else 90
    key = (days, bool(etf))
    hit = _MB_CACHE.get(key)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    since = (date.today() - timedelta(days=days)).isoformat()
    with db() as c:
        rows = c.execute(f"{TRADE_SELECT} WHERE t.side='buy' AND t.tx_date >= ?", (since,)).fetchall()
    out = {"days": days, "since": since, "items": most_bought.rank(rows, days, bool(etf), 250)}
    _MB_CACHE[key] = (time.time(), out)
    return out


@app.get("/api/portfolios")
def portfolios():
    """Estimated portfolio summary for everyone with priced stock trades (see portfolio.py for the method)."""
    return portfolio_summaries()


@app.get("/api/portfolio")
def portfolio(name: str, holdings: int = Query(200, le=2000)):
    with db() as c:
        p = c.execute("""SELECT chamber, MAX(party) party, MAX(state) state, MAX(district) district, MAX(bioguide) bioguide,
            COUNT(*) n, SUM(side='buy') buys, SUM(side='sell') sells, MAX(disclosure_date) latest, MIN(tx_date) first_tx
            FROM trades WHERE politician=?""", (name,)).fetchone()
    if not p or not p["n"]:
        raise HTTPException(404, "not found")
    r = _pf(name)
    return {**dict(p), **{k: v for k, v in r.items() if k != "holdings"}, "politician": name,
            "holdings": r["holdings"][:holdings], "n_holdings": len(r["holdings"]),
            "periods": {k: pf.period_stats(r["series"], k) for k in pf.PERIODS} if r["series"]["d"] else {},
            "win_days": pf.WIN_DAYS}


@app.get("/api/trade")
def trade(uid: str):
    with db() as c:
        r = c.execute(f"{TRADE_SELECT} WHERE t.uid=?", (uid,)).fetchone()
    if not r:
        raise HTTPException(404, "not found")
    return dict(r)


@app.get("/api/status")
def status():
    with db() as c:
        by = c.execute("""SELECT chamber, source, COUNT(*) n, MAX(disclosure_date) newest_disclosure,
            MIN(disclosure_date) oldest_disclosure, MAX(tx_date) newest_tx, MAX(first_seen) newest_seen
            FROM trades GROUP BY chamber, source""").fetchall()
        fil = c.execute("SELECT status, COUNT(*) n FROM filings GROUP BY status").fetchall()
        pc = c.execute("""SELECT SUM(ticker IS NOT NULL AND (asset_type IS NULL OR asset_type IN ('ST','EF'))) priceable,
            SUM(est_price IS NOT NULL) priced, SUM(ticker IS NOT NULL) with_ticker, COUNT(*) n FROM trades""").fetchone()
    return {"running": _state["running"], "last_refresh": meta_get("last_refresh"), "last_error": _state["last_error"],
            "refresh_minutes": REFRESH_MINUTES, "senate_min_hours": BARGO_MIN_HOURS, "bargo_key": bool(BARGO_KEY),
            "sources": [dict(r) for r in by], "house_filings": {r["status"]: r["n"] for r in fil},
            "prices": dict(pc), "bargo_rate": json.loads(meta_get("bargo_rate", "{}") or "{}"),
            "house_years": HOUSE_YEARS, "log": _state["log"][-15:]}


_last_manual = {"t": 0.0}


@app.post("/api/refresh")
def do_refresh():
    if _state["running"]:
        return {"started": False, "message": "Already refreshing"}
    if time.time() - _last_manual["t"] < 120:
        return {"started": False, "message": "Refreshed moments ago"}
    _last_manual["t"] = time.time()
    threading.Thread(target=refresh, daemon=True).start()
    return {"started": True}


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


# the box layout keeps the frontend in static/; the GitHub repo keeps the Pages build in web/
STATIC_DIR = BASE / "static" if (BASE / "static").exists() else BASE / "web" / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
