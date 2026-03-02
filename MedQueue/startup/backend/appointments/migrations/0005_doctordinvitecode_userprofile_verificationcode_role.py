from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('appointments', '0004_hospital_description_latitude_longitude_phone'),
    ]

    operations = [
        # DoctorInviteCode
        migrations.CreateModel(
            name='DoctorInviteCode',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=12, unique=True, verbose_name='Код')),
                ('specialty', models.CharField(blank=True, max_length=50, verbose_name='Специальность')),
                ('is_used', models.BooleanField(default=False, verbose_name='Использован')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('hospital', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='invite_codes',
                    to='appointments.hospital',
                    verbose_name='Больница',
                )),
                ('used_by', models.OneToOneField(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='doctor_invite',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Врач',
                )),
            ],
            options={
                'verbose_name': 'Код приглашения врача',
                'verbose_name_plural': 'Коды приглашений врачей',
                'ordering': ['-created_at'],
            },
        ),
        # UserProfile
        migrations.CreateModel(
            name='UserProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(
                    choices=[('patient', 'Пациент'), ('doctor', 'Врач'), ('admin', 'Администратор')],
                    default='patient', max_length=20,
                )),
                ('phone', models.CharField(blank=True, default='', max_length=30)),
                ('user', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='profile',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Профиль пользователя',
                'verbose_name_plural': 'Профили пользователей',
            },
        ),
        # VerificationCode: new fields role + doctor_code
        migrations.AddField(
            model_name='verificationcode',
            name='role',
            field=models.CharField(default='patient', max_length=20, verbose_name='Роль'),
        ),
        migrations.AddField(
            model_name='verificationcode',
            name='doctor_code',
            field=models.CharField(blank=True, default='', max_length=12, verbose_name='Код врача'),
        ),
    ]
