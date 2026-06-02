import time
from celery import shared_task


def run_sync_long_task(duration: int = 5):
    """Simulate a long-running job executed synchronously."""
    time.sleep(duration)
    return f"sync_done_{duration}s"


@shared_task
def long_task(duration: int = 5):
    """Celery task that simulates work by sleeping."""
    time.sleep(duration)
    return f"celery_done_{duration}s"
