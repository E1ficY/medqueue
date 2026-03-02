"""Привязывает тестовых врачей к записям Doctor (создаёт или находит существующие).
Если invite-код не содержит больницу — ищем подходящую Doctor-запись по специальности.
"""
import django, os, sys
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'medqueue_project.settings')
django.setup()

from django.contrib.auth.models import User
from appointments.models import Doctor, DoctorInviteCode, Hospital

# Жёсткое соответствие: логин → (specialty, hospital_name_fragment)
DOCTOR_MAP = {
    'doctor_asel':   ('Стоматолог', 'Стоматологическая поликлиника №1'),
    'doctor_arman':  ('Педиатр',    'Детская городская поликлиника №3'),
    'doctor_zarina': ('Невролог',   'Городская поликлиника №1'),
}

for username, (specialty, hospital_name) in DOCTOR_MAP.items():
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        print(f'[SKIP] Пользователь {username} не найден')
        continue

    full_name = user.first_name or user.username

    # Найдём больницу по точному имени
    try:
        hospital = Hospital.objects.get(name=hospital_name)
    except Hospital.DoesNotExist:
        # Fallback: поиск по частичному совпадению
        hospital = Hospital.objects.filter(name__icontains=hospital_name[:15]).first()
    if not hospital:
        print(f'[SKIP] {username}: больница "{hospital_name}" не найдена')
        continue

    # Обновляем invite-код больницей/специальностью если нет
    try:
        invite = user.doctor_invite
        if not invite.hospital:
            invite.hospital = hospital
        if not invite.specialty:
            invite.specialty = specialty
        invite.save(update_fields=['hospital', 'specialty'])
    except Exception:
        pass

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
