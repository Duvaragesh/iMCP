"""OAuth2 client_credentials token fetching with TTL-based caching."""
from __future__ import annotations

import logging
from typing import Optional

import httpx
from cachetools import TTLCache

logger = logging.getLogger(__name__)

# Module-level cache: TTL of 3500s keeps tokens safely under the typical 3600s lifetime.
_token_cache: TTLCache = TTLCache(maxsize=256, ttl=3500)


async def fetch_oauth_token(
    token_url: str,
    client_id: str,
    client_secret: str,
    scope: Optional[str] = None,
    cache_key: Optional[str] = None,
) -> str:
    """Fetch (or return cached) an OAuth2 client_credentials access token.

    The token is cached by cache_key for up to 3500 seconds so subsequent
    calls within the same token lifetime skip the token endpoint entirely.
    """
    key = cache_key or f"{token_url}:{client_id}"

    if key in _token_cache:
        logger.debug(f"OAuth2 token cache hit for key={key!r}")
        return _token_cache[key]

    logger.info(f"Fetching OAuth2 token from {token_url}")
    data: dict = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }
    if scope:
        data["scope"] = scope

    async with httpx.AsyncClient(timeout=15.0, verify=False) as client:
        resp = await client.post(token_url, data=data)
        resp.raise_for_status()

    payload = resp.json()
    token: str = payload["access_token"]
    _token_cache[key] = token
    logger.info(f"OAuth2 token obtained and cached for key={key!r}")
    return token


def invalidate_oauth_token(cache_key: str) -> None:
    """Remove a cached token so the next call re-fetches it."""
    _token_cache.pop(cache_key, None)
