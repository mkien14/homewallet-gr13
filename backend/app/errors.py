from flask import current_app, g, jsonify


class ApiError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def error_response(status, code, message):
    body = {"error": {"code": code, "message": message, "request_id": g.get("request_id")}}
    return jsonify(body), status


def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def _api_error(e):
        return error_response(e.status, e.code, e.message)

    @app.errorhandler(404)
    def _not_found(_e):
        return error_response(404, "NOT_FOUND", "Không tìm thấy")

    @app.errorhandler(405)
    def _method(_e):
        return error_response(405, "METHOD_NOT_ALLOWED", "Phương thức không được hỗ trợ")

    @app.errorhandler(500)
    def _internal(e):
        current_app.logger.exception("unhandled error", exc_info=getattr(e, "original_exception", e))
        return error_response(500, "INTERNAL", "Lỗi hệ thống")