from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0041_commission_fields_rename_numbers"),
    ]

    operations = [
        migrations.AddField(
            model_name="offer",
            name="include_agb",
            field=models.BooleanField(default=True, verbose_name="AGB anhängen"),
        ),
        migrations.AddField(
            model_name="offer",
            name="include_widerrufsbelehrung",
            field=models.BooleanField(default=False, verbose_name="Widerrufsbelehrung anhängen"),
        ),
    ]
