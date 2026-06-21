from django.contrib.auth import get_user_model
User = get_user_model()

# Reset Doctors by username prefix
doctors = User.objects.filter(username__startswith='doctor_')
count = 0
for d in doctors:
    d.set_password('DoctorMedqueue123!')
    d.save()
    count += 1
print(f"Set passwords for {count} doctors to DoctorMedqueue123!")
