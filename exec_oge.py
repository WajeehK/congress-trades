"""Executive branch beyond the President: the Vice President and Cabinet(-level) officials.

Documents come from OGE's public disclosure collection (the "PAS Index" in extapps2.oge.gov/201/Presiden.nsf, served
through its DataTables REST API): OGE 278-T periodic transaction reports and 278e annual / termination reports
(Part 7, Transactions). Documents marked "Request this Document" need an OGE Form 201 and are skipped.
Most of these are Integrity.gov e-filed PDFs with a clean text layer (parse_integrity); scanned ones fall back to
the President's OCR pipeline (app._parse_oge_pdf / oge_parser.parse_278e).
"""
import re
import time
from datetime import date

import requests

import oge_parser

API = "https://extapps2.oge.gov/201/Presiden.nsf/API.xsp/v3/rest"
START = "2025-01-01"   # this administration's officials (documents posted from 2025 on)

# key: OGE filer name exactly as the index lists it.  bioguide = congress-legislators id (gives a photo) when the
# official served in Congress; photo = static/img file otherwise (or None: initials avatar).
PEOPLE = {
    "Vance, JD": {"name": "JD Vance", "last": "Vance", "party": "R", "role": "Vice President", "bioguide": "V000137"},
    "Rubio, Marco": {"name": "Marco Rubio", "last": "Rubio", "party": "R", "role": "Secretary of State", "bioguide": "R000595"},
    "Bessent, Scott": {"name": "Scott Bessent", "last": "Bessent", "party": "R", "role": "Treasury Secretary"},
    "Hegseth, Pete": {"name": "Pete Hegseth", "last": "Hegseth", "party": "R", "role": "Defense Secretary"},
    "Bondi, Pam": {"name": "Pam Bondi", "last": "Bondi", "party": "R", "role": "Attorney General"},
    "Blanche, Todd": {"name": "Todd Blanche", "last": "Blanche", "party": "R", "role": "Attorney General"},
    "Burgum, Douglas J": {"name": "Doug Burgum", "last": "Burgum", "party": "R", "role": "Interior Secretary"},
    "Rollins, Brooke L": {"name": "Brooke Rollins", "last": "Rollins", "party": "R", "role": "Agriculture Secretary"},
    "Lutnick, Howard": {"name": "Howard Lutnick", "last": "Lutnick", "party": "R", "role": "Commerce Secretary"},
    "Chavez-DeRemer, Lori": {"name": "Lori Chavez-DeRemer", "last": "Chavez-DeRemer", "party": "R", "role": "Labor Secretary", "bioguide": "C001135"},
    "Sonderling, Keith": {"name": "Keith Sonderling", "last": "Sonderling", "party": "R", "role": "Labor Secretary"},
    "Kennedy, Robert F": {"name": "Robert F. Kennedy Jr.", "last": "Kennedy", "party": "I", "role": "HHS Secretary"},
    "Turner, Eric Scott": {"name": "Scott Turner", "last": "Turner", "party": "R", "role": "HUD Secretary"},
    "Duffy, Sean": {"name": "Sean Duffy", "last": "Duffy", "party": "R", "role": "Transportation Secretary", "bioguide": "D000614"},
    "Wright, Christopher A": {"name": "Chris Wright", "last": "Wright", "party": "R", "role": "Energy Secretary"},
    "McMahon, Linda E": {"name": "Linda McMahon", "last": "McMahon", "party": "R", "role": "Education Secretary"},
    "Collins, Doug": {"name": "Doug Collins", "last": "Collins", "party": "R", "role": "Veterans Affairs Secretary", "bioguide": "C001093"},
    "Noem, Kristi": {"name": "Kristi Noem", "last": "Noem", "party": "R", "role": "Homeland Security Secretary", "bioguide": "N000184"},
    "Mullin, Markwayne": {"name": "Markwayne Mullin", "last": "Mullin", "party": "R", "role": "Homeland Security Secretary", "bioguide": "M001190"},
    "Zeldin, Lee": {"name": "Lee Zeldin", "last": "Zeldin", "party": "R", "role": "EPA Administrator", "bioguide": "Z000017"},
    "Vought, Russell": {"name": "Russ Vought", "last": "Vought", "party": "R", "role": "OMB Director"},
    "Gabbard, Tulsi": {"name": "Tulsi Gabbard", "last": "Gabbard", "party": "R", "role": "Director of National Intelligence", "bioguide": "G000571"},
    "Greer, Jamieson": {"name": "Jamieson Greer", "last": "Greer", "party": "R", "role": "U.S. Trade Representative"},
    "Ratcliffe, John L": {"name": "John Ratcliffe", "last": "Ratcliffe", "party": "R", "role": "CIA Director", "bioguide": "R000601"},
    "Loeffler, Kelly": {"name": "Kelly Loeffler", "last": "Loeffler", "party": "R", "role": "SBA Administrator", "bioguide": "L000594"},
}


def filings(ua, delay=1.0):
    """[{who, docid, received, kind, label, file_name, amended, url}] for PEOPLE (same shape as app.oge_filings)."""
    out = []
    for who in PEOPLE:
        start = 0
        while True:
            r = requests.get(API, params={"draw": 1, "start": start, "length": 100, "search[value]": who},
                             headers=ua, timeout=240)
            r.raise_for_status()
            d = r.json()
            for x in d.get("data", []):
                if x.get("name") != who:
                    continue
                label = re.sub(r"<[^>]+>", "", x.get("type") or "").strip()
                m = re.search(r"href='([^']+\$FILE/[^']+)'", x.get("type") or "")
                if not m or "Request this Document" in label or (x.get("docDate") or "") < START:
                    continue
                if label.startswith("278 Transaction"):
                    kind = "278t"
                elif re.match(r"(Annual|Termination)", label):
                    kind = "278e"
                else:
                    continue   # nominee reports, ethics agreements, certifications: no transactions
                url = m.group(1).replace("\\/", "/")
                docid = url.split("/")[-3]
                out.append({"who": who, "docid": docid, "received": x["docDate"][:10], "kind": kind,
                            "label": label if kind == "278t" else re.sub(r"\s*\(Amended.*", "", label),
                            "file_name": requests.utils.unquote(url.split("/")[-1]),
                            "amended": "amend" in label.lower() or "AMEND" in url.upper(), "url": url, "exec": True})
            start += 100
            if start >= int(d.get("recordsFiltered") or 0):
                break
            time.sleep(delay)
        time.sleep(delay)
    return out


_ROW = re.compile(r"^\s*(\d{1,4})\s{2,}(\S.*?)\s{2,}(?:See Endnote\s+)?(Purchase|Sale|Exchange)(?:\s*\((partial|full)\))?"
                  r"\s{2,}(\d{1,2}/\d{1,2}/\d{4})(?:\s{2,}(Yes|No))?\s{2,}(.*)$", re.I)
_SKIP = re.compile(r"^\s*(#\s+DESCRIPTION|RECEIVED OVER|30 DAYS AGO|Data Revised|.* - Page \d+\s*$)", re.I)
_END = re.compile(r"^\s*(8\.\s+Liabilities|Endnotes\s*$|Summary of Contents|Part 7 discloses|9\.\s+Gifts)", re.I)


def parse_integrity(text):
    """Integrity.gov 278-T ("Transactions") and 278e ("7. Transactions") tables -> rows like oge_parser's."""
    rows, cur, on = [], None, False

    def flush():
        if not cur:
            return
        amt = oge_parser._amount(cur["amt"])
        desc = re.sub(r"\s+", " ", cur["desc"]).strip(" -")
        if not amt or len(desc) < 2:
            return
        try:
            mo, dd, yy = (int(x) for x in cur["date"].split("/"))
            d = date(yy, mo, dd)
        except ValueError:
            return
        t = cur["type"].lower()
        rows.append({"n": cur["n"], "asset": desc, "tx_type": {"purchase": "Purchase", "sale": "Sale"}.get(t, "Exchange")
                     + (" (partial)" if (cur["part"] or "").lower() == "partial" else ""),
                     "tx_date": d.isoformat(), "date_src": "exact", "amount_low": amt[0], "amount_high": amt[1],
                     "amount": oge_parser.band_text(*amt), "late": (cur["late"] or "").lower() == "yes"})

    for line in text.replace("\f", "\n").splitlines():
        s = line.strip()
        if re.match(r"^(7\.\s+)?Transactions$", s):
            on = True
            continue
        if not on:
            continue
        if _END.match(line):
            flush(); cur = None; on = False
            continue
        if not s or _SKIP.match(line):
            continue
        m = _ROW.match(line)
        if m:
            flush()
            cur = {"n": int(m.group(1)), "desc": m.group(2), "type": m.group(3), "part": m.group(4), "date": m.group(5),
                   "late": m.group(6), "amt": m.group(7), "c_desc": m.start(2), "c_type": m.start(3)}
        elif cur:
            ind = len(line) - len(line.lstrip())
            if ind >= cur["c_type"] - 2:
                if "$" in s:
                    cur["amt"] += " " + s
            else:
                part = line[:cur["c_type"]].strip()
                part = re.sub(r"\s{2,}See Endnote$", "", part)
                cur["desc"] += " " + part
                tail = line[cur["c_type"]:].strip()
                if "$" in tail:
                    cur["amt"] += " " + tail
    flush()
    for r in rows:   # a bare "See Endnote" marker sometimes stays in the description column
        r["asset"] = re.sub(r"\s*See Endnote\s*", " ", r["asset"]).strip()
    return rows


def ticker_of(asset):
    """Ticker written into the description: "QQQ - Invesco QQQ Trust" or "iShares MSCI Germany ETF (EWG)"."""
    m = re.match(r"^([A-Z]{1,5}(?:\.[A-Z])?)\s+-\s+\S", asset or "")
    if m:
        return m.group(1)
    m = re.search(r"\(([A-Z]{1,5}(?:\.[A-Z])?)\)\s*$", asset or "")
    if m and m.group(1) not in ("LLC", "LP", "IRA", "USD", "ETF", "UK", "US", "II", "III", "IV", "MLP"):
        return m.group(1)
    return None


def signed_on(text):
    """Filer's e-signature date ("electronically signed on MM/DD/YYYY by <filer>")."""
    m = re.search(r"electronically signed on (\d{2})/(\d{2})/(\d{4})", text or "")
    return f"{m.group(3)}-{m.group(1)}-{m.group(2)}" if m else None


def sane_dates(rows, received):
    """Typed-in year slips ("04/04/2225"): a trade can't postdate its report; take the report's year when that fits,
    otherwise drop the row."""
    out = []
    for r in rows:
        d = r["tx_date"]
        if d > received or d < "2000":
            fixed = received[:4] + d[4:]
            if fixed <= received:
                r = dict(r, tx_date=fixed, date_src="year-fixed")
            else:
                fixed = str(int(received[:4]) - 1) + d[4:]
                if not ("2000" <= fixed <= received):
                    continue
                r = dict(r, tx_date=fixed, date_src="year-fixed")
        out.append(r)
    return out
