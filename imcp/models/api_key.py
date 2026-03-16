"""API Key model for persistent MCP client authentication."""
from datetime import datetime
from django.db import models


class APIKey(models.Model):
    """API Key for MCP client authentication.

    Format: imcp_<32_random_chars>
    Keys are stored as SHA256 hashes — the full key is returned only once on creation.
    """

    key_hash = models.CharField(max_length=64, unique=True, db_index=True)  # SHA256 hash
    key_prefix = models.CharField(max_length=16)   # First 12 chars for display
    name = models.CharField(max_length=100)        # Human-readable label
    user_id = models.CharField(max_length=100, db_index=True)   # e.g. email/username
    roles = models.JSONField(default=list)         # List of roles
    enabled = models.BooleanField(default=True)
    revoked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    description = models.TextField(null=True, blank=True)

    class Meta:
        app_label = "imcp"
        db_table = "imcp_api_keys"

    def __str__(self):
        return f"APIKey({self.id}, {self.name}, user={self.user_id}, prefix={self.key_prefix})"

    def is_valid(self) -> bool:
        """Return True if the key is enabled, not revoked, and not expired."""
        if not self.enabled or self.revoked:
            return False
        if self.expires_at and self.expires_at < datetime.utcnow():
            return False
        return True
