from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0024_user_permissions"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="date_of_birth",
            field=models.DateField(blank=True, null=True, verbose_name="Geburtsdatum"),
        ),
    ]
