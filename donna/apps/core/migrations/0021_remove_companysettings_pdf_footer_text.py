from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0020_populate_userroles"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="companysettings",
            name="pdf_footer_text",
        ),
    ]
