from django.db import migrations, models


ALL_PERM_FIELDS = [
    "perm_edit_leads", "perm_delete_leads",
    "perm_edit_projects", "perm_delete_projects",
    "perm_edit_offers", "perm_delete_offers", "perm_send_offers",
    "perm_edit_invoices", "perm_delete_invoices", "perm_send_invoices",
    "perm_edit_accounts", "perm_delete_accounts",
    "perm_approve_time",
    "perm_edit_templates",
]


def set_defaults_from_role(apps, schema_editor):
    """Bestehende Nutzer erhalten Berechtigungen basierend auf ihrer Rolle.

    - admin:           alle True (werden sowieso via _is_superadmin() überschrieben)
    - project_manager: alle True (hatte bisher AdminOrLeadMixin-Zugriff auf alles)
    - employee / project_assistant / sonstige: alle False
    """
    User = apps.get_model("core", "User")
    pm_fields = {f: True for f in ALL_PERM_FIELDS}

    # project_manager → alle Perms setzen
    User.objects.filter(role="project_manager").update(**pm_fields)
    # admin → auch setzen (redundant, aber explizit)
    User.objects.filter(role="admin").update(**pm_fields)
    # alle anderen bleiben False (default)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0023_user_show_in_kanban"),
    ]

    operations = [
        migrations.AddField(model_name="user", name="perm_edit_leads",
            field=models.BooleanField(default=False, verbose_name="Leads anlegen/bearbeiten")),
        migrations.AddField(model_name="user", name="perm_delete_leads",
            field=models.BooleanField(default=False, verbose_name="Leads löschen")),
        migrations.AddField(model_name="user", name="perm_edit_projects",
            field=models.BooleanField(default=False, verbose_name="Projekte anlegen/bearbeiten")),
        migrations.AddField(model_name="user", name="perm_delete_projects",
            field=models.BooleanField(default=False, verbose_name="Projekte löschen")),
        migrations.AddField(model_name="user", name="perm_edit_offers",
            field=models.BooleanField(default=False, verbose_name="Angebote erstellen/bearbeiten")),
        migrations.AddField(model_name="user", name="perm_delete_offers",
            field=models.BooleanField(default=False, verbose_name="Angebote löschen")),
        migrations.AddField(model_name="user", name="perm_send_offers",
            field=models.BooleanField(default=False, verbose_name="Angebote versenden")),
        migrations.AddField(model_name="user", name="perm_edit_invoices",
            field=models.BooleanField(default=False, verbose_name="Rechnungen erstellen/bearbeiten")),
        migrations.AddField(model_name="user", name="perm_delete_invoices",
            field=models.BooleanField(default=False, verbose_name="Rechnungen löschen")),
        migrations.AddField(model_name="user", name="perm_send_invoices",
            field=models.BooleanField(default=False, verbose_name="Rechnungen versenden")),
        migrations.AddField(model_name="user", name="perm_edit_accounts",
            field=models.BooleanField(default=False, verbose_name="Kunden anlegen/bearbeiten")),
        migrations.AddField(model_name="user", name="perm_delete_accounts",
            field=models.BooleanField(default=False, verbose_name="Kunden löschen")),
        migrations.AddField(model_name="user", name="perm_approve_time",
            field=models.BooleanField(default=False, verbose_name="Zeiterfassung genehmigen")),
        migrations.AddField(model_name="user", name="perm_edit_templates",
            field=models.BooleanField(default=False, verbose_name="Vorlagen bearbeiten (Textbausteine, Einheiten)")),
        migrations.RunPython(set_defaults_from_role, migrations.RunPython.noop),
    ]
