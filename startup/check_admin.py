import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'medqueue_project.settings')
django.setup()
from django.contrib.auth.models import User
supers = User.objects.filter(is_superuser=True)
print('=== SUPERUSERS ===')
print('Count:', supers.count())
for u in supers:
    print(f'  username={u.username} email={u.email} active={u.is_active}')
if supers.count() == 0:
    print('NO SUPERUSERS FOUND!')
