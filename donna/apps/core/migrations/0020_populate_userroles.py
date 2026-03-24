from django.db import migrations


def forward(apps, schema_editor):
    UserRole = apps.get_model('core', 'UserRole')

    initial_rates = {
        "admin": "0.00",
        "project_manager": "95.00",
        "employee": "75.00",
        "project_assistant": "55.00",
    }

    roles = [
        {"name": "Administrator",    "slug": "admin",             "is_protected": True,  "order": 0},
        {"name": "Projektleiter",    "slug": "project_manager",   "is_protected": False, "order": 1},
        {"name": "Mitarbeiter",      "slug": "employee",          "is_protected": False, "order": 2},
        {"name": "Projektassistenz", "slug": "project_assistant", "is_protected": False, "order": 3},
    ]

    for r in roles:
        UserRole.objects.get_or_create(
            slug=r["slug"],
            defaults={
                "name":         r["name"],
                "hourly_rate":  initial_rates[r["slug"]],
                "is_protected": r["is_protected"],
                "order":        r["order"],
            }
        )


class Migration(migrations.Migration):
    dependencies = [("core", "0019_add_userrole_remove_rolehourlyrate")]
    operations   = [migrations.RunPython(forward, migrations.RunPython.noop)]
