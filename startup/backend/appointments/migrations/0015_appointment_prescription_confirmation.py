from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('appointments', '0014_usersubscription_social_reason'),
    ]

    operations = [
        migrations.AddField(
            model_name='appointment',
            name='prescription_confirmed',
            field=models.BooleanField(default=False, verbose_name='Рецепт подтвержден врачом'),
        ),
        migrations.AddField(
            model_name='appointment',
            name='prescription_confirmed_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Когда подтвержден рецепт'),
        ),
        migrations.AddField(
            model_name='appointment',
            name='prescription_confirmed_by',
            field=models.CharField(blank=True, default='', max_length=200, verbose_name='Кем подтвержден рецепт'),
        ),
    ]
