import json
import pathlib
import sys
import time

import boto3 

from common import parse_date, parse_vnd

REGION = "ap-southeast-1"
client = boto3.client("textract", region_name=REGION)
OUT = pathlib.Path("out/textract")
OUT.mkdir(parents=True, exist_ok=True)


def field(summary, wanted):
    for f in summary:
        if f["Type"]["Text"] == wanted:
            return f.get("ValueDetection", {}).get("Text")
    return None


def run(path):
    data = pathlib.Path(path).read_bytes()
    t0 = time.time()
    resp = client.analyze_expense(Document={"Bytes": data})
    elapsed = time.time() - t0
    stem = pathlib.Path(path).stem
    (OUT / f"{stem}.raw.json").write_text(
        json.dumps(resp, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    doc = resp["ExpenseDocuments"][0]
    summary = doc["SummaryFields"]
    items = []
    for grp in doc.get("LineItemGroups", []):
        for li in grp["LineItems"]:
            row = {f["Type"]["Text"]: f.get("ValueDetection", {}).get("Text")
                   for f in li["LineItemExpenseFields"]}
            items.append(row)

    pred = {
        "merchant": field(summary, "VENDOR_NAME"),
        "date": parse_date(field(summary, "INVOICE_RECEIPT_DATE")),
        "total": parse_vnd(field(summary, "TOTAL") or field(summary, "AMOUNT_DUE")),
        "items_count": len(items),
        "seconds": round(elapsed, 2),
    }
    (OUT / f"{stem}.pred.json").write_text(
        json.dumps(pred, ensure_ascii=False, indent=1), encoding="utf-8")
    return pred, items


if __name__ == "__main__":
    for p in sys.argv[1:]:
        try:
            pred, items = run(p)
            print(p, json.dumps(pred, ensure_ascii=False))
            for it in items[:5]:
                print("   ", json.dumps(it, ensure_ascii=False))
        except Exception as e:
            print(p, "LỖI:", type(e).__name__, e)