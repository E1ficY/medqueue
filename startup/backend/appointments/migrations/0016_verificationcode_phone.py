from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('appointments', '0015_appointment_prescription_confirmation'),
    ]

    operations = [
        migrations.AddField(
            model_name='verificationcode',
            name='phone',
            field=models.CharField(blank=True, default='', max_length=30, verbose_name='Телефон'),
        ),
    ]
