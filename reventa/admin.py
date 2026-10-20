"""
Vista técnica en /admin/ (para revisar datos). La operación del día a día
va por el panel: los créditos se mueven SOLO con reventa/servicios.py, por
eso la libreta y las renovaciones acá son de solo lectura.
"""

from django.contrib import admin

from .models import Cliente, Compra, CreditoCliente, Demo, Movimiento, Paquete, Pantalla, Renovacion, Revendedor


class SoloLectura(admin.ModelAdmin):
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Revendedor)
class RevendedorAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'precio_pantalla', 'saldo']
    search_fields = ['usuario__username', 'usuario__first_name', 'usuario__last_name']
    raw_id_fields = ['usuario']


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'revendedor', 'codigo', 'vence', 'suspendido']
    list_filter = ['suspendido', 'revendedor']
    search_fields = ['nombre', 'telefono', 'codigo']
    readonly_fields = ['codigo', 'vence', 'demo_hasta']


@admin.register(Demo)
class DemoAdmin(SoloLectura):
    list_display = ['cliente', 'cantidad', 'desde', 'hasta', 'hecha_por']
    search_fields = ['cliente__nombre']


@admin.register(Paquete)
class PaqueteAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'creditos', 'precio', 'activo']


@admin.register(Compra)
class CompraAdmin(SoloLectura):
    list_display = ['revendedor', 'creditos', 'precio', 'estado', 'creada', 'resuelta']
    list_filter = ['estado']


@admin.register(Renovacion)
class RenovacionAdmin(SoloLectura):
    list_display = ['cliente', 'pantallas', 'creditos', 'desde', 'hasta']


@admin.register(Movimiento)
class MovimientoAdmin(SoloLectura):
    list_display = ['fecha', 'revendedor', 'cantidad', 'tipo', 'detalle', 'hecho_por']
    list_filter = ['tipo', 'revendedor']


@admin.register(Pantalla)
class PantallaAdmin(admin.ModelAdmin):
    list_display = ['cliente', 'numero', 'nombre', 'titular', 'codigo', 'cortada']
    list_filter = ['cortada']
    search_fields = ['cliente__nombre', 'nombre', 'titular', 'codigo']
    readonly_fields = ['codigo']


@admin.register(CreditoCliente)
class CreditoClienteAdmin(SoloLectura):
    list_display = ['fecha', 'cliente', 'cantidad', 'tipo', 'revendedor', 'cortesia', 'monto_cobrado', 'hecho_por']
    list_filter = ['tipo', 'cortesia']
