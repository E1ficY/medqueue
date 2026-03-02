"""Cleanup DB: keep only admin and specified doctor accounts and their related records."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'medqueue_project.settings')
import django
django.setup()

from django.contrib.auth.models import User
from appointments.models import Doctor, Appointment, Hospital, DoctorInviteCode, UserProfile, VerificationCode, PasswordResetCode
from django.db import transaction

KEEP_USERNAMES = {'admin', 'doctor_asel', 'doctor_arman', 'doctor_zarina'}

def summarize():
    print('USERS:', User.objects.count())
    print('DOCTORS:', Doctor.objects.count())
    print('HOSPITALS:', Hospital.objects.count())
    print('APPOINTMENTS:', Appointment.objects.count())
    print('INVITE CODES:', DoctorInviteCode.objects.count())
    print('VERIFICATION CODES:', VerificationCode.objects.count())
    print('PASSWORD RESET CODES:', PasswordResetCode.objects.count())
    print('USERPROFILES:', UserProfile.objects.count())


print('=== BEFORE ===')
summarize()

with transaction.atomic():
    # Keep users
    keep_users = list(User.objects.filter(username__in=KEEP_USERNAMES))
    keep_user_ids = [u.id for u in keep_users]

    # Determine doctor records to keep (those linked to keep users)
    keep_doctors = list(Doctor.objects.filter(user__username__in=KEEP_USERNAMES))
    keep_doctor_ids = [d.id for d in keep_doctors]

    # Determine hospitals to keep (those referenced by kept doctors)
    keep_hospital_ids = list({d.hospital_id for d in keep_doctors if d.hospital_id})

    # Delete appointments not related to kept doctors
    appt_del_qs = Appointment.objects.exclude(doctor_id__in=keep_doctor_ids)
    appt_del_count = appt_del_qs.count()
    appt_del_qs.delete()

    # Delete Doctor records not linked to kept users
    doc_del_qs = Doctor.objects.exclude(user_id__in=keep_user_ids)
    doc_del_count = doc_del_qs.count()
    doc_del_qs.delete()

    # Delete hospitals not used by kept doctors
    hosp_del_qs = Hospital.objects.exclude(id__in=keep_hospital_ids)
    hosp_del_count = hosp_del_qs.count()
    hosp_del_qs.delete()

    # Delete invite codes not used by kept users
    invite_del_qs = DoctorInviteCode.objects.exclude(used_by_id__in=keep_user_ids)
    invite_del_count = invite_del_qs.count()
    invite_del_qs.delete()

    # Delete users except keep
    user_del_qs = User.objects.exclude(id__in=keep_user_ids)
    user_del_count = user_del_qs.count()
    user_del_qs.delete()

    # Cleanup verification/password codes
    vc_del = VerificationCode.objects.all().delete()
    prc_del = PasswordResetCode.objects.all().delete()

print('\n=== ACTIONS ===')
print('Deleted appointments:', appt_del_count)
print('Deleted doctor records:', doc_del_count)
print('Deleted hospitals:', hosp_del_count)
print('Deleted invite codes:', invite_del_count)
print('Deleted users:', user_del_count)
print('Deleted verification codes:', vc_del[0])
print('Deleted password reset codes:', prc_del[0])

print('\n=== AFTER ===')
summarize()

print('\nKept users:')
for u in User.objects.all():
    print('-', u.username, ' (is_staff=' + str(u.is_staff) + ')')

print('\nKept doctors:')
for d in Doctor.objects.all():
    print('-', d.id, d.full_name, 'user=', d.user.username if d.user else None)

print('\nDone.')
