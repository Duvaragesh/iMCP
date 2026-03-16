"""Admin views for system status monitoring."""
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from imcp.models.service import Service
from imcp.models.audit import AuditEvent
from imcp.decorators import require_mcp_auth
from imcp.services.health_checker import check_service_reachability
from imcp.services.cache import get_cache_stats
from imcp.services._settings import imcp_setting

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["GET"])
@require_mcp_auth
def get_system_status(request):
    """GET /imcp/admin/status"""
    try:
        services = list(Service.objects.filter(enabled=True))

        # Check service health
        service_health = []
        for service in services:
            try:
                result = check_service_reachability(service)
                service_health.append(result.to_dict())
            except Exception as e:
                logger.error(f"Health check failed for service {service.id}: {e}")

        # Cache status
        cache_stats = get_cache_stats()
        cache_status = {
            "enabled": True,
            "size": cache_stats["size"],
            "max_size": cache_stats["max_size"],
            "ttl_seconds": imcp_setting("CACHE_TTL_SECONDS"),
            "hits": cache_stats["hits"],
            "misses": cache_stats["misses"],
            "hit_rate": cache_stats["hit_rate"],
        }

        # Recent errors from audit log
        recent_errors = []
        for err in AuditEvent.objects.filter(status="failure").order_by("-timestamp")[:10]:
            recent_errors.append({
                "timestamp": err.timestamp.isoformat(),
                "actor": err.actor,
                "action": err.action,
                "tool_name": err.tool_name,
                "service_id": err.service_id,
                "error": err.details.get("error") if err.details else None,
            })

        return JsonResponse({
            "adapter_healthy": True,
            "app_name": imcp_setting("APP_NAME"),
            "version": imcp_setting("APP_VERSION"),
            "service_count": len(services),
            "tool_count": len(services) * 5,  # Approximate
            "cache_status": cache_status,
            "service_health": service_health,
            "recent_errors": recent_errors,
        })

    except Exception as e:
        logger.error(f"Failed to get system status: {e}")
        return JsonResponse({
            "adapter_healthy": False,
            "app_name": imcp_setting("APP_NAME"),
            "version": imcp_setting("APP_VERSION"),
            "service_count": 0,
            "tool_count": 0,
            "cache_status": {"enabled": False, "size": 0, "max_size": 0,
                             "ttl_seconds": 0, "hits": 0, "misses": 0, "hit_rate": 0.0},
            "service_health": [],
            "recent_errors": [{"error": str(e), "action": "get_status",
                                "actor": request.imcp_user.actor, "timestamp": ""}],
        })


@csrf_exempt
@require_http_methods(["POST"])
@require_mcp_auth
def run_health_checks(request):
    """POST /imcp/admin/status/run-checks"""
    services = list(Service.objects.filter(enabled=True))
    service_health = []

    for service in services:
        try:
            result = check_service_reachability(service)
            service_health.append(result.to_dict())
        except Exception as e:
            logger.error(f"Health check failed for service {service.id}: {e}")

    logger.info(
        f"Manual health checks completed for {len(service_health)} services",
        extra={"actor": request.imcp_user.actor},
    )
    return JsonResponse({"status": "success", "service_health": service_health})
