"""Audit logging service — adapted for Django ORM."""
from typing import Dict, Any, Optional
import logging
import uuid
from datetime import datetime
from .redaction import redact_payload

logger = logging.getLogger(__name__)


class AuditService:
    """Audit event logging using Django ORM."""

    def log_event(
        self,
        actor: str,
        action: str,
        status: str,
        correlation_id: str = None,
        service_id: Optional[int] = None,
        tool_name: Optional[str] = None,
        latency_ms: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """
        Log audit event to database using Django ORM.

        Args:
            actor: User/service identity
            action: Action performed (e.g. tool_call, service_create)
            status: success / failure / denied
            correlation_id: Request correlation ID (generated if not provided)
            service_id: Service ID (optional)
            tool_name: Tool name (optional)
            latency_ms: Latency in milliseconds (optional)
            details: Additional details (will be redacted)
        """
        # Import inside function to avoid circular import at module load time
        from imcp.models.audit import AuditEvent

        if correlation_id is None:
            correlation_id = str(uuid.uuid4())

        redacted_details = redact_payload(details) if details else None

        try:
            event = AuditEvent.objects.create(
                actor=actor,
                action=action,
                service_id=service_id,
                tool_name=tool_name,
                status=status,
                correlation_id=correlation_id,
                latency_ms=latency_ms,
                details=redacted_details,
            )
            logger.info(
                f"Audit event logged: {action} by {actor}, "
                f"status={status}, correlation_id={correlation_id}"
            )
            return event
        except Exception as e:
            logger.error(f"Failed to log audit event: {e}")
            return None


# Global audit service instance
auditor = AuditService()


def log_audit_event(
    actor: str,
    action: str,
    status: str,
    correlation_id: str = None,
    **kwargs,
):
    """Log an audit event."""
    return auditor.log_event(
        actor=actor,
        action=action,
        status=status,
        correlation_id=correlation_id,
        **kwargs,
    )
