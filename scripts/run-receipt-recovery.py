"""Inspect or perform one guarded receipt-1 recovery in the existing dev worker image."""

import argparse
import ast
import base64
import hashlib
import json
import lzma
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import boto3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check-model", action="store_true",
                        help="Read model metadata without sending an invoice or generating content")
    parser.add_argument("--execute", action="store_true",
                        help="Perform one receipt recovery attempt, using a saved readiness plan")
    parser.add_argument("--plan-file", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("refusing_to_overwrite_evidence")
    plan = None
    if args.execute:
        if not args.plan_file:
            raise ValueError("execute_requires_readiness_plan")
        plan = json.loads(args.plan_file.read_text(encoding="utf-8"))
        inspections = [x for x in plan.get("events", []) if x.get("event") == "RECEIPT_RECOVERY_INSPECTION"]
        if (plan.get("status") != "INSPECTED" or len(inspections) != 1
                or inspections[0].get("provider_metadata_probe") != {"performed": True, "available": True}):
            raise ValueError("invalid_readiness_plan")
    session = boto3.Session(region_name="ap-southeast-1")
    if session.client("sts").get_caller_identity()["Account"] != "179923444714":
        raise ValueError("wrong_aws_account")
    ecs, logs = session.client("ecs"), session.client("logs")
    service = ecs.describe_services(cluster="homewallet", services=["worker"])["services"][0]
    definition = ecs.describe_task_definition(taskDefinition=service["taskDefinition"])["taskDefinition"]
    if plan and plan["task_definition"] != definition["taskDefinitionArn"]:
        raise ValueError("worker_definition_changed_after_plan")
    container = definition["containerDefinitions"][0]
    log_options = container["logConfiguration"]["options"]
    source = Path(__file__).with_name("receipt-recovery-runtime.py").read_bytes()
    tree = ast.parse(source)
    if isinstance(tree.body[0], ast.Expr):
        tree.body.pop(0)
    payload = ast.unparse(tree).encode()
    encoded = base64.b64encode(lzma.compress(payload)).decode("ascii")
    boot = "import base64,lzma;exec(lzma.decompress(base64.b64decode('" + encoded + "')))"
    overrides = {"containerOverrides": [{"name": container["name"], "command": [
        "python", "-c", boot, "--receipt-id", "1", "--household-id", "1"]}]}
    if args.check_model:
        overrides["containerOverrides"][0]["command"].append("--check-model")
    if args.execute:
        overrides["containerOverrides"][0]["command"].extend([
            "--execute", "--expected-inspection-sha256", inspections[0]["inspection_sha256"]])
    if len(json.dumps(overrides)) >= 8192:
        raise ValueError("ecs_override_too_large")
    result = {"status": "RUNNING", "mode": "READ_ONLY_INSPECTION", "provider_metadata_check": args.check_model, "receipt_id": 1,
              "household_id": 1, "started_at": datetime.now(timezone.utc).isoformat(),
              "task_definition": definition["taskDefinitionArn"],
              "runtime_source_sha256": hashlib.sha256(source).hexdigest()}
    if args.execute:
        result.update(mode="CONTROLLED_RECOVERY", provider_metadata_check=True,
                      readiness_artifact=args.plan_file.name,
                      expected_inspection_sha256=inspections[0]["inspection_sha256"],
                      generation_limit=1, fallback_enabled=False)
    response = ecs.run_task(cluster="homewallet", taskDefinition=definition["taskDefinitionArn"],
                            launchType="FARGATE", count=1, clientToken=str(uuid.uuid4()),
                            networkConfiguration=service["networkConfiguration"],
                            startedBy="receipt1-recovery-execute" if args.execute else "receipt1-recovery-inspect", overrides=overrides)
    if response.get("failures") or len(response.get("tasks", [])) != 1:
        raise RuntimeError("inspection_task_launch_failed")
    task_arn = result["task_arn"] = response["tasks"][0]["taskArn"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"event": "RECEIPT_RECOVERY_TASK_STARTED", "mode": result["mode"],
                      "task_arn": task_arn}), flush=True)
    deadline = time.monotonic() + 300
    while True:
        task = ecs.describe_tasks(cluster="homewallet", tasks=[task_arn])["tasks"][0]
        if task["lastStatus"] == "STOPPED":
            result["exit_code"] = task["containers"][0].get("exitCode")
            result["image_digest"] = task["containers"][0].get("imageDigest")
            break
        if time.monotonic() > deadline:
            ecs.stop_task(cluster="homewallet", task=task_arn, reason="Receipt inspection bounded timeout")
            result["status"] = "TIMEOUT"
            args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
            raise RuntimeError("inspection_timeout")
        time.sleep(5)
    stream = "/".join([log_options["awslogs-stream-prefix"], container["name"],
                       task_arn.rsplit("/", 1)[-1]])
    result["events"] = []
    for attempt in range(8):
        try:
            events = logs.get_log_events(logGroupName=log_options["awslogs-group"],
                                         logStreamName=stream, startFromHead=True)["events"]
            for event in events:
                try:
                    entry = json.loads(event["message"])
                except ValueError:
                    continue
                if str(entry.get("event", "")).startswith("RECEIPT_RECOVERY_"):
                    result["events"].append(entry)
            if result["events"]:
                break
        except logs.exceptions.ResourceNotFoundException:
            pass
        time.sleep(2)
    inspection_count = sum(x.get("event") == "RECEIPT_RECOVERY_INSPECTION"
                           for x in result["events"])
    success_count = sum(x.get("event") == "RECEIPT_RECOVERY_SUCCEEDED" for x in result["events"])
    if args.execute:
        result["status"] = "RECOVERED_TO_DRAFT" if result.get("exit_code") == 0 and success_count == 1 else "FAILED"
    else:
        result["status"] = "INSPECTED" if result.get("exit_code") == 0 and inspection_count == 1 else "FAILED"
    result["completed_at"] = datetime.now(timezone.utc).isoformat()
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=True), flush=True)
    return 0 if result["status"] in {"INSPECTED", "RECOVERED_TO_DRAFT"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
