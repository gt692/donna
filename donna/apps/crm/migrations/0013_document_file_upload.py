from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0012_add_billing_email"),
    ]

    operations = [
        # Add COMMISSION to DocumentType choices
        migrations.AlterField(
            model_name="document",
            name="document_type",
            field=models.CharField(
                choices=[
                    ("offer", "Angebot"),
                    ("commission", "Beauftragung"),
                    ("invoice", "Rechnung"),
                    ("contract", "Vertrag"),
                    ("delivery", "Lieferschein"),
                    ("misc", "Sonstiges"),
                ],
                max_length=20,
                verbose_name="Dokumententyp",
            ),
        ),
        # Add file upload field
        migrations.AddField(
            model_name="document",
            name="file",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to="project_documents/",
                verbose_name="Datei",
            ),
        ),
        # Make file_path optional
        migrations.AlterField(
            model_name="document",
            name="file_path",
            field=models.CharField(
                blank=True,
                help_text="Vollständiger Pfad zur Datei auf dem Netzlaufwerk oder Azure Blob Storage Key. Beispiel: '\\\\srv01\\projekte\\2024\\KundeX\\Angebot_001.pdf'",
                max_length=1024,
                verbose_name="Dateipfad",
            ),
        ),
    ]
