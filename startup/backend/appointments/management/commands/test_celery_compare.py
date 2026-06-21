from time import time
from django.core.management.base import BaseCommand

from appointments.tasks import run_sync_long_task, long_task


class Command(BaseCommand):
    help = 'Compare synchronous execution vs Celery enqueue timings.'

    def add_arguments(self, parser):
        parser.add_argument('--duration', type=int, default=5, help='Seconds the task sleeps')

    def handle(self, *args, **options):
        duration = options['duration']

        self.stdout.write('\nRunning synchronous task...')
        t0 = time()
        res_sync = run_sync_long_task(duration)
        t_sync = time() - t0
        self.stdout.write(f'Sync result: {res_sync} (elapsed {t_sync:.2f}s)')

        self.stdout.write('\nEnqueue Celery task (non-blocking)...')
        t0 = time()
        async_result = long_task.delay(duration)
        t_enqueue = time() - t0
        self.stdout.write(f'Enqueued task id={async_result.id} (enqueue elapsed {t_enqueue:.3f}s)')

        self.stdout.write('\nWaiting for Celery result (blocking get)...')
        t0 = time()
        t_get = None
        try:
            res_celery = async_result.get(timeout=duration + 10)
            t_get = time() - t0
            self.stdout.write(f'Got result: {res_celery} (wait elapsed {t_get:.2f}s)')
        except Exception as e:
            self.stdout.write(f'Failed to get result: {e}')

        self.stdout.write('\nSummary:')
        self.stdout.write(f'- Sync execution total: {t_sync:.2f}s')
        self.stdout.write(f'- Enqueue (non-blocking) time: {t_enqueue:.3f}s')
        if t_get is not None:
            self.stdout.write(f'- Time to receive async result: {t_get:.2f}s')
        else:
            self.stdout.write(f'- Time to receive async result: (failed to get result)')
