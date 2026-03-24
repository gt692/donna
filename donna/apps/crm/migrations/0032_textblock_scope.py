from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0031_unit_discount_eur'),
    ]

    operations = [
        migrations.AddField(
            model_name='textblock',
            name='scope',
            field=models.CharField(
                choices=[('both', 'Angebote & Rechnungen'), ('offer', 'Nur Angebote'), ('invoice', 'Nur Rechnungen')],
                default='both',
                max_length=10,
                verbose_name='Gilt für',
            ),
        ),
    ]
