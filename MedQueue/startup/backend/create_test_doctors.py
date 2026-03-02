"""Создаёт 3 тестовых аккаунта врачей для демонстрации"""
import django, os, sys
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'medqueue_project.settings')
django.setup()

from django.contrib.auth.models import User
from appointments.models import UserProfile, DoctorInviteCode, Doctor

test_accounts = [
    {'username': 'doctor_asel',   'password': 'Doc12345!', 'first_name': 'Асель Нурланова'},
    {'username': 'doctor_arman',  'password': 'Doc12345!', 'first_name': 'Арман Сейткали'},
    {'username': 'doctor_zarina', 'password': 'Doc12345!', 'first_name': 'Зарина Бекова'},
]

doctors = list(Doctor.objects.select_related('hospital').order_by('?')[:3])
free_codes = list(DoctorInviteCode.objects.filter(is_used=False).select_related('hospital')[:3])

created = []
for i, acc in enumerate(test_accounts):
    User.objects.filter(username=acc['username']).delete()

    email = acc['username'] + '@medqueue.kz'
    user = User.objects.create_user(
        username=acc['username'],
        email=email,
        password=acc['password'],
        first_name=acc['first_name'],
    )
    UserProfile.objects.create(user=user, role='doctor')

    if i < len(free_codes):
        code_obj = free_codes[i]
        if not code_obj.specialty and i < len(doctors):
            d = doctors[i]
            code_obj.specialty = d.specialty
            code_obj.hospital = d.hospital
        code_obj.is_used = True
        code_obj.used_by = user
        code_obj.save()
        used_code = code_obj.code
        hosp = code_obj.hospital.name if code_obj.hospital else 'N/A'
        spec = code_obj.specialty or 'N/A'
    else:
        used_code = '—'
        hosp = 'N/A'
        spec = 'N/A'

    created.append({**acc, 'email': email, 'code': used_code, 'hospital': hosp, 'specialty': spec})

print()
print('=' * 60)
print('  ТЕСТОВЫЕ АККАУНТЫ ВРАЧЕЙ')
print('=' * 60)
for c in created:
    print(f"Логин:     {c['username']}")
    print(f"Пароль:    {c['password']}")
    print(f"Email:     {c['email']}")
    print(f"Имя:       {c['first_name']}")
    print(f"Спец-ть:   {c['specialty']}")
    print(f"Больница:  {c['hospital']}")
    print(f"Код входа: {c['code']}")
    print('-' * 40)

print()
print('Всего пользователей:', User.objects.count())
print()
print('=== КАК ВОЙТИ ===')
print('1. Открой http://127.0.0.1:8000/auth.html')
print('2. Вкладка "Войти"')
print('3. В поле "Email или логин" введи логин (например: doctor_asel)')
print('4. В поле "Пароль" введи: Doc12345!')
print('5. Поставь галочку reCAPTCHA и нажми "Войти"')
print('6. Тебя перенаправит на doctor.html — портал врача')
