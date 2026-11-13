"""Prevent requirements-only updates from disagreeing with the runtime lock."""
import hashlib
from pathlib import Path
import re

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


ROOT = Path(__file__).resolve().parents[1]


def test_all_direct_requirements_are_satisfied_by_hash_locked_versions():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    lock = (ROOT / "requirements.lock").read_text(encoding="utf-8")
    versions = {
        canonicalize_name(name): version
        for name, version in re.findall(r"^([a-zA-Z0-9_.-]+)==([^\s\\]+)", lock, re.MULTILINE)
    }
    for line in requirements.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        requirement = Requirement(line)
        assert versions[canonicalize_name(requirement.name)] in requirement.specifier
    digest = hashlib.sha256(requirements.encode("utf-8")).hexdigest()
    assert f"# requirements.txt SHA256 (LF): {digest}" in lock
