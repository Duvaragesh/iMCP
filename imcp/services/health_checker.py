"""Health check service for upstream services."""
from typing import Dict, Any
from datetime import datetime
import logging
import httpx

logger = logging.getLogger(__name__)


class HealthCheckResult:
    """Result of a service health check."""

    def __init__(
        self,
        service_id: int,
        service_name: str,
        reachable: bool,
        status_code: int = None,
        latency_ms: int = None,
        last_check: datetime = None,
        error: str = None,
    ):
        self.service_id = service_id
        self.service_name = service_name
        self.reachable = reachable
        self.status_code = status_code
        self.latency_ms = latency_ms
        self.last_check = last_check or datetime.utcnow()
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "service_id": self.service_id,
            "service_name": self.service_name,
            "reachable": self.reachable,
            "status_code": self.status_code,
            "latency_ms": self.latency_ms,
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "error": self.error,
        }


class HealthChecker:
    """Service health checker."""

    def __init__(self, timeout: float = 5.0):
        self.timeout = timeout

    def check_service_reachability(self, service) -> HealthCheckResult:
        """Check if a service is reachable.

        For file:// spec URLs: verifies the local spec file exists.
        For http/https URLs: sends a lightweight HEAD/GET to the service.
        """
        start_time = datetime.utcnow()

        # file:// — check that the local spec file exists
        if service.url.startswith("file://"):
            return self._check_file_url(service, start_time)

        # http/https — try to reach the server
        return self._check_http_url(service, start_time)

    def _check_file_url(self, service, start_time) -> HealthCheckResult:
        """Check a file:// spec URL by verifying the file exists on disk."""
        import os
        from urllib.request import url2pathname

        try:
            path = url2pathname(service.url[len("file://"):])
            # On Windows, /C:/... → C:/...
            if len(path) > 2 and path[0] == "/" and path[2] == ":":
                path = path[1:]
            exists = os.path.isfile(path)
            latency_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            return HealthCheckResult(
                service_id=service.id,
                service_name=service.name,
                reachable=exists,
                latency_ms=latency_ms,
                last_check=datetime.utcnow(),
                error=None if exists else f"Spec file not found: {path}",
            )
        except Exception as e:
            latency_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            return HealthCheckResult(
                service_id=service.id,
                service_name=service.name,
                reachable=False,
                latency_ms=latency_ms,
                last_check=datetime.utcnow(),
                error=f"File check error: {e}",
            )

    def _check_http_url(self, service, start_time) -> HealthCheckResult:
        """Check an http/https URL by sending a HEAD or GET request."""
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True, verify=False) as client:
                try:
                    response = client.head(service.url)
                except (httpx.HTTPStatusError, httpx.RequestError):
                    response = client.get(service.url)

            latency_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            reachable = 200 <= response.status_code < 400

            logger.info(
                f"Health check for service {service.id}: "
                f"{'reachable' if reachable else 'unreachable'}",
            )
            return HealthCheckResult(
                service_id=service.id,
                service_name=service.name,
                reachable=reachable,
                status_code=response.status_code,
                latency_ms=latency_ms,
                last_check=datetime.utcnow(),
                error=None if reachable else f"HTTP {response.status_code}",
            )

        except httpx.TimeoutException:
            latency_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            return HealthCheckResult(
                service_id=service.id,
                service_name=service.name,
                reachable=False,
                latency_ms=latency_ms,
                last_check=datetime.utcnow(),
                error="Timeout",
            )

        except httpx.RequestError as e:
            latency_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            return HealthCheckResult(
                service_id=service.id,
                service_name=service.name,
                reachable=False,
                latency_ms=latency_ms,
                last_check=datetime.utcnow(),
                error=str(e),
            )

        except Exception as e:
            latency_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            return HealthCheckResult(
                service_id=service.id,
                service_name=service.name,
                reachable=False,
                latency_ms=latency_ms,
                last_check=datetime.utcnow(),
                error=f"Error: {str(e)}",
            )


# Global health checker instance
health_checker = HealthChecker()


def check_service_reachability(service) -> HealthCheckResult:
    """Check service reachability."""
    return health_checker.check_service_reachability(service)
