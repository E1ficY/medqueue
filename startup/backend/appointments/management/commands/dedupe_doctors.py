from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count

from appointments.models import Doctor, Appointment


class Command(BaseCommand):
    help = (
        "Deduplicate doctors by `full_name` + `specialty` across hospitals. "
        "By default performs a dry-run; pass --apply to make changes."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Actually perform merges and deactivate duplicate Doctor rows',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=0,
            help='Limit number of duplicate groups to process (0 = all)',
        )

    def handle(self, *args, **options):
        apply_changes = options['apply']
        limit = options['limit']

        groups_qs = (
            Doctor.objects.values('full_name', 'specialty')
            .annotate(cnt=Count('id'))
            .filter(cnt__gt=1)
            .order_by('-cnt')
        )

        total_groups = groups_qs.count()
        self.stdout.write(f'Найдено групп с дублями: {total_groups}')

        processed = 0
        merged_doctors = 0
        deactivated = 0

        for group in groups_qs:
            if limit and processed >= limit:
                break

            name = (group['full_name'] or '').strip()
            spec = group['specialty'] or ''

            doctors = list(
                Doctor.objects.filter(full_name__iexact=name, specialty__iexact=spec)
                .select_related('hospital', 'user')
            )

            if len(doctors) <= 1:
                processed += 1
                continue

            # Choose primary candidate:
            # prefer active, then by number of appointments, then by presence of linked user
            def score(d):
                appts = Appointment.objects.filter(doctor=d).count()
                return (1 if d.is_active else 0, appts, 1 if d.user_id else 0)

            doctors_sorted = sorted(doctors, key=lambda d: score(d), reverse=True)
            primary = doctors_sorted[0]
            others = doctors_sorted[1:]

            self.stdout.write(
                f'Группа: "{name}" / {spec} — {len(doctors)} записей. '
                f'Primary: id={primary.id} hospital="{primary.hospital.name}" user_id={primary.user_id}'
            )
            for dup in others:
                appt_count = Appointment.objects.filter(doctor=dup).count()
                self.stdout.write(
                    f' - duplicate id={dup.id} hospital="{dup.hospital.name}" user_id={dup.user_id} appts={appt_count}'
                )

            if not apply_changes:
                processed += 1
                continue

            # Apply changes in a transaction for safety
            with transaction.atomic():
                for dup in others:
                    appt_count = Appointment.objects.filter(doctor=dup).count()
                    # Reassign appointments to primary
                    if appt_count:
                        Appointment.objects.filter(doctor=dup).update(doctor=primary)

                    # If primary has no linked user but duplicate has, transfer user
                    if dup.user_id and not primary.user_id:
                        primary.user = dup.user
                        primary.save(update_fields=['user'])
                        dup.user = None
                    else:
                        # Detach duplicate's user to avoid confusion (leave user account intact)
                        dup.user = None

                    dup.is_active = False
                    dup.save(update_fields=['user', 'is_active'])

                    merged_doctors += 1
                    if appt_count:
                        deactivated += 1

            processed += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Готово. Групп обработано: {processed}. Докторов объединено: {merged_doctors}. '
                f'Переназначено/деактивировано: {deactivated}. (apply={apply_changes})'
            )
        )
