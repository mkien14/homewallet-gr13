"""Run Redis client acceptance on a disposable local TLS server, never on AWS.

Requires Docker plus cryptography and the backend test dependencies. --image
runs tests inside an existing test image with pytest and the application installed.
No production credentials or data are loaded; only this run's container is removed.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
import uuid

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


REDIS_IMAGE = "redis@sha256:2f66de68111e64c3927859f158f8e666066dae2b97d9f82770a6f37a5aa1c335"
ROOT = Path(__file__).resolve().parents[1]


def docker(*args):
    return subprocess.run(["docker", *args], check=True, capture_output=True, text=True).stdout.strip()


def container_user():
    # POSIX TemporaryDirectory is 0700. Match its owner instead of making its
    # private key/config readable to other host users. Desktop bind mounts on
    # Windows do not use the caller's POSIX UID, so use the fixture's normal UID.
    if os.name == "posix":
        return f"{os.getuid()}:{os.getgid()}"
    return "999:999"


def certificates(directory):
    now = datetime.datetime.now(datetime.timezone.utc)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "HomeWallet local Redis acceptance")])
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=1))
            .not_valid_after(now + datetime.timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
            .sign(key, hashes.SHA256()))
    (directory / "server.key").write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    (directory / "ca.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    # The POSIX container uses the caller's UID/GID and can read private files
    # without broadening the TemporaryDirectory's 0700 permissions.
    for path in directory.iterdir():
        path.chmod(0o600)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", help="Existing application test image containing pytest")
    args = parser.parse_args()
    docker("info", "--format", "{{.ServerVersion}}")
    name = "hw-redis-acceptance-" + uuid.uuid4().hex[:12]
    password = secrets.token_hex(24)
    with tempfile.TemporaryDirectory(prefix="homewallet-local-redis-") as temporary:
        directory = Path(temporary).resolve()
        if not directory.is_relative_to(Path(tempfile.gettempdir()).resolve()):
            raise ValueError("Unexpected temporary path")
        certificates(directory)
        (directory / "redis.conf").write_text(
            "bind 0.0.0.0\nport 0\ntls-port 6379\ntls-cert-file /tls/ca.pem\n"
            "tls-key-file /tls/server.key\ntls-ca-cert-file /tls/ca.pem\n"
            "tls-auth-clients no\nrequirepass " + password + "\nsave \"\"\nappendonly no\n",
            encoding="utf-8")
        (directory / "redis.conf").chmod(0o600)
        try:
            docker("run", "--detach", "--name", name, "--user", container_user(), "--read-only",
                   "--cap-drop", "ALL", "--tmpfs", "/data:rw,noexec,nosuid,size=16m",
                   "--publish", "127.0.0.1::6379",
                   "--mount", f"type=bind,source={directory},target=/tls,readonly",
                   REDIS_IMAGE, "redis-server", "/tls/redis.conf")
            # PING needs no password in argv and tests will verify trusted TLS/auth.
            ready = False
            for _ in range(40):
                state = json.loads(docker("inspect", name))[0]["State"]
                if not state["Running"]:
                    diagnostic = docker("logs", "--tail", "8", name).replace(password, "[redacted]")
                    raise RuntimeError(f"Disposable TLS Redis exited ({state['ExitCode']}): {diagnostic}")
                probe = subprocess.run(["docker", "exec", name, "redis-cli", "--tls",
                                        "--cacert", "/tls/ca.pem", "-h", "localhost", "PING"],
                                       capture_output=True, text=True)
                if "NOAUTH" in probe.stdout + probe.stderr:
                    ready = True
                    break
                time.sleep(0.25)
            if not ready:
                raise RuntimeError("Disposable TLS Redis did not become ready")
            metadata = json.loads(docker("inspect", name))[0]
            port = metadata["NetworkSettings"]["Ports"]["6379/tcp"][0]["HostPort"]
            env = dict(os.environ, PYTHON_DOTENV_DISABLED="1", AWS_EC2_METADATA_DISABLED="true",
                       HOMEWALLET_REDIS_ACCEPTANCE="1", HOMEWALLET_REDIS_TLS_HOST="localhost",
                       HOMEWALLET_REDIS_TLS_PORT=str(port), HOMEWALLET_REDIS_TLS_PASSWORD=password,
                       HOMEWALLET_REDIS_TLS_CA=str(directory / "ca.pem"))
            tests = ["tests/test_cache_client.py", "tests/test_redis_tls.py"]
            if args.image:
                env.update(HOMEWALLET_REDIS_TLS_PORT="6379", HOMEWALLET_REDIS_TLS_CA="/tls/ca.pem")
                command = ["docker", "run", "--rm", "--network", "container:" + name,
                           "--mount", f"type=bind,source={directory},target=/tls,readonly",
                           "--mount", f"type=bind,source={ROOT / 'backend' / 'tests'},target=/srv/tests,readonly"]
                for key in ("PYTHON_DOTENV_DISABLED", "AWS_EC2_METADATA_DISABLED",
                            "HOMEWALLET_REDIS_ACCEPTANCE", "HOMEWALLET_REDIS_TLS_HOST",
                            "HOMEWALLET_REDIS_TLS_PORT", "HOMEWALLET_REDIS_TLS_PASSWORD", "HOMEWALLET_REDIS_TLS_CA"):
                    command.extend(["--env", key])
                command.extend(["--entrypoint", "python", args.image, "-m", "pytest", "-p", "no:cacheprovider", *tests, "-q"])
            else:
                command = [sys.executable, "-m", "pytest", *tests, "-q"]
            result = subprocess.run(command, cwd=ROOT / "backend", env=env)
            print(json.dumps({"event": "LOCAL_REDIS_TLS_ACCEPTANCE", "exit_code": result.returncode,
                              "server_image": REDIS_IMAGE, "aws_mutations": False}))
            return result.returncode
        finally:
            # Name is generated here; never remove an unrelated container or volume.
            subprocess.run(["docker", "rm", "--force", name], capture_output=True, text=True)


if __name__ == "__main__":
    raise SystemExit(main())
