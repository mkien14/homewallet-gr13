"""Prevent a public sign-up frontend from being published over closed API policy."""
import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.mark.parametrize("frontend_public,api_public", [(True, "false"), (False, "true")])
def test_publisher_rejects_mismatched_registration_before_registry_lookup(tmp_path, frontend_public, api_public):
    spec = importlib.util.spec_from_file_location("publisher", Path(__file__).parents[1] / "publish-frontend-release.py")
    publisher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(publisher)
    (tmp_path / "manifest.json").write_text(json.dumps({"ocr_enabled": True, "public_registration_enabled": frontend_public}), encoding="utf-8")
    session = MagicMock()
    ecs = session.client.return_value
    ecs.describe_services.return_value = {"services": [{"taskDefinition": "candidate"}]}
    ecs.describe_task_definition.return_value = {"taskDefinition": {"containerDefinitions": [{
        "name": "api", "image": "candidate@sha256:reviewed",
        "environment": [{"name": "OCR_ENABLED", "value": "true"}, {"name": "PRODUCTION_PUBLIC_REGISTRATION", "value": api_public}],
    }]}}
    with pytest.raises(ValueError, match="registration profile differs"):
        publisher.verify_running_image(session, {"cluster": "test", "api_service": "api"}, tmp_path)
    ecs.batch_get_image.assert_not_called()
