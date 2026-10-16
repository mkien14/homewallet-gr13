import logging
import os
import uuid

from flask import Flask, g, jsonify, request

from . import households
from .config import load_config
from .db import close_db
from .errors import register_error_handlers

def create_app(test_config=None) -> Flask:
    app = Flask(__name__)
    app.json.ensure_ascii = False  
    app.config.update(load_config())
    if test_config:
        app.config.update(test_config)

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format='{"time":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
    )

    @app.before_request
    def attach_request_id():
        g.request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())

    @app.after_request
    def add_request_id(resp):
        resp.headers["X-Request-Id"] = g.get("request_id", "")
        return resp

    app.teardown_appcontext(close_db)
    register_error_handlers(app)
    app.register_blueprint(households.bp)

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    @app.get("/api/ping")
    def ping():
        return jsonify(message="pong")

    return app


app = create_app()