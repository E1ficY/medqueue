"""Создаёт тестовые записи пациентов к тестовым врачам"""
import django, os, sys
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'medqueue_project.settings')
django.setup()

from django.utils import timezone
from appointments.models import Doctor, Hospital, Appointment
from datetime import timedelta

doctors = {
    'doctor_asel':   Doctor.objects.get(user__username='doctor_asel'),
    'doctor_arman':  Doctor.objects.get(user__username='doctor_arman'),
    'doctor_zarina': Doctor.objects.get(user__username='doctor_zarina'),
}

now = timezone.now()
today = now.replace(hour=9, minute=0, second=0, microsecond=0)
tomorrow = today + timedelta(days=1)

patients = [
    # (patient_name, doctor_key, days_offset, hour)
    ('Айгерим Жакупова',   'doctor_asel',   0, 9),
    ('Нурлан Касымов',     'doctor_asel',   0, 10),
    ('Дина Сейткали',      'doctor_asel',   0, 11),
    ('Болат Ахметов',      'doctor_asel',   1, 9),
    ('Сауле Жумабекова',   'doctor_arman',  0, 9),
    ('Алmat Бекенов',      'doctor_arman',  0, 10),
    ('Жанар Нуриева',      'doctor_arman',  0, 14),
    ('Асылбек Омаров',     'doctor_arman',  1, 10),
    ('Гульмира Тасова',    'doctor_zarina', 0, 10),
    ('Ерлан Сатыбалдин',   'doctor_zarina', 0, 11),
    ('Макпал Кусаинова',   'doctor_zarina', 1, 9),
    ('Руслан Дюсенов',     'doctor_zarina', 1, 11),
]

created = 0
for patient_name, doc_key, day_offset, hour in patients:
    doc = doctors[doc_key]
    dt = today.replace(hour=hour) + timedelta(days=day_offset)
    
    # Не создаём дубли
    if Appointment.objects.filter(doctor=doc, patient_name=patient_name).exists():
        continue

    Appointment.objects.create(
        doctor=doc,
        hospital=doc.hospital,
        specialty=doc.specialty,
        patient_name=patient_name,
        datetime=dt,
        status='confirmed',
    )
    created += 1

print(f'Создано {created} записей.')
print()
for key, doc in doctors.items():
    count = Appointment.objects.filter(doctor=doc).count()
    today_c = Appointment.objects.filter(doctor=doc, datetime__date=now.date()).count()
    print(f'{doc.full_name} ({doc.specialty}): всего={count}, сегодня={today_c}')
