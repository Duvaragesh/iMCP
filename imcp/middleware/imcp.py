"""Django middleware for iMCP: Correlation ID and request logging."""
import uuid
import logging

logger = logging.getLogger(__name__)


class CorrelationIDMiddleware:
    """Add a unique correlation ID to every request.

    Reads X-Correlation-ID from incoming headers (or generates a new UUID),
    stores it on request.imcp_correlation_id, and adds it to the response.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        request.imcp_correlation_id = correlation_id

        response = self.get_response(request)
        response["X-Correlation-ID"] = correlation_id
        return response


class RequestLoggingMiddleware:
    """Log every request and response with correlation ID."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        correlation_id = getattr(request, "imcp_correlation_id", "unknown")

        logger.info(
            "request_received",
            extra={
                "method": request.method,
                "path": request.path,
                "correlation_id": correlation_id,
            },
        )

        response = self.get_response(request)

        logger.info(
            "request_completed",
            extra={
                "method": request.method,
                "path": request.path,
                "status_code": response.status_code,
                "correlation_id": correlation_id,
            },
        )

        return response
