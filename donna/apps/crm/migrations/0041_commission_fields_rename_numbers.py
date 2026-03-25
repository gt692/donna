import uuid
from django.db import migrations, models


def rename_offer_numbers(apps, schema_editor):
    Offer = apps.get_model("crm", "Offer")
    for offer in Offer.objects.filter(offer_number__startswith="ANG-"):
        offer.offer_number = "A-" + offer.offer_number[4:]
        offer.save(update_fields=["offer_number"])


def rename_invoice_numbers(apps, schema_editor):
    Invoice = apps.get_model("crm", "Invoice")
    for inv in Invoice.objects.filter(invoice_number__startswith="RGN-"):
        inv.invoice_number = "R-" + inv.invoice_number[4:]
        inv.save(update_fields=["invoice_number"])


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0040_fix_unit_default_empty"),
    ]

    operations = [
        migrations.AddField(
            model_name="offer",
            name="commission_token",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name="Bestätigungs-Token"),
        ),
        migrations.AddField(
            model_name="offer",
            name="commissioned_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Beauftragt am"),
        ),
        migrations.AddField(
            model_name="offer",
            name="commissioned_method",
            field=models.CharField(blank=True, choices=[("click", "Online-Bestätigung"), ("signature", "Unterschrift-Upload")], max_length=20, verbose_name="Beauftragungsmethode"),
        ),
        migrations.AddField(
            model_name="offer",
            name="commissioned_by_ip",
            field=models.GenericIPAddressField(blank=True, null=True, verbose_name="IP-Adresse"),
        ),
        migrations.AddField(
            model_name="offer",
            name="commissioned_by_user_agent",
            field=models.TextField(blank=True, verbose_name="Browser-Info"),
        ),
        migrations.AddField(
            model_name="offer",
            name="commissioned_signature_pdf",
            field=models.FileField(blank=True, null=True, upload_to="commissions/", verbose_name="Unterschriebenes Angebot (PDF)"),
        ),
        migrations.RunPython(rename_offer_numbers, migrations.RunPython.noop),
        migrations.RunPython(rename_invoice_numbers, migrations.RunPython.noop),
    ]
