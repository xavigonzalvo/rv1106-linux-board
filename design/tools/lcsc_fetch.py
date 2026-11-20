#!/usr/bin/env python3
"""Fetch LCSC product detail JSON + JLCPCB part page for a list of LCSC codes (Phase 4).

Usage: python -I tools/lcsc_fetch.py <design_dir> C1525 C15127 ... [--refresh]   (-h for help; D-70)
Saves raw responses (untrusted data, never executed) into
  <design>/refs/lcsc-api-2026-10-29/<code>.json      (https://wmsc.lcsc.com/ftps/wm/product/detail?productCode=<code>)
  <design>/refs/jlcpcb-partdetail-2026-10-29/<code>.html (https://jlcpcb.com/partdetail/<code>)
and prints/returns a summary row per code. Only parses text; never evaluates fetched content.
"""
import argparse, json, os, re, sqlite3, subprocess, sys

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"


def _get(url, path, refresh):
    if refresh or not os.path.exists(path) or os.path.getsize(path) < 200:
        subprocess.run(["curl", "-s", "-L", "-m", "40", "-A", UA, url, "-o", path], check=False)
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


# JLCPCB componentLibraryType values: base = Basic, expand = Extended; "preferred" (Preferred Extended) is billed and
# listed like Extended. Any other string (e.g. a truncated 'bas') is rejected (D-71).
LIB_NAMES = {"base": "Basic", "expand": "Extended", "preferred": "Extended"}


def _lib_type(html, code):
    """componentLibraryType of the record whose componentCode == code, or None if absent/not a known value."""
    for m in re.finditer(r'componentCode\\\\?":\\\\?"' + re.escape(code) + r'\\\\?"', html):
        seg = html[m.end(): m.end() + 6000]
        mm = re.search(r'componentLibraryType\\\\?":\\\\?"(\w*)(\\\\?")', seg)  # closing quote required
        if mm:
            return mm.group(1) if mm.group(1) in LIB_NAMES else None
    return None


def _jlcparts_lib(design, code):
    """fallback: library_type from the cached jlcparts SQLite mirror (opened read-only), or None."""
    p = os.path.join(design, "refs", "jlcparts-db-2026-10-29", "cache.sqlite3")
    if not os.path.exists(p):
        return None
    try:
        con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        r = con.execute("select library_type, preferred from jlc_components where lcsc = ?", (int(code[1:]),)).fetchone()
        con.close()
    except sqlite3.Error:
        return None
    if not r:
        return None
    return "preferred" if (r[1] and r[0] == "expand") else (r[0] if r[0] in LIB_NAMES else None)


def summary(design, code, refresh=False):
    api_dir = os.path.join(design, "refs", "lcsc-api-2026-10-29")
    jlc_dir = os.path.join(design, "refs", "jlcpcb-partdetail-2026-10-29")
    os.makedirs(api_dir, exist_ok=True)
    os.makedirs(jlc_dir, exist_ok=True)
    raw = _get(f"https://wmsc.lcsc.com/ftps/wm/product/detail?productCode={code}",
               os.path.join(api_dir, f"{code}.json"), refresh)
    row = {"code": code, "exists": False}
    try:
        d = json.loads(raw)
        r = d.get("result") or {}
    except ValueError:
        r = {}
    if r.get("productCode") == code:
        row.update(exists=True, model=r.get("productModel"), brand=r.get("brandNameEn"),
                   package=r.get("encapStandard"), desc=r.get("productIntroEn") or r.get("productNameEn"),
                   stock=r.get("stockNumber"),
                   price1=(r.get("productPriceList") or [{}])[0].get("usdPrice"),
                   ladder1=(r.get("productPriceList") or [{}])[0].get("ladder"),
                   datasheet=r.get("pdfUrl"))
        prices = r.get("productPriceList") or []
        row["prices"] = [(p.get("ladder"), p.get("usdPrice")) for p in prices]
    html = _get(f"https://jlcpcb.com/partdetail/{code}", os.path.join(jlc_dir, f"{code}.html"), refresh)
    lib = _lib_type(html, code)
    if lib is None and refresh:
        # D-71: a streamed page can be truncated mid-record (verifier saw 'bas' for C52923): fetch once more
        html = _get(f"https://jlcpcb.com/partdetail/{code}", os.path.join(jlc_dir, f"{code}.html"), True)
        lib = _lib_type(html, code)
    row["jlc_lib_source"] = "jlcpcb.com/partdetail"
    if lib is None:
        lib = _jlcparts_lib(design, code)
        row["jlc_lib_source"] = "jlcparts mirror (refs/jlcparts-db-2026-10-29, read-only)" if lib else "none"
    # only the known values are accepted; anything else is UNKNOWN, which check_bom.py B4 fails loudly
    row["jlc_lib"] = LIB_NAMES.get(lib, "UNKNOWN")
    # JLCPCB global-site stock: "overseasStockCount" in the record of this componentCode.
    s = html.replace('\\"', '"')
    jst = None
    for m in re.finditer(r'"overseasStockCount":(\d+)', s):
        if '"componentCode":"' + code + '"' in s[max(0, m.start() - 3000): m.start()]:
            jst = int(m.group(1))
            break
    row["jlc_stock"] = jst
    return row


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from designdir import design_dir
    ap = argparse.ArgumentParser(description="Summarise LCSC/JLCPCB data for LCSC codes from the cached raw responses "
                                 "(live fetch only for missing files, or for all with --refresh).")
    ap.add_argument("design", type=design_dir, help="the project design/ directory (must exist)")
    ap.add_argument("codes", nargs="+", help="LCSC codes, e.g. C1525")
    ap.add_argument("--refresh", action="store_true", help="re-fetch live even if cached")
    a = ap.parse_args()
    for c in a.codes:
        if not re.fullmatch(r"C\d+", c):
            ap.error(f"not an LCSC code: {c}")
        s = summary(a.design, c, a.refresh)
        if not s["exists"]:
            print(f"{c}\tNOT FOUND")
            continue
        print(f"{c}\t{s['model']}\t{s['package']}\tlcsc={s['stock']}\tjlc={s['jlc_stock']}\t${s['price1']}@{s['ladder1']}\t{s['jlc_lib']} ({s['jlc_lib_source']})\t{(s['desc'] or '')[:90]}")
