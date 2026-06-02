"""
ORM Security Examples: Parameterized Queries vs Raw SQL (OWASP A03 Mitigation)

This file contains production-ready design examples of secure database access
patterns that prevent SQL Injection (OWASP A03) in Django.
"""

from django.contrib.auth.models import User
from django.db import connection
from .models import Appointment, Doctor, Hospital

# =====================================================================
# 1. SECURE DATABASE ACCESS (Using Django ORM with auto-parameterization)
# =====================================================================

def get_user_appointments_secure(user_id: int):
    """
    SECURE: Django ORM filter() automatically parameterizes parameters.
    The database driver executes:
        SELECT * FROM appointments_appointment WHERE user_id = %s;
    with user_id passed as a separate query parameter. SQL Injection is impossible.
    """
    return Appointment.objects.filter(user_id=user_id)


def search_doctors_secure(specialty_query: str, hospital_name_query: str):
    """
    SECURE: Using Django Q-objects and filter. All string parameters are escaped
    properly before query execution.
    """
    return Doctor.objects.filter(
        specialty__icontains=specialty_query,
        hospital__name__icontains=hospital_name_query,
        is_active=True
    ).select_related('hospital')


def update_appointment_status_secure(appointment_id: int, new_status: str):
    """
    SECURE: Using ORM update() or save(). Parameter types and values are sanitised.
    """
    Appointment.objects.filter(id=appointment_id).update(
        status=new_status,
        updated_at=connection.ops.value_to_db_datetime(connection.timezone.now()) if hasattr(connection.ops, 'value_to_db_datetime') else connection.timezone.now()
    )


# =====================================================================
# 2. UNSAFE VS SECURE COMPARISONS (Educational reference)
# =====================================================================

def unsafe_login_raw_sql(email_input: str, password_hash: str):
    """
    UNSAFE (Vulnerable to SQL Injection):
    If email_input is: admin@medqueue.kz' OR 1=1; --
    The query becomes:
        SELECT * FROM auth_user WHERE email = 'admin@medqueue.kz' OR 1=1; --' AND password = ...
    This logs the attacker in as the first user in the DB without a valid password.
    """
    # DO NOT USE THIS PATTERN:
    query = f"SELECT * FROM auth_user WHERE email = '{email_input}' AND password = '{password_hash}'"
    with connection.cursor() as cursor:
        cursor.execute(query) # VULNERABLE
        return cursor.fetchone()


def secure_login_raw_sql_fallback(email_input: str, password_hash: str):
    """
    SECURE (If raw SQL is absolutely necessary, always parameterize):
    By passing inputs inside a list/tuple as the second argument to execute(),
    the database adapter enforces parameter escaping.
    """
    query = "SELECT * FROM auth_user WHERE email = %s AND password = %s"
    with connection.cursor() as cursor:
        cursor.execute(query, [email_input, password_hash]) # SECURE
        return cursor.fetchone()


def secure_login_orm(email_input: str):
    """
    RECOMMENDED SECURE ORM WAY:
    No SQL, no raw syntax. Django handles execution safely.
    """
    try:
        return User.objects.get(email__iexact=email_input)
    except User.DoesNotExist:
        return None
