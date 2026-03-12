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
        verbose_name=_("Account-Manager"),
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

    class Meta:
        verbose_name = _("Account")
        verbose_name_plural = _("Accounts")
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.account_number:
            from django.db import transaction
            with transaction.atomic():
                last = (
                    Account.objects
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
    class Company(models.TextChoices):
        DIRESO     = "direso",     _("DIRESO")
        GT_IMMO    = "gt_immo",    _("GT Immo")
        GT_PROJEKT = "gt_projekt", _("GT Projekt")

    class ProjectType(models.TextChoices):
        CONSULTING          = "consulting",          _("Beratung")
        DEVELOPER           = "developer",           _("Erschließungsträger")
        APPRAISAL           = "appraisal",           _("Gutachten")
        PLATFORM            = "platform",            _("Plattform")
        PROJECT_MANAGEMENT  = "project_management",  _("Projektmanagement")
        SCAN                = "scan",                _("Scan")
        SALE                = "sale",                _("Verkauf")
        RENTAL              = "rental",              _("Vermietung")

    # Welche Projekttypen sind je Firma erlaubt (alphabetisch nach Label)
    PROJECT_TYPES_BY_COMPANY = {
        Company.DIRESO:     ["platform", "scan"],
        Company.GT_IMMO:    ["consulting", "appraisal", "project_management", "sale", "rental"],
        Company.GT_PROJEKT: ["consulting", "developer", "project_management"],
    }

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

    company = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name=_("Unternehmen"),
    )

    project_number = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        verbose_name=_("Projektnummer"),
        help_text=_("Wird automatisch vergeben, z.B. PRJ-00001"),
    )

    name = models.CharField(max_length=255, verbose_name=_("Projektname"))
    project_type = models.CharField(
        max_length=20,
        default=ProjectType.CONSULTING,
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
        limit_choices_to={"role__in": ["project_manager", "admin"]},
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

    class Meta:
        verbose_name = _("Projekt")
        verbose_name_plural = _("Projekte")
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.project_number:
            from django.db import transaction
            with transaction.atomic():
                last = (
                    Project.objects
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
    """Jahresziel für ein bestimmtes internes Unternehmen (z.B. 'gt_immo')."""

    company = models.CharField(
        max_length=50,
        verbose_name=_("Unternehmen"),
        help_text=_("Interner Wert, z.B. 'gt_immo'."),
    )
    year = models.IntegerField(verbose_name=_("Jahr"))
    target_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name=_("Jahresziel (€ netto)"),
    )

    class Meta:
        unique_together     = [("company", "year")]
        verbose_name        = _("Umsatzziel")
        verbose_name_plural = _("Umsatzziele")
        ordering            = ["-year", "company"]

    def __str__(self) -> str:
        return f"Umsatzziel {self.company} {self.year}: {self.target_amount:,.0f} €"


# ---------------------------------------------------------------------------
# CompanyProjectTypeMapping — Admin-editierbare Projekttyp-Zuweisungen
# ---------------------------------------------------------------------------

class CompanyProjectTypeMapping(models.Model):
    """
    Steuert, welche Projekttypen für ein bestimmtes Unternehmen auswählbar sind.
    Ersetzt das hardcodierte PROJECT_TYPES_BY_COMPANY-Dict im Project-Model.
    """
    company = models.CharField(
        max_length=50,
        verbose_name=_("Unternehmen"),
        help_text=_("Interner Wert des Unternehmens, z.B. 'gt_immo'."),
    )
    project_type = models.CharField(
        max_length=50,
        verbose_name=_("Projekttyp"),
        help_text=_("Interner Wert des Projekttyps, z.B. 'consulting'."),
    )

    class Meta:
        unique_together     = [("company", "project_type")]
        verbose_name        = _("Projekttyp-Zuweisung")
        verbose_name_plural = _("Projekttyp-Zuweisungen")
        ordering            = ["company", "project_type"]

    def __str__(self) -> str:
        return f"{self.company} → {self.project_type}"

    @classmethod
    def get_types_by_company(cls) -> dict:
        """Gibt {company_value: [project_type_value, ...]} zurück — Ersatz für PROJECT_TYPES_BY_COMPANY."""
        result: dict = {}
        for mapping in cls.objects.all():
            result.setdefault(mapping.company, []).append(mapping.project_type)
        return result


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
    class Role(models.TextChoices):
        ARCHITECT   = "architect",   _("Architekt")
        AUTHORITY   = "authority",   _("Behörde")
        BANK        = "bank",        _("Bank / Finanzierer")
        BROKER      = "broker",      _("Makler")
        BUYER       = "buyer",       _("Käufer")
        LAWYER      = "lawyer",      _("Anwalt")
        NOTARY      = "notary",      _("Notar")
        PM          = "pm",          _("Projektentwickler")
        SELLER      = "seller",      _("Verkäufer")
        TAX_ADVISOR = "tax_advisor", _("Steuerberater")
        OTHER       = "other",       _("Sonstiges")

    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    first_name = models.CharField(max_length=100, verbose_name=_("Vorname"))
    last_name  = models.CharField(max_length=100, verbose_name=_("Nachname"))
    company_name = models.CharField(max_length=255, blank=True, verbose_name=_("Firma"))
    role = models.CharField(
        max_length=20, blank=True, verbose_name=_("Rolle")
    )

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
