"""Earnings dates around trades, from Nasdaq's free public earnings calendar (one request per weekday).

The calendar is cached in the DB meta table (key earn_cal_v1): past days are fetched once, the last 3 days and
upcoming days are refetched at most every 12 hours. build() returns {ticker: [YYYY-MM-DD, ...]} for traded tickers,
and the app tags trades made 0-14 days before an earnings date ("Earnings in 6d").
"""
import json
import time
from datetime import date, timedelta

import requests

URL = "https://api.nasdaq.com/api/calendar/earnings"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
      "Accept": "application/json"}
KEY, BACK, AHEAD, MAX_FETCH = "earn_cal_v1", 200, 45, 260


def _days(today):
    d = today - timedelta(days=BACK)
    while d <= today + timedelta(days=AHEAD):
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def refresh(meta_get, meta_set, note=print, today=None):
    today = today or date.today()
    try:
        cal = json.loads(meta_get(KEY) or "{}")
    except Exception:
        cal = {}
    lo = (today - timedelta(days=BACK)).isoformat()
    cal = {k: v for k, v in cal.items() if k >= lo}
    now, n, fails = time.time(), 0, 0
    s = requests.Session()
    for d in _days(today):
        k = d.isoformat()
        hit = cal.get(k)
        stale = hit is None or (d >= today - timedelta(days=3) and now - hit.get("at", 0) > 12 * 3600)
        if not stale or n >= MAX_FETCH or fails >= 5:
            continue
        n += 1
        try:
            r = s.get(URL, params={"date": k}, headers=UA, timeout=20)
            r.raise_for_status()
            rows = ((r.json().get("data") or {}).get("rows")) or []
            cal[k] = {"at": now, "t": sorted({(x.get("symbol") or "").upper().replace("/", ".") for x in rows} - {""})}
        except Exception as e:
            fails += 1
            note(f"earnings: {k} failed ({type(e).__name__})")
        time.sleep(0.15)
    meta_set(KEY, json.dumps(cal, separators=(",", ":")))
    if n:
        note(f"earnings: fetched {n} calendar day(s), {len(cal)} cached")
    return cal


def build(cal, tickers):
    out = {}
    for k in sorted(cal):
        for t in cal[k].get("t", []):
            if t in tickers:
                out.setdefault(t, []).append(k)
    return out
