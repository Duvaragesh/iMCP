"""MCP JSON-RPC 2.0 and REST views."""
import asyncio
import json
import uuid
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from imcp.decorators import require_mcp_auth
from imcp.models.service import Service
from imcp.services.wsdl_parser import parse_wsdl
from imcp.services.openapi_parser import parse_openapi, extract_operations as extract_openapi_operations
from imcp.services.mcp_json_parser import parse_mcp_json, extract_tools as extract_mcp_json_tools
from imcp.services.mcp_json_executor import execute_mcp_json_tool, MCPJsonExecutionError
from imcp.services.openapi_executor import execute_openapi_operation, OpenAPIExecutionError
from imcp.services.tool_generator import generate_mcp_tools, MCPTool
from imcp.services.audit import log_audit_event

logger = logging.getLogger(__name__)


def health_check(request):
    """GET /imcp/health"""
    return JsonResponse({"status": "ok", "app": "iMCP"})


# ---------------------------------------------------------------------------
# Shared logic helpers
# ---------------------------------------------------------------------------

def _collect_all_tools():
    """Collect MCPTool objects from all enabled services."""
    services = list(Service.objects.filter(enabled=True))
    all_tools = []

    for service in services:
        try:
            allowlist = service.allowlist.get("operations") if service.allowlist else None
            denylist = service.denylist.get("operations") if service.denylist else None

            if service.spec_type == "WSDL":
                metadata = parse_wsdl(service.url)
                tools = generate_mcp_tools(str(service.id), metadata, use_cache=True)

            elif service.spec_type == "OpenAPI":
                metadata = parse_openapi(service.url)
                tools = generate_mcp_tools(str(service.id), metadata, use_cache=True)

            elif service.spec_type == "MCP_JSON":
                mcp_json_metadata = parse_mcp_json(service.url)
                tool_defs = extract_mcp_json_tools(mcp_json_metadata, allowlist=allowlist, denylist=denylist)
                tools = [
                    MCPTool(name=t["name"], description=t["description"], input_schema=t["inputSchema"])
                    for t in tool_defs
                ]
            else:
                logger.warning(f"Unsupported spec type for service {service.id}: {service.spec_type}")
                continue

            all_tools.extend(tools)

        except Exception as e:
            logger.error(f"Error loading tools for service {service.id}: {e}")

    return all_tools


def _find_tool_call_target(tool_name: str, arguments: dict):
    """Sync: search enabled services for tool_name, parse the spec, and return
    everything needed to make the upstream HTTP call.

    Returns a dict with keys: spec_type, and either
      - openapi: {spec, operation, arguments}
      - mcp_json: {tool_def, arguments}
    Returns None if the tool is not found.
    """
    services = list(Service.objects.filter(enabled=True))

    for service in services:
        allowlist = service.allowlist.get("operations") if service.allowlist else None
        denylist = service.denylist.get("operations") if service.denylist else None

        if service.spec_type == "OpenAPI":
            try:
                openapi_metadata = parse_openapi(service.url)
                operations = extract_openapi_operations(openapi_metadata, allowlist=allowlist, denylist=denylist)
            except Exception as e:
                logger.error(f"Failed to parse OpenAPI spec for service {service.id}: {e}")
                continue
            operation = next((op for op in operations if op.get("name") == tool_name), None)
            if operation:
                return {"spec_type": "OpenAPI", "spec": openapi_metadata.spec,
                        "operation": operation, "arguments": arguments or {}, "service": service}

        elif service.spec_type == "MCP_JSON":
            try:
                mcp_json_metadata = parse_mcp_json(service.url)
                tool_defs = extract_mcp_json_tools(mcp_json_metadata, allowlist=allowlist, denylist=denylist)
            except Exception as e:
                logger.error(f"Failed to parse MCP JSON spec for service {service.id}: {e}")
                continue
            matched = next((t for t in tool_defs if t.get("name") == tool_name), None)
            if matched:
                return {"spec_type": "MCP_JSON", "tool_def": matched, "arguments": arguments or {}, "service": service}

    return None


def _run_async(coro):
    """Run an async coroutine safely from a sync Django view.

    Always uses a fresh event loop in a worker thread so it never conflicts
    with any existing running loop (e.g. ASGI server loop).
    """
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _execute_tool(tool_name: str, arguments: dict) -> dict:
    """Find the tool (sync ORM), then dispatch the upstream HTTP call (async)."""
    target = _find_tool_call_target(tool_name, arguments)
    if target is None:
        return {
            "content": [{"type": "text", "text": f"Tool '{tool_name}' not found in any enabled service."}],
            "isError": True,
        }

    from imcp.services.auth_headers import build_auth_headers_async
    svc = target.get("service")
    auth_headers = _run_async(
        build_auth_headers_async(
            svc.auth_type if svc else None,
            svc.get_credentials() if svc else None,
            str(svc.id) if svc else None,
        )
    )

    try:
        if target["spec_type"] == "OpenAPI":
            result = _run_async(execute_openapi_operation(
                spec=target["spec"],
                operation=target["operation"],
                arguments=target["arguments"],
                headers=auth_headers,
            ))
        elif target["spec_type"] == "MCP_JSON":
            result = _run_async(execute_mcp_json_tool(
                target["tool_def"], target["arguments"], headers=auth_headers,
            ))
        else:
            result = {
                "content": [{"type": "text", "text": f"Unsupported spec type: {target['spec_type']}"}],
                "isError": True,
            }
    except (OpenAPIExecutionError, MCPJsonExecutionError) as e:
        result = {"content": [{"type": "text", "text": str(e)}], "isError": True}

    return result


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 dispatcher
# ---------------------------------------------------------------------------

@csrf_exempt
@require_mcp_auth
def handle_jsonrpc(request):
    """POST /imcp/mcp — JSON-RPC 2.0 endpoint."""
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"jsonrpc": "2.0", "id": None,
                             "error": {"code": -32700, "message": "Parse error"}})

    rpc_id = body.get("id")
    method = body.get("method")
    params = body.get("params") or {}

    logger.info(f"JSON-RPC method: {method}, id: {rpc_id}")

    try:
        if method == "initialize":
            result = _handle_initialize(params)
        elif method == "tools/list":
            tools = _collect_all_tools()
            result = {"tools": [t.to_dict() for t in tools]}
        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            correlation_id = getattr(request, "imcp_correlation_id", str(uuid.uuid4()))

            log_audit_event(
                actor=request.imcp_user.actor,
                action="tool_call",
                status="success",
                correlation_id=correlation_id,
                tool_name=tool_name,
                details={"arguments": arguments},
            )

            result = _execute_tool(tool_name, arguments)
        else:
            return JsonResponse({
                "jsonrpc": "2.0", "id": rpc_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            })

        return JsonResponse({"jsonrpc": "2.0", "id": rpc_id, "result": result})

    except Exception as e:
        logger.error(f"JSON-RPC error: {e}")
        return JsonResponse({
            "jsonrpc": "2.0", "id": rpc_id,
            "error": {"code": -32603, "message": f"Internal error: {str(e)}"},
        })


def _handle_initialize(params: dict) -> dict:
    client_info = params.get("clientInfo", {})
    logger.info(f"MCP initialization from client: {client_info}")
    return {
        "protocolVersion": "2024-11-05",
        "serverInfo": {"name": "iMCP", "version": "0.1.0"},
        "capabilities": {
            "tools": {"listChanged": False},
            "notifications": {},
        },
    }


# ---------------------------------------------------------------------------
# REST convenience endpoints
# ---------------------------------------------------------------------------

@csrf_exempt
@require_http_methods(["POST"])
@require_mcp_auth
def list_tools(request):
    """POST /imcp/mcp/tools/list"""
    try:
        tools = _collect_all_tools()
        logger.info(f"Returning {len(tools)} tools")
        return JsonResponse({"tools": [t.to_dict() for t in tools]})
    except Exception as e:
        logger.error(f"Error listing tools: {e}")
        return JsonResponse({"error": "Internal server error"}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@require_mcp_auth
def call_tool(request):
    """POST /imcp/mcp/tools/call"""
    correlation_id = getattr(request, "imcp_correlation_id", str(uuid.uuid4()))

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    tool_name = body.get("name")
    arguments = body.get("arguments", {})

    if not tool_name:
        return JsonResponse(
            {"content": [{"type": "text", "text": "Missing required parameter: name"}], "isError": True}
        )

    try:
        log_audit_event(
            actor=request.imcp_user.actor,
            action="tool_call",
            status="success",
            correlation_id=correlation_id,
            tool_name=tool_name,
            details={"arguments": arguments},
        )

        result = _execute_tool(tool_name, arguments)
        return JsonResponse({"content": result.get("content", []), "isError": bool(result.get("isError"))})

    except Exception as e:
        logger.error(f"Error calling tool: {e}")

        log_audit_event(
            actor=request.imcp_user.actor,
            action="tool_call",
            status="failure",
            correlation_id=correlation_id,
            tool_name=tool_name,
            details={"error": str(e)},
        )

        return JsonResponse(
            {"content": [{"type": "text", "text": f"Error executing tool: {str(e)}"}], "isError": True}
        )
