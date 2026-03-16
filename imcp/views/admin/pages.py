"""Admin portal page views — render Django templates for the iMCP management UI."""
import logging

from django.shortcuts import render, redirect
from django.urls import reverse

from imcp.decorators import portal_login_required
from imcp.models.service import Service
from imcp.models.audit import AuditEvent
from imcp.models.tool_cache import ToolCacheMetadata
from imcp.services.cache import get_cache_stats
from imcp.services._settings import imcp_setting

logger = logging.getLogger(__name__)


def _get_tools_for_service_portal(service: Service) -> tuple:
    """Return (tools_list, is_cached) for a service.

    Reads from ToolCacheMetadata first. If empty, generates on demand and
    persists so subsequent page loads show results without a manual Refresh.
    """
    try:
        tc = ToolCacheMetadata.objects.get(service=service)
        tools = tc.tools_json if isinstance(tc.tools_json, list) else []
        if tools:
            return tools, True
    except ToolCacheMetadata.DoesNotExist:
        pass

    # No DB cache — generate now and persist
    try:
        from imcp.views.admin.tools import _generate_tools
        mcp_tools = _generate_tools(service)
        tools = [t.to_dict() if hasattr(t, "to_dict") else t for t in mcp_tools]
        return tools, bool(tools)
    except Exception as e:
        logger.error(f"On-demand tool generation failed for service {service.id}: {e}")
        return [], False


def _get_api_token(request):
    """Return an API token for embedding in portal page HTMX requests.

    For portal pages we use a short-lived token generated from the Django
    session user so that HTMX calls to admin JSON API endpoints can pass
    ``Authorization: Bearer <token>`` without a separate login flow.

    Falls back to an empty string when DEBUG_ALLOW_DEV_TOKENS is off or
    jose is unavailable (pages still load, but HTMX API calls will 401).
    """
    try:
        from jose import jwt
        secret = imcp_setting("JWT_SECRET")
        algorithm = imcp_setting("JWT_ALGORITHM")
        if not secret:
            return ""
        payload = {
            "sub": str(request.user),
            "roles": ["portal"],
        }
        return jwt.encode(payload, secret, algorithm=algorithm)
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Index redirect
# ---------------------------------------------------------------------------

@portal_login_required
def portal_index(request):
    """GET /imcp/portal/ — redirect to dashboard."""
    return redirect(reverse("imcp-portal-dashboard"))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@portal_login_required
def dashboard(request):
    """GET /imcp/portal/dashboard"""
    try:
        service_count = Service.objects.filter(enabled=True).count()
        cache_stats = get_cache_stats()
        cache_hit_rate = cache_stats.get("hit_rate", 0)

        # Total tool count: pull from ToolCacheMetadata when available
        try:
            tool_count = sum(
                len(tc.tools_json) if isinstance(tc.tools_json, list) else 0
                for tc in ToolCacheMetadata.objects.all()
            )
        except Exception:
            tool_count = 0

        # Error count in last 24 h
        from django.utils import timezone
        import datetime
        since = timezone.now() - datetime.timedelta(hours=24)
        error_count = AuditEvent.objects.filter(
            status="failure", timestamp__gte=since
        ).count()

        # Recent events (last 20)
        recent_events = list(
            AuditEvent.objects.order_by("-timestamp")
            .values("action", "actor", "status")[:20]
        )

    except Exception as e:
        logger.error(f"Dashboard context error: {e}")
        service_count = 0
        tool_count = 0
        cache_hit_rate = 0
        error_count = 0
        recent_events = []

    context = {
        "service_count": service_count,
        "tool_count": tool_count,
        "cache_hit_rate": round(cache_hit_rate, 1),
        "error_count": error_count,
        "recent_events": recent_events,
        "api_token": _get_api_token(request),
    }
    return render(request, "imcp/dashboard.html", context)


# ---------------------------------------------------------------------------
# Service Catalog
# ---------------------------------------------------------------------------

@portal_login_required
def service_catalog(request):
    """GET /imcp/portal/services"""
    services = list(Service.objects.all().order_by("name"))
    context = {
        "services": services,
        "api_token": _get_api_token(request),
    }
    return render(request, "imcp/service_catalog.html", context)


# ---------------------------------------------------------------------------
# Tool Registry
# ---------------------------------------------------------------------------

@portal_login_required
def tool_registry(request):
    """GET /imcp/portal/tools"""
    services = list(Service.objects.filter(enabled=True).order_by("name"))
    tool_entries = []

    for service in services:
        try:
            tools, cache_hit = _get_tools_for_service_portal(service)
            tool_entries.append({
                "service_name": service.name,
                "service_id": service.id,
                "tools": tools,
                "cached": cache_hit,
            })
        except Exception as e:
            logger.error(f"Tool registry error for service {service.id}: {e}")
            tool_entries.append({
                "service_name": service.name,
                "service_id": service.id,
                "tools": [],
                "cached": False,
            })

    context = {
        "services": services,
        "tool_entries": tool_entries,
        "api_token": _get_api_token(request),
    }
    return render(request, "imcp/tool_registry.html", context)


@portal_login_required
def tools_list_partial(request):
    """GET /imcp/portal/tools/list?serviceId=<id>
    Returns an HTML partial for the tools list panel (used by HTMX).
    """
    service_id = request.GET.get("serviceId")
    qs = Service.objects.filter(enabled=True).order_by("name")
    if service_id:
        qs = qs.filter(pk=service_id)

    tool_entries = []
    for service in qs:
        try:
            tools, cache_hit = _get_tools_for_service_portal(service)
        except Exception as e:
            logger.error(f"tools_list_partial error for service {service.id}: {e}")
            tools = []
            cache_hit = False

        tool_entries.append({
            "service_name": service.name,
            "service_id": service.id,
            "tools": tools,
            "cached": cache_hit,
        })

    return render(request, "imcp/components/tools_list.html", {"tool_entries": tool_entries})


# ---------------------------------------------------------------------------
# Test Console
# ---------------------------------------------------------------------------

@portal_login_required
def test_console(request):
    """GET /imcp/portal/test-console"""
    services = list(Service.objects.filter(enabled=True).order_by("name"))
    tool_entries = []

    for service in services:
        try:
            tools, _ = _get_tools_for_service_portal(service)
        except Exception:
            tools = []

        tool_entries.append({
            "service_name": service.name,
            "service_id": service.id,
            "tools": tools,
        })

    context = {
        "tool_entries": tool_entries,
        "api_token": _get_api_token(request),
    }
    return render(request, "imcp/test_console.html", context)


# ---------------------------------------------------------------------------
# Tokens & API Keys
# ---------------------------------------------------------------------------

@portal_login_required
def tokens_page(request):
    """GET /imcp/portal/tokens"""
    from imcp.models.api_key import APIKey
    api_keys = list(APIKey.objects.order_by("-created_at"))
    context = {
        "api_keys": api_keys,
        "api_token": _get_api_token(request),
    }
    return render(request, "imcp/tokens.html", context)


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

@portal_login_required
def status_page(request):
    """GET /imcp/portal/status"""
    from imcp.services.health_checker import check_service_reachability
    from imcp.services.cache import get_cache_stats

    services = list(Service.objects.filter(enabled=True))

    service_health = []
    for service in services:
        try:
            result = check_service_reachability(service)
            service_health.append(result.to_dict())
        except Exception as e:
            logger.error(f"Health check error for service {service.id}: {e}")
            service_health.append({
                "service_name": service.name,
                "reachable": False,
                "latency_ms": None,
                "last_check": None,
                "error": str(e),
            })

    cache_stats = get_cache_stats()
    cache_status = {
        "enabled": True,
        "size": cache_stats.get("size", 0),
        "max_size": cache_stats.get("max_size", 0),
        "ttl_seconds": imcp_setting("CACHE_TTL_SECONDS"),
        "hits": cache_stats.get("hits", 0),
        "misses": cache_stats.get("misses", 0),
        "hit_rate": round(cache_stats.get("hit_rate", 0), 1),
    }

    recent_errors = []
    for err in AuditEvent.objects.filter(status="failure").order_by("-timestamp")[:10]:
        recent_errors.append({
            "action": err.action,
            "actor": err.actor,
            "error": err.details.get("error") if err.details else None,
            "timestamp": err.timestamp.isoformat() if err.timestamp else None,
        })

    adapter_healthy = all(h.get("reachable", False) for h in service_health) if service_health else True

    status = {
        "adapter_healthy": adapter_healthy,
        "service_count": len(services),
        "service_health": service_health,
        "cache_status": cache_status,
        "recent_errors": recent_errors,
    }

    context = {
        "status": status,
        "api_token": _get_api_token(request),
    }
    return render(request, "imcp/status.html", context)
