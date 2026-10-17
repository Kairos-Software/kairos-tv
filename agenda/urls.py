from django.urls import path

from . import views

app_name = 'agenda'

urlpatterns = [
    path('', views.lista, name='lista'),
    path('nuevo/', views.editar, name='nuevo'),
    path('<int:pk>/', views.editar, name='editar'),
    path('<int:pk>/eliminar/', views.eliminar, name='eliminar'),
]
