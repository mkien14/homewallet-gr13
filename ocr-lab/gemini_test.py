import json
import os
import pathlib
import re
import sys
import time

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

from common import parse_date, parse_vnd

os.chdir(pathlib.Path(__file__).resolve().parent)
load_dotenv()

client = genai.Client(
    api_key=os.environ["GEMINI_API_KEY"],
    http_options=types.HttpOptions(timeout=60000),  # 60 giây
)
MODEL = os.environ["GEMINI_MODEL"]
OUT = pathlib.Path("out/gemini")
OUT.mkdir(parents=True, exist_ok=True)

MIN_INTERVAL = 13   # giây giữa hai yêu cầu (gói miễn phí: 5 yêu cầu/phút)
MAX_TRIES = 6

PROMPT = """Bạn đọc ảnh hóa đơn tại Việt Nam. Trả về DUY NHẤT một JSON đúng schema:
{
  "merchant": "tên cửa hàng, giữ nguyên chữ và dấu như in trên hóa đơn",
  "date": "YYYY-MM-DD hoặc null",
  "total": số nguyên VND là tổng thanh toán cuối cùng, hoặc null,
  "items": [{"description": "...", "quantity": số hoặc null, "amount": số nguyên VND}]
}
Quy tắc:
- Ngày trên hóa đơn theo thứ tự ngày/tháng/năm.
- Số tiền Việt Nam dùng dấu chấm hoặc phẩy ngăn nghìn: "245.000" hay "245,000" đều là 245000.
- Chỉ đưa vào "items" những dòng hàng CÓ GIÁ. Bỏ qua dòng phụ kiện, ghi chú không có giá.
- Không đoán. Nếu không đọc được, trả null.
- Không thêm lời giải thích."""


def wait_time(err, attempt):
    """Đọc thời gian chờ Google gợi ý; nếu không có thì chờ tăng dần."""
    m = re.search(r"retry in ([\d.]+)\s*(ms|s)", str(err), re.I)
    if m:
        v = float(m.group(1)) / (1000 if m.group(2).lower() == "ms" else 1)
        return v + 2
    return 10 * attempt


def call_model(img_bytes):
    for attempt in range(1, MAX_TRIES + 1):
        t0 = time.time()
        try:
            resp = client.models.generate_content(
                model=MODEL,
                contents=[types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"), PROMPT],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", temperature=0),
            )
            return resp, time.time() - t0
        except errors.APIError as e:
            code = getattr(e, "code", None)
            if "PerDay" in str(e):
                print("  Hết hạn mức THEO NGÀY, dừng. Chạy lại sau hoặc đổi mô hình/gói.")
                sys.exit(1)
            if code in (429, 503) and attempt < MAX_TRIES:
                w = wait_time(e, attempt)
                print(f"  {code}, chờ {w:.0f}s rồi thử lại ({attempt}/{MAX_TRIES})")
                time.sleep(w)
                continue
            raise


def run(path):
    p = pathlib.Path(path)
    resp, elapsed = call_model(p.read_bytes())
    (OUT / f"{p.stem}.raw.txt").write_text(resp.text or "", encoding="utf-8")
    try:
        d = json.loads(resp.text)
    except Exception:
        d = {}
    pred = {
        "merchant": d.get("merchant"),
        "date": parse_date(d.get("date")),
        "total": parse_vnd(d.get("total")),
        "items_count": len(d.get("items") or []),
        "seconds": round(elapsed, 2),  # chỉ tính lần gọi thành công, không tính thời gian chờ
    }
    (OUT / f"{p.stem}.pred.json").write_text(
        json.dumps(pred, ensure_ascii=False, indent=1), encoding="utf-8")
    return pred


if __name__ == "__main__":
    force = "--force" in sys.argv
    paths = [a for a in sys.argv[1:] if not a.startswith("--")]
    last = 0.0
    for path in paths:
        stem = pathlib.Path(path).stem
        if not force and (OUT / f"{stem}.pred.json").exists():
            print(stem, "đã có kết quả, bỏ qua")
            continue
        gap = MIN_INTERVAL - (time.time() - last)
        if gap > 0:
            time.sleep(gap)
        last = time.time()
        try:
            print(stem, json.dumps(run(path), ensure_ascii=False))
        except Exception as e:
            print(stem, "LỖI:", type(e).__name__, str(e)[:200])