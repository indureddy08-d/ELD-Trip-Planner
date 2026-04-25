"""
Local development settings.
Never use in production.
"""
from .base import *  # noqa: F401, F403
from decouple import config

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

CORS_ALLOW_ALL_ORIGINS = True

# Verbose logging in dev — see every SQL query and request
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "dev": {
            "format": "[{levelname}] {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "dev",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "DEBUG",
    },
    "loggers": {
        "django.db.backends": {
            "handlers": ["console"],
            "level": config("SQL_LOG_LEVEL", default="WARNING"),
            "propagate": False,
        },
    },
}
