"""
Lo que el sistema BUSCA de la reventa (capa Base): saldos, clientes y los
números de cada revendedor y del negocio entero.
"""

from datetime import timedelta

from django.db.models import Count, OuterRef, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import Cliente, Compra, CreditoCliente, Movimiento, Pantalla, Revendedor

DIAS_POR_VENCER = 7


def _suma(queryset, campo):
    return queryset.aggregate(total=Sum(campo))['total'] or 0


def clientes_de(revendedor=None):
    """
    Los clientes de un revendedor (o todos, para el administrador), con
    `dispositivos_hoy`: sus pantallas habilitadas (None si no tiene). Las
    tablas lo muestran solo si está vigente.
    """
    hoy = (Pantalla.objects.filter(cliente=OuterRef('pk'), cortada=False).order_by()
           .values('cliente').annotate(total=Count('pk')).values('total'))
    clientes = Cliente.objects.select_related('revendedor__usuario').annotate(dispositivos_hoy=Subquery(hoy))
    return clientes.filter(revendedor=revendedor) if revendedor else clientes


def filtrar_clientes(clientes, estado=''):
    """estado: 'vigentes', 'por_vencer', 'vencidos', 'sin_activar', 'suspendidos', 'en_prueba' o '' (todos)."""
    ahora = timezone.now()
    if estado == 'en_prueba':   # usando una demo ahora (sin el servicio pago activo)
        return clientes.filter(suspendido=False, demo_hasta__gt=ahora).exclude(vence__gt=ahora)
    if estado == 'vigentes':
        return clientes.filter(suspendido=False, vence__gt=ahora)
    if estado == 'por_vencer':
        return clientes.filter(suspendido=False, vence__gt=ahora, vence__lte=ahora + timedelta(days=DIAS_POR_VENCER))
    if estado == 'vencidos':
        return clientes.filter(vence__lte=ahora)
    if estado == 'sin_activar':
        return clientes.filter(vence__isnull=True)
    if estado == 'suspendidos':
        return clientes.filter(suspendido=True)
    return clientes


def _conteo_clientes(clientes):
    return {estado: filtrar_clientes(clientes, estado).count()
            for estado in ('vigentes', 'por_vencer', 'vencidos', 'sin_activar', 'suspendidos')} | {
        'total': clientes.count()}


def resumen_revendedor(revendedor):
    """Créditos, clientes y plata de un revendedor."""
    movimientos = revendedor.movimientos.all()
    cobrado = _suma(CreditoCliente.objects.filter(revendedor=revendedor), 'monto_cobrado')
    invertido = _suma(revendedor.compras.filter(estado=Compra.Estado.PAGADA), 'precio')
    return {
        'saldo': _suma(movimientos, 'cantidad'),
        'comprados': _suma(movimientos.filter(tipo=Movimiento.Tipo.COMPRA), 'cantidad'),
        'regalados': _suma(movimientos.filter(tipo=Movimiento.Tipo.REGALO), 'cantidad'),
        'usados': -_suma(movimientos.filter(tipo=Movimiento.Tipo.RENOVACION), 'cantidad'),
        'ajustes': _suma(movimientos.filter(tipo=Movimiento.Tipo.AJUSTE), 'cantidad'),
        'clientes': _conteo_clientes(clientes_de(revendedor)),
        'cobrado': cobrado,
        'invertido': invertido,
        'ganancia': cobrado - invertido,
        'compras_pendientes': revendedor.compras.filter(estado=Compra.Estado.PENDIENTE).count(),
    }


def resumen_general():
    """Los números del negocio entero (para el administrador)."""
    pagadas = Compra.objects.filter(estado=Compra.Estado.PAGADA)
    movimientos = Movimiento.objects.filter(revendedor__eliminado_en__isnull=True)
    # Lo que cobró la empresa a clientes con créditos propios (directos, o cargas "de la empresa")
    de_la_empresa = CreditoCliente.objects.filter(tipo=CreditoCliente.Tipo.CARGA, revendedor__isnull=True)
    return {
        'revendedores': Revendedor.objects.count(),
        'ingresos': _suma(pagadas, 'precio') + _suma(de_la_empresa, 'monto_cobrado'),
        'ingresos_paquetes': _suma(pagadas, 'precio'),
        'ingresos_directos': _suma(de_la_empresa, 'monto_cobrado'),
        'creditos_de_la_empresa': _suma(de_la_empresa, 'cantidad'),
        'creditos_vendidos': _suma(pagadas, 'creditos'),
        'creditos_regalados': _suma(movimientos.filter(tipo=Movimiento.Tipo.REGALO), 'cantidad'),
        'creditos_usados': -_suma(movimientos.filter(tipo=Movimiento.Tipo.RENOVACION), 'cantidad'),
        'creditos_sin_usar': _suma(movimientos, 'cantidad'),
        'clientes': _conteo_clientes(clientes_de()),
        'compras_pendientes': Compra.objects.filter(estado=Compra.Estado.PENDIENTE).count(),
    }


def revendedores_con_numeros():
    """
    Revendedores con `saldo_actual` y `clientes_vigentes` ya calculados (para
    la lista). Van como subconsultas separadas: si se hicieran las dos con
    JOIN en la misma consulta, cada movimiento se contaría una vez por cliente.
    """
    ahora = timezone.now()
    saldo = (Movimiento.objects.filter(revendedor=OuterRef('pk')).order_by()
             .values('revendedor').annotate(total=Sum('cantidad')).values('total'))
    vigentes = (Cliente.objects.filter(revendedor=OuterRef('pk'), suspendido=False, vence__gt=ahora).order_by()
                .values('revendedor').annotate(total=Count('pk')).values('total'))
    return (
        Revendedor.objects.select_related('usuario')
        .annotate(saldo_actual=Coalesce(Subquery(saldo), 0), clientes_vigentes=Coalesce(Subquery(vigentes), 0))
    )
