from django.contrib import admin

from .models import Evento


@admin.register(Evento)
class EventoAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'tipo', 'canal', 'empieza', 'termina')
    list_filter = ('tipo',)
    search_fields = ('titulo', 'detalle')
    raw_id_fields = ('canal',)
