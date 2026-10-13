"""
Estadísticas de la reventa (capa Base): números mes a mes, ranking de
revendedores y los de cada cliente.

Todo sale de lo que ya se guarda (compras, renovaciones, la libreta de
créditos): no hay tablas propias de estadísticas, así nunca se desfasan.

    por_mes(revendedor=None, meses=12)   -> filas de los últimos meses
    ranking_revendedores()               -> revendedores ordenados por créditos usados
    numeros_cliente(cliente)             -> lo que pagó, renovaciones, desde cuándo
"""

from datetime import date, datetime, time

from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from . import consultas
from .models import Cliente, Compra, CreditoCliente, Dispositivo, Movimiento, Renovacion, Revendedor

MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre',
         'noviembre', 'diciembre']


def _ultimos_meses(cantidad):
    """[date(2026, 10, 1), date(2026, 9, 1), ...] empezando por el mes actual."""
    hoy = timezone.localdate()
    anio, mes = hoy.year, hoy.month
    resultado = []
    for _ in range(cantidad):
        resultado.append(date(anio, mes, 1))
        mes -= 1
        if mes == 0:
            anio, mes = anio - 1, 12
    return resultado


def _comienzo(mes):
    """date(2026, 10, 1) -> el 1/10/2026 a las 00:00 en la hora de Argentina."""
    return timezone.make_aware(datetime.combine(mes, time.min))


def _por_mes(queryset, campo_fecha, **sumas):
    """{date(primer día del mes): {nombre: valor}} agrupando `queryset` por mes (en la hora local)."""
    filas = queryset.order_by().annotate(mes=TruncMonth(campo_fecha)).values('mes').annotate(**sumas)
    return {timezone.localtime(f['mes']).date(): f for f in filas}


def por_mes(revendedor=None, meses=12):
    """
    Una fila por mes (el actual primero). Con `revendedor`, solo lo suyo; sin
    él, el negocio entero (incluye ingresos por paquetes y clientes directos).
    """
    desde = _comienzo(_ultimos_meses(meses)[-1])

    renovaciones = Renovacion.objects.filter(fecha__gte=desde)
    cargas = CreditoCliente.objects.filter(tipo=CreditoCliente.Tipo.CARGA, fecha__gte=desde)
    compras = Compra.objects.filter(estado=Compra.Estado.PAGADA, resuelta__gte=desde)
    regalos = Movimiento.objects.filter(tipo=Movimiento.Tipo.REGALO, fecha__gte=desde)
    clientes = Cliente.objects.filter(creado__gte=desde)
    if revendedor is not None:
        renovaciones = renovaciones.filter(cliente__revendedor=revendedor)
        cargas = cargas.filter(revendedor=revendedor)
        compras = compras.filter(revendedor=revendedor)
        regalos = regalos.filter(revendedor=revendedor)
        clientes = clientes.filter(revendedor=revendedor)

    datos_renov = _por_mes(renovaciones, 'fecha', renovaciones=Count('pk'), creditos=Sum('creditos'))
    datos_cobrado = _por_mes(cargas, 'fecha', cobrado=Sum('monto_cobrado'))
    datos_directos = _por_mes(cargas.filter(revendedor__isnull=True), 'fecha', cobrado=Sum('monto_cobrado'))
    datos_compras = _por_mes(compras, 'resuelta', compras=Count('pk'), creditos=Sum('creditos'), monto=Sum('precio'))
    datos_regalos = _por_mes(regalos, 'fecha', creditos=Sum('cantidad'))
    datos_clientes = _por_mes(clientes, 'creado', nuevos=Count('pk'))

    filas = []
    for mes in _ultimos_meses(meses):
        r, c = datos_renov.get(mes, {}), datos_compras.get(mes, {})
        fila = {
            'mes': mes,
            'nombre': f'{MESES[mes.month - 1]} {mes.year}',
            'clientes_nuevos': datos_clientes.get(mes, {}).get('nuevos', 0),
            'renovaciones': r.get('renovaciones', 0),
            'creditos_usados': r.get('creditos') or 0,
            'cobrado': datos_cobrado.get(mes, {}).get('cobrado') or 0,   # lo cobrado a clientes (revendedores + empresa)
            'creditos_comprados': c.get('creditos') or 0,
            'invertido': c.get('monto') or 0,                     # para el revendedor: lo que pagó; para el negocio: ingreso
            'creditos_regalados': datos_regalos.get(mes, {}).get('creditos') or 0,
        }
        if revendedor is None:
            fila['cobrado_directos'] = datos_directos.get(mes, {}).get('cobrado') or 0
            fila['ingresos'] = fila['invertido'] + fila['cobrado_directos']
        else:
            fila['ganancia'] = fila['cobrado'] - fila['invertido']
        filas.append(fila)
    return filas


def totales(filas):
    """La suma de las columnas numéricas de `por_mes`."""
    if not filas:
        return {}
    return {clave: sum(f[clave] for f in filas) for clave, valor in filas[0].items()
            if isinstance(valor, (int, float)) or hasattr(valor, 'as_tuple')}


def ranking_revendedores():
    """Cada revendedor con sus números, ordenados por créditos usados (los que más venden primero)."""
    inicio_mes = _comienzo(_ultimos_meses(1)[0])
    filas = []
    for revendedor in Revendedor.objects.select_related('usuario'):
        numeros = consultas.resumen_revendedor(revendedor)
        numeros['revendedor'] = revendedor
        numeros['usados_este_mes'] = -(revendedor.movimientos.filter(
            tipo=Movimiento.Tipo.RENOVACION, fecha__gte=inicio_mes).aggregate(t=Sum('cantidad'))['t'] or 0)
        filas.append(numeros)
    return sorted(filas, key=lambda n: (n['usados'], n['clientes']['vigentes']), reverse=True)


def en_vivo(revendedor=None):
    """Ahora mismo: dispositivos conectados y clientes vigentes."""
    dispositivos = Dispositivo.objects.filter(cliente__eliminado_en__isnull=True)
    if revendedor is not None:
        dispositivos = dispositivos.filter(cliente__revendedor=revendedor)
    return {
        'dispositivos': dispositivos.count(),
        'clientes_mirando': dispositivos.values('cliente').distinct().count(),
    }


def numeros_cliente(cliente):
    renovaciones = cliente.renovaciones.all()
    agregados = renovaciones.aggregate(creditos=Sum('creditos'), cantidad=Count('pk'))
    cobrado = cliente.creditos.filter(tipo=CreditoCliente.Tipo.CARGA).aggregate(t=Sum('monto_cobrado'))['t']
    primera = renovaciones.order_by('desde').first()
    return {
        'cobrado': cobrado or 0,
        'creditos': agregados['creditos'] or 0,
        'renovaciones': agregados['cantidad'],
        'activo_desde': primera.desde if primera else None,
    }
