"""
crm/models.py

Account- und Projekt-Management mit Lexoffice-Vorbereitung,
Storage-Path-Anbindung und Dokument-Pfad-Speicherung.
"""
from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


# ---------------------------------------------------------------------------
# Account (Kunden & interne Einheiten)
# ---------------------------------------------------------------------------

class Account(models.Model):
    """
    Repräsentiert einen Kunden oder eine interne Einheit (z.B. Abteilung).
    """
    class AccountType(models.TextChoices):
        CUSTOMER = "customer", _("Kunde")
        INTERNAL = "internal", _("Intern")
        PARTNER  = "partner",  _("Partner")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(max_length=255, verbose_name=_("Name"))
    account_type = models.CharField(
        max_length=20,
        choices=AccountType.choices,
        default=AccountType.CUSTOMER,
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

    # Lexoffice-Vorbereitung
    lexoffice_id = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Lexoffice-ID"),
        help_text=_("UUID des Kontakts in Lexoffice. Wird für API-Sync benötigt."),
    )

    # Interne Notizen
    notes = models.TextField(blank=True, verbose_name=_("Notizen"))

    # Account-Manager (Hauptverantwortlicher)
    account_manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="managed_accounts",
        verbose_name=_("Account-Manager"),
    )

    is_active = models.BooleanField(default=True, verbose_name=_("Aktiv"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Erstellt am"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Aktualisiert am"))

    class Meta:
        verbose_name = _("Account")
        verbose_name_plural = _("Accounts")
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_account_type_display()})"


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
        COMPLETED  = "completed",  _("Abgeschlossen")
        CANCELLED  = "cancelled",  _("Storniert")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(max_length=255, verbose_name=_("Projektname"))
    account = models.ForeignKey(
        Account,
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
        limit_choices_to={"role__in": ["project_manager", "admin"]},
        verbose_name=_("Projektleiter"),
    )
    team_members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="assigned_projects",
        verbose_name=_("Team-Mitglieder"),
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

    class Meta:
        verbose_name = _("Projekt")
        verbose_name_plural = _("Projekte")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} [{self.get_status_display()}]"

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

    # Primärer Pfad auf dem Netzlaufwerk / Azure Blob
    file_path = models.CharField(
        max_length=1024,
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
