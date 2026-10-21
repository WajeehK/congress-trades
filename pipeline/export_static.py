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

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "_site")
RECENT_DAYS = 100
PUBLISH_SENATE = os.environ.get("PUBLISH_SENATE", "1") != "0"
COLS = ["uid", "chamber", "politician", "party", "state", "district", "bioguide", "owner", "ticker", "asset",
        "asset_type", "tx_type", "side", "tx_date", "disclosure_date", "amount", "amount_low", "amount_high",
        "description", "url", "first_seen", "est_price", "est_date", "cur_price", "company", "pct_since",
        "day_low", "day_high", "day_open", "lag_days"]


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def senate_ok(r):
    if r["chamber"] != "Senate":
        return True
    if not PUBLISH_SENATE:
        return False
    return (r["disclosure_date"] or "") >= (date.today() - timedelta(days=100)).isoformat()


def row(r):
    d = dict(r)
    if d["chamber"] == "Senate":  # processed fields only
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

    by_pol, fil_by = {}, {}
    for r in rows:
        by_pol.setdefault(r["politician"], []).append(r)
    for f in filings:
        fil_by.setdefault(f["politician"], []).append({k: f[k] for k in ("source", "filing_date", "url", "status", "n_tx")})
    for name, trs in by_pol.items():
        try:
            pf = app.portfolio(name, holdings=2000)
        except Exception:
            continue
        pf.pop("log", None)
        dump(data / "p" / f"{slug(name)}.json", {"portfolio": pf, "filings": fil_by.get(name, []), "trades": pack(trs)})

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
