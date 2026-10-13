from django.urls import path

from . import views

app_name = 'core'

urlpatterns = [
    path('', views.inicio, name='inicio'),
    path('sistema/mantenimiento/', views.mantenimiento_config, name='mantenimiento'),
    path('sistema/herramientas/', views.herramientas, name='herramientas'),
    path('sistema/trabajos/', views.trabajos_en_curso, name='trabajos'),
    path('sistema/mantenimiento/vista-previa/', views.mantenimiento_vista_previa, name='mantenimiento_vista_previa'),
]
