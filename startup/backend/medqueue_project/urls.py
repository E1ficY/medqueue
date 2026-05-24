from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView, TemplateView
from django.conf import settings
from django.conf.urls.static import static

AUTH_PAGE_CONTEXT = {
    'turnstile_site_key': settings.TURNSTILE_SITE_KEY,
}
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

urlpatterns = [
    path('', RedirectView.as_view(url='/main.html', permanent=False)),
    path('favicon.ico', RedirectView.as_view(url='/images/favicon.svg', permanent=False)),
    path('main.html', TemplateView.as_view(template_name='main.html')),
    path('doctors.html', TemplateView.as_view(template_name='doctors.html')),
    path('recording.html', TemplateView.as_view(template_name='recording.html')),
    path('profile.html', TemplateView.as_view(template_name='profile.html')),
    path('contacts and about.html', TemplateView.as_view(template_name='contacts and about.html')),
    path('auth.html', TemplateView.as_view(template_name='auth.html', extra_context=AUTH_PAGE_CONTEXT)),
    path('hospital.html', TemplateView.as_view(template_name='hospital.html')),
    path('doctor.html', TemplateView.as_view(template_name='doctor.html')),
    path('admin-panel.html', TemplateView.as_view(template_name='admin-panel.html')),
    path('subscription.html', TemplateView.as_view(template_name='subscription.html')),
    path('admin/', admin.site.urls),
    path('api/schema/', SpectacularAPIView.as_view(), name='api-schema'),
    path('api/docs/swagger/', SpectacularSwaggerView.as_view(url_name='api-schema'), name='swagger-ui'),
    path('api/docs/redoc/', SpectacularRedocView.as_view(url_name='api-schema'), name='redoc-ui'),
    path('api/', include('appointments.urls')),
]

if settings.DEBUG:
    urlpatterns += static('/css/', document_root=settings.FRONTEND_DIR / 'css')
    urlpatterns += static('/js/', document_root=settings.FRONTEND_DIR / 'js')
    urlpatterns += static('/images/', document_root=settings.FRONTEND_DIR / 'images')
    urlpatterns += static('/video/', document_root=settings.FRONTEND_DIR / 'video')
