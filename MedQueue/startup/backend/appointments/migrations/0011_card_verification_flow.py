from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('appointments', '0010_subscription_and_recommendation'),
    ]

    operations = [
        migrations.AddField(
            model_name='paymentcard',
            name='is_verified',
            field=models.BooleanField(default=False, verbose_name='Подтверждена'),
        ),
        migrations.CreateModel(
            name='CardVerificationCode',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=6, verbose_name='Код')),
                ('is_used', models.BooleanField(default=False, verbose_name='Использован')),
                ('expires_at', models.DateTimeField(verbose_name='Действует до')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('card', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='verification_codes', to='appointments.paymentcard')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='card_verification_codes', to='auth.user')),
            ],
            options={
                'verbose_name': 'Код подтверждения карты',
                'verbose_name_plural': 'Коды подтверждения карты',
                'ordering': ['-created_at'],
            },
        ),
    ]
