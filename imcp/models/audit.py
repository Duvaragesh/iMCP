"""Audit event model for tracking all system actions."""
from django.db import models


class AuditEvent(models.Model):
    """Audit log for all MCP tool calls and admin actions."""

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.CharField(max_length=255, db_index=True)     # User/service identity
    action = models.CharField(max_length=100, db_index=True)    # tool_call/service_create/etc
    service_id = models.IntegerField(null=True, blank=True, db_index=True)
    tool_name = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    status = models.CharField(max_length=50, db_index=True)     # success/failure/denied
    correlation_id = models.CharField(max_length=36, unique=True, db_index=True)  # UUID
    latency_ms = models.IntegerField(null=True, blank=True)
    details = models.JSONField(null=True, blank=True)            # Additional context (redacted)

    class Meta:
        app_label = "imcp"
        db_table = "imcp_audit_events"

    def __str__(self):
        return f"AuditEvent({self.id}, {self.actor}, {self.action}, {self.status})"
