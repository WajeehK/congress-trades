"""Senate Periodic Transaction Reports straight from the Senate's own eFD site (efdsearch.senate.gov).

Flow (the site is a Django app behind a usage agreement): GET /search/home/ -> POST the agreement with its CSRF token
-> POST /search/report/data/ (the JSON behind the search page) for report type 11 (PTR) -> fetch each report page.
E-filed PTRs are HTML tables; paper PTRs are scanned page images (recorded as 'paper', not parsed here).

Politeness: one session, sequential requests, EFD_DELAY seconds between requests (default 1.5), at most EFD_MAX_REPORTS
report pages per run (the 2-year backfill is spread over several runs), and a report is fetched once: its filing row
in the DB (status parsed / no_transactions / paper) means it's never requested again.

The site refuses this project's box (Akamai HTTP 403) but answers GitHub's runners, so this runs in Actions; the box
server mirrors these rows from the published site instead (see app.ingest_efd_from_site).
"""
import html as htmllib
import json
import os
import re
import time
import unicodedata
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser

import requests

BASE = "https://efdsearch.senate.gov"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36 "
                    "(politician-trades-tracker; personal research)",
      "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.9"}
DELAY = float(os.environ.get("EFD_DELAY", "1.5"))
MAX_REPORTS = int(os.environ.get("EFD_MAX_REPORTS", "250"))
BACKFILL_DAYS = int(os.environ.get("EFD_BACKFILL_DAYS", "730"))
RESCAN_DAYS = 45   # after the backfill, each run re-lists the last 45 days (late-indexed and amended reports)

ASSET_TYPES = {"stock": "ST", "stock option": "OP", "corporate bond": "BOND", "municipal security": "BOND",
               "government security": "BOND", "mutual fund": "MF", "cryptocurrency": "CRYPTO", "non-public stock": "NP",
               "other securities": "OT", "commodities/futures contract": "OT", "pdf disclosed filing": "OT"}


class Blocked(Exception):
    pass


class _Table(HTMLParser):
    """Collect <table> rows as lists of (cell text, first link href)."""
    def __init__(self):
        super().__init__()
        self.tables, self._row, self._cell, self._href, self._depth = [], None, None, None, 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.tables.append([])
        elif tag == "tr" and self.tables:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell, self._href = [], None
        elif tag == "a" and self._cell is not None and self._href is None:
            self._href = dict(attrs).get("href")
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")
        elif tag == "div" and self._cell is not None:
            self._cell.append(" | ")   # sub-lines (e.g. "Rate/Coupon", option details) inside the asset cell

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append((re.sub(r"\s+", " ", "".join(self._cell)).strip(), self._href))
            self._cell = None
        elif tag == "tr" and self._row is not None and self.tables:
            if self._row:
                self.tables[-1].append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


class Client:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update(UA)
        self.n = 0
        self._last = 0.0
        self.ok = False

    def _wait(self):
        dt = time.time() - self._last
        if dt < DELAY:
            time.sleep(DELAY - dt)
        self._last = time.time()
        self.n += 1

    def _req(self, method, path, **kw):
        for attempt in range(3):
            self._wait()
            try:
                r = self.s.request(method, BASE + path, timeout=60, **kw)
            except requests.RequestException:
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code == 403 and "Access Denied" in r.text[:500]:
                raise Blocked("HTTP 403 (Akamai access denied)")
            if r.status_code in (429, 502, 503, 504):
                time.sleep(10 * (attempt + 1))
                continue
            # the session expired: the site bounces back to the agreement page
            if "/search/home/" in r.url and path != "/search/home/" and method == "GET":
                self.agree()
                continue
            return r
        r.raise_for_status()
        return r

    def agree(self):
        r = self._req("GET", "/search/home/")
        m = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', r.text)
        if not m:
            raise RuntimeError(f"eFD agreement form not found (HTTP {r.status_code})")
        r = self._req("POST", "/search/home/", data={"prohibition_agreement": "1", "csrfmiddlewaretoken": m.group(1)},
                      headers={"Referer": BASE + "/search/home/"})
        self.ok = r.status_code == 200
        return self.ok

    def search_ptrs(self, start_date, end_date=None):
        """All PTRs submitted from start_date: [{first, last, office, report_id, kind, title, submitted}]"""
        if not self.ok:
            self.agree()
        out, start, length = [], 0, 100
        while True:
            tok = self.s.cookies.get("csrftoken")
            r = self._req("POST", "/search/report/data/", data={
                "start": str(start), "length": str(length), "report_types": "[11]", "filer_types": "[]",
                "submitted_start_date": start_date.strftime("%m/%d/%Y 00:00:00"),
                "submitted_end_date": end_date.strftime("%m/%d/%Y 23:59:59") if end_date else "",
                "candidate_state": "", "senator_state": "", "office_id": "", "first_name": "", "last_name": "",
                "csrfmiddlewaretoken": tok}, headers={"Referer": BASE + "/search/", "X-CSRFToken": tok,
                                                      "X-Requested-With": "XMLHttpRequest"})
            if r.status_code != 200 or not r.text.lstrip().startswith("{"):
                if start == 0 and not out:
                    self.agree()   # stale session once: retry from scratch
                    tok = None
                    r = self._req("POST", "/search/report/data/", data={
                        "start": "0", "length": str(length), "report_types": "[11]", "filer_types": "[]",
                        "submitted_start_date": start_date.strftime("%m/%d/%Y 00:00:00"), "submitted_end_date": "",
                        "candidate_state": "", "senator_state": "", "office_id": "", "first_name": "", "last_name": "",
                        "csrfmiddlewaretoken": self.s.cookies.get("csrftoken")},
                        headers={"Referer": BASE + "/search/", "X-CSRFToken": self.s.cookies.get("csrftoken"),
                                 "X-Requested-With": "XMLHttpRequest"})
                if r.status_code != 200 or not r.text.lstrip().startswith("{"):
                    raise RuntimeError(f"eFD search failed: HTTP {r.status_code}")
            d = r.json()
            for row in d.get("data", []):
                first, last, office, link, submitted = (row + [""] * 5)[:5]
                m = re.search(r'href="(/search/view/(ptr|paper)/([0-9a-fA-F-]+)/?)"', link)
                if not m:
                    continue
                title = htmllib.unescape(re.sub(r"<[^>]+>", "", link)).strip()
                out.append({"first": htmllib.unescape(first).strip(), "last": htmllib.unescape(last).strip(),
                            "office": htmllib.unescape(office).strip(), "path": m.group(1), "kind": m.group(2),
                            "report_id": m.group(3).lower(), "title": title, "submitted": _iso(submitted)})
            start += length
            if start >= int(d.get("recordsFiltered") or 0) or not d.get("data"):
                break
        return out

    def report(self, path):
        r = self._req("GET", path)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}")
        return r.text


def _iso(s):
    try:
        return datetime.strptime((s or "").strip()[:10], "%m/%d/%Y").date().isoformat()
    except ValueError:
        return None


def parse_amount(s):
    s = re.sub(r"\s+", " ", s or "").strip()
    nums = [int(n.replace(",", "")) for n in re.findall(r"\$([\d,]+)", s)]
    if re.search(r"over", s, re.I):
        return s, (nums[0] + 1 if nums else None), None
    if len(nums) >= 2:
        return f"${nums[0]:,} - ${nums[1]:,}", nums[0], nums[1]
    return s, (nums[0] if nums else None), None


def parse_ptr_html(text):
    """E-filed PTR page -> list of transactions. Columns are matched by header name."""
    p = _Table()
    p.feed(text)
    rows = []
    for tbl in p.tables:
        if not tbl:
            continue
        head = [c[0].lower() for c in tbl[0]]
        if not any("transaction date" in h for h in head) or not any("amount" in h for h in head):
            continue
        col = lambda name: next((i for i, h in enumerate(head) if name in h), None)
        ci = {k: col(k) for k in ("transaction date", "owner", "ticker", "asset name", "asset type", "type", "amount", "comment")}
        ci["type"] = next((i for i, h in enumerate(head) if h == "type"), ci["type"])
        for tr in tbl[1:]:
            get = lambda k: tr[ci[k]][0] if ci[k] is not None and ci[k] < len(tr) else ""
            d = _iso(get("transaction date"))
            if not d:
                continue
            tick = get("ticker").strip()
            tick = None if tick in ("", "--", "N/A") else tick.split()[0].upper()
            asset_full = get("asset name")
            asset = asset_full.split(" | ")[0].strip()
            extra = " ".join(x.strip() for x in asset_full.split(" | ")[1:] if x.strip())
            at = get("asset type").strip()
            amt, lo, hi = parse_amount(get("amount"))
            ty = get("type").strip()
            comment = get("comment").strip()
            desc = "; ".join(x for x in (extra, comment if comment not in ("--", "") else "") if x) or None
            kind = ASSET_TYPES.get(at.lower(), "OT" if at else None)
            if kind == "OT" and tick:
                kind = "EF"   # ETFs are filed as "Other Securities"
            rows.append({"tx_date": d, "owner": (get("owner").strip() or "Self").title(), "ticker": tick, "asset": asset,
                         "asset_type": kind, "asset_type_label": at, "tx_type": ty.replace("(Full)", "").replace("  ", " ").strip()
                         if ty.startswith("Sale (Full") else ty, "amount": amt, "amount_low": lo, "amount_high": hi,
                         "description": desc})
    return rows


def paper_pages(text):
    """Image URLs of a paper (scanned) PTR."""
    return re.findall(r'<img[^>]+src="([^"]+\.(?:gif|png|jpe?g))"', text, re.I)


# ---------------------------------------------------------------- senators (party, state, bioguide, display name)
def _n(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z ]", "", re.sub(r"[-.,']", " ", s)).split()


class Senators:
    def __init__(self, current, historical):
        self.by_last = {}
        for p in list(historical) + list(current):
            terms = [t for t in p.get("terms", []) if t.get("type") == "sen" and t.get("end", "") >= "2018"]
            if not terms:
                continue
            t = terms[-1]
            nm = p["name"]
            full = nm.get("official_full") or f"{nm.get('first')} {nm.get('last')}"
            party = {"Democrat": "D", "Republican": "R", "Independent": "I"}.get(t.get("party"), t.get("party"))
            info = {"name": full, "first": _n(nm.get("first")) + _n(nm.get("nickname")) + _n(nm.get("middle")),
                    "state": t["state"], "party": party, "bioguide": p["id"].get("bioguide"), "end": t.get("end", "")}
            for key in {" ".join(_n(nm["last"])), (_n(nm["last"]) or [""])[-1]}:
                self.by_last.setdefault(key, []).append(info)

    def find(self, first, last):
        ln = _n(re.sub(r"\b(jr|sr|ii|iii|iv)\b\.?", "", last or "", flags=re.I))
        cands = self.by_last.get(" ".join(ln)) or self.by_last.get(ln[-1] if ln else "", [])
        if len(cands) == 1:
            return cands[0]
        fn = _n(first)
        hit = [c for c in cands if fn and any(f in c["first"] or any(x.startswith(f) or f.startswith(x) for x in c["first"])
                                              for f in fn)]
        hit = hit or cands
        return sorted(hit, key=lambda c: c["end"])[-1] if hit else None


# ---------------------------------------------------------------- ingestion (called from app.refresh)
SOURCE = "senate_efd"
SITE_DATA = os.environ.get("EFD_MIRROR_URL", "https://wajeehk.github.io/congress-trades/data/trades-all.json")
BACKFILL_SEEN = "T12:00:00+00:00"   # first_seen of backfilled rows (the disclosure date at noon), never alerted


def _akey(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())[:14]


def keys(last, tx_date, side, amount_low, ticker, asset):
    ln = (_n(last) or [""])[-1]
    k = [(ln, tx_date, side, amount_low, "t:" + ticker.upper())] if ticker else []
    return k + [(ln, tx_date, side, amount_low, "a:" + _akey(asset))]


def efd_keys(c):
    out = set()
    for r in c.execute("SELECT last_name, tx_date, side, amount_low, ticker, asset FROM trades WHERE source=?", (SOURCE,)):
        out.update(keys(r["last_name"], r["tx_date"], r["side"], r["amount_low"], r["ticker"], r["asset"]))
    return out


def bargo_dupe(ek, row):
    return any(k in ek for k in keys(row.get("last_name") or row.get("politician"), row.get("tx_date"), row.get("side"),
                                     row.get("amount_low"), row.get("ticker"), row.get("asset")))


def drop_bargo_dupes(c):
    """Bargo rows the Senate's own data now covers (same senator, date, side, band and ticker/asset) are removed."""
    ek = efd_keys(c)
    if not ek:
        return 0
    gone = [r["uid"] for r in c.execute("SELECT uid, politician, last_name, tx_date, side, amount_low, ticker, asset "
                                        "FROM trades WHERE source='bargo'") if bargo_dupe(ek, dict(r))]
    for u in gone:
        c.execute("DELETE FROM trades WHERE uid=?", (u,))
    return len(gone)


def _senators(app):
    cur = json.loads((app.DATA / "legislators-current.json").read_text()) if (app.DATA / "legislators-current.json").exists() else []
    hist = json.loads((app.DATA / "legislators-historical.json").read_text()) if (app.DATA / "legislators-historical.json").exists() else []
    return Senators(cur, hist)


def fetch(app):
    """Direct eFD ingestion (GitHub Actions). Returns rows that are genuinely new (alertable)."""
    if os.environ.get("EFD_DISABLE") == "1":
        return []
    blocked_until = float(app.meta_get("efd_blocked_until") or 0)
    if time.time() < blocked_until:
        return mirror_from_site(app)
    backfill = app.meta_get("efd_backfill_done") != "1"
    today = date.today()
    since = today - timedelta(days=BACKFILL_DAYS if backfill else RESCAN_DAYS)
    cl = Client()
    try:
        listing = cl.search_ptrs(since)
    except Blocked as e:
        app.meta_set("efd_blocked_until", str(time.time() + 12 * 3600))
        app.note(f"Senate eFD: {e}; using the published mirror for 12 h")
        return mirror_from_site(app)
    with app.db() as c:
        done = {r["id"] for r in c.execute("SELECT id FROM filings WHERE source=? AND status IN "
                                           "('parsed','no_transactions','paper')", (SOURCE,))}
    sen = _senators(app)
    todo = sorted([x for x in listing if f"efd:{x['report_id']}" not in done], key=lambda x: x["submitted"] or "", reverse=True)
    new_rows, fetched, papers, failed = [], 0, 0, 0
    with app.db() as c:
        ek = set(k for r in c.execute("SELECT last_name, tx_date, side, amount_low, ticker, asset FROM trades WHERE source='bargo'")
                 for k in keys(r["last_name"], r["tx_date"], r["side"], r["amount_low"], r["ticker"], r["asset"]))
    for x in todo:
        fid = f"efd:{x['report_id']}"
        who = sen.find(x["first"], x["last"]) or {}
        name = who.get("name") or f"{x['first']} {x['last']}".strip()
        state = who.get("state")
        url = BASE + x["path"]
        if x["kind"] == "paper":
            with app.db() as c:
                c.execute("INSERT OR REPLACE INTO filings VALUES(?,?,?,?,?,?,?,?,?,?)",
                          (fid, SOURCE, "Senate", app.clean_name(name), state, x["submitted"], url, "paper", 0, app.now()))
            papers += 1
            continue
        if fetched >= MAX_REPORTS:
            continue
        try:
            txs = parse_ptr_html(cl.report(x["path"]))
            fetched += 1
        except Blocked as e:
            app.note(f"Senate eFD blocked mid-run: {e}")
            break
        except Exception as e:
            failed += 1
            app.note(f"Senate eFD {x['report_id']} failed: {e}")
            continue
        amended = "amend" in x["title"].lower()
        is_backfill = backfill or (x["submitted"] or "") < (today - timedelta(days=app.NEW_WINDOW_DAYS)).isoformat()
        with app.db() as c:
            c.execute("INSERT OR REPLACE INTO filings VALUES(?,?,?,?,?,?,?,?,?,?)",
                      (fid, SOURCE, "Senate", app.clean_name(name), state, x["submitted"], url,
                       "parsed" if txs else "no_transactions", len(txs), app.now()))
            prev = {r["uid"]: r["first_seen"] for r in c.execute("SELECT uid, first_seen FROM trades WHERE filing_id=?", (fid,))}
            c.execute("DELETE FROM trades WHERE filing_id=?", (fid,))
            others = set()
            if amended:   # an amendment repeats the original's rows: keep only rows not already filed
                for r in c.execute("SELECT tx_date, ticker, asset, tx_type, amount_low, owner FROM trades WHERE source=? "
                                   "AND bioguide IS ? AND politician=?", (SOURCE, who.get("bioguide"), app.clean_name(name))):
                    others.add((r["tx_date"], r["ticker"] or _akey(r["asset"]), r["tx_type"], r["amount_low"], r["owner"]))
            for i, t in enumerate(txs):
                if amended and (t["tx_date"], t["ticker"] or _akey(t["asset"]), t["tx_type"], t["amount_low"], t["owner"]) in others:
                    continue
                uid = f"{fid}:{i}"
                row = {"uid": uid, "source": SOURCE, "filing_id": fid, "chamber": "Senate", "politician": name,
                       "last_name": x["last"], "party": who.get("party"), "state": state, "district": state,
                       "owner": t["owner"], "ticker": t["ticker"], "asset": t["asset"], "asset_type": t["asset_type"],
                       "tx_type": t["tx_type"], "side": app.side_of(t["tx_type"]), "tx_date": t["tx_date"],
                       "disclosure_date": x["submitted"], "amount": t["amount"], "amount_low": t["amount_low"],
                       "amount_high": t["amount_high"], "description": t["description"], "url": url,
                       "fetched_at": app.now(), "bioguide": who.get("bioguide"),
                       "first_seen": prev.get(uid) or ((x["submitted"] + BACKFILL_SEEN) if is_backfill else app.first_seen_for(x["submitted"]))}
                app.insert_trade(c, row)
                # alert only for rows nobody has alerted yet (Bargo may have carried the same trade first)
                if uid not in prev and not is_backfill and not bargo_dupe(ek, row):
                    new_rows.append(row)
            for (tk,) in c.execute("SELECT DISTINCT ticker FROM trades WHERE filing_id=? AND ticker IS NOT NULL", (fid,)).fetchall():
                c.execute(app.EST_SQL, (tk,))
    left = sum(1 for x in todo if x["kind"] == "ptr") - fetched - failed
    with app.db() as c:
        dropped = drop_bargo_dupes(c)
        app.canonical_names(c)
    if backfill and left <= 0 and not failed:
        app.meta_set("efd_backfill_done", "1")
    app.meta_set("efd_last_fetch", str(time.time()))
    app.note(f"Senate eFD: {len(listing)} PTRs listed since {since}, {fetched} e-filed fetched, {papers} paper recorded, "
             f"{left} left for later runs, {failed} failed, {cl.n} requests; {dropped} Bargo duplicates removed"
             + (" [backfill, no alerts]" if backfill else f"; {len(new_rows)} new"))
    return new_rows


def mirror_from_site(app):
    """Box server (eFD refuses its network): copy the eFD rows the GitHub pipeline published."""
    try:
        r = requests.get(SITE_DATA, headers={"User-Agent": "politician-trades-tracker box mirror"}, timeout=120)
        r.raise_for_status()
        d = r.json()
    except Exception as e:
        app.note(f"Senate eFD mirror failed: {e}")
        return []
    cols = d["cols"]
    seeded = app.meta_get("efd_mirror_seeded") == "1"
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    new_rows, n, fil = [], 0, {}
    with app.db() as c:
        have = {r["uid"] for r in c.execute("SELECT uid FROM trades WHERE source=?", (SOURCE,))}
        for vals in d["rows"]:
            t = dict(zip(cols, vals))
            if not str(t.get("uid", "")).startswith("efd:") or t["uid"] in have:
                continue
            row = {k: t.get(k) for k in app.TRADE_COLS if k in t}
            fid = t["uid"].rsplit(":", 1)[0]
            row.update(source=SOURCE, filing_id=fid, last_name=(t.get("politician") or "").split()[-1:][0] if t.get("politician") else "",
                       fetched_at=app.now())
            app.insert_trade(c, row, ignore=True)
            n += 1
            fil.setdefault(fid, [t, 0])[1] += 1
            fs = t.get("first_seen") or ""
            if seeded and fs >= cutoff and not fs.endswith(BACKFILL_SEEN):
                new_rows.append(row)
        for fid, (t, k) in fil.items():
            c.execute("INSERT OR IGNORE INTO filings VALUES(?,?,?,?,?,?,?,?,?,?)",
                      (fid, SOURCE, "Senate", t["politician"], t.get("state"), t.get("disclosure_date"), t.get("url"),
                       "parsed", k, app.now()))
        dropped = drop_bargo_dupes(c)
        app.canonical_names(c)
        for (tk,) in c.execute("SELECT DISTINCT ticker FROM trades WHERE source=? AND est_price IS NULL AND ticker IS NOT NULL", (SOURCE,)).fetchall():
            c.execute(app.EST_SQL, (tk,))
    app.meta_set("efd_mirror_seeded", "1")
    app.note(f"Senate eFD (mirrored from the published site): {n} rows added, {dropped} Bargo duplicates removed"
             + ("" if seeded else " [first sync, no alerts]"))
    return new_rows


if __name__ == "__main__":   # quick check: python senate_efd.py [days]
    import sys
    cl = Client()
    lst = cl.search_ptrs(date.today() - timedelta(days=int(sys.argv[1]) if len(sys.argv) > 1 else 30))
    print(len(lst), "PTRs;", sum(x["kind"] == "paper" for x in lst), "paper")
    for x in [y for y in lst if y["kind"] == "ptr"][:2]:
        rows = parse_ptr_html(cl.report(x["path"]))
        print(x["first"], x["last"], x["title"], x["submitted"], len(rows))
        for r in rows[:4]:
            print("  ", r)
