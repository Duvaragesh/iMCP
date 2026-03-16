"""iMCP URL configuration.

Include this in your project's urls.py:

    path("imcp/", include("imcp.urls")),
"""
from django.urls import path
from imcp.views import mcp as mcp_views
from imcp.views import auth as auth_views
from imcp.views.admin import services as admin_services
from imcp.views.admin import tools as admin_tools
from imcp.views.admin import test as admin_test
from imcp.views.admin import status as admin_status
from imcp.views.admin import api_keys as admin_api_keys
from imcp.views.admin import pages as portal_pages

urlpatterns = [
    # Health check
    path("health", mcp_views.health_check, name="imcp-health"),

    # MCP JSON-RPC 2.0 endpoint
    path("mcp", mcp_views.handle_jsonrpc, name="imcp-jsonrpc"),

    # MCP REST endpoints
    path("mcp/tools/list", mcp_views.list_tools, name="imcp-tools-list"),
    path("mcp/tools/call", mcp_views.call_tool, name="imcp-tools-call"),

    # Auth (debug only)
    path("auth/dev-token", auth_views.dev_token, name="imcp-dev-token"),

    # Admin API: Services
    path("admin/services", admin_services.services_list_create, name="imcp-admin-services"),
    path("admin/services/<int:service_id>", admin_services.service_detail, name="imcp-admin-service-detail"),
    path("admin/services/<int:service_id>/discover-operations", admin_services.discover_operations, name="imcp-admin-discover-ops"),

    # Admin API: Tools
    path("admin/tools", admin_tools.list_tools, name="imcp-admin-tools"),
    path("admin/tools/refresh", admin_tools.refresh_tools, name="imcp-admin-tools-refresh"),

    # Admin API: Test console
    path("admin/test/call", admin_test.test_call, name="imcp-admin-test-call"),

    # Admin API: Status
    path("admin/status", admin_status.get_system_status, name="imcp-admin-status"),
    path("admin/status/run-checks", admin_status.run_health_checks, name="imcp-admin-run-checks"),

    # Admin API: API Keys
    path("admin/api-keys", admin_api_keys.api_keys_list_create, name="imcp-admin-api-keys"),
    path("admin/api-keys/<int:key_id>", admin_api_keys.api_key_detail, name="imcp-admin-api-key-detail"),

    # Admin Portal UI pages
    path("portal/", portal_pages.portal_index, name="imcp-portal"),
    path("portal/dashboard", portal_pages.dashboard, name="imcp-portal-dashboard"),
    path("portal/services", portal_pages.service_catalog, name="imcp-portal-services"),
    path("portal/tools", portal_pages.tool_registry, name="imcp-portal-tools"),
    path("portal/tools/list", portal_pages.tools_list_partial, name="imcp-portal-tools-list"),
    path("portal/test-console", portal_pages.test_console, name="imcp-portal-test-console"),
    path("portal/tokens", portal_pages.tokens_page, name="imcp-portal-tokens"),
    path("portal/status", portal_pages.status_page, name="imcp-portal-status"),
]
