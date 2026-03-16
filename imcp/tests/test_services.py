"""Service-layer tests — ported from backend/tests/ with updated import paths.

These tests cover pure-Python service modules that are framework-agnostic
and do NOT require database access.  Run with:

    python manage.py test imcp.tests.test_services
"""
import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


# ---------------------------------------------------------------------------
# Redaction service
# ---------------------------------------------------------------------------

class TestRedactionService(unittest.TestCase):

    def _make_redactor(self, patterns=None):
        from imcp.services.redaction import RedactionService
        return RedactionService(patterns=patterns or ["password", "token"])

    def test_redact_simple_dict(self):
        redactor = self._make_redactor()
        payload = {
            "username": "john",
            "password": "secret123",
            "token": "abc123",
            "email": "john@example.com",
        }
        result = redactor.redact_payload(payload)
        self.assertEqual(result["username"], "john")
        self.assertEqual(result["password"], "[REDACTED]")
        self.assertEqual(result["token"], "[REDACTED]")
        self.assertEqual(result["email"], "john@example.com")

    def test_redact_nested_dict(self):
        redactor = self._make_redactor(["secret"])
        payload = {"user": {"name": "john", "secret_key": "hidden"}, "data": "public"}
        result = redactor.redact_payload(payload)
        self.assertEqual(result["user"]["name"], "john")
        self.assertEqual(result["user"]["secret_key"], "[REDACTED]")
        self.assertEqual(result["data"], "public")

    def test_redact_list(self):
        redactor = self._make_redactor(["password"])
        payload = [{"password": "s1"}, {"password": "s2"}, {"username": "john"}]
        result = redactor.redact_payload(payload)
        self.assertEqual(result[0]["password"], "[REDACTED]")
        self.assertEqual(result[1]["password"], "[REDACTED]")
        self.assertEqual(result[2]["username"], "john")

    def test_redact_case_insensitive(self):
        redactor = self._make_redactor(["token"])
        payload = {"Token": "v1", "TOKEN": "v2", "token": "v3"}
        result = redactor.redact_payload(payload)
        for key in payload:
            self.assertEqual(result[key], "[REDACTED]")

    def test_redact_primitive_types(self):
        redactor = self._make_redactor()
        self.assertEqual(redactor.redact_payload("hello"), "hello")
        self.assertEqual(redactor.redact_payload(123), 123)
        self.assertTrue(redactor.redact_payload(True))
        self.assertIsNone(redactor.redact_payload(None))

    def test_global_redact_function(self):
        from imcp.services.redaction import redact_payload
        payload = {"username": "john", "password": "secret", "authorization": "Bearer token"}
        result = redact_payload(payload)
        self.assertEqual(result["username"], "john")
        self.assertEqual(result["password"], "[REDACTED]")
        self.assertEqual(result["authorization"], "[REDACTED]")


# ---------------------------------------------------------------------------
# Cache service
# ---------------------------------------------------------------------------

class TestCacheService(unittest.TestCase):

    def _make_cache(self, max_size=10, ttl=3600):
        from imcp.services.cache import CacheService
        return CacheService(max_size=max_size, ttl=ttl)

    def test_cache_get_set(self):
        cache = self._make_cache()
        cache.set("test_key", {"data": "value"})
        self.assertEqual(cache.get("test_key"), {"data": "value"})

    def test_cache_miss(self):
        cache = self._make_cache()
        self.assertIsNone(cache.get("nonexistent"))

    def test_cache_delete(self):
        cache = self._make_cache()
        cache.set("key", "value")
        cache.delete("key")
        self.assertIsNone(cache.get("key"))

    def test_cache_clear(self):
        cache = self._make_cache()
        cache.set("k1", "v1")
        cache.set("k2", "v2")
        cache.clear()
        self.assertIsNone(cache.get("k1"))
        self.assertIsNone(cache.get("k2"))

    def test_cache_stats(self):
        cache = self._make_cache()
        cache.set("k1", "v1")
        cache.get("k1")   # hit
        cache.get("k2")   # miss
        stats = cache.get_stats()
        self.assertEqual(stats["size"], 1)
        self.assertEqual(stats["max_size"], 10)
        self.assertEqual(stats["hits"], 1)
        self.assertEqual(stats["misses"], 1)
        self.assertAlmostEqual(stats["hit_rate"], 50.0)

    def test_get_set_cached_tools(self):
        from imcp.services.cache import cache, get_cached_tools, set_cached_tools
        cache.clear()
        self.assertIsNone(get_cached_tools("svc_1"))
        tools = [{"name": "t1"}, {"name": "t2"}]
        set_cached_tools("svc_1", tools)
        self.assertEqual(get_cached_tools("svc_1"), tools)

    def test_invalidate_service_cache(self):
        from imcp.services.cache import cache, set_cached_tools, get_cached_tools, invalidate_service_cache
        cache.clear()
        set_cached_tools("svc_2", [{"name": "t"}])
        invalidate_service_cache("svc_2")
        self.assertIsNone(get_cached_tools("svc_2"))


# ---------------------------------------------------------------------------
# MCP JSON parser
# ---------------------------------------------------------------------------

class TestMCPJsonParser(unittest.TestCase):

    def _sample_spec(self):
        return {
            "name": "test-tools",
            "version": "1.0.0",
            "description": "Test MCP tools",
            "tools": [
                {
                    "name": "getThing",
                    "description": "Get a thing",
                    "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
                    "endpoint": {"method": "GET", "path": "/api/things/{id}", "baseUrl": "https://api.example.com"},
                },
                {
                    "name": "listThings",
                    "description": "List things",
                    "inputSchema": {"type": "object", "properties": {}, "required": []},
                    "endpoint": {"method": "GET", "path": "/api/things", "baseUrl": "https://api.example.com"},
                },
                {
                    "name": "createThing",
                    "description": "Create a thing",
                    "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
                    "endpoint": {"method": "POST", "path": "/api/things", "baseUrl": "https://api.example.com"},
                },
            ],
        }

    def test_parse_from_file(self):
        import tempfile, os, json
        from imcp.services.mcp_json_parser import MCPJsonParser, MCPJsonMetadata
        spec = self._sample_spec()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(spec, f)
            fname = f.name
        try:
            result = MCPJsonParser().parse_mcp_json(fname)
            self.assertIsInstance(result, MCPJsonMetadata)
            self.assertEqual(result.name, "test-tools")
            self.assertEqual(len(result.tools), 3)
        finally:
            os.unlink(fname)

    def test_parse_from_http_url(self):
        from imcp.services.mcp_json_parser import MCPJsonParser, MCPJsonMetadata
        spec = self._sample_spec()
        with patch("httpx.get") as mock_get:
            mock_resp = Mock()
            mock_resp.json.return_value = spec
            mock_resp.raise_for_status = Mock()
            mock_get.return_value = mock_resp
            result = MCPJsonParser().parse_mcp_json("https://example.com/tools.json")
            self.assertIsInstance(result, MCPJsonMetadata)
            self.assertEqual(result.name, "test-tools")

    def test_validate_missing_required_field(self):
        from imcp.services.mcp_json_parser import MCPJsonParser
        with self.assertRaises(ValueError) as ctx:
            MCPJsonParser()._validate_required_fields({"name": "x"})
        self.assertIn("Missing required field", str(ctx.exception))

    def test_validate_empty_tools(self):
        from imcp.services.mcp_json_parser import MCPJsonParser
        with self.assertRaises(ValueError) as ctx:
            MCPJsonParser()._validate_required_fields({"name": "x", "version": "1.0.0", "tools": []})
        self.assertIn("cannot be empty", str(ctx.exception))

    def test_validate_tool_missing_name(self):
        from imcp.services.mcp_json_parser import MCPJsonParser
        with self.assertRaises(ValueError) as ctx:
            MCPJsonParser()._validate_tools([{"description": "d", "inputSchema": {"type": "object"}}])
        self.assertIn("name", str(ctx.exception))

    def test_validate_tool_missing_description(self):
        from imcp.services.mcp_json_parser import MCPJsonParser
        with self.assertRaises(ValueError) as ctx:
            MCPJsonParser()._validate_tools([{"name": "t", "inputSchema": {"type": "object"}}])
        self.assertIn("description", str(ctx.exception))

    def test_validate_tool_missing_input_schema(self):
        from imcp.services.mcp_json_parser import MCPJsonParser
        with self.assertRaises(ValueError) as ctx:
            MCPJsonParser()._validate_tools([{"name": "t", "description": "d"}])
        self.assertIn("inputSchema", str(ctx.exception))

    def test_validate_tool_invalid_schema_type(self):
        from imcp.services.mcp_json_parser import MCPJsonParser
        with self.assertRaises(ValueError) as ctx:
            MCPJsonParser()._validate_tools([{"name": "t", "description": "d", "inputSchema": "bad"}])
        self.assertIn("inputSchema must be an object", str(ctx.exception))

    def test_validate_endpoint_missing_base_url(self):
        from imcp.services.mcp_json_parser import MCPJsonParser
        with self.assertRaises(ValueError) as ctx:
            MCPJsonParser()._validate_endpoint("t", {"method": "GET", "path": "/x"})
        self.assertIn("baseUrl", str(ctx.exception))

    def test_validate_endpoint_invalid_method(self):
        from imcp.services.mcp_json_parser import MCPJsonParser
        with self.assertRaises(ValueError) as ctx:
            MCPJsonParser()._validate_endpoint("t", {"method": "INVALID", "path": "/x", "baseUrl": "http://x"})
        self.assertIn("invalid method", str(ctx.exception))

    def test_extract_tools_no_filter(self):
        from imcp.services.mcp_json_parser import MCPJsonParser, MCPJsonMetadata
        meta = MCPJsonMetadata(url="file:///x.json", name="t", version="1.0", description="d", tools=[
            {"name": "a", "description": "A", "inputSchema": {"type": "object"}},
            {"name": "b", "description": "B", "inputSchema": {"type": "object"}},
        ])
        result = MCPJsonParser().extract_tools(meta, allowlist=None, denylist=None)
        self.assertEqual(len(result), 2)

    def test_extract_tools_allowlist(self):
        from imcp.services.mcp_json_parser import MCPJsonParser, MCPJsonMetadata
        meta = MCPJsonMetadata(url="file:///x.json", name="t", version="1.0", description="d", tools=[
            {"name": "t1", "description": "T1", "inputSchema": {"type": "object"}},
            {"name": "t2", "description": "T2", "inputSchema": {"type": "object"}},
            {"name": "t3", "description": "T3", "inputSchema": {"type": "object"}},
        ])
        result = MCPJsonParser().extract_tools(meta, allowlist=["t1", "t3"], denylist=None)
        self.assertEqual(len(result), 2)
        names = [t["name"] for t in result]
        self.assertIn("t1", names)
        self.assertIn("t3", names)

    def test_extract_tools_denylist(self):
        from imcp.services.mcp_json_parser import MCPJsonParser, MCPJsonMetadata
        meta = MCPJsonMetadata(url="file:///x.json", name="t", version="1.0", description="d", tools=[
            {"name": "t1", "description": "T1", "inputSchema": {"type": "object"}},
            {"name": "t2", "description": "T2", "inputSchema": {"type": "object"}},
        ])
        result = MCPJsonParser().extract_tools(meta, allowlist=None, denylist=["t2"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "t1")

    def test_extract_tools_allowlist_and_denylist(self):
        from imcp.services.mcp_json_parser import MCPJsonParser, MCPJsonMetadata
        meta = MCPJsonMetadata(url="file:///x.json", name="t", version="1.0", description="d", tools=[
            {"name": "t1", "description": "T1", "inputSchema": {"type": "object"}},
            {"name": "t2", "description": "T2", "inputSchema": {"type": "object"}},
            {"name": "t3", "description": "T3", "inputSchema": {"type": "object"}},
        ])
        result = MCPJsonParser().extract_tools(meta, allowlist=["t1", "t2"], denylist=["t2"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "t1")

    def test_global_functions(self):
        import tempfile, os, json
        from imcp.services.mcp_json_parser import parse_mcp_json, extract_tools, MCPJsonMetadata
        spec = self._sample_spec()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(spec, f)
            fname = f.name
        try:
            meta = parse_mcp_json(fname)
            self.assertIsInstance(meta, MCPJsonMetadata)
            result = extract_tools(meta, allowlist=["getThing"], denylist=None)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["name"], "getThing")
        finally:
            os.unlink(fname)


# ---------------------------------------------------------------------------
# Tool generator
# ---------------------------------------------------------------------------

class TestToolGenerator(unittest.TestCase):

    def test_mcp_tool_init_and_to_dict(self):
        from imcp.services.tool_generator import MCPTool
        tool = MCPTool(
            name="getClaim",
            description="Get claim",
            input_schema={"type": "object", "properties": {"id": {"type": "string"}}},
        )
        self.assertEqual(tool.name, "getClaim")
        d = tool.to_dict()
        self.assertEqual(d["name"], "getClaim")
        self.assertEqual(d["inputSchema"]["type"], "object")

    def test_create_tool_from_operation(self):
        from imcp.services.tool_generator import ToolGenerator, MCPTool
        op = {"name": "getClaim", "documentation": "Get claim info", "input": {"type": None}}
        result = ToolGenerator()._create_tool_from_operation(op)
        self.assertIsInstance(result, MCPTool)
        self.assertEqual(result.name, "getClaim")
        self.assertEqual(result.description, "Get claim info")

    def test_create_tool_no_documentation(self):
        from imcp.services.tool_generator import ToolGenerator
        op = {"name": "updatePolicy", "input": {"type": None}}
        result = ToolGenerator()._create_tool_from_operation(op)
        self.assertIn("updatePolicy", result.description)

    def test_generate_empty_operations(self):
        from imcp.services.tool_generator import ToolGenerator
        from imcp.services.wsdl_parser import WSDLMetadata
        meta = WSDLMetadata(url="http://x", operations=[])
        result = ToolGenerator().generate_mcp_tools("svc_1", meta, use_cache=False)
        self.assertEqual(len(result), 0)

    def test_generate_multiple_operations(self):
        from imcp.services.tool_generator import ToolGenerator
        from imcp.services.wsdl_parser import WSDLMetadata
        ops = [
            {"name": "getClaim", "documentation": "Get", "input": {"type": None}},
            {"name": "updateClaim", "documentation": "Update", "input": {"type": None}},
        ]
        meta = WSDLMetadata(url="http://x", operations=ops)
        result = ToolGenerator().generate_mcp_tools("svc_2", meta, use_cache=False)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].name, "getClaim")

    def test_generate_global_function(self):
        from imcp.services.tool_generator import generate_mcp_tools
        from imcp.services.wsdl_parser import WSDLMetadata
        meta = WSDLMetadata(url="http://x", operations=[
            {"name": "getPolicy", "documentation": "Get policy", "input": {"type": None}},
        ])
        result = generate_mcp_tools("svc_3", meta, use_cache=False)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "getPolicy")
