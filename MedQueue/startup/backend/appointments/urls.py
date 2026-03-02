from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    HospitalViewSet, AppointmentViewSet,
    doctor_me, doctor_appointments, doctor_update_appointment,
    admin_stats, admin_hospitals, admin_doctors, admin_doctor_detail,
    admin_invite_codes, admin_invite_code_detail, admin_users,
)
from . import auth_views

router = DefaultRouter()
router.register(r'hospitals', HospitalViewSet, basename='hospital')
router.register(r'appointments', AppointmentViewSet, basename='appointment')

urlpatterns = [
    path('', include(router.urls)),
    path('auth/register/', auth_views.register_user),
    path('auth/verify/', auth_views.verify_email),
    path('auth/login/', auth_views.login_user),
    path('auth/resend/', auth_views.resend_code),
    path('auth/validate-doctor-code/', auth_views.validate_doctor_code),
    path('auth/password-reset/', auth_views.password_reset_request),
    path('auth/password-reset/confirm/', auth_views.password_reset_confirm),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('ai/chat/', auth_views.ai_chat),
    # Doctor portal
    path('doctor/me/', doctor_me),
    path('doctor/appointments/', doctor_appointments),
    path('doctor/appointments/<int:appointment_id>/', doctor_update_appointment),
    # Admin panel
    path('admin/stats/', admin_stats),
    path('admin/hospitals/', admin_hospitals),
    path('admin/doctors/', admin_doctors),
    path('admin/doctors/<int:doctor_id>/', admin_doctor_detail),
    path('admin/invite-codes/', admin_invite_codes),
    path('admin/invite-codes/<int:code_id>/', admin_invite_code_detail),
    path('admin/users/', admin_users),
]
