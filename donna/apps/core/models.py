"""
core/models.py

Zentrales User-Modell mit Rollenverteilung und TOTP-2FA-Infrastruktur.
Außerdem: NotificationService-Schema nach Observer-Pattern.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import timedelta

from django.conf import settings
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
        verbose_name=_("TOTP eingerichtet"),
        help_text=_("Wird automatisch gesetzt sobald der User den QR-Code bestätigt hat."),
    )
    totp_required = models.BooleanField(
        default=True,
        verbose_name=_("2FA Pflicht"),
        help_text=_("Wenn aktiv, muss der User beim Login einen TOTP-Code eingeben. Nur vom Admin steuerbar."),
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

    # E-Mail-MFA
    email_mfa_enabled = models.BooleanField(
        default=False,
        verbose_name=_("E-Mail-MFA aktiviert"),
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
        return f"{self.get_full_name() or self.username} ({self.role})"

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

    @property
    def default_hourly_rate(self):
        """Gibt den admin-pflegbaren Standard-Stundensatz (netto) für diese Rolle zurück."""
        try:
            return RoleHourlyRate.objects.get(role=self.role).hourly_rate
        except RoleHourlyRate.DoesNotExist:
            return None

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


# ---------------------------------------------------------------------------
# Lookup — Admin-editierbare Auswahloptionen
# ---------------------------------------------------------------------------

class Lookup(models.Model):
    """
    Zentrale Tabelle für alle admin-editierbaren Auswahloptionen.
    Ermöglicht dem Admin das Pflegen von Kontaktrollen, Projekttypen etc.
    ohne Code-Änderungen.
    """
    class Category(models.TextChoices):
        CONTACT_ROLE = "contact_role", _("Kontaktrolle")
        PROJECT_TYPE = "project_type", _("Projekttyp")
        COMPANY      = "company",      _("Unternehmen")
        USER_ROLE    = "user_role",    _("Benutzerrolle")

    category = models.CharField(
        max_length=30,
        choices=Category.choices,
        verbose_name=_("Kategorie"),
    )
    label = models.CharField(
        max_length=100,
        verbose_name=_("Bezeichnung"),
        help_text=_("Angezeigter Text im Dropdown, z.B. 'Architekt'"),
    )
    value = models.CharField(
        max_length=50,
        verbose_name=_("Wert"),
        help_text=_("Interner Schlüssel, z.B. 'architect'. Kleinbuchstaben, keine Leerzeichen."),
    )
    order = models.PositiveSmallIntegerField(
        default=0,
        verbose_name=_("Reihenfolge"),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Aktiv"),
    )
    color = models.CharField(
        max_length=7,
        blank=True,
        verbose_name=_("Farbe (Hex)"),
        help_text=_("Optionale Markenfarbe, z.B. '#1B70BF'. Wird u.a. im Dashboard verwendet."),
    )

    class Meta:
        verbose_name        = _("Auswahloption")
        verbose_name_plural = _("Auswahloptionen")
        ordering            = ["category", "order", "label"]
        unique_together     = [("category", "value")]

    def __str__(self) -> str:
        return f"{self.get_category_display()} · {self.label}"

    @classmethod
    def choices_for(cls, category: str):
        """Gibt eine Liste von (value, label) Tuples für ein Formular-Feld zurück."""
        return list(
            cls.objects.filter(category=category, is_active=True)
            .order_by("order", "label")
            .values_list("value", "label")
        )

    @classmethod
    def entries_for(cls, category: str):
        """Gibt eine Liste von Dicts {value, label, color} zurück — z.B. für Dashboard-Tabs."""
        return list(
            cls.objects.filter(category=category, is_active=True)
            .order_by("order", "label")
            .values("value", "label", "color")
        )


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


# ---------------------------------------------------------------------------
# RoleHourlyRate — Admin-editierbare Standard-Stundensätze je Rolle
# ---------------------------------------------------------------------------

class EmailOTPCode(models.Model):
    """
    Einmaliger 6-stelliger Code für die E-Mail-basierte MFA.
    Gültig für 10 Minuten; wird nach Verwendung als used=True markiert.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="email_otp_codes",
        verbose_name=_("Benutzer"),
    )
    code = models.CharField(max_length=6, verbose_name=_("Code"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Erstellt am"))
    expires_at = models.DateTimeField(verbose_name=_("Läuft ab am"))
    used = models.BooleanField(default=False, verbose_name=_("Verwendet"))

    class Meta:
        verbose_name = _("E-Mail-OTP-Code")
        verbose_name_plural = _("E-Mail-OTP-Codes")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"OTP für {self.user.email} ({self.created_at:%Y-%m-%d %H:%M})"

    def is_valid(self) -> bool:
        return not self.used and timezone.now() < self.expires_at


class CompanyCredential(models.Model):
    """
    Speichert integrationsrelevante Zugangsdaten je Unternehmen (company-Lookup-Value).
    Derzeit: Lexoffice API-Key.  Wird über den Donna-Admin gepflegt.
    """
    company = models.CharField(
        max_length=50,
        unique=True,
        verbose_name=_("Unternehmen"),
        help_text=_("Interner Wert aus dem Lookup 'company', z.B. 'gt_immo'."),
    )
    lexoffice_api_key = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Lexoffice API-Key"),
        help_text=_("Persönlicher API-Schlüssel aus dem jeweiligen Lexoffice-Konto."),
    )

    class Meta:
        verbose_name = _("Firmen-Zugangsdaten")
        verbose_name_plural = _("Firmen-Zugangsdaten")
        ordering = ["company"]

    def __str__(self) -> str:
        configured = "✓" if self.lexoffice_api_key else "—"
        return f"{self.company} (Lexoffice {configured})"

    @classmethod
    def get_lexoffice_key(cls, company: str) -> str:
        """Gibt den Lexoffice API-Key für ein Unternehmen zurück, oder '' wenn nicht konfiguriert."""
        try:
            return cls.objects.get(company=company).lexoffice_api_key
        except cls.DoesNotExist:
            return ""


class RoleHourlyRate(models.Model):
    """
    Speichert den Standard-Netto-Stundensatz für eine User-Rolle.
    Wird beim Anlegen von ProjectMemberRates als Vorschlagswert genutzt.
    """
    role = models.CharField(
        max_length=30,
        choices=Role.choices,
        unique=True,
        verbose_name=_("Rolle"),
    )
    hourly_rate = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        verbose_name=_("Stundensatz (€ netto)"),
    )

    class Meta:
        verbose_name = _("Rollen-Stundensatz")
        verbose_name_plural = _("Rollen-Stundensätze")
        ordering = ["role"]

    def __str__(self) -> str:
        return f"{self.get_role_display()} — {self.hourly_rate} €/h"


# ---------------------------------------------------------------------------
# CompanySettings — Singleton für Firmen-Stammdaten
# ---------------------------------------------------------------------------

class CompanySettings(models.Model):
    """Singleton — always use CompanySettings.get() to access."""

    company_name    = models.CharField(max_length=255, default="", verbose_name="Firmenname")
    legal_form      = models.CharField(max_length=100, blank=True, verbose_name="Rechtsform")
    slogan          = models.CharField(max_length=255, blank=True, verbose_name="Slogan")
    logo            = models.ImageField(upload_to="company/", null=True, blank=True, verbose_name="Logo")
    street          = models.CharField(max_length=255, blank=True, verbose_name="Straße + Nr.")
    postal_code     = models.CharField(max_length=20, blank=True, verbose_name="PLZ")
    city            = models.CharField(max_length=100, blank=True, verbose_name="Stadt")
    country         = models.CharField(max_length=100, blank=True, default="Deutschland", verbose_name="Land")
    hrb_number      = models.CharField(max_length=100, blank=True, verbose_name="HRB-Nummer")
    vat_id          = models.CharField(max_length=50, blank=True, verbose_name="Umsatzsteuer-ID")
    tax_number      = models.CharField(max_length=50, blank=True, verbose_name="Steuernummer")
    bank_name       = models.CharField(max_length=255, blank=True, verbose_name="Bankname")
    iban            = models.CharField(max_length=34, blank=True, verbose_name="IBAN")
    bic             = models.CharField(max_length=11, blank=True, verbose_name="BIC")
    email           = models.EmailField(blank=True, verbose_name="E-Mail")
    phone           = models.CharField(max_length=50, blank=True, verbose_name="Telefon")
    website         = models.URLField(blank=True, verbose_name="Website")
    pdf_footer_text = models.TextField(blank=True, verbose_name="PDF-Fußzeile")
    payment_days    = models.PositiveSmallIntegerField(default=14, verbose_name="Zahlungsziel (Tage)")
    primary_color   = models.CharField(max_length=7, default="#1666b0", verbose_name="Primärfarbe (Hex)")
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Firmeneinstellungen"
        verbose_name_plural = "Firmeneinstellungen"

    def __str__(self):
        return self.company_name or "Firmeneinstellungen"

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
