"""Admin views for service management."""
import json
import uuid
import logging
from pathlib import Path

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from imcp.models.service import Service
from imcp.decorators import require_mcp_auth
from imcp.services.wsdl_parser import parse_wsdl, extract_operations as extract_wsdl_operations
from imcp.services.openapi_parser import parse_openapi, extract_operations as extract_openapi_operations
from imcp.services.mcp_json_parser import parse_mcp_json, extract_tools as extract_mcp_json_tools
from imcp.services.cache import invalidate_service_cache
from imcp.services.audit import log_audit_event

logger = logging.getLogger(__name__)

VALID_SPEC_TYPES = {"WSDL", "OpenAPI", "MCP_JSON"}
VALID_URL_PREFIXES = ("http://", "https://", "file://")
VALID_AUTH_TYPES = {"Bearer", "Basic", "Custom", "OAuth2_ClientCredentials"}

# Allowed file extensions per spec type
ALLOWED_EXTENSIONS = {
    "OpenAPI": {".yaml", ".yml", ".json"},
    "WSDL": {".wsdl", ".xml"},
    "MCP_JSON": {".json"},
}


def _validate_credentials(auth_type: str | None, credentials: dict | None) -> str | None:
    """Return an error message string if credentials are invalid, else None."""
    if not auth_type or not credentials:
        return None
    if auth_type == "Bearer":
        if not credentials.get("token"):
            return "Bearer auth requires a non-empty 'token' field"
    elif auth_type == "Basic":
        if not credentials.get("username") or not credentials.get("password"):
            return "Basic auth requires non-empty 'username' and 'password' fields"
    elif auth_type == "Custom":
        headers = credentials.get("headers")
        if not isinstance(headers, dict) or not headers:
            return "Custom auth requires a non-empty 'headers' dict"
    elif auth_type == "OAuth2_ClientCredentials":
        for field in ("token_url", "client_id", "client_secret"):
            if not credentials.get(field):
                return f"OAuth2 Client Credentials requires a non-empty '{field}' field"
    return None


def _save_uploaded_spec(uploaded_file, service_name: str) -> str:
    """Save an uploaded spec file to MEDIA_ROOT/imcp_specs/ and return a file:// URL."""
    upload_dir = Path(settings.MEDIA_ROOT) / "imcp_specs"
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Sanitise filename: <service_name>_<uuid><ext>
    original_name = Path(uploaded_file.name)
    safe_stem = "".join(c if c.isalnum() or c in "-_" else "_" for c in service_name)
    filename = f"{safe_stem}_{uuid.uuid4().hex[:8]}{original_name.suffix.lower()}"
    dest = upload_dir / filename

    with open(dest, "wb") as f:
        for chunk in uploaded_file.chunks():
            f.write(chunk)

    return dest.as_uri()  # file:///absolute/path/to/file


def _parse_json_field(value):
    """Parse a JSONField value that may arrive as a JSON-encoded string from FormData."""
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)  # "null" -> None, '{"operations":[...]}' -> dict
    except (json.JSONDecodeError, ValueError):
        return None


def _delete_local_spec_file(url: str) -> None:
    """Delete a local spec file if the URL is a file:// URL pointing inside MEDIA_ROOT."""
    if not url.startswith("file://"):
        return
    try:
        from urllib.request import url2pathname
        file_path = Path(url2pathname(url[7:]))  # strip "file://"
        media_root = Path(settings.MEDIA_ROOT).resolve()
        if file_path.resolve().is_relative_to(media_root) and file_path.exists():
            file_path.unlink()
            logger.info(f"Deleted local spec file: {file_path}")
    except Exception as e:
        logger.warning(f"Could not delete local spec file '{url}': {e}")


def _service_to_dict(service: Service) -> dict:
    return {
        "id": service.id,
        "name": service.name,
        "spec_type": service.spec_type,
        "url": service.url,
        "category": service.category,
        "auth_type": service.auth_type,
        "enabled": service.enabled,
        "allowlist": service.allowlist,
        "denylist": service.denylist,
        "created_at": service.created_at.isoformat(),
        "updated_at": service.updated_at.isoformat(),
    }


@csrf_exempt
@require_mcp_auth
def services_list_create(request):
    """GET /imcp/admin/services — list; POST — create."""
    if request.method == "GET":
        return _list_services(request)
    elif request.method == "POST":
        return _create_service(request)
    return JsonResponse({"error": "Method not allowed"}, status=405)


def _list_services(request):
    qs = Service.objects.all()

    category = request.GET.get("category")
    spec_type = request.GET.get("spec_type")
    enabled = request.GET.get("enabled")
    skip = int(request.GET.get("skip", 0))
    limit = min(int(request.GET.get("limit", 100)), 1000)

    if category:
        qs = qs.filter(category=category)
    if spec_type:
        qs = qs.filter(spec_type=spec_type)
    if enabled is not None:
        qs = qs.filter(enabled=(enabled.lower() == "true"))

    services = list(qs[skip: skip + limit])
    logger.info(f"Listed {len(services)} services", extra={"actor": request.imcp_user.actor})
    return JsonResponse([_service_to_dict(s) for s in services], safe=False)


def _create_service(request):
    correlation_id = str(uuid.uuid4())

    # Support both JSON body (API clients) and multipart/form-data (portal file upload)
    content_type = request.content_type or ""
    if "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
        data = {k: v for k, v in request.POST.items()}
    else:
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON body"}, status=400)

    # Validate required fields (url not required when a file is uploaded)
    uploaded_file = request.FILES.get("spec_file")
    for field in ["name", "spec_type", "category"]:
        if not data.get(field):
            return JsonResponse({"error": f"Missing required field: {field}"}, status=400)

    if not data.get("url") and not uploaded_file:
        return JsonResponse({"error": "Provide either a URL or upload a spec file"}, status=400)

    if data["spec_type"] not in VALID_SPEC_TYPES:
        return JsonResponse({"error": f"spec_type must be one of {sorted(VALID_SPEC_TYPES)}"}, status=400)

    # Handle file upload: validate extension, save file, derive file:// URL
    if uploaded_file:
        ext = Path(uploaded_file.name).suffix.lower()
        allowed = ALLOWED_EXTENSIONS.get(data["spec_type"], set())
        if ext not in allowed:
            return JsonResponse(
                {"error": f"Invalid file type '{ext}' for {data['spec_type']}. "
                          f"Allowed: {', '.join(sorted(allowed))}"},
                status=400,
            )
        try:
            data["url"] = _save_uploaded_spec(uploaded_file, data["name"])
        except Exception as e:
            logger.error(f"Failed to save uploaded spec file: {e}")
            return JsonResponse({"error": "Failed to save uploaded file"}, status=500)
    else:
        if not data["url"].startswith(VALID_URL_PREFIXES):
            return JsonResponse({"error": "url must start with http://, https://, or file://"}, status=400)

    if Service.objects.filter(name=data["name"]).exists():
        return JsonResponse({"error": f"Service with name '{data['name']}' already exists"}, status=400)

    auth_type = data.get("auth_type") or None
    credentials = data.get("credentials") or None
    if isinstance(credentials, str):
        try:
            credentials = json.loads(credentials)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "credentials must be valid JSON"}, status=400)

    cred_error = _validate_credentials(auth_type, credentials)
    if cred_error:
        return JsonResponse({"error": cred_error}, status=400)

    try:
        service = Service.objects.create(
            name=data["name"],
            spec_type=data["spec_type"],
            url=data["url"],
            category=data["category"],
            auth_type=auth_type,
            enabled=data.get("enabled", True),
            allowlist=_parse_json_field(data.get("allowlist")),
            denylist=_parse_json_field(data.get("denylist")),
        )
        service.set_credentials(credentials)
        service.save(update_fields=["credentials_enc"])

        log_audit_event(
            actor=request.imcp_user.actor,
            action="service_create",
            status="success",
            correlation_id=correlation_id,
            service_id=service.id,
            details={
                "service_name": service.name,
                "spec_type": service.spec_type,
                "source": "file_upload" if uploaded_file else "url",
            },
        )

        # Generate and cache tools immediately so the test console shows them
        # without requiring a manual refresh.
        try:
            from imcp.views.admin.tools import _generate_tools
            _generate_tools(service)
        except Exception as e:
            logger.warning(f"Auto tool generation failed for service {service.id}: {e}")

        logger.info(f"Created service {service.id}", extra={"actor": request.imcp_user.actor})
        return JsonResponse(_service_to_dict(service), status=201)

    except Exception as e:
        logger.error(f"Failed to create service: {e}")
        return JsonResponse({"error": "Failed to create service"}, status=500)


@csrf_exempt
@require_mcp_auth
def service_detail(request, service_id: int):
    """GET / PUT / DELETE /imcp/admin/services/<id>"""
    if request.method == "GET":
        return _get_service(request, service_id)
    elif request.method == "PUT":
        return _update_service(request, service_id)
    elif request.method == "DELETE":
        return _delete_service(request, service_id)
    return JsonResponse({"error": "Method not allowed"}, status=405)


def _get_service(request, service_id: int):
    try:
        service = Service.objects.get(pk=service_id)
    except Service.DoesNotExist:
        return JsonResponse({"error": "Service not found"}, status=404)
    return JsonResponse(_service_to_dict(service))


def _update_service(request, service_id: int):
    correlation_id = str(uuid.uuid4())
    try:
        service = Service.objects.get(pk=service_id)
    except Service.DoesNotExist:
        return JsonResponse({"error": "Service not found"}, status=404)

    content_type = request.content_type or ""
    if "multipart/form-data" in content_type:
        # Django only auto-parses multipart for POST; do it manually for PUT.
        from django.http.multipartparser import MultiPartParser
        try:
            post_data, files = MultiPartParser(
                request.META, request, request.upload_handlers
            ).parse()
        except Exception as e:
            logger.error(f"Multipart parse error: {e}")
            return JsonResponse({"error": "Failed to parse multipart body"}, status=400)
        data = {k: v for k, v in post_data.items()}
        uploaded_file = files.get("spec_file")
    elif "application/x-www-form-urlencoded" in content_type:
        data = {k: v for k, v in request.POST.items()}
        uploaded_file = None
    else:
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON body"}, status=400)
        uploaded_file = None

    # Handle file upload: save new spec file and update url
    old_url = service.url  # remember before mutation
    if uploaded_file:
        spec_type = data.get("spec_type") or service.spec_type
        ext = Path(uploaded_file.name).suffix.lower()
        allowed = ALLOWED_EXTENSIONS.get(spec_type, set())
        if ext not in allowed:
            return JsonResponse(
                {"error": f"Invalid file type '{ext}' for {spec_type}. Allowed: {', '.join(sorted(allowed))}"},
                status=400,
            )
        try:
            data["url"] = _save_uploaded_spec(uploaded_file, service.name)
        except Exception as e:
            logger.error(f"Failed to save uploaded spec file: {e}")
            return JsonResponse({"error": "Failed to save uploaded file"}, status=500)

    if "spec_type" in data:
        if data["spec_type"] not in VALID_SPEC_TYPES:
            return JsonResponse({"error": f"spec_type must be one of {sorted(VALID_SPEC_TYPES)}"}, status=400)
        service.spec_type = data["spec_type"]
    if "url" in data:
        if not data["url"].startswith(VALID_URL_PREFIXES):
            return JsonResponse({"error": "url must start with http://, https://, or file://"}, status=400)
        service.url = data["url"]
    if "category" in data:
        service.category = data["category"]
    if "auth_type" in data:
        service.auth_type = data["auth_type"]
    if "credentials" in data:
        credentials = data["credentials"]
        if isinstance(credentials, str):
            try:
                credentials = json.loads(credentials)
            except (json.JSONDecodeError, ValueError):
                return JsonResponse({"error": "credentials must be valid JSON"}, status=400)
        cred_error = _validate_credentials(service.auth_type, credentials)
        if cred_error:
            return JsonResponse({"error": cred_error}, status=400)
        service.set_credentials(credentials)
    if "allowlist" in data:
        service.allowlist = _parse_json_field(data["allowlist"])
    if "denylist" in data:
        service.denylist = _parse_json_field(data["denylist"])
    if "enabled" in data:
        service.enabled = bool(data["enabled"])

    service.save()
    invalidate_service_cache(str(service.id))

    # If a new file was uploaded, remove the old local spec file
    if uploaded_file and old_url != service.url:
        _delete_local_spec_file(old_url)

    # Re-generate tools when the spec file or spec_type changes
    if uploaded_file or "spec_type" in data:
        try:
            from imcp.views.admin.tools import _generate_tools
            _generate_tools(service)
        except Exception as e:
            logger.warning(f"Auto tool regeneration failed for service {service.id}: {e}")

    log_audit_event(
        actor=request.imcp_user.actor,
        action="service_update",
        status="success",
        correlation_id=correlation_id,
        service_id=service.id,
        details={"service_name": service.name},
    )

    logger.info(f"Updated service {service.id}", extra={"actor": request.imcp_user.actor})
    return JsonResponse(_service_to_dict(service))


def _delete_service(request, service_id: int):
    correlation_id = str(uuid.uuid4())
    hard_delete = request.GET.get("hard_delete", "false").lower() == "true"

    try:
        service = Service.objects.get(pk=service_id)
    except Service.DoesNotExist:
        return JsonResponse({"error": "Service not found"}, status=404)

    service_name = service.name
    service_url = service.url

    if hard_delete:
        service.delete()
        _delete_local_spec_file(service_url)
        action = "service_delete"
    else:
        service.enabled = False
        service.save()
        action = "service_disable"

    invalidate_service_cache(str(service_id))

    log_audit_event(
        actor=request.imcp_user.actor,
        action=action,
        status="success",
        correlation_id=correlation_id,
        service_id=service_id,
        details={"service_name": service_name, "hard_delete": hard_delete},
    )

    return JsonResponse({}, status=204)


@csrf_exempt
@require_http_methods(["POST"])
@require_mcp_auth
def discover_operations(request, service_id: int):
    """POST /imcp/admin/services/<id>/discover-operations"""
    correlation_id = str(uuid.uuid4())

    try:
        service = Service.objects.get(pk=service_id)
    except Service.DoesNotExist:
        return JsonResponse({"error": "Service not found"}, status=404)

    operations = []

    try:
        if service.spec_type == "WSDL":
            wsdl_metadata = parse_wsdl(service.url)
            for op in extract_wsdl_operations(wsdl_metadata, allowlist=None, denylist=None):
                operations.append({
                    "name": op["name"],
                    "documentation": op.get("documentation", ""),
                })

        elif service.spec_type == "OpenAPI":
            openapi_metadata = parse_openapi(service.url)
            for op in extract_openapi_operations(openapi_metadata, allowlist=None, denylist=None):
                operations.append({
                    "name": op["name"],
                    "method": op.get("method"),
                    "path": op.get("path"),
                    "summary": op.get("summary"),
                    "description": op.get("description"),
                })

        elif service.spec_type == "MCP_JSON":
            mcp_json_metadata = parse_mcp_json(service.url)
            for tool in extract_mcp_json_tools(mcp_json_metadata, allowlist=None, denylist=None):
                endpoint = tool.get("endpoint", {})
                operations.append({
                    "name": tool["name"],
                    "method": endpoint.get("method"),
                    "path": endpoint.get("path"),
                    "summary": tool["description"],
                    "description": tool["description"],
                })
        else:
            return JsonResponse({"error": f"Unsupported spec type: {service.spec_type}"}, status=400)

    except Exception as e:
        logger.error(f"Failed to discover operations for service {service_id}: {e}")
        return JsonResponse({"error": f"Failed to discover operations: {str(e)}"}, status=400)

    log_audit_event(
        actor=request.imcp_user.actor,
        action="discover_operations",
        status="success",
        correlation_id=correlation_id,
        service_id=service.id,
        details={"service_name": service.name, "operation_count": len(operations)},
    )

    return JsonResponse(operations, safe=False)
