from .base import *  # noqa: F401, F403

DEBUG = False

# ── Sicherheit ─────────────────────────────────────────────────────────────
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["donna-app.de", "www.donna-app.de"])  # noqa: F405

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT       = True
SESSION_COOKIE_SECURE     = True
CSRF_COOKIE_SECURE        = True
SECURE_HSTS_SECONDS       = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD       = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS           = "DENY"

# ── CORS ───────────────────────────────────────────────────────────────────
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])  # noqa: F405

# ── Logging ────────────────────────────────────────────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "file": {
            "level": "WARNING",
            "class": "logging.FileHandler",
            "filename": BASE_DIR / "logs" / "donna.log",  # noqa: F405
            "formatter": "verbose",
        },
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["file", "console"],
        "level": "WARNING",
    },
    "loggers": {
        "django": {
            "handlers": ["file"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}
