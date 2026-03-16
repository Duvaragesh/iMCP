"""Helper to read iMCP settings from Django settings.IMCP dict."""


def get_imcp_setting(key: str, default=None):
    """Get a setting from settings.IMCP, falling back to default."""
    from django.conf import settings as django_settings
    imcp_settings = getattr(django_settings, "IMCP", {})
    return imcp_settings.get(key, default)


# Defaults mirroring the FastAPI config
DEFAULTS = {
    "CACHE_TTL_SECONDS": 3600,
    "CACHE_MAX_SIZE": 1000,
    "RATE_LIMIT_PER_MINUTE": 100,
    "JWT_SECRET": "change-me-in-production-use-strong-secret",
    "JWT_ALGORITHM": "HS256",
    "LOG_LEVEL": "INFO",
    "LOG_FORMAT": "json",
    "REDACTION_PATTERNS": ["password", "token", "secret", "authorization", "bearer"],
    "OTEL_ENABLED": False,
    "HEALTH_CHECK_INTERVAL_MINUTES": 5,
    "DEBUG_ALLOW_DEV_TOKENS": False,
    "APP_NAME": "iMCP",
    "APP_VERSION": "0.1.0",
}


def imcp_setting(key: str):
    """Get iMCP setting, using defaults table for fallback."""
    return get_imcp_setting(key, DEFAULTS.get(key))
