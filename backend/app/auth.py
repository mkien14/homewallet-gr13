import functools

import jwt
from flask import current_app, g, request
from jwt import PyJWKClient

from . import users
from .errors import ApiError

_clients = {}


def signing_key_for(token, cfg):
    uri = cfg["COGNITO_JWKS_URI"]
    client = _clients.get(uri)
    if client is None:
        client = _clients[uri] = PyJWKClient(uri, cache_keys=True, lifespan=3600, timeout=5)
    return client.get_signing_key_from_jwt(token).key


def verify_token(token, cfg):
    if not cfg.get("COGNITO_ISSUER") or not cfg.get("COGNITO_CLIENT_IDS"):
        raise ApiError(500, "AUTH_NOT_CONFIGURED", "Máy chủ chưa cấu hình xác thực")
    try:
        key = signing_key_for(token, cfg)
        claims = jwt.decode(
            token, key, algorithms=["RS256"], issuer=cfg["COGNITO_ISSUER"],
            options={"require": ["exp", "iss", "sub"], "verify_aud": False},
        )
    except jwt.ExpiredSignatureError:
        raise ApiError(401, "TOKEN_EXPIRED", "Token đã hết hạn")
    except jwt.PyJWKClientConnectionError:
        raise ApiError(503, "AUTH_UNAVAILABLE", "Không lấy được khóa xác thực, thử lại sau")
    except jwt.PyJWTError:
        raise ApiError(401, "INVALID_TOKEN", "Token không hợp lệ")

    if claims.get("token_use") != "access":
        raise ApiError(401, "INVALID_TOKEN", "Cần access token")
    if claims.get("client_id") not in cfg["COGNITO_CLIENT_IDS"]:
        raise ApiError(401, "INVALID_TOKEN", "Token không dành cho ứng dụng này")
    return claims


def require_auth(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        scheme, _, token = request.headers.get("Authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise ApiError(401, "UNAUTHENTICATED", "Thiếu hoặc sai định dạng token")
        token = token.strip()
        g.claims = verify_token(token, current_app.config)
        g.user = users.get_or_create_user(g.claims, token)
        return fn(*args, **kwargs)
    return wrapper