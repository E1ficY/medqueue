from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import HospitalViewSet, AppointmentViewSet
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
]
