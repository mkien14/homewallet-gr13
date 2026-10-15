import re
from datetime import datetime


def parse_vnd(text):
    if text is None:
        return None
    s = re.sub(r"[^\d.,]", "", str(text))
    if not s:
        return None
    if re.search(r"[.,]\d{1,2}$", s):          
        s = re.sub(r"[.,]\d{1,2}$", "", s)
    digits = re.sub(r"[.,]", "", s)
    return int(digits) if digits else None


DATE_FORMATS = ["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d",
                "%d/%m/%y", "%d-%m-%y", "%d %b %Y"]


def parse_date(text):
    if not text:
        return None
    t = str(text).strip().split(" ")[0] if re.match(r"\d", str(text).strip()) else str(text).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(t, fmt).date().isoformat()
        except ValueError:
            continue
    m = re.search(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})", str(text))
    if m:
        d, mo, y = int(m[1]), int(m[2]), int(m[3])
        y += 2000 if y < 100 else 0
        try:
            return datetime(y, mo, d).date().isoformat()
        except ValueError:
            return None
    return None