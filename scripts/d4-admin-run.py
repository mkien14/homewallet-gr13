"""Run isolated D4 AC3 and bounded read-only load against dev.

Requires boto3 and requests. Credentials and tokens stay in process memory.
The sanitized result is written to a local JSON path supplied by --output.
"""

import argparse
import concurrent.futures
import json
import math
import secrets
import statistics
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import boto3
import requests


ACCOUNT = "179923444714"
REGION = "ap-southeast-1"
POOL = "ap-southeast-1_9mOMUx9Ds"
CLIENT = "5h1qm7tdm4ksbrd8bv9ltcmsma"
BASE = "https://daoedidcrnf1f.cloudfront.net"
QUEUE_NAMES = ("receipts-queue", "receipts-dlq")


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def api(method, path, token=None, body=None):
    headers = {"Cache-Control": "no-cache"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    start = time.perf_counter()
    response = requests.request(
        method, BASE + path, headers=headers, json=body, timeout=15
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    request_id = response.headers.get("x-request-id")
    if not request_id and isinstance(payload, dict):
        request_id = payload.get("error", {}).get("request_id")
    return response.status_code, payload, round(elapsed_ms, 2), request_id


def percentile(values, percent):
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent / 100
    lo = math.floor(position)
    hi = math.ceil(position)
    return round(ordered[lo] + (ordered[hi] - ordered[lo]) * (position - lo), 2)


def queue_snapshot(sqs, urls):
    result = {"time_utc": utc_now()}
    for name, url in urls.items():
        attributes = sqs.get_queue_attributes(
            QueueUrl=url,
            AttributeNames=[
                "ApproximateNumberOfMessages",
                "ApproximateNumberOfMessagesNotVisible",
            ],
        )["Attributes"]
        result[name] = {
            "visible": int(attributes.get("ApproximateNumberOfMessages", "0")),
            "inflight": int(
                attributes.get("ApproximateNumberOfMessagesNotVisible", "0")
            ),
        }
    return result


def run_load(token, sqs, urls, baseline, seconds):
    stop = threading.Event()
    statuses = Counter()
    latencies = []
    errors = []
    snapshots = [baseline]
    lock = threading.Lock()
    start = time.monotonic()
    start_utc = utc_now()

    def client():
        while not stop.is_set() and time.monotonic() - start < seconds:
            try:
                code, _, ms, _ = api(
                    "GET", "/api/dashboard?period=2026-11", token
                )
                with lock:
                    statuses[str(code)] += 1
                    latencies.append(ms)
                if code >= 500:
                    errors.append(f"HTTP {code}")
                    stop.set()
            except requests.RequestException as exc:
                with lock:
                    errors.append(type(exc).__name__)
                stop.set()
            stop.wait(2.0)

    def monitor():
        previous_main = baseline["receipts-queue"]["visible"]
        previous_dlq = baseline["receipts-dlq"]["visible"]
        consecutive_rises = 0
        while not stop.wait(15.0) and time.monotonic() - start < seconds:
            try:
                snap = queue_snapshot(sqs, urls)
                with lock:
                    snapshots.append(snap)
                main = snap["receipts-queue"]["visible"]
                dlq = snap["receipts-dlq"]["visible"]
                if dlq > previous_dlq:
                    errors.append("DLQ visible increased")
                    stop.set()
                if main > previous_main:
                    consecutive_rises += 1
                else:
                    consecutive_rises = 0
                if consecutive_rises >= 2:
                    errors.append("main queue visible increased twice")
                    stop.set()
                previous_main, previous_dlq = main, dlq
            except Exception as exc:
                errors.append(f"queue monitor: {type(exc).__name__}")
                stop.set()

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(client) for _ in range(5)]
        future_monitor = pool.submit(monitor)
        for future in futures:
            future.result()
        stop.set()
        future_monitor.result()

    snapshots.append(queue_snapshot(sqs, urls))
    return {
        "start_utc": start_utc,
        "end_utc": utc_now(),
        "duration_seconds": round(time.monotonic() - start, 2),
        "max_clients": 5,
        "request_interval_seconds_per_client": 2,
        "requests": sum(statuses.values()),
        "statuses": dict(statuses),
        "network_errors": errors,
        "latency_ms": {
            "sample_count": len(latencies),
            "p50": percentile(latencies, 50),
            "p95": percentile(latencies, 95),
            "min": min(latencies, default=None),
            "max": max(latencies, default=None),
            "mean": round(statistics.mean(latencies), 2) if latencies else None,
        },
        "queue_snapshots": snapshots,
        "stopped_early": time.monotonic() - start < seconds - 2,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--seconds", type=int, default=120)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 120:
        raise SystemExit("--seconds must be between 1 and 120")

    session = boto3.Session(region_name=REGION)
    sts = session.client("sts")
    identity = sts.get_caller_identity()
    if identity["Account"] != ACCOUNT:
        raise SystemExit("AWS account does not match dev")
    cognito = session.client("cognito-idp")
    sqs = session.client("sqs")
    urls = {name: sqs.get_queue_url(QueueName=name)["QueueUrl"] for name in QUEUE_NAMES}
    result = {
        "started_utc": utc_now(),
        "account": ACCOUNT,
        "region": REGION,
        "caller_arn": identity["Arn"],
        "endpoint": BASE,
        "fixture": {},
        "ac3": [],
        "cleanup": [],
    }
    email_prefix = "d4-kien-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    emails = [f"{email_prefix}.test{i}@example.com" for i in (1, 2)]
    tokens = {}
    created_users = []
    households = {}
    receipt_id = None
    try:
        for index, email in enumerate(emails, 1):
            password = "Aa1!" + secrets.token_urlsafe(24)
            # Track the identity before authentication so cleanup also covers a
            # partial setup failure after Cognito accepted creation.
            cognito.admin_create_user(
                UserPoolId=POOL,
                Username=email,
                UserAttributes=[
                    {"Name": "email", "Value": email},
                    {"Name": "email_verified", "Value": "true"},
                ],
                MessageAction="SUPPRESS",
            )
            created_users.append((index, email))
            cognito.admin_set_user_password(
                UserPoolId=POOL, Username=email, Password=password, Permanent=True
            )
            auth = cognito.initiate_auth(
                ClientId=CLIENT,
                AuthFlow="USER_PASSWORD_AUTH",
                AuthParameters={"USERNAME": email, "PASSWORD": password},
            )
            tokens[index] = auth["AuthenticationResult"]["AccessToken"]
            result["fixture"][f"user_{index}"] = email
            print(f"Created isolated D4 user {index}", flush=True)

        code, payload, _, rid = api("GET", "/api/ping")
        result["ping"] = {"status": code, "request_id": rid}
        if code != 200 or payload.get("message") != "pong":
            raise RuntimeError("API ping preflight failed")

        for index in (1, 2):
            code, payload, _, _ = api("GET", "/api/me", tokens[index])
            if code != 200 or payload.get("household"):
                raise RuntimeError(f"user {index} profile preflight failed")
            code, payload, _, _ = api(
                "POST", "/api/households", tokens[index],
                {"name": f"D4 isolated {email_prefix} H{index}"},
            )
            if code != 201 or not payload.get("id"):
                raise RuntimeError(f"household {index} creation failed: HTTP {code}")
            households[index] = int(payload["id"])
            result["fixture"][f"household_{index}_id"] = households[index]
            print(f"Created isolated D4 household {index}", flush=True)
        if households[1] == households[2]:
            raise RuntimeError("test users share a household")

        code, payload, _, _ = api(
            "POST", "/api/receipts", tokens[1],
            {"content_type": "image/jpeg", "size": 1000},
        )
        if code != 201 or not payload.get("receipt", {}).get("id"):
            raise RuntimeError(f"test receipt creation failed: HTTP {code}")
        receipt_id = int(payload["receipt"]["id"])
        result["fixture"]["receipt_id"] = receipt_id
        print("Created isolated D4 receipt metadata", flush=True)

        cases = [
            ("no_token_me", "GET", "/api/me", None, 401),
            ("cross_household_members", "GET", f"/api/households/{households[1]}/members", tokens[2], 404),
            ("cross_household_receipt", "GET", f"/api/receipts/{receipt_id}", tokens[2], 404),
            ("same_household_members", "GET", f"/api/households/{households[1]}/members", tokens[1], 200),
        ]
        for name, method, path, token, expected in cases:
            code, _, _, rid = api(method, path, token)
            result["ac3"].append({
                "case": name, "expected": expected, "actual": code,
                "pass": code == expected, "request_id": rid,
            })
            print(f"AC3 {name}: HTTP {code}", flush=True)
        if not all(case["pass"] for case in result["ac3"]):
            raise RuntimeError("AC3 case failed; load was not run")

        code, _, _, rid = api("GET", "/api/dashboard?period=2026-11", tokens[1])
        result["dashboard_preflight"] = {"status": code, "request_id": rid}
        if code != 200:
            raise RuntimeError(f"dashboard preflight HTTP {code}; load was not run")
        baseline = queue_snapshot(sqs, urls)
        print(f"Load started: 5 clients, at most {args.seconds}s", flush=True)
        result["load"] = run_load(tokens[1], sqs, urls, baseline, args.seconds)
        print("Load finished", flush=True)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        print(f"D4 halted: {type(exc).__name__}", flush=True)
    finally:
        if receipt_id and 1 in tokens:
            try:
                code, _, _, rid = api("DELETE", f"/api/receipts/{receipt_id}", tokens[1])
                result["cleanup"].append({"object": "receipt", "id": receipt_id, "status": code, "request_id": rid})
            except Exception as exc:
                result["cleanup"].append({"object": "receipt", "error": type(exc).__name__})
        for index in (1, 2):
            if index in households and index in tokens:
                try:
                    code, _, _, rid = api(
                        "POST", f"/api/households/{households[index]}/delete",
                        tokens[index], {"confirm": True, "household_id": households[index]},
                    )
                    result["cleanup"].append({"object": "household", "id": households[index], "status": code, "request_id": rid})
                except Exception as exc:
                    result["cleanup"].append({"object": "household", "id": households[index], "error": type(exc).__name__})
        for index, email in created_users:
            try:
                cognito.admin_delete_user(UserPoolId=POOL, Username=email)
                result["cleanup"].append({"object": "cognito_user", "index": index, "deleted": True})
            except Exception as exc:
                result["cleanup"].append({"object": "cognito_user", "index": index, "error": type(exc).__name__})
        result["finished_utc"] = utc_now()
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Sanitized result: {output}", flush=True)
    if "error" in result:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
