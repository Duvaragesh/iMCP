"""Build HTTP auth headers from a service's auth_type and credentials dict."""
from __future__ import annotations

import base64
from typing import Optional


async def build_auth_headers_async(
    auth_type: Optional[str],
    credentials: Optional[dict],
    service_id: Optional[str] = None,
) -> dict:
    """Async version of build_auth_headers — required for OAuth2 token fetching.

    For all non-OAuth2 auth types this simply delegates to the sync version.
    """
    if auth_type == "OAuth2_ClientCredentials" and credentials:
        from imcp.services.oauth import fetch_oauth_token
        token = await fetch_oauth_token(
            token_url=credentials["token_url"],
            client_id=credentials["client_id"],
            client_secret=credentials["client_secret"],
            scope=credentials.get("scope"),
            cache_key=f"oauth:{service_id}" if service_id else None,
        )
        return {"Authorization": f"Bearer {token}"}
    return build_auth_headers(auth_type, credentials)


def build_auth_headers(
    auth_type: Optional[str],
    credentials: Optional[dict],
) -> dict:
    """Return a dict of HTTP headers to inject for the given auth_type + credentials.

    Returns an empty dict when auth_type or credentials are absent.
    """
    if not auth_type or not credentials:
        return {}

    if auth_type == "Bearer":
        token = credentials.get("token", "")
        return {"Authorization": f"Bearer {token}"} if token else {}

    if auth_type == "Basic":
        username = credentials.get("username", "")
        password = credentials.get("password", "")
        encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
        return {"Authorization": f"Basic {encoded}"}

    if auth_type == "Custom":
        return dict(credentials.get("headers") or {})

    return {}
