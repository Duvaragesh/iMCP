"""Admin views for API key management."""
import json
import secrets
import string
import uuid
import hashlib
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from imcp.models.api_key import APIKey
from imcp.decorators import require_mcp_auth
from imcp.services.audit import log_audit_event

logger = logging.getLogger(__name__)


def _generate_random_string(length: int = 32) -> str:
    """Generate cryptographically secure random base62 string."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _key_to_dict(api_key: APIKey, include_full_key: str = None) -> dict:
    data = {
        "id": api_key.id,
        "key_prefix": api_key.key_prefix,
        "name": api_key.name,
        "user_id": api_key.user_id,
        "roles": api_key.roles,
        "enabled": api_key.enabled,
        "revoked": api_key.revoked,
        "created_at": api_key.created_at.isoformat(),
        "expires_at": api_key.expires_at.isoformat() if api_key.expires_at else None,
        "last_used_at": api_key.last_used_at.isoformat() if api_key.last_used_at else None,
        "description": api_key.description,
    }
    if include_full_key:
        data["key"] = include_full_key
    return data


@csrf_exempt
@require_mcp_auth
def api_keys_list_create(request):
    """GET /imcp/admin/api-keys — list; POST — create."""
    if request.method == "GET":
        return _list_keys(request)
    elif request.method == "POST":
        return _create_key(request)
    return JsonResponse({"error": "Method not allowed"}, status=405)


def _list_keys(request):
    qs = APIKey.objects.all()
    user_id = request.GET.get("user_id")
    enabled = request.GET.get("enabled")
    skip = int(request.GET.get("skip", 0))
    limit = min(int(request.GET.get("limit", 100)), 1000)

    if user_id:
        qs = qs.filter(user_id=user_id)
    if enabled is not None:
        qs = qs.filter(enabled=(enabled.lower() == "true"))

    keys = list(qs[skip: skip + limit])
    logger.info(f"Listed {len(keys)} API keys", extra={"actor": request.imcp_user.actor})
    return JsonResponse([_key_to_dict(k) for k in keys], safe=False)


def _create_key(request):
    correlation_id = str(uuid.uuid4())
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    for field in ["name", "user_id"]:
        if not data.get(field):
            return JsonResponse({"error": f"Missing required field: {field}"}, status=400)

    key_suffix = _generate_random_string(32)
    key = f"imcp_{key_suffix}"
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    key_prefix = key[:12]

    try:
        api_key = APIKey.objects.create(
            key_hash=key_hash,
            key_prefix=key_prefix,
            name=data["name"],
            user_id=data["user_id"],
            roles=data.get("roles", ["user"]),
            description=data.get("description"),
            expires_at=data.get("expires_at"),
            enabled=True,
            revoked=False,
        )

        log_audit_event(
            actor=request.imcp_user.actor,
            action="api_key_create",
            status="success",
            correlation_id=correlation_id,
            details={
                "key_id": api_key.id,
                "key_name": api_key.name,
                "key_prefix": api_key.key_prefix,
                "user_id": api_key.user_id,
                "roles": api_key.roles,
            },
        )

        logger.info(f"API key created: {api_key.name} (ID: {api_key.id})",
                    extra={"actor": request.imcp_user.actor})

        # Return full key ONLY on creation
        return JsonResponse(_key_to_dict(api_key, include_full_key=key), status=201)

    except Exception as e:
        logger.error(f"Failed to create API key: {e}")
        return JsonResponse({"error": "Failed to create API key"}, status=500)


@csrf_exempt
@require_mcp_auth
def api_key_detail(request, key_id: int):
    """GET / PUT / DELETE /imcp/admin/api-keys/<id>"""
    if request.method == "GET":
        return _get_key(request, key_id)
    elif request.method == "PUT":
        return _update_key(request, key_id)
    elif request.method == "DELETE":
        return _revoke_key(request, key_id)
    return JsonResponse({"error": "Method not allowed"}, status=405)


def _get_key(request, key_id: int):
    try:
        key = APIKey.objects.get(pk=key_id)
    except APIKey.DoesNotExist:
        return JsonResponse({"error": "API key not found"}, status=404)
    return JsonResponse(_key_to_dict(key))


def _update_key(request, key_id: int):
    correlation_id = str(uuid.uuid4())
    try:
        api_key = APIKey.objects.get(pk=key_id)
    except APIKey.DoesNotExist:
        return JsonResponse({"error": "API key not found"}, status=404)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    if "name" in data:
        api_key.name = data["name"]
    if "description" in data:
        api_key.description = data["description"]
    if "enabled" in data:
        api_key.enabled = bool(data["enabled"])

    api_key.save()

    log_audit_event(
        actor=request.imcp_user.actor,
        action="api_key_update",
        status="success",
        correlation_id=correlation_id,
        details={"key_id": key_id, "key_name": api_key.name},
    )
    return JsonResponse(_key_to_dict(api_key))


def _revoke_key(request, key_id: int):
    correlation_id = str(uuid.uuid4())
    try:
        api_key = APIKey.objects.get(pk=key_id)
    except APIKey.DoesNotExist:
        return JsonResponse({"error": "API key not found"}, status=404)

    api_key.revoked = True
    api_key.enabled = False
    api_key.save()

    log_audit_event(
        actor=request.imcp_user.actor,
        action="api_key_revoke",
        status="success",
        correlation_id=correlation_id,
        details={"key_id": key_id, "key_name": api_key.name, "key_prefix": api_key.key_prefix},
    )

    logger.info(f"API key revoked: {api_key.name} (ID: {key_id})",
                extra={"actor": request.imcp_user.actor})
    return JsonResponse({}, status=204)
