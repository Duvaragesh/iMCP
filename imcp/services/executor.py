"""Tool execution service — routes tool calls to the right backend executor."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _find_service_for_tool(tool_name: str):
    """Return the Service that owns tool_name, or None."""
    from imcp.models.tool_cache import ToolCacheMetadata

    for tc in ToolCacheMetadata.objects.select_related("service").filter(
        service__enabled=True
    ):
        tools = tc.tools_json if isinstance(tc.tools_json, list) else []
        if any(t.get("name") == tool_name for t in tools):
            return tc.service
    return None


def _run_async(coro):
    """Run an async coroutine from sync context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Inside an already-running loop (e.g. async Django) — use nest_asyncio or a thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def execute_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    actor: str,
) -> Dict[str, Any]:
    """Execute a tool by routing to the appropriate backend executor.

    Returns a dict with keys:
      status, result, raw_request, raw_response, execution_details
    """
    logger.info(f"Executing tool '{tool_name}' for actor '{actor}'")

    service = _find_service_for_tool(tool_name)
    if service is None:
        raise ValueError(f"Tool '{tool_name}' not found in any enabled service")

    if service.spec_type == "OpenAPI":
        return _execute_openapi_tool(service, tool_name, arguments)

    elif service.spec_type == "WSDL":
        return _execute_wsdl_tool(service, tool_name, arguments)

    elif service.spec_type == "MCP_JSON":
        return _execute_mcp_json_tool(service, tool_name, arguments)

    raise ValueError(f"Unsupported spec_type '{service.spec_type}' for service '{service.name}'")


# ---------------------------------------------------------------------------
# OpenAPI execution
# ---------------------------------------------------------------------------

def _execute_openapi_tool(service, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    from imcp.services.openapi_parser import parse_openapi
    from imcp.services.openapi_executor import execute_openapi_operation
    from imcp.services.auth_headers import build_auth_headers_async

    metadata = parse_openapi(service.url)

    operation = next(
        (op for op in metadata.operations if op["name"] == tool_name),
        None,
    )
    if operation is None:
        raise ValueError(
            f"Operation '{tool_name}' not found in OpenAPI spec for service '{service.name}'"
        )

    method = operation.get("method", "").upper()
    path = operation.get("path", "")
    raw_request = f"{method} {path} | args={json.dumps(arguments)}"

    auth_headers = _run_async(
        build_auth_headers_async(service.auth_type, service.get_credentials(), str(service.id))
    )

    mcp_result = _run_async(
        execute_openapi_operation(
            spec=metadata.spec,
            operation=operation,
            arguments=arguments or {},
            headers=auth_headers,
        )
    )

    content = mcp_result.get("content", [])
    text_out = content[0].get("text", "") if content else ""
    is_error = mcp_result.get("isError", False)

    try:
        result_data = json.loads(text_out)
    except (json.JSONDecodeError, ValueError):
        result_data = text_out

    return {
        "status": "error" if is_error else "success",
        "result": result_data,
        "raw_request": raw_request,
        "raw_response": text_out,
        "execution_details": {
            "tool_name": tool_name,
            "service": service.name,
            "method": method,
            "path": path,
            "actor": None,
        },
    }


# ---------------------------------------------------------------------------
# WSDL execution (stub — full SOAP executor not yet implemented)
# ---------------------------------------------------------------------------

def _execute_wsdl_tool(service, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    logger.warning(f"WSDL execution not yet implemented for tool '{tool_name}'")
    return {
        "status": "error",
        "result": {"message": "WSDL/SOAP execution is not yet implemented"},
        "raw_request": None,
        "raw_response": None,
        "execution_details": {"tool_name": tool_name, "service": service.name},
    }


# ---------------------------------------------------------------------------
# MCP JSON execution
# ---------------------------------------------------------------------------

def _execute_mcp_json_tool(service, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    from imcp.services.mcp_json_parser import parse_mcp_json, extract_tools
    from imcp.services.mcp_json_executor import execute_mcp_json_tool as _exec
    from imcp.services.auth_headers import build_auth_headers_async

    raw_request = f"MCP_JSON tool={tool_name} args={json.dumps(arguments)}"

    metadata = parse_mcp_json(service.url)
    tool_def = next(
        (t for t in extract_tools(metadata, allowlist=None, denylist=None) if t["name"] == tool_name),
        None,
    )
    if tool_def is None:
        raise ValueError(f"Tool '{tool_name}' not found in MCP_JSON spec for service '{service.name}'")

    auth_headers = _run_async(
        build_auth_headers_async(service.auth_type, service.get_credentials(), str(service.id))
    )

    mcp_result = _run_async(
        _exec(
            tool_def=tool_def,
            arguments=arguments or {},
            headers=auth_headers,
        )
    )

    content = mcp_result.get("content", [])
    text_out = content[0].get("text", "") if content else ""
    is_error = mcp_result.get("isError", False)

    try:
        result_data = json.loads(text_out)
    except (json.JSONDecodeError, ValueError):
        result_data = text_out

    return {
        "status": "error" if is_error else "success",
        "result": result_data,
        "raw_request": raw_request,
        "raw_response": text_out,
        "execution_details": {"tool_name": tool_name, "service": service.name},
    }
