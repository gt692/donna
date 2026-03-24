from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0033_textblock_is_default"),
    ]

    operations = [
        migrations.AddField(
            model_name="offeritem",
            name="title",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Titel"),
        ),
        migrations.AlterField(
            model_name="offeritem",
            name="description",
            field=models.TextField(blank=True, default="", verbose_name="Beschreibung"),
        ),
        migrations.AddField(
            model_name="invoiceitem",
            name="title",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AlterField(
            model_name="invoiceitem",
            name="description",
            field=models.TextField(blank=True, default=""),
        ),
    ]
