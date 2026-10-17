from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path('', include('usuarios.urls')),
    path('actividad/', include('actividad.urls')),
    path('canales/', include('canales.urls')),
    path('reventa/', include('reventa.urls')),
    path('', include('descargas.urls')),   # /descargar/ y /app-android/
    path('notificaciones/', include('notificaciones.urls')),
    path('api/', include('api.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Páginas de error propias (con DEBUG=True Django muestra las suyas de diagnóstico)
handler403 = 'core.views.error_403'
handler404 = 'core.views.error_404'
handler500 = 'core.views.error_500'
