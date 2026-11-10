"""Read-only IAM check, optionally followed by one synthetic text invocation.

No pilot images, model text, credentials, or old pilot locks are read or changed.
"""

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, ProfileNotFound

from bedrock_access import profile_resources, simulate_inference_access, simulate_resource


ACCOUNT = "179923444714"
REGION = "ap-southeast-1"
MODEL = "apac.amazon.nova-lite-v1:0"
PROFILE_ARN = f"arn:aws:bedrock:{REGION}:{ACCOUNT}:inference-profile/{MODEL}"
PROMPT = "Return the text OK, and nothing else."


def synthetic_call(runtime):
    started = time.monotonic()
    response = runtime.converse(
        modelId=MODEL,
        messages=[{"role": "user", "content": [{"text": PROMPT}]}],
        inferenceConfig={"temperature": 0, "maxTokens": 8})
    text = "".join(x.get("text", "") for x in response.get("output", {}).get("message", {}).get("content", []))
    metadata = response.get("ResponseMetadata", {})
    usage = response.get("usage", {})
    return {"http_status": metadata.get("HTTPStatusCode"),
            "request_id": metadata.get("RequestId"),
            "latency_seconds": round(time.monotonic() - started, 3),
            "response_text_present": bool(text.strip()),
            "matches_synthetic_answer": text.strip() == "OK",
            "stop_reason": response.get("stopReason"),
            "input_tokens": usage.get("inputTokens"), "output_tokens": usage.get("outputTokens")}


def error_fields(exc):
    data = {"error_type": type(exc).__name__}
    if isinstance(exc, ClientError):
        metadata = exc.response.get("ResponseMetadata", {})
        error = exc.response.get("Error", {})
        message = error.get("Message", "").lower()
        data.update(aws_error_code=error.get("Code"), request_id=metadata.get("RequestId"),
                    http_status=metadata.get("HTTPStatusCode"),
                    explicit_deny="explicit deny" in message,
                    identity_policy_mentioned="identity-based policy" in message,
                    scp_mentioned="service control policy" in message)
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="homewallet-d3-pilot")
    parser.add_argument("--expected-user", choices=["hoang", "kien"], default="hoang")
    parser.add_argument("--simulate-user", choices=["hoang", "kien"])
    parser.add_argument("--invoke-synthetic", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = {"status": "STARTED", "started_utc": datetime.now(timezone.utc).isoformat(),
              "region": REGION, "model": MODEL, "pilot_images_sent": 0,
              "synthetic_requests_attempted": 0, "sdk_total_attempts": 1,
              "benchmark_status": "NOT_RUN"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Reserve the evidence file before any call. Reusing a filename cannot rerun inference.
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)

    def save():
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    try:
        config = Config(retries={"total_max_attempts": 1, "mode": "standard"},
                        connect_timeout=5, read_timeout=30)
        session = boto3.Session(profile_name=args.profile, region_name=REGION)
        identity = session.client("sts", config=config).get_caller_identity()
        expected = f"arn:aws:iam::{ACCOUNT}:user/{args.expected_user}"
        if identity.get("Account") != ACCOUNT or identity.get("Arn") != expected:
            raise ValueError("unexpected_aws_caller")
        result["caller_arn"] = identity["Arn"]
        principal = f"arn:aws:iam::{ACCOUNT}:user/{args.simulate_user or args.expected_user}"
        result["simulated_principal_arn"] = principal
        bedrock = session.client("bedrock", config=config)
        profile = bedrock.get_inference_profile(inferenceProfileIdentifier=MODEL)
        if profile.get("inferenceProfileArn") != PROFILE_ARN:
            raise ValueError("unexpected_profile_arn")
        resources = profile_resources(profile)
        result["iam_evaluations"] = simulate_inference_access(session.client("iam", config=config), principal, profile)
        result["iam_all_resources_allowed"] = all(x["allowed"] for x in result["iam_evaluations"])
        direct = next(x for x in resources[1:] if x.split(":")[3] == REGION)
        result["direct_model_without_profile"] = simulate_resource(session.client("iam", config=config), principal, direct)
        result["direct_model_without_profile_denied"] = result["direct_model_without_profile"]["decision"] in {"implicitDeny", "explicitDeny"}
        result["status"] = "PREFLIGHT_PASS" if result["iam_all_resources_allowed"] else "IAM_BLOCKED"
        if principal.endswith("/hoang") and not result["direct_model_without_profile_denied"]:
            result["status"] = "IAM_SCOPE_TOO_BROAD"
        save()
        if result["status"] != "PREFLIGHT_PASS":
            return 1
        if args.invoke_synthetic:
            result["synthetic_requests_attempted"] = 1
            result["invocation_scope"] = "hoang_live_identity" if args.expected_user == "hoang" else "kien_admin_connectivity_only"
            save()
            result["runtime"] = synthetic_call(session.client("bedrock-runtime", config=config))
            result["status"] = "LIVE_CALL_PASS" if result["runtime"]["http_status"] == 200 and result["runtime"]["response_text_present"] else "LIVE_CALL_FAILED"
        return 0 if result["status"] in {"PREFLIGHT_PASS", "LIVE_CALL_PASS"} else 1
    except ProfileNotFound as exc:
        result.update(status="BLOCKED_CREDENTIAL_PROFILE", error=error_fields(exc))
        return 1
    except Exception as exc:
        result.update(status="FAILED", error=error_fields(exc))
        return 1
    finally:
        result["completed_utc"] = datetime.now(timezone.utc).isoformat()
        save()
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
