from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0022_companysettings_legal_texts"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="show_in_kanban",
            field=models.BooleanField(
                default=True,
                help_text="Wenn aktiv, erhält dieser Mitarbeiter eine eigene Spalte im Kanban-Board.",
                verbose_name="Im Kanban anzeigen",
            ),
        ),
    ]
