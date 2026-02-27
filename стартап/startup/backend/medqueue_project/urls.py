from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView, TemplateView
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', RedirectView.as_view(url='/main.html', permanent=False)),
    path('main.html', TemplateView.as_view(template_name='main.html')),
    path('recording.html', TemplateView.as_view(template_name='recording.html')),
    path('status.html', TemplateView.as_view(template_name='status.html')),
    path('profile.html', TemplateView.as_view(template_name='profile.html')),
    path('contacts and about.html', TemplateView.as_view(template_name='contacts and about.html')),
    path('auth.html', TemplateView.as_view(template_name='auth.html')),
    path('admin/', admin.site.urls),
    path('api/', include('appointments.urls')),
]

if settings.DEBUG:
    urlpatterns += static('/css/', document_root=settings.FRONTEND_DIR / 'css')
    urlpatterns += static('/js/', document_root=settings.FRONTEND_DIR / 'js')
    urlpatterns += static('/images/', document_root=settings.FRONTEND_DIR / 'images')
    urlpatterns += static('/video/', document_root=settings.FRONTEND_DIR / 'video')
