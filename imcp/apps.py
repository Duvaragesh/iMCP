"""Django AppConfig for iMCP."""
from django.apps import AppConfig


class ImcpConfig(AppConfig):
    name = "imcp"
    verbose_name = "iMCP - Intelligent Legacy Bridge"

    def ready(self):
        """Initialize global service instances when the app starts."""
        # Import here so Django ORM is ready
        from imcp.services import cache as cache_module  # noqa: F401
        from imcp.services import audit as audit_module  # noqa: F401
        from imcp.services import health_checker as hc_module  # noqa: F401
        from imcp.services import redaction as redaction_module  # noqa: F401
