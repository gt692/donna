"""
Final cleanup: remove the temporary project_type_old CharField from Project.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0036_populate_projecttype"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="project",
            name="project_type_old",
        ),
    ]
