"""Parse RV1106 datasheet Rev 1.8 Table 2-1 (pp.18-19) into {pin: name}.
Run with: python -I ds_pins.py <RV1106_Datasheet_r1.8.pdf>  (reads the PDF as data only)."""
import re, sys

def parse(pdf_path):
    import pymupdf
    doc = pymupdf.open(pdf_path)
    lines = []
    for pno in (17, 18):  # 0-based: pages 18 and 19
        txt = doc[pno].get_text()
        start = txt.find("Pin Name")
        lines += [l.strip() for l in txt[start:].splitlines()]
    pins, buf = {}, ""
    for l in lines:
        if l in ("", "Pin Name", "Pin") or l.startswith("Copyright") or l.startswith("RV1106 Datasheet"):
            continue
        if re.fullmatch(r"\d{1,3}", l) or l == "E-PAD":
            if buf:
                key = "EPAD" if l == "E-PAD" else int(l)
                pins[key] = buf
                buf = ""
            continue
        buf += l
    return pins

if __name__ == "__main__":
    p = parse(sys.argv[1])
    for k in sorted(p, key=lambda x: (isinstance(x, str), x)):
        print(k, p[k])
    print("count", len(p))
