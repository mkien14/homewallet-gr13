import unittest
from datetime import datetime, timedelta, timezone

import d3_pilot_v2 as pilot


class ParserTests(unittest.TestCase):
    def test_valid_json_response(self):
        raw = '{"merchant":"PHUC LONG","date":"2021-06-12","total":0,"items":[{"description":"tea","quantity":1,"amount":0}]}'
        parsed, errors = pilot.parse_response(raw)
        self.assertEqual(errors, [])
        self.assertEqual(parsed["total"], 0)
        self.assertEqual(len(parsed["items"]), 1)

    def test_valid_fenced_response(self):
        raw = '```json\n{"merchant":null,"date":null,"total":null,"items":[]}\n```'
        parsed, errors = pilot.parse_response(raw)
        self.assertEqual(errors, [])
        self.assertIsNone(parsed["merchant"])

    def test_rejects_invalid_json(self):
        parsed, errors = pilot.parse_response('{"merchant":')
        self.assertIsNone(parsed)
        self.assertEqual(errors, ["invalid_json"])

    def test_rejects_wrong_field_types_and_bad_date(self):
        raw = {"merchant": 4, "date": "2021-02-30", "total": True, "items": "none"}
        parsed, errors = pilot.parse_response(raw)
        self.assertIsNone(parsed)
        self.assertIn("merchant_type", errors)
        self.assertIn("date_value", errors)
        self.assertIn("total_type", errors)
        self.assertIn("items_type", errors)

    def test_rejects_malformed_item(self):
        raw = {"merchant": "Shop", "date": None, "total": 100,
               "items": [{"description": "Tea", "quantity": "one", "amount": 100}]}
        parsed, errors = pilot.parse_response(raw)
        self.assertIsNone(parsed)
        self.assertIn("items_0_quantity_type", errors)

    def test_unknown_date_excluded_from_date_metric(self):
        row = {"merchant": "PHUC LONG", "date": "None", "total": "100", "items_count": "1"}
        prediction = {"merchant": "Phuc Long", "date": None, "total": 100, "items": []}
        scored = pilot.score_prediction(prediction, row)
        self.assertIsNone(scored["date_correct"])
        self.assertTrue(scored["merchant_correct"])

    def test_cost_ceiling_preflight_stays_under_half_dollar(self):
        for provider in pilot.RATES_USD_PER_MILLION:
            self.assertLess(pilot.estimated_max_cost(provider), 0.50)

    def test_gemini_sdk_accepts_response_schema_without_api_call(self):
        config = pilot.types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=pilot.OUTPUT_SCHEMA,
            max_output_tokens=pilot.MAX_OUTPUT_TOKENS,
        )
        self.assertIsNotNone(config.response_schema)

    def test_accuracy_denominator_includes_errors_and_skips(self):
        rows = []
        for index in range(10):
            rows.append({"provider": "gemini", "id": f"{index:03d}",
                         "status": "skipped" if index == 9 else "call_error",
                         "date_in_label": index != 0})
        summary = pilot.summarize_provider(rows, "gemini")
        self.assertEqual(summary["requests_attempted"], 9)
        self.assertEqual(summary["merchant_correct"], {"correct": 0, "evaluated": 10})
        self.assertEqual(summary["date_correct"], {"correct": 0, "evaluated": 9})

    def test_quota_gate_requires_confirmed_model_rate_and_headroom(self):
        quota = {"verified_in_ai_studio": True, "model": pilot.GEMINI_MODEL,
                 "rpm": 5, "remaining_requests_today": 10,
                 "checked_utc": "2099-01-01T00:00:00Z",
                 "api_key_project_matches": True}
        self.assertFalse(pilot.quota_is_ready(quota))
        quota["checked_utc"] = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        self.assertTrue(pilot.quota_is_ready(quota))
        quota["rpm"] = 3
        self.assertFalse(pilot.quota_is_ready(quota))


class IamSimulationTests(unittest.TestCase):
    def test_accepts_all_resource_specific_allow_decisions(self):
        resources = ["profile-arn", "model-a-arn", "model-b-arn"]
        simulation = {"EvaluationResults": [{
            "EvalDecision": "allowed",
            "ResourceSpecificResults": [
                {"EvalResourceName": resource, "EvalResourceDecision": "allowed"}
                for resource in resources
            ],
        }]}
        self.assertTrue(pilot.simulation_allows_resources(simulation, resources))

    def test_rejects_a_resource_specific_deny(self):
        resources = ["profile-arn", "model-arn"]
        simulation = {"EvaluationResults": [{
            "EvalDecision": "implicitDeny",
            "ResourceSpecificResults": [
                {"EvalResourceName": "profile-arn", "EvalResourceDecision": "allowed"},
                {"EvalResourceName": "model-arn", "EvalResourceDecision": "implicitDeny"},
            ],
        }]}
        self.assertFalse(pilot.simulation_allows_resources(simulation, resources))

    def test_rejects_missing_resource_decision(self):
        resources = ["profile-arn", "model-arn"]
        simulation = {"EvaluationResults": [{
            "ResourceSpecificResults": [
                {"EvalResourceName": "profile-arn", "EvalResourceDecision": "allowed"},
            ],
        }]}
        self.assertFalse(pilot.simulation_allows_resources(simulation, resources))


if __name__ == "__main__":
    unittest.main()
