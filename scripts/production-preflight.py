"""Read-only production release gate. Never retrieves secret values or sends mail.

Use --settings with an operator-reviewed copy of deploy/production.example.json.
Exit 2 means NO-GO. Output contains gate names/counts, never tokens or user data.
HA topology and dated restore/rollback evidence are checked in addition to sign-off.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError


def evaluate(settings, session):
    results = []

    def gate(name, ok):
        results.append({"gate": name, "pass": bool(ok)})
        return bool(ok)

    required = ("account", "region", "cluster", "api_service", "worker_service", "jobs_task_family", "frontend_bucket",
                "distribution_id", "public_url", "cognito_admin_group")
    if not gate("settings_complete", all(settings.get(k) for k in required)):
        return results
    gate("data_boundary_reviewed", settings.get("data_boundary_reviewed") is True)
    gate("operations_owner_named", bool(settings.get("operations_owner")))
    ceiling = settings.get("monthly_budget_usd")
    gate("monthly_budget_chosen", isinstance(ceiling, (int, float)) and not isinstance(ceiling, bool) and ceiling > 0)
    account = session.client("sts").get_caller_identity()["Account"]
    if not gate("expected_aws_account", account == settings["account"]):
        return results
    cf = session.client("cloudfront").get_distribution(Id=settings["distribution_id"])["Distribution"]
    config = cf["DistributionConfig"]
    gate("public_cloudfront_url", settings["public_url"] == "https://" + cf["DomainName"])
    api_behavior = next((x for x in config.get("CacheBehaviors", {}).get("Items", []) if x["PathPattern"] == "/api/*"), {})
    origin = next((x for x in config["Origins"]["Items"] if x["Id"] == api_behavior.get("TargetOriginId")), {})
    gate("public_api_origin_https", origin.get("CustomOriginConfig", {}).get("OriginProtocolPolicy") == "https-only")
    gate("cloudfront_deployed", cf["Status"] == "Deployed" and config["Enabled"])
    gate("api_viewer_https", api_behavior.get("ViewerProtocolPolicy") in {"https-only", "redirect-to-https"})
    cache_id = api_behavior.get("CachePolicyId")
    if gate("api_cache_policy_present", bool(cache_id)):
        cache = session.client("cloudfront").get_cache_policy(Id=cache_id)["CachePolicy"]["CachePolicyConfig"]
        gate("authenticated_api_not_cached", all(cache.get(key) == 0 for key in ("MinTTL", "DefaultTTL", "MaxTTL")))
    frontend_origin = next((x for x in config["Origins"]["Items"] if x["Id"] == config["DefaultCacheBehavior"]["TargetOriginId"]), {})
    gate("frontend_bucket_matches_distribution", frontend_origin.get("DomainName", "").startswith(settings["frontend_bucket"] + ".s3."))
    acl_arn = config.get("WebACLId", "")
    if gate("cloudfront_waf_present", ":wafv2:" in acl_arn):
        parts = acl_arn.rsplit("/", 2)
        acl = session.client("wafv2", region_name="us-east-1").get_web_acl(Name=parts[-2], Id=parts[-1], Scope="CLOUDFRONT")["WebACL"]
        gate("waf_common_rules_enforced", any(rule.get("Statement", {}).get("ManagedRuleGroupStatement", {}).get("Name") == "AWSManagedRulesCommonRuleSet"
             and "None" in rule.get("OverrideAction", {}) and not rule["Statement"]["ManagedRuleGroupStatement"].get("RuleActionOverrides")
             for rule in acl["Rules"]))
        gate("waf_rate_rule_enforced", any("RateBasedStatement" in rule.get("Statement", {}) and "Block" in rule.get("Action", {})
             for rule in acl["Rules"]))
    gate("origin_header_present", any(x["HeaderName"].lower() == "x-origin-verify" and len(x["HeaderValue"]) >= 32
                                     for x in origin.get("CustomHeaders", {}).get("Items", [])))
    ecs = session.client("ecs")
    response = ecs.describe_services(cluster=settings["cluster"], services=[settings["api_service"]])
    if not gate("api_service_exists", not response.get("failures") and len(response.get("services", [])) == 1):
        return results
    service = response["services"][0]
    resilience_spec = importlib.util.spec_from_file_location(
        "production_resilience", Path(__file__).with_name("production-resilience-check.py"))
    resilience = importlib.util.module_from_spec(resilience_spec)
    resilience_spec.loader.exec_module(resilience)
    results.extend(resilience.evaluate(settings, session, service))
    gate("api_service_stable", service["runningCount"] >= 1 and service["pendingCount"] == 0 and
         len(service.get("deployments", [])) == 1 and service["deployments"][0].get("rolloutState") == "COMPLETED")
    task = ecs.describe_task_definition(taskDefinition=service["taskDefinition"])["taskDefinition"]
    container = next((x for x in task["containerDefinitions"] if x["name"] == "api"), {})
    env = {x["name"]: x["value"] for x in container.get("environment", [])}
    secrets = {x["name"]: x["valueFrom"] for x in container.get("secrets", [])}
    truth = lambda name: env.get(name, "").lower() in {"true", "1"}
    gate("production_runtime_profile", env.get("APP_ENV") == "production")
    gate("immutable_api_image", bool(re.search(r"@sha256:[a-f0-9]{64}$", container.get("image", ""))))
    gate("identified_release", bool(re.fullmatch(r"[a-f0-9]{40}", env.get("APP_RELEASE", ""))))
    gate("reviewed_release_matches_runtime", env.get("APP_RELEASE") == settings.get("release"))
    gate("reviewed_image_matches_runtime", bool(settings.get("release_image_digest")) and
         container.get("image", "").endswith("@" + settings.get("release_image_digest", "")))
    approved = settings.get("allowed_household_ids", [])
    approved_valid = isinstance(approved, list) and bool(approved) and all(type(value) is int and value > 1 for value in approved)
    public_registration = settings.get("public_registration_enabled", False)
    gate("registration_policy_explicit", type(public_registration) is bool)

    def scope_matches(runtime):
        public = runtime.get("PRODUCTION_PUBLIC_REGISTRATION", "false").lower()
        if public_registration is True:
            return public == "true"
        return public == "false" and approved_valid and set(runtime.get("PRODUCTION_ALLOWED_HOUSEHOLD_IDS", "").split(",")) == {str(value) for value in approved}

    gate("approved_household_scope_enforced", scope_matches(env))
    expected_image = container.get("image", "")
    expected_release = env.get("APP_RELEASE", "")
    image_ref = re.fullmatch(re.escape(account + ".dkr.ecr." + settings["region"] + ".amazonaws.com/") +
                             r"(?P<repository>[a-z0-9][a-z0-9._/-]*)@sha256:[a-f0-9]{64}", expected_image)
    if gate("api_image_in_expected_private_registry", bool(image_ref)):
        repository = session.client("ecr").describe_repositories(
            registryId=account, repositoryNames=[image_ref["repository"]])["repositories"][0]
        gate("release_tags_immutable", repository.get("imageTagMutability") == "IMMUTABLE")

    def container_security(kind, candidate):
        linux = candidate.get("linuxParameters", {})
        caps = linux.get("capabilities", {})
        gate(f"{kind}_unprivileged_runtime", candidate.get("user") == "10001:10001" and
             "ALL" in caps.get("drop", []) and not caps.get("add") and
             linux.get("initProcessEnabled") is True and not candidate.get("privileged", False))

    container_security("api", container)
    gate("api_private_network", service.get("networkConfiguration", {}).get("awsvpcConfiguration", {}).get("assignPublicIp") == "DISABLED")
    worker_response = ecs.describe_services(cluster=settings["cluster"], services=[settings["worker_service"]])
    if gate("worker_service_exists", not worker_response.get("failures") and len(worker_response.get("services", [])) == 1):
        worker_service = worker_response["services"][0]
        gate("worker_service_stable", worker_service["runningCount"] >= 1 and worker_service["pendingCount"] == 0 and
             len(worker_service.get("deployments", [])) == 1 and worker_service["deployments"][0].get("rolloutState") == "COMPLETED")
        gate("worker_private_network", worker_service.get("networkConfiguration", {}).get("awsvpcConfiguration", {}).get("assignPublicIp") == "DISABLED")
        worker_task = ecs.describe_task_definition(taskDefinition=worker_service["taskDefinition"])["taskDefinition"]
        worker = next((x for x in worker_task["containerDefinitions"] if x["name"] == "worker"), {})
        worker_env = {x["name"]: x["value"] for x in worker.get("environment", [])}
        gate("worker_household_scope_enforced", scope_matches(worker_env))
        gate("worker_matches_production_release", worker.get("image") == expected_image and
             worker_env.get("APP_RELEASE") == expected_release and worker_env.get("APP_ENV") == "production")
        container_security("worker", worker)
        if worker_env.get("OCR_ENABLED", "false").lower() in {"true", "1"}:
            worker_secrets = {x["name"]: x["valueFrom"] for x in worker.get("secrets", [])}
            gate("ocr_worker_rotation_and_secret", worker_env.get("GEMINI_ENABLED") == "true" and
                 worker_env.get("GEMINI_ROTATION_CONFIRMED") == "true" and
                 settings.get("gemini_provider_revocation_confirmed") is True and bool(worker_secrets.get("GEMINI_API_KEY")))
            gate("ocr_worker_isolated_queue", worker_env.get("SQS_QUEUE_URL", "").rstrip("/").endswith("production-ocr-queue"))
            gate("ocr_worker_provider_budget", 1 <= int(worker_env.get("OCR_PROVIDER_REQUESTS_PER_DAY", "0")) <= 15 and
                 1 <= int(worker_env.get("GEMINI_MAX_TRIES", "0")) <= 2 and
                 worker_env.get("TEXTRACT_FALLBACK_ENABLED", "false").lower() == "false")
    jobs_task = ecs.describe_task_definition(taskDefinition=settings["jobs_task_family"])["taskDefinition"]
    jobs = next((x for x in jobs_task["containerDefinitions"] if x["name"] == "jobs"), {})
    jobs_env = {x["name"]: x["value"] for x in jobs.get("environment", [])}
    gate("jobs_match_production_release", jobs.get("image") == expected_image and
         jobs_env.get("APP_RELEASE") == expected_release and jobs_env.get("APP_ENV") == "production")
    gate("jobs_approved_household_scope_enforced", scope_matches(jobs_env))
    container_security("jobs", jobs)
    gate("admin_mfa_challenge_verified", settings.get("admin_mfa_challenge_verified") is True)
    gate("admission_and_consent", truth("RATE_LIMIT_ENABLED") and truth("OCR_REQUIRE_CONSENT"))
    gate("runtime_credentials_tls", bool(env.get("DB_SSL_CA") and env.get("REDIS_HOST") and
         secrets.get("DB_USER") and secrets.get("DB_PASSWORD") and secrets.get("REDIS_AUTH_TOKEN") and
         secrets.get("ORIGIN_VERIFY_HEADER")))
    disabled = lambda name: env.get(name, "").lower() in {"false", "0"}
    gate("gemini_rotation_or_disabled", disabled("GEMINI_ENABLED") or
         (truth("GEMINI_ROTATION_CONFIRMED") and settings.get("gemini_provider_revocation_confirmed") is True))
    gate("ocr_acceptance_or_disabled", disabled("OCR_ENABLED") or
         (truth("OCR_ENABLED") and settings.get("ocr_benchmark_accepted") is True))
    pool_id = env.get("COGNITO_ISSUER", "").rsplit("/", 1)[-1]
    cognito = session.client("cognito-idp")
    if gate("cognito_pool_configured", bool(pool_id and pool_id.startswith(settings["region"] + "_"))):
        pool = cognito.describe_user_pool(UserPoolId=pool_id)["UserPool"]
        gate("cognito_registration_matches_policy", pool.get("AdminCreateUserConfig", {}).get("AllowAdminCreateUserOnly") is (not public_registration))
        gate("cognito_email_verification_enabled", "email" in pool.get("AutoVerifiedAttributes", []))
        clients = [x.strip() for x in env.get("COGNITO_CLIENT_IDS", "").split(",") if x.strip()]
        gate("one_spa_client_only", len(clients) == 1)
        for client_id in clients:
            client = cognito.describe_user_pool_client(UserPoolId=pool_id, ClientId=client_id)["UserPoolClient"]
            gate("srp_client_without_password_flow", "ALLOW_USER_SRP_AUTH" in client.get("ExplicitAuthFlows", []) and
                 "ALLOW_USER_PASSWORD_AUTH" not in client.get("ExplicitAuthFlows", []) and not client.get("ClientSecret"))
            gate("no_localhost_production_callbacks", all(url.startswith(settings["public_url"] + "/")
                 for url in client.get("CallbackURLs", []) + client.get("LogoutURLs", [])))
        admin_count = unenrolled = 0
        paginator = cognito.get_paginator("list_users_in_group")
        for page in paginator.paginate(UserPoolId=pool_id, GroupName=settings["cognito_admin_group"]):
            for user in page.get("Users", []):
                if not user.get("Enabled", True):
                    continue
                admin_count += 1
                details = cognito.admin_get_user(UserPoolId=pool_id, Username=user["Username"])
                if "SOFTWARE_TOKEN_MFA" not in details.get("UserMFASettingList", []) or details.get("PreferredMfaSetting") != "SOFTWARE_TOKEN_MFA":
                    unenrolled += 1
        gate("admin_totp_enrolled_and_preferred", admin_count > 0 and unenrolled == 0)
        ses = session.client("sesv2").get_account()
        gate("ses_transactional_sending_available", ses.get("ProductionAccessEnabled") and ses.get("SendingEnabled"))
    s3 = session.client("s3")
    for kind, bucket in (("frontend", settings["frontend_bucket"]), ("receipts", env.get("S3_BUCKET"))):
        if gate(f"{kind}_bucket_configured", bool(bucket)):
            block = s3.get_public_access_block(Bucket=bucket)["PublicAccessBlockConfiguration"]
            gate(f"{kind}_bucket_private", len(block) == 4 and all(block.values()))
            gate(f"{kind}_bucket_encrypted", bool(s3.get_bucket_encryption(Bucket=bucket)["ServerSideEncryptionConfiguration"]["Rules"]))
            if kind == "frontend":
                gate("frontend_release_history_versioned", s3.get_bucket_versioning(Bucket=bucket).get("Status") == "Enabled")
    schedules = settings.get("schedule_names", [])
    gate("scheduler_inventory_recorded", len(schedules) == 3 and len(set(schedules)) == 3)
    schedules_enabled = settings.get("job_schedules_enabled", False)
    valid_schedule_setting = type(schedules_enabled) is bool
    gate("scheduler_state_setting_valid", valid_schedule_setting)
    if schedules_enabled is True:
        gate("notification_delivery_accepted", settings.get("notifications_release_accepted") is True)
    expected_schedule_state = "ENABLED" if schedules_enabled is True else "DISABLED"
    for name in schedules:
        schedule = session.client("scheduler").get_schedule(Name=name, GroupName=settings.get("schedule_group", "default"))
        gate("schedule_state_matches_operator_settings", valid_schedule_setting and schedule["State"] == expected_schedule_state)
        gate("schedule_targets_reviewed_jobs_revision", schedule.get("Target", {}).get("EcsParameters", {}).get("TaskDefinitionArn") == jobs_task["taskDefinitionArn"])
    if gate("budget_name_configured", bool(settings.get("budget_name"))):
        try:
            budget = session.client("budgets").describe_budget(AccountId=account, BudgetName=settings["budget_name"])["Budget"]
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") != "NotFoundException":
                raise
            gate("monthly_cost_budget_exists", False)
            gate("external_resilience_signoff", settings.get("resilience_signoff") is True)
            return results
        gate("monthly_cost_budget_exists", budget["TimeUnit"] == "MONTHLY" and budget["BudgetType"] == "COST" and
             budget.get("BudgetLimit", {}).get("Unit") == "USD" and
             float(budget.get("BudgetLimit", {}).get("Amount", 0)) == ceiling)
        notifications = session.client("budgets").describe_notifications_for_budget(AccountId=account, BudgetName=settings["budget_name"])
        gate("cost_budget_notifications_configured", bool(notifications.get("Notifications")))
        for notification in notifications.get("Notifications", []):
            subscribers = session.client("budgets").describe_subscribers_for_notification(
                AccountId=account, BudgetName=settings["budget_name"], Notification=notification)
            gate("cost_notification_has_subscriber", bool(subscribers.get("Subscribers")))
    gate("external_resilience_signoff", settings.get("resilience_signoff") is True)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", required=True)
    parser.add_argument("--output")
    parser.add_argument("--profile")
    args = parser.parse_args()
    settings = json.loads(Path(args.settings).read_text(encoding="utf-8-sig"))
    try:
        session = boto3.Session(profile_name=args.profile, region_name=settings.get("region", "ap-southeast-1"))
        results = evaluate(settings, session)
        report = {"status": "GO" if results and all(x["pass"] for x in results) else "NO_GO", "checks": results}
    except (BotoCoreError, ClientError, ValueError, KeyError) as exc:
        # AWS error strings can contain resource/user identifiers; do not echo them.
        report = {"status": "NO_GO", "error_type": type(exc).__name__}
        if isinstance(exc, ClientError):
            report["aws_error_code"] = exc.response.get("Error", {}).get("Code")
    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, separators=(",", ":")))
    return 0 if report["status"] == "GO" else 2


if __name__ == "__main__":
    raise SystemExit(main())
