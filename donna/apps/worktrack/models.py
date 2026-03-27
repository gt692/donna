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

    # Abrechnung
    invoiced_in = models.ForeignKey(
        "crm.Invoice",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="imported_time_entries",
        verbose_name=_("Abgerechnet in Rechnung"),
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
# PublicHoliday — Feiertage & firmenweit geschenkte Tage
# ---------------------------------------------------------------------------

class PublicHoliday(models.Model):
    """
    Gesetzliche Feiertage und vom Arbeitgeber geschenkte freie Tage.
    Werden in der Wochenansicht aller Mitarbeiter angezeigt.
    """
    date = models.DateField(unique=True, verbose_name=_("Datum"))
    name = models.CharField(max_length=100, verbose_name=_("Bezeichnung"))
    is_half_day = models.BooleanField(
        default=False,
        verbose_name=_("Halber Tag"),
        help_text=_("z.B. Heiligabend Nachmittag"),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Aktiv"),
        help_text=_("Inaktive Feiertage werden nicht angezeigt."),
    )
    note = models.CharField(max_length=200, blank=True, verbose_name=_("Hinweis"))

    class Meta:
        verbose_name = _("Feiertag")
        verbose_name_plural = _("Feiertage")
        ordering = ["date"]

    def __str__(self) -> str:
        suffix = " (½ Tag)" if self.is_half_day else ""
        return f"{self.date:%d.%m.%Y} – {self.name}{suffix}"


# ---------------------------------------------------------------------------
# WorkSchedule — Arbeitszeitmodell pro Mitarbeiter
# ---------------------------------------------------------------------------

class WorkSchedule(models.Model):
    """Wöchentliche Soll-Arbeitszeit eines Mitarbeiters."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="work_schedule",
        verbose_name=_("Mitarbeiter"),
    )
    hours_per_week = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        default=Decimal("40.0"),
        verbose_name=_("Soll-Stunden / Woche"),
    )
    days_per_week = models.PositiveSmallIntegerField(
        default=5,
        verbose_name=_("Arbeitstage / Woche"),
    )
    vacation_days_per_year = models.PositiveSmallIntegerField(
        default=30,
        verbose_name=_("Urlaubstage / Jahr"),
    )
    track_overtime = models.BooleanField(
        default=True,
        verbose_name=_("Überstunden erfassen"),
        help_text=_("Bei Vertrauensarbeitszeit deaktivieren."),
    )
    default_start_time = models.TimeField(
        null=True, blank=True,
        verbose_name=_("Standard-Arbeitsbeginn"),
        help_text=_("z.B. 08:00 — ermöglicht Schnell-Erfassung ganzer Tage."),
    )
    default_end_time = models.TimeField(
        null=True, blank=True,
        verbose_name=_("Standard-Arbeitsende"),
        help_text=_("z.B. 16:00"),
    )
    default_break_mins = models.PositiveSmallIntegerField(
        default=30,
        verbose_name=_("Standard-Pause (Minuten)"),
    )

    class Meta:
        verbose_name = _("Arbeitszeitmodell")
        verbose_name_plural = _("Arbeitszeitmodelle")

    def __str__(self) -> str:
        return f"{self.user} — {self.hours_per_week} h/Woche"

    def hours_per_day(self) -> Decimal:
        if self.days_per_week:
            return (self.hours_per_week / self.days_per_week).quantize(Decimal("0.01"))
        return Decimal("0")


# ---------------------------------------------------------------------------
# WorkdayLog — Stempeluhr (Kommen / Gehen / Pause)
# ---------------------------------------------------------------------------

class WorkdayLog(models.Model):
    """Stempeluhr-Eintrag: wann hat ein Mitarbeiter angefangen/aufgehört."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="workday_logs",
        verbose_name=_("Mitarbeiter"),
    )
    date = models.DateField(verbose_name=_("Datum"))
    start_time = models.TimeField(null=True, blank=True, verbose_name=_("Arbeitsbeginn"))
    end_time = models.TimeField(null=True, blank=True, verbose_name=_("Arbeitsende"))
    break_mins = models.PositiveSmallIntegerField(
        default=0,
        verbose_name=_("Pause (Minuten)"),
    )
    note = models.CharField(max_length=255, blank=True, verbose_name=_("Notiz"))

    class Meta:
        verbose_name = _("Stempeluhr-Eintrag")
        verbose_name_plural = _("Stempeluhr-Einträge")
        unique_together = [("user", "date")]
        ordering = ["-date"]

    def __str__(self) -> str:
        return f"{self.user} | {self.date}"

    @property
    def net_hours(self) -> Decimal:
        """Nettoarbeitszeit in Stunden (ohne Pause)."""
        if self.start_time and self.end_time:
            import datetime as dt
            delta = dt.datetime.combine(dt.date.today(), self.end_time) \
                  - dt.datetime.combine(dt.date.today(), self.start_time)
            gross = Decimal(str(delta.seconds / 3600))
            pause = Decimal(str(self.break_mins / 60))
            return max(Decimal("0"), gross - pause).quantize(Decimal("0.01"))
        return Decimal("0")


# ---------------------------------------------------------------------------
# Absence — Abwesenheiten (Urlaub, Krankheit, Sonstiges)
# ---------------------------------------------------------------------------

class Absence(models.Model):
    """Eine Abwesenheit eines Mitarbeiters (Urlaub, Krankheit, …)."""

    class AbsenceType(models.TextChoices):
        VACATION   = "vacation",   _("Urlaub")
        SICK       = "sick",       _("Krankmeldung")
        SPECIAL    = "special",    _("Sonderurlaub")
        OTHER      = "other",      _("Sonstiges")

    class Status(models.TextChoices):
        PENDING  = "pending",  _("Beantragt")
        APPROVED = "approved", _("Genehmigt")
        REJECTED = "rejected", _("Abgelehnt")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="absences",
        verbose_name=_("Mitarbeiter"),
    )
    absence_type = models.CharField(
        max_length=20,
        choices=AbsenceType.choices,
        default=AbsenceType.VACATION,
        verbose_name=_("Art"),
    )
    start_date = models.DateField(verbose_name=_("Von"))
    end_date = models.DateField(verbose_name=_("Bis"))
    note = models.TextField(blank=True, verbose_name=_("Notiz"))

    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name=_("Status"),
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_absences",
        verbose_name=_("Genehmigt von"),
    )
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Genehmigt am"))

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Abwesenheit")
        verbose_name_plural = _("Abwesenheiten")
        ordering = ["-start_date"]
        indexes = [
            models.Index(fields=["user", "start_date", "end_date"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return f"{self.user} | {self.get_absence_type_display()} {self.start_date}–{self.end_date}"

    @property
    def working_days(self) -> int:
        """Anzahl Werktage (Mo–Fr) im Zeitraum."""
        import datetime as dt
        days = 0
        current = self.start_date
        while current <= self.end_date:
            if current.weekday() < 5:  # Mo=0 … Fr=4
                days += 1
            current += dt.timedelta(days=1)
        return days

    def approve(self, approver) -> None:
        self.status = self.Status.APPROVED
        self.approved_by = approver
        self.approved_at = timezone.now()
        self.save(update_fields=["status", "approved_by", "approved_at"])

    def reject(self, approver) -> None:
        self.status = self.Status.REJECTED
        self.approved_by = approver
        self.approved_at = timezone.now()
        self.save(update_fields=["status", "approved_by", "approved_at"])


# ---------------------------------------------------------------------------
# VacationAllowance — Urlaubskonto pro Jahr
# ---------------------------------------------------------------------------

class VacationAllowance(models.Model):
    """Urlaubsanspruch und -verbrauch pro Mitarbeiter und Jahr."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="vacation_allowances",
        verbose_name=_("Mitarbeiter"),
    )
    year = models.PositiveSmallIntegerField(verbose_name=_("Jahr"))
    total_days = models.PositiveSmallIntegerField(
        default=30,
        verbose_name=_("Urlaubstage gesamt"),
    )
    carry_over_days = models.PositiveSmallIntegerField(
        default=0,
        verbose_name=_("Übertrag aus Vorjahr"),
    )

    class Meta:
        verbose_name = _("Urlaubskonto")
        verbose_name_plural = _("Urlaubskonten")
        unique_together = [("user", "year")]
        ordering = ["-year", "user__last_name"]

    def __str__(self) -> str:
        return f"{self.user} — {self.year}: {self.total_days} Tage"

    @property
    def available_days(self) -> int:
        return self.total_days + self.carry_over_days

    def used_days(self) -> int:
        """Genehmigte Urlaubstage im Jahr."""
        return sum(
            a.working_days
            for a in self.user.absences.filter(
                absence_type=Absence.AbsenceType.VACATION,
                status=Absence.Status.APPROVED,
                start_date__year=self.year,
            )
        )

    def remaining_days(self) -> int:
        return self.available_days - self.used_days()


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
