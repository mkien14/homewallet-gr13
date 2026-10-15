import csv
import json
import os
import pathlib
import sys
import unicodedata

from rapidfuzz import fuzz

os.chdir(pathlib.Path(__file__).resolve().parent)


def strip_accents(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D").lower().strip()


def norm(s):
    return unicodedata.normalize("NFC", s or "").lower().strip()


def merchant_ok(pred, label):
    p = strip_accents(pred).replace("\n", " ")
    l = strip_accents(label)
    return bool(p) and (l in p or fuzz.ratio(l, p) >= 88)


def has_accent(label):
    return strip_accents(label) != norm(label)


def evaluate(method, split, verbose=False):
    rows = [r for r in csv.DictReader(open("labels.csv", encoding="utf-8-sig"))
            if r["split"].strip() == split]
    n = tot = dat = mer = missing = 0
    n_acc = acc = 0
    secs = []
    for r in rows:
        stem = pathlib.Path(r["file"].strip()).stem
        f = pathlib.Path("out") / method / f"{stem}.pred.json"
        if not f.exists():
            missing += 1
            if verbose:
                print(f"  [{method}] {r['file']}: KHÔNG có file kết quả")
            continue
        n += 1
        p = json.loads(f.read_text(encoding="utf-8"))
        exp_total = int(r["total"].strip())
        label_m = r["merchant"].strip()
        m = p.get("merchant") or ""
        ok_t = p.get("total") == exp_total
        ok_d = p.get("date") == r["date"].strip()
        ok_m = merchant_ok(m, label_m)
        tot += ok_t
        dat += ok_d
        mer += ok_m
        if has_accent(label_m):
            n_acc += 1
            acc += norm(label_m) in norm(m).replace("\n", " ")
        secs.append(p.get("seconds", 0))
        if verbose:
            print(f"  [{method}] {r['file']}")
            print(f"     tổng    : nhãn={exp_total!r}  dự đoán={p.get('total')!r}  {'ĐÚNG' if ok_t else 'sai'}")
            print(f"     ngày    : nhãn={r['date'].strip()!r}  dự đoán={p.get('date')!r}  {'ĐÚNG' if ok_d else 'sai'}")
            print(f"     cửa hàng: nhãn={label_m!r}  dự đoán={m!r}  {'ĐÚNG' if ok_m else 'sai'}")
    pct = lambda x, d: f"{100 * x / d:5.1f}%" if d else "  n/a"
    if secs:
        print(f"{method:10s} [{split}] n={n} (thiếu {missing})  tổng={pct(tot, n)}  ngày={pct(dat, n)}  "
              f"cửa hàng={pct(mer, n)}  đúng dấu={pct(acc, n_acc)} (trên {n_acc} ảnh có dấu)  "
              f"TB={sum(secs) / len(secs):.1f}s")
    else:
        print(f"{method}: chưa có kết quả")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    split = args[0] if args else "dev"
    verbose = "-v" in sys.argv
    for m in ("textract", "gemini"):
        evaluate(m, split, verbose)