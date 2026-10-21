"""Re-OCR an OGE 278-T PDF with tesseract after removing the table grid lines (much better than the scanned text layer)."""
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image


def clean(png):
    im = np.array(Image.open(png).convert("L"))
    b = im < 140
    out = im.copy()
    for y in np.where(b.mean(1) > 0.25)[0]:
        out[max(0, y - 1):y + 2, :] = 255
    for x in np.where(b.mean(0) > 0.25)[0]:
        out[:, max(0, x - 1):x + 2] = 255
    for x in np.where(b[int(b.shape[0] * 0.15):].mean(0) > 0.35)[0]:
        out[:, max(0, x - 1):x + 2] = 255
    Image.fromarray(out).resize((out.shape[1] * 2, out.shape[0] * 2), Image.LANCZOS).save(png)


def page(png):
    txt = png.with_suffix(".txt")
    if txt.exists():
        return
    clean(png)
    subprocess.run(["nice", "-n", "15", "tesseract", str(png), str(png.with_suffix("")), "--psm", "6"], capture_output=True,
                   env={**os.environ, "OMP_THREAD_LIMIT": "1"})
    png.unlink()


def ocr_pdf(pdf, workers=3):
    pdf = Path(pdf)
    d = pdf.with_suffix(".ocr")
    d.mkdir(exist_ok=True)
    if (d / "ALL.txt").exists():
        return (d / "ALL.txt").read_text()
    if not any(d.glob("p-*.txt")):
        subprocess.run(["nice", "-n", "15", "pdftoppm", "-r", "300", "-gray", "-png", str(pdf), str(d / "p")], check=True)
    pngs = sorted(d.glob("p-*.png"))
    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(page, pngs))
    text = "\n".join(p.read_text() for p in sorted(d.glob("p-*.txt")))
    (d / "ALL.txt").write_text(text)
    return text


if __name__ == "__main__":
    for f in sys.argv[1:]:
        ocr_pdf(f, workers=int(os.environ.get("OCR_WORKERS", "4")))
        print("done", f, flush=True)
