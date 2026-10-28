"""Build the static GitHub Pages site: copy web/ and write pre-generated JSON from the SQLite state.

usage: python pipeline/export_static.py OUT_DIR

Senate rows come from Bargo's free API, whose terms forbid redistributing the raw records. We publish only
the processed fields the UI needs (our own cleaned names, our own Yahoo-derived price estimates; none of
Bargo's price/performance fields), restricted to Bargo's rolling ~3-month window, with a visible credit.
Set PUBLISH_SENATE=0 to leave Senate trades out of the static site entirely.
"""
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("NO_SCHEDULER", "1")
import app  # noqa: E402
import earnings  # noqa: E402
import gems  # noqa: E402
import recap  # noqa: E402
import most_bought  # noqa: E402
import stock_page  # noqa: E402

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "_site")
RECENT_DAYS = 100
PUBLISH_SENATE = os.environ.get("PUBLISH_SENATE", "1") != "0"
COLS = ["uid", "chamber", "politician", "party", "state", "district", "bioguide", "owner", "ticker", "asset",
        "asset_type", "tx_type", "side", "tx_date", "disclosure_date", "amount", "amount_low", "amount_high",
        "description", "url", "first_seen", "est_price", "est_date", "cur_price", "company", "pct_since",
        "day_low", "day_high", "day_open", "lag_days"]


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def stock_file(t):
    return re.sub(r"[^A-Za-z0-9.\-]", "_", t)


def senate_ok(r):
    # only Bargo-sourced rows carry Bargo's redistribution limits; the Senate's own eFD data is public record
    if r["chamber"] != "Senate" or r["source"] != "bargo":
        return True
    if not PUBLISH_SENATE:
        return False
    return (r["disclosure_date"] or "") >= (date.today() - timedelta(days=100)).isoformat()


def row(r):
    d = dict(r)
    if d["chamber"] == "Senate" and d.get("source") == "bargo":  # processed fields only
        d["description"] = None
    for k in ("est_price", "cur_price", "day_low", "day_high", "day_open"):
        if d.get(k) is not None:
            d[k] = round(d[k], 4)
    return [d.get(k) for k in COLS]


def pack(rows):
    return {"cols": COLS, "rows": [row(r) for r in rows]}


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, separators=(",", ":"), default=str))


def news_snapshot(path):
    """Fallback copy of FinancialJuice's public RSS headlines (the app fetches the feed live; this is only used if that fails)."""
    import urllib.request
    import xml.etree.ElementTree as ET
    from email.utils import parsedate_to_datetime
    try:
        req = urllib.request.Request("https://www.financialjuice.com/feed.ashx?xy=rss", headers={
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"})
        with urllib.request.urlopen(req, timeout=20) as r:
            root = ET.fromstring(r.read())
        items = []
        for it in root.iter("item"):
            title = re.sub(r"^FinancialJuice:\s*", "", (it.findtext("title") or "").strip())
            link = (it.findtext("link") or "").strip()
            if not title:
                continue
            if not re.match(r"^https://(www\.)?financialjuice\.com/", link, re.I):
                link = "https://www.financialjuice.com"
            try:
                t = int(parsedate_to_datetime(it.findtext("pubDate")).timestamp() * 1000)
            except Exception:
                t = 0
            items.append({"id": (it.findtext("guid") or link).strip(), "title": title, "link": link, "t": t})
        if items:
            dump(path, {"at": int(datetime.now(timezone.utc).timestamp() * 1000), "items": items[:60]})
            print(f"news snapshot: {len(items[:60])} headlines")
    except Exception as e:  # never fail the build over news
        print(f"news snapshot skipped: {e}")


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(ROOT / "web", OUT)
    data = OUT / "data"
    build = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    with app.db() as c:
        rows = [r for r in c.execute(f"{app.TRADE_SELECT} ORDER BY {app.SORTS['disclosure_date']}").fetchall() if senate_ok(r)]
        filings = c.execute("SELECT * FROM filings ORDER BY filing_date DESC").fetchall()
    recent_from = (date.today() - timedelta(days=RECENT_DAYS)).isoformat()
    dump(data / "trades-all.json", pack(rows))
    dump(data / "trades-recent.json", pack([r for r in rows if (r["disclosure_date"] or "") >= recent_from]))

    published = {r["politician"] for r in rows}
    pols = [p for p in app.politicians() if p["politician"] in published]
    dump(data / "politicians.json", pols)
    pfs = [p for p in app.portfolios() if p["politician"] in published]
    dump(data / "portfolios.json", pfs)
    dump(data / "most-bought.json", most_bought.build(rows))
    try:
        sec = json.loads((ROOT / "ticker_sectors.json").read_text())
    except Exception:
        sec = {}
    recent_rows = [r for r in rows if (r["first_seen"] or "") >= (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()]
    dump(data / "recap.json", {k: recap.build(recent_rows, k, sectors=sec) for k in ("daily", "weekly")})
    gm = gems.build(rows, sec)
    dump(data / "gems.json", gm)
    print(f"hidden gems: {len(gm['items'])} ({gm['caps']} caps)")

    by_pol, fil_by = {}, {}
    for r in rows:
        by_pol.setdefault(r["politician"], []).append(r)
    for f in filings:
        fil_by.setdefault(f["politician"], []).append({k: f[k] for k in ("source", "filing_date", "url", "status", "n_tx")})
    holders = {}
    for name, trs in by_pol.items():
        try:
            pf = app.portfolio(name, holdings=2000)
        except Exception:
            continue
        pf.pop("log", None)
        dump(data / "p" / f"{slug(name)}.json", {"portfolio": pf, "filings": fil_by.get(name, []), "trades": pack(trs)})
        for h in pf.get("holdings") or []:
            for hr in stock_page.holder_rows(h["ticker"], name, {"holdings": [h]}, pf):
                holders.setdefault(h["ticker"], []).append(hr)

    dump(data / "bench.json", app.bench_api())
    dump(data / "intro.json", app.intro_api())
    dump(data / "unusual.json", app.unusual_api())
    (data / "unusual").mkdir(exist_ok=True)
    for ev in app._unusual_recent():
        dump(data / "unusual" / f"{ev['id']}.json", ev)
    dump(data / "context.json", app.context_api())
    # stock pages: one small file per traded ticker (price series + estimated holders)
    first_tx = {}
    for r in rows:
        if r["ticker"] and r["tx_date"]:
            t = r["ticker"]
            first_tx[t] = min(first_tx.get(t, r["tx_date"]), r["tx_date"])
    with app.db() as c:
        for t, f in first_tx.items():
            hs = sorted(holders.get(t, []), key=lambda h: -h["value"])
            dump(data / "stock" / f"{stock_file(t)}.json", {"ticker": t, "px": stock_page.series(c, t, f), "holders": hs})

    news_snapshot(data / "news.json")
    try:  # earnings dates for the tags on trades made shortly before a report
        cal = earnings.refresh(app.meta_get, app.meta_set)
        dump(data / "earnings.json", earnings.build(cal, {(r["ticker"] or "").upper().replace("-", ".") for r in rows if r["ticker"]}))
    except Exception as e:
        print(f"earnings skipped: {e}")
    st = app.status()
    st["log"] = []
    st["running"] = False
    st["static"] = True
    st["sources"] = [s for s in st["sources"] if PUBLISH_SENATE or s["chamber"] != "Senate"]
    dump(data / "meta.json", {"build": build, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                              "recent_from": recent_from, "status": st, "publish_senate": PUBLISH_SENATE})
    # stamp a code version (hash of web/) so browsers and the service worker only refetch code when it changes
    h = hashlib.sha1()
    for f in sorted((ROOT / "web").rglob("*")):
        if f.is_file():
            h.update(f.read_bytes())
    code = h.hexdigest()[:10]
    for name in ("index.html", "sw.js"):
        f = OUT / name
        f.write_text(f.read_text().replace("__BUILD__", code))
    (OUT / ".nojekyll").write_text("")
    print(f"built {OUT}: {len(rows)} trades, {len(by_pol)} politician files, build {build}")


if __name__ == "__main__":
    main()
