"""Tests for the Django-adapted audit service.

The Django version uses AuditEvent.objects.create() instead of SQLAlchemy
sessions.  These tests use Django's TestCase which wraps each test in a
transaction that is rolled back automatically.

Run with:
    python manage.py test imcp.tests.test_audit_service
"""
from django.test import TestCase

from imcp.models.audit import AuditEvent
from imcp.services.audit import AuditService, log_audit_event


class TestAuditService(TestCase):

    def test_log_event_basic(self):
        auditor = AuditService()
        event = auditor.log_event(
            actor="user@example.com",
            action="tool_call",
            status="success",
            correlation_id="corr-001",
        )
        self.assertIsNotNone(event)
        self.assertEqual(AuditEvent.objects.count(), 1)
        stored = AuditEvent.objects.get(correlation_id="corr-001")
        self.assertEqual(stored.actor, "user@example.com")
        self.assertEqual(stored.status, "success")

    def test_log_event_with_optional_fields(self):
        auditor = AuditService()
        auditor.log_event(
            actor="user2",
            action="service_create",
            status="success",
            correlation_id="corr-002",
            service_id=42,
            tool_name="getClaim",
            latency_ms=250,
            details={"request": "data"},
        )
        stored = AuditEvent.objects.get(correlation_id="corr-002")
        self.assertEqual(stored.service_id, 42)
        self.assertEqual(stored.tool_name, "getClaim")
        self.assertEqual(stored.latency_ms, 250)

    def test_log_event_redacts_sensitive_details(self):
        auditor = AuditService()
        auditor.log_event(
            actor="user3",
            action="tool_call",
            status="success",
            correlation_id="corr-003",
            details={
                "username": "john",
                "password": "secret123",
                "token": "Bearer abc",
                "data": "public",
            },
        )
        stored = AuditEvent.objects.get(correlation_id="corr-003")
        self.assertEqual(stored.details["username"], "john")
        self.assertEqual(stored.details["password"], "[REDACTED]")
        self.assertEqual(stored.details["token"], "[REDACTED]")
        self.assertEqual(stored.details["data"], "public")

    def test_log_event_failure_status(self):
        auditor = AuditService()
        auditor.log_event(
            actor="user4",
            action="tool_call",
            status="failure",
            correlation_id="corr-004",
            tool_name="updateClaim",
            details={"error": "Validation failed"},
        )
        stored = AuditEvent.objects.get(correlation_id="corr-004")
        self.assertEqual(stored.status, "failure")
        self.assertEqual(stored.tool_name, "updateClaim")

    def test_log_event_denied_status(self):
        auditor = AuditService()
        auditor.log_event(
            actor="user5",
            action="tool_call",
            status="denied",
            correlation_id="corr-005",
            tool_name="approveClaim",
        )
        stored = AuditEvent.objects.get(correlation_id="corr-005")
        self.assertEqual(stored.status, "denied")

    def test_log_event_latency(self):
        auditor = AuditService()
        auditor.log_event(
            actor="user6",
            action="tool_call",
            status="success",
            correlation_id="corr-006",
            latency_ms=1500,
        )
        stored = AuditEvent.objects.get(correlation_id="corr-006")
        self.assertEqual(stored.latency_ms, 1500)

    def test_auto_correlation_id(self):
        """log_event generates a UUID correlation_id when none is provided."""
        auditor = AuditService()
        event = auditor.log_event(
            actor="user7",
            action="tool_call",
            status="success",
        )
        self.assertIsNotNone(event)
        stored = AuditEvent.objects.filter(actor="user7").first()
        self.assertIsNotNone(stored)
        self.assertIsNotNone(stored.correlation_id)

    def test_global_log_audit_event(self):
        log_audit_event(
            actor="user8",
            action="test_action",
            status="success",
            correlation_id="corr-008",
            tool_name="testTool",
        )
        stored = AuditEvent.objects.get(correlation_id="corr-008")
        self.assertEqual(stored.tool_name, "testTool")
