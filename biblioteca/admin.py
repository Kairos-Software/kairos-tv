from django.contrib import admin

from .models import Favorito, Progreso, Visto


@admin.register(Favorito)
class FavoritoAdmin(admin.ModelAdmin):
    list_display = ('clave', 'cliente', 'pantalla', 'usuario', 'agregado')
    raw_id_fields = ('cliente', 'pantalla', 'usuario')


@admin.register(Progreso)
class ProgresoAdmin(admin.ModelAdmin):
    list_display = ('canal', 'posicion', 'duracion', 'cliente', 'pantalla', 'usuario', 'aparato', 'cuando')
    raw_id_fields = ('cliente', 'pantalla', 'usuario', 'canal')


@admin.register(Visto)
class VistoAdmin(admin.ModelAdmin):
    list_display = ('canal', 'cliente', 'pantalla', 'usuario', 'aparato', 'cuando')
    raw_id_fields = ('cliente', 'pantalla', 'usuario', 'canal')
