"""
worktrack/models.py

Zeiterfassung mit einem expliziten Status-Workflow:
  draft → submitted → approved / rejected

Teamleiter können Stunden ihrer direct_reports freigeben.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


# ---------------------------------------------------------------------------
# TimeEntry — einzelne Stundenbuchung
# ---------------------------------------------------------------------------

class TimeEntry(models.Model):
    """
    Eine einzelne Zeitbuchung eines Mitarbeiters auf ein Projekt.

    Status-Workflow:
        DRAFT       → Mitarbeiter arbeitet noch daran
        SUBMITTED   → Eingereicht, wartet auf Freigabe
        APPROVED    → Vom Teamleiter / Admin genehmigt
        REJECTED    → Abgelehnt (mit Begründung)
    """
    class Status(models.TextChoices):
        DRAFT     = "draft",     _("Entwurf")
        SUBMITTED = "submitted", _("Eingereicht")
        APPROVED  = "approved",  _("Freigegeben")
        REJECTED  = "rejected",  _("Abgelehnt")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Wer hat gebucht?
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="time_entries",
        verbose_name=_("Mitarbeiter"),
    )

    # Auf welches Projekt?
    project = models.ForeignKey(
        "crm.Project",
        on_delete=models.PROTECT,
        related_name="time_entries",
        verbose_name=_("Projekt"),
    )

    # Zeitangaben
    date = models.DateField(verbose_name=_("Datum"))
    duration_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.25")), MaxValueValidator(Decimal("24.00"))],
        verbose_name=_("Dauer (Stunden)"),
        help_text=_("Mindestens 0,25 h (15 min), maximal 24 h."),
    )
    start_time = models.TimeField(null=True, blank=True, verbose_name=_("Startzeit"))
    end_time   = models.TimeField(null=True, blank=True, verbose_name=_("Endzeit"))

    # Beschreibung der Tätigkeit
    description = models.TextField(verbose_name=_("Tätigkeit"))

    # Tätigkeitsart
    class ActivityCategory(models.TextChoices):
        AG_RUECKSPRACHE  = "ag_ruecksprache",   _("AG Rücksprache")
        AKQUISE          = "akquise",           _("Akquise")
        BEARBEITUNG      = "bearbeitung",       _("Bearbeitung des Projekts")
        BESPRECHUNG      = "besprechung",       _("Besprechung")
        ERHEBUNGEN       = "erhebungen",        _("Erhebungen")
        MAILS_TELEFONATE = "mails_telefonate",  _("Mails-Telefonate")
        ORTSTERMIN       = "ortstermin",        _("Ortstermin")
        PROJEKTABLAGE    = "projektablage",     _("Projektablage")

    activity_type = models.CharField(
        max_length=30,
        choices=ActivityCategory.choices,
        blank=True,
        default="",
        verbose_name=_("Tätigkeitsart"),
    )

    # Fakturierbar?
    is_billable = models.BooleanField(
        default=True,
        verbose_name=_("Fakturierbar"),
        help_text=_("Ob diese Stunden dem Kunden in Rechnung gestellt werden können."),
    )

    # Status-Workflow
    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name=_("Status"),
    )

    # Freigabe-Informationen
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_time_entries",
        verbose_name=_("Geprüft von"),
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Geprüft am"))
    review_note = models.TextField(
        blank=True,
        verbose_name=_("Prüfnotiz"),
        help_text=_("Pflichtfeld bei Ablehnung."),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Zeitbuchung")
        verbose_name_plural = _("Zeitbuchungen")
        ordering = ["-date", "-created_at"]
        indexes = [
            models.Index(fields=["user", "date"]),
            models.Index(fields=["project", "status"]),
        ]

    def __str__(self) -> str:
        return (
            f"{self.user} | {self.project} | "
            f"{self.date} | {self.duration_hours} h [{self.get_status_display()}]"
        )

    # ------------------------------------------------------------------
    # Status-Transitions (Business-Logic in Methoden kapseln)
    # ------------------------------------------------------------------

    def submit(self) -> None:
        """Mitarbeiter reicht Stunden ein."""
        if self.status != self.Status.DRAFT:
            raise ValueError(_("Nur Entwürfe können eingereicht werden."))
        self.status = self.Status.SUBMITTED
        self.save(update_fields=["status", "updated_at"])

    def approve(self, reviewer: settings.AUTH_USER_MODEL) -> None:
        """Teamleiter / Admin genehmigt."""
        if self.status != self.Status.SUBMITTED:
            raise ValueError(_("Nur eingereichte Buchungen können genehmigt werden."))
        self.status      = self.Status.APPROVED
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])

    def reject(self, reviewer: settings.AUTH_USER_MODEL, note: str) -> None:
        """Teamleiter / Admin lehnt ab."""
        if self.status != self.Status.SUBMITTED:
            raise ValueError(_("Nur eingereichte Buchungen können abgelehnt werden."))
        if not note:
            raise ValueError(_("Eine Begründung ist bei der Ablehnung Pflicht."))
        self.status      = self.Status.REJECTED
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.review_note = note
        self.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note", "updated_at"])


# ---------------------------------------------------------------------------
# ActivityType — Tätigkeitskategorien
# ---------------------------------------------------------------------------

class ActivityType(models.Model):
    """
    Kategorisiert Tätigkeiten (z.B. Entwicklung, Beratung, Dokumentation).
    Ermöglicht spätere Auswertungen nach Tätigkeitsart.
    """
    name = models.CharField(max_length=100, unique=True, verbose_name=_("Name"))
    is_billable_default = models.BooleanField(
        default=True,
        verbose_name=_("Standardmäßig fakturierbar"),
    )
    color_hex = models.CharField(
        max_length=7,
        blank=True,
        default="#6366f1",
        verbose_name=_("Farbe (Hex)"),
        help_text=_("Für die spätere UI-Darstellung, z.B. '#6366f1'."),
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = _("Tätigkeitsart")
        verbose_name_plural = _("Tätigkeitsarten")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


# ---------------------------------------------------------------------------
# TimeEntryBulkApproval — Batch-Freigabe durch Teamleiter
# ---------------------------------------------------------------------------

class TimeEntryBulkApproval(models.Model):
    """
    Protokolliert eine Batch-Freigabe, z.B. „Teamleiter X hat alle
    Stunden von Mitarbeiter Y für Monat 2024-11 freigegeben."

    Erleichtert das Audit-Trail und reduziert einzelne Approve-Calls.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="bulk_approvals_made",
        verbose_name=_("Freigegeben von"),
    )
    entries = models.ManyToManyField(
        TimeEntry,
        related_name="bulk_approvals",
        verbose_name=_("Zeitbuchungen"),
    )
    note = models.TextField(blank=True, verbose_name=_("Anmerkung"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Batch-Freigabe")
        verbose_name_plural = _("Batch-Freigaben")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Batch-Freigabe von {self.approved_by} am {self.created_at:%Y-%m-%d %H:%M}"
