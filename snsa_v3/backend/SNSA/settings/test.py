import os
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")

from .base import *  # noqa

DEBUG = True
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Faster password hashing for tests
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Disable IP whitelist in tests
MIDDLEWARE = [m for m in MIDDLEWARE if "IPWhitelist" not in m]
