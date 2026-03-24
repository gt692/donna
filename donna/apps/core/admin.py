"""
core/admin.py

Admin-Konfiguration für User, Notification-Templates und -Logs.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import CompanySettings, NotificationLog, NotificationSubscription, NotificationTemplate, Role, User, UserRole


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
            _("2FA / Authenticator-App"),
            {
                "fields": ("totp_required", "totp_enabled", "totp_secret"),
                "description": _(
                    "Mit '2FA Pflicht' legt der Admin fest, ob dieser User einen TOTP-Code "
                    "beim Login eingeben muss. 'TOTP eingerichtet' und 'TOTP-Secret' werden "
                    "automatisch gesetzt und sind schreibgeschützt."
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
                    "totp_required",
                ),
            },
        ),
    )

    readonly_fields = ("last_login", "date_joined", "totp_enabled", "totp_secret")

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        role_choices = list(UserRole.objects.values_list("slug", "name"))
        form.base_fields["role"].widget.choices = [("", "— Rolle wählen —")] + role_choices
        return form

    def save_model(self, request, obj, form, change):
        if change and "totp_required" in form.changed_data and not obj.totp_required:
            # Admin hat 2FA deaktiviert → Secret und Status zurücksetzen
            obj.totp_enabled = False
            obj.totp_secret = ""
        super().save_model(request, obj, form, change)

    # ── Custom Display-Methoden ────────────────────────────────────────────

    @admin.display(description=_("Rolle"), ordering="role")
    def role_badge(self, obj: User) -> str:
        colors = {
            "admin":             ("#dc2626", "#fee2e2"),
            "project_manager":   ("#d97706", "#fef3c7"),
            "employee":          ("#2563eb", "#dbeafe"),
            "project_assistant": ("#7c3aed", "#ede9fe"),
        }
        fg, bg = colors.get(obj.role, ("#6b7280", "#f3f4f6"))
        try:
            label = UserRole.objects.get(slug=obj.role).name
        except UserRole.DoesNotExist:
            label = obj.role
        return format_html(
            '<span style="background:{bg};color:{fg};padding:2px 8px;'
            'border-radius:4px;font-size:11px;font-weight:600;">{label}</span>',
            bg=bg, fg=fg, label=label,
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


# ---------------------------------------------------------------------------
# CompanySettings Admin
# ---------------------------------------------------------------------------

@admin.register(CompanySettings)
class CompanySettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        ("Firma", {
            "fields": ("company_name", "legal_form", "slogan", "logo", "primary_color"),
        }),
        ("Adresse", {
            "fields": ("street", "postal_code", "city", "country"),
        }),
        ("Rechtliches", {
            "fields": ("hrb_number", "vat_id", "tax_number"),
        }),
        ("Bankdaten", {
            "fields": ("bank_name", "iban", "bic"),
        }),
        ("Kontakt", {
            "fields": ("email", "phone", "website"),
        }),
        ("PDF-Einstellungen", {
            "fields": ("pdf_footer_text", "payment_days"),
        }),
    )
    readonly_fields = ("updated_at",)

    def has_add_permission(self, request):
        return not CompanySettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


