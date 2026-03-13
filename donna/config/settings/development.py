from .base import *  # noqa: F401, F403

DEBUG = True

INSTALLED_APPS += [  # noqa: F405
    "debug_toolbar",
    "django_extensions",
]

MIDDLEWARE = ["debug_toolbar.middleware.DebugToolbarMiddleware"] + MIDDLEWARE  # noqa: F405

INTERNAL_IPS = ["127.0.0.1"]

ALLOWED_HOSTS += ["192.168.0.126", "0.0.0.0"]  # noqa: F405

# Alle CORS-Anfragen lokal erlauben
CORS_ALLOW_ALL_ORIGINS = True
