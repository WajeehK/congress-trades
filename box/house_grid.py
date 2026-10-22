import numpy as np, sys
from PIL import Image

def runs_mask(b, L, axis):
    """pixels that belong to a run of >= L dark pixels along axis (1=horizontal)."""
    a = b if axis == 1 else b.T
    cs = np.cumsum(np.pad(a.astype(np.int32), ((0, 0), (1, 0))), axis=1)
    win = cs[:, L:] - cs[:, :-L]          # count of dark pixels in window starting at x
    full = win >= int(L * 0.92)
    m = np.zeros_like(a, dtype=bool)
    # mark pixels covered by any full window (dilate by L)
    cf = np.cumsum(np.pad(full.astype(np.int32), ((0, 0), (1, 0))), axis=1)
    n = a.shape[1]
    idx = np.arange(n)
    lo = np.clip(idx - L + 1, 0, full.shape[1]); hi = np.clip(idx + 1, 0, full.shape[1])
    m = (cf[:, hi] - cf[:, lo]) > 0
    return m if axis == 1 else m.T

def lines(prof, thr, gap=6):
    ys = np.where(prof > thr)[0]
    out = []
    for y in ys:
        if out and y - out[-1][1] <= gap:
            out[-1][1] = y
        else:
            out.append([y, y])
    return [((a + b) // 2, b - a + 1) for a, b in out]

def grid(path):
    im = np.array(Image.open(path).convert("L"))
    b = im < 150
    H, W = b.shape
    hm = runs_mask(b, W // 25, 1)
    vm = runs_mask(b, H // 60, 0)
    hl = lines(hm.sum(1), W * 0.35)
    return im, b, hm, vm, hl

if __name__ == "__main__":
    im, b, hm, vm, hl = grid(sys.argv[1])
    print(im.shape, "hlines", len(hl), [h[0] for h in hl][:60])

def data_rows(hl):
    ys = [h[0] for h in hl]
    iv = [(ys[i], ys[i + 1]) for i in range(len(ys) - 1)]
    # longest run of consecutive intervals with plausible, similar heights
    best, cur = [], []
    for a, b2 in iv:
        h = b2 - a
        if 30 <= h <= 175 and (not cur or abs(h - np.median([y - x for x, y in cur])) <= 0.4 * np.median([y - x for x, y in cur])):
            cur.append((a, b2))
        else:
            if len(cur) >= len(best): best = cur
            cur = [(a, b2)] if 30 <= h <= 175 else []
    if len(cur) >= len(best): best = cur
    return best

def vcols(vm, rows, b=None):
    """Cell borders: vertical lines running (almost) unbroken through every data row. Printed checkbox edges stop
    short of the row lines, so they are rejected by the raw-ink continuity test (tolerating ~2 px of skew)."""
    y0, y1 = rows[0][0], rows[-1][1]
    if b is not None:
        a = b[y0:y1]
        w = a.copy()
        for k in (1, 2):
            w[:, k:] |= a[:, :-k]
            w[:, :-k] |= a[:, k:]
        return lines(w.mean(0), 0.93, gap=4)
    prof = vm[y0:y1].sum(0)
    return lines(prof, (y1 - y0) * 0.85, gap=4)
