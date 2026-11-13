"""Shared SEC EDGAR client for Form 4 and 13F fetches.

Free official endpoints only. A declared User-Agent with a contact email is required;
requests stay under 10/sec with backoff on 403/429.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

import requests

UA = "TheInsiderHouse khurramwajeeh-d0ymqp@mail.grokbot.com"
HEADERS = {
    "User-Agent": UA,
    "Accept-Encoding": "gzip, deflate",
}
MIN_INTERVAL = 0.15  # ~6.6 req/s, under the 10/s cap
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVES = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{name}"
INDEX = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/index.json"
FILING_PAGE = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{acc_dash}-index.htm"

_lock = threading.Lock()
_last = 0.0
_tickers_cache = None
_session = requests.Session()
_session.headers.update(HEADERS)


def pad_cik(cik) -> str:
    return str(cik).lstrip("0").zfill(10) if cik is not None else ""


def bare_cik(cik) -> str:
    return str(cik).lstrip("0") or "0"


def acc_nodash(accession: str) -> str:
    return (accession or "").replace("-", "")


def _throttle():
    global _last
    with _lock:
        wait = MIN_INTERVAL - (time.monotonic() - _last)
        if wait > 0:
            time.sleep(wait)
        _last = time.monotonic()


def get(url, timeout=60, retries=4):
    """GET with throttle, gzip, and backoff on 403/429/5xx. Raises on final failure."""
    last_err = None
    for attempt in range(retries):
        _throttle()
        try:
            r = _session.get(url, timeout=timeout)
        except requests.RequestException as e:
            last_err = e
            time.sleep(min(40, 5 * 2 ** attempt))
            continue
        if r.status_code in (403, 429) or r.status_code >= 500:
            last_err = RuntimeError(f"HTTP {r.status_code} for {url}")
            time.sleep(min(60, 10 * 2 ** attempt))
            continue
        if r.status_code == 404:
            r.raise_for_status()
        r.raise_for_status()
        return r
    if last_err:
        raise last_err
    raise RuntimeError(f"failed GET {url}")


def get_json(url, timeout=60):
    return get(url, timeout=timeout).json()


def get_bytes(url, timeout=60):
    return get(url, timeout=timeout).content


def company_tickers(cache_path: Path | None = None, max_age=86400):
    """Ticker/CIK/title map from the official SEC file. Cached in memory and optionally on disk."""
    global _tickers_cache
    if _tickers_cache is not None:
        return _tickers_cache
    if cache_path and cache_path.exists() and time.time() - cache_path.stat().st_mtime < max_age:
        import json
        _tickers_cache = json.loads(cache_path.read_text())
        return _tickers_cache
    data = get_json(TICKERS_URL)
    rows = list(data.values()) if isinstance(data, dict) else data
    if cache_path:
        import json
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(rows))
    _tickers_cache = rows
    return rows


def ticker_index(cache_path: Path | None = None):
    """{TICKER: {cik, ticker, title}} and a CIK->tickers map."""
    by_ticker, by_cik = {}, {}
    for row in company_tickers(cache_path):
        tk = (row.get("ticker") or "").upper()
        cik = pad_cik(row.get("cik_str"))
        title = row.get("title") or ""
        if not tk or not cik:
            continue
        rec = {"cik": cik, "ticker": tk, "title": title}
        by_ticker[tk] = rec
        by_cik.setdefault(cik, []).append(rec)
    return by_ticker, by_cik


def submissions(cik):
    return get_json(SUBMISSIONS.format(cik=pad_cik(cik)), timeout=90)


def recent_filings(sub, types):
    """Zip filings.recent parallel arrays; types is a set of form strings (exact)."""
    rec = (sub or {}).get("filings", {}).get("recent", {})
    forms = rec.get("form") or []
    accs = rec.get("accessionNumber") or []
    dates = rec.get("filingDate") or []
    reports = rec.get("reportDate") or [""] * len(forms)
    docs = rec.get("primaryDocument") or [""] * len(forms)
    out = []
    for i, form in enumerate(forms):
        if form not in types:
            continue
        out.append({
            "form": form,
            "accession": accs[i],
            "filing_date": dates[i],
            "report_date": reports[i] if i < len(reports) else "",
            "primary": docs[i] if i < len(docs) else "",
        })
    return out


def filing_index(cik, accession):
    return get_json(INDEX.format(cik=bare_cik(cik), acc=acc_nodash(accession)))


def filing_files(cik, accession):
    try:
        d = filing_index(cik, accession)
    except Exception:
        return []
    items = (d.get("directory") or {}).get("item") or []
    return [it.get("name") or "" for it in items]


def archives_url(cik, accession, name):
    return ARCHIVES.format(cik=bare_cik(cik), acc=acc_nodash(accession), name=name.lstrip("/"))


def filing_url(cik, accession):
    acc = accession
    return FILING_PAGE.format(cik=bare_cik(cik), acc=acc_nodash(acc), acc_dash=acc)


def raw_document(cik, accession, primary):
    """Fetch a filing document, dropping an XSL stylesheet folder from primaryDocument if present."""
    name = (primary or "").lstrip("/")
    if "/xsl" in f"/{name}" or name.startswith("xsl"):
        # xslF345X06/form4.xml -> form4.xml; xslForm13F_X02/primary_doc.xml -> primary_doc.xml
        name = name.split("/", 1)[-1]
    url = archives_url(cik, accession, name)
    try:
        return get_bytes(url), url, name
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            return None, url, name
        raise


def first_xml_named(cik, accession, prefer):
    """Pick an XML file from the filing directory, preferring names in `prefer` (substrings)."""
    names = filing_files(cik, accession)
    xmls = [n for n in names if n.lower().endswith(".xml")]
    for needle in prefer:
        for n in xmls:
            if needle.lower() in n.lower():
                return n
    return xmls[0] if xmls else None
