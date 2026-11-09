from django.urls import path

from . import views

app_name = 'descargas'

urlpatterns = [
    path('descargar/', views.descargar, name='descargar'),
    path('descargar/<int:pk>/', views.descargar, name='descargar_version'),
    path('app-android/', views.pagina, name='pagina'),
    path('app-android/<int:pk>/publicada/', views.cambiar_publicada, name='cambiar_publicada'),
    # El analizador de canales para PC: solo superusuarios
    path('app-android/analizador/pedazo/', views.analizador_pedazo, name='analizador_pedazo'),
    path('app-android/analizador/publicar/', views.analizador_publicar, name='analizador_publicar'),
    path('app-android/analizador/descargar/', views.analizador_descargar, name='analizador_descargar'),
    path('app-android/analizador/descargar/<int:pk>/', views.analizador_descargar,
         name='analizador_descargar_version'),
    path('app-android/analizador/<int:pk>/publicada/', views.analizador_publicada, name='analizador_publicada'),
    path('app-android/analizador/pc/<int:pk>/', views.analizador_pc, name='analizador_pc'),
]
