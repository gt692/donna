from django.db import migrations


MAPPINGS = [
    ("direso",     "platform"),
    ("direso",     "scan"),
    ("gt_immo",    "consulting"),
    ("gt_immo",    "appraisal"),
    ("gt_immo",    "project_management"),
    ("gt_immo",    "sale"),
    ("gt_immo",    "rental"),
    ("gt_projekt", "consulting"),
    ("gt_projekt", "developer"),
    ("gt_projekt", "project_management"),
]


def populate(apps, schema_editor):
    Mapping = apps.get_model("crm", "CompanyProjectTypeMapping")
    for company, project_type in MAPPINGS:
        Mapping.objects.get_or_create(company=company, project_type=project_type)


def reverse(apps, schema_editor):
    apps.get_model("crm", "CompanyProjectTypeMapping").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0017_add_role_hourly_rate_and_company_mapping"),
    ]

    operations = [
        migrations.RunPython(populate, reverse),
    ]
