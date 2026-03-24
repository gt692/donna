"""
crm/admin.py

Admin-Konfiguration für Account, Project und Document.
Projekte zeigen direkt Kunde, Status und Budget-Auslastung.
"""
from django.contrib import admin
from django.db.models import QuerySet, Sum
from django.http import HttpRequest
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import Account, Document, ProductCatalog, Project, ProjectType, RevenueTarget


# ---------------------------------------------------------------------------
# Inlines
# ---------------------------------------------------------------------------

class DocumentInline(admin.TabularInline):
    """Dokumente direkt im Projekt anzeigen."""
    model  = Document
    extra  = 0
    fields = (
        "document_type", "title", "file_path",
        "lexoffice_document_number", "document_date", "net_amount",
    )
    readonly_fields = ("created_at",)
    show_change_link = True


class ProjectInline(admin.TabularInline):
    """Projekte direkt im Account anzeigen (kompakte Übersicht)."""
    model  = Project
    extra  = 0
    fields = ("name", "status", "team_lead", "start_date", "end_date")
    readonly_fields = ("name", "status", "team_lead")
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False  # Projekte über eigene Maske anlegen


# ---------------------------------------------------------------------------
# Account Admin
# ---------------------------------------------------------------------------

@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display  = (
        "name", "account_type_badge", "email",
        "city", "account_manager", "project_count", "is_active",
    )
    list_filter   = ("account_type", "is_active", "country")
    search_fields = ("name", "email", "lexoffice_id", "city")
    ordering      = ("name",)
    autocomplete_fields = ("account_manager",)
    list_select_related = ("account_manager",)

    fieldsets = (
        (None, {"fields": ("name", "account_type", "is_active", "account_manager")}),
        (
            _("Kontakt"),
            {"fields": ("email", "phone", "website"), "classes": ("collapse",)},
        ),
        (
            _("Adresse"),
            {
                "fields": (
                    "address_line1", "address_line2",
                    "postal_code", "city", "country",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            _("Lexoffice"),
            {
                "fields": ("lexoffice_id",),
                "description": _("Wird für die Lexoffice-Synchronisation benötigt."),
            },
        ),
        (_("Notizen"), {"fields": ("notes",), "classes": ("collapse",)}),
    )

    readonly_fields = ("created_at", "updated_at")
    inlines = [ProjectInline]

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        return super().get_queryset(request).prefetch_related("projects")

    @admin.display(description=_("Typ"), ordering="account_type")
    def account_type_badge(self, obj: Account) -> str:
        colors = {
            "private":  ("#1666b0", "#ddf1fb"),
            "company":  ("#2563eb", "#dbeafe"),
            "estate":   ("#0891b2", "#cffafe"),
            "internal": ("#7c3aed", "#ede9fe"),
        }
        fg, bg = colors.get(obj.account_type, ("#6b7280", "#f3f4f6"))
        return format_html(
            '<span style="background:{bg};color:{fg};padding:2px 8px;'
            'border-radius:4px;font-size:11px;font-weight:600;">{label}</span>',
            bg=bg, fg=fg, label=obj.get_account_type_display(),
        )

    @admin.display(description=_("Projekte"))
    def project_count(self, obj: Account) -> str:
        count = obj.projects.count()
        url   = (
            reverse("admin:crm_project_changelist")
            + f"?account__id__exact={obj.pk}"
        )
        return format_html('<a href="{url}">{count}</a>', url=url, count=count)


# ---------------------------------------------------------------------------
# Project Admin
# ---------------------------------------------------------------------------

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display  = (
        "name", "account_link", "status_badge",
        "team_lead", "budget_progress", "start_date", "end_date",
    )
    list_filter   = ("status", "account", "team_lead")
    search_fields = ("name", "internal_reference", "lexoffice_id", "account__name")
    ordering      = ("-created_at",)
    date_hierarchy = "start_date"
    autocomplete_fields = ("account", "team_lead", "team_members", "created_by")
    list_select_related = ("account", "team_lead")
    filter_horizontal   = ("team_members",)

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name", "account", "status",
                    "internal_reference", "description",
                ),
            },
        ),
        (
            _("Team"),
            {"fields": ("team_lead", "team_members", "created_by")},
        ),
        (
            _("Zeitraum"),
            {"fields": ("start_date", "end_date"), "classes": ("collapse",)},
        ),
        (
            _("Budget"),
            {
                "fields": ("budget_hours", "budget_amount", "hourly_rate"),
                "classes": ("collapse",),
            },
        ),
        (
            _("Speicher & Lexoffice"),
            {
                "fields": ("storage_path", "lexoffice_id"),
                "description": _(
                    "storage_path: UNC-Pfad oder Azure-Blob-Key zum Projektordner. "
                    "lexoffice_id: UUID des Vorgangs in Lexoffice."
                ),
            },
        ),
    )

    readonly_fields = ("created_at", "updated_at")
    inlines = [DocumentInline]

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        return (
            super().get_queryset(request)
            .select_related("account", "team_lead")
            .prefetch_related("time_entries")
        )

    # ── Custom Display ─────────────────────────────────────────────────────

    @admin.display(description=_("Kunde"), ordering="account__name")
    def account_link(self, obj: Project) -> str:
        if not obj.account:
            return format_html('<span style="color:#9ca3af;">—</span>')
        url = reverse("admin:crm_account_change", args=[obj.account.pk])
        return format_html('<a href="{url}">{name}</a>', url=url, name=obj.account.name)

    @admin.display(description=_("Status"), ordering="status")
    def status_badge(self, obj: Project) -> str:
        colors = {
            "lead":       ("#6b7280", "#f3f4f6"),
            "offer_sent": ("#d97706", "#fef3c7"),
            "active":     ("#16a34a", "#dcfce7"),
            "on_hold":    ("#9333ea", "#f3e8ff"),
            "completed":  ("#2563eb", "#dbeafe"),
            "cancelled":  ("#dc2626", "#fee2e2"),
        }
        fg, bg = colors.get(obj.status, ("#6b7280", "#f3f4f6"))
        return format_html(
            '<span style="background:{bg};color:{fg};padding:2px 8px;'
            'border-radius:4px;font-size:11px;font-weight:600;">{label}</span>',
            bg=bg, fg=fg, label=obj.get_status_display(),
        )

    @admin.display(description=_("Budget-Auslastung"))
    def budget_progress(self, obj: Project) -> str:
        if obj.budget_hours is None:
            return format_html('<span style="color:#9ca3af;">Kein Budget</span>')

        logged = obj.get_logged_hours()
        budget = float(obj.budget_hours)
        pct    = min(int(logged / budget * 100), 100) if budget > 0 else 0

        color = "#16a34a"   # Grün
        if pct >= 90:
            color = "#dc2626"  # Rot
        elif pct >= 75:
            color = "#d97706"  # Amber

        return format_html(
            '<div style="display:flex;align-items:center;gap:6px;">'
            '  <div style="width:80px;background:#e5e7eb;border-radius:4px;height:8px;">'
            '    <div style="width:{pct}%;background:{color};border-radius:4px;height:8px;"></div>'
            '  </div>'
            '  <span style="font-size:11px;color:{color};font-weight:600;">'
            '    {logged:.1f} / {budget:.0f} h ({pct}%)</span>'
            '</div>',
            pct=pct, color=color, logged=logged, budget=budget,
        )


# ---------------------------------------------------------------------------
# RevenueTarget Admin
# ---------------------------------------------------------------------------

@admin.register(RevenueTarget)
class RevenueTargetAdmin(admin.ModelAdmin):
    list_display  = ("company", "year", "target_amount")
    list_editable = ("target_amount",)
    list_filter   = ("company", "year")
    ordering      = ("-year", "company")

    def get_form(self, request, obj=None, **kwargs):
        from django import forms as dj_forms
        from apps.core.models import Lookup
        form = super().get_form(request, obj, **kwargs)
        company_choices = [("", "---------")] + Lookup.choices_for("company")
        form.base_fields["company"].widget = dj_forms.Select(choices=company_choices)
        return form


# ---------------------------------------------------------------------------
# ProjectType Admin
# ---------------------------------------------------------------------------

@admin.register(ProjectType)
class ProjectTypeAdmin(admin.ModelAdmin):
    list_display  = ("name", "color", "order", "is_active")
    list_editable = ("order", "is_active")
    ordering      = ("order", "name")

    def get_form(self, request, obj=None, **kwargs):
        from django import forms as dj_forms
        from apps.core.models import Lookup
        form = super().get_form(request, obj, **kwargs)
        company_choices = [("", "---------")] + Lookup.choices_for("company")
        pt_choices      = [("", "---------")] + Lookup.choices_for("project_type")
        form.base_fields["company"].widget      = dj_forms.Select(choices=company_choices)
        form.base_fields["project_type"].widget = dj_forms.Select(choices=pt_choices)
        return form


# ---------------------------------------------------------------------------
# Document Admin
# ---------------------------------------------------------------------------

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display  = (
        "title", "document_type_badge", "project",
        "lexoffice_document_number", "document_date", "net_amount", "gross_amount",
    )
    list_filter   = ("document_type", "document_date")
    search_fields = (
        "title", "lexoffice_id", "lexoffice_document_number",
        "project__name", "project__account__name",
    )
    ordering      = ("-document_date", "-created_at")
    date_hierarchy = "document_date"
    autocomplete_fields = ("project", "uploaded_by")
    list_select_related = ("project", "project__account")

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "project", "document_type", "title",
                    "document_date", "due_date",
                ),
            },
        ),
        (
            _("Dateipfad"),
            {
                "fields": ("file_path",),
                "description": _(
                    "Vollständiger Pfad zur Datei auf dem Netzlaufwerk oder "
                    "Azure Blob Storage Key."
                ),
            },
        ),
        (
            _("Lexoffice"),
            {"fields": ("lexoffice_id", "lexoffice_document_number")},
        ),
        (
            _("Beträge"),
            {"fields": ("net_amount", "gross_amount"), "classes": ("collapse",)},
        ),
        (
            _("Metadaten"),
            {"fields": ("uploaded_by", "notes"), "classes": ("collapse",)},
        ),
    )

    readonly_fields = ("created_at", "updated_at")

    @admin.display(description=_("Typ"), ordering="document_type")
    def document_type_badge(self, obj: Document) -> str:
        colors = {
            "offer":    ("#2563eb", "#dbeafe"),
            "invoice":  ("#16a34a", "#dcfce7"),
            "contract": ("#7c3aed", "#ede9fe"),
            "delivery": ("#0891b2", "#cffafe"),
            "misc":     ("#6b7280", "#f3f4f6"),
        }
        fg, bg = colors.get(obj.document_type, ("#6b7280", "#f3f4f6"))
        return format_html(
            '<span style="background:{bg};color:{fg};padding:2px 8px;'
            'border-radius:4px;font-size:11px;font-weight:600;">{label}</span>',
            bg=bg, fg=fg, label=obj.get_document_type_display(),
        )


# ---------------------------------------------------------------------------
# ProductCatalog Admin
# ---------------------------------------------------------------------------

@admin.register(ProductCatalog)
class ProductCatalogAdmin(admin.ModelAdmin):
    list_display  = ["name", "category", "unit_price", "unit", "quantity", "is_active", "sort_order"]
    list_editable = ["unit_price", "is_active", "sort_order"]
    list_filter   = ["is_active", "category"]
    search_fields = ["name", "description"]
