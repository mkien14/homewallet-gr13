import time

import jwt
import pymysql
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app import auth, users
from app.main import create_app

ISS = "https://cognito-idp.ap-southeast-1.amazonaws.com/ap-southeast-1_TEST"
CLIENT = "testclient"


@pytest.fixture(scope="session")
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def app(monkeypatch, rsa_key):
    app = create_app({
        "TESTING": True,
        "COGNITO_ISSUER": ISS,
        "COGNITO_JWKS_URI": "http://invalid.local/jwks.json",
        "COGNITO_CLIENT_IDS": [CLIENT],
        "COGNITO_HOSTED_UI": None,
        "DB_HOST": "localhost", "DB_PORT": 3307, "DB_USER": "root",
        "DB_PASSWORD": "devpass", "DB_NAME": "homewallet", "DB_SSL_CA": None,
    })
    monkeypatch.setattr(auth, "signing_key_for", lambda token, cfg: rsa_key.public_key())
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def make_token(rsa_key):
    def _make(key=None, algorithm="RS256", **over):
        now = int(time.time())
        claims = {"sub": "sub-a", "iss": ISS, "client_id": CLIENT, "token_use": "access",
                  "scope": "openid email", "iat": now, "exp": now + 3600}
        claims.update(over)
        return jwt.encode(claims, key or rsa_key, algorithm=algorithm, headers={"kid": "k1"})
    return _make


@pytest.fixture
def db_app(app, monkeypatch):
    c = app.config
    if c["DB_HOST"] not in ("localhost", "127.0.0.1"):
        pytest.skip("Chỉ chạy kiểm thử DB trên máy cục bộ")
    try:
        conn = pymysql.connect(host=c["DB_HOST"], port=c["DB_PORT"], user=c["DB_USER"],
                               password=c["DB_PASSWORD"], database=c["DB_NAME"], connect_timeout=2)
    except Exception:
        pytest.skip("Không kết nối được MySQL cục bộ (docker start hw-mysql)")
    with conn.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        for t in ("household_members", "households", "users"):
            cur.execute(f"TRUNCATE TABLE {t}")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
    conn.commit()
    conn.close()
    monkeypatch.setattr(users, "fetch_email", lambda token, claims, cfg: claims["sub"] + "@test.local")
    return app