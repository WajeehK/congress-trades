"""Institutional 13F holdings from official SEC EDGAR filings.

v1 roster is a short list of sovereign and well-known managers. Only 13F-HR / 13F-HR/A
information tables are used (13F-NT is a notice that someone else filed the holdings).
Holdings are a delayed, long-only snapshot of US Section 13(f) securities — not a trade blotter.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date, datetime

import sec_edgar

SOURCE = "sec_13f"
CHAMBER = "Institution"

# Display names are the public filer, never a chairperson's personal account.
FUNDS = {
    "0001767640": {
        "name": "Public Investment Fund (Saudi Arabia), chaired by MBS",
        "short": "PIF",
        "note": "Saudi Arabia's Public Investment Fund (PIF), chaired by Mohammed bin Salman. "
                "This is the fund's SEC 13F of US-listed long positions, not MBS's personal account, "
                "and not PIF's full portfolio (private, non-US and short positions are not reported).",
    },
    "0001374170": {
        "name": "Norges Bank",
        "short": "Norges Bank",
        "note": "Norges Bank Investment Management, manager of Norway's Government Pension Fund Global. "
                "13F covers US-listed long positions only, filed up to 45 days after quarter-end.",
    },
    "0001704268": {
        "name": "Mubadala Investment Company",
        "short": "Mubadala",
        "note": "Mubadala Investment Company (Abu Dhabi). US-listed long positions on its 13F only; "
                "filed up to 45 days after quarter-end.",
    },
    "0001021944": {
        "name": "Temasek Holdings",
        "short": "Temasek",
        "note": "Temasek Holdings (Singapore). US-listed long positions on its 13F only; "
                "filed up to 45 days after quarter-end.",
    },
    "0001067983": {
        "name": "Berkshire Hathaway",
        "short": "Berkshire Hathaway",
        "note": "Berkshire Hathaway Inc. US-listed long equity portfolio as reported on Form 13F, "
                "filed up to 45 days after quarter-end. Not a complete picture of Berkshire's assets.",
    },
    "0001336528": {
        "name": "Pershing Square",
        "short": "Pershing Square",
        "note": "Pershing Square Capital Management (Bill Ackman). Only 13F-HR holdings tables are used "
                "(13F-NT notices are skipped). US-listed longs, up to 45 days delayed.",
    },
}

HR_FORMS = {"13F-HR", "13F-HR/A"}
# Infer QoQ changes at or above this dollar move, except small books (PIF) where we show all.
QOQ_MIN = 10_000_000
QOQ_CAP = 40
SCHEMA = """
CREATE TABLE IF NOT EXISTS holdings_13f(
  cik TEXT NOT NULL,
  accession TEXT NOT NULL,
  row_no INTEGER NOT NULL,
  period_end TEXT,
  filed TEXT,
  name TEXT,
  issuer TEXT,
  title TEXT,
  cusip TEXT,
  ticker TEXT,
  shares REAL,
  value REAL,
  put_call TEXT NOT NULL DEFAULT '',
  ssh_type TEXT,
  PRIMARY KEY (cik, accession, row_no)
);
CREATE INDEX IF NOT EXISTS ix_13f_name ON holdings_13f(name, filed);
"""


def local(tag):
    return tag.split("}")[-1] if tag and "}" in tag else (tag or "")


def _text(el):
    return (el.text or "").strip() if el is not None else ""


def _num(s):
    if s is None or s == "":
        return None
    try:
        return float(str(s).replace(",", "").strip())
    except ValueError:
        return None


def ensure_schema(c):
    cols = {r[1] for r in c.execute("PRAGMA table_info(holdings_13f)")}
    if cols and "row_no" not in cols:
        c.execute("DROP TABLE holdings_13f")
    c.executescript(SCHEMA)


def _norm_name(s):
    s = uniclean(s)
    s = re.sub(r"[^A-Z0-9 ]+", " ", s.upper())
    for w in (" INCORPORATED", " CORPORATION", " COMPANY", " LIMITED", " LTD", " INC", " CORP",
              " PLC", " SA", " AG", " NV", " CO", " THE "):
        s = s.replace(w, " ")
    return re.sub(r"\s+", " ", s).strip()


def uniclean(s):
    return re.sub(r"\s+", " ", (s or "").strip())


def build_name_map(app):
    cache = app.DATA / "sec_company_tickers.json"
    by_ticker, _ = sec_edgar.ticker_index(cache)
    by_name = {}
    for rec in by_ticker.values():
        key = _norm_name(rec["title"])
        if key and key not in by_name:
            by_name[key] = rec["ticker"]
        # also index without trailing class words
    return by_ticker, by_name


# Hand map for issuers the name matcher can miss (verified against 13F issuer names).
ALIASES = {
    "UBER TECHNOLOGIES": "UBER",
    "ELECTRONIC ARTS": "EA",
    "LUCID GROUP": "LCID",
    "CLARITEV": "CTEV",
    "SPACE EXPLORATION TECHN": None,  # no public ticker
    "SPACE EXPLORATION TECHNOLOGIES": None,
    "APPLE": "AAPL",
    "MICROSOFT": "MSFT",
    "NVIDIA": "NVDA",
    "AMAZON COM": "AMZN",
    "AMAZON": "AMZN",
    "ALPHABET": "GOOGL",
    "META PLATFORMS": "META",
    "TESLA": "TSLA",
    "BERKSHIRE HATHAWAY": "BRK-B",
}


def map_ticker(issuer, title, by_name):
    if not issuer:
        return None
    key = _norm_name(issuer)
    if key in by_name:
        return by_name[key]
    for alias, tk in ALIASES.items():
        if key.startswith(alias) or alias in key:
            return tk  # may be None (= known unlisted)
    # try dropping CLASS / COM / NEW suffixes already stripped by _norm_name
    # prefix match: "LUCID GROUP" vs "LUCID GROUP INC"
    hits = [tk for n, tk in by_name.items() if n.startswith(key) or key.startswith(n)]
    if len(set(hits)) == 1:
        return hits[0]
    return None


def parse_info_table(xml_bytes):
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []
    rows = []
    for it in root.iter():
        if local(it.tag) != "infoTable":
            continue
        rec = {}
        for c in it.iter():
            rec[local(c.tag)] = (c.text or "").strip()
        rows.append({
            "issuer": rec.get("nameOfIssuer") or "",
            "title": rec.get("titleOfClass") or "",
            "cusip": rec.get("cusip") or "",
            "figi": rec.get("figi") or "",
            "value": _num(rec.get("value")) or 0.0,  # dollars (post-2023 schema)
            "shares": _num(rec.get("sshPrnamt")) or 0.0,
            "ssh_type": rec.get("sshPrnamtType") or "SH",
            "put_call": (rec.get("putCall") or "").upper(),
        })
    return rows


def _latest_hr_by_period(filings):
    """For each report period, the latest 13F-HR or 13F-HR/A (skip 13F-NT)."""
    by = {}
    for f in filings:
        if f["form"] not in HR_FORMS:
            continue
        period = f.get("report_date") or ""
        key = period or f["accession"]
        prev = by.get(key)
        if not prev or (f["filing_date"], f["accession"]) > (prev["filing_date"], prev["accession"]):
            by[key] = f
    periods = sorted(by.keys(), reverse=True)
    return [by[p] for p in periods]


def _info_xml(cik, accession, primary):
    """Pick the XML that actually contains the holdings table, not the 13F cover page."""
    candidates = []
    names = sec_edgar.filing_files(cik, accession)
    xmls = [n for n in names if n.lower().endswith(".xml") and "xsl" not in n.lower()]
    # try the obvious names first, then every non-cover xml, largest first
    prefer = ["informationtable.xml", "infotable.xml", "form13fInfoTable.xml", "13fInfoTable.xml"]
    ordered = []
    for p in prefer:
        if p in xmls and p not in ordered:
            ordered.append(p)
    for n in xmls:
        if n not in ordered:
            ordered.append(n)
    best, best_n = None, -1
    for n in ordered:
        try:
            blob = sec_edgar.get_bytes(sec_edgar.archives_url(cik, accession, n))
        except Exception:
            continue
        n_rows = blob.count(b"nameOfIssuer")
        if n_rows > best_n:
            best, best_n = blob, n_rows
        if n_rows > 3 and "primary_doc" not in n.lower():
            return blob
    return best if best_n > 0 else None


def is_thin(rows):
    """A placeholder or empty 13F (e.g. Norges Q1 2026 filed a 1-row $0 table)."""
    v = sum((r.get("value") or 0) for r in rows)
    return v < 1_000_000 or (len(rows) <= 2 and v < 10_000_000)


def aggregate(rows):
    """Merge split-discretion lines that share a CUSIP / put-call (Berkshire files many of these)."""
    by = {}
    for r in rows:
        k = (r.get("cusip") or "", r.get("put_call") or "", (r.get("ticker") or ""), (r.get("issuer") or "").upper())
        cur = by.get(k)
        if not cur:
            by[k] = dict(r)
        else:
            cur["shares"] = (cur.get("shares") or 0) + (r.get("shares") or 0)
            cur["value"] = (cur.get("value") or 0) + (r.get("value") or 0)
    return list(by.values())


def _amount_str(dollars):
    if dollars is None:
        return None
    sign = "-" if dollars < 0 else ""
    d = abs(dollars)
    if d >= 1_000_000_000:
        return f"{sign}${d / 1_000_000_000:.2f}B"
    if d >= 1_000_000:
        return f"{sign}${d / 1_000_000:.2f}M"
    return f"{sign}${d:,.0f}"


def _key(row):
    # Same security can appear under slightly different issuer names (e.g. BANK OF AMER CORP vs BANK AMERICA CORP).
    if row.get("cusip"):
        return ("cusip", row["cusip"], row.get("put_call") or "")
    return ("name", (row.get("issuer") or "").upper(), row.get("put_call") or "")


def ingest_filing(app, c, fund, f, by_name, prev_rows):
    """Store holdings for one 13F-HR and optionally emit inferred QoQ change rows. Returns new trade rows."""
    cik, name, note = fund["cik"], fund["name"], fund["note"]
    existing = _holdings_for(c, cik, f["accession"])
    if existing and not is_thin(existing):
        return _qqq_trades(app, c, fund, f, sec_edgar.filing_url(cik, f["accession"]),
                           f"{SOURCE}:{f['accession']}", existing, prev_rows, note)
    blob = _info_xml(cik, f["accession"], f.get("primary") or "")
    if not blob:
        app.note(f"13F {fund['short']}: no information table in {f['accession']}")
        return []
    parsed = parse_info_table(blob)
    url = sec_edgar.filing_url(cik, f["accession"])
    fid = f"{SOURCE}:{f['accession']}"
    period, filed = f.get("report_date") or "", f.get("filing_date") or ""
    # replace this accession's holdings
    c.execute("DELETE FROM holdings_13f WHERE cik=? AND accession=?", (cik, f["accession"]))
    rows = []
    for i, p in enumerate(parsed, start=1):
        ticker = map_ticker(p["issuer"], p["title"], by_name)
        title = p["title"]
        if p["put_call"]:
            title = f"{title} {p['put_call']}".strip()
        rec = {
            "cik": cik, "accession": f["accession"], "period_end": period, "filed": filed,
            "name": name, "issuer": p["issuer"], "title": title, "cusip": p["cusip"] or "",
            "ticker": ticker, "shares": p["shares"], "value": p["value"],
            "put_call": p["put_call"] or "", "ssh_type": p["ssh_type"],
        }
        c.execute("""INSERT OR REPLACE INTO holdings_13f
            (cik, accession, row_no, period_end, filed, name, issuer, title, cusip, ticker, shares, value, put_call, ssh_type)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (rec["cik"], rec["accession"], i, rec["period_end"], rec["filed"], rec["name"], rec["issuer"],
                   rec["title"], rec["cusip"], rec["ticker"], rec["shares"], rec["value"], rec["put_call"], rec["ssh_type"]))
        rows.append(rec)
    c.execute("INSERT OR REPLACE INTO filings VALUES(?,?,?,?,?,?,?,?,?,?)",
              (fid, SOURCE, CHAMBER, name, fund["short"], filed, url, "parsed", len(rows), app.now()))
    app.note(f"13F {fund['short']}: {filed} period {period or '?'} — {len(rows)} holdings, {_amount_str(sum(r['value'] or 0 for r in rows))}")
    return _qqq_trades(app, c, fund, f, url, fid, rows, prev_rows, note)


def _qqq_trades(app, c, fund, f, url, fid, rows, prev_rows, note):
    if not prev_rows:
        return []
    if is_thin(prev_rows):
        return []
    cur = {_key(r): r for r in aggregate(rows)}
    prev = {_key(r): r for r in aggregate(prev_rows)}
    changes = []
    keys = set(cur) | set(prev)
    for k in keys:
        a, b = cur.get(k), prev.get(k)
        if a and not b:
            kind, side, delta = "13F new", "buy", a["value"] or 0
        elif b and not a:
            kind, side, delta = "13F exited", "sell", b["value"] or 0
        elif a and b:
            dv = (a["value"] or 0) - (b["value"] or 0)
            if abs(dv) < 1:
                continue
            kind, side, delta = ("13F increase" if dv > 0 else "13F decrease"), ("buy" if dv > 0 else "sell"), abs(dv)
        else:
            continue
        issuer = (a or b)["issuer"]
        changes.append((delta, kind, side, a, b, issuer))
    # PIF (tiny book): keep all; others: material + cap
    small = len(rows) <= 15 and len(prev_rows) <= 15
    if not small:
        changes = [x for x in changes if x[0] >= QOQ_MIN]
        changes.sort(key=lambda x: -x[0])
        changes = changes[:QOQ_CAP]
    else:
        changes.sort(key=lambda x: -x[0])
    seeded = app.meta_get("sec13f_seeded")
    filed, period = f.get("filing_date") or "", f.get("report_date") or ""
    backfill = not seeded
    first_seen = (filed + "T12:00:00+00:00") if filed else app.now()
    desc = ("Inferred from 13F quarter-over-quarter change. Form 13F is a delayed snapshot of "
            "US-listed long positions only (no shorts, most bonds, cash, private or non-US assets), "
            "filed up to 45 days after quarter-end. This is not a disclosed trade ticket. " + note)
    new_rows = []
    # replace previously inferred rows for this accession
    c.execute("DELETE FROM trades WHERE filing_id=? AND source=?", (fid, SOURCE))
    for delta, kind, side, a, b, issuer in changes:
        rec = a or b
        ticker = rec.get("ticker")
        asset = rec.get("issuer") or ""
        if rec.get("put_call"):
            asset = f"{asset} {rec['put_call']}"
        dollars = delta
        uid = f"13f:{fund['cik']}:{f['accession']}:{rec.get('cusip') or 'x'}:{rec.get('put_call') or ''}:{kind}"
        uid = uid[:120]
        row = {
            "uid": uid, "source": SOURCE, "filing_id": fid, "chamber": CHAMBER,
            "politician": fund["name"], "last_name": fund["short"], "party": None,
            "state": None, "district": fund["short"],
            "owner": None, "ticker": ticker, "asset": asset,
            "asset_type": "ST" if ticker and not rec.get("put_call") else (None if not ticker else "ST"),
            "tx_type": kind, "side": side, "tx_date": period or filed,
            "disclosure_date": filed, "amount": _amount_str(dollars),
            "amount_low": int(round(dollars)), "amount_high": int(round(dollars)),
            "description": desc, "url": url, "fetched_at": app.now(),
            "bioguide": None, "first_seen": first_seen,
        }
        app.insert_trade(c, row, ignore=False)
        if ticker:
            c.execute(app.EST_SQL, (ticker,))
        if not backfill:
            new_rows.append(row)
    return new_rows


def _holdings_for(c, cik, accession):
    rows = c.execute("SELECT * FROM holdings_13f WHERE cik=? AND accession=?", (cik, accession)).fetchall()
    return [dict(r) for r in rows]


def _latest_stored(c, cik):
    r = c.execute("""SELECT accession, period_end, filed FROM holdings_13f WHERE cik=?
                     ORDER BY filed DESC, period_end DESC, accession DESC LIMIT 1""", (cik,)).fetchone()
    return dict(r) if r else None


def fetch(app):
    with app.db() as c:
        ensure_schema(c)
    by_ticker, by_name = build_name_map(app)
    # merge aliases so map_ticker can hit them via startswith on normalized names — handled in ALIASES
    new_rows = []
    for cik, meta in FUNDS.items():
        fund = {**meta, "cik": cik}
        try:
            sub = sec_edgar.submissions(cik)
        except Exception as e:
            app.note(f"13F {meta['short']}: submissions failed: {e}")
            continue
        periods = _latest_hr_by_period(sec_edgar.recent_filings(sub, HR_FORMS))
        if not periods:
            app.note(f"13F {meta['short']}: no 13F-HR in recent filings (may be 13F-NT only this quarter)")
            continue
        with app.db() as c:
            substantial = []
            for f in periods:
                if len(substantial) >= 2:
                    break
                try:
                    ingest_filing(app, c, fund, f, by_name, prev_rows=[])
                except Exception as e:
                    app.note(f"13F {meta['short']} {f.get('report_date')}: ingest failed: {e}")
                    continue
                got = _holdings_for(c, cik, f["accession"])
                if is_thin(got):
                    app.note(f"13F {meta['short']}: skipping thin {f['filing_date']} period {f.get('report_date') or '?'} ({len(got)} rows)")
                    continue
                substantial.append((f, got))
            if not substantial:
                app.note(f"13F {meta['short']}: no substantial 13F-HR table found")
                continue
            latest, latest_rows = substantial[0]
            prev_rows = substantial[1][1] if len(substantial) > 1 else []
            # Re-run QoQ now that we have a real previous book (first ingest passed prev_rows=[])
            try:
                new_rows += ingest_filing(app, c, fund, latest, by_name, prev_rows)
            except Exception as e:
                app.note(f"13F {meta['short']}: QoQ ingest failed: {e}")
    if not app.meta_get("sec13f_seeded"):
        app.meta_set("sec13f_seeded", "1")
    app.note(f"13F: done, {len(new_rows)} inferred QoQ rows this run")
    return new_rows


def list_names(c):
    rows = c.execute("SELECT DISTINCT name, cik FROM holdings_13f").fetchall()
    return [dict(r) for r in rows]


def latest_for_name(c, name):
    """Newest *substantial* 13F-HR for this institution (skip empty/placeholder tables)."""
    accs = c.execute("""SELECT cik, accession, period_end, filed, name
                        FROM holdings_13f WHERE name=?
                        GROUP BY cik, accession, period_end, filed, name
                        ORDER BY filed DESC, period_end DESC, accession DESC""", (name,)).fetchall()
    first = None
    for r in accs:
        d = dict(r)
        if first is None:
            first = d
        if not is_thin(_holdings_for(c, d["cik"], d["accession"])):
            return d
    return first


def portfolio(c, name):
    """Holdings snapshot for an institution, shaped like portfolio.compute() but with no fake performance series."""
    meta = latest_for_name(c, name)
    empty = {"name": name, "avg_delay": None, "n_priced": 0, "value": 0.0, "pnl": None, "invested": None,
             "holdings": [], "series": {"d": [], "v": [], "p": [], "i": []}, "win_rate": None, "win_n": 0,
             "edge": None, "source": SOURCE, "period_end": None, "filed": None, "note": None, "first": None}
    if not meta:
        return empty
    fund = FUNDS.get(meta["cik"], {})
    rows = aggregate(_holdings_for(c, meta["cik"], meta["accession"]))
    # live prices where we have a ticker
    tickers = sorted({r["ticker"] for r in rows if r.get("ticker")})
    last, asof = {}, {}
    if tickers:
        q = ",".join("?" * len(tickers))
        for r in c.execute(f"""SELECT ticker, adjclose, d FROM prices p
                               WHERE ticker IN ({q}) AND adjclose > 0
                               AND d = (SELECT MAX(d) FROM prices p2 WHERE p2.ticker=p.ticker AND adjclose > 0)""",
                           tickers):
            last[r["ticker"]] = r["adjclose"]
            asof[r["ticker"]] = r["d"]
        # fallback if the MAX subquery is picky
        if not last:
            for r in c.execute(f"SELECT ticker, adjclose, d FROM prices WHERE ticker IN ({q}) AND adjclose > 0 ORDER BY d",
                               tickers):
                last[r["ticker"]] = r["adjclose"]
                asof[r["ticker"]] = r["d"]
    hold = []
    reported_total = 0.0
    current_total = 0.0
    priced = 0
    for r in rows:
        reported = r["value"] or 0
        reported_total += reported
        tk = r.get("ticker")
        unlisted = not tk
        price = last.get(tk) if tk else None
        shares = r["shares"] or 0
        if tk and price and shares and not r.get("put_call"):
            value = shares * price
            priced += 1
        else:
            value = reported
        if tk and price:
            current_total += value
        else:
            current_total += reported
        hold.append({
            "ticker": tk or "",
            "name": r["issuer"],
            "title": r.get("title") or "",
            "shares": round(shares, 4) if shares else 0,
            "value": round(value, 2),
            "reported_value": round(reported, 2),
            "cost": round(reported, 2),
            "price": price,
            "gain_pct": round(100 * (value / reported - 1), 2) if reported and tk and price and not r.get("put_call") else None,
            "unlisted": unlisted,
            "put_call": r.get("put_call") or "",
            "as_of": r.get("period_end"),
        })
    hold.sort(key=lambda h: -h["value"])
    total = current_total or reported_total
    for h in hold:
        h["weight"] = round(100 * h["value"] / total, 2) if total else 0
    lag = None
    if meta.get("filed") and meta.get("period_end"):
        try:
            lag = (date.fromisoformat(meta["filed"]) - date.fromisoformat(meta["period_end"])).days
        except ValueError:
            lag = None
    note = fund.get("note")
    if is_thin(rows) or total < 1:
        note = (note + " " if note else "") + (
            "No substantial 13F-HR table in the latest filings — a recent file was empty or a placeholder, not a $0 portfolio."
        )
    empty.update(
        avg_delay=lag, n_priced=priced, value=round(total, 2), pnl=None, invested=round(reported_total, 2),
        holdings=hold, source=SOURCE, period_end=meta.get("period_end"), filed=meta.get("filed"),
        note=note, first=meta.get("period_end"), reported_value=round(reported_total, 2),
        thin=bool(is_thin(rows) or total < 1),
        thin_note="No substantial 13F-HR table in the latest filings — a recent file was empty or a placeholder, not a $0 portfolio." if (is_thin(rows) or total < 1) else None,
    )
    return empty
