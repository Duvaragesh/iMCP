"""Admin views for the test console."""
import json
import uuid
import logging
from datetime import datetime

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from imcp.decorators import require_mcp_auth
from imcp.services.executor import execute_tool
from imcp.services.audit import log_audit_event

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["POST"])
@require_mcp_auth
def test_call(request):
    """POST /imcp/admin/test/call

    Execute a tool through the same execution path as MCP tools/call.
    Returns normalized response, raw request/response, and latency metadata.
    """
    correlation_id = str(uuid.uuid4())
    start_time = datetime.utcnow()

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    tool_name = body.get("toolName")
    arguments = body.get("arguments", {})

    if not tool_name:
        return JsonResponse({"error": "Missing required field: toolName"}, status=400)

    try:
        result = execute_tool(
            tool_name=tool_name,
            arguments=arguments,
            actor=request.imcp_user.actor,
        )

        latency_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        log_audit_event(
            actor=request.imcp_user.actor,
            action="test_call",
            status=result.get("status", "success"),
            correlation_id=correlation_id,
            tool_name=tool_name,
            latency_ms=latency_ms,
            details={"tool_name": tool_name, "arguments_count": len(arguments)},
        )

        return JsonResponse({
            "status": result.get("status", "success"),
            "correlationId": correlation_id,
            "latencyMs": latency_ms,
            "normalized": result.get("result", {}),
            "rawRequest": result.get("raw_request"),
            "rawResponse": result.get("raw_response"),
            "metadata": {
                "tool_name": tool_name,
                "actor": request.imcp_user.actor,
                "timestamp": start_time.isoformat(),
                "execution_details": result.get("execution_details", {}),
            },
        })

    except Exception as e:
        latency_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        log_audit_event(
            actor=request.imcp_user.actor,
            action="test_call",
            status="failure",
            correlation_id=correlation_id,
            tool_name=tool_name,
            latency_ms=latency_ms,
            details={"tool_name": tool_name, "error": str(e)},
        )

        logger.error(f"Test call failed: {e}", extra={"actor": request.imcp_user.actor})
        return JsonResponse({"error": f"Test call failed: {str(e)}"}, status=500)
