from django.urls import path

from . import views

app_name = 'canales'

urlpatterns = [
    path('', views.inicio, name='inicio'),
    path('verificar/lote/', views.verificar_lote, name='verificar_lote'),
    path('importaciones/<int:pk>/', views.importacion, name='importacion'),
    path('importaciones/<int:pk>/lote/', views.importacion_lote, name='importacion_lote'),
    path('importaciones/<int:pk>/cargar/', views.importacion_cargar, name='importacion_cargar'),
    path('importaciones/<int:pk>/reintentar/', views.importacion_reintentar, name='importacion_reintentar'),
    path('importaciones/<int:pk>/elegir/', views.importacion_elegir, name='importacion_elegir'),
    path('importaciones/<int:pk>/borrar/', views.importacion_borrar, name='importacion_borrar'),
    path('catalogo/', views.catalogo, name='catalogo'),
    path('series/', views.series, name='series'),
    path('como-en-la-app/', views.como_en_la_app, name='como_en_la_app'),
    path('organizar/', views.organizar_contenido, name='organizar'),
    path('organizar/editar/', views.organizar_editar, name='organizar_editar'),
    path('organizar/eliminar/', views.organizar_eliminar, name='organizar_eliminar'),
    path('organizar/exportar/', views.organizar_exportar, name='organizar_exportar'),
    path('eliminados/', views.eliminados, name='eliminados'),
    path('series/detalle/', views.serie_detalle, name='serie_detalle'),
    path('series/ordenar/', views.serie_ordenar, name='serie_ordenar'),
    path('canal/<int:pk>/editar/', views.canal_editar, name='canal_editar'),
    path('probar/', views.probar, name='probar'),
    path('youtube/', views.traer_de_youtube, name='youtube'),
    path('lo-mas-visto/', views.lo_mas_visto, name='lo_mas_visto'),
    path('limpiar-nombres/', views.limpiar_nombres, name='limpiar_nombres'),
    path('catalogo/quitar/', views.catalogo_quitar, name='catalogo_quitar'),
    path('catalogo/mostrar/', views.catalogo_mostrar, name='catalogo_mostrar'),
    path('catalogo/categoria/', views.catalogo_categoria, name='catalogo_categoria'),
    path('catalogo/tipo/', views.catalogo_contenido, name='catalogo_contenido'),
    path('series/acciones/', views.series_acciones, name='series_acciones'),
    path('categorias/', views.categorias, name='categorias'),
    path('secciones/', views.secciones_acciones, name='secciones'),
]
