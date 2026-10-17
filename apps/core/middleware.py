import logging
import uuid
from contextvars import ContextVar

_request_id: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIDLogFilter(logging.Filter):
    def filter(self, record):
        record.request_id = _request_id.get()
        return True


class RequestIDMiddleware:
    """Attach/propagate X-Request-ID (also into logs)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        token = _request_id.set(rid)
        request.request_id = rid
        try:
            response = self.get_response(request)
        finally:
            _request_id.reset(token)
        response["X-Request-ID"] = rid
        return response
