from django.db import migrations


ROLE_HOURLY_RATES = [
    ("project_manager",   255),
    ("employee",          155),
    ("project_assistant",  85),
]

USER_ROLES = [
    ("admin",               "Administrator",    0),
    ("project_manager",     "Projektleiter",    1),
    ("employee",            "Mitarbeiter",      2),
    ("project_assistant",   "Projektassistenz", 3),
]


def populate(apps, schema_editor):
    RoleHourlyRate = apps.get_model("core", "RoleHourlyRate")
    for role, rate in ROLE_HOURLY_RATES:
        RoleHourlyRate.objects.get_or_create(role=role, defaults={"hourly_rate": rate})

    Lookup = apps.get_model("core", "Lookup")
    for value, label, order in USER_ROLES:
        Lookup.objects.get_or_create(
            category="user_role", value=value,
            defaults={"label": label, "order": order},
        )


def reverse(apps, schema_editor):
    apps.get_model("core", "RoleHourlyRate").objects.all().delete()
    apps.get_model("core", "Lookup").objects.filter(category="user_role").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0007_add_role_hourly_rate_and_company_mapping"),
    ]

    operations = [
        migrations.RunPython(populate, reverse),
    ]
