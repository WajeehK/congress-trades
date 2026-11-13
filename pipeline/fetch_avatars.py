#!/usr/bin/env python3
"""Download official / freely licensed avatars into web/static/img/.

Sources (no hotlinks in the app):
  - US Congress official portraits: unitedstates/images (bioguide ID)
  - Insider headshots: Wikidata P18 on Wikimedia Commons, only when the
    item can be confidently matched to the named officer at that company
  - Company and fund logos: Wikimedia Commons (official/brand marks)

Never invent or guess a face. If a match is uncertain, fall back to the
company/institution logo (or leave the UI to render initials).
"""
from __future__ import annotations

import io, json, re, sys, time, unicodedata
from pathlib import Path

import requests
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web" / "static" / "img"
UA = {
    "User-Agent": (
        "TheInsiderHouse/1.0 (https://wajeehk.github.io/congress-trades/; "
        "khurramwajeeh-d0ymqp@mail.grokbot.com) python-requests"
    )
}
WD = "https://www.wikidata.org/w/api.php"
CM = "https://commons.wikimedia.org/w/api.php"
CONGRESS = "https://unitedstates.github.io/images/congress/225x275/{bio}.jpg"
POLS_URL = "https://wajeehk.github.io/congress-trades/data/politicians.json"

COMPANY_HINT = {
    "AAPL": re.compile(r"\bapple\b", re.I),
    "MSFT": re.compile(r"\bmicrosoft\b", re.I),
    "NVDA": re.compile(r"\bnvidia\b", re.I),
    "AMZN": re.compile(r"\bamazon\b", re.I),
    "GOOGL": re.compile(r"\balphabet\b|\bgoogle\b", re.I),
    "META": re.compile(r"\bmeta\b|\bfacebook\b", re.I),
    "TSLA": re.compile(r"\btesla\b", re.I),
    "AMD": re.compile(r"\bamd\b|advanced micro", re.I),
    "NFLX": re.compile(r"\bnetflix\b", re.I),
    "ORCL": re.compile(r"\boracle\b", re.I),
    "AVGO": re.compile(r"\bbroadcom\b", re.I),
    "JPM": re.compile(r"jpmorgan|j\.?\s*p\.?\s*morgan|jp morgan", re.I),
}
COMPANY_LABEL = {
    "AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "NVIDIA", "AMZN": "Amazon",
    "GOOGL": "Alphabet / Google", "META": "Meta", "TSLA": "Tesla", "AMD": "AMD",
    "NFLX": "Netflix", "ORCL": "Oracle", "AVGO": "Broadcom", "JPM": "JPMorgan",
}
ROLE_HINT = re.compile(
    r"chief|ceo|cfo|cto|coo|executive|business|entrepreneur|investor|"
    r"engineer|computer scientist|lawyer|attorney|director|officer|"
    r"president of|chairman|chairwoman|chair of|board member|professor|"
    r"nobel|founder",
    re.I,
)

# Preferred Commons filenames (checked first). These are well-known brand marks.
COMPANY_FILES = {
    "AAPL": ["Apple logo black.svg", "Apple logo (black).svg", "Apple Computer Logo.svg"],
    "MSFT": ["Microsoft logo (2012).svg", "Microsoft logo.svg"],
    "NVDA": ["NVIDIA logo.svg", "Nvidia-Logo.svg", "Nvidia logo.svg"],
    "AMZN": ["Amazon logo.svg", "Amazon.com-Logo.svg"],
    "GOOGL": ["Alphabet Inc Logo 2015.svg", "Alphabet Inc. logo.svg", "Google 2015 logo.svg"],
    "META": ["Meta Platforms Inc. logo.svg", "Meta-Logo.png", "Meta logo (2021).svg"],
    "TSLA": ["Tesla Motors logo.svg", "Tesla, Inc.-Logo.svg", "Tesla logo.svg"],
    "AMD": ["AMD logo.svg", "AMD Logo.svg", "AMD_Logo.svg"],
    "NFLX": ["Netflix 2015 logo.svg", "Netflix logo.svg"],
    "ORCL": ["Oracle logo.svg", "Oracle Corporation logo.svg"],
    "AVGO": ["Broadcom Inc. logo.svg", "Broadcom Corporation logo.svg", "Broadcom logo.svg"],
    "JPM": ["JPMorgan Chase logo.svg", "J.P. Morgan logo.svg", "JPMorgan Chase & Co. logo.svg"],
}
COMPANY_SEARCH = {
    "AAPL": "Apple logo", "MSFT": "Microsoft logo", "NVDA": "NVIDIA logo",
    "AMZN": "Amazon logo", "GOOGL": "Alphabet Inc logo", "META": "Meta Platforms logo",
    "TSLA": "Tesla logo", "AMD": "AMD logo", "NFLX": "Netflix logo",
    "ORCL": "Oracle logo", "AVGO": "Broadcom logo", "JPM": "JPMorgan Chase logo",
}
FUNDS = [
    {
        "key": "pif",
        "name": "Public Investment Fund (Saudi Arabia), chaired by MBS",
        "files": ["Public Investment Fund (Saudi Arabia) logo.svg", "Logo of the Public Investment Fund.svg"],
        "search": "Public Investment Fund (Saudi Arabia) logo",
        "require": r"saudi|public investment fund \(saudi",
    },
    {
        "key": "norges",
        "name": "Norges Bank",
        "files": ["Logo of Norges Bank.svg", "Norges Bank logo.svg", "NBIM logo.svg"],
        "search": "Norges Bank logo",
    },
    {
        "key": "mubadala",
        "name": "Mubadala Investment Company",
        "files": ["Mubadala logo.svg", "Mubadala Investment Company logo.svg", "Mubadala Development logo.svg"],
        "search": "Mubadala logo",
    },
    {
        "key": "temasek",
        "name": "Temasek Holdings",
        "files": ["Temasek Holdings logo.svg", "Temasek logo.svg", "Logo of Temasek Holdings.svg"],
        "search": "Temasek Holdings logo",
    },
    {
        "key": "berkshire",
        "name": "Berkshire Hathaway",
        "files": ["Berkshire Hathaway logo.svg", "Berkshire-hathaway-logo.svg", "Berkshire Hathaway.svg"],
        "search": "Berkshire Hathaway logo",
    },
    {
        "key": "pershing",
        "name": "Pershing Square",
        "files": ["Pershing Square Capital Management logo.svg", "Pershing Square logo.svg"],
        "search": "Pershing Square Capital Management logo",
    },
]

SLEEP = 0.2
session = requests.Session()
session.headers.update(UA)


def get(url, **kw):
    time.sleep(SLEEP)
    r = session.get(url, timeout=kw.pop("timeout", 40), **kw)
    r.raise_for_status()
    return r


def slug(n: str) -> str:
    n = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", n).strip("-")


def search_names(name: str) -> list[str]:
    out = []
    def add(x):
        x = re.sub(r"\s+", " ", x).strip()
        if x and x not in out:
            out.append(x)
    add(name)
    parts = name.split()
    if not parts:
        return out
    titled = name.title() if name == name.upper() else name
    tparts = titled.split()
    last, rest = tparts[0], tparts[1:]
    if rest:
        add(" ".join(rest + [last]))
        add(rest[0] + " " + last)
        if len(rest) >= 2 and len(rest[-1]) <= 2:
            add(" ".join(rest[:-1] + [last]))  # drop middle initial
    # common nicknames
    first = rest[0] if rest else ""
    nick = {"Timothy": "Tim", "Theodore": "Ted", "Bradford": "Brad", "Christopher": "Chris",
            "Andrew": "Andy", "Stephen": "Steve", "Frances": "Frances", "Deirdre": "Deirdre"}
    if first in nick and rest:
        add(nick[first] + " " + last)
    return out


def save_portrait(img_bytes: bytes, dest_big: Path, dest_small: Path | None, box=(450, 550)):
    im = Image.open(io.BytesIO(img_bytes))
    im = ImageOps.exif_transpose(im)
    if im.mode in ("P", "RGBA", "LA"):
        bg = Image.new("RGB", im.size, (247, 247, 244))
        if im.mode == "P":
            im = im.convert("RGBA")
        bg.paste(im, mask=im.split()[-1] if im.mode == "RGBA" else None)
        im = bg
    else:
        im = im.convert("RGB")
    w, h = im.size
    tr = box[0] / box[1]
    if w / h > tr:
        nw = int(h * tr)
        im = im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    else:
        nh = int(w / tr)
        top = max(0, int((h - nh) * 0.12))
        if top + nh > h:
            top = h - nh
        im = im.crop((0, top, w, top + nh))
    dest_big.parent.mkdir(parents=True, exist_ok=True)
    im.resize(box, Image.LANCZOS).save(dest_big, "JPEG", quality=84, optimize=True, progressive=True)
    if dest_small:
        sm = (box[0] // 2, box[1] // 2)
        im.resize(sm, Image.LANCZOS).save(dest_small, "JPEG", quality=82, optimize=True, progressive=True)


def save_logo(img_bytes: bytes, dest: Path, size=128):
    im = Image.open(io.BytesIO(img_bytes))
    im = ImageOps.exif_transpose(im)
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA") if "A" in im.getbands() else im.convert("RGB")
    # square canvas with padding so wordmarks / marks aren't cropped
    w, h = im.size
    side = int(max(w, h) * 1.18) or 1
    canvas = Image.new("RGBA", (side, side), (255, 255, 255, 255))
    canvas.paste(im, ((side - w) // 2, (side - h) // 2), im if im.mode == "RGBA" else None)
    canvas = canvas.convert("RGB").resize((size, size), Image.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(dest, "PNG", optimize=True)


def commons_info(fn: str, width=900):
    r = get(CM, params={
        "action": "query", "titles": "File:" + fn, "prop": "imageinfo",
        "iiprop": "url|extmetadata|mime|size", "iiurlwidth": width, "format": "json",
    }).json()
    pages = r.get("query", {}).get("pages", {})
    page = next(iter(pages.values()))
    if page.get("missing") or "imageinfo" not in page:
        return None
    ii = page["imageinfo"][0]
    md = ii.get("extmetadata", {})
    strip = lambda s: re.sub(r"<[^>]+>", "", (s or {}).get("value", "") or "").strip()
    return {
        "file": fn,
        "thumb": ii.get("thumburl") or ii["url"],
        "url": ii["url"],
        "page": ii["descriptionurl"],
        "license": strip(md.get("LicenseShortName")),
        "artist": strip(md.get("Artist")),
        "credit": strip(md.get("Credit")),
        "mime": ii.get("mime", ""),
    }


def commons_search(q: str, limit=8):
    r = get(CM, params={
        "action": "query", "list": "search", "srnamespace": 6, "srsearch": q,
        "srlimit": limit, "format": "json",
    }).json()
    out = []
    for h in r.get("query", {}).get("search", []):
        title = h["title"]
        if title.lower().startswith("file:"):
            out.append(title[5:])
    return out


def fetch_bytes(url: str) -> bytes:
    return get(url).content


def pick_logo(files: list[str], search: str, require: str | None = None):
    tried = []
    def ok(fn, info):
        if not info:
            return False
        mime = (info.get("mime") or "")
        if not mime.startswith("image/"):
            return False
        if require and not re.search(require, fn + " " + (info.get("file") or ""), re.I):
            return False
        return True
    for fn in files:
        tried.append(fn)
        info = commons_info(fn, width=512)
        if ok(fn, info):
            return info
    for fn in commons_search(search):
        if fn in tried:
            continue
        if re.search(r"icon|flag of|map of|portrait|coat of arms|screenshot|\.pdf$", fn, re.I):
            continue
        info = commons_info(fn, width=512)
        if ok(fn, info):
            return info
    return None


# ---------- congress ----------
def fetch_congress(bios: list[str], sources: list):
    out = []
    dest_dir = WEB / "congress"
    dest_dir.mkdir(parents=True, exist_ok=True)
    for i, bio in enumerate(bios, 1):
        dest = dest_dir / f"{bio}.jpg"
        dest_s = dest_dir / f"{bio}-s.jpg"
        if dest.exists() and dest_s.exists() and dest.stat().st_size > 1000:
            out.append(bio)
            continue
        urls = [
            CONGRESS.format(bio=bio),
            f"https://unitedstates.github.io/images/congress/450x550/{bio}.jpg",
        ]
        try:
            data = None
            url = urls[0]
            for url in urls:
                try:
                    data = fetch_bytes(url)
                except Exception:
                    data = None
                    continue
                if data and data[:2] == b"\xff\xd8":
                    break
                data = None
            if not data or data[:2] != b"\xff\xd8":
                print(f"  skip {bio}: no official jpeg")
                continue
            # official portraits are already 225x275; keep that as the large
            # file and write a 128-wide small avatar.
            im = Image.open(io.BytesIO(data)).convert("RGB")
            # upscale slightly to 256x314 for the person-page hero (max CSS 132x164)
            big = im.resize((256, 314), Image.LANCZOS) if im.size[0] < 256 else im
            big.save(dest, "JPEG", quality=86, optimize=True, progressive=True)
            im.resize((128, 157), Image.LANCZOS).save(dest_s, "JPEG", quality=84, optimize=True, progressive=True)
            out.append(bio)
            sources.append({
                "kind": "congress", "id": bio, "file": f"congress/{bio}.jpg",
                "license": "Public domain (U.S. government work)",
                "source": url,
                "credit": "Official congressional portrait via unitedstates/images",
            })
            if i % 25 == 0:
                print(f"  congress {i}/{len(bios)}")
        except Exception as e:
            print(f"  fail {bio}: {e}")
    return out


# ---------- wikidata insiders ----------
def wd_search(q: str):
    r = get(WD, params={
        "action": "wbsearchentities", "search": q, "language": "en",
        "type": "item", "limit": 8, "format": "json",
    }).json()
    return r.get("search", [])


def wd_entity(qid: str):
    r = get(WD, params={
        "action": "wbgetentities", "ids": qid, "props": "labels|descriptions|claims",
        "languages": "en", "format": "json",
    }).json()
    return r.get("entities", {}).get(qid) or {}


def claim_ids(ent, prop):
    ids = []
    for cl in (ent.get("claims") or {}).get(prop, []):
        dv = (cl.get("mainsnak") or {}).get("datavalue") or {}
        if dv.get("type") == "wikibase-entityid":
            ids.append(dv["value"]["id"])
    return ids


def labels_for(ids: list[str]) -> str:
    if not ids:
        return ""
    r = get(WD, params={
        "action": "wbgetentities", "ids": "|".join(ids[:12]), "props": "labels",
        "languages": "en", "format": "json",
    }).json()
    bits = []
    for e in (r.get("entities") or {}).values():
        lab = (e.get("labels") or {}).get("en", {}).get("value")
        if lab:
            bits.append(lab)
    return " ".join(bits)


def p18_file(ent) -> str | None:
    cl = (ent.get("claims") or {}).get("P18", [])
    if not cl:
        return None
    dv = (cl[0].get("mainsnak") or {}).get("datavalue")
    return dv["value"] if dv else None


def confident_match(hit, ent, ticker: str, queries: list[str]) -> bool:
    hint = COMPANY_HINT[ticker]
    desc = (hit.get("description") or "")
    label = (hit.get("label") or "")
    en_desc = ((ent.get("descriptions") or {}).get("en") or {}).get("value") or desc
    text = f"{label} {desc} {en_desc}"
    employers = labels_for(claim_ids(ent, "P108") + claim_ids(ent, "P39") + claim_ids(ent, "P101"))
    text_plus = f"{text} {employers}"
    if not hint.search(text_plus):
        return False
    # require the flipped/natural name to be close to the item label
    lab_n = re.sub(r"[^a-z]+", "", label.lower())
    ok_name = False
    for q in queries:
        qn = re.sub(r"[^a-z]+", "", q.lower())
        if not qn:
            continue
        if qn == lab_n or qn in lab_n or lab_n in qn:
            ok_name = True
            break
        # first+last tokens present
        toks = [t for t in re.findall(r"[a-z]+", q.lower()) if len(t) > 1 and t not in {"de", "da", "von", "van"}]
        lab_toks = set(re.findall(r"[a-z]+", label.lower()))
        if len(toks) >= 2 and toks[0] in lab_toks and toks[-1] in lab_toks:
            ok_name = True
            break
    return ok_name


def find_insider(name: str, ticker: str):
    queries = search_names(name)
    # also search "Name Company"
    company = COMPANY_LABEL[ticker]
    extra = [f"{q} {company}" for q in queries[:3]]
    seen = set()
    candidates = []
    for q in queries + extra:
        for h in wd_search(q):
            qid = h.get("id")
            if not qid or qid in seen:
                continue
            seen.add(qid)
            candidates.append(h)
    matches = []
    for h in candidates:
        try:
            ent = wd_entity(h["id"])
        except Exception as e:
            print(f"    wd get {h.get('id')}: {e}")
            continue
        if confident_match(h, ent, ticker, queries):
            fn = p18_file(ent)
            matches.append((h, ent, fn))
    # unique people
    uniq = {}
    for h, ent, fn in matches:
        uniq[h["id"]] = (h, ent, fn)
    with_photo = [(h, ent, fn) for h, ent, fn in uniq.values() if fn]
    if len(with_photo) == 1:
        return with_photo[0]
    if len(with_photo) > 1:
        # too ambiguous — don't pick a face
        print(f"    ambiguous {name}: {[h['id']+':'+h.get('label','') for h,_,_ in with_photo]}")
        return None
    return None


def fetch_insiders(insiders: list[dict], sources: list):
    photos, company_of, missed = {}, {}, []
    dest_dir = WEB / "insiders"
    dest_dir.mkdir(parents=True, exist_ok=True)
    for i, p in enumerate(insiders, 1):
        name, ticker = p["politician"], (p.get("state") or "").upper()
        company_of[name] = ticker
        print(f"  [{i}/{len(insiders)}] {name} ({ticker})")
        try:
            hit = find_insider(name, ticker)
        except Exception as e:
            print(f"    error: {e}")
            hit = None
        if not hit:
            missed.append((name, ticker, "no confident photo"))
            continue
        h, ent, fn = hit
        info = commons_info(fn, width=900)
        if not info:
            missed.append((name, ticker, f"no commons file {fn}"))
            continue
        try:
            data = fetch_bytes(info["thumb"])
            base = slug(h.get("label") or name)
            save_portrait(data, dest_dir / f"{base}.jpg", dest_dir / f"{base}-s.jpg")
            photos[name] = f"static/img/insiders/{base}"
            sources.append({
                "kind": "insider", "name": name, "qid": h["id"], "label": h.get("label"),
                "file": f"insiders/{base}.jpg",
                "license": info["license"], "artist": info["artist"], "credit": info["credit"],
                "source": info["page"],
            })
            print(f"    OK {h['id']} {h.get('label')} ← {fn}")
        except Exception as e:
            missed.append((name, ticker, str(e)))
            print(f"    save fail: {e}")
    return photos, company_of, missed


# ---------- logos ----------
def fetch_logos(sources: list):
    companies, funds = {}, {}
    cdir, fdir = WEB / "companies", WEB / "funds"
    cdir.mkdir(parents=True, exist_ok=True)
    fdir.mkdir(parents=True, exist_ok=True)
    for ticker, files in COMPANY_FILES.items():
        print(f"  logo {ticker}")
        info = pick_logo(files, COMPANY_SEARCH[ticker])
        if not info:
            print(f"    MISS {ticker}")
            continue
        try:
            data = fetch_bytes(info["thumb"])
            dest = cdir / f"{ticker.lower()}.png"
            save_logo(data, dest, 128)
            companies[ticker] = f"static/img/companies/{ticker.lower()}.png"
            sources.append({
                "kind": "company", "ticker": ticker, "file": f"companies/{ticker.lower()}.png",
                "license": info["license"], "artist": info["artist"], "credit": info["credit"],
                "source": info["page"], "commons": info["file"],
            })
            print(f"    OK {info['file']} ({info['license']})")
        except Exception as e:
            print(f"    fail {ticker}: {e}")
    for f in FUNDS:
        print(f"  fund {f['key']}")
        info = pick_logo(f["files"], f["search"], f.get("require"))
        if not info:
            print(f"    MISS {f['key']}")
            continue
        try:
            data = fetch_bytes(info["thumb"])
            dest = fdir / f"{f['key']}.png"
            save_logo(data, dest, 128)
            funds[f["name"]] = f"static/img/funds/{f['key']}.png"
            sources.append({
                "kind": "fund", "name": f["name"], "file": f"funds/{f['key']}.png",
                "license": info["license"], "artist": info["artist"], "credit": info["credit"],
                "source": info["page"], "commons": info["file"],
            })
            print(f"    OK {info['file']} ({info['license']})")
        except Exception as e:
            print(f"    fail {f['key']}: {e}")
    return companies, funds



def write_spacex_chip(size=128):
    """Deterministic high-contrast stand-in. The official Commons X-swoosh is a
    light glyph and is unreadable at avatar size on a light row."""
    from PIL import ImageDraw, ImageFont
    dest = WEB / "companies" / "spacex.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", (size, size), (17, 17, 17))
    draw = ImageDraw.Draw(im)
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    try:
        font = ImageFont.truetype(font_path, 96)
    except Exception:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), "X", font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    target = size * 0.76
    try:
        font = ImageFont.truetype(font_path, max(8, int(font.size * (target / max(tw, th)))))
    except Exception:
        pass
    bbox = draw.textbbox((0, 0), "X", font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - tw) // 2 - bbox[0], (size - th) // 2 - bbox[1]), "X", font=font, fill=(255, 255, 255))
    im.save(dest, "PNG", optimize=True)
    return dest


HOLDING_LOGOS = {
    "LCID": "static/img/companies/lcid.png",
    "SPACE EXPLORATION TECHN CORP": "static/img/companies/spacex.png",
    "SPACEX": "static/img/companies/spacex.png",
    "SpaceX": "static/img/companies/spacex.png",
    "SPACE EXPLORATION TECHNOLOGIES": "static/img/companies/spacex.png",
    "SPACE EXPLORATION TECHNOLOGIES CORP": "static/img/companies/spacex.png",
}


def write_js(congress, photos, company_of, companies, funds):
    payload = {
        "CONGRESS_PHOTOS": {b: 1 for b in congress},
        "INSIDER_PHOTOS": photos,
        "INSIDER_COMPANY": company_of,
        "COMPANY_LOGOS": companies,
        "FUND_LOGOS": funds,
        "HOLDING_LOGOS": HOLDING_LOGOS,
    }
    lines = ["/* Generated by pipeline/fetch_avatars.py. Local avatars; do not hotlink. See img/SOURCES-avatars.md */"]
    for k, v in payload.items():
        lines.append(f"window.{k} = {json.dumps(v, ensure_ascii=False, sort_keys=True)};")
    (WEB / "avatars.js").write_text("\n".join(lines) + "\n")


def write_sources(sources, missed):
    dest = WEB / "SOURCES-avatars.md"
    lines = [
        "# Avatar sources",
        "",
        "All images are stored in this repo and served from GitHub Pages. Nothing is hotlinked at runtime.",
        "",
        "## Congress and some White House officials with a bioguide ID",
        "",
        "Official portraits from the [unitedstates/images](https://github.com/unitedstates/images) dataset (`congress/225x275/{bioguide}.jpg`), resized to 256×314 and 128×157 JPEGs. These are U.S. government works and are in the public domain. Cabinet officials without a bioguide already have local Wikimedia portraits under `img/people/` (see `people/SOURCES.md`). The President uses `img/trump.jpg`.",
        "",
        f"{sum(1 for s in sources if s['kind']=='congress')} portraits downloaded.",
        "",
        "## Corporate insiders (SEC Form 4)",
        "",
        "A headshot is used only when Wikidata identifies the person with high confidence (name match plus employer/description tying them to the filing company) and that item has a Wikimedia Commons photograph (P18). Everyone else uses the company's mark, then initials if that is also missing. Faces are never guessed.",
        "",
        "| Person | File | Wikidata | License | Credit | Source |",
        "|---|---|---|---|---|---|",
    ]
    for s in sources:
        if s["kind"] != "insider":
            continue
        cred = (s.get("artist") or s.get("credit") or "").replace("|", "/")
        lines.append(f"| {s['name']} | {s['file']} | {s['qid']} ({s.get('label') or ''}) | {s.get('license','')} | {cred} | {s['source']} |")
    lines += [
        "",
        "### Insiders without a confident headshot (company logo / initials fallback)",
        "",
    ]
    if missed:
        lines.append("| Person | Company | Reason |")
        lines.append("|---|---|---|")
        for name, ticker, reason in missed:
            lines.append(f"| {name} | {ticker} | {reason} |")
    else:
        lines.append("None.")
    lines += [
        "",
        "## Company logos (insider fallback, and consistency)",
        "",
        "| Ticker | File | Commons file | License | Credit | Source |",
        "|---|---|---|---|---|---|",
    ]
    for s in sources:
        if s["kind"] != "company":
            continue
        cred = (s.get("artist") or s.get("credit") or "").replace("|", "/")
        lines.append(f"| {s['ticker']} | {s['file']} | {s.get('commons','')} | {s.get('license','')} | {cred} | {s['source']} |")
    lines += [
        "",
        "## Fund / institution logos",
        "",
        "| Fund | File | Commons file | License | Credit | Source |",
        "|---|---|---|---|---|---|",
    ]
    for s in sources:
        if s["kind"] != "fund":
            continue
        cred = (s.get("artist") or s.get("credit") or "").replace("|", "/")
        lines.append(f"| {s['name']} | {s['file']} | {s.get('commons','')} | {s.get('license','')} | {cred} | {s['source']} |")
    dest.write_text("\n".join(lines) + "\n")


def main():
    print("Loading politicians…")
    pols = get(POLS_URL).json()
    ins = [p for p in pols if p.get("chamber") == "Insider"]
    bios = sorted({p["bioguide"] for p in pols if p.get("bioguide")})
    print(f"  {len(pols)} people, {len(ins)} insiders, {len(bios)} bioguides")
    sources = []
    print("Congress portraits…")
    congress = fetch_congress(bios, sources)
    print(f"  got {len(congress)}/{len(bios)}")
    print("Company and fund logos…")
    companies, funds = fetch_logos(sources)
    print("Insider headshots…")
    photos, company_of, missed = fetch_insiders(ins, sources)
    write_spacex_chip()
    write_js(congress, photos, company_of, companies, funds)
    write_sources(sources, missed)
    print("DONE")
    print(f"  congress {len(congress)}  insiders-photos {len(photos)}  logos {len(companies)}  funds {len(funds)}  missed {len(missed)}")


if __name__ == "__main__":
    main()
