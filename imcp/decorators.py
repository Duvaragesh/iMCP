"""Auth decorators for iMCP views."""
import hashlib
import logging
from functools import wraps
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required

logger = logging.getLogger(__name__)


class TokenPayload:
    """Decoded token/API-key payload. Compatible with existing service layer."""

    def __init__(self, sub: str, roles: list = None):
        self.sub = sub
        self.actor = sub
        self.roles = roles or []


def _verify_jwt_token(token: str) -> TokenPayload:
    """Verify a JWT bearer token against IMCP['JWT_SECRET']."""
    from jose import JWTError, jwt
    from imcp.services._settings import imcp_setting

    try:
        payload = jwt.decode(
            token,
            imcp_setting("JWT_SECRET"),
            algorithms=[imcp_setting("JWT_ALGORITHM")],
        )
        sub = payload.get("sub")
        roles = payload.get("roles", [])
        if sub is None:
            raise ValueError("Missing 'sub' claim")
        return TokenPayload(sub=sub, roles=roles)
    except (JWTError, Exception) as e:
        logger.warning(f"JWT verification failed: {e}")
        raise ValueError("Invalid JWT token") from e


def _verify_api_key(key: str) -> TokenPayload:
    """Verify an imcp_ prefixed API key against the database."""
    from imcp.models.api_key import APIKey
    from datetime import datetime

    if not key.startswith("imcp_"):
        raise ValueError("Invalid API key format")

    key_hash = hashlib.sha256(key.encode()).hexdigest()

    try:
        api_key = APIKey.objects.get(key_hash=key_hash, enabled=True, revoked=False)
    except APIKey.DoesNotExist:
        logger.warning(f"Invalid or revoked API key attempt: {key[:16]}...")
        raise ValueError("Invalid or revoked API key")

    if api_key.expires_at and api_key.expires_at < datetime.utcnow():
        logger.warning(f"Expired API key: {api_key.key_prefix}... (ID: {api_key.id})")
        raise ValueError("API key has expired")

    # Update last_used_at (best effort)
    try:
        APIKey.objects.filter(pk=api_key.pk).update(last_used_at=datetime.utcnow())
    except Exception as e:
        logger.error(f"Failed to update last_used_at for API key {api_key.id}: {e}")

    logger.info(f"API key authenticated: {api_key.name} (user: {api_key.user_id})")
    return TokenPayload(sub=api_key.user_id, roles=api_key.roles)


def get_imcp_user(request) -> TokenPayload:
    """Extract and validate the iMCP caller from Authorization header.

    Supports:
    - Bearer <jwt_token>
    - Bearer imcp_<api_key>

    Returns TokenPayload or raises ValueError on failure.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise ValueError("Missing or invalid Authorization header")

    token = auth_header[len("Bearer "):]

    if token.startswith("imcp_"):
        return _verify_api_key(token)

    return _verify_jwt_token(token)


def require_mcp_auth(view_func):
    """Decorator that enforces JWT or API key auth on iMCP API endpoints.

    On success, sets request.imcp_user (TokenPayload).
    On failure, returns 401 JSON.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        try:
            request.imcp_user = get_imcp_user(request)
        except ValueError as e:
            return JsonResponse({"error": str(e)}, status=401)
        return view_func(request, *args, **kwargs)

    return wrapper


def portal_login_required(view_func):
    """Decorator that requires Django session auth for portal page views."""
    return login_required(view_func)
