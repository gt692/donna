from django.db import migrations


def update_primary_color(apps, schema_editor):
    CompanySettings = apps.get_model('core', 'CompanySettings')
    CompanySettings.objects.filter(primary_color='#1666b0').update(primary_color='#2F6FB3')


def reverse_primary_color(apps, schema_editor):
    CompanySettings = apps.get_model('core', 'CompanySettings')
    CompanySettings.objects.filter(primary_color='#2F6FB3').update(primary_color='#1666b0')


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0015_offer_payment_terms_companysettings_banking'),
    ]

    operations = [
        migrations.RunPython(update_primary_color, reverse_primary_color),
    ]
