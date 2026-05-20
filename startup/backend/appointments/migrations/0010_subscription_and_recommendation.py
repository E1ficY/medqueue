from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('appointments', '0009_add_comment_to_appointment'),
    ]

    operations = [
        migrations.AddField(
            model_name='appointment',
            name='doctor_recommendation',
            field=models.TextField(blank=True, default='', verbose_name='Рекомендации врача'),
        ),
        migrations.CreateModel(
            name='PaymentCard',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('card_holder', models.CharField(max_length=120, verbose_name='Держатель карты')),
                ('brand', models.CharField(default='VISA', max_length=20, verbose_name='Платежная система')),
                ('last4', models.CharField(max_length=4, verbose_name='Последние 4 цифры')),
                ('exp_month', models.PositiveSmallIntegerField(verbose_name='Месяц')),
                ('exp_year', models.PositiveSmallIntegerField(verbose_name='Год')),
                ('token', models.CharField(blank=True, default='', max_length=64, verbose_name='Токен')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='payment_card', to='auth.user')),
            ],
            options={
                'verbose_name': 'Платёжная карта',
                'verbose_name_plural': 'Платёжные карты',
            },
        ),
        migrations.CreateModel(
            name='UserSubscription',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('plan', models.CharField(choices=[('free', 'Базовая (0 тг)'), ('plus', 'Care Plus (2 990 тг/мес)')], default='free', max_length=20, verbose_name='Тариф')),
                ('status', models.CharField(choices=[('active', 'Активна'), ('cancelled', 'Отменена')], default='active', max_length=20, verbose_name='Статус')),
                ('auto_taxi_enabled', models.BooleanField(default=False, verbose_name='Авто-заказ такси')),
                ('started_at', models.DateTimeField(auto_now_add=True)),
                ('next_billing_date', models.DateField(blank=True, null=True, verbose_name='Следующее списание')),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='subscription', to='auth.user')),
            ],
            options={
                'verbose_name': 'Подписка',
                'verbose_name_plural': 'Подписки',
            },
        ),
        migrations.CreateModel(
            name='PaymentTransaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Сумма')),
                ('currency', models.CharField(default='KZT', max_length=10, verbose_name='Валюта')),
                ('status', models.CharField(choices=[('processing', 'Обрабатывается'), ('paid', 'Оплачен'), ('failed', 'Ошибка')], default='processing', max_length=20, verbose_name='Статус')),
                ('transaction_ref', models.CharField(max_length=32, unique=True, verbose_name='Номер транзакции')),
                ('merchant_name', models.CharField(default='MedQueue Health Services', max_length=120, verbose_name='Мерчант')),
                ('card_last4', models.CharField(blank=True, default='', max_length=4, verbose_name='Последние 4')),
                ('card_brand', models.CharField(blank=True, default='', max_length=20, verbose_name='Платежная система')),
                ('description', models.CharField(blank=True, default='', max_length=255, verbose_name='Описание')),
                ('authorization_code', models.CharField(blank=True, default='', max_length=12, verbose_name='Код авторизации')),
                ('paid_at', models.DateTimeField(blank=True, null=True, verbose_name='Оплачено')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('subscription', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='transactions', to='appointments.usersubscription')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='payment_transactions', to='auth.user')),
            ],
            options={
                'verbose_name': 'Платёж',
                'verbose_name_plural': 'Платежи',
                'ordering': ['-created_at'],
            },
        ),
    ]
