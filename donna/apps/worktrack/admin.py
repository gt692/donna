"""
worktrack/admin.py

Admin-Konfiguration für Zeitbuchungen mit Freigabe-Workflow und Batch-Aktionen.
"""
from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import ActivityType, TimeEntry, TimeEntryBulkApproval


# ---------------------------------------------------------------------------
# ActivityType
# ---------------------------------------------------------------------------

@admin.register(ActivityType)
class ActivityTypeAdmin(admin.ModelAdmin):
    list_display  = ("color_dot", "name", "is_billable_default", "is_active")
    list_filter   = ("is_billable_default", "is_active")
    search_fields = ("name",)
    ordering      = ("name",)

    @admin.display(description="")
    def color_dot(self, obj: ActivityType) -> str:
        return format_html(
            '<span style="display:inline-block;width:12px;height:12px;'
            'border-radius:50%;background:{color};"></span>',
            color=obj.color_hex or "#6366f1",
        )


# ---------------------------------------------------------------------------
# TimeEntry
# ---------------------------------------------------------------------------

@admin.register(TimeEntry)
class TimeEntryAdmin(admin.ModelAdmin):
    list_display  = (
        "date", "user", "project_link", "duration_hours",
        "activity_type", "is_billable", "status_badge", "reviewed_by",
    )
    list_filter   = (
        "status", "is_billable", "date",
        "project__account", "activity_type",
    )
    search_fields = (
        "user__username", "user__first_name", "user__last_name",
        "project__name", "description",
    )
    ordering       = ("-date", "-created_at")
    date_hierarchy  = "date"
    autocomplete_fields = ("user", "project", "activity_type", "reviewed_by")
    list_select_related = ("user", "project", "project__account", "reviewed_by", "activity_type")

    fieldsets = (
        (
            None,
            {"fields": ("user", "project", "activity_type", "date", "is_billable")},
        ),
        (
            _("Zeitangaben"),
            {"fields": ("duration_hours", "start_time", "end_time")},
        ),
        (_("Tätigkeit"), {"fields": ("description",)}),
        (
            _("Freigabe"),
            {
                "fields": ("status", "reviewed_by", "reviewed_at", "review_note"),
                "classes": ("collapse",),
            },
        ),
    )

    readonly_fields = ("created_at", "updated_at", "reviewed_at")

    # ── Batch-Aktionen ─────────────────────────────────────────────────────
    actions = ["approve_entries", "reject_entries"]

    @admin.action(description=_("Ausgewählte Buchungen freigeben"))
    def approve_entries(self, request: HttpRequest, queryset: QuerySet) -> None:
        submittable = queryset.filter(status=TimeEntry.Status.SUBMITTED)
        count = 0
        for entry in submittable:
            entry.approve(reviewer=request.user)
            count += 1
        self.message_user(
            request,
            f"{count} Buchung(en) freigegeben.",
            messages.SUCCESS,
        )

    @admin.action(description=_("Ausgewählte Buchungen ablehnen"))
    def reject_entries(self, request: HttpRequest, queryset: QuerySet) -> None:
        submittable = queryset.filter(status=TimeEntry.Status.SUBMITTED)
        count = 0
        for entry in submittable:
            entry.reject(reviewer=request.user, note="Abgelehnt via Admin-Batch-Aktion.")
            count += 1
        self.message_user(
            request,
            f"{count} Buchung(en) abgelehnt.",
            messages.WARNING,
        )

    # ── Custom Display ─────────────────────────────────────────────────────

    @admin.display(description=_("Projekt"), ordering="project__name")
    def project_link(self, obj: TimeEntry) -> str:
        from django.urls import reverse
        url = reverse("admin:crm_project_change", args=[obj.project.pk])
        return format_html(
            '<a href="{url}">{name}</a><br>'
            '<span style="font-size:11px;color:#6b7280;">{account}</span>',
            url=url,
            name=obj.project.name,
            account=obj.project.account.name,
        )

    @admin.display(description=_("Status"), ordering="status")
    def status_badge(self, obj: TimeEntry) -> str:
        colors = {
            "draft":     ("#6b7280", "#f3f4f6"),
            "submitted": ("#d97706", "#fef3c7"),
            "approved":  ("#16a34a", "#dcfce7"),
            "rejected":  ("#dc2626", "#fee2e2"),
        }
        fg, bg = colors.get(obj.status, ("#6b7280", "#f3f4f6"))
        return format_html(
            '<span style="background:{bg};color:{fg};padding:2px 8px;'
            'border-radius:4px;font-size:11px;font-weight:600;">{label}</span>',
            bg=bg, fg=fg, label=obj.get_status_display(),
        )


# ---------------------------------------------------------------------------
# BulkApproval
# ---------------------------------------------------------------------------

@admin.register(TimeEntryBulkApproval)
class TimeEntryBulkApprovalAdmin(admin.ModelAdmin):
    list_display  = ("created_at", "approved_by", "entry_count", "note")
    search_fields = ("approved_by__username",)
    ordering      = ("-created_at",)
    readonly_fields = ("id", "approved_by", "entries", "created_at")
    filter_horizontal = ("entries",)

    def has_add_permission(self, request):
        return False  # Nur über den Freigabe-Workflow erstellt

    @admin.display(description=_("Buchungen"))
    def entry_count(self, obj: TimeEntryBulkApproval) -> int:
        return obj.entries.count()
