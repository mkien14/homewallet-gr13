import re
from datetime import datetime


DATE_FORMATS = [
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%Y-%m-%d",
    "%d/%m/%y",
    "%d-%m-%y",
    "%d %b %Y",
]


def parse_vnd(text):
    if text is None:
        return None
    value = re.sub(r"[^\d.,]", "", str(text))
    if not value:
        return None
    if re.search(r"[.,]\d{1,2}$", value):
        value = re.sub(r"[.,]\d{1,2}$", "", value)
    digits = re.sub(r"[.,]", "", value)
    return int(digits) if digits else None


def parse_date(text):
    if not text:
        return None
    value = str(text).strip()
    candidates = [value]
    if re.match(r"\d", value):
        first_part = value.split(" ")[0]
        if first_part != value:
            candidates.append(first_part)

    months = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    for candidate in candidates:
        for date_format in DATE_FORMATS:
            try:
                return datetime.strptime(candidate, date_format).date().isoformat()
            except ValueError:
                continue
        match = re.fullmatch(r"(\d{1,2}) ([A-Za-z]{3}) (\d{4})", candidate)
        if match:
            month = months.get(match[2].lower())
            if month is not None:
                try:
                    return datetime(
                        int(match[3]), month, int(match[1])
                    ).date().isoformat()
                except ValueError:
                    return None

    match = re.search(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})", value)
    if match:
        day, month, year = int(match[1]), int(match[2]), int(match[3])
        year += 2000 if year < 100 else 0
        try:
            return datetime(year, month, day).date().isoformat()
        except ValueError:
            return None
    return None
