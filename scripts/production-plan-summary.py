"""Redact a plan and bind releases to reviewed immutable task revisions.

Only images and APP_RELEASE may change during an application release. Other
task/infrastructure changes must be applied separately before a fresh plan.
Environment values and full container definitions are never exported.
"""
import argparse
import copy
import json
import re
import sys


TASKS = {
    "module.compute.aws_ecs_task_definition.api": "api",
    "module.compute.aws_ecs_task_definition.worker": "worker",
    "module.compute.aws_ecs_task_definition.jobs": "jobs",
}
COMPUTED = {"arn", "arn_without_revision", "id", "revision"}


def has_unknown(value):
    if isinstance(value, dict):
        return any(has_unknown(item) for item in value.values())
    if isinstance(value, list):
        return any(has_unknown(item) for item in value)
    return value is True


def normalize(value, *, commit, expected_image=None):
    result = copy.deepcopy(value)
    for key in COMPUTED:
        result.pop(key, None)
    # ECS/provider reads include defaults omitted by equivalent HCL. Normalize
    # only documented defaults, keeping all actual runtime changes visible.
    for key in ("ipc_mode", "pid_mode", "tags", "volume", "placement_constraints", "proxy_configuration", "inference_accelerator"):
        if not result.get(key):
            result.pop(key, None)
    if not result.get("enable_fault_injection"):
        result.pop("enable_fault_injection", None)
    containers = json.loads(result.pop("container_definitions"))
    if not isinstance(containers, list) or len(containers) != 1:
        raise ValueError("Unexpected task container layout")
    for container in containers:
        container.setdefault("essential", True)
        if container.get("cpu") == 0:
            container.pop("cpu")
        for key in ("mountPoints", "systemControls", "volumesFrom", "portMappings", "secrets"):
            if not container.get(key):
                container.pop(key, None)
        for mapping in container.get("portMappings", []):
            mapping.setdefault("protocol", "tcp")
            if result.get("network_mode") == "awsvpc" and not mapping.get("hostPort"):
                mapping["hostPort"] = mapping["containerPort"]
        image = container.pop("image")
        if expected_image and image != expected_image:
            raise ValueError("Planned task image differs from reviewed digest")
        environment = container.get("environment", [])
        releases = [item for item in environment if item.get("name") == "APP_RELEASE"]
        if expected_image and len(releases) != 1:
            raise ValueError("Production service task must identify APP_RELEASE")
        if len(releases) > 1 or (expected_image and releases and releases[0].get("value") != commit):
            raise ValueError("Planned APP_RELEASE differs from reviewed source")
        container["environment"] = sorted((item for item in environment if item.get("name") != "APP_RELEASE"), key=lambda item: item["name"])
        if "secrets" in container:
            container["secrets"].sort(key=lambda item: item["name"])
    result["containers"] = containers
    return result


def summarize(plan, commit, digest):
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError("Invalid release identity")
    variables = plan.get("variables", {})
    account = variables.get("expected_account_id", {}).get("value", "")
    if not re.fullmatch(r"[0-9]{12}", account):
        raise ValueError("Plan must identify the production AWS account")
    if variables.get("release_digest", {}).get("value") != digest:
        raise ValueError("Plan digest differs from release input")
    if variables.get("release_commit", {}).get("value") != commit:
        raise ValueError("Plan commit differs from release input")
    image = f"{account}.dkr.ecr.ap-southeast-1.amazonaws.com/homewallet-prod-backend@{digest}"
    changes, tasks = [], {}
    for item in plan.get("resource_changes", []):
        address, change = item["address"], item["change"]
        actions = change["actions"]
        entry = {"address": address, "actions": actions}
        if address in TASKS:
            before, after = change.get("before"), change.get("after")
            image_only = False
            unknown = {k: v for k, v in change.get("after_unknown", {}).items() if k not in COMPUTED}
            try:
                if before and after and not has_unknown(unknown):
                    image_only = normalize(before, commit=commit) == normalize(after, commit=commit, expected_image=image)
            except (KeyError, TypeError, ValueError):
                pass
            entry["release_changes_only"] = image_only
            if before and image_only:
                tasks[TASKS[address]] = {"task_definition": before["arn"]}
        if actions != ["no-op"]:
            changes.append(entry)
    return {"schema_version": 2, "commit": commit, "digest": digest, "account": account,
            "changes": changes, "tasks": tasks}


def require_review(review, commit, digest, account=None):
    if review.get("schema_version") != 2 or review.get("commit") != commit or review.get("digest") != digest:
        raise ValueError("Plan review is missing or belongs to a different release")
    account = account or review.get("account", "")
    if review.get("account") != account or not re.fullmatch(r"[0-9]{12}", account):
        raise ValueError("Plan review belongs to a different AWS account")
    for item in review.get("changes", []):
        if item.get("address") not in TASKS or item.get("release_changes_only") is not True:
            raise ValueError("Apply and review non-release infrastructure/task changes before release")
        if item.get("actions") not in (["update"], ["delete", "create"], ["create", "delete"]):
            raise ValueError("Unexpected task change action")
    tasks = review.get("tasks", {})
    families = {"api": "api", "worker": "worker", "jobs": "jobs"}
    if set(tasks) != set(families):
        raise ValueError("Review must contain all three existing production service/job task revisions")
    for name, suffix in families.items():
        arn = tasks[name].get("task_definition", "")
        if not re.fullmatch(f"arn:aws:ecs:ap-southeast-1:{account}:task-definition/homewallet-prod-{suffix}:[1-9][0-9]*", arn):
            raise ValueError("Unexpected reviewed production task revision")
    return review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--digest", required=True)
    parser.add_argument("--check", help="Validate a previously redacted plan review")
    args = parser.parse_args()
    if args.check:
        with open(args.check, encoding="utf-8") as handle:
            require_review(json.load(handle), args.commit, args.digest)
        print("Reviewed image/APP_RELEASE-only plan accepted.")
    else:
        print(json.dumps(summarize(json.load(sys.stdin), args.commit, args.digest), indent=2))


if __name__ == "__main__":
    main()
