"""Django settings for iMCP local development."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# ------------------------------------------------------------------
# Security
# ------------------------------------------------------------------
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-imcp-local-dev-key-change-in-production",
)
DEBUG = os.environ.get("DEBUG", "true").lower() != "false"
ALLOWED_HOSTS = ["*"]

# ------------------------------------------------------------------
# Application
# ------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "imcp",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "imcp.middleware.imcp.CorrelationIDMiddleware",
    "imcp.middleware.imcp.RequestLoggingMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ------------------------------------------------------------------
# Database — SQLite, stored at project root
# ------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "imcp.db",
    }
}

# ------------------------------------------------------------------
# Auth
# ------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "/admin/login/"           # Portal redirects here when not logged in
LOGIN_REDIRECT_URL = "/imcp/portal/"

# ------------------------------------------------------------------
# Internationalisation
# ------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ------------------------------------------------------------------
# Static files
# ------------------------------------------------------------------
STATIC_URL = "/static/"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ------------------------------------------------------------------
# iMCP configuration
# ------------------------------------------------------------------
IMCP = {
    "APP_NAME": os.environ.get("APP_NAME", "iMCP"),
    "APP_VERSION": os.environ.get("APP_VERSION", "0.1.0"),
    "CACHE_TTL_SECONDS": int(os.environ.get("CACHE_TTL_SECONDS", 3600)),
    "CACHE_MAX_SIZE": int(os.environ.get("CACHE_MAX_SIZE", 1000)),
    "RATE_LIMIT_PER_MINUTE": int(os.environ.get("RATE_LIMIT_PER_MINUTE", 100)),
    "JWT_SECRET": os.environ.get("JWT_SECRET", "change-me-in-production"),
    "JWT_ALGORITHM": os.environ.get("JWT_ALGORITHM", "HS256"),
    "LOG_LEVEL": os.environ.get("LOG_LEVEL", "INFO"),
    "REDACTION_PATTERNS": [
        "password", "token", "secret", "authorization", "bearer", "ssn", "credit_card",
    ],
    "DEBUG_ALLOW_DEV_TOKENS": DEBUG,
}

# ------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "[%(levelname)s] %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
    "loggers": {
        "imcp": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
