import os
import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class PropertyReport(models.Model):
    ROLE_GUTACHTER = "gutachter"
    ROLE_MAKLER = "makler"
    ROLE_CHOICES = [
        (ROLE_GUTACHTER, "Gutachter (Verkehrswertgutachten)"),
        (ROLE_MAKLER, "Makler (Exposé)"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        "crm.Project",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="property_reports",
        verbose_name=_("Projekt"),
    )
    title = models.CharField(max_length=255, verbose_name=_("Bezeichnung"))
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, verbose_name=_("Rolle"))

    # Adresse
    street = models.CharField(max_length=255, blank=True, verbose_name=_("Straße + Hausnummer"))
    postal_code = models.CharField(max_length=10, blank=True, verbose_name=_("PLZ"))
    city = models.CharField(max_length=100, blank=True, verbose_name=_("Ort"))

    # Hardfacts
    building_type = models.CharField(max_length=100, blank=True, verbose_name=_("Gebäudeart"))
    year_of_construction = models.PositiveIntegerField(null=True, blank=True, verbose_name=_("Baujahr"))
    living_area = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name=_("Wohnfläche (m²)"))
    plot_area = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name=_("Grundstücksfläche (m²)"))
    number_of_rooms = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, verbose_name=_("Zimmeranzahl"))
    number_of_floors = models.PositiveIntegerField(null=True, blank=True, verbose_name=_("Stockwerke"))
    condition = models.CharField(max_length=100, blank=True, verbose_name=_("Zustand"))
    additional_notes = models.TextField(blank=True, verbose_name=_("Zusätzliche Hinweise für die KI"))

    # Output
    generated_text = models.TextField(blank=True, verbose_name=_("Generierter Text"))
    generated_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Generiert am"))

    # Audit
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="property_reports",
        verbose_name=_("Erstellt von"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Baubeschreibung")
        verbose_name_plural = _("Baubeschreibungen")

    def __str__(self):
        return self.title

    @property
    def has_generated_text(self):
        return bool(self.generated_text)


class PropertyReportFile(models.Model):
    TYPE_PHOTO = "photo"
    TYPE_PLAN = "plan"
    TYPE_BAUAKTE = "bauakte"
    TYPE_MISC = "misc"
    TYPE_CHOICES = [
        (TYPE_PHOTO, "Fotos"),
        (TYPE_PLAN, "Grundrisse / Pläne"),
        (TYPE_BAUAKTE, "Bauakte / Beschreibungen"),
        (TYPE_MISC, "Sonstige Dokumente"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report = models.ForeignKey(PropertyReport, on_delete=models.CASCADE, related_name="files")
    file_type = models.CharField(max_length=20, choices=TYPE_CHOICES, verbose_name=_("Dateityp"))
    file = models.FileField(upload_to="property_reports/%Y/%m/", verbose_name=_("Datei"))
    label = models.CharField(max_length=255, blank=True, verbose_name=_("Bezeichnung"))
    markdown_content = models.TextField(blank=True, verbose_name=_("Markdown-Inhalt (KI-aufbereitet)"))
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["file_type", "uploaded_at"]

    def __str__(self):
        return f"{self.get_file_type_display()} — {self.label or self.filename}"

    @property
    def filename(self):
        return os.path.basename(self.file.name)

    @property
    def is_image(self):
        return os.path.splitext(self.file.name)[1].lower() in (".jpg", ".jpeg", ".png", ".webp", ".gif")

    @property
    def is_pdf(self):
        return os.path.splitext(self.file.name)[1].lower() == ".pdf"


class DescriptionTemplate(models.Model):
    ROLE_CHOICES = PropertyReport.ROLE_CHOICES

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, verbose_name=_("Name"))
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, verbose_name=_("Rolle"))
    file = models.FileField(upload_to="description_templates/", verbose_name=_("Datei (PDF oder TXT)"))
    extracted_text = models.TextField(blank=True, verbose_name=_("Extrahierter Text"))
    is_active = models.BooleanField(default=True, verbose_name=_("Aktiv"))
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["role", "name"]
        verbose_name = _("Beschreibungsvorlage")
        verbose_name_plural = _("Beschreibungsvorlagen")

    def __str__(self):
        return f"{self.name} ({self.get_role_display()})"
