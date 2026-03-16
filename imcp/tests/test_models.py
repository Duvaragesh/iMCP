"""Django ORM model tests.

Run with:
    python manage.py test imcp.tests.test_models
"""
import hashlib
from datetime import datetime, timedelta

from django.test import TestCase
from django.utils import timezone

from imcp.models.service import Service
from imcp.models.audit import AuditEvent
from imcp.models.api_key import APIKey
from imcp.models.tool_cache import ToolCacheMetadata


class TestServiceModel(TestCase):

    def _make_service(self, **kwargs):
        defaults = {
            "name": "TestService",
            "spec_type": "OpenAPI",
            "url": "https://api.example.com/openapi.json",
            "category": "Claims",
        }
        defaults.update(kwargs)
        return Service.objects.create(**defaults)

    def test_create_service(self):
        svc = self._make_service()
        self.assertIsNotNone(svc.id)
        self.assertEqual(svc.name, "TestService")
        self.assertTrue(svc.enabled)

    def test_unique_name(self):
        self._make_service()
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            self._make_service()

    def test_defaults(self):
        svc = self._make_service()
        self.assertTrue(svc.enabled)
        self.assertIsNone(svc.allowlist)
        self.assertIsNone(svc.denylist)
        self.assertIsNone(svc.auth_type)

    def test_json_fields(self):
        svc = self._make_service(
            allowlist=["getPolicy", "getClaim"],
            denylist=["deletePolicy"],
        )
        svc.refresh_from_db()
        self.assertEqual(svc.allowlist, ["getPolicy", "getClaim"])
        self.assertEqual(svc.denylist, ["deletePolicy"])

    def test_str(self):
        svc = self._make_service()
        self.assertIn("TestService", str(svc))

    def test_auto_timestamps(self):
        svc = self._make_service()
        self.assertIsNotNone(svc.created_at)
        self.assertIsNotNone(svc.updated_at)


class TestAuditEventModel(TestCase):

    def test_create_audit_event(self):
        event = AuditEvent.objects.create(
            actor="user@example.com",
            action="tool_call",
            status="success",
            correlation_id="corr-001",
            tool_name="getClaim",
            latency_ms=120,
        )
        self.assertIsNotNone(event.id)
        self.assertEqual(event.actor, "user@example.com")
        self.assertEqual(event.status, "success")

    def test_unique_correlation_id(self):
        AuditEvent.objects.create(actor="u", action="a", status="success", correlation_id="corr-dup")
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            AuditEvent.objects.create(actor="u", action="a", status="success", correlation_id="corr-dup")

    def test_details_json(self):
        event = AuditEvent.objects.create(
            actor="u",
            action="tool_call",
            status="success",
            correlation_id="corr-002",
            details={"request": "data", "response": "result"},
        )
        event.refresh_from_db()
        self.assertEqual(event.details["request"], "data")

    def test_str(self):
        event = AuditEvent.objects.create(
            actor="u", action="a", status="success", correlation_id="corr-003"
        )
        self.assertIn("success", str(event))


class TestAPIKeyModel(TestCase):

    def _make_key(self, raw_key="imcp_testkey1234567890", **kwargs):
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        defaults = {
            "key_hash": key_hash,
            "key_prefix": raw_key[:12],
            "name": "Test Key",
            "user_id": "user@example.com",
            "roles": ["admin"],
        }
        defaults.update(kwargs)
        return APIKey.objects.create(**defaults)

    def test_create_api_key(self):
        key = self._make_key()
        self.assertIsNotNone(key.id)
        self.assertEqual(key.name, "Test Key")
        self.assertTrue(key.enabled)
        self.assertFalse(key.revoked)

    def test_is_valid_active_key(self):
        key = self._make_key()
        self.assertTrue(key.is_valid())

    def test_is_valid_disabled_key(self):
        key = self._make_key(raw_key="imcp_disabled000000000", enabled=False)
        self.assertFalse(key.is_valid())

    def test_is_valid_revoked_key(self):
        key = self._make_key(raw_key="imcp_revoked000000000", revoked=True)
        self.assertFalse(key.is_valid())

    def test_is_valid_expired_key(self):
        past = timezone.now() - timedelta(days=1)
        key = self._make_key(raw_key="imcp_expired0000000000", expires_at=past)
        self.assertFalse(key.is_valid())

    def test_is_valid_not_yet_expired(self):
        future = timezone.now() + timedelta(days=30)
        key = self._make_key(raw_key="imcp_future00000000000", expires_at=future)
        self.assertTrue(key.is_valid())

    def test_roles_json(self):
        key = self._make_key(roles=["read", "write"])
        key.refresh_from_db()
        self.assertEqual(key.roles, ["read", "write"])


class TestToolCacheMetadataModel(TestCase):

    def setUp(self):
        self.service = Service.objects.create(
            name="CachedService",
            spec_type="MCP_JSON",
            url="https://api.example.com/tools.json",
            category="Tools",
        )

    def test_create_cache_entry(self):
        entry = ToolCacheMetadata.objects.create(
            service=self.service,
            spec_hash="abc123def456" * 4,  # 48 chars < 64
            ttl=3600,
            tools_json=[{"name": "tool1"}, {"name": "tool2"}],
        )
        self.assertIsNotNone(entry.id)
        self.assertEqual(entry.service, self.service)

    def test_tools_json_list(self):
        tools = [{"name": "t1", "description": "d1"}, {"name": "t2", "description": "d2"}]
        entry = ToolCacheMetadata.objects.create(
            service=self.service,
            spec_hash="a" * 64,
            ttl=3600,
            tools_json=tools,
        )
        entry.refresh_from_db()
        self.assertEqual(len(entry.tools_json), 2)
        self.assertEqual(entry.tools_json[0]["name"], "t1")

    def test_cascade_delete(self):
        ToolCacheMetadata.objects.create(
            service=self.service,
            spec_hash="b" * 64,
            ttl=3600,
            tools_json=[],
        )
        self.assertEqual(ToolCacheMetadata.objects.count(), 1)
        self.service.delete()
        self.assertEqual(ToolCacheMetadata.objects.count(), 0)

    def test_str(self):
        entry = ToolCacheMetadata.objects.create(
            service=self.service,
            spec_hash="c" * 64,
            ttl=3600,
            tools_json=[],
        )
        self.assertIn("CachedService", str(entry))
