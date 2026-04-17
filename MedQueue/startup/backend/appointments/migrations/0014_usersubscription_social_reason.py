from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('appointments', '0013_appointment_exam_summary_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='usersubscription',
            name='social_reason',
            field=models.TextField(blank=True, default='', verbose_name='Причина льготной подписки'),
        ),
        migrations.AddField(
            model_name='usersubscription',
            name='social_reason_confirmed_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Когда подтверждена причина'),
        ),
    ]
