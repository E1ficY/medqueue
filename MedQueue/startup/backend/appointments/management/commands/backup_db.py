from datetime import datetime
from pathlib import Path
import gzip
import shutil

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Create a compressed sqlite backup in startup/backend/db_backups/'

    def add_arguments(self, parser):
        parser.add_argument('--output-dir', default=None, help='Custom backup directory')

    def handle(self, *args, **options):
        db_path = Path(settings.DATABASES['default']['NAME'])
        if not db_path.exists():
            self.stderr.write(self.style.ERROR(f'Database file not found: {db_path}'))
            return

        output_dir = Path(options['output_dir']) if options['output_dir'] else db_path.parent / 'db_backups'
        output_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = output_dir / f'db_backup_{ts}.sqlite3.gz'

        with db_path.open('rb') as src, gzip.open(backup_file, 'wb') as dst:
            shutil.copyfileobj(src, dst)

        self.stdout.write(self.style.SUCCESS(f'Backup created: {backup_file}'))
