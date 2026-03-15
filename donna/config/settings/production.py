from .base import *  # noqa: F401, F403

DEBUG = False

# ── Sicherheit ─────────────────────────────────────────────────────────────
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["donna-app.de", "www.donna-app.de", "187.124.164.248"])  # noqa: F405

CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=["https://donna-app.de", "https://www.donna-app.de", "http://187.124.164.248"])  # noqa: F405

# HTTPS-Einstellungen — werden auf True gesetzt sobald SSL eingerichtet ist
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT       = False  # TODO: True nach SSL-Setup
SESSION_COOKIE_SECURE     = False  # TODO: True nach SSL-Setup
CSRF_COOKIE_SECURE        = False  # TODO: True nach SSL-Setup
SECURE_HSTS_SECONDS       = 0      # TODO: 31536000 nach SSL-Setup
SECURE_HSTS_INCLUDE_SUBDOMAINS = False  # TODO: True nach SSL-Setup
SECURE_HSTS_PRELOAD       = False  # TODO: True nach SSL-Setup
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
