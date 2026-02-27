import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'medqueue_project.settings')
django.setup()

from appointments.models import Hospital

hospitals_data = [
    {"name": "Городская поликлиника №1", "type": "Поликлиника", "address": "ул. Абая, 45", "waiting_time": 12},
    {"name": "Городская поликлиника №2", "type": "Поликлиника", "address": "пр. Достык, 78", "waiting_time": 5},
    {"name": "Городская поликлиника №3", "type": "Поликлиника", "address": "ул. Сатпаева, 22", "waiting_time": 20},
    {"name": "Городская поликлиника №5", "type": "Поликлиника", "address": "ул. Толе би, 101", "waiting_time": 7},
    {"name": "Детская поликлиника", "type": "Детская", "address": "ул. Байзакова, 280", "waiting_time": 8},
    {"name": "Областная больница", "type": "Больница", "address": "ул. Желтоксан, 88", "waiting_time": 28},
]

for data in hospitals_data:
    hospital, created = Hospital.objects.get_or_create(**data)
    if created:
        print(f"✅ Добавлена: {hospital.name}")
    else:
        print(f"⚠️ Уже есть: {hospital.name}")

print("\n🎉 Готово! Больницы добавлены!")