"""Admin views for tool management."""
import hashlib
import uuid
import logging

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from imcp.models.service import Service
from imcp.models.tool_cache import ToolCacheMetadata
from imcp.decorators import require_mcp_auth
from imcp.services.tool_generator import MCPTool, generate_mcp_tools
from imcp.services.wsdl_parser import parse_wsdl, extract_operations as extract_wsdl_operations
from imcp.services.openapi_parser import parse_openapi, extract_operations as extract_openapi_operations
from imcp.services.mcp_json_parser import parse_mcp_json, extract_tools as extract_mcp_json_tools
from imcp.services.cache import (
    get_cached_tools, set_cached_tools, invalidate_service_cache, get_cache_stats
)
from imcp.services.audit import log_audit_event
from imcp.services._settings import imcp_setting

logger = logging.getLogger(__name__)


def _persist_tools(service: Service, tools: list) -> None:
    """Upsert ToolCacheMetadata with the generated tool list."""
    tools_dicts = [t.to_dict() if hasattr(t, "to_dict") else t for t in tools]
    spec_hash = hashlib.sha256(service.url.encode()).hexdigest()
    ttl = imcp_setting("CACHE_TTL_SECONDS") or 3600
    obj, created = ToolCacheMetadata.objects.get_or_create(
        service=service,
        defaults={
            "spec_hash": spec_hash,
            "ttl": ttl,
            "tools_json": tools_dicts,
        },
    )
    if not created:
        obj.spec_hash = spec_hash
        obj.ttl = ttl
        obj.tools_json = tools_dicts
        obj.generated_at = timezone.now()
        obj.save(update_fields=["spec_hash", "ttl", "tools_json", "generated_at"])


def _get_tools_for_service(service: Service):
    """Return (tools: list[MCPTool], is_cached: bool) for a service."""
    cached = get_cached_tools(str(service.id))
    if cached:
        tools = [
            MCPTool(name=t["name"], description=t["description"], input_schema=t["inputSchema"])
            for t in cached
        ]
        return tools, True

    tools = _generate_tools(service)
    return tools, False


def _generate_tools(service: Service):
    """Generate or import tools for a service (no cache check). Also persists to DB."""
    allowlist = service.allowlist.get("operations") if service.allowlist else None
    denylist = service.denylist.get("operations") if service.denylist else None

    if service.spec_type == "WSDL":
        metadata = parse_wsdl(service.url)
        metadata.operations = extract_wsdl_operations(metadata, allowlist=allowlist, denylist=denylist)
        tools = generate_mcp_tools(str(service.id), metadata, use_cache=True)

    elif service.spec_type == "OpenAPI":
        metadata = parse_openapi(service.url)
        metadata.operations = extract_openapi_operations(metadata, allowlist=allowlist, denylist=denylist)
        tools = generate_mcp_tools(str(service.id), metadata, use_cache=True)

    elif service.spec_type == "MCP_JSON":
        mcp_json_metadata = parse_mcp_json(service.url)
        tool_defs = extract_mcp_json_tools(mcp_json_metadata, allowlist=allowlist, denylist=denylist)
        tools = [
            MCPTool(name=t["name"], description=t["description"], input_schema=t["inputSchema"])
            for t in tool_defs
        ]
        set_cached_tools(str(service.id), [t.to_dict() for t in tools])

    else:
        return []

    try:
        _persist_tools(service, tools)
    except Exception as e:
        logger.warning(f"Failed to persist tools to DB for service {service.id}: {e}")

    return tools


@csrf_exempt
@require_http_methods(["GET"])
@require_mcp_auth
def list_tools(request):
    """GET /imcp/admin/tools[?serviceId=<id>]"""
    service_id = request.GET.get("serviceId")

    qs = Service.objects.all()
    if service_id:
        qs = qs.filter(pk=service_id)
        if not qs.exists():
            return JsonResponse({"error": "Service not found"}, status=404)
    else:
        qs = qs.filter(enabled=True)

    result = []
    cache_stats = get_cache_stats()

    for service in qs:
        try:
            tools, is_cached = _get_tools_for_service(service)
            result.append({
                "service_id": service.id,
                "service_name": service.name,
                "tools": [t.to_dict() for t in tools],
                "cached": is_cached,
                "cache_metadata": {
                    "cache_size": cache_stats["size"],
                    "cache_hits": cache_stats["hits"],
                    "cache_misses": cache_stats["misses"],
                    "hit_rate": cache_stats["hit_rate"],
                } if is_cached else None,
            })
        except Exception as e:
            logger.error(f"Failed to generate tools for service {service.id}: {e}")

    logger.info(f"Listed tools for {len(result)} services", extra={"actor": request.imcp_user.actor})
    return JsonResponse(result, safe=False)


@csrf_exempt
@require_http_methods(["POST"])
@require_mcp_auth
def refresh_tools(request):
    """POST /imcp/admin/tools/refresh[?serviceId=<id>]"""
    correlation_id = str(uuid.uuid4())
    service_id = request.GET.get("serviceId")

    qs = Service.objects.all()
    if service_id:
        qs = qs.filter(pk=service_id)
        if not qs.exists():
            return JsonResponse({"error": "Service not found"}, status=404)
    else:
        qs = qs.filter(enabled=True)

    refreshed = []
    total_tools = 0

    for service in qs:
        try:
            invalidate_service_cache(str(service.id))
            tools = _generate_tools(service)
            refreshed.append(service.id)
            total_tools += len(tools)
            logger.info(f"Refreshed {len(tools)} tools for service {service.id}")
        except Exception as e:
            logger.error(f"Failed to refresh tools for service {service.id}: {e}")

    log_audit_event(
        actor=request.imcp_user.actor,
        action="tools_refresh",
        status="success",
        correlation_id=correlation_id,
        details={"refreshed_services": refreshed, "total_tools": total_tools},
    )

    return JsonResponse({
        "status": "success",
        "refreshed_services": refreshed,
        "total_tools_generated": total_tools,
    })
