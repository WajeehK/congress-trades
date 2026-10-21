"""Parser for electronically-filed House Periodic Transaction Reports (PTR PDFs).

Uses `pdftotext -layout` (poppler-utils) and anchors on the transaction line, which
always contains: <type> <transaction date> <notification date> <amount>.
Scanned paper filings (DocIDs starting with 8/9) contain no text and are skipped.
"""
import re
import subprocess

TX_RE = re.compile(
    r"\s(P|S(?:\s*\(partial\))?|E)\s+(\d{1,2}/\d{1,2}/\d{4})\s+(\d{1,2}/\d{1,2}/\d{4})\s+"
    r"(\$[\d,]+\s*-?\s*(?:\$[\d,]+)?|Spouse/DC Over(?:\s+\$[\d,]+)?|Over\s+\$[\d,]+)"
)
OWNER_RE = re.compile(r"^\s*(?:\S+\s+)?(SP|JT|DC)\s{2,}")
TICKER_RE = re.compile(r"\(([A-Z][A-Z0-9.\-/$]{0,9})\)")
ATYPE_RE = re.compile(r"\[([A-Z]{2})\]")
META_RE = re.compile(r"^\s*(F\s+S\s*:|S\s+O\s*:|D\s*:|C\s*:|L\s*:|\* For the complete|Filing ID #|ID\s+Owner|Type\s+Date|\$200\?|Gains >)")
HEADER_RE = re.compile(r"(Filing ID #|ID\s+Owner Asset|^\s*Type\s+Date|^\s*\$200\?|Gains >|Clerk of the House|^\s*P\s+T\s+R\s*$)")
OWNER_MAP = {"SP": "Spouse", "JT": "Joint", "DC": "Dependent child", "": "Self"}
TYPE_MAP = {"P": "Purchase", "S": "Sale", "E": "Exchange"}


def pdf_text(path):
    return subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True, timeout=60).stdout


def parse_amount(s):
    s = re.sub(r"\s+", " ", s).strip()
    nums = [int(n.replace(",", "")) for n in re.findall(r"\$([\d,]+)", s)]
    if "Over" in s:
        return s, (nums[0] + 1 if nums else None), None
    if len(nums) >= 2:
        return f"${nums[0]:,} - ${nums[1]:,}", nums[0], nums[1]
    return s, (nums[0] if nums else None), None


def parse_ptr_text(text):
    """Return list of dict transactions."""
    # restrict to the transactions section(s)
    lines = text.replace("\f", "\n").split("\n")
    out = []
    # find section start: after first '$200?' line; end at '* For the complete list'
    start = 0
    for i, l in enumerate(lines):
        if "$200?" in l:
            start = i + 1
            break
    end = len(lines)
    for i in range(start, len(lines)):
        if "* For the complete list" in lines[i] or re.match(r"^\s*I\s+P\s+O\s*$", lines[i]):
            end = i
            break
    sec = [l for l in lines[start:end] if not HEADER_RE.search(l)]

    # group into blocks separated by blank lines
    blocks, cur = [], []
    for l in sec:
        if l.strip() == "":
            if cur:
                blocks.append(cur)
                cur = []
        else:
            cur.append(l)
    if cur:
        blocks.append(cur)
    # re-join blocks split by a page break: a block with no transaction line that follows
    # a block whose metadata (F S : ...) has not started yet is a continuation
    merged = []
    for b in blocks:
        has_tx = any(TX_RE.search(l) for l in b)
        if merged and not has_tx and not any(re.match(r"^\s*F\s+S\s*:", l) for l in merged[-1][1:]):
            merged[-1].extend(b)
        else:
            merged.append(b)
    blocks = merged

    pending_asset = []  # asset text lines appearing in a block before the tx line (rare page splits)
    for b in blocks:
        txi = next((i for i, l in enumerate(b) if TX_RE.search(l)), None)
        if txi is None:
            # block of metadata (F S / S O / D) belonging to previous transaction
            if out:
                for l in b:
                    m = re.match(r"^\s*D\s*:\s*(.*)", l)
                    if m:
                        out[-1]["description"] = ((out[-1].get("description") or "") + " " + m.group(1)).strip()
            continue
        txl = b[txi]
        m = TX_RE.search(txl)
        type_col = m.start(1)
        amt_col = m.start(4)
        asset_parts, owner = [], ""
        amount = m.group(4)
        meta_started = False
        desc = []
        for i, l in enumerate(b):
            if i > txi and META_RE.match(l):
                meta_started = True
            if meta_started:
                dm = re.match(r"^\s*D\s*:\s*(.*)", l)
                if dm:
                    desc.append(dm.group(1).strip())
                elif desc and not META_RE.match(l):
                    desc.append(l.strip())
                continue
            if i > txi:
                am = re.search(r"\s{2,}(\$[\d,]+|Over \$[\d,]+)\s*$", l)
                if am:
                    if amount.rstrip().endswith(("-", "Over")):
                        amount += " " + am.group(1)
                    l = l[:am.start()]
                left = l
            else:
                left = l[:type_col] if i == txi else l
            om = OWNER_RE.match(left)
            if om:
                owner = om.group(1)
                left = left[om.end():]
            asset_parts.append(left.strip())
        asset = re.sub(r"\s+", " ", " ".join(p for p in asset_parts if p)).strip()
        tickers = TICKER_RE.findall(asset)
        at = ATYPE_RE.findall(asset)
        amt_str, lo, hi = parse_amount(amount)
        t = m.group(1)
        out.append({
            "owner": OWNER_MAP.get(owner, owner),
            "asset": asset,
            "ticker": tickers[-1] if tickers else None,
            "asset_type": at[-1] if at else None,
            "tx_type": "Sale (partial)" if "partial" in t else TYPE_MAP.get(t[0], t),
            "tx_code": t[0],
            "tx_date": m.group(2),
            "notification_date": m.group(3),
            "amount": amt_str,
            "amount_low": lo,
            "amount_high": hi,
            "description": " ".join(desc).strip() or None,
        })
    return out


def parse_ptr_pdf(path):
    text = pdf_text(path)
    if len(text.strip()) < 50:
        return None  # scanned / image-only
    return parse_ptr_text(text)


if __name__ == "__main__":
    import json, sys
    for p in sys.argv[1:]:
        print(json.dumps(parse_ptr_pdf(p), indent=1))
