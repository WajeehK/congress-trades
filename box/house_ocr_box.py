"""Box-side OCR of scanned (paper) House PTRs into a committed cell text format.

For each page: render 300 dpi, fix orientation (tesseract OSD), find the transaction grid (long ruled lines),
then per data row OCR the owner / asset / date cells and measure ink in the type and amount checkbox cells.
Output (one file per DocID, house_ocr/<doc>.txt):
  #house_ocr v1 doc=<doc> pages=<n>
  R|<page>|<row>|<owner>|<asset>|<tx date>|<notified date>|<type inks>|<amount inks>
  T|<page>|<full page OCR text line>      (fallback text for pages without a detectable grid)
The interpretation (which box is ticked, date repair, neighbour inference) lives in house_scan_parser.py so it can
change without re-OCR.
"""
import os, re, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(__file__))
from house_grid import runs_mask, lines, data_rows, vcols


def osd_rotate(path):
    out = subprocess.run(["tesseract", path, "-", "--psm", "0"], capture_output=True, text=True).stdout
    m = re.search(r"Rotate: (\d+)", out)
    c = re.search(r"Orientation confidence: ([\d.]+)", out)
    return int(m.group(1)) if m and c and float(c.group(1)) >= 1.5 else 0


def ocr(img, psm=7, wl=None):
    with tempfile.NamedTemporaryFile(suffix=".png") as f:
        img.save(f.name)
        cmd = ["tesseract", f.name, "-", "--psm", str(psm)]
        if wl:
            cmd += ["-c", f"tessedit_char_whitelist={wl}"]
        return re.sub(r"\s+", " ", subprocess.run(cmd, capture_output=True, text=True).stdout).strip().replace("|", "/")


def crop(im, x0, x1, y0, y1, pad=0.12):
    dx, dy = int((x1 - x0) * pad), int((y1 - y0) * pad)
    return im.crop((x0 + dx, y0 + dy, x1 - dx, y1 - dy))


def ink(b, x0, x1, y0, y1, pad=0.08):
    """share of dark pixels in the cell that are not part of straight ruled/box lines (ticks and X marks are diagonal)"""
    dx, dy = max(3, int((x1 - x0) * pad)), max(3, int((y1 - y0) * pad))
    a = b[y0 + dy:y1 - dy, x0 + dx:x1 - dx]
    if a.size == 0 or min(a.shape) < 8:
        return 0.0
    L = max(6, int(0.4 * min(a.shape)))
    lm = runs_mask(a, L, 1) | runs_mask(a, L, 0)
    return float((a & ~lm).mean())


def classify(widths):
    """indexes: owner?, asset, type cols, date cols, amount cols."""
    a = int(np.argmax(widths))
    narrow = np.median(widths[a + 1:]) if len(widths) > a + 1 else 0
    i = a + 1
    types = []
    while i < len(widths) and widths[i] < narrow * 1.6:
        types.append(i); i += 1
    dates = []
    while i < len(widths) and widths[i] >= narrow * 1.6 and len(dates) < 2:
        dates.append(i); i += 1
    amts = list(range(i, len(widths)))
    return a, types, dates, amts


def layout(pil):
    """Grid of one page orientation -> (bool mask, data rows, column x's, (asset, types, dates, amounts)) or None."""
    im = np.array(pil)
    b = im < 150
    H, W = b.shape
    hm = runs_mask(b, W // 25, 1)
    hl = lines(hm.sum(1), W * 0.35)
    rows = data_rows(hl)
    if not rows:
        return None
    vm = runs_mask(b, max(20, H // 60), 0)
    xs = [v[0] for v in vcols(vm, rows, b)]
    widths = np.diff(xs)
    if len(widths) < 12:
        return None
    a, types, dates, amts = classify(widths)
    if 2 <= len(types) <= 4 and len(dates) == 2 and 8 <= len(amts) <= 12 and a <= 3:
        return b, rows, xs, (a, types, dates, amts)
    return None


def page(path, pno):
    rot0 = osd_rotate(path)
    base = Image.open(path).convert("L")
    found = None
    # OSD often misreads ruled forms scanned sideways: try its answer, then the other orientations
    for rot in dict.fromkeys([rot0, 90, 270, 0, 180]):
        pil = base.rotate(-rot, expand=True) if rot else base
        lay = layout(pil)
        if lay:
            found = (rot, pil, lay)
            break
    out = []
    if found:
        rot, pil, (b, rows, xs, (a, types, dates, amts)) = found
        for ri, (y0, y1) in enumerate(rows):
            cell = lambda k: (xs[k], xs[k + 1], y0, y1)
            x0, x1 = cell(a)[:2]
            asset = ocr(pil.crop((x0 + 7, y0 + int((y1 - y0) * 0.1), x1 - 7, y1 - int((y1 - y0) * 0.1))), 7)
            owner = ocr(crop(pil, *cell(a - 1), pad=0.08), 7, "SPJTDCsp") if a >= 1 else ""
            d1 = ocr(crop(pil, *cell(dates[0]), pad=0.06), 7, "0123456789/-.")
            d2 = ocr(crop(pil, *cell(dates[1]), pad=0.06), 7, "0123456789/-.")
            ti = ",".join(f"{ink(b, *cell(k)):.3f}" for k in types)
            ai = ",".join(f"{ink(b, *cell(k)):.3f}" for k in amts)
            out.append(f"R|{pno}|{ri}|{owner}|{asset}|{d1}|{d2}|{ti}|{ai}")
        return out, rot
    pil = base.rotate(-rot0, expand=True) if rot0 else base
    with tempfile.NamedTemporaryFile(suffix=".png") as f:
        pil.save(f.name)
        txt = subprocess.run(["tesseract", f.name, "-", "--psm", "6"], capture_output=True, text=True).stdout
    return [f"T|{pno}|{ln}" for ln in txt.splitlines() if ln.strip()], rot0


def run(pdf, outdir):
    doc = os.path.basename(pdf).split("_")[-1][:-4]
    dest = os.path.join(outdir, f"{doc}.txt")
    if os.path.exists(dest):
        return dest, "cached"
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(["pdftoppm", "-r", "300", "-gray", pdf, os.path.join(td, "p")], check=True)
        pages = sorted(os.listdir(td))
        res = []
        for i, f in enumerate(pages, 1):
            res.append(page(os.path.join(td, f), i))
    lines_ = [f"#house_ocr v2 doc={doc} pages={len(pages)}"]
    for r, rot in res:
        lines_ += r
    with open(dest + ".tmp", "w") as f:
        f.write("\n".join(lines_) + "\n")
    os.replace(dest + ".tmp", dest)
    return dest, f"{sum(1 for l in lines_ if l.startswith('R|'))} grid rows"


if __name__ == "__main__":
    outdir = sys.argv[1]
    pdfs = sys.argv[2:]
    os.makedirs(outdir, exist_ok=True)
    with ThreadPoolExecutor(max_workers=int(os.environ.get("WORKERS", "5"))) as ex:
        for p, (d, msg) in zip(pdfs, ex.map(lambda p: run(p, outdir), pdfs)):
            print(os.path.basename(p), msg, flush=True)
