"""Validate security evidence against the exact saved container, without running it.

This verifies artifact consistency, not provenance: obtain the candidate only
from the reviewed main workflow. Never accept a report for a different image.
"""
from __future__ import annotations

import hashlib
import json
import re
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


SCANNER = "ghcr.io/aquasecurity/trivy@sha256:8f6bb947dbc528902e11f2f5be52f7b519f6a39d5d148f41166f2040499768fb"
POLICY = "high-critical-and-secrets-v1"


def security_metadata(root: Path, release: str) -> dict:
    if not re.fullmatch(r"[a-f0-9]{40}", release):
        raise ValueError("Expected reviewed release commit")
    report = json.loads((root / "security/container-scan.json").read_text(encoding="utf-8"))
    results = report.get("Results", [])
    if (report.get("SchemaVersion") != 2 or report.get("ArtifactType") != "container_image" or
            report.get("Trivy", {}).get("Version") != "0.76.2"):
        raise ValueError("Unsupported container scan report")
    if not any(item.get("Class") == "os-pkgs" for item in results) or not any(
        item.get("Type") == "python-pkg" for item in results
    ):
        raise ValueError("OS and Python package scans are required")
    os_info = report.get("Metadata", {}).get("OS", {})
    if os_info.get("EOSL") is True or os_info.get("Family") != "alpine" or not os_info.get("Name", "").startswith("3.24."):
        raise ValueError("Expected supported Alpine 3.24 runtime")
    if any(v.get("Severity") in {"HIGH", "CRITICAL"} for item in results for v in item.get("Vulnerabilities", [])):
        raise ValueError("HIGH/CRITICAL findings block release, including unfixed findings")
    if any(item.get("Secrets") for item in results):
        raise ValueError("Secret findings block release")
    scanned_at = datetime.fromisoformat(report["CreatedAt"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    if scanned_at.tzinfo is None or not now - timedelta(hours=72) <= scanned_at <= now + timedelta(minutes=15):
        raise ValueError("Security report must be at most 72 hours old")

    # Read two small JSON files; never extract paths or execute the container.
    with tarfile.open(root / "backend.tar", "r:*") as archive:
        members = archive.getmembers()
        if len({member.name for member in members}) != len(members):
            raise ValueError("Duplicate container archive entries")
        manifest_entry = archive.getmember("manifest.json")
        if not manifest_entry.isfile() or manifest_entry.size > 1_048_576:
            raise ValueError("Invalid container archive manifest")
        manifests = json.load(archive.extractfile(manifest_entry))
        if len(manifests) != 1 or manifests[0].get("RepoTags") != ["homewallet-release:" + release]:
            raise ValueError("Archive must contain the reviewed release image only")
        entry = archive.getmember(manifests[0]["Config"])
        if not entry.isfile() or entry.size > 1_048_576:
            raise ValueError("Invalid image config")
        config_body = archive.extractfile(entry).read()
    image_id = "sha256:" + hashlib.sha256(config_body).hexdigest()
    config = json.loads(config_body)
    image = config.get("config", {})
    if report["Metadata"].get("ImageID") != image_id:
        raise ValueError("Container scan does not match the saved image")
    if config.get("os") != "linux" or config.get("architecture") != "amd64":
        raise ValueError("Release requires Linux amd64")
    if image.get("Labels", {}).get("org.opencontainers.image.revision") != release or (
        "APP_RELEASE=" + release not in image.get("Env", [])
    ):
        raise ValueError("Image release metadata mismatch")
    if image.get("User") != "10001:10001":
        raise ValueError("Release must use the unprivileged runtime user")
    sbom = json.loads((root / "security/sbom.cdx.json").read_text(encoding="utf-8"))
    if sbom.get("bomFormat") != "CycloneDX" or not sbom.get("components"):
        raise ValueError("Nonempty CycloneDX SBOM required")
    if any("sqlite" in component.get("name", "").lower() for component in sbom["components"]):
        raise ValueError("SQLite is excluded from the MySQL-only runtime, regardless of scanner severity")
    root_component = sbom.get("metadata", {}).get("component", {})
    if root_component.get("type") != "container" or not any(
        prop.get("name") == "aquasecurity:trivy:ImageID" and prop.get("value") == image_id
        for prop in root_component.get("properties", [])
    ):
        raise ValueError("SBOM does not match the saved image")
    return {"scanner": SCANNER, "policy": POLICY, "image_id": image_id}


def verify_security(root: Path, release: str, manifest: dict) -> None:
    if manifest.get("security") != security_metadata(root, release):
        raise ValueError("Missing or inconsistent release security evidence")
