import json
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError, ProfileNotFound

import bedrock_access as access
import bedrock_access_check as check
import pilot_run_guard as guard
import d3_pilot_v2 as pilot


PROFILE = "arn:aws:bedrock:ap-southeast-1:179923444714:inference-profile/apac.amazon.nova-lite-v1:0"
SOURCE = "arn:aws:bedrock:ap-southeast-1::foundation-model/amazon.nova-lite-v1:0"
DESTINATION = "arn:aws:bedrock:ap-southeast-2::foundation-model/amazon.nova-lite-v1:0"
PRINCIPAL = "arn:aws:iam::179923444714:user/hoang"


class FakeIAM:
    def __init__(self, deny_other_regions=False):
        self.calls = []
        self.deny_other_regions = deny_other_regions

    def simulate_principal_policy(self, **kwargs):
        self.calls.append(kwargs)
        context = {x["ContextKeyName"]: x["ContextKeyValues"][0] for x in kwargs["ContextEntries"]}
        resource = kwargs["ResourceArns"][0]
        decision = "explicitDeny" if self.deny_other_regions and context["aws:RequestedRegion"] != "ap-southeast-1" else "allowed"
        return {"EvaluationResults": [{"EvalActionName": "bedrock:InvokeModel",
                                       "EvalResourceName": resource, "EvalDecision": decision}]}


class CrossRegionTests(unittest.TestCase):
    def profile(self):
        return {"status": "ACTIVE", "inferenceProfileArn": PROFILE,
                "models": [{"modelArn": SOURCE}, {"modelArn": DESTINATION}]}

    def test_destination_region_deny_is_not_hidden_by_source_region_context(self):
        iam = FakeIAM(deny_other_regions=True)
        results = access.simulate_inference_access(iam, PRINCIPAL, self.profile())
        self.assertEqual([r["decision"] for r in results], ["allowed", "allowed", "explicitDeny"])
        self.assertEqual(results[-1]["requested_region"], "ap-southeast-2")
        self.assertFalse(results[-1]["allowed"])

    def test_profile_claim_is_only_supplied_for_foundation_models(self):
        iam = FakeIAM()
        results = access.simulate_inference_access(iam, PRINCIPAL, self.profile())
        self.assertTrue(all(r["allowed"] for r in results))
        first = {x["ContextKeyName"] for x in iam.calls[0]["ContextEntries"]}
        self.assertNotIn("bedrock:InferenceProfileArn", first)
        for call in iam.calls[1:]:
            context = {x["ContextKeyName"]: x["ContextKeyValues"][0] for x in call["ContextEntries"]}
            self.assertEqual(context["bedrock:InferenceProfileArn"], PROFILE)
            self.assertEqual(context["aws:RequestedRegion"], call["ResourceArns"][0].split(":")[3])

    def test_missing_or_incomplete_evaluation_fails_closed(self):
        iam = Mock()
        iam.simulate_principal_policy.return_value = {"EvaluationResults": []}
        self.assertFalse(access.simulate_resource(iam, PRINCIPAL, SOURCE)["allowed"])
        iam.simulate_principal_policy.return_value = {"EvaluationResults": [{
            "EvalActionName": "bedrock:InvokeModel", "EvalResourceName": SOURCE,
            "EvalDecision": "allowed", "MissingContextValues": ["required_context"]}]}
        self.assertFalse(access.simulate_resource(iam, PRINCIPAL, SOURCE)["allowed"])

    def test_resource_specific_deny_overrides_top_level_allow(self):
        iam = Mock()
        iam.simulate_principal_policy.return_value = {"EvaluationResults": [{
            "EvalActionName": "bedrock:InvokeModel", "EvalResourceName": SOURCE, "EvalDecision": "allowed",
            "ResourceSpecificResults": [{"EvalResourceName": SOURCE, "EvalResourceDecision": "explicitDeny"}]}]}
        self.assertFalse(access.simulate_resource(iam, PRINCIPAL, SOURCE)["allowed"])

    def test_synthetic_probe_is_one_short_text_request_and_omits_model_text(self):
        runtime = Mock()
        runtime.converse.return_value = {"ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": "request-1"},
                                        "output": {"message": {"content": [{"text": "OK"}]}},
                                        "usage": {"inputTokens": 10, "outputTokens": 1}, "stopReason": "end_turn"}
        result = check.synthetic_call(runtime)
        runtime.converse.assert_called_once()
        sent = runtime.converse.call_args.kwargs
        self.assertEqual(sent["inferenceConfig"]["maxTokens"], 8)
        self.assertEqual(sent["modelId"], check.MODEL)
        self.assertEqual(sent["messages"][0]["content"], [{"text": check.PROMPT}])
        self.assertTrue(result["matches_synthetic_answer"])
        self.assertNotIn("text", result)

    def test_error_diagnostics_do_not_store_error_message(self):
        exc = ClientError({"Error": {"Code": "AccessDeniedException", "Message": "private text; explicit deny in an identity-based policy"}}, "Converse")
        result = check.error_fields(exc)
        self.assertTrue(result["explicit_deny"])
        self.assertTrue(result["identity_policy_mentioned"])
        self.assertNotIn("private text", json.dumps(result))

    def test_historical_runs_remain_blocked_without_local_lock_files(self):
        for name in ("d3-pilot", "d3-pilot-v2"):
            with self.assertRaises(RuntimeError):
                guard.require_unconsumed_run(name)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.json"
            path.write_text('{"runs": {}}', encoding="utf-8")
            with patch.object(guard, "HISTORY", path), self.assertRaises(RuntimeError):
                guard.require_unconsumed_run("unapproved-new-run")

    def test_retired_v2_execution_stops_before_preflight_or_any_provider(self):
        with patch.object(pilot, "run_preflight") as preflight:
            with self.assertRaises(pilot.PilotError):
                pilot.execute_run()
            preflight.assert_not_called()

    def test_retired_preflight_cannot_report_ready_even_if_quota_is_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "preflight.json"
            with (
                patch.object(pilot, "load_approval", return_value=({}, {})),
                patch.object(pilot, "sample_rows", return_value=[]),
                patch.object(pilot, "verify_gemini_model", return_value={}),
                patch.object(pilot, "verify_aws_access", return_value=({}, None)),
                patch.object(pilot, "quota_is_ready", return_value=True),
                patch.object(pilot, "ARTIFACT_DIR", output.parent),
                patch.object(pilot, "PREFLIGHT_REPORT", output),
            ):
                result = pilot.run_preflight()
            self.assertFalse(result["ready_to_run"])
            self.assertEqual(result["run_authorization"], "CONSUMED_OR_UNAPPROVED")

    def test_wrong_caller_stops_before_iam_or_runtime_clients(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "evidence.json"
            session = Mock()
            session.client.return_value.get_caller_identity.return_value = {
                "Account": check.ACCOUNT, "Arn": "arn:aws:iam::179923444714:user/unexpected"}
            args = ["probe", "--invoke-synthetic", "--output", str(output)]
            with (
                patch("sys.argv", args),
                patch.object(check.boto3, "Session", return_value=session),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(check.main(), 1)
            self.assertEqual([c.args[0] for c in session.client.call_args_list], ["sts"])
            evidence = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(evidence["synthetic_requests_attempted"], 0)
            self.assertEqual(evidence["status"], "FAILED")

    def test_missing_profile_records_blocker_without_provider_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "evidence.json"
            args = ["probe", "--invoke-synthetic", "--output", str(output)]
            with (
                patch("sys.argv", args),
                patch.object(check.boto3, "Session", side_effect=ProfileNotFound(profile="missing")),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(check.main(), 1)
            evidence = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(evidence["status"], "BLOCKED_CREDENTIAL_PROFILE")
            self.assertEqual(evidence["synthetic_requests_attempted"], 0)

    def test_existing_evidence_file_cannot_trigger_another_call(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "evidence.json"
            output.write_text("original", encoding="utf-8")
            args = ["probe", "--invoke-synthetic", "--output", str(output)]
            with patch("sys.argv", args), patch.object(check.boto3, "Session") as session:
                with self.assertRaises(FileExistsError):
                    check.main()
                session.assert_not_called()
            self.assertEqual(output.read_text(encoding="utf-8"), "original")


if __name__ == "__main__":
    unittest.main()
