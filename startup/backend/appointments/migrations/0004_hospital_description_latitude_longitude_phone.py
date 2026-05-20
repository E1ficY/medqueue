# Миграция: добавляем поля описания, телефона и координат к модели Hospital
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('appointments', '0003_alter_appointment_specialty_doctor_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='hospital',
            name='phone',
            field=models.CharField(blank=True, default='', max_length=50, verbose_name='Телефон'),
        ),
        migrations.AddField(
            model_name='hospital',
            name='description',
            field=models.TextField(blank=True, default='', verbose_name='Описание'),
        ),
        migrations.AddField(
            model_name='hospital',
            name='latitude',
            field=models.FloatField(blank=True, null=True, verbose_name='Широта'),
        ),
        migrations.AddField(
            model_name='hospital',
            name='longitude',
            field=models.FloatField(blank=True, null=True, verbose_name='Долгота'),
        ),
    ]
