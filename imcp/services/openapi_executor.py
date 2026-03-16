"""Execute OpenAPI operations by calling their declared HTTP endpoints."""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
import json

import re

import httpx

from .redaction import redact_payload


class OpenAPIExecutionError(RuntimeError):
    """Raised when an OpenAPI operation cannot be executed."""


def _extract_html_error(html: str) -> str:
    """Extract a concise error summary from an HTML error page (e.g. Django debug page)."""
    lines = []

    # <title>TypeError at /path</title>
    m = re.search(r"<title>([^<]+)</title>", html, re.IGNORECASE)
    if m:
        lines.append(m.group(1).strip())

    # Django debug: <pre class="exception_value">...</pre>
    m = re.search(r'class="exception_value"[^>]*>\s*([^<]+)', html)
    if m:
        lines.append(m.group(1).strip())

    # Last meaningful Exception/Error line from traceback text
    exceptions = re.findall(
        r"(?:Exception|Error|TypeError|ValueError|DatabaseError)[^\n<]{0,200}", html
    )
    for exc in exceptions[-3:]:
        cleaned = re.sub(r"<[^>]+>", "", exc).strip()
        if cleaned and cleaned not in lines:
            lines.append(cleaned)

    return " | ".join(lines) if lines else html[:300]


def _get_base_url(spec: Dict[str, Any]) -> str:
    servers = spec.get("servers") or []
    if not servers:
        raise OpenAPIExecutionError("OpenAPI spec has no servers[].url")
    url = (servers[0] or {}).get("url")
    if not url:
        raise OpenAPIExecutionError("OpenAPI spec servers[0].url is empty")
    return str(url)


def _build_url(base_url: str, path: str) -> str:
    if not path:
        raise OpenAPIExecutionError("OpenAPI operation path is empty")
    return base_url.rstrip("/") + "/" + path.lstrip("/")


def _extract_query_param_names(operation: Dict[str, Any]) -> set:
    names: set = set()
    for p in operation.get("parameters") or []:
        try:
            if p.get("in") == "query" and p.get("name"):
                names.add(str(p["name"]))
        except Exception:
            continue
    return names


def _split_args_for_openapi(
    operation: Dict[str, Any],
    arguments: Dict[str, Any],
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    query_names = _extract_query_param_names(operation)
    query: Dict[str, Any] = {}
    body: Dict[str, Any] = {}

    for k, v in (arguments or {}).items():
        if k in query_names:
            query[k] = v
        else:
            body[k] = v

    request_body = operation.get("requestBody") or {}
    has_body = bool(request_body)

    return (query, body) if (has_body and body) else (query, None)


async def execute_openapi_operation(
    *,
    spec: Dict[str, Any],
    operation: Dict[str, Any],
    arguments: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
    timeout_seconds: float = 30.0,
) -> Dict[str, Any]:
    """Execute an OpenAPI operation and return MCP tools/call result format.

    Returns: {"content": [{"type": "text", "text": "..."}], "isError": bool}
    """
    base_url = _get_base_url(spec)
    method = str(operation.get("method", "")).upper()
    path = str(operation.get("path", ""))
    url = _build_url(base_url, path)

    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
        raise OpenAPIExecutionError(f"Unsupported HTTP method: {method}")

    query, body = _split_args_for_openapi(operation, arguments or {})

    # Ensure userInputs defaults to {} BEFORE null-stripping — servers that
    # iterate over it for template variable substitution crash on None/missing.
    if body and "userInputs" in body and body["userInputs"] is None:
        body["userInputs"] = {}

    # Strip remaining null/None values — optional fields sent as null can cause
    # TypeErrors on servers that don't handle them gracefully.
    if body:
        body = {k: v for k, v in body.items() if v is not None}
    if query:
        query = {k: v for k, v in query.items() if v is not None}

    # If the requestBody schema defines a userInputs property but it was stripped
    # (because caller passed null), inject an empty dict so the server doesn't crash.
    if body is not None and "userInputs" not in body:
        try:
            schema_props = (
                operation.get("requestBody", {})
                .get("content", {})
                .get("application/json", {})
                .get("schema", {})
                .get("properties", {})
            )
            if "userInputs" in schema_props:
                body["userInputs"] = {}
        except Exception:
            pass

    # NOTE: verify=False disables SSL certificate verification for self-signed certs
    async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True, verify=False) as client:
        try:
            resp = await client.request(method, url, params=query, json=body, headers=headers or {})
        except httpx.RequestError as e:
            cause = getattr(e, "__cause__", None) or getattr(e, "__context__", None)
            cause_text = f"; cause={repr(cause)}" if cause else ""
            raise OpenAPIExecutionError(
                f"Upstream request failed ({type(e).__name__}): {repr(e)}{cause_text}"
            ) from e

    content_type = resp.headers.get("content-type", "")

    if 200 <= resp.status_code < 300:
        if "application/json" in content_type:
            try:
                payload: Any = resp.json()
            except Exception:
                payload = resp.text
            payload = redact_payload(payload)
            text_out = json.dumps(payload, indent=2, ensure_ascii=False) if not isinstance(payload, str) else payload
        else:
            text_out = resp.text

        return {"content": [{"type": "text", "text": text_out}], "isError": False}

    if "application/json" in content_type:
        try:
            error_payload = redact_payload(resp.json())
            error_snippet = json.dumps(error_payload, indent=2, ensure_ascii=False)
        except Exception:
            error_snippet = resp.text[:500]
    elif "text/html" in content_type:
        error_snippet = _extract_html_error(resp.text)
    else:
        error_snippet = resp.text[:500]

    raise OpenAPIExecutionError(
        f"Upstream returned HTTP {resp.status_code} for {method} {url}: {error_snippet}"
    )
