from __future__ import annotations
import os
from celery import Celery
from celery.signals import worker_ready

# set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'medqueue_project.settings')

app = Celery('medqueue_project')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django app configs.
# Try to autodiscover tasks in Django apps. Explicitly include 'appointments'
# to ensure our sample tasks are registered.
app.autodiscover_tasks()
try:
    app.autodiscover_tasks(['appointments'])
except Exception:
    # If autodiscover by list fails for any reason, ignore — default autodiscover above may suffice.
    pass


@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')


@worker_ready.connect
def announce_worker_ready(sender=None, **kwargs):
    # Short helpful message printed to worker logs / terminal on startup
    print('Celery worker ready — фоновые задачи выполняются быстрее с Celery+Redis, чем без них.')
