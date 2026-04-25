"""
Centralised DRF exception handler.
Normalises all error responses to a consistent shape:
  { "error": "...", "detail": {...} }
"""
import logging
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        payload = {
            "error": _status_label(response.status_code),
            "detail": response.data,
        }
        response.data = payload
        return response

    # Unhandled exception — log it, return 500
    logger.exception("Unhandled exception in %s", context.get("view"))
    return Response(
        {"error": "internal_server_error", "detail": "An unexpected error occurred."},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def _status_label(code: int) -> str:
    labels = {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        405: "method_not_allowed",
        422: "unprocessable_entity",
        429: "too_many_requests",
        500: "internal_server_error",
    }
    return labels.get(code, "error")
