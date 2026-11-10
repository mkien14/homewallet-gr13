"""Run bounded dev API/job acceptance with temporary identities and no email.

Tokens, passwords, invite codes, and synthetic email addresses are never written
to the result. Scheduled jobs keep their existing disabled state. The runtime
harness uses explicit fixture selectors and an in-memory email capture sink.
"""

import argparse
import ast
import base64
import hashlib
import json
import lzma
import secrets
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import boto3
import requests


ACCOUNT = "179923444714"
REGION = "ap-southeast-1"
POOL = "ap-southeast-1_9mOMUx9Ds"
CLIENT = "5h1qm7tdm4ksbrd8bv9ltcmsma"
BASE = "https://daoedidcrnf1f.cloudfront.net"


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def progress(event, **fields):
    print(json.dumps({"event": event, "at_utc": now(), **fields}), flush=True)


def require(condition, label):
    if not condition:
        raise RuntimeError(label)


class Runner:
    def __init__(self, result, *, runtime_source=None, event_prefix="CHI43", checkpoint=None):
        self.result = result
        self.event_prefix = event_prefix
        self.checkpoint = checkpoint or (lambda: None)
        session = boto3.Session(region_name=REGION)
        self.cognito = session.client("cognito-idp")
        self.ecs = session.client("ecs")
        self.logs = session.client("logs")
        identity = session.client("sts").get_caller_identity()
        require(identity["Account"] == ACCOUNT, "wrong_aws_account")
        self.result["account"] = identity["Account"]
        service = self.ecs.describe_services(cluster="homewallet", services=["api"])["services"][0]
        require(service["taskDefinition"].endswith("/hw-api:21"), "review_changed_api_task_definition")
        self.task_definition = service["taskDefinition"]
        self.runtime_container = "api"
        self.runtime_log_group = "/ecs/hw-api"
        self.runtime_log_prefix = "api"
        self.network = service["networkConfiguration"]
        self.source = (Path(runtime_source) if runtime_source else
                       Path(__file__).with_name("chi43-fixture-runtime.py")).read_bytes()
        tree = ast.parse(self.source)
        # Fit ECS's override limit by removing comments/module documentation.
        if tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, ast.Constant) and isinstance(tree.body[0].value.value, str):
            tree.body.pop(0)
        self.payload = ast.unparse(tree).encode("utf-8")
        self.result["runtime_source_sha256"] = hashlib.sha256(self.source).hexdigest()
        self.result["runtime_payload_sha256"] = hashlib.sha256(self.payload).hexdigest()

    def api(self, case, method, path, token=None, body=None, expected=200):
        headers = {"Cache-Control": "no-cache"}
        if token:
            headers["Authorization"] = "Bearer " + token
        response = requests.request(method, BASE + path, headers=headers, json=body, timeout=20)
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        entry = {"case": case, "method": method, "path": path,
                 "status": response.status_code, "expected": expected,
                 "request_id": response.headers.get("X-Request-Id"),
                 "pass": response.status_code == expected}
        self.result["api"].append(entry)
        self.checkpoint()
        progress(self.event_prefix + "_API_RESULT", **entry)
        require(entry["pass"], "api_" + case + "_unexpected_status")
        return payload

    def runtime(self, mode, fixture=None, *, admin=False, extra_args=None):
        encoded = base64.b64encode(lzma.compress(self.payload, preset=9)).decode("ascii")
        boot = "import base64,lzma;exec(lzma.decompress(base64.b64decode('" + encoded + "')))"
        command = ["python", "-c", boot, mode]
        if fixture:
            for flag, key in [("--run-id", "run_id"), ("--household-id", "household_id"),
                              ("--vi-user-id", "vi_user_id"), ("--en-user-id", "en_user_id")]:
                command.extend([flag, str(fixture[key])])
        command.extend(extra_args or [])
        task_definition = "hw-db-runtime-bootstrap:2" if admin else self.task_definition
        container_name = "bootstrap" if admin else self.runtime_container
        log_group = "/ecs/hw-db-runtime-bootstrap" if admin else self.runtime_log_group
        log_prefix = "bootstrap" if admin else self.runtime_log_prefix
        environment = ([{"name": "VAPID_CLAIMS_SUB", "value": "mailto:homewallet26@gmail.com"}]
                       if self.event_prefix == "CHI43" else [])
        overrides = {"containerOverrides": [{"name": container_name, "command": command,
            "environment": environment}]}
        require(len(json.dumps(overrides)) < 8192, "ecs_override_size_exceeded")
        response = self.ecs.run_task(cluster="homewallet", taskDefinition=task_definition,
            launchType="FARGATE", count=1, clientToken=str(uuid.uuid4()),
            startedBy=self.event_prefix.lower() + "-runtime-" + mode, networkConfiguration=self.network, overrides=overrides)
        require(not response.get("failures") and len(response.get("tasks", [])) == 1, "runtime_task_launch_failed")
        task_arn = response["tasks"][0]["taskArn"]
        record = {"mode": mode, "task_arn": task_arn, "task_definition": task_definition,
                  "credential_role": "bootstrap_admin" if admin else "runtime",
                  "log_group": log_group,
                  "log_stream": log_prefix + "/" + container_name + "/" + task_arn.rsplit("/", 1)[-1]}
        self.result["runtime_tasks"].append(record)
        self.checkpoint()
        progress(self.event_prefix + "_RUNTIME_STARTED", mode=mode, task_arn=task_arn)
        started = time.monotonic()
        last_status = None
        while True:
            task = self.ecs.describe_tasks(cluster="homewallet", tasks=[task_arn])["tasks"][0]
            if task["lastStatus"] != last_status:
                last_status = task["lastStatus"]
                progress(self.event_prefix + "_RUNTIME_STATUS", mode=mode, status=last_status)
            if last_status == "STOPPED":
                record["exit_code"] = task["containers"][0].get("exitCode")
                record["image"] = task["containers"][0].get("image")
                record["image_digest"] = task["containers"][0].get("imageDigest")
                break
            if time.monotonic() - started > 300:
                self.ecs.stop_task(cluster="homewallet", task=task_arn, reason="Bounded " + self.event_prefix + " acceptance timeout")
                raise RuntimeError("runtime_timeout_" + mode)
            time.sleep(4)
        events = []
        for attempt in range(6):
            try:
                messages = self.logs.get_log_events(logGroupName=record["log_group"],
                    logStreamName=record["log_stream"], startFromHead=True)["events"]
                for message in messages:
                    try:
                        value = json.loads(message["message"])
                    except ValueError:
                        continue
                    if str(value.get("event", "")).startswith(self.event_prefix + "_"):
                        events.append(value)
                if events:
                    break
            except self.logs.exceptions.ResourceNotFoundException:
                pass
            if attempt < 5:
                time.sleep(2)
        record["events"] = events
        self.checkpoint()
        for event in events:
            progress(self.event_prefix + "_RUNTIME_EVENT", mode=mode, details=event)
        require(record.get("exit_code") == 0, "runtime_task_failed_" + mode)
        return events


def execute(args, result):
    runner = Runner(result)
    if args.seed_only:
        result["seed"] = runner.runtime("seed-browser")
        return
    flows = runner.cognito.describe_user_pool_client(UserPoolId=POOL, ClientId=CLIENT)["UserPoolClient"]["ExplicitAuthFlows"]
    require("ALLOW_USER_PASSWORD_AUTH" in flows, "dev_test_client_flow_unavailable")
    tokens, created = {}, []
    fixture = {"run_id": result["run_id"]}
    result["fixture"] = fixture
    ready = False
    try:
        for locale in ("vi", "en"):
            username = "chi43-" + result["run_id"] + "." + locale + "@example.com"
            password = "Aa1!" + secrets.token_urlsafe(32)
            runner.cognito.admin_create_user(UserPoolId=POOL, Username=username,
                UserAttributes=[{"Name": "email", "Value": username},
                    {"Name": "email_verified", "Value": "true"},
                    {"Name": "custom:preferred_locale", "Value": locale}], MessageAction="SUPPRESS")
            created.append(username)
            runner.cognito.admin_set_user_password(UserPoolId=POOL, Username=username, Password=password, Permanent=True)
            auth = runner.cognito.initiate_auth(ClientId=CLIENT, AuthFlow="USER_PASSWORD_AUTH",
                AuthParameters={"USERNAME": username, "PASSWORD": password})
            tokens[locale] = auth["AuthenticationResult"]["AccessToken"]
            profile = runner.api("fixture_profile_" + locale, "GET", "/api/me", tokens[locale])
            require(not profile.get("household"), "new_fixture_user_has_household")
            fixture[locale + "_user_id"] = int(profile["user"]["id"])
            runner.api("fixture_locale_" + locale, "PATCH", "/api/me", tokens[locale], {"preferred_locale": locale})
        household = runner.api("fixture_household_create", "POST", "/api/households", tokens["vi"],
                               {"name": "CHI43 runtime " + result["run_id"]}, expected=201)
        fixture["household_id"] = int(household["id"])
        joined = runner.api("fixture_member_join", "POST", "/api/households/join", tokens["en"],
                            {"invite_code": household["invite_code"]})
        require(joined["id"] == fixture["household_id"], "fixture_join_mismatch")
        ready = True
        runner.api("notifications_anonymous", "GET", "/api/notifications?limit=50", expected=401)
        runner.api("notifications_invalid_limit", "GET", "/api/notifications?limit=0", tokens["vi"], expected=422)
        runner.runtime("prepare", fixture, admin=True)
        events = runner.runtime("exercise", fixture)
        exercise = next((x for x in events if x["event"] == "CHI43_RUNTIME_EXERCISE_PASS"), None)
        require(exercise is not None, "runtime_pass_event_missing")
        result["runtime_checks"] = exercise
        for locale in ("vi", "en"):
            user_id = fixture[locale + "_user_id"]
            listing = runner.api("notifications_list_" + locale, "GET", "/api/notifications?limit=50", tokens[locale])
            expected_ids = exercise["fixture_notification_ids"][str(user_id)]
            require({x["id"] for x in listing["items"]} == set(expected_ids), "notification_list_scope_failed")
            require(all(not x["read"] for x in listing["items"]), "initial_notification_read_state_failed")
            notification_id = expected_ids[0]
            read = runner.api("notification_mark_read_" + locale, "PATCH", f"/api/notifications/{notification_id}",
                              tokens[locale], {"read": True})
            require(read["id"] == notification_id and read["read"] is True and bool(read["read_at"]),
                    "notification_patch_body_failed")
            repeat = runner.api("notification_repeat_read_" + locale, "PATCH", f"/api/notifications/{notification_id}",
                                tokens[locale], {"read": True})
            require(repeat["read_at"] == read["read_at"], "notification_read_not_idempotent")
            runner.api("notification_bad_read_value_" + locale, "PATCH", f"/api/notifications/{notification_id}",
                       tokens[locale], {"read": False}, expected=422)
            other_locale = "en" if locale == "vi" else "vi"
            runner.api("notification_other_user_denied_" + locale, "PATCH", f"/api/notifications/{notification_id}",
                       tokens[other_locale], {"read": True}, expected=404)
            fresh = runner.api("notification_read_persisted_" + locale, "GET", "/api/notifications?limit=50", tokens[locale])
            match = next(x for x in fresh["items"] if x["id"] == notification_id)
            require(match["read"] is True and match["read_at"] == read["read_at"], "notification_read_not_persisted")
        result["checks_passed"] = True
    finally:
        if ready:
            try:
                runner.runtime("cleanup", fixture, admin=True)
                result["fixture_cleanup"] = "PASS"
            except Exception as exc:
                result["fixture_cleanup"] = "FAILED"
                result["cleanup_error_type"] = type(exc).__name__
        elif fixture.get("household_id"):
            # Preserve a guarded diagnostic instead of guessing how to delete a partial fixture.
            result["fixture_cleanup"] = "NEEDS_PARTIAL_SETUP_REVIEW"
        elif fixture.get("vi_user_id") or fixture.get("en_user_id"):
            result["fixture_cleanup"] = "NEEDS_ORPHAN_PROFILE_REVIEW"
        deleted = 0
        for username in created:
            try:
                runner.cognito.admin_delete_user(UserPoolId=POOL, Username=username)
                deleted += 1
            except Exception:
                pass
        result["cognito_cleanup"] = {"created": len(created), "deleted": deleted,
                                     "pass": len(created) == deleted}
        tokens.clear()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--seed-only", action="store_true")
    args = parser.parse_args()
    result = {"run_id": uuid.uuid4().hex[:12], "started_utc": now(), "api": [], "runtime_tasks": [],
              "email_transport": "INTERCEPTED_NOT_SENT", "scope": "API and bounded deployed-function integration"}
    try:
        execute(args, result)
        result["status"] = "PASS" if (args.seed_only or (result.get("checks_passed") and
            result.get("fixture_cleanup") == "PASS" and result.get("cognito_cleanup", {}).get("pass"))) else "PARTIAL"
    except Exception as exc:
        result["status"] = "FAILED"
        result["error_type"] = type(exc).__name__
        if type(exc) is RuntimeError and all(x.isalnum() or x == "_" for x in str(exc)):
            result["reason"] = str(exc)
    result["finished_utc"] = now()
    target = Path(args.output)
    target.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    progress("CHI43_RESULT_WRITTEN", status=result["status"], output=str(target))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
