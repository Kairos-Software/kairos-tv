from django.contrib import admin

from .models import PcConAnalizador, VersionAnalizador, VersionApp


@admin.register(VersionApp)
class VersionAppAdmin(admin.ModelAdmin):
    list_display = ['version', 'publicada', 'subida', 'subida_por']
    list_filter = ['publicada']


@admin.register(VersionAnalizador)
class VersionAnalizadorAdmin(admin.ModelAdmin):
    list_display = ['version', 'publicada', 'tamanio', 'subida', 'subida_por']
    list_filter = ['publicada']
    readonly_fields = ['sha256', 'tamanio']


@admin.register(PcConAnalizador)
class PcConAnalizadorAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'version', 'ultima_vez', 'desconectada']
    list_filter = ['desconectada']
