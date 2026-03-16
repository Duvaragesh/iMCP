"""Tests for MCP views (health, JSON-RPC 2.0 dispatcher, REST tools endpoints).

Run with:
    python manage.py test imcp.tests.test_mcp_views
"""
import json
import hashlib
from unittest.mock import patch, MagicMock

from django.test import TestCase, Client
from django.urls import reverse

from imcp.models.service import Service
from imcp.models.api_key import APIKey


def _make_api_key(raw="imcp_testviews1234567890"):
    """Create an APIKey record and return the raw key string."""
    APIKey.objects.create(
        key_hash=hashlib.sha256(raw.encode()).hexdigest(),
        key_prefix=raw[:12],
        name="Test",
        user_id="tester",
        roles=["admin"],
    )
    return raw


class TestHealthCheck(TestCase):

    def test_health_endpoint(self):
        response = self.client.get(reverse("imcp-health"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")


class TestJsonRPC(TestCase):

    def setUp(self):
        self.raw_key = _make_api_key()
        self.auth_header = {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _post(self, body):
        return self.client.post(
            reverse("imcp-jsonrpc"),
            data=json.dumps(body),
            content_type="application/json",
            **self.auth_header,
        )

    def test_initialize(self):
        resp = self._post({"jsonrpc": "2.0", "method": "initialize", "id": 1})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["jsonrpc"], "2.0")
        self.assertIn("result", data)

    def test_tools_list_empty(self):
        resp = self._post({"jsonrpc": "2.0", "method": "tools/list", "id": 2})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("result", data)
        self.assertIn("tools", data["result"])

    def test_unknown_method(self):
        resp = self._post({"jsonrpc": "2.0", "method": "unknown/method", "id": 3})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("error", data)
        self.assertEqual(data["error"]["code"], -32601)

    def test_invalid_json(self):
        resp = self.client.post(
            reverse("imcp-jsonrpc"),
            data="not-json",
            content_type="application/json",
            **self.auth_header,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("error", data)

    def test_missing_auth(self):
        resp = self.client.post(
            reverse("imcp-jsonrpc"),
            data=json.dumps({"jsonrpc": "2.0", "method": "initialize", "id": 1}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401)

    def test_tools_call_missing_name(self):
        resp = self._post({
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"arguments": {}},
            "id": 4,
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("error", data)


class TestRestToolsEndpoints(TestCase):

    def setUp(self):
        self.raw_key = _make_api_key("imcp_resttools123456789")
        self.auth_header = {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def test_list_tools_empty(self):
        resp = self.client.post(
            reverse("imcp-tools-list"),
            data=json.dumps({}),
            content_type="application/json",
            **self.auth_header,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("tools", data)
        self.assertEqual(data["tools"], [])

    def test_call_tool_missing_name(self):
        resp = self.client.post(
            reverse("imcp-tools-call"),
            data=json.dumps({"arguments": {}}),
            content_type="application/json",
            **self.auth_header,
        )
        self.assertEqual(resp.status_code, 400)

    def test_call_tool_not_found(self):
        resp = self.client.post(
            reverse("imcp-tools-call"),
            data=json.dumps({"name": "nonExistentTool", "arguments": {}}),
            content_type="application/json",
            **self.auth_header,
        )
        self.assertIn(resp.status_code, [400, 404, 500])

    def test_list_tools_requires_auth(self):
        resp = self.client.post(
            reverse("imcp-tools-list"),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401)
