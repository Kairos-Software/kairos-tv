from django.urls import path

from . import views

app_name = 'reventa'

urlpatterns = [
    path('', views.inicio, name='inicio'),
    path('mi-pantalla/', views.mi_pantalla, name='mi_pantalla'),
    path('estadisticas/', views.ver_estadisticas, name='estadisticas'),
    path('revendedores/', views.revendedores, name='revendedores'),
    path('revendedores/nuevo/', views.revendedor_nuevo, name='revendedor_nuevo'),
    path('revendedores/<int:pk>/', views.revendedor, name='revendedor'),
    path('revendedores/<int:pk>/accion/', views.revendedor_accion, name='revendedor_accion'),
    path('clientes/', views.clientes, name='clientes'),
    path('clientes/nuevo/', views.cliente_nuevo, name='cliente_nuevo'),
    path('clientes/<int:pk>/', views.cliente, name='cliente'),
    path('clientes/<int:pk>/editar/', views.cliente_editar, name='cliente_editar'),
    path('clientes/<int:pk>/activar/', views.cliente_activar, name='cliente_activar'),
    path('clientes/<int:pk>/cargar/', views.cliente_cargar, name='cliente_cargar'),
    path('clientes/<int:pk>/pantallas/agregar/', views.cliente_agregar_pantalla, name='cliente_agregar_pantalla'),
    path('clientes/<int:pk>/pantallas/<int:pantalla>/', views.cliente_pantalla, name='cliente_pantalla'),
    path('clientes/<int:pk>/pasar/', views.cliente_pasar, name='cliente_pasar'),
    path('clientes/<int:pk>/codigo/', views.cliente_codigo, name='cliente_codigo'),
    path('clientes/<int:pk>/liberar/', views.cliente_liberar, name='cliente_liberar'),
    path('creditos/', views.creditos, name='creditos'),
    path('creditos/comprar/', views.pedir_compra, name='pedir_compra'),
    path('creditos/mi-precio/', views.mi_precio, name='mi_precio'),
    path('paquetes/', views.paquetes, name='paquetes'),
    path('paquetes/nuevo/', views.paquete_editar, name='paquete_nuevo'),
    path('paquetes/<int:pk>/', views.paquete_editar, name='paquete_editar'),
    path('compras/', views.compras, name='compras'),
    path('compras/<int:pk>/', views.compra_resolver, name='compra_resolver'),
]
