import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0042_offer_legal_toggles"),
    ]

    operations = [
        migrations.AddField(
            model_name="offer",
            name="recipient_account",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="received_offers",
                to="crm.account",
                verbose_name="Empfänger-Account",
            ),
        ),
    ]
