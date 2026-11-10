"""D1/#25/#37: signed dev API cases and disposable-schema runtime checks.

The only live model request contains synthetic category/month aggregates.
Job emails are captured in memory; existing Scheduler delivery evidence is reused.
"""

import argparse
import base64
import hashlib
import importlib.util
import json
import lzma
import re
import secrets
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("chi43_acceptance", Path(__file__).with_name("run-chi43-runtime-acceptance.py"))
shared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared)


def require(value, label):
    shared.require(value, label)


class Runner(shared.Runner):
    def __init__(self, result, checkpoint):
        super().__init__(result, runtime_source=Path(__file__).with_name("budget-acceptance-runtime.py"),
                         event_prefix="D1", checkpoint=checkpoint)
        encoded = base64.b64encode(lzma.compress(self.payload, preset=9)).decode("ascii")
        # Check room for the longest command before creating any fixture.
        boot = "import base64,lzma;exec(lzma.decompress(base64.b64decode('" + encoded + "')))"
        command = ["python", "-c", boot, "exercise", "--run-id", "0" * 12]
        for flag in ("--household-id", "--vi-user-id", "--en-user-id"):
            command.extend([flag, str(2**63 - 1)])
        result["packed_runtime_override_upper_bound"] = len(json.dumps({"containerOverrides": [
            {"name": "bootstrap", "command": command, "environment": []}]}))
        require(result["packed_runtime_override_upper_bound"] < 8192, "ecs_payload_too_large")


def budget_body(categories, income, savings, values):
    return {"income_estimate": income, "savings_goal": savings,
            "allocations": [{"category_id": category, "amount": amount}
                            for category, amount in zip(categories, values)]}


def live_api_cases(runner, tokens):
    owner, member, outsider = (tokens[x] for x in ("owner", "member", "outsider"))
    listing = runner.api("SETUP-categories", "GET", "/api/categories", owner)
    items = listing.get("items", listing.get("categories", []))
    require(len(items) >= 3, "not_enough_system_categories")
    categories = [x["id"] for x in items if x.get("household_id") is None][:3]
    require(len(categories) == 3, "system_category_contract_changed")
    result = runner.result
    result["api_matrix"] = []

    def read(period, token=owner):
        return runner.api("CHECK-saved-state-" + str(len(result["api"])), "GET", "/api/budgets/" + period, token)["budget"]

    def save_case(case, period, body, expected, invalid=False):
        before = read(period) if invalid else None
        response = runner.api(case, "PUT", "/api/budgets/" + period, owner, body, expected=expected)
        if invalid:
            require(response.get("error", {}).get("code") == "VALIDATION", "validation_error_contract_failed")
            require(read(period) == before, "rejected_budget_changed_saved_state")
        else:
            value = response["budget"]
            require(value["source"] == "MANUAL" and value["status"] == "ACTIVE", "saved_budget_source_or_status_failed")
            require(read(period) == value, "budget_readback_different")
        result["api_matrix"].append({"case": case, "period": period, "http_status": expected,
                                      "status": "PASS", "saved_state_unchanged": True if invalid else None})
        runner.checkpoint()
        return response

    for case, period, income, savings, values in (
        ("BUD-01", "2026-10", 20000000, 2000000, (5000000, 2000000, 11000000)),
        ("BUD-02", "2026-11", 15000000, 0, (4000000, 7000000)),
        ("BUD-03", "2026-12", 10000000, 1000000, (9000000,)),
    ):
        save_case(case, period, budget_body(categories, income, savings, values), 201)
    for case, income, savings, values in (
        ("BUD-04", 10000000, 1000000, (10000001,)),
        ("BUD-05", 5000000, 0, (5000001,)),
        ("BUD-06", -1, 0, (100000,)),
        ("BUD-07", 10000000, -1, (100000,)),
        ("BUD-08", 10000000, 0, (-100000,)),
    ):
        save_case(case, "2026-10", budget_body(categories, income, savings, values), 422, True)
    unknown = budget_body([2147483647], 10000000, 0, (100000,))
    save_case("BUD-09", "2026-10", unknown, 422, True)
    save_case("BUD-10-upsert", "2026-10", budget_body(categories, 12000000, 1000000, (5000000,)), 200)
    extra = [
        ("BUD-duplicate-category", {"income_estimate": 100, "savings_goal": 0,
          "allocations": [{"category_id": categories[0], "amount": 1}, {"category_id": categories[0], "amount": 2}]}),
        ("BUD-savings-above-income", budget_body(categories, 100, 101, (0,))),
        ("BUD-boolean-income", budget_body(categories, True, 0, (0,))),
        ("BUD-fractional-amount", budget_body(categories, 100, 0, (1.5,))),
    ]
    for case, body in extra:
        save_case(case, "2026-10", body, 422, True)
    valid = budget_body(categories, 1000, 0, (100,))
    runner.api("AUTH-anonymous-read", "GET", "/api/budgets/2026-10", expected=401)
    before = read("2026-10")
    require(read("2026-10", member) == before, "member_read_scope_failed")
    runner.api("AUTH-member-write-denied", "PUT", "/api/budgets/2026-10", member, valid, expected=403)
    runner.api("AUTH-member-suggest-denied", "POST", "/api/budgets/2026-10/suggest", member,
               {"income_estimate": 1000, "savings_goal": 0}, expected=403)
    require(read("2026-10", outsider) is None, "other_household_budget_leaked")
    require(read("2026-10") == before, "denied_write_changed_budget")
    for period, body, case in (
        ("2026-13", {"income_estimate": 100, "savings_goal": 0}, "SUG-invalid-period"),
        ("2026-10", {"income_estimate": -1, "savings_goal": 0}, "SUG-negative-income"),
        ("2026-10", {"income_estimate": 100, "savings_goal": -1}, "SUG-negative-savings"),
        ("2026-10", {"income_estimate": 100, "savings_goal": 101}, "SUG-savings-above-income"),
    ):
        response = runner.api(case, "POST", "/api/budgets/" + period + "/suggest", owner, body, expected=422)
        require(response.get("error", {}).get("code") == "VALIDATION", "suggest_validation_code_failed")
    result["live_api_pass"] = True


def cleanup_cognito(runner, run_id, roles):
    deleted, failed = 0, []
    for role in roles:
        try:
            runner.cognito.admin_delete_user(UserPoolId=shared.POOL, Username=f"d1-{run_id}.{role}@example.com")
            deleted += 1
        except runner.cognito.exceptions.UserNotFoundException:
            deleted += 1
        except Exception as exc:
            failed.append({"role": role, "error_type": type(exc).__name__})
    return {"expected": len(roles), "removed_or_absent": deleted, "failed": failed,
            "pass": deleted == len(roles)}


def execute(args, result, checkpoint):
    runner = Runner(result, checkpoint)
    run = result["run_id"]
    fixture = result.setdefault("fixture", {"run_id": run, "household_id": 0, "vi_user_id": 0, "en_user_id": 0})
    if args.cleanup_from:
        runner.runtime("cleanup", fixture, admin=True)
        result["fixture_cleanup"] = "PASS"
        result["cognito_cleanup"] = cleanup_cognito(runner, run, ("owner", "member", "outsider"))
        return
    tokens, created, attempted_roles = {}, [], []
    try:
        flows = runner.cognito.describe_user_pool_client(UserPoolId=shared.POOL, ClientId=shared.CLIENT)["UserPoolClient"]["ExplicitAuthFlows"]
        require("ALLOW_USER_PASSWORD_AUTH" in flows, "test_auth_flow_unavailable")
        for role in ("owner", "member", "outsider"):
            username = f"d1-{run}.{role}@example.com"
            password = "Aa1!" + secrets.token_urlsafe(32)
            attempted_roles.append(role)
            result["cognito_attempted_roles"] = list(attempted_roles)
            checkpoint()
            runner.cognito.admin_create_user(UserPoolId=shared.POOL, Username=username,
                UserAttributes=[{"Name": "email", "Value": username}, {"Name": "email_verified", "Value": "true"}],
                MessageAction="SUPPRESS")
            created.append(role)
            result["cognito_created_roles"] = list(created)
            checkpoint()
            runner.cognito.admin_set_user_password(UserPoolId=shared.POOL, Username=username, Password=password, Permanent=True)
            auth = runner.cognito.initiate_auth(ClientId=shared.CLIENT, AuthFlow="USER_PASSWORD_AUTH",
                                               AuthParameters={"USERNAME": username, "PASSWORD": password})
            tokens[role] = auth["AuthenticationResult"]["AccessToken"]
            profile = runner.api("SETUP-profile-" + role, "GET", "/api/me", tokens[role])
            require(not profile.get("household"), "new_fixture_user_has_household")
            if role in ("owner", "member"):
                fixture["vi_user_id" if role == "owner" else "en_user_id"] = profile["user"]["id"]
        owner_hh = runner.api("SETUP-household", "POST", "/api/households", tokens["owner"],
                              {"name": "D1 runtime " + run}, expected=201)
        fixture["household_id"] = owner_hh["id"]
        runner.api("SETUP-member", "POST", "/api/households/join", tokens["member"], {"invite_code": owner_hh["invite_code"]})
        runner.api("AUTH-without-household", "GET", "/api/budgets/2026-10", tokens["outsider"], expected=404)
        runner.api("SETUP-outsider-household", "POST", "/api/households", tokens["outsider"],
                   {"name": "D1 outsider " + run}, expected=201)
        checkpoint()
        live_api_cases(runner, tokens)
        runner.runtime("prepare", fixture, admin=True)
        events = runner.runtime("exercise", fixture)
        evidence = next((e for e in events if e["event"] == "D1_EXERCISE_PASS"), None)
        require(evidence is not None, "runtime_pass_event_missing")
        result["runtime_checks"] = evidence
        require(all(hashlib.sha256((ROOT / "backend" / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest() == digest
                    for path, digest in evidence["deployed_source_sha256"].items()), "deployed_source_differs_from_reviewed_main")
        result["reviewed_source_matches_deployed"] = True
    finally:
        if attempted_roles:
            try:
                runner.runtime("cleanup", fixture, admin=True)
                result["fixture_cleanup"] = "PASS"
            except Exception as exc:
                result.update(fixture_cleanup="FAILED", cleanup_error_type=type(exc).__name__)
            result["cognito_cleanup"] = cleanup_cognito(runner, run, attempted_roles)
        tokens.clear()
        checkpoint()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cleanup-from", type=Path)
    args = parser.parse_args()
    result = {"run_id": uuid.uuid4().hex[:12], "started_utc": shared.now(), "api": [], "runtime_tasks": [],
              "status": "STARTED", "real_job_email": "PENDING_MAILBOX_CONFIRMATION",
              "email_transport": "INTERCEPTED_NOT_SENT", "gemini_max_attempts": 1}
    if args.cleanup_from:
        previous = json.loads(args.cleanup_from.read_text(encoding="utf-8"))
        require(re.fullmatch(r"[0-9a-f]{12}", previous["run_id"]) is not None, "invalid_previous_run")
        result["run_id"], result["fixture"] = previous["run_id"], previous["fixture"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
    def checkpoint():
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    try:
        execute(args, result, checkpoint)
        cleanup_ok = result.get("fixture_cleanup") == "PASS" and result.get("cognito_cleanup", {}).get("pass")
        if args.cleanup_from:
            result["status"] = "CLEANUP_PASS" if cleanup_ok else "CLEANUP_FAILED"
        elif cleanup_ok and result.get("live_api_pass") and result.get("reviewed_source_matches_deployed"):
            result["status"] = ("PASS_CORE_PENDING_MAILBOX" if result["runtime_checks"]["live_llm"]["status"] == "PASS"
                                else "PARTIAL_LIVE_LLM")
        else:
            result["status"] = "PARTIAL"
    except Exception as exc:
        result.update(status="FAILED", error_type=type(exc).__name__)
        if type(exc) is RuntimeError and re.fullmatch(r"[a-z0-9_]+", str(exc)):
            result["reason"] = str(exc)
    result["finished_utc"] = shared.now()
    checkpoint()
    shared.progress("D1_RESULT_WRITTEN", status=result["status"], output=str(args.output))
    return 0 if result["status"] in {"PASS_CORE_PENDING_MAILBOX", "CLEANUP_PASS"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
