"""
config/settings/base.py

Basis-Konfiguration für alle Umgebungen.
Sensible Werte werden ausschließlich über django-environ (.env) geladen.
"""
from pathlib import Path

import environ

# ── Pfade ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent.parent   # /donna/
ROOT_DIR = BASE_DIR.parent                                  # /Donna/

# ── django-environ initialisieren ─────────────────────────────────────────
env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
)
environ.Env.read_env(BASE_DIR / ".env")


# ── Sicherheit ─────────────────────────────────────────────────────────────
SECRET_KEY = env("SECRET_KEY")
DEBUG       = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")


# ── Anwendungen ────────────────────────────────────────────────────────────
DJANGO_APPS = [
    "jazzmin",                              # Muss vor django.contrib.admin stehen
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "django_otp",
    "django_otp.plugins.otp_totp",         # TOTP-Gerät
    "django_otp.plugins.otp_static",       # Backup-Codes
]

LOCAL_APPS = [
    "apps.core.apps.CoreConfig",
    "apps.crm.apps.CrmConfig",
    "apps.worktrack.apps.WorktrackConfig",
    "apps.dashboard.apps.DashboardConfig",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS


# ── Middleware ─────────────────────────────────────────────────────────────
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",              # 2FA-Middleware
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

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
                "apps.core.context_processors.pending_approvals",
                "apps.core.context_processors.lead_pending_count",
                "apps.core.context_processors.company_settings",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# ── Datenbank ──────────────────────────────────────────────────────────────
DATABASES = {
    "default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
}
DATABASES["default"]["ATOMIC_REQUESTS"] = True    # Jeder Request = 1 Transaktion


# ── Auth ───────────────────────────────────────────────────────────────────
AUTH_USER_MODEL = "core.User"                      # Unser erweitertes User-Modell

AUTHENTICATION_BACKENDS = [
    "apps.core.backends.EmailBackend",             # Login per E-Mail
    "django.contrib.auth.backends.ModelBackend",   # Fallback für Admin (Username)
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL          = "/auth/login/"
LOGIN_REDIRECT_URL = "/dashboard/"


# ── Internationalisierung ──────────────────────────────────────────────────
LANGUAGE_CODE = "de-de"
TIME_ZONE     = "Europe/Berlin"
USE_I18N      = True
USE_TZ        = True


# ── Statische & Medien-Dateien ─────────────────────────────────────────────
STATIC_URL  = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL  = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


# ── REST Framework ─────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
}


# ── E-Mail ─────────────────────────────────────────────────────────────────
EMAIL_BACKEND      = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="Donna <noreply@example.com>")

# Microsoft Graph API (OAuth2) — wird genutzt wenn EMAIL_BACKEND auf GraphAPIEmailBackend gesetzt
MS_CLIENT_ID     = env("MS_CLIENT_ID", default="")
MS_TENANT_ID     = env("MS_TENANT_ID", default="")
MS_CLIENT_SECRET = env("MS_CLIENT_SECRET", default="")
MS_SENDER_EMAIL  = env("MS_SENDER_EMAIL", default="donna@direso.de")


# ── Externe Dienste ────────────────────────────────────────────────────────
LEXOFFICE_API_KEY      = env("LEXOFFICE_API_KEY", default="")
LEXOFFICE_API_BASE_URL = env("LEXOFFICE_API_BASE_URL", default="https://api.lexoffice.io/v1")
GOOGLE_MAPS_API_KEY    = env("GOOGLE_MAPS_API_KEY", default="")

# Basis-Pfad für Netzlaufwerk / lokales Storage
STORAGE_BASE_PATH = env("STORAGE_BASE_PATH", default="")


# ── Jazzmin Admin-Theme ────────────────────────────────────────────────────
JAZZMIN_SETTINGS = {
    # Branding
    "site_title":        "Donna",
    "site_header":       "Donna",
    "site_brand":        "Donna",
    "welcome_sign":      "Willkommen bei Donna",
    "copyright":         "Donna Business OS",

    # Layout
    "show_ui_builder":      False,
    "navigation_expanded":  True,
    "hide_apps":            ["auth", "otp_static", "otp_totp"],
    "hide_models":          ["crm.ProductCatalog", "core.Lookup"],
    "order_with_respect_to": [
        "core", "core.User",
        "crm", "crm.Account", "crm.Contact", "crm.Project", "crm.Document",
        "crm.RevenueTarget", "crm.CompanyProjectTypeMapping",
        "worktrack",
    ],

    # Link zurück zur App
    "topmenu_links": [
        {"name": "Zur App", "url": "/dashboard/", "new_window": False},
    ],
    "usermenu_links": [
        {"name": "Zur App", "url": "/dashboard/"},
    ],

    # Icons
    "icons": {
        "auth":                         "fas fa-shield-alt",
        "auth.Group":                   "fas fa-users-cog",
        "core":                         "fas fa-cog",
        "core.User":                    "fas fa-users",
        "core.NotificationTemplate":    "fas fa-bell",
        "crm":                          "fas fa-briefcase",
        "crm.Account":                  "fas fa-building",
        "crm.Contact":                  "fas fa-address-book",
        "crm.Project":                  "fas fa-project-diagram",
        "crm.Document":                 "fas fa-file-alt",
        "crm.RevenueTarget":            "fas fa-bullseye",
        "worktrack":                    "fas fa-clock",
        "worktrack.TimeEntry":          "fas fa-clock",
        "worktrack.ActivityType":       "fas fa-tags",
    },
    "default_icon_parents":  "fas fa-folder",
    "default_icon_children": "fas fa-circle",

    # Formulare
    "related_modal_active": True,
    "changeform_format":    "horizontal_tabs",

    # Custom CSS
    "custom_css": "admin/css/custom.css",
}

JAZZMIN_UI_TWEAKS = {
    "navbar_small_text":        False,
    "footer_small_text":        False,
    "body_small_text":          False,
    "brand_small_text":         False,
    "brand_colour":             False,
    "accent":                   "accent-primary",
    "navbar":                   "navbar-dark",
    "no_navbar_border":         True,
    "navbar_fixed":             True,
    "layout_boxed":             False,
    "footer_fixed":             False,
    "sidebar_fixed":            True,
    "sidebar":                  "sidebar-dark-primary",
    "sidebar_nav_small_text":   False,
    "sidebar_disable_expand":   False,
    "sidebar_nav_child_indent": True,
    "sidebar_nav_compact_style":  False,
    "sidebar_nav_legacy_style":   False,
    "sidebar_nav_flat_style":     False,
    "theme":                    "default",
    "dark_mode_theme":          None,
    "button_classes": {
        "primary":   "btn-primary",
        "secondary": "btn-secondary",
        "info":      "btn-info",
        "warning":   "btn-warning",
        "danger":    "btn-danger",
        "success":   "btn-success",
    },
}
