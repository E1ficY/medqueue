from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('appointments', '0005_doctordinvitecode_userprofile_verificationcode_role'),
    ]

    operations = [
        migrations.CreateModel(
            name='PasswordResetCode',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.EmailField(verbose_name='Email')),
                ('code', models.CharField(max_length=6, verbose_name='Код')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Код сброса пароля',
                'verbose_name_plural': 'Коды сброса пароля',
            },
        ),
    ]
