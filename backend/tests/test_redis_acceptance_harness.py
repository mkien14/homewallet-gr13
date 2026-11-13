"""Regress the POSIX bind-mount permissions that failed on GitHub Actions."""
import importlib.util
import os
from pathlib import Path
import stat
from types import SimpleNamespace

from cryptography import x509
import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "run-redis-acceptance.py"
spec = importlib.util.spec_from_file_location("redis_acceptance_harness", SCRIPT)
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


@pytest.mark.parametrize("uid,gid", [(1001, 1001), (10001, 10001), (0, 0)])
def test_posix_redis_uses_the_private_directory_owners_uid_gid(monkeypatch, uid, gid):
    monkeypatch.setattr(harness, "os", SimpleNamespace(name="posix", getuid=lambda: uid, getgid=lambda: gid))
    assert harness.container_user() == f"{uid}:{gid}"


def test_windows_desktop_uses_the_fixture_uid(monkeypatch):
    monkeypatch.setattr(harness, "os", SimpleNamespace(name="nt"))
    assert harness.container_user() == "999:999"


def test_generated_key_stays_private_and_certificate_covers_localhost(tmp_path):
    before = stat.S_IMODE(tmp_path.stat().st_mode)
    harness.certificates(tmp_path)
    cert = x509.load_pem_x509_certificate((tmp_path / "ca.pem").read_bytes())
    assert cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName) == ["localhost"]
    assert stat.S_IMODE(tmp_path.stat().st_mode) == before
    if os.name == "posix":
        assert stat.S_IMODE((tmp_path / "server.key").stat().st_mode) == 0o600
        assert stat.S_IMODE((tmp_path / "ca.pem").stat().st_mode) == 0o600
