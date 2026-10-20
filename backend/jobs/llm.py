import json
import os
import re
import time

from google import genai
from google.genai import errors, types


MAX_TRIES = 6
MIN_INTERVAL = 13
_last_request_at = 0.0

PROMPT = """Bạn đọc ảnh hóa đơn tại Việt Nam. Trả về DUY NHẤT một JSON đúng schema:
{
  "merchant": "tên cửa hàng, giữ nguyên chữ và dấu như in trên hóa đơn",
  "date": "YYYY-MM-DD hoặc null",
  "total": số nguyên VND là tổng thanh toán cuối cùng, hoặc null,
  "items": [{
    "description": "...",
    "quantity": số hoặc null,
    "unit_price": số nguyên VND hoặc null,
    "amount": số nguyên VND,
    "category": "tên danh mục phù hợp nhất trong danh sách hoặc null"
  }]
}
Quy tắc:
- Ngày trên hóa đơn theo thứ tự ngày/tháng/năm.
- Số tiền Việt Nam dùng dấu chấm hoặc phẩy ngăn nghìn: "245.000" hay "245,000" đều là 245000.
- Chỉ đưa vào "items" những dòng hàng CÓ GIÁ. Bỏ qua dòng phụ kiện, ghi chú không có giá.
- Chỉ chọn category từ danh sách danh mục được cung cấp. Nếu không phù hợp, trả null.
- Không đoán. Nếu không đọc được, trả null.
- Không thêm lời giải thích."""


def wait_time(error, attempt):
    match = re.search(r"retry in ([\d.]+)\s*(ms|s)", str(error), re.I)
    if match:
        delay = float(match.group(1))
        if match.group(2).lower() == "ms":
            delay /= 1000
        return delay + 2
    return 10 * attempt


def extract_invoice(image_bytes, mime_type, category_names, *, client=None, sleep=None):
    api_key = os.getenv("GEMINI_API_KEY")
    model = os.getenv("GEMINI_MODEL")
    if not api_key:
        raise ValueError("Set GEMINI_API_KEY to process a receipt")
    if not model:
        raise ValueError("Set GEMINI_MODEL to process a receipt")

    client = client or genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=20_000),
    )
    sleep = sleep or time.sleep
    categories = ", ".join(category_names) if category_names else "không có danh mục"
    prompt = f"{PROMPT}\nDanh sách danh mục:\n{categories}"

    for attempt in range(1, MAX_TRIES + 1):
        global _last_request_at
        now = time.monotonic()
        if _last_request_at:
            remaining = MIN_INTERVAL - (now - _last_request_at)
            if remaining > 0:
                sleep(remaining)
        _last_request_at = time.monotonic()
        try:
            response = client.models.generate_content(
                model=model,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                    prompt,
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0,
                ),
            )
            if not response.text:
                raise ValueError("Gemini returned an empty receipt response")
            result = json.loads(response.text)
            if not isinstance(result, dict):
                raise ValueError("Gemini receipt response must be a JSON object")
            return result
        except errors.APIError as exc:
            code = getattr(exc, "code", None)
            if code not in (429, 503) or attempt == MAX_TRIES:
                raise
            sleep(wait_time(exc, attempt))
        except json.JSONDecodeError as exc:
            raise ValueError("Gemini returned invalid JSON for the receipt") from exc

    raise RuntimeError("Gemini request exhausted retries")
