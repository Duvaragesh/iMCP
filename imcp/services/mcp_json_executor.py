"""Execute MCP_JSON tools by calling their declared HTTP endpoints."""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
import json

import httpx

from .redaction import redact_payload


class MCPJsonExecutionError(RuntimeError):
    """Raised when a MCP_JSON tool cannot be executed."""


def _build_url(base_url: str, path: str) -> str:
    if not base_url:
        raise MCPJsonExecutionError("Missing endpoint.baseUrl")
    if not path:
        raise MCPJsonExecutionError("Missing endpoint.path")
    return base_url.rstrip("/") + "/" + path.lstrip("/")


def _split_args(
    arguments: Dict[str, Any],
    query_params: Optional[list],
    body_params: Optional[list],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    query: Dict[str, Any] = {}
    body: Dict[str, Any] = {}

    if query_params:
        for key in query_params:
            if key in arguments:
                query[key] = arguments[key]

    if body_params:
        for key in body_params:
            if key in arguments:
                body[key] = arguments[key]

    return query, body


async def execute_mcp_json_tool(
    tool_def: Dict[str, Any],
    arguments: Dict[str, Any],
    *,
    headers: Optional[Dict[str, str]] = None,
    timeout_seconds: float = 30.0,
) -> Dict[str, Any]:
    """Execute a single MCP_JSON tool definition.

    Returns: {"content": [{"type": "text", "text": "..."}], "isError": bool}
    """
    endpoint = tool_def.get("endpoint")
    if not isinstance(endpoint, dict):
        raise MCPJsonExecutionError(
            f"Tool '{tool_def.get('name', 'unknown')}' missing endpoint metadata"
        )

    # Apply defaults from inputSchema for any missing arguments
    properties = (tool_def.get("inputSchema") or {}).get("properties") or {}
    arguments = dict(arguments or {})
    for param, schema in properties.items():
        if param not in arguments and "default" in schema:
            arguments[param] = schema["default"]

    method = str(endpoint.get("method", "")).upper()
    url = _build_url(str(endpoint.get("baseUrl", "")), str(endpoint.get("path", "")))

    query_params = endpoint.get("queryParams")
    body_params = endpoint.get("bodyParams")
    query, body = _split_args(arguments or {}, query_params, body_params)

    if method == "GET":
        if not query_params and arguments:
            query = dict(arguments)
        body = {}
    else:
        if not body_params and arguments:
            body = dict(arguments)

    async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True, verify=False) as client:
        try:
            if method == "GET":
                resp = await client.request(method, url, params=query, headers=headers or {})
            else:
                resp = await client.request(method, url, params=query, json=body, headers=headers or {})
        except httpx.RequestError as e:
            cause = getattr(e, "__cause__", None) or getattr(e, "__context__", None)
            cause_text = f"; cause={repr(cause)}" if cause else ""
            raise MCPJsonExecutionError(
                f"Upstream request failed ({type(e).__name__}): {repr(e)}{cause_text}"
            ) from e

    content_type = resp.headers.get("content-type", "")

    if 200 <= resp.status_code < 300:
        if "application/json" in content_type:
            try:
                payload = resp.json()
            except Exception:
                payload = resp.text
            payload = redact_payload(payload)
            text_out = json.dumps(payload, indent=2, ensure_ascii=False) if not isinstance(payload, str) else payload
        else:
            text_out = resp.text

        return {"content": [{"type": "text", "text": text_out}], "isError": False}

    error_snippet = resp.text
    if "application/json" in content_type:
        try:
            error_payload = redact_payload(resp.json())
            error_snippet = json.dumps(error_payload, indent=2, ensure_ascii=False)
        except Exception:
            pass

    raise MCPJsonExecutionError(
        f"Upstream returned HTTP {resp.status_code} for {method} {url}: {error_snippet[:2000]}"
    )
