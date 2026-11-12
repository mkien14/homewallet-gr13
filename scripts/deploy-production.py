"""Manually approved release only; no Terraform apply, migrations or secret output."""
import datetime
import json
import os
import re
import time
import urllib.request
import urllib.parse
from pathlib import Path

import boto3


def required(key):
    value = os.environ.get(key, "").strip()
    if not value:
        raise RuntimeError(f"Missing required configuration: {key}")
    return value


def main():
    commit, digest = required("RELEASE_COMMIT"), required("RELEASE_DIGEST")
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise RuntimeError("Invalid immutable release identity")
    account = required("PROD_ACCOUNT_ID")
    if boto3.client("sts").get_caller_identity()["Account"] != account:
        raise RuntimeError("Production account mismatch")
    image = f"{account}.dkr.ecr.ap-southeast-1.amazonaws.com/homewallet-prod-backend@{digest}"
    ecr, ecs, sqs = boto3.client("ecr"), boto3.client("ecs"), boto3.client("sqs")
    elb = boto3.client("elbv2")
    details = ecr.describe_images(repositoryName="homewallet-prod-backend", imageIds=[{"imageDigest": digest}])["imageDetails"][0]
    if f"sha-{commit}" not in details.get("imageTags", []):
        raise RuntimeError("ECR digest has no matching reviewed source SHA tag")
    scan = ecr.describe_image_scan_findings(repositoryName="homewallet-prod-backend", imageId={"imageDigest": digest})
    if scan["imageScanStatus"]["status"] != "COMPLETE":
        raise RuntimeError("A completed ECR vulnerability scan is required")
    counts = scan.get("imageScanFindings", {}).get("findingSeverityCounts", {})
    if counts.get("CRITICAL", 0) or counts.get("HIGH", 0):
        raise RuntimeError("Release blocked by high/critical image vulnerabilities")
    # Promotion must also verify OCI source labels/attestation; see readiness runbook.
    review = required("COMPATIBILITY_REVIEW")
    url = required("PROD_URL").rstrip("/")
    parsed_url = urllib.parse.urlsplit(url)
    if parsed_url.scheme != "https" or parsed_url.path or parsed_url.query or parsed_url.fragment or parsed_url.username:
        raise RuntimeError("Smoke URL must use HTTPS")
    token = required("SMOKE_TOKEN")
    distribution_id = required("CLOUDFRONT_DISTRIBUTION_ID")
    distribution = boto3.client("cloudfront").get_distribution(Id=distribution_id)["Distribution"]
    if distribution["DomainName"] != parsed_url.netloc or distribution["DistributionConfig"].get("Comment") != "homewallet-prod frontend and API":
        raise RuntimeError("Smoke URL/distribution is not the isolated production frontend")
    queue = required("PROD_QUEUE_URL")
    if not queue.startswith(f"https://sqs.ap-southeast-1.amazonaws.com/{account}/homewallet-prod-"):
        raise RuntimeError("Queue is not an isolated production queue")
    cluster = "homewallet-prod"
    record = {"commit": commit, "digest": digest, "migration_version": required("MIGRATION_VERSION"),
              "compatibility_review": review, "cloudfront_distribution": distribution_id,
              "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(), "services": {}}
    path = Path("production-release-record.json")

    def save():
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")

    def register(base, container):
        task = ecs.describe_task_definition(taskDefinition=base)["taskDefinition"]
        if task["family"] != f"homewallet-prod-{container}":
            raise RuntimeError("Unexpected task family")
        if task["executionRoleArn"] != f"arn:aws:iam::{account}:role/homewallet-prod-task-execution-role":
            raise RuntimeError("Unexpected execution role")
        role_name = "weekly-report" if container == "jobs" else container
        if task.get("taskRoleArn") != f"arn:aws:iam::{account}:role/homewallet-prod-{role_name}-task-role":
            raise RuntimeError("Unexpected task role")
        if len(task["containerDefinitions"]) != 1 or task["containerDefinitions"][0]["name"] != container:
            raise RuntimeError("Unexpected task container layout")
        for definition in task["containerDefinitions"]:
            if any(not secret["valueFrom"].startswith(f"arn:aws:secretsmanager:ap-southeast-1:{account}:secret:hw/prod/") for secret in definition.get("secrets", [])):
                raise RuntimeError("Task secrets must belong to production")
            if definition["name"] == container:
                definition["image"] = image
        allowed = {"family", "taskRoleArn", "executionRoleArn", "networkMode", "containerDefinitions", "volumes",
                   "placementConstraints", "requiresCompatibilities", "cpu", "memory", "runtimePlatform", "ephemeralStorage"}
        return ecs.register_task_definition(**{k: v for k, v in task.items() if k in allowed})["taskDefinition"]["taskDefinitionArn"]

    def rollout(service):
        current = ecs.describe_services(cluster=cluster, services=[service])["services"][0]
        old = current["taskDefinition"]
        previous = ecs.describe_task_definition(taskDefinition=old)["taskDefinition"]
        record["services"][service] = {"previous_task_definition": old,
                                         "previous_images": [c["image"] for c in previous["containerDefinitions"]]}
        save()
        new = register(old, service)
        record["services"][service]["new_task_definition"] = new
        save()
        ecs.update_service(cluster=cluster, service=service, taskDefinition=new)
        ecs.get_waiter("services_stable").wait(cluster=cluster, services=[service])
        active = ecs.describe_services(cluster=cluster, services=[service])["services"][0]
        if active["taskDefinition"] != new or active["runningCount"] < (2 if service == "api" else 1):
            raise RuntimeError("Circuit breaker rollback or insufficient healthy tasks")
        arns = ecs.list_tasks(cluster=cluster, serviceName=service, desiredStatus="RUNNING")["taskArns"]
        tasks = ecs.describe_tasks(cluster=cluster, tasks=arns)["tasks"]
        tasks = [task for task in tasks if task["taskDefinitionArn"] == new]
        if not tasks or any(c.get("imageDigest") != digest for task in tasks for c in task["containers"] if c["name"] == service):
            raise RuntimeError("Running image digest does not match reviewed release")
        if service == "api":
            if len({task.get("availabilityZone") for task in tasks} - {None}) < 2:
                raise RuntimeError("API tasks must run in two availability zones")
            group = active["loadBalancers"][0]["targetGroupArn"]
            health = elb.describe_target_health(TargetGroupArn=group)["TargetHealthDescriptions"]
            if sum(item["TargetHealth"]["State"] == "healthy" for item in health) < 2:
                raise RuntimeError("ALB requires two healthy production targets")

    def smoke():
        for endpoint, bearer in [("/api/health", None), ("/api/ready", None), ("/api/me", token)]:
            headers = {"Authorization": f"Bearer {bearer}"} if bearer else {}
            with urllib.request.urlopen(urllib.request.Request(url + endpoint, headers=headers), timeout=10) as response:
                if response.status != 200:
                    raise RuntimeError("Production smoke failed")
                body = json.load(response)
                if endpoint.endswith("/me") and not body.get("user"):
                    raise RuntimeError("Authenticated test principal missing")

    save()
    rollout("api")
    smoke()
    # Pause uploads externally under the recorded change ticket before this gate.
    for _ in range(3):
        attrs = sqs.get_queue_attributes(QueueUrl=queue, AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible", "ApproximateNumberOfMessagesDelayed"])["Attributes"]
        if any(int(value) for value in attrs.values()):
            raise RuntimeError("Worker rollout blocked: queue must drain with uploads paused")
        time.sleep(20)
    rollout("worker")
    scheduler = boto3.client("scheduler")
    names = scheduler.list_schedules(GroupName="homewallet-prod-jobs")["Schedules"]
    if len(names) != 3:
        raise RuntimeError("Expected three isolated disabled schedules")
    jobs = register("homewallet-prod-jobs", "jobs")
    record["jobs_task_definition"] = jobs
    save()
    for item in names:
        schedule = scheduler.get_schedule(Name=item["Name"], GroupName="homewallet-prod-jobs")
        if schedule["State"] != "DISABLED":
            raise RuntimeError("Scheduled jobs must remain disabled until separate SES review")
        record.setdefault("previous_job_tasks", {})[item["Name"]] = schedule["Target"]["EcsParameters"]["TaskDefinitionArn"]
        save()
        schedule["Target"]["EcsParameters"]["TaskDefinitionArn"] = jobs
        allowed = {"Name", "GroupName", "ScheduleExpression", "StartDate", "EndDate", "Description", "ScheduleExpressionTimezone", "State", "KmsKeyArn", "Target", "FlexibleTimeWindow", "ActionAfterCompletion"}
        scheduler.update_schedule(**{k: v for k, v in schedule.items() if k in allowed})
    smoke()
    record["status"] = "verified"
    save()


if __name__ == "__main__":
    main()
