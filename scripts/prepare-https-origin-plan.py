"""Write nonsecret Terraform inputs for HTTPS phase 1, preserving deployed images.

This only reads AWS metadata. It does not create resources or read secret values.
Do not use this bootstrap helper after the stack has been promoted to production.
"""
import argparse
import json
import re
from pathlib import Path

import boto3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="Local .tfvars.json file, outside Git")
    parser.add_argument("--profile")
    args = parser.parse_args()
    session = boto3.Session(profile_name=args.profile, region_name="ap-southeast-1")
    account = session.client("sts").get_caller_identity()["Account"]
    if account != "179923444714":
        raise ValueError("Wrong account")
    ecs = session.client("ecs")
    service = ecs.describe_services(cluster="homewallet", services=["api"])["services"][0]
    api_task = ecs.describe_task_definition(taskDefinition=service["taskDefinition"])["taskDefinition"]
    api = next(container for container in api_task["containerDefinitions"] if container["name"] == "api")
    env = {item["name"]: item["value"] for item in api.get("environment", [])}
    if env.get("APP_ENV") == "production":
        raise ValueError("Already production; use the reviewed release inputs instead")
    migrate = ecs.describe_task_definition(taskDefinition="hw-migrate")["taskDefinition"]["containerDefinitions"][0]
    worker_service = ecs.describe_services(cluster="homewallet", services=["worker"])["services"][0]
    worker = ecs.describe_task_definition(taskDefinition=worker_service["taskDefinition"])["taskDefinition"]["containerDefinitions"][0]
    jobs = ecs.describe_task_definition(taskDefinition="hw-jobs")["taskDefinition"]["containerDefinitions"][0]

    def reviewed_image(image):
        prefix = re.escape(account + ".dkr.ecr.ap-southeast-1.amazonaws.com/homewallet-backend")
        if not re.fullmatch(prefix + r"(?:@sha256:[a-f0-9]{64}|:[A-Za-z0-9_][A-Za-z0-9_.-]{0,127})", image):
            raise ValueError("Expected same-account backend ECR image tag or digest")
        return image

    if not env.get("GEMINI_MODEL"):
        raise ValueError("Missing existing model configuration")
    payload = {"enable_api_https_gateway": True, "api_image_uri": reviewed_image(api["image"]),
               "worker_image_uri": reviewed_image(worker["image"]), "jobs_image_uri": reviewed_image(jobs["image"]),
               "migrate_image_uri": reviewed_image(migrate["image"]), "gemini_model": env["GEMINI_MODEL"]}
    path = Path(args.output)
    if path.exists():
        raise ValueError("Refusing to overwrite existing operator inputs")
    if not path.name.endswith(".tfvars.json"):
        raise ValueError("Output must end with .tfvars.json")
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({"status": "INPUTS_WRITTEN", "fields": sorted(payload)}))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"status": "FAILED", "error_type": type(exc).__name__}))
        raise SystemExit(1)
