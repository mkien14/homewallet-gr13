import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def release(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("production_release", Path(__file__).parents[1] / "deploy-production.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    values = {
        "RELEASE_COMMIT": "a" * 40, "RELEASE_DIGEST": "sha256:" + "b" * 64,
        "PROD_ACCOUNT_ID": "123456789012", "COMPATIBILITY_REVIEW": "CHG-123",
        "PROD_URL": "https://wallet.example.com", "MIGRATION_VERSION": "001",
        "PROD_QUEUE_URL": "https://sqs.ap-southeast-1.amazonaws.com/123456789012/homewallet-prod-receipts-queue",
        "CLOUDFRONT_DISTRIBUTION_ID": "PROD123", "SMOKE_TOKEN": "private-test-token",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    clients = {name: MagicMock() for name in ["sts", "ecr", "ecs", "sqs", "elbv2", "scheduler", "cloudfront"]}
    monkeypatch.setattr(module.boto3, "client", lambda name: clients[name])
    clients["sts"].get_caller_identity.return_value = {"Account": values["PROD_ACCOUNT_ID"]}
    clients["cloudfront"].get_distribution.return_value = {"Distribution": {"DomainName": "wallet.example.com", "DistributionConfig": {"Comment": "homewallet-prod frontend and API"}}}
    clients["ecr"].describe_images.return_value = {"imageDetails": [{"imageTags": ["sha-" + values["RELEASE_COMMIT"]]}]}
    clients["ecr"].describe_image_scan_findings.return_value = {"imageScanStatus": {"status": "COMPLETE"}, "imageScanFindings": {"findingSeverityCounts": {}}}
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    return module, clients, values


@pytest.mark.parametrize("case", ["mutable", "wrong_account", "wrong_source", "scan_pending", "critical", "dev_queue", "http", "dev_frontend"])
def test_rejected_release_cannot_update_ecs(release, monkeypatch, case):
    module, clients, _ = release
    if case == "mutable":
        monkeypatch.setenv("RELEASE_DIGEST", "dev")
    elif case == "wrong_account":
        clients["sts"].get_caller_identity.return_value = {"Account": "999999999999"}
    elif case == "wrong_source":
        clients["ecr"].describe_images.return_value = {"imageDetails": [{"imageTags": ["sha-other"]}]}
    elif case == "scan_pending":
        clients["ecr"].describe_image_scan_findings.return_value = {"imageScanStatus": {"status": "IN_PROGRESS"}}
    elif case == "critical":
        clients["ecr"].describe_image_scan_findings.return_value["imageScanFindings"]["findingSeverityCounts"] = {"CRITICAL": 1}
    elif case == "dev_queue":
        monkeypatch.setenv("PROD_QUEUE_URL", "https://sqs.ap-southeast-1.amazonaws.com/123456789012/receipts-queue")
    elif case == "http":
        monkeypatch.setenv("PROD_URL", "http://wallet.example.com")
    else:
        clients["cloudfront"].get_distribution.return_value["Distribution"]["DistributionConfig"]["Comment"] = "homewallet-dev frontend and API"
    with pytest.raises(RuntimeError):
        module.main()
    clients["ecs"].update_service.assert_not_called()
    clients["ecs"].register_task_definition.assert_not_called()


def test_smoke_failure_stops_before_worker_rollout_and_keeps_rollback_record(release, monkeypatch):
    module, clients, values = release
    ecs = clients["ecs"]
    ecs.describe_services.side_effect = [
        {"services": [{"taskDefinition": "previous-api"}]},
        {"services": [{"taskDefinition": "new-api", "runningCount": 2, "loadBalancers": [{"targetGroupArn": "prod-target"}]}]},
    ]
    ecs.describe_task_definition.return_value = {"taskDefinition": {
        "family": "homewallet-prod-api",
        "executionRoleArn": "arn:aws:iam::123456789012:role/homewallet-prod-task-execution-role",
        "taskRoleArn": "arn:aws:iam::123456789012:role/homewallet-prod-api-task-role",
        "containerDefinitions": [{"name": "api", "image": "previous@sha256:old"}],
    }}
    ecs.register_task_definition.return_value = {"taskDefinition": {"taskDefinitionArn": "new-api"}}
    ecs.list_tasks.return_value = {"taskArns": ["task-a", "task-b"]}
    ecs.describe_tasks.return_value = {"tasks": [
        {"taskDefinitionArn": "new-api", "availabilityZone": az, "containers": [{"name": "api", "imageDigest": values["RELEASE_DIGEST"]}]}
        for az in ["ap-southeast-1a", "ap-southeast-1b"]
    ]}
    clients["elbv2"].describe_target_health.return_value = {"TargetHealthDescriptions": [{"TargetHealth": {"State": "healthy"}}] * 2}
    monkeypatch.setattr(module.urllib.request, "urlopen", MagicMock(side_effect=RuntimeError("smoke failed")))
    with pytest.raises(RuntimeError, match="smoke failed"):
        module.main()
    assert [call.kwargs["service"] for call in ecs.update_service.call_args_list] == ["api"]
    clients["sqs"].get_queue_attributes.assert_not_called()
    record = json.loads(Path("production-release-record.json").read_text())
    assert record["services"]["api"]["previous_task_definition"] == "previous-api"
    assert values["SMOKE_TOKEN"] not in json.dumps(record)
