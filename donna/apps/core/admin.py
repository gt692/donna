"""
core/admin.py

Admin-Konfiguration für User, Notification-Templates und -Logs.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import NotificationLog, NotificationSubscription, NotificationTemplate, User


# ---------------------------------------------------------------------------
# User Admin
# ---------------------------------------------------------------------------

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Erweiterter UserAdmin.

    Zeigt Rolle, reporting_to-Hierarchie und TOTP-Status direkt in der Liste.
    """
    list_display  = (
        "username", "get_full_name", "email",
        "role_badge", "reporting_to_link", "totp_status", "is_active",
    )
    list_filter   = ("role", "is_active", "totp_enabled", "is_staff")
    search_fields = ("username", "first_name", "last_name", "email")
    ordering      = ("last_name", "first_name")

    # Spalten-Sortierung
    list_select_related = ("reporting_to",)

    # ── Fieldsets ──────────────────────────────────────────────────────────
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (_("Persönliche Daten"), {"fields": ("first_name", "last_name", "email")}),
        (
            _("Donna-Rollen & Hierarchie"),
            {
                "fields": ("role", "reporting_to"),
                "description": _(
                    "Die reporting_to-Zuweisung steuert, wer Stunden des Nutzers "
                    "genehmigen kann."
                ),
            },
        ),
        (
            _("TOTP / 2FA"),
            {
                "fields": ("totp_secret", "totp_enabled"),
                "classes": ("collapse",),
                "description": _(
                    "Das TOTP-Secret wird beim ersten Login-Setup automatisch generiert. "
                    "Nur in Ausnahmefällen manuell setzen."
                ),
            },
        ),
        (
            _("Benachrichtigungen"),
            {"fields": ("notify_by_email",)},
        ),
        (
            _("Berechtigungen"),
            {
                "fields": (
                    "is_active", "is_staff", "is_superuser",
                    "groups", "user_permissions",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            _("Wichtige Daten"),
            {"fields": ("last_login", "date_joined"), "classes": ("collapse",)},
        ),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username", "email",
                    "first_name", "last_name",
                    "role", "reporting_to",
                    "password1", "password2",
                ),
            },
        ),
    )

    readonly_fields = ("last_login", "date_joined")

    # ── Custom Display-Methoden ────────────────────────────────────────────

    @admin.display(description=_("Rolle"), ordering="role")
    def role_badge(self, obj: User) -> str:
        colors = {
            "admin":             ("#dc2626", "#fee2e2"),   # Rot
            "project_manager":   ("#d97706", "#fef3c7"),   # Amber
            "employee":          ("#2563eb", "#dbeafe"),   # Blau
            "project_assistant": ("#7c3aed", "#ede9fe"),   # Violett
        }
        fg, bg = colors.get(obj.role, ("#6b7280", "#f3f4f6"))
        return format_html(
            '<span style="background:{bg};color:{fg};padding:2px 8px;'
            'border-radius:4px;font-size:11px;font-weight:600;">{label}</span>',
            bg=bg, fg=fg, label=obj.get_role_display(),
        )

    @admin.display(description=_("Berichtet an"), ordering="reporting_to__last_name")
    def reporting_to_link(self, obj: User) -> str:
        if not obj.reporting_to:
            return format_html('<span style="color:#9ca3af;">—</span>')
        return format_html(
            '<a href="/admin/core/user/{pk}/change/">{name}</a>',
            pk=obj.reporting_to.pk,
            name=obj.reporting_to.get_full_name() or obj.reporting_to.username,
        )

    @admin.display(description=_("2FA"), boolean=False)
    def totp_status(self, obj: User) -> str:
        if obj.totp_enabled:
            return format_html(
                '<span style="color:#16a34a;font-weight:600;">✓ Aktiv</span>'
            )
        return format_html(
            '<span style="color:#dc2626;">✗ Inaktiv</span>'
        )


# ---------------------------------------------------------------------------
# Notification-Admin
# ---------------------------------------------------------------------------

@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display  = ("event", "subject", "is_active")
    list_filter   = ("is_active",)
    search_fields = ("event", "subject")
    ordering      = ("event",)


@admin.register(NotificationSubscription)
class NotificationSubscriptionAdmin(admin.ModelAdmin):
    list_display  = ("user", "event", "project")
    list_filter   = ("event",)
    search_fields = ("user__username", "user__email")
    autocomplete_fields = ("user", "project")
    list_select_related = ("user", "project")


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display  = ("created_at", "event", "recipient", "subject", "status_badge", "sent_at")
    list_filter   = ("status", "event")
    search_fields = ("recipient__username", "recipient__email", "subject")
    readonly_fields = (
        "id", "recipient", "event", "subject", "body",
        "status", "error_message", "created_at", "sent_at", "context_payload",
    )
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False  # Logs werden nur vom System erstellt

    def has_change_permission(self, request, obj=None):
        return False  # Read-only

    @admin.display(description=_("Status"))
    def status_badge(self, obj: NotificationLog) -> str:
        colors = {
            "pending": ("#d97706", "#fef3c7"),
            "sent":    ("#16a34a", "#dcfce7"),
            "failed":  ("#dc2626", "#fee2e2"),
        }
        fg, bg = colors.get(obj.status, ("#6b7280", "#f3f4f6"))
        return format_html(
            '<span style="background:{bg};color:{fg};padding:2px 8px;'
            'border-radius:4px;font-size:11px;font-weight:600;">{label}</span>',
            bg=bg, fg=fg, label=obj.get_status_display(),
        )
