"""Publish a reviewed candidate after the running production API passes its gate.

Uploads assets before index.html, keeps old assets, then invalidates CloudFront.
No migrations, service changes, mail, or schedule changes are performed.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import mimetypes
import re
import sys
import urllib.request
from pathlib import Path

import boto3


def load_gate():
    spec = importlib.util.spec_from_file_location("production_gate", Path(__file__).with_name("production-preflight.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.evaluate


def verify_artifact(root, release):
    if not re.fullmatch(r"[a-f0-9]{40}", release):
        raise ValueError("Expected a reviewed 40-character release commit")
    expected = {}
    for line in (root / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        path = (root / name).resolve()
        if not re.fullmatch(r"[a-f0-9]{64}", digest) or not path.is_relative_to(root) or not path.is_file():
            raise ValueError("Invalid artifact manifest")
        if path in expected:
            raise ValueError("Duplicate artifact entry")
        with path.open("rb") as source:
            actual = hashlib.file_digest(source, "sha256").hexdigest()
        if actual != digest:
            raise ValueError("Artifact hash mismatch")
        expected[path] = digest
    actual_paths = {path.resolve() for path in root.rglob("*") if path.is_file() and path != root / "SHA256SUMS"}
    if set(expected) != actual_paths or any(path.is_symlink() for path in root.rglob("*")):
        raise ValueError("Artifact file set mismatch or symlink")
    profiles = []
    for name in ("manifest.json", "frontend/release.json"):
        manifest = json.loads((root / name).read_text(encoding="utf-8"))
        if manifest.get("release") != release or type(manifest.get("ocr_enabled")) is not bool or manifest.get("channel") != "production-candidate":
            raise ValueError("Wrong candidate release or feature profile")
        registration = manifest.get("public_registration_enabled", False)
        if type(registration) is not bool:
            raise ValueError("Invalid candidate registration profile")
        profiles.append((manifest["ocr_enabled"], registration))
    if profiles[0] != profiles[1]:
        raise ValueError("Candidate feature profiles differ")
    if not (root / "frontend/index.html").is_file() or not (root / "backend.tar").is_file():
        raise ValueError("Incomplete release candidate")
    spec = importlib.util.spec_from_file_location("release_security", Path(__file__).with_name("release-security.py"))
    security = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(security)
    security.verify_security(root, release, json.loads((root / "manifest.json").read_text(encoding="utf-8")))


def verify_running_image(session, settings, root):
    """Bind the approved container evidence to the API image actually deployed."""
    ecs = session.client("ecs")
    service = ecs.describe_services(cluster=settings["cluster"], services=[settings["api_service"]])["services"][0]
    task = ecs.describe_task_definition(taskDefinition=service["taskDefinition"])["taskDefinition"]
    image = next(x["image"] for x in task["containerDefinitions"] if x["name"] == "api")
    container = next(x for x in task["containerDefinitions"] if x["name"] == "api")
    env = {x["name"]: x["value"] for x in container.get("environment", [])}
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest["ocr_enabled"] != (env.get("OCR_ENABLED", "false").lower() in {"true", "1"}):
        raise ValueError("Candidate OCR profile differs from the running API")
    if manifest.get("public_registration_enabled", False) != (env.get("PRODUCTION_PUBLIC_REGISTRATION", "false").lower() == "true"):
        raise ValueError("Candidate registration profile differs from the running API")
    prefix = settings["account"] + ".dkr.ecr." + settings["region"] + ".amazonaws.com/"
    if not image.startswith(prefix) or "@sha256:" not in image:
        raise ValueError("Expected immutable image in the reviewed account")
    repository, digest = image[len(prefix):].rsplit("@", 1)
    response = session.client("ecr").batch_get_image(
        registryId=settings["account"], repositoryName=repository,
        imageIds=[{"imageDigest": digest}],
        acceptedMediaTypes=["application/vnd.docker.distribution.manifest.v2+json", "application/vnd.oci.image.manifest.v1+json"],
    )
    if response.get("failures") or len(response.get("images", [])) != 1:
        raise ValueError("Cannot resolve deployed image manifest")
    deployed = json.loads(response["images"][0]["imageManifest"])
    expected = json.loads((root / "manifest.json").read_text(encoding="utf-8"))["security"]["image_id"]
    if deployed.get("config", {}).get("digest") != expected:
        raise ValueError("Deployed API image differs from the scanned candidate")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings")
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--release", required=True)
    parser.add_argument("--profile")
    parser.add_argument("--verify-only", action="store_true", help="Check candidate integrity locally, without calling AWS")
    parser.add_argument("--apply", action="store_true", help="Publish after all gates pass; default is read-only")
    args = parser.parse_args()
    root = Path(args.artifact_dir).resolve()
    verify_artifact(root, args.release)
    if args.verify_only:
        print(json.dumps({"status": "ARTIFACT_INTEGRITY_VERIFIED", "release": args.release}))
        return 0
    if not args.settings:
        parser.error("--settings is required unless --verify-only is used")
    settings = json.loads(Path(args.settings).read_text(encoding="utf-8-sig"))
    session = boto3.Session(profile_name=args.profile, region_name=settings["region"])
    checks = load_gate()(settings, session)
    if not checks or not all(check["pass"] for check in checks):
        print(json.dumps({"status": "NO_GO", "checks": checks}))
        return 2
    verify_running_image(session, settings, root)
    with urllib.request.urlopen(settings["public_url"] + "/api/release", timeout=15) as response:
        if json.load(response).get("release") != args.release:
            raise ValueError("Running API does not match the candidate commit")
    frontend = root / "frontend"
    files = sorted((path for path in frontend.rglob("*") if path.is_file()),
                   key=lambda path: (path.name == "index.html", path.as_posix()))
    if not args.apply:
        print(json.dumps({"status": "READY_TO_PUBLISH", "release": args.release, "files": len(files)}))
        return 0
    s3 = session.client("s3")
    for path in files:
        key = path.relative_to(frontend).as_posix()
        cache = "public,max-age=31536000,immutable" if key.startswith("assets/") else "no-store"
        content_types = {".js": "text/javascript", ".css": "text/css", ".html": "text/html; charset=utf-8", ".json": "application/json"}
        with path.open("rb") as body:
            s3.put_object(Bucket=settings["frontend_bucket"], Key=key, Body=body,
                          ExpectedBucketOwner=settings["account"], CacheControl=cache,
                          ContentType=content_types.get(path.suffix, mimetypes.guess_type(key)[0] or "application/octet-stream"))
    import uuid
    session.client("cloudfront").create_invalidation(
        DistributionId=settings["distribution_id"],
        InvalidationBatch={"Paths": {"Quantity": 1, "Items": ["/*"]}, "CallerReference": str(uuid.uuid4())})
    print(json.dumps({"status": "PUBLISHED_INVALIDATION_REQUESTED", "release": args.release, "files": len(files)}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Do not print AWS request details, presigned URLs or public user data.
        print(json.dumps({"status": "FAILED", "error_type": type(exc).__name__}), file=sys.stderr)
        raise SystemExit(1)
