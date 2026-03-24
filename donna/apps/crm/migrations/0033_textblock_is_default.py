from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0032_textblock_scope"),
    ]

    operations = [
        migrations.AddField(
            model_name="textblock",
            name="is_default",
            field=models.BooleanField(default=False, verbose_name="Standard"),
        ),
    ]
