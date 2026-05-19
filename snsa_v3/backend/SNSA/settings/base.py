import os
from pathlib import Path
import dj_database_url

# BASE_DIR points to backend/ (3 levels up from settings/base.py)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key")
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.scanning",
    "apps.acf",
    "apps.core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "apps.core.middleware.IPWhitelistMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "SNSA.urls"
WSGI_APPLICATION = "SNSA.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

DATABASES = {
    "default": dj_database_url.config(
        env="DATABASE_URL",
        conn_max_age=600,
    )
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Europe/Amsterdam"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"

# APIM (Azure API Management):
# ACF is the functional framework/layer; APIM is the technical gateway the app
# calls. Use APIM_* names in all code, manifests and env files.
# If APIM_* vars are absent, fall back to ACF_* equivalents
# so existing deployments are not broken during transition.
APIM_BASE_URL = (
    os.environ.get("APIM_BASE_URL")
    or os.environ.get("ACF_BASE_URL")
    or "http://localhost:8080"
)
APIM_API_KEY = os.environ.get("APIM_API_KEY") or os.environ.get("ACF_API_KEY") or ""
APIM_TIMEOUT_SECONDS = int(
    os.environ.get("APIM_TIMEOUT_SECONDS")
    or os.environ.get("ACF_TIMEOUT_SECONDS")
    or "10"
)

SESSION_TIMEOUT_MINUTES = int(os.environ.get("SESSION_TIMEOUT_MINUTES", "30"))

# Proxy / IP whitelist
# Space or comma-separated list of CIDRs for trusted reverse proxies
# (OpenShift router, HAProxy ingress, etc.).
# X-Forwarded-For is only trusted when the request originates from one of these.
# eg:  TRUSTED_PROXY_CIDRS=10.128.0.0/14 172.30.0.0/16
TRUSTED_PROXY_CIDRS = os.environ.get("TRUSTED_PROXY_CIDRS", "")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "apps.scanning": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "apps.acf": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "apps.core": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
