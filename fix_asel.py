from appointments.models import User, UserSubscription
users = User.objects.filter(first_name__icontains='асель')
for u in users:
    UserSubscription.objects.filter(user=u).delete()
    print(f"Removed subscriptions for {u.username}")
