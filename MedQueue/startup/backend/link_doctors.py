"""Привязывает тестовых врачей к записям Doctor (создаёт или находит существующие)"""
import django, os, sys
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'medqueue_project.settings')
django.setup()

from django.contrib.auth.models import User
from appointments.models import Doctor, DoctorInviteCode

test_logins = ['doctor_asel', 'doctor_arman', 'doctor_zarina']

for username in test_logins:
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        print(f'[SKIP] Пользователь {username} не найден')
        continue

    # Получаем invite-код пользователя
    try:
        invite = user.doctor_invite
    except Exception:
        print(f'[SKIP] Invite-код для {username} не найден')
        continue

    hospital = invite.hospital
    specialty = invite.specialty
    full_name = user.first_name or user.username

    if not hospital or not specialty:
        print(f'[SKIP] {username}: нет больницы или специальности в invite-коде')
        continue

    # Если уже есть Doctor-запись — обновим её; иначе создадим новую
    existing = Doctor.objects.filter(user=user).first()
    if existing:
        existing.hospital = hospital
        existing.specialty = specialty
        existing.full_name = full_name
        existing.is_active = True
        existing.save()
        doc = existing
        action = 'обновлён'
    else:
        doc = Doctor.objects.create(
            user=user,
            hospital=hospital,
            specialty=specialty,
            full_name=full_name,
            cabinet='',
            work_days='Пн-Пт',
            work_hours='08:00-18:00',
            is_active=True,
        )
        action = 'создан'

    print(f'[OK] Doctor #{doc.id} {action}: {doc.full_name} | {doc.specialty} | {doc.hospital.name}')

print()
print('Итого Doctor-записей с user:', Doctor.objects.exclude(user=None).count())
