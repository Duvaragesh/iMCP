"""Tool cache metadata model for tracking generated MCP tools."""
from django.db import models
from django.utils import timezone
from .service import Service


class ToolCacheMetadata(models.Model):
    """Metadata for cached tool definitions."""

    service = models.ForeignKey(Service, on_delete=models.CASCADE, db_index=True)
    spec_hash = models.CharField(max_length=64)   # SHA256 hash of spec
    generated_at = models.DateTimeField(default=timezone.now)
    ttl = models.IntegerField()                   # TTL in seconds
    tools_json = models.JSONField()               # Serialized tool definitions

    class Meta:
        app_label = "imcp"
        db_table = "imcp_tool_cache_metadata"

    def __str__(self):
        return f"ToolCacheMetadata({self.id}, service_id={self.service_id}, hash={self.spec_hash[:8]})"
