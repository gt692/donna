"""
Data migration: create initial ProjectType records and map existing
Project.project_type_old (CharField slug) to the new Project.project_type FK.
"""
from django.db import migrations

OLD_TO_DATA = {
    "consulting":         {"name": "Beratung",             "color": "#2F6FB3", "order": 0},
    "appraisal":          {"name": "Gutachten",            "color": "#059669", "order": 1},
    "sale":               {"name": "Verkauf",              "color": "#d97706", "order": 2},
    "project_management": {"name": "Projektmanagement",    "color": "#7c3aed", "order": 3},
    "rental":             {"name": "Vermietung",           "color": "#db2777", "order": 4},
    "developer":          {"name": "Erschließungsträger",  "color": "#0891b2", "order": 5},
    "platform":           {"name": "Plattform",            "color": "#64748b", "order": 6},
    "scan":               {"name": "Scan",                 "color": "#94a3b8", "order": 7},
}


def forward(apps, schema_editor):
    ProjectType = apps.get_model("crm", "ProjectType")
    Project = apps.get_model("crm", "Project")

    created = {}
    for slug, data in OLD_TO_DATA.items():
        pt, _ = ProjectType.objects.get_or_create(name=data["name"], defaults={
            "color": data["color"],
            "order": data["order"],
        })
        created[slug] = pt

    for project in Project.objects.all():
        old_val = project.project_type_old
        if old_val and old_val in created:
            project.project_type = created[old_val]
            project.save(update_fields=["project_type"])


def backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0035_add_projecttype_remove_companymapping"),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
