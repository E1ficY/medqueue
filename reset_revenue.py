from appointments.models import PaymentTransaction
deleted_count, _ = PaymentTransaction.objects.all().delete()
print(f"Deleted {deleted_count} payment transactions. Revenue is now 0.")
