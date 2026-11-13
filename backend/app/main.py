import logging
import os
import uuid
import hmac

from flask import Flask, g, jsonify, request
from flask.json.provider import DefaultJSONProvider

from . import (
    budgets,
    community,
    dashboard,
    households,
    notifications,
    receipts,
    recurring_bills,
    transactions,
)
from .config import load_config
from .db import close_db
from .errors import ApiError, register_error_handlers
from .readiness import Readiness
from .release_policy import validate_release_config


class UTF8JSONProvider(DefaultJSONProvider):
    ensure_ascii = False


def create_app(test_config=None) -> Flask:
    app = Flask(__name__)
    app.json = UTF8JSONProvider(app)
    app.config.update(load_config())
    if test_config:
        app.config.update(test_config)
    readiness = Readiness()
    validate_release_config(app.config)

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format='{"time":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
    )

    @app.before_request
    def attach_request_id():
        g.request_id = str(uuid.uuid4())
        expected = app.config.get("ORIGIN_VERIFY_HEADER")
        if request.path not in {"/health", "/ready"} and expected and not hmac.compare_digest(
            request.headers.get("X-Origin-Verify", "").encode(), expected.encode()
        ):
            raise ApiError(403, "ORIGIN_FORBIDDEN", "Không được phép truy cập")

    @app.after_request
    def add_request_id(resp):
        resp.headers["X-Request-Id"] = g.get("request_id", "")
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        if g.get("retry_after"):
            resp.headers["Retry-After"] = str(g.retry_after)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return resp


    app.teardown_appcontext(close_db)
    register_error_handlers(app)
    app.register_blueprint(households.bp)
    app.register_blueprint(community.bp)
    app.register_blueprint(notifications.bp)
    app.register_blueprint(budgets.bp)
    app.register_blueprint(receipts.bp)
    app.register_blueprint(recurring_bills.bp)
    app.register_blueprint(transactions.bp)
    app.register_blueprint(dashboard.bp)
    
    @app.get("/health")
    @app.get("/api/health")
    def health():
        return jsonify(status="ok")

    @app.get("/ready")
    @app.get("/api/ready")
    def ready():
        ok = readiness.check(app.config)
        response = jsonify(status="ready" if ok else "unavailable")
        response.headers["Cache-Control"] = "no-store"
        return response, 200 if ok else 503

    @app.get("/api/release")
    def release():
        return jsonify(release=app.config["APP_RELEASE"])

    @app.get("/api/ping")
    def ping():
        return jsonify(message="pong")

    return app


app = create_app()
