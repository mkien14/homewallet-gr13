"""One-shot, privacy-minimizing paired OCR pilot for images 021-030."""
import csv
import json
import os
import pathlib
import re
import sys
import time
from datetime import datetime, timezone

import boto3
from botocore.config import Config
from dotenv import load_dotenv
from google import genai
from google.genai import types

ROOT = pathlib.Path(__file__).resolve().parent
os.chdir(ROOT)
load_dotenv(ROOT.parent / ".env")
load_dotenv(ROOT / ".env")

IDS = tuple(f"{n:03d}" for n in range(21, 31))
AWS_PROFILE = "homewallet-d3-pilot"
AWS_REGION = "ap-southeast-1"
AWS_MODEL = "apac.amazon.nova-lite-v1:0"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
LOCK = ROOT / "out" / "d3-pilot-run.json"
RESULT = ROOT / "out" / "d3-pilot-report.json"
MAX_OUTPUT_TOKENS = 256
MAX_INPUT_TOKENS_ESTIMATE = 45_000
CEILING_USD = 0.50
# Deliberately conservative planning rates per million tokens. These are
# ceilings for the preflight estimate, not a claim about the final bill.
RATES = {
    "gemini": {"input": 0.75, "output": 3.75},
    "bedrock": {"input": 1.00, "output": 5.00},
}

PROMPT = """Read this Vietnamese receipt. Return only JSON matching:
{"merchant": string|null, "date": "YYYY-MM-DD"|null, "total": integer|null,
 "items": [{"description": string, "quantity": number|null, "amount": integer|null}]}
Use the final payable total in VND. Dates on receipts are day/month/year.
Convert thousands separators in VND to an integer. Include only priced items.
Do not guess; use null when unreadable. Return no explanation."""


def load_pilot():
    with (ROOT / "labels.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = {pathlib.Path(r["file"]).stem: r for r in csv.DictReader(f)}
    samples = []
    for sid in IDS:
        row = rows.get(sid)
        image = ROOT / "data_small" / f"{sid}.jpg"
        if not row or row["split"].strip() != "test":
            raise RuntimeError(f"Missing test label for {sid}")
        if row.get("source_detail", "").strip() != "Roboflow":
            raise RuntimeError(f"Unexpected source for pilot image {sid}")
        if not image.is_file():
            raise RuntimeError(f"Missing pilot image {sid}")
        samples.append((sid, row, image.read_bytes()))
    return samples


def parse_response(text):
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            return None
        if set(("merchant", "date", "total", "items")) - set(data):
            return None
        return data
    except (TypeError, json.JSONDecodeError):
        return None


def expected_cost(provider):
    rates = RATES[provider]
    return 10 * (MAX_INPUT_TOKENS_ESTIMATE * rates["input"] + MAX_OUTPUT_TOKENS * rates["output"]) / 1_000_000


def usage_cost(provider, results):
    rates = RATES[provider]
    input_tokens = sum(x["input_tokens"] or 0 for x in results)
    output_tokens = sum(x["output_tokens"] or 0 for x in results)
    return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000


def merchant_match(pred, label):
    import unicodedata
    from rapidfuzz import fuzz

    def norm(value):
        value = unicodedata.normalize("NFD", value or "")
        value = "".join(c for c in value if unicodedata.category(c) != "Mn")
        return value.lower().strip()

    p, e = norm(str(pred or "")), norm(label)
    return bool(p) and (e in p or fuzz.ratio(e, p) >= 88)


def score(pred, row):
    if pred is None:
        return {"schema_valid": False, "merchant_correct": False,
                "date_correct": None if row["date"].strip().lower() == "none" else False,
                "total_correct": False, "items_count_correct": False}
    date_label = row["date"].strip()
    items = pred.get("items")
    total = pred.get("total")
    date_pred = pred.get("date")
    return {
        "schema_valid": isinstance(pred.get("merchant"), (str, type(None)))
            and isinstance(date_pred, (str, type(None)))
            and isinstance(total, (int, type(None)))
            and isinstance(items, list),
        "merchant_correct": merchant_match(pred.get("merchant"), row["merchant"]),
        "date_correct": None if date_label.lower() == "none" else date_pred == date_label,
        "total_correct": total == int(row["total"]),
        "items_count_correct": isinstance(items, list) and len(items) == int(row["items_count"]),
    }


def invoke_gemini(client, image):
    start = time.monotonic()
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[types.Part.from_bytes(data=image, mime_type="image/jpeg"), PROMPT],
        config=types.GenerateContentConfig(
            response_mime_type="application/json", temperature=0,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        ),
    )
    usage = response.usage_metadata
    return response.text or "", {
        "input_tokens": getattr(usage, "prompt_token_count", None),
        "output_tokens": getattr(usage, "candidates_token_count", None),
        "latency_seconds": round(time.monotonic() - start, 3),
    }


def invoke_bedrock(client, image):
    start = time.monotonic()
    response = client.converse(
        modelId=AWS_MODEL,
        messages=[{"role": "user", "content": [
            {"image": {"format": "jpeg", "source": {"bytes": image}}},
            {"text": PROMPT},
        ]}],
        inferenceConfig={"temperature": 0, "maxTokens": MAX_OUTPUT_TOKENS},
    )
    text = "".join(part.get("text", "") for part in response["output"]["message"]["content"])
    usage = response.get("usage", {})
    return text, {
        "input_tokens": usage.get("inputTokens"),
        "output_tokens": usage.get("outputTokens"),
        "latency_seconds": round(time.monotonic() - start, 3),
    }


def main():
    if LOCK.exists():
        raise RuntimeError(f"One-shot guard exists ({LOCK}); this pilot must never be rerun.")
    samples = load_pilot()
    for provider in RATES:
        if expected_cost(provider) > CEILING_USD:
            raise RuntimeError(f"Conservative {provider} estimate exceeds USD 0.50.")
    if not os.getenv("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY is missing; no inference was sent.")

    session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
    sts = session.client("sts", config=Config(retries={"total_max_attempts": 1, "mode": "standard"}))
    identity = sts.get_caller_identity()
    if identity.get("Account") != "179923444714" or not identity.get("Arn", "").endswith(":user/hoang"):
        raise RuntimeError("AWS identity does not match the approved pilot identity.")
    bedrock = session.client("bedrock", config=Config(retries={"total_max_attempts": 1, "mode": "standard"}))
    profile = bedrock.get_inference_profile(inferenceProfileIdentifier=AWS_MODEL)
    if profile.get("status") != "ACTIVE":
        raise RuntimeError("Bedrock inference profile is not ACTIVE.")

    gemini = genai.Client(
        api_key=os.environ["GEMINI_API_KEY"],
        http_options=types.HttpOptions(
            timeout=60000,
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )
    runtime = session.client("bedrock-runtime", config=Config(
        retries={"total_max_attempts": 1, "mode": "standard"}))

    # Permanently consume the one-shot authorization before the first inference.
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    state = {"started_utc": datetime.now(timezone.utc).isoformat(), "sample_ids": list(IDS),
             "providers": {"gemini": {"attempts": 0}, "bedrock": {"attempts": 0}},
             "status": "started", "region": AWS_REGION, "bedrock_profile": AWS_MODEL,
             "gemini_model": GEMINI_MODEL}
    with LOCK.open("x", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

    report = {"started_utc": state["started_utc"], "sample_ids": list(IDS),
              "region": AWS_REGION, "bedrock_profile": AWS_MODEL,
              "gemini_model": GEMINI_MODEL, "retry_count": 0,
              "cost_is_estimate": True, "providers": {}}
    try:
        for provider in ("gemini", "bedrock"):
            results = []
            state["providers"][provider]["attempts"] = 1
            with LOCK.open("w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            for sid, row, image in samples:
                state["providers"][provider]["requests_attempted"] = (
                    state["providers"][provider].get("requests_attempted", 0) + 1
                )
                with LOCK.open("w", encoding="utf-8") as f:
                    json.dump(state, f, indent=2)
                raw, meta = invoke_gemini(gemini, image) if provider == "gemini" else invoke_bedrock(runtime, image)
                pred = parse_response(raw)
                results.append({"id": sid, **score(pred, row), **meta})
                del raw, pred
                # Flush after each call so partial progress and usage survive a failure.
                report["providers"][provider] = {
                    "requests_sent": len(results),
                    "estimated_cost_usd": round(usage_cost(provider, results), 6),
                    "conservative_preflight_ceiling_usd": round(expected_cost(provider), 6),
                    "usage": {"input_tokens": sum(x["input_tokens"] or 0 for x in results),
                              "output_tokens": sum(x["output_tokens"] or 0 for x in results)},
                    "results": results,
                }
                RESULT.write_text(json.dumps(report, indent=2), encoding="utf-8")
                if usage_cost(provider, results) > CEILING_USD:
                    raise RuntimeError(f"{provider} usage estimate exceeded USD 0.50; stopping without retry.")
            state["providers"][provider]["status"] = "complete"
            with LOCK.open("w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        report["completed_utc"] = datetime.now(timezone.utc).isoformat()
        state["status"] = "complete"
    except Exception as exc:
        state["status"] = "failed; rerun forbidden"
        state["failure_type"] = type(exc).__name__
        with LOCK.open("w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        raise
    finally:
        gemini.close()
    RESULT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    with LOCK.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    print(f"Completed one-shot pilot. Report: {RESULT}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Pilot stopped: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
