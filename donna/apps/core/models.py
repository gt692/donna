"""
core/models.py

Zentrales User-Modell mit Rollenverteilung und TOTP-2FA-Infrastruktur.
Außerdem: NotificationService-Schema nach Observer-Pattern.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import timedelta

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

class Role(models.TextChoices):
    ADMIN               = "admin",               _("Administrator")
    PROJECT_MANAGER     = "project_manager",     _("Projektleiter")
    EMPLOYEE            = "employee",            _("Mitarbeiter")
    PROJECT_ASSISTANT   = "project_assistant",   _("Projektassistenz")


class NotificationEvent(models.TextChoices):
    """Alle Ereignisse, auf die der NotificationService reagieren kann."""
    INVOICE_CREATED       = "invoice_created",       _("Rechnung erstellt")
    INVOICE_PAID          = "invoice_paid",           _("Rechnung bezahlt")
    OFFER_CREATED         = "offer_created",          _("Angebot erstellt")
    BUDGET_WARNING        = "budget_warning",         _("Budget-Warnung (80 %)")
    BUDGET_EXCEEDED       = "budget_exceeded",        _("Budget überschritten")
    TIME_ENTRY_SUBMITTED  = "time_entry_submitted",   _("Stunden eingereicht")
    TIME_ENTRY_APPROVED   = "time_entry_approved",    _("Stunden freigegeben")
    TIME_ENTRY_REJECTED   = "time_entry_rejected",    _("Stunden abgelehnt")
    PROJECT_STATUS_CHANGE = "project_status_change",  _("Projektstatus geändert")


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class User(AbstractUser):
    """
    Erweitertes User-Modell.

    Ergänzt AbstractUser um:
    - Pflichtfeld `role` (Admin / Teamleiter / Mitarbeiter)
    - TOTP-2FA-Felder (Secret + aktiviert-Flag)
    - optionale Verknüpfung zu einem Teamleiter (für Mitarbeiter)
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    role = models.CharField(
        max_length=30,
        choices=Role.choices,
        default=Role.EMPLOYEE,
        verbose_name=_("Rolle"),
    )

    # TOTP-2FA  (Secret wird von django-otp / pyotp befüllt)
    totp_secret = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("TOTP-Secret"),
        help_text=_("Base32-kodiertes Secret für TOTP-Authenticator-Apps."),
    )
    totp_enabled = models.BooleanField(
        default=False,
        verbose_name=_("TOTP aktiviert"),
    )

    # Hierarchie: Wem berichtet dieser User? (Mitarbeiter → Teamleiter → Admin)
    reporting_to = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="direct_reports",
        verbose_name=_("Berichtet an"),
        help_text=_(
            "Vorgesetzter dieses Benutzers. "
            "Teamleiter sehen und genehmigen die Stunden ihrer direct_reports."
        ),
    )

    # Benachrichtigungs-Präferenzen
    notify_by_email = models.BooleanField(default=True, verbose_name=_("E-Mail-Benachrichtigungen"))

    # Einladungs-Flow
    invitation_token = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        verbose_name=_("Einladungs-Token"),
    )
    invitation_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Einladung gesendet am"),
    )

    class Meta:
        verbose_name = _("Benutzer")
        verbose_name_plural = _("Benutzer")
        ordering = ["last_name", "first_name"]

    def __str__(self) -> str:
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"

    # ------------------------------------------------------------------
    # Convenience-Properties
    # ------------------------------------------------------------------

    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMIN

    @property
    def is_project_manager(self) -> bool:
        return self.role == Role.PROJECT_MANAGER

    @property
    def is_employee(self) -> bool:
        return self.role == Role.EMPLOYEE

    @property
    def is_project_assistant(self) -> bool:
        return self.role == Role.PROJECT_ASSISTANT

    def can_approve_time_entries(self) -> bool:
        """Projektleiter und Admins dürfen Stundeneinträge freigeben."""
        return self.role in (Role.ADMIN, Role.PROJECT_MANAGER)

    # ------------------------------------------------------------------
    # Einladungs-Hilfsmethoden
    # ------------------------------------------------------------------

    def generate_invitation_token(self) -> str:
        """Erstellt einen neuen sicheren Token und speichert ihn."""
        token = secrets.token_urlsafe(32)
        self.invitation_token   = token
        self.invitation_sent_at = timezone.now()
        self.save(update_fields=["invitation_token", "invitation_sent_at"])
        return token

    def is_invitation_valid(self) -> bool:
        """True wenn Token gesetzt und nicht älter als 7 Tage."""
        if not self.invitation_token or not self.invitation_sent_at:
            return False
        return timezone.now() - self.invitation_sent_at < timedelta(days=7)

    def accept_invitation(self, raw_password: str) -> None:
        """Passwort setzen, Token löschen, Account aktivieren."""
        self.set_password(raw_password)
        self.invitation_token   = ""
        self.invitation_sent_at = None
        self.is_active          = True
        self.save(update_fields=["password", "invitation_token", "invitation_sent_at", "is_active"])

    def get_approvable_users(self) -> models.QuerySet:
        """
        Gibt alle User zurück, deren Stunden dieser User genehmigen darf.
        Admins sehen alle, Teamleiter nur ihre direct_reports.
        """
        if self.is_admin:
            return User.objects.exclude(pk=self.pk)
        if self.is_project_manager:
            return self.direct_reports.all()
        return User.objects.none()


# ---------------------------------------------------------------------------
# NotificationService — Observer-Pattern
# ---------------------------------------------------------------------------

class NotificationTemplate(models.Model):
    """
    Definiert den E-Mail-/In-App-Inhalt für ein bestimmtes Ereignis.

    Ermöglicht späteres Pflegen der Texte über das Admin-Interface,
    ohne Code anzufassen.
    """
    event = models.CharField(
        max_length=50,
        choices=NotificationEvent.choices,
        unique=True,
        verbose_name=_("Ereignis"),
    )
    subject = models.CharField(max_length=255, verbose_name=_("Betreff"))
    body_template = models.TextField(
        verbose_name=_("Nachrichtenvorlage"),
        help_text=_(
            "Django-Template-Syntax. Verfügbare Variablen hängen vom Ereignis ab, "
            "z.B. {{ project.name }}, {{ invoice.amount }}."
        ),
    )
    is_active = models.BooleanField(default=True, verbose_name=_("Aktiv"))

    class Meta:
        verbose_name = _("Benachrichtigungsvorlage")
        verbose_name_plural = _("Benachrichtigungsvorlagen")

    def __str__(self) -> str:
        return f"[{self.get_event_display()}] {self.subject}"


class NotificationSubscription(models.Model):
    """
    Observer-Registrierung: Welcher User möchte über welches Ereignis informiert werden?

    Ermöglicht granulare Abonnements pro User + Ereignis.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notification_subscriptions",
        verbose_name=_("Benutzer"),
    )
    event = models.CharField(
        max_length=50,
        choices=NotificationEvent.choices,
        verbose_name=_("Ereignis"),
    )
    # Optionale Einschränkung auf ein bestimmtes Projekt (NULL = alle Projekte)
    project = models.ForeignKey(
        "crm.Project",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="notification_subscriptions",
        verbose_name=_("Projekt (optional)"),
    )

    class Meta:
        verbose_name = _("Benachrichtigungs-Abonnement")
        verbose_name_plural = _("Benachrichtigungs-Abonnements")
        unique_together = [("user", "event", "project")]

    def __str__(self) -> str:
        project_label = f" @ {self.project}" if self.project_id else " (global)"
        return f"{self.user} → {self.get_event_display()}{project_label}"


class NotificationLog(models.Model):
    """
    Protokolliert jede versendete Benachrichtigung für Audit-Zwecke.
    """
    class DeliveryStatus(models.TextChoices):
        PENDING = "pending", _("Ausstehend")
        SENT    = "sent",    _("Gesendet")
        FAILED  = "failed",  _("Fehlgeschlagen")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="notification_logs",
        verbose_name=_("Empfänger"),
    )
    event = models.CharField(max_length=50, choices=NotificationEvent.choices, verbose_name=_("Ereignis"))
    subject = models.CharField(max_length=255, verbose_name=_("Betreff"))
    body = models.TextField(verbose_name=_("Inhalt"))
    status = models.CharField(
        max_length=10,
        choices=DeliveryStatus.choices,
        default=DeliveryStatus.PENDING,
        verbose_name=_("Status"),
    )
    error_message = models.TextField(blank=True, verbose_name=_("Fehlermeldung"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Erstellt am"))
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Gesendet am"))

    # Generischer Kontext-Payload (JSON), damit wir den Ereignis-Kontext nachvollziehen können
    context_payload = models.JSONField(default=dict, blank=True, verbose_name=_("Kontext-Payload"))

    class Meta:
        verbose_name = _("Benachrichtigungs-Log")
        verbose_name_plural = _("Benachrichtigungs-Logs")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.event} → {self.recipient} [{self.status}] {self.created_at:%Y-%m-%d %H:%M}"
