"""Auth views — development token issuer (DEBUG only)."""
import json
import logging
from datetime import datetime, timedelta

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["POST"])
def dev_token(request):
    """POST /imcp/auth/dev-token

    Issue a short-lived JWT for development/testing.
    Only available when settings.DEBUG is True OR IMCP['DEBUG_ALLOW_DEV_TOKENS'] is True.
    """
    from imcp.services._settings import imcp_setting

    if not (settings.DEBUG or imcp_setting("DEBUG_ALLOW_DEV_TOKENS")):
        return JsonResponse({"error": "Dev token endpoint disabled in production"}, status=403)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    sub = body.get("sub", "dev-user")
    roles = body.get("roles", ["user"])
    expires_in_minutes = int(body.get("expires_in_minutes", 60))

    try:
        from jose import jwt as jose_jwt
        payload = {
            "sub": sub,
            "roles": roles,
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(minutes=expires_in_minutes),
        }
        token = jose_jwt.encode(payload, imcp_setting("JWT_SECRET"), algorithm=imcp_setting("JWT_ALGORITHM"))

        logger.info(f"Dev token issued for sub={sub}, roles={roles}")
        return JsonResponse({"access_token": token, "token_type": "bearer", "expires_in": expires_in_minutes * 60})

    except Exception as e:
        logger.error(f"Failed to issue dev token: {e}")
        return JsonResponse({"error": "Failed to generate token"}, status=500)
