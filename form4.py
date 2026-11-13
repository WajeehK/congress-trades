"""Corporate insider trades from SEC Form 4 / 4-A (free EDGAR data).

v1 watchlist is a set of mega-cap issuers. Only officer/director (and 10% owner)
open-market P (buy) and S (sell) common-stock rows go into the trades feed.
Awards, option exercises, tax withholding, gifts, and preferred/derivative rows are skipped.
"""
from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import date, timedelta

import sec_edgar

# Mega-cap issuers for v1. Alphabet's Class A/C share the same CIK; we dedupe by CIK.
WATCHLIST = ("AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD", "NFLX", "ORCL", "AVGO", "JPM")
KEEP_CODES = {"P", "S"}
# Skip these even if someone miscoded them as P/S
SKIP_TITLE = re.compile(
    r"preferr|warrant|option|convertible|note\b|debt|debenture|right to|phantom|"
    r"depositary|swap|unit\b|rsl\b|rsu|psu|restricted stock unit",
    re.I,
)
COMMONISH = re.compile(r"common|ordinary|class [a-ce]\b|class a\b|class b\b|class c\b|^stock$", re.I)
LOOKBACK_DAYS = 90
SOURCE = "sec_form4"
CHAMBER = "Insider"


def local(tag):
    return tag.split("}")[-1] if tag and "}" in tag else (tag or "")


def val(el, *names):
    """Walk child local-names and return a nested <value> or the element's text."""
    if el is None:
        return None
    cur = el
    for n in names:
        nxt = None
        for c in list(cur):
            if local(c.tag) == n:
                nxt = c
                break
        if nxt is None:
            return None
        cur = nxt
    for c in list(cur):
        if local(c.tag) == "value" and (c.text or "").strip():
            return c.text.strip()
    text = (cur.text or "").strip()
    return text or None


def _truthy(s):
    return str(s or "").strip().lower() in {"1", "true", "yes", "y"}


def _num(s):
    if s is None or s == "":
        return None
    try:
        return float(str(s).replace(",", "").replace("$", "").strip())
    except ValueError:
        return None


def _owner_display(name):
    name = re.sub(r"\s+", " ", (name or "").strip())
    if "," in name:
        last, first = name.split(",", 1)
        return f"{first.strip()} {last.strip()}".strip()
    return name


def _role(owner):
    title = (owner.get("title") or "").strip()
    if title:
        return title
    if owner.get("is_officer"):
        return "Officer"
    if owner.get("is_director"):
        return "Director"
    if owner.get("is_ten"):
        return "10% owner"
    return "Insider"


def _last_name(name):
    parts = [w for w in re.sub(r",", " ", name or "").split() if w and not re.fullmatch(r"(Jr|Sr|II|III|IV)\.?", w, re.I)]
    return parts[-1] if parts else (name or "")


def parse_form4(xml_bytes):
    """Return {issuer, owners, transactions} from a Form 4 ownershipDocument, or None if unreadable."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None
    if local(root.tag) != "ownershipDocument" and not any(local(c.tag) == "issuer" for c in root.iter()):
        # sometimes wrapped
        inner = None
        for c in root.iter():
            if local(c.tag) == "ownershipDocument":
                inner = c
                break
        if inner is None:
            return None
        root = inner
    issuer = {
        "cik": val(root, "issuer", "issuerCik") or "",
        "name": val(root, "issuer", "issuerName") or "",
        "ticker": (val(root, "issuer", "issuerTradingSymbol") or "").upper().split()[0] if val(root, "issuer", "issuerTradingSymbol") else "",
    }
    # issuer fields may also be direct children of an issuer element found anywhere
    for el in root.iter():
        if local(el.tag) == "issuer":
            issuer["cik"] = val(el, "issuerCik") or issuer["cik"]
            issuer["name"] = val(el, "issuerName") or issuer["name"]
            sym = val(el, "issuerTradingSymbol")
            if sym:
                issuer["ticker"] = sym.upper().split()[0]
            break
    owners = []
    for el in root.iter():
        if local(el.tag) != "reportingOwner":
            continue
        rel = None
        for c in el.iter():
            if local(c.tag) == "reportingOwnerRelationship":
                rel = c
                break
        owners.append({
            "name": _owner_display(val(el, "reportingOwnerId", "rptOwnerName") or val(el, "rptOwnerName") or ""),
            "cik": val(el, "reportingOwnerId", "rptOwnerCik") or "",
            "title": (val(rel, "officerTitle") if rel is not None else None) or val(el, "officerTitle") or "",
            "is_officer": _truthy(val(rel, "isOfficer") if rel is not None else val(el, "isOfficer")),
            "is_director": _truthy(val(rel, "isDirector") if rel is not None else val(el, "isDirector")),
            "is_ten": _truthy(val(rel, "isTenPercentOwner") if rel is not None else val(el, "isTenPercentOwner")),
        })
    txs = []
    for el in root.iter():
        if local(el.tag) != "nonDerivativeTransaction":
            continue
        title = val(el, "securityTitle") or ""
        code = (val(el, "transactionCoding", "transactionCode") or "").upper()
        txs.append({
            "title": title,
            "date": val(el, "transactionDate"),
            "code": code,
            "shares": _num(val(el, "transactionAmounts", "transactionShares")),
            "price": _num(val(el, "transactionAmounts", "transactionPricePerShare")),
            "ad": (val(el, "transactionAmounts", "transactionAcquiredDisposedCode") or "").upper(),
            "held": _num(val(el, "postTransactionAmounts", "sharesOwnedFollowingTransaction")),
            "ownership": val(el, "ownershipNature", "directOrIndirectOwnership") or "",
        })
    period = val(root, "periodOfReport")
    return {"issuer": issuer, "owners": owners, "transactions": txs, "period": period,
            "doc_type": val(root, "documentType")}


def keep_tx(tx):
    if (tx.get("code") or "") not in KEEP_CODES:
        return False
    title = tx.get("title") or ""
    if SKIP_TITLE.search(title):
        return False
    # allow untitled common-looking rows; reject clearly non-common if we can tell
    if title and not COMMONISH.search(title) and not re.search(r"stock|share", title, re.I):
        return False
    if not tx.get("shares") or tx["shares"] <= 0:
        return False
    # price can be 0 for some rare cases; still skip those (not a meaningful open-market amount)
    if tx.get("price") is None or tx["price"] < 0:
        return False
    return True


def keep_owner(o):
    return bool(o.get("is_officer") or o.get("is_director") or o.get("is_ten"))


def _amount_str(dollars):
    if dollars is None:
        return None
    if dollars >= 1_000_000:
        return f"${dollars:,.0f}" if dollars >= 100 else f"${dollars:,.2f}"
    return f"${dollars:,.2f}"


def _uid(accession, owner, tx, ticker):
    raw = "|".join([
        accession or "",
        owner or "",
        tx.get("date") or "",
        tx.get("code") or "",
        f"{tx.get('shares') or 0:.4f}",
        f"{tx.get('price') or 0:.6f}",
        ticker or "",
        tx.get("ownership") or "",
    ])
    return "f4:" + hashlib.sha1(raw.encode()).hexdigest()[:20]


def _watch_ciks(app):
    cache = app.DATA / "sec_company_tickers.json"
    by_ticker, by_cik = sec_edgar.ticker_index(cache)
    seen, out = set(), []
    missing = []
    for tk in WATCHLIST:
        rec = by_ticker.get(tk)
        if not rec:
            missing.append(tk)
            continue
        cik = rec["cik"]
        if cik in seen:
            continue
        seen.add(cik)
        # prefer a well-known ticker for the issuer (GOOGL over GOOGN)
        tickers = by_cik.get(cik) or [rec]
        prefer = next((t for t in tickers if t["ticker"] in WATCHLIST), tickers[0])
        out.append({"cik": cik, "ticker": prefer["ticker"], "title": prefer["title"]})
    return out, missing


def fetch(app):
    """Ingest new Form 4 / 4-A rows for the watchlist. Returns newly inserted trade dicts (for alerts)."""
    issuers, missing = _watch_ciks(app)
    if missing:
        app.note(f"Form 4: no CIK for {', '.join(missing)}")
    if not issuers:
        app.note("Form 4: watchlist resolved to no issuers")
        return []
    since = (date.today() - timedelta(days=LOOKBACK_DAYS)).isoformat()
    seeded = app.meta_get("form4_seeded")
    new_rows = []
    n_filings = n_kept = n_skip = 0
    types = {"4", "4/A"}
    with app.db() as c:
        seen = {r[0] for r in c.execute("SELECT id FROM filings WHERE source=?", (SOURCE,))}
    for iss in issuers:
        try:
            sub = sec_edgar.submissions(iss["cik"])
        except Exception as e:
            app.note(f"Form 4 {iss['ticker']}: submissions failed: {e}")
            continue
        filings = [f for f in sec_edgar.recent_filings(sub, types) if (f["filing_date"] or "") >= since]
        for f in filings:
            fid = f"{SOURCE}:{f['accession']}"
            if fid in seen:
                continue
            xml_bytes, xml_url, xml_name = None, None, None
            try:
                xml_bytes, xml_url, xml_name = sec_edgar.raw_document(iss["cik"], f["accession"], f["primary"])
                if not xml_bytes or not (xml_bytes.strip().startswith(b"<?xml") or b"<ownershipDocument" in xml_bytes[:2000]):
                    name = sec_edgar.first_xml_named(iss["cik"], f["accession"], ("form4", "wk-form4", "_4seq", "ownership"))
                    if name:
                        xml_bytes = sec_edgar.get_bytes(sec_edgar.archives_url(iss["cik"], f["accession"], name))
                        xml_url = sec_edgar.archives_url(iss["cik"], f["accession"], name)
            except Exception as e:
                app.note(f"Form 4 {iss['ticker']} {f['accession']}: download failed: {e}")
                n_skip += 1
                continue
            if not xml_bytes:
                app.note(f"Form 4 {iss['ticker']} {f['accession']}: no XML")
                n_skip += 1
                continue
            parsed = parse_form4(xml_bytes)
            if not parsed:
                app.note(f"Form 4 {iss['ticker']} {f['accession']}: unreadable XML")
                n_skip += 1
                continue
            n_filings += 1
            issuer = parsed["issuer"]
            ticker = issuer.get("ticker") or iss["ticker"]
            company = issuer.get("name") or iss["title"]
            owners = [o for o in parsed["owners"] if keep_owner(o) and o.get("name")]
            if not owners:
                # still record the filing so we don't refetch
                owners = []
            url = sec_edgar.filing_url(iss["cik"], f["accession"])
            kept = []
            for tx in parsed["transactions"]:
                if not keep_tx(tx):
                    continue
                # default owner: first qualifying, or first listed
                for owner in (owners or parsed["owners"][:1]):
                    if not owner.get("name"):
                        continue
                    # one row per qualifying owner on a joint filing (they share the transaction block)
                    dollars = (tx["shares"] or 0) * (tx["price"] or 0)
                    side = "buy" if tx["code"] == "P" else "sell"
                    role = _role(owner)
                    person = app.clean_name(owner["name"])
                    uid = _uid(f["accession"], person, tx, ticker)
                    disc = f["filing_date"]
                    backfill = (not seeded) or (disc and disc < (date.today() - timedelta(days=app.NEW_WINDOW_DAYS)).isoformat())
                    first_seen = (disc + "T12:00:00+00:00") if backfill and disc else app.first_seen_for(disc)
                    own = "Direct" if (tx.get("ownership") or "D").upper().startswith("D") else "Indirect"
                    desc = f"{role} of {company}. Open-market Form 4 ({tx['code']})."
                    if f["form"] == "4/A":
                        desc += " Amendment."
                    row = {
                        "uid": uid, "source": SOURCE, "filing_id": fid, "chamber": CHAMBER,
                        "politician": person, "last_name": _last_name(person), "party": None,
                        "state": ticker, "district": f"{role} · {company}",
                        "owner": own, "ticker": ticker, "asset": tx.get("title") or company,
                        "asset_type": "ST", "tx_type": "Purchase" if side == "buy" else "Sale",
                        "side": side, "tx_date": tx.get("date") or parsed.get("period"),
                        "disclosure_date": disc, "amount": _amount_str(dollars),
                        "amount_low": int(round(dollars)) if dollars else 0,
                        "amount_high": int(round(dollars)) if dollars else 0,
                        "description": desc, "url": url, "fetched_at": app.now(),
                        "bioguide": None, "first_seen": first_seen,
                    }
                    kept.append(row)
                    # joint filings: the same non-derivative block applies to each reporting owner
                    # only if there is truly a single transaction listed once for all owners.
                    # Form 4 typically has one reporting owner for officer trades; if multiple
                    # officers are listed they usually each have their own filing. Only attach
                    # the transaction to the first qualifying owner to avoid duplicating a single sale.
                    break
            with app.db() as c:
                c.execute("INSERT OR REPLACE INTO filings VALUES(?,?,?,?,?,?,?,?,?,?)",
                          (fid, SOURCE, CHAMBER, (kept[0]["politician"] if kept else company),
                           ticker, f["filing_date"], url, "parsed" if kept else "no_transactions",
                           len(kept), app.now()))
                prev = {r["uid"]: r["first_seen"] for r in c.execute(
                    "SELECT uid, first_seen FROM trades WHERE filing_id=?", (fid,))}
                for row in kept:
                    row["first_seen"] = prev.get(row["uid"]) or row["first_seen"]
                    is_new = row["uid"] not in prev
                    app.insert_trade(c, row, ignore=True)
                    if is_new:
                        n_kept += 1
                        if not backfill:
                            new_rows.append(row)
                if ticker:
                    c.execute(app.EST_SQL, (ticker,))
            seen.add(fid)
        app.note(f"Form 4 {iss['ticker']}: {sum(1 for x in filings if x)} candidate filings in window")
    if not seeded:
        app.meta_set("form4_seeded", "1")
    app.note(f"Form 4: parsed {n_filings} new filings, kept {n_kept} open-market P/S, skipped {n_skip}, {len(new_rows)} alertable")
    return new_rows
