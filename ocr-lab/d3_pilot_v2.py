"""New one-shot D3 paired pilot. Old pilot artifacts are never read or changed."""
import argparse
import csv
import json
import os
import pathlib
import re
import statistics
import sys
import time
from datetime import datetime, timezone

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from google import genai
from google.genai import types
from bedrock_access import simulate_inference_access

ROOT = pathlib.Path(__file__).resolve().parent
IDS = tuple(f"{n:03d}" for n in range(21, 31))
AWS_PROFILE = "homewallet-d3-pilot"
AWS_REGION = "ap-southeast-1"
AWS_MODEL = "apac.amazon.nova-lite-v1:0"
AWS_ACCOUNT = "179923444714"
AWS_USER_ARN = f"arn:aws:iam::{AWS_ACCOUNT}:user/hoang"
GEMINI_MODEL = "gemini-3.6-flash"
MAX_OUTPUT_TOKENS = 512
MAX_INPUT_TOKENS_PER_IMAGE = 40_000
GEMINI_GAP_SECONDS = 20
CEILING_USD = 0.50
RATES_USD_PER_MILLION = {
    # Conservative planning rates, not a provider quote or billing guarantee.
    "gemini": {"input": 0.75, "output": 3.75},
    "bedrock": {"input": 1.00, "output": 5.00},
}

ARTIFACT_DIR = ROOT / "out"
RUN_LOCK = ARTIFACT_DIR / "d3-pilot-v2-run.json"
REPORT = ARTIFACT_DIR / "d3-pilot-v2-report.json"
PREFLIGHT_REPORT = ARTIFACT_DIR / "d3-pilot-v2-preflight.json"
APPROVAL_FILE = ROOT / "d3-pilot-v2-preflight.json"

PROMPT = """Extract the Vietnamese receipt. Return exactly one JSON object with:
merchant: string or null; date: YYYY-MM-DD string or null; total: integer VND or null;
items: array of objects with description (string), quantity (number or null),
amount (integer VND or null). Use the final payable total. Receipt dates are
day/month/year. Convert thousands separators to integer VND. Include only priced
items. Do not guess; use null when unreadable. No markdown or explanation."""

OUTPUT_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "merchant": {"type": "STRING", "nullable": True},
        "date": {"type": "STRING", "nullable": True},
        "total": {"type": "INTEGER", "nullable": True},
        "items": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "description": {"type": "STRING"},
                    "quantity": {"type": "NUMBER", "nullable": True},
                    "amount": {"type": "INTEGER", "nullable": True},
                },
                "required": ["description", "quantity", "amount"],
            },
        },
    },
    "required": ["merchant", "date", "total", "items"],
}


class PilotError(RuntimeError):
    pass


def parse_response(payload):
    """Parse and validate a model response without retaining its contents."""
    errors = []
    data = payload
    if isinstance(payload, str):
        text = payload.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I).strip()
        try:
            data = json.loads(text)
        except (TypeError, json.JSONDecodeError):
            return None, ["invalid_json"]
    if not isinstance(data, dict):
        return None, ["root_not_object"]

    required = {"merchant", "date", "total", "items"}
    missing = sorted(required - data.keys())
    if missing:
        errors.extend(f"missing_{key}" for key in missing)
    if "merchant" in data and data["merchant"] is not None and not isinstance(data["merchant"], str):
        errors.append("merchant_type")
    if "date" in data and data["date"] is not None:
        if not isinstance(data["date"], str):
            errors.append("date_type")
        elif not re.fullmatch(r"\d{4}-\d{2}-\d{2}", data["date"]):
            errors.append("date_format")
        else:
            try:
                datetime.strptime(data["date"], "%Y-%m-%d")
            except ValueError:
                errors.append("date_value")
    if "total" in data and data["total"] is not None:
        if isinstance(data["total"], bool) or not isinstance(data["total"], int):
            errors.append("total_type")
    if "items" in data:
        if not isinstance(data["items"], list):
            errors.append("items_type")
        else:
            for index, item in enumerate(data["items"]):
                prefix = f"items_{index}"
                if not isinstance(item, dict):
                    errors.append(f"{prefix}_not_object")
                    continue
                for key in ("description", "quantity", "amount"):
                    if key not in item:
                        errors.append(f"{prefix}_missing_{key}")
                if "description" in item and not isinstance(item["description"], str):
                    errors.append(f"{prefix}_description_type")
                quantity = item.get("quantity")
                if quantity is not None and (isinstance(quantity, bool) or not isinstance(quantity, (int, float))):
                    errors.append(f"{prefix}_quantity_type")
                amount = item.get("amount")
                if amount is not None and (isinstance(amount, bool) or not isinstance(amount, int)):
                    errors.append(f"{prefix}_amount_type")
    return (data if not errors else None), errors


def sample_rows():
    with (ROOT / "labels.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = {pathlib.Path(r["file"]).stem: r for r in csv.DictReader(f)}
    samples = []
    for sid in IDS:
        row = rows.get(sid)
        image_path = ROOT / "data_small" / f"{sid}.jpg"
        if not row or row.get("split", "").strip() != "test":
            raise PilotError(f"Test label missing for {sid}")
        if row.get("source_detail", "").strip() != "Roboflow":
            raise PilotError(f"Approved source mismatch for {sid}")
        if not image_path.is_file():
            raise PilotError(f"Image missing for {sid}")
        samples.append((sid, row, image_path))
    return samples


def estimated_max_cost(provider):
    rates = RATES_USD_PER_MILLION[provider]
    return 10 * (
        MAX_INPUT_TOKENS_PER_IMAGE * rates["input"]
        + MAX_OUTPUT_TOKENS * rates["output"]
    ) / 1_000_000


def estimate_usage_cost(provider, input_tokens, output_tokens):
    rates = RATES_USD_PER_MILLION[provider]
    if input_tokens is None or output_tokens is None:
        return None
    return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000


def load_approval():
    if not APPROVAL_FILE.exists():
        raise PilotError(f"Preflight file missing: {APPROVAL_FILE.name}")
    approval = json.loads(APPROVAL_FILE.read_text(encoding="utf-8"))
    shared = approval.get("image_sharing", {})
    if (shared.get("confirmed") is not True
            or shared.get("sample_ids") != list(IDS)
            or set(shared.get("services", [])) != {"Google Gemini", "Amazon Bedrock"}
            or shared.get("source") != "Roboflow"):
        raise PilotError("Written sharing/source confirmation is incomplete or mismatched.")
    quota = approval.get("gemini_quota", {})
    return approval, quota


def quota_is_ready(quota):
    if quota.get("verified_in_ai_studio") is not True or quota.get("model") != GEMINI_MODEL:
        return False
    if not quota.get("checked_utc"):
        return False
    try:
        checked = datetime.fromisoformat(quota["checked_utc"].replace("Z", "+00:00"))
        rpm = int(quota.get("rpm", 0))
        remaining = int(quota.get("remaining_requests_today", 0))
    except (TypeError, ValueError):
        return False
    age_hours = (datetime.now(timezone.utc) - checked.astimezone(timezone.utc)).total_seconds() / 3600
    return (quota.get("api_key_project_matches") is True
            and 0 <= age_hours <= 24 and rpm >= 4 and remaining >= 10)


def verify_gemini_model():
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT.parent / ".env")
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise PilotError("GEMINI_API_KEY is missing (value is never displayed).")
    client = genai.Client(
        api_key=key,
        http_options=types.HttpOptions(
            timeout=30000,
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )
    try:
        exists = any(
            getattr(model, "name", "").removeprefix("models/") == GEMINI_MODEL
            for model in client.models.list()
        )
    except Exception as exc:
        raise PilotError(f"Gemini model-list preflight failed ({error_code(exc)}).") from exc
    finally:
        client.close()
    if not exists:
        raise PilotError(f"Gemini model is unavailable to the configured key: {GEMINI_MODEL}")
    return {"model_list": "available", "model": GEMINI_MODEL,
            "quota_confirmed_in_ai_studio": True}


def verify_aws_access():
    session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
    no_retry = Config(retries={"total_max_attempts": 1, "mode": "standard"})
    try:
        identity = session.client("sts", config=no_retry).get_caller_identity()
    except Exception as exc:
        raise PilotError(f"AWS STS identity check failed ({error_code(exc)}).") from exc
    if identity.get("Account") != AWS_ACCOUNT or identity.get("Arn") != AWS_USER_ARN:
        raise PilotError("AWS caller identity does not match the approved account and user.")

    bedrock = session.client("bedrock", config=no_retry)
    try:
        profile = bedrock.get_inference_profile(inferenceProfileIdentifier=AWS_MODEL)
    except Exception as exc:
        raise PilotError(f"Bedrock inference-profile check failed ({error_code(exc)}).") from exc
    if profile.get("status") != "ACTIVE":
        raise PilotError("Bedrock inference profile is not ACTIVE.")
    profile_arn = profile.get("inferenceProfileArn")
    resources = [profile_arn] + [m["modelArn"] for m in profile.get("models", [])]
    if not profile_arn or len(resources) < 2:
        raise PilotError("Bedrock inference profile returned no destination resources.")

    iam = session.client("iam", config=no_retry)
    try:
        evaluations = simulate_inference_access(iam, AWS_USER_ARN, profile)
    except Exception as exc:
        raise PilotError(
            f"IAM authorization simulation failed ({error_code(exc)}); "
            "the caller may lack iam:SimulatePrincipalPolicy."
        ) from exc
    if not all(item["allowed"] for item in evaluations):
        raise PilotError("IAM simulation did not allow bedrock:InvokeModel on every profile resource.")
    return {
        "identity": "verified",
        "profile_status": profile["status"],
        "profile_type": profile.get("type"),
        "invoke_policy_simulation": "allowed",
        "resources_checked": len(resources),
        "iam_evaluations": evaluations,
        "live_invocation_verified": False,
        "model": AWS_MODEL,
        "region": AWS_REGION,
    }, session


def simulation_allows_resources(simulation, resources):
    """Check each per-resource decision in SimulatePrincipalPolicy's response."""
    evaluations = simulation.get("EvaluationResults", [])
    resource_results = [
        item
        for evaluation in evaluations
        for item in evaluation.get("ResourceSpecificResults", [])
    ]
    if len(resource_results) != len(resources):
        return False
    decisions = {
        item.get("EvalResourceName"): item.get("EvalResourceDecision")
        for item in resource_results
    }
    return (set(decisions) == set(resources)
            and all(decisions.get(resource) == "allowed" for resource in resources))


def run_preflight():
    from pilot_run_guard import require_unconsumed_run
    try:
        require_unconsumed_run("d3-pilot-v2")
        run_authorized = True
    except RuntimeError:
        run_authorized = False
    approval, quota = load_approval()
    samples = sample_rows()
    gemini = verify_gemini_model()
    aws, _session = verify_aws_access()
    max_costs = {name: round(estimated_max_cost(name), 6) for name in RATES_USD_PER_MILLION}
    if any(amount > CEILING_USD for amount in max_costs.values()):
        raise PilotError("Conservative preflight cost estimate exceeds the per-provider ceiling.")
    result = {
        "checked_utc": datetime.now(timezone.utc).isoformat(),
        "sample_count": len(samples),
        "sample_ids": list(IDS),
        "sharing_approval": "confirmed for both providers and exact sample",
        "gemini": {**gemini, "quota": "verified" if quota_is_ready(quota) else "not verified"},
        "bedrock": aws,
        "max_cost_estimate_usd": max_costs,
        "cost_ceiling_each_usd": CEILING_USD,
        "run_identity": "d3-pilot-v2",
        "run_authorization": "UNCONSUMED" if run_authorized else "CONSUMED_OR_UNAPPROVED",
        "ready_to_run": run_authorized and quota_is_ready(quota),
    }
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    PREFLIGHT_REPORT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def merchant_match(predicted, expected):
    import unicodedata
    from rapidfuzz import fuzz

    def normalize(value):
        s = unicodedata.normalize("NFD", value or "")
        s = "".join(c for c in s if unicodedata.category(c) != "Mn")
        return s.lower().strip()

    p, e = normalize(predicted), normalize(expected)
    return bool(p) and (e in p or fuzz.ratio(e, p) >= 88)


def score_prediction(prediction, row):
    if prediction is None:
        return {"merchant_correct": False, "date_correct": None if row["date"].lower() == "none" else False,
                "total_correct": False, "items_count_correct": False}
    date_label = row["date"].strip()
    return {
        "merchant_correct": merchant_match(prediction["merchant"], row["merchant"]),
        "date_correct": None if date_label.lower() == "none" else prediction["date"] == date_label,
        "total_correct": prediction["total"] == int(row["total"]),
        "items_count_correct": len(prediction["items"]) == int(row["items_count"]),
    }


def call_gemini(client, image_bytes):
    start = time.monotonic()
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"), PROMPT],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=OUTPUT_SCHEMA,
            temperature=0,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        ),
    )
    parsed = getattr(response, "parsed", None)
    text = response.text or ""
    if parsed is not None:
        if hasattr(parsed, "model_dump"):
            parsed = parsed.model_dump()
        return parsed, {
            "input_tokens": getattr(response.usage_metadata, "prompt_token_count", None),
            "output_tokens": getattr(response.usage_metadata, "candidates_token_count", None),
            "latency_seconds": round(time.monotonic() - start, 3),
        }
    return text, {
        "input_tokens": getattr(response.usage_metadata, "prompt_token_count", None),
        "output_tokens": getattr(response.usage_metadata, "candidates_token_count", None),
        "latency_seconds": round(time.monotonic() - start, 3),
    }


def call_bedrock(client, image_bytes):
    start = time.monotonic()
    response = client.converse(
        modelId=AWS_MODEL,
        messages=[{"role": "user", "content": [
            {"image": {"format": "jpeg", "source": {"bytes": image_bytes}}},
            {"text": PROMPT},
        ]}],
        inferenceConfig={"temperature": 0, "maxTokens": MAX_OUTPUT_TOKENS},
    )
    text = "".join(block.get("text", "") for block in response["output"]["message"]["content"])
    return text, {
        "input_tokens": response.get("usage", {}).get("inputTokens"),
        "output_tokens": response.get("usage", {}).get("outputTokens"),
        "latency_seconds": round(time.monotonic() - start, 3),
        "stop_reason": response.get("stopReason"),
    }


def error_code(exc):
    if isinstance(exc, ClientError):
        return exc.response.get("Error", {}).get("Code", type(exc).__name__)
    status = getattr(exc, "code", None)
    if isinstance(status, (str, int)):
        return str(status)
    return type(exc).__name__


def update_artifacts(report, lock):
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    RUN_LOCK.write_text(json.dumps(lock, indent=2), encoding="utf-8")


def summarize_provider(calls, provider):
    provider_calls = [c for c in calls if c["provider"] == provider]
    attempted = [c for c in provider_calls if c["status"] != "skipped"]
    success = [c for c in attempted if c["status"] == "success"]
    schema_errors = sum(not c.get("schema_valid", False) for c in success)
    summary = {
        "requests_attempted": len(attempted),
        "successful_responses": len(success),
        "call_errors": sum(c["status"] == "call_error" for c in attempted),
        "schema_errors": schema_errors,
        "retry_count": 0,
    }
    for metric in ("merchant_correct", "date_correct", "total_correct", "items_count_correct"):
        considered = [c for c in provider_calls if metric != "date_correct" or c.get("date_in_label", True)]
        summary[metric] = {
            "correct": sum(bool(c.get(metric, False)) for c in considered),
            "evaluated": len(considered),
        }
    token_in = [c.get("input_tokens") for c in success]
    token_out = [c.get("output_tokens") for c in success]
    if all(v is not None for v in token_in + token_out):
        input_sum, output_sum = sum(token_in), sum(token_out)
        summary["usage"] = {"input_tokens": input_sum, "output_tokens": output_sum}
        summary["estimated_cost_usd"] = round(estimate_usage_cost(provider, input_sum, output_sum), 6)
    else:
        summary["usage"] = {"input_tokens": None, "output_tokens": None}
        summary["estimated_cost_usd"] = None
    latencies = [c["latency_seconds"] for c in attempted if c.get("latency_seconds") is not None]
    summary["latency_seconds"] = {
        "mean": round(sum(latencies) / len(latencies), 3) if latencies else None,
        "p50": round(statistics.median(latencies), 3) if latencies else None,
        "p95": round(sorted(latencies)[min(len(latencies) - 1, int(0.95 * len(latencies)))], 3) if latencies else None,
        "samples": len(latencies),
    }
    return summary


def execute_run():
    from pilot_run_guard import require_unconsumed_run
    try:
        require_unconsumed_run("d3-pilot-v2")
    except RuntimeError as exc:
        raise PilotError(str(exc)) from None
    if RUN_LOCK.exists() or REPORT.exists():
        raise PilotError("New-pilot v2 artifact already exists; this pilot cannot be rerun.")
    preflight = run_preflight()
    if not preflight["ready_to_run"]:
        raise PilotError("Preflight checks finished, but Gemini quota has not been confirmed in AI Studio.")

    approval, _ = load_approval()
    samples = sample_rows()
    gemini = genai.Client(
        api_key=os.environ["GEMINI_API_KEY"],
        http_options=types.HttpOptions(
            timeout=60000,
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )
    session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
    no_retry = Config(retries={"total_max_attempts": 1, "mode": "standard"})
    bedrock = session.client("bedrock-runtime", config=no_retry)
    state = {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "sample_ids": list(IDS), "retry_count": 0,
        "providers": {"gemini": {"attempts": 0}, "bedrock": {"attempts": 0}},
        "status": "started", "old_pilot_artifacts_modified": False,
        "approval_date": approval["image_sharing"]["confirmed_date"],
    }
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    with RUN_LOCK.open("x", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    report = {
        "started_utc": state["started_utc"], "completed_utc": None,
        "sample_ids": list(IDS), "sample_count": len(IDS),
        "gemini_model": GEMINI_MODEL, "bedrock_model": AWS_MODEL,
        "bedrock_region": AWS_REGION, "max_output_tokens": MAX_OUTPUT_TOKENS,
        "retry_count": 0, "cost_is_estimate": True,
        "planning_rates_usd_per_million": RATES_USD_PER_MILLION,
        "calls": [], "providers": {},
    }
    next_gemini_at = 0.0
    stopped = {"gemini": False, "bedrock": False}
    try:
        for sid, row, image_path in samples:
            image_bytes = image_path.read_bytes()
            row_date_known = row["date"].strip().lower() != "none"
            for provider in ("gemini", "bedrock"):
                if stopped[provider]:
                    report["calls"].append({"id": sid, "provider": provider, "status": "skipped",
                                            "reason": "provider_stopped_after_error",
                                            "date_in_label": row_date_known})
                    continue
                if provider == "gemini":
                    delay = next_gemini_at - time.monotonic()
                    if delay > 0:
                        time.sleep(delay)
                    started = time.monotonic()
                    next_gemini_at = started + GEMINI_GAP_SECONDS
                state["providers"][provider]["requests_attempted"] = (
                    state["providers"][provider].get("requests_attempted", 0) + 1
                )
                state["providers"][provider]["attempts"] = 1
                update_artifacts(report, state)
                try:
                    raw, meta = call_gemini(gemini, image_bytes) if provider == "gemini" else call_bedrock(bedrock, image_bytes)
                    prediction, validation_errors = parse_response(raw)
                    del raw
                    call = {"id": sid, "provider": provider, "status": "success",
                            "schema_valid": prediction is not None,
                            "schema_errors": validation_errors,
                            "date_in_label": row_date_known, **meta}
                    call.update(score_prediction(prediction, row))
                    call["usage_cost_estimate_usd"] = estimate_usage_cost(
                        provider, call.get("input_tokens"), call.get("output_tokens"))
                except Exception as exc:
                    code = error_code(exc)
                    call = {"id": sid, "provider": provider, "status": "call_error",
                            "error_code": code, "date_in_label": row_date_known,
                            "latency_seconds": round(time.monotonic() - started, 3)}
                    stopped[provider] = True
                report["calls"].append(call)
                report["providers"][provider] = summarize_provider(report["calls"], provider)
                update_artifacts(report, state)
                estimated = report["providers"][provider]["estimated_cost_usd"]
                if estimated is None and report["providers"][provider]["successful_responses"]:
                    stopped[provider] = True
                    state["providers"][provider]["stop_reason"] = "usage_unavailable_stop_for_budget"
                    update_artifacts(report, state)
                elif estimated is not None and estimated > CEILING_USD:
                    stopped[provider] = True
                    state["providers"][provider]["stop_reason"] = "estimated_cost_ceiling_reached"
                    update_artifacts(report, state)
        report["completed_utc"] = datetime.now(timezone.utc).isoformat()
        state["status"] = "complete_with_failures" if any(
            c["status"] == "call_error" or c["status"] == "skipped" or not c.get("schema_valid", True)
            for c in report["calls"]
        ) else "complete"
        for provider in RATES_USD_PER_MILLION:
            report["providers"][provider] = summarize_provider(report["calls"], provider)
        update_artifacts(report, state)
    except Exception as exc:
        state["status"] = "failed_rerun_forbidden"
        state["failure_type"] = type(exc).__name__
        update_artifacts(report, state)
        raise
    finally:
        gemini.close()
    print(f"New D3 pilot finished. Report: {REPORT.name}")
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true", help="Run read-only checks only; sends no images.")
    parser.add_argument("--run", action="store_true", help="Historical entrypoint; consumed runs are blocked before preflight.")
    args = parser.parse_args()
    if args.preflight == args.run:
        parser.error("choose exactly one of --preflight or --run")
    try:
        if args.preflight:
            report = run_preflight()
            print(json.dumps(report, indent=2))
            return 0 if report["ready_to_run"] else 2
        return execute_run()
    except Exception as exc:
        detail = str(exc) if isinstance(exc, PilotError) else f"{type(exc).__name__} ({error_code(exc)})"
        print(f"D3 v2 stopped before/while running: {detail}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
