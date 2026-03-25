"""
crm/models.py

Account- und Projekt-Management mit Lexoffice-Vorbereitung,
Storage-Path-Anbindung und Dokument-Pfad-Speicherung.
"""
from __future__ import annotations

import datetime
import uuid
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


# ---------------------------------------------------------------------------
# Soft-Delete Manager
# ---------------------------------------------------------------------------

class ActiveManager(models.Manager):
    """Excludes soft-deleted records from all default queries."""
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


# ---------------------------------------------------------------------------
# Account (Kunden & interne Einheiten)
# ---------------------------------------------------------------------------

class Account(models.Model):
    """
    Repräsentiert einen Kunden oder eine interne Einheit (z.B. Abteilung).
    """
    class AccountType(models.TextChoices):
        PRIVATE  = "private",  _("Privatperson")
        COMPANY  = "company",  _("Unternehmen")
        ESTATE   = "estate",   _("Erbengemeinschaft")
        INTERNAL = "internal", _("Intern")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    account_number = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        verbose_name=_("Kundennummer"),
        help_text=_("Wird automatisch vergeben, z.B. KD-00001"),
    )

    name = models.CharField(max_length=255, verbose_name=_("Name"))
    account_type = models.CharField(
        max_length=20,
        choices=AccountType.choices,
        default=AccountType.COMPANY,
        verbose_name=_("Typ"),
    )

    # Kontaktdaten
    email = models.EmailField(blank=True, verbose_name=_("E-Mail"))
    phone = models.CharField(max_length=50, blank=True, verbose_name=_("Telefon"))
    website = models.URLField(blank=True, verbose_name=_("Website"))

    # Adresse
    address_line1 = models.CharField(max_length=255, blank=True, verbose_name=_("Adresszeile 1"))
    address_line2 = models.CharField(max_length=255, blank=True, verbose_name=_("Adresszeile 2"))
    postal_code   = models.CharField(max_length=20, blank=True, verbose_name=_("PLZ"))
    city          = models.CharField(max_length=100, blank=True, verbose_name=_("Stadt"))
    country       = models.CharField(max_length=100, blank=True, default="Deutschland", verbose_name=_("Land"))

    # Rechnungsversand
    billing_email = models.EmailField(
        blank=True,
        verbose_name=_("Rechnungs-E-Mail"),
        help_text=_("Empfängeradresse für den automatischen Rechnungsversand"),
    )

    # Lexoffice-Vorbereitung
    lexoffice_id = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Lexoffice-ID"),
        help_text=_("UUID des Kontakts in Lexoffice. Wird für API-Sync benötigt."),
    )

    # Interne Notizen
    notes = models.TextField(blank=True, verbose_name=_("Notizen"))

    # Account-Manager (Hauptverantwortlicher intern)
    account_manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="managed_accounts",
        verbose_name=_("Kundenbetreuer"),
    )

    # Primärer externer Ansprechpartner (Kontakt-Objekt)
    primary_contact = models.ForeignKey(
        "Contact",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="primary_for_accounts",
        verbose_name=_("Ansprechpartner"),
    )

    is_active = models.BooleanField(default=True, verbose_name=_("Aktiv"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Erstellt am"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Aktualisiert am"))
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Gelöscht am"))

    objects     = ActiveManager()
    all_objects = models.Manager()  # includes deleted, for admin/numbering

    class Meta:
        verbose_name = _("Account")
        verbose_name_plural = _("Accounts")
        ordering = ["name"]

    def delete(self, keep_projects=False, *args, **kwargs):
        """Soft-delete. With keep_projects=True the projects are detached (account=None) instead of deleted."""
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at"])
        if keep_projects:
            self.projects.all().update(account=None)
        else:
            for project in self.projects.all():
                project.delete()

    def save(self, *args, **kwargs):
        if not self.account_number:
            from django.db import transaction
            with transaction.atomic():
                last = (
                    Account.all_objects
                    .select_for_update()
                    .filter(account_number__regex=r"^KD-\d+$")
                    .order_by("-account_number")
                    .values_list("account_number", flat=True)
                    .first()
                )
                num = (int(last.split("-")[1]) + 1) if last else 1
                self.account_number = f"KD-{num:05d}"
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.account_number} · {self.name}"


# ---------------------------------------------------------------------------
# ProjectType — Standalone Projekttyp-Modell
# ---------------------------------------------------------------------------

class ProjectType(models.Model):
    name        = models.CharField(max_length=100, unique=True, verbose_name=_("Name"))
    description = models.CharField(max_length=255, blank=True, verbose_name=_("Beschreibung"))
    color       = models.CharField(max_length=7, default="#2F6FB3", verbose_name=_("Farbe"))
    order       = models.PositiveSmallIntegerField(default=0, verbose_name=_("Reihenfolge"))
    is_active   = models.BooleanField(default=True, verbose_name=_("Aktiv"))

    class Meta:
        ordering            = ["order", "name"]
        verbose_name        = _("Projekttyp")
        verbose_name_plural = _("Projekttypen")

    def __str__(self) -> str:
        return self.name


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------

class Project(models.Model):
    """
    Projekt, verknüpft mit einem Account.

    Enthält:
    - Status-Tracking
    - Team-Zuweisung
    - Budget-Verwaltung
    - storage_path für Laufwerk-Integration
    - lexoffice_id für spätere Rechnungs-Synchronisation
    """
    class Status(models.TextChoices):
        LEAD       = "lead",       _("Lead")
        OFFER_SENT = "offer_sent", _("Angebot versendet")
        ACTIVE     = "active",     _("Aktiv")
        ON_HOLD    = "on_hold",    _("Pausiert")
        INVOICED    = "invoiced",    _("Rechnung")
        COMPLETED   = "completed",  _("Abgeschlossen")
        CANCELLED   = "cancelled",  _("Storniert")
        OFFER_LOST  = "offer_lost", _("Angebot nicht beauftragt")

    # Status-Gruppen für Archivierung
    ARCHIVED_STATUSES = {Status.COMPLETED, Status.CANCELLED, Status.OFFER_LOST}

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    project_number = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        verbose_name=_("Projektnummer"),
        help_text=_("Wird automatisch vergeben, z.B. PRJ-00001"),
    )

    name = models.CharField(max_length=255, verbose_name=_("Projektname"))
    project_type = models.ForeignKey(
        "ProjectType",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="projects",
        verbose_name=_("Projekttyp"),
    )
    account = models.ForeignKey(
        Account,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="projects",
        verbose_name=_("Account"),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.LEAD,
        verbose_name=_("Status"),
    )
    description = models.TextField(blank=True, verbose_name=_("Beschreibung"))

    # Team-Zuweisung
    team_lead = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="led_projects",
        verbose_name=_("Projektleiter"),
    )
    team_members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="assigned_projects",
        verbose_name=_("Team-Mitglieder"),
    )

    predecessor_projects = models.ManyToManyField(
        "self",
        blank=True,
        symmetrical=False,
        related_name="successor_projects",
        verbose_name=_("Vorgängerprojekte"),
    )

    # Zeitraum
    start_date = models.DateField(null=True, blank=True, verbose_name=_("Startdatum"))
    end_date   = models.DateField(null=True, blank=True, verbose_name=_("Enddatum"))

    # Budget in EUR (Cent-genau)
    budget_hours   = models.DecimalField(
        max_digits=8, decimal_places=2,
        null=True, blank=True,
        verbose_name=_("Budget (Stunden)"),
    )
    budget_amount  = models.DecimalField(
        max_digits=12, decimal_places=2,
        null=True, blank=True,
        verbose_name=_("Budget (€)"),
    )
    hourly_rate    = models.DecimalField(
        max_digits=8, decimal_places=2,
        null=True, blank=True,
        verbose_name=_("Stundensatz (€)"),
    )

    # -----------------------------------------------------------------------
    # Verkaufsprojekt – Maklerprovisionsfelder
    # -----------------------------------------------------------------------
    purchase_price = models.DecimalField(
        max_digits=14, decimal_places=2,
        null=True, blank=True,
        verbose_name=_("Not. Kaufpreis (€)"),
        help_text=_("Notarieller Kaufpreis in EUR (Basis für Provisionsberechnung)."),
    )
    commission_inner = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True,
        verbose_name=_("Innenprovision (% netto)"),
    )
    commission_outer = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True,
        verbose_name=_("Außenprovision (% netto)"),
    )

    # -----------------------------------------------------------------------
    # Laufwerk-Integration
    # -----------------------------------------------------------------------
    storage_path = models.CharField(
        max_length=1024,
        blank=True,
        verbose_name=_("Speicherpfad"),
        help_text=_(
            "Absoluter oder relativer Pfad zum Projektordner auf dem Netzlaufwerk "
            "bzw. Azure Blob Storage Container-Pfad. "
            "Beispiele: '\\\\srv01\\projekte\\2024\\Kunde-X' oder "
            "'projects/2024/kunde-x' (Azure Blob)."
        ),
    )

    # -----------------------------------------------------------------------
    # Lexoffice-Vorbereitung
    # -----------------------------------------------------------------------
    lexoffice_id = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Lexoffice-ID"),
        help_text=_("UUID des zugehörigen Projekts / Vorgangs in Lexoffice."),
    )

    # Interne Projektnummer (optional für eigene Nummernsystematik)
    internal_reference = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Interne Referenz"),
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="created_projects",
        verbose_name=_("Erstellt von"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Erstellt am"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Aktualisiert am"))
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Gelöscht am"))

    objects     = ActiveManager()
    all_objects = models.Manager()  # includes deleted, for admin/numbering

    class Meta:
        verbose_name = _("Projekt")
        verbose_name_plural = _("Projekte")
        ordering = ["-created_at"]

    def delete(self, *args, **kwargs):
        """Soft-delete: marks as deleted and cascades to offers + invoices."""
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at"])
        self.offers.filter(status__in=["draft", "sent"]).update(deleted_at=timezone.now())
        self.invoices.filter(status__in=["draft", "sent"]).update(deleted_at=timezone.now())

    def save(self, *args, **kwargs):
        if not self.project_number:
            from django.db import transaction
            with transaction.atomic():
                last = (
                    Project.all_objects
                    .select_for_update()
                    .filter(project_number__regex=r"^PRJ-\d+$")
                    .order_by("-project_number")
                    .values_list("project_number", flat=True)
                    .first()
                )
                num = (int(last.split("-")[1]) + 1) if last else 1
                self.project_number = f"PRJ-{num:05d}"
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.project_number} · {self.name}"

    def get_logged_hours(self) -> float:
        """Gibt die Summe aller genehmigten Stunden zurück."""
        from worktrack.models import TimeEntry
        result = self.time_entries.filter(
            status=TimeEntry.Status.APPROVED
        ).aggregate(total=models.Sum("duration_hours"))
        return float(result["total"] or 0)

    def is_over_budget(self) -> bool:
        if self.budget_hours is None:
            return False
        return self.get_logged_hours() > float(self.budget_hours)


# ---------------------------------------------------------------------------
# RevenueTarget — Admin-pflegbares Umsatzziel pro Unternehmen & Jahr
# ---------------------------------------------------------------------------

class RevenueTarget(models.Model):
    """Jahresziel (Umsatz) pro Jahr."""

    year = models.IntegerField(unique=True, verbose_name=_("Jahr"))
    target_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name=_("Jahresziel (€ netto)"),
    )

    class Meta:
        verbose_name        = _("Umsatzziel")
        verbose_name_plural = _("Umsatzziele")
        ordering            = ["-year"]

    def __str__(self) -> str:
        return f"Umsatzziel {self.year}: {self.target_amount:,.0f} €"


# ---------------------------------------------------------------------------
# ProjectMemberRate — Stundensatz je Teammitglied
# ---------------------------------------------------------------------------

class ProjectMemberRate(models.Model):
    """
    Speichert den projektspezifischen Stundensatz (netto) eines Teammitglieds.
    Wird beim Anlegen/Bearbeiten eines Projekts gesetzt und kann vom
    rollenbasierten Standardsatz abweichen.
    """
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="member_rates",
        verbose_name=_("Projekt"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="project_rates",
        verbose_name=_("Mitarbeiter"),
    )
    hourly_rate = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        verbose_name=_("Stundensatz (€ netto)"),
    )

    class Meta:
        unique_together = [("project", "user")]
        verbose_name = _("Projektmitglied-Stundensatz")
        verbose_name_plural = _("Projektmitglied-Stundensätze")
        ordering = ["user__last_name", "user__first_name"]

    def __str__(self) -> str:
        return f"{self.user} @ {self.project}: {self.hourly_rate} €/h"


# ---------------------------------------------------------------------------
# ProjectBudgetExtension — Nachträgliche Budget-Freigaben durch den Kunden
# ---------------------------------------------------------------------------

class ProjectBudgetExtension(models.Model):
    """
    Protokolliert eine Budgeterweiterung, die der Kunde nachträglich freigegeben hat.
    Das Gesamtbudget ergibt sich aus project.budget_amount + Summe aller Erweiterungen.
    """
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="budget_extensions",
        verbose_name=_("Projekt"),
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_("Betrag (€ netto)"),
    )
    approved_at = models.DateField(verbose_name=_("Freigabedatum"))
    note = models.TextField(blank=True, verbose_name=_("Anmerkung"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Budget-Erweiterung")
        verbose_name_plural = _("Budget-Erweiterungen")
        ordering = ["approved_at"]

    def __str__(self) -> str:
        return f"{self.project} +{self.amount} € ({self.approved_at})"


# ---------------------------------------------------------------------------
# Contact — Projektkontakte (Käufer, Architekten, Notare, …)
# ---------------------------------------------------------------------------

class Contact(models.Model):
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    first_name = models.CharField(max_length=100, verbose_name=_("Vorname"))
    last_name  = models.CharField(max_length=100, verbose_name=_("Nachname"))
    company_name = models.CharField(max_length=255, blank=True, verbose_name=_("Firma"))

    email  = models.EmailField(blank=True, verbose_name=_("E-Mail"))
    phone  = models.CharField(max_length=50, blank=True, verbose_name=_("Telefon"))
    mobile = models.CharField(max_length=50, blank=True, verbose_name=_("Mobil"))

    address_line1 = models.CharField(max_length=255, blank=True, verbose_name=_("Straße / Nr."))
    postal_code   = models.CharField(max_length=20,  blank=True, verbose_name=_("PLZ"))
    city          = models.CharField(max_length=100, blank=True, verbose_name=_("Stadt"))
    country       = models.CharField(max_length=100, blank=True, default="Deutschland", verbose_name=_("Land"))

    notes = models.TextField(blank=True, verbose_name=_("Notizen"))

    projects = models.ManyToManyField(
        "Project", blank=True, related_name="contacts", verbose_name=_("Projekte")
    )
    accounts = models.ManyToManyField(
        "Account", blank=True, related_name="contacts", verbose_name=_("Accounts")
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = _("Kontakt")
        verbose_name_plural = _("Kontakte")
        ordering            = ["last_name", "first_name"]

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def get_full_name(self) -> str:
        return str(self)


# ---------------------------------------------------------------------------
# Document — Pfad-Speicherung für Angebote und Rechnungen
# ---------------------------------------------------------------------------

class Document(models.Model):
    """
    Verknüpft ein physisches Dokument (Angebot, Rechnung, Vertrag …)
    mit einem Projekt. Speichert den Dateipfad als zentralen Verweis,
    damit Donna als Dashboard fungiert.

    Kein Datei-Upload in die DB — nur der Pfad, da wir eine
    Laufwerk-/Azure-Blob-Lösung nutzen.
    """
    class DocumentType(models.TextChoices):
        OFFER        = "offer",        _("Angebot")
        COMMISSION   = "commission",   _("Beauftragung")
        INVOICE      = "invoice",      _("Rechnung")
        CONTRACT     = "contract",     _("Vertrag")
        DELIVERY     = "delivery",     _("Lieferschein")
        MISC         = "misc",         _("Sonstiges")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="documents",
        verbose_name=_("Projekt"),
    )
    document_type = models.CharField(
        max_length=20,
        choices=DocumentType.choices,
        verbose_name=_("Dokumententyp"),
    )
    title = models.CharField(max_length=255, verbose_name=_("Titel"))

    # Hochgeladene Datei (PDF-Upload)
    file = models.FileField(
        upload_to="project_documents/",
        null=True,
        blank=True,
        verbose_name=_("Datei"),
    )

    # Primärer Pfad auf dem Netzlaufwerk / Azure Blob
    file_path = models.CharField(
        max_length=1024,
        blank=True,
        verbose_name=_("Dateipfad"),
        help_text=_(
            "Vollständiger Pfad zur Datei auf dem Netzlaufwerk oder "
            "Azure Blob Storage Key. "
            "Beispiel: '\\\\srv01\\projekte\\2024\\KundeX\\Angebot_001.pdf'"
        ),
    )

    # Lexoffice-Referenz (z.B. Rechnungs-ID aus Lexoffice)
    lexoffice_id = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Lexoffice-ID"),
        help_text=_("ID des Belegs in Lexoffice (bei Rechnungen und Angeboten)."),
    )
    lexoffice_document_number = models.CharField(
        max_length=50,
        blank=True,
        verbose_name=_("Belegnummer (Lexoffice)"),
        help_text=_("Lesbare Belegnummer aus Lexoffice, z.B. 'RE-2024-0042'."),
    )

    # Finanzielle Kennzahlen (aus Lexoffice übernommen)
    net_amount   = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name=_("Nettobetrag (€)"))
    gross_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name=_("Bruttobetrag (€)"))

    document_date = models.DateField(null=True, blank=True, verbose_name=_("Belegdatum"))
    due_date      = models.DateField(null=True, blank=True, verbose_name=_("Fälligkeitsdatum"))

    notes = models.TextField(blank=True, verbose_name=_("Notizen"))

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="uploaded_documents",
        verbose_name=_("Eingetragen von"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Erstellt am"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Aktualisiert am"))

    class Meta:
        verbose_name = _("Dokument")
        verbose_name_plural = _("Dokumente")
        ordering = ["-document_date", "-created_at"]

    def __str__(self) -> str:
        return f"{self.get_document_type_display()} – {self.title} ({self.project})"


# ---------------------------------------------------------------------------
# ProjectActivity — Aktivitäten-Timeline pro Projekt
# ---------------------------------------------------------------------------

class ProjectActivity(models.Model):
    class ActivityType(models.TextChoices):
        CALL     = "call",     _("Telefonat")
        MEETING  = "meeting",  _("Meeting")
        EMAIL    = "email",    _("E-Mail-Verweis")
        NOTE     = "note",     _("Notiz")
        DOCUMENT = "document", _("Dokument")

    id            = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project       = models.ForeignKey("Project", on_delete=models.CASCADE, related_name="activities")
    activity_type = models.CharField(max_length=20, choices=ActivityType.choices)
    title         = models.CharField(max_length=255, verbose_name=_("Titel"))
    body          = models.TextField(blank=True, verbose_name=_("Inhalt"))
    attachment    = models.FileField(upload_to="activity_attachments/", null=True, blank=True, verbose_name=_("Dateianhang"))
    occurred_at   = models.DateTimeField(default=timezone.now, verbose_name=_("Datum / Uhrzeit"))
    created_by    = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_activities",
        verbose_name=_("Erstellt von"),
    )
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at"]
        verbose_name = _("Projektaktivität")
        verbose_name_plural = _("Projektaktivitäten")

    def __str__(self) -> str:
        return f"{self.get_activity_type_display()} — {self.title}"


# ---------------------------------------------------------------------------
# Offer + OfferItem — PDF-Angebote
# ---------------------------------------------------------------------------

class Offer(models.Model):
    class Status(models.TextChoices):
        DRAFT    = "draft",    "Entwurf"
        SENT     = "sent",     "Versendet"
        ACCEPTED = "accepted", "Beauftragt"
        REJECTED = "rejected", "Abgelehnt"

    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    offer_number = models.CharField(max_length=20, unique=True, blank=True)
    project      = models.ForeignKey(
        "Project",
        on_delete=models.PROTECT,
        related_name="offers",
        null=True,
        blank=True,
        verbose_name=_("Projekt"),
    )
    recipient_account = models.ForeignKey(
        "Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="received_offers",
        verbose_name=_("Empfänger-Account"),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name=_("Status"),
    )
    title        = models.CharField(max_length=255, verbose_name=_("Titel"))
    intro_text     = models.TextField(blank=True, verbose_name=_("Einleitungstext"))
    closing_text   = models.TextField(blank=True, verbose_name=_("Nachbemerkung"))
    payment_terms  = models.TextField(blank=True, verbose_name=_("Zahlungsbedingung"))
    tax_rate     = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("19.00"),
        verbose_name=_("Umsatzsteuer (%)"),
    )
    valid_until  = models.DateField(null=True, blank=True, verbose_name=_("Gültig bis"))
    offer_date   = models.DateField(default=datetime.date.today, verbose_name=_("Angebotsdatum"))

    recipient_name    = models.CharField(max_length=255, blank=True, verbose_name=_("Empfänger Name"))
    recipient_email   = models.EmailField(blank=True, verbose_name=_("Empfänger E-Mail"))
    recipient_address = models.TextField(blank=True, verbose_name=_("Empfänger Adresse"))
    discount_percent  = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0"),
        verbose_name=_("Gesamtrabatt (%)"),
    )
    discount_amount_eur = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        verbose_name=_("Gesamtrabatt (€)"),
    )
    is_kleinunternehmer = models.BooleanField(
        default=False,
        verbose_name=_("Kleinunternehmer (§19 UStG)"),
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_offers",
        verbose_name=_("Erstellt von"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_order_confirmation      = models.BooleanField(default=False)
    include_agb                = models.BooleanField(default=True,  verbose_name=_("AGB anhängen"))
    include_widerrufsbelehrung = models.BooleanField(default=False,  verbose_name=_("Widerrufsbelehrung anhängen"))
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Gelöscht am"))

    # Beauftragung
    commission_token = models.UUIDField(
        default=uuid.uuid4, unique=True, editable=False,
        verbose_name=_("Bestätigungs-Token"),
    )
    commissioned_at = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Beauftragt am"),
    )
    commissioned_method = models.CharField(
        max_length=20,
        choices=[("click", "Online-Bestätigung"), ("signature", "Unterschrift-Upload")],
        blank=True,
        verbose_name=_("Beauftragungsmethode"),
    )
    commissioned_by_ip = models.GenericIPAddressField(
        null=True, blank=True, verbose_name=_("IP-Adresse"),
    )
    commissioned_by_user_agent = models.TextField(
        blank=True, verbose_name=_("Browser-Info"),
    )
    commissioned_signature_pdf = models.FileField(
        upload_to="commissions/", null=True, blank=True,
        verbose_name=_("Unterschriebenes Angebot (PDF)"),
    )

    objects     = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        ordering        = ["-offer_date", "-created_at"]
        verbose_name    = "Angebot"
        verbose_name_plural = "Angebote"

    def save(self, *args, **kwargs):
        if not self.offer_number:
            from django.db import transaction
            with transaction.atomic():
                last = (
                    Offer.all_objects
                    .select_for_update()
                    .filter(offer_number__regex=r"^A-\d+$")
                    .order_by("-offer_number")
                    .values_list("offer_number", flat=True)
                    .first()
                )
                num = (int(last.split("-")[1]) + 1) if last else 1
                self.offer_number = f"A-{num:05d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.offer_number} — {self.title}"

    @property
    def net_total(self):
        subtotal = sum((item.net_amount for item in self.items.all()), Decimal("0.00"))
        return (subtotal - self.discount_amount).quantize(Decimal("0.01"))

    @property
    def discount_amount(self):
        subtotal = sum((item.net_amount for item in self.items.all()), Decimal("0.00"))
        if self.discount_amount_eur:
            return min(self.discount_amount_eur, subtotal).quantize(Decimal("0.01"))
        if self.discount_percent:
            return (subtotal * self.discount_percent / Decimal("100")).quantize(Decimal("0.01"))
        return Decimal("0.00")

    @property
    def tax_amount(self):
        if self.is_kleinunternehmer:
            return Decimal("0.00")
        return (self.net_total * self.tax_rate / Decimal("100")).quantize(Decimal("0.01"))

    @property
    def gross_total(self):
        return self.net_total + self.tax_amount

    @property
    def display_number(self):
        """AB-00001 für Auftragsbestätigungen, sonst offer_number."""
        if self.is_order_confirmation and self.offer_number.startswith("A-"):
            return "AB-" + self.offer_number[2:]
        return self.offer_number


class OfferItem(models.Model):
    class ItemType(models.TextChoices):
        NORMAL   = "normal",   _("Standard")
        OPTIONAL = "optional", _("Optional")
        TEXT     = "text",     _("Freitext")

    offer       = models.ForeignKey(
        Offer,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("Angebot"),
    )
    position    = models.PositiveSmallIntegerField(default=1, verbose_name=_("Position"))
    item_type   = models.CharField(
        max_length=10, choices=ItemType.choices, default=ItemType.NORMAL,
        verbose_name=_("Typ"),
    )
    title       = models.CharField(max_length=255, blank=True, default="", verbose_name=_("Titel"))
    description = models.TextField(blank=True, default="", verbose_name=_("Beschreibung"))
    quantity    = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("1"),
        verbose_name=_("Menge"),
    )
    unit       = models.CharField(
        max_length=50, blank=True, default="",
        verbose_name=_("Einheit"),
    )
    unit_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0"),
        verbose_name=_("Einzelpreis (€ netto)"),
    )
    discount_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0"),
        verbose_name=_("Rabatt (%)"),
    )

    class Meta:
        ordering     = ["position"]
        verbose_name = _("Angebotsposition")
        verbose_name_plural = _("Angebotspositionen")

    @property
    def net_amount(self):
        if self.item_type in (self.ItemType.OPTIONAL, self.ItemType.TEXT):
            return Decimal("0.00")
        amount = (self.quantity * self.unit_price).quantize(Decimal("0.01"))
        if self.discount_percent:
            amount = amount * (1 - self.discount_percent / Decimal("100"))
        return amount.quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# Invoice + InvoiceItem — Rechnungen
# ---------------------------------------------------------------------------

class Invoice(models.Model):
    class InvoiceType(models.TextChoices):
        STANDARD = "standard", "Standardrechnung"
        PARTIAL  = "partial",  "Abschlagsrechnung"
        FINAL    = "final",    "Schlussrechnung"

    class Status(models.TextChoices):
        DRAFT     = "draft",     "Entwurf"
        SENT      = "sent",      "Versendet"
        PAID      = "paid",      "Bezahlt"
        CANCELLED = "cancelled", "Storniert"

    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice_number = models.CharField(max_length=20, unique=True, blank=True)
    project        = models.ForeignKey("Project", on_delete=models.PROTECT, related_name="invoices", null=True, blank=True)
    offer          = models.ForeignKey("Offer", null=True, blank=True, on_delete=models.SET_NULL, related_name="invoices")
    invoice_type   = models.CharField(max_length=20, choices=InvoiceType.choices, default=InvoiceType.STANDARD)
    status         = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    invoice_date   = models.DateField(default=date.today)
    due_date       = models.DateField(null=True, blank=True)
    payment_date   = models.DateField(null=True, blank=True)
    title          = models.CharField(max_length=255)
    intro_text     = models.TextField(blank=True)
    closing_text   = models.TextField(blank=True)
    payment_info   = models.TextField(blank=True, help_text="IBAN, BIC, Verwendungszweck")
    tax_rate       = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("19.00"))
    recipient_name    = models.CharField(max_length=255, blank=True)
    recipient_email   = models.EmailField(blank=True)
    recipient_address = models.TextField(blank=True)
    discount_percent    = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    discount_amount_eur = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    is_kleinunternehmer = models.BooleanField(default=False)
    net_total_cached  = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    created_by     = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="created_invoices")
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)
    deleted_at     = models.DateTimeField(null=True, blank=True, verbose_name=_("Gelöscht am"))

    objects     = ActiveManager()
    all_objects = models.Manager()

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            with transaction.atomic():
                last = Invoice.all_objects.select_for_update().filter(
                    invoice_number__regex=r"^R-\d+$"
                ).order_by("-invoice_number").first()
                if last:
                    num = int(last.invoice_number.split("-")[1]) + 1
                else:
                    num = 1
                self.invoice_number = f"R-{num:05d}"
        if not self.due_date and self.invoice_date:
            from datetime import timedelta
            self.due_date = self.invoice_date + timedelta(days=14)
        super().save(*args, **kwargs)

    @property
    def net_total(self):
        subtotal = sum((item.net_amount for item in self.items.all()), Decimal("0.00"))
        return (subtotal - self.discount_amount).quantize(Decimal("0.01"))

    @property
    def discount_amount(self):
        subtotal = sum((item.net_amount for item in self.items.all()), Decimal("0.00"))
        if self.discount_amount_eur:
            return min(self.discount_amount_eur, subtotal).quantize(Decimal("0.01"))
        if self.discount_percent:
            return (subtotal * self.discount_percent / Decimal("100")).quantize(Decimal("0.01"))
        return Decimal("0.00")

    @property
    def tax_amount(self):
        if self.is_kleinunternehmer:
            return Decimal("0.00")
        return (self.net_total * self.tax_rate / Decimal("100")).quantize(Decimal("0.01"))

    @property
    def gross_total(self):
        return self.net_total + self.tax_amount

    @property
    def is_overdue(self):
        from datetime import date as date_today
        return (
            self.status not in {self.Status.PAID, self.Status.CANCELLED}
            and self.due_date is not None
            and self.due_date < date_today.today()
        )

    def __str__(self):
        return f"{self.invoice_number} – {self.title}"

    class Meta:
        ordering = ["-invoice_date", "-created_at"]
        verbose_name = "Rechnung"
        verbose_name_plural = "Rechnungen"


class InvoiceItem(models.Model):
    class ItemType(models.TextChoices):
        NORMAL   = "normal",   "Standard"
        OPTIONAL = "optional", "Optional"
        TEXT     = "text",     "Freitext"

    invoice          = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="items")
    position         = models.PositiveSmallIntegerField(default=1)
    item_type        = models.CharField(max_length=10, choices=ItemType.choices, default=ItemType.NORMAL)
    title            = models.CharField(max_length=255, blank=True, default="")
    description      = models.TextField(blank=True, default="")
    quantity         = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("1"))
    unit             = models.CharField(max_length=50, blank=True, default="")
    unit_price       = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))

    @property
    def net_amount(self):
        if self.item_type in (self.ItemType.OPTIONAL, self.ItemType.TEXT):
            return Decimal("0.00")
        amount = (self.quantity * self.unit_price).quantize(Decimal("0.01"))
        if self.discount_percent:
            amount = amount * (1 - self.discount_percent / Decimal("100"))
        return amount.quantize(Decimal("0.01"))

    class Meta:
        ordering = ["position"]
        verbose_name = "Rechnungsposition"
        verbose_name_plural = "Rechnungspositionen"


# ---------------------------------------------------------------------------
# ProductCatalog — Standard-Produkte und Dienstleistungen
# ---------------------------------------------------------------------------

class ProductCatalog(models.Model):
    """Standard products/services for quick-add in offers and invoices."""
    name        = models.CharField(max_length=255, verbose_name="Bezeichnung")
    description = models.TextField(blank=True, verbose_name="Beschreibung")
    unit        = models.CharField(max_length=50, default="pauschal", verbose_name="Einheit")
    quantity    = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("1"), verbose_name="Menge")
    unit_price  = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Einzelpreis (Netto)")
    category    = models.CharField(max_length=100, blank=True, verbose_name="Kategorie")
    is_active   = models.BooleanField(default=True, verbose_name="Aktiv")
    sort_order  = models.PositiveSmallIntegerField(default=0, verbose_name="Reihenfolge")
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Produkt / Dienstleistung"
        verbose_name_plural = "Produktkatalog"

    def __str__(self):
        return self.name

    @property
    def net_amount(self):
        return (self.quantity * self.unit_price).quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# TextBlock — Wiederverwendbare Textbausteine für Angebote/Rechnungen
# ---------------------------------------------------------------------------

class TextBlock(models.Model):
    class Category(models.TextChoices):
        INTRO   = "intro",   _("Einleitungstext")
        CLOSING = "closing", _("Nachbemerkung")
        PAYMENT = "payment", _("Zahlungsbedingung")
        OTHER   = "other",   _("Sonstiges")

    class Scope(models.TextChoices):
        BOTH    = "both",    _("Angebote & Rechnungen")
        OFFER   = "offer",   _("Nur Angebote")
        INVOICE = "invoice", _("Nur Rechnungen")

    name       = models.CharField(max_length=100, verbose_name=_("Name"))
    category   = models.CharField(max_length=20, choices=Category.choices, verbose_name=_("Kategorie"))
    scope      = models.CharField(max_length=10, choices=Scope.choices, default="both", verbose_name=_("Gilt für"))
    content    = models.TextField(verbose_name=_("Inhalt"))
    is_default = models.BooleanField(default=False, verbose_name=_("Standard"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["category", "name"]
        verbose_name = _("Textbaustein")
        verbose_name_plural = _("Textbausteine")

    def __str__(self):
        return f"{self.get_category_display()} — {self.name}"


class Unit(models.Model):
    name       = models.CharField(max_length=50, unique=True, verbose_name=_("Einheit"))
    sort_order = models.PositiveSmallIntegerField(default=0, verbose_name=_("Reihenfolge"))

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = _("Einheit")
        verbose_name_plural = _("Einheiten")

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# LeadInquiry — Kontaktdaten-Anfrage für Quick-Lead-Projekte
# ---------------------------------------------------------------------------

class LeadInquiry(models.Model):
    class Status(models.TextChoices):
        PENDING   = "pending",   "Ausstehend"
        SUBMITTED = "submitted", "Eingereicht"
        IMPORTED  = "imported",  "Übernommen"

    class CustomerType(models.TextChoices):
        PRIVATE = "private", "Privatperson"
        COMPANY = "company", "Unternehmen"

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    token       = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    project     = models.OneToOneField("Project", on_delete=models.CASCADE, related_name="lead_inquiry")
    status      = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    # Customer-provided data (filled via public form)
    customer_type   = models.CharField(max_length=10, choices=CustomerType.choices, default=CustomerType.PRIVATE, verbose_name="Kundentyp")
    first_name      = models.CharField(max_length=100, blank=True, verbose_name="Vorname")
    last_name       = models.CharField(max_length=100, blank=True, verbose_name="Nachname")
    company_name    = models.CharField(max_length=255, blank=True, verbose_name="Firma")
    email           = models.EmailField(blank=True, verbose_name="E-Mail")
    phone           = models.CharField(max_length=50, blank=True, verbose_name="Telefon")
    street          = models.CharField(max_length=255, blank=True, verbose_name="Straße + Nr.")
    postal_code     = models.CharField(max_length=20, blank=True, verbose_name="PLZ")
    city            = models.CharField(max_length=100, blank=True, verbose_name="Stadt")
    request_description = models.TextField(blank=True, verbose_name="Beschreibung des Anliegens")
    invoice_email   = models.EmailField(blank=True, verbose_name="Rechnungs-E-Mail")

    sent_at         = models.DateTimeField(null=True, blank=True)
    submitted_at    = models.DateTimeField(null=True, blank=True)
    expires_at      = models.DateTimeField(null=True, blank=True)
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Lead-Anfrage"
        verbose_name_plural = "Lead-Anfragen"

    def __str__(self):
        return f"Anfrage für {self.project.name}"

    @property
    def is_expired(self):
        from django.utils import timezone
        return self.expires_at and timezone.now() > self.expires_at

    @property
    def customer_full_name(self):
        parts = [self.first_name, self.last_name]
        return " ".join(p for p in parts if p) or self.company_name or "—"
