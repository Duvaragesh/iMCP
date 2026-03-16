"""Django admin registrations for iMCP models."""
from django.contrib import admin
from imcp.models.service import Service
from imcp.models.audit import AuditEvent
from imcp.models.api_key import APIKey
from imcp.models.tool_cache import ToolCacheMetadata


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("name", "spec_type", "category", "auth_type", "enabled", "created_at")
    list_filter = ("spec_type", "category", "enabled")
    search_fields = ("name", "url", "category")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("name",)


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "actor", "action", "tool_name", "status", "latency_ms")
    list_filter = ("status", "action")
    search_fields = ("actor", "action", "tool_name", "correlation_id")
    readonly_fields = (
        "timestamp", "actor", "action", "tool_name", "service_id",
        "status", "latency_ms", "correlation_id", "details",
    )
    ordering = ("-timestamp",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = ("name", "key_prefix", "user_id", "enabled", "revoked", "created_at", "last_used_at")
    list_filter = ("enabled", "revoked")
    search_fields = ("name", "key_prefix", "user_id")
    readonly_fields = ("key_hash", "key_prefix", "created_at", "last_used_at")
    ordering = ("-created_at",)


@admin.register(ToolCacheMetadata)
class ToolCacheMetadataAdmin(admin.ModelAdmin):
    list_display = ("service", "spec_hash", "ttl", "generated_at")
    search_fields = ("service__name", "spec_hash")
    readonly_fields = ("service", "spec_hash", "tools_json", "generated_at")
    ordering = ("-generated_at",)

    def has_add_permission(self, request):
        return False
