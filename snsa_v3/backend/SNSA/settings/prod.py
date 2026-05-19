from .base import *  # noqa
import os

from django.core.exceptions import ImproperlyConfigured

DEBUG = False

def _require(name: str, value: str, *, insecure_defaults: tuple = ()) -> str:
    if not value or value in insecure_defaults:
        raise ImproperlyConfigured(
            f"{name} is required in production. "
            f"Inject it via the snsa-secret Kubernetes Secret."
        )
    return value

_require("DJANGO_SECRET_KEY", SECRET_KEY, insecure_defaults=("dev-only-insecure-key",))
_require("APIM_API_KEY (or legacy ACF_API_KEY)", APIM_API_KEY)

CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if o.strip()
]

# Security headers:
SECURE_PROXY_SSL_HEADER     = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE       = True
CSRF_COOKIE_SECURE          = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY      = "same-origin"
X_FRAME_OPTIONS             = "DENY"

# HSTS start at 60s, raise to 31536000 once HTTPS is confirmed stable
SECURE_HSTS_SECONDS             = 60
SECURE_HSTS_INCLUDE_SUBDOMAINS  = True
SECURE_HSTS_PRELOAD             = False

# Silenced deploy-check warnings:
# security.W008 (SECURE_SSL_REDIRECT not True):
# security.W021 (SECURE_HSTS_PRELOAD not True):

SILENCED_SYSTEM_CHECKS = ["security.W008", "security.W021"]

# WhiteNoise insert after SecurityMiddleware
# We INSERT rather than redefine MIDDLEWARE so that IPWhitelistMiddleware
# and all other middleware inherited from base.py remain intact.
MIDDLEWARE = list(MIDDLEWARE)
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")


STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
