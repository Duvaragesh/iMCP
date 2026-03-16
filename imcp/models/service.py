"""Service model for storing WSDL/OpenAPI/MCP_JSON service catalog."""
from __future__ import annotations

from typing import Optional

from django.db import models


class Service(models.Model):
    """Service catalog entry for WSDL/OpenAPI/MCP_JSON endpoints."""

    SPEC_TYPE_CHOICES = [
        ("WSDL", "WSDL"),
        ("OpenAPI", "OpenAPI"),
        ("MCP_JSON", "MCP JSON"),
    ]

    AUTH_TYPE_CHOICES = [
        ("Bearer", "Bearer Token"),
        ("Basic", "Basic Auth"),
        ("Custom", "Custom"),
        ("OAuth2_ClientCredentials", "OAuth2 (Client Credentials)"),
    ]

    name = models.CharField(max_length=255, unique=True, db_index=True)
    spec_type = models.CharField(max_length=50, choices=SPEC_TYPE_CHOICES)
    url = models.TextField()
    category = models.CharField(max_length=100, db_index=True)
    auth_type = models.CharField(max_length=50, choices=AUTH_TYPE_CHOICES, null=True, blank=True)
    credentials_enc = models.TextField(null=True, blank=True)  # Fernet-encrypted JSON
    enabled = models.BooleanField(default=True, db_index=True)
    allowlist = models.JSONField(null=True, blank=True)  # e.g. {"operations": ["getClaim", "getPolicy"]}
    denylist = models.JSONField(null=True, blank=True)   # e.g. {"operations": ["deleteClaim"]}
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "imcp"
        db_table = "imcp_services"

    def get_credentials(self) -> Optional[dict]:
        """Decrypt and return stored credentials, or None if not set."""
        if not self.credentials_enc:
            return None
        from imcp.services.encryption import decrypt_json
        try:
            return decrypt_json(self.credentials_enc)
        except Exception:
            return None

    def set_credentials(self, data: Optional[dict]) -> None:
        """Encrypt and store credentials. Pass None to clear."""
        if data is None:
            self.credentials_enc = None
        else:
            from imcp.services.encryption import encrypt_json
            self.credentials_enc = encrypt_json(data)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "spec_type": self.spec_type,
            "url": self.url,
            "category": self.category,
            "auth_type": self.auth_type,
            "enabled": self.enabled,
            "allowlist": self.allowlist,
            "denylist": self.denylist,
        }

    def __str__(self):
        return f"Service({self.id}, {self.name}, {self.spec_type})"
