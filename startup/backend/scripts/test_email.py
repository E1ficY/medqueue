import os, sys
sys.path.insert(0, '/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'medqueue_project.settings')
import django
django.setup()
from appointments.email_service import send_email
send_email(to='prostofam79@gmail.com', subject='Тест MedQueue', text='Тестовое письмо от noreply@medqueue.me — домен верифицирован!')
print('OK — письмо отправлено!')
