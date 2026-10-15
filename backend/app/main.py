import logging
import os
import uuid

from flask import Flask, g, jsonify, request


def create_app() -> Flask:
    app = Flask(__name__)

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

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    @app.get("/api/ping")
    def ping():
        return jsonify(message="pong")

    @app.errorhandler(404)
    def not_found(_e):
        return jsonify(error={
            "code": "NOT_FOUND",
            "message": "Không tìm thấy",
            "request_id": g.get("request_id"),
        }), 404

    return app


app = create_app()