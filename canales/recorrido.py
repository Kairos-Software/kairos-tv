"""
El MODO REVISIÓN de la app: un aparato (una TV o un celular viejo, en una
casa) que recorre los canales solo, de a uno, y cuenta cuáles andan.

Sirve para lo que el servidor NO puede probar: los paneles Xtream bloquean
las IP de los servidores (el VPS anota "?"), pero desde una casa entregan la
señal como a un cliente. Es la misma prueba que hacer a mano con VLC, para
todos los canales, sin que nadie tenga que mirarlos.

    pendientes(cantidad)   -> las próximas fuentes que conviene probar
    anotar(resultados)     -> lo que encontró el aparato, a la memoria (salud.py)

Qué se prueba primero:
  1. En vivo antes que películas y series (secciones "en vivo" incluidas).
  2. Lo que quitó o retiró la limpieza (canales enteros o señales sueltas: si
     anda, vuelve a la app en el momento).
  3. Lo que está fallando (falla o lo rechaza el proveedor).
  4. Lo que nadie vio nunca ("Sin datos").
  5. Lo demás, lo probado hace más tiempo primero.
No se prueba lo que un cliente vio andar hace poco (VISTO_HACE_POCO), ni lo
que ya probó el modo revisión en las últimas DESCANSO horas, ni lo apagado a
mano, ni lo quitado a mano. Tampoco YouTube ni páginas de video: esas el
servidor sí las puede probar.
"""

from datetime import timedelta

from django.db.models import Case, F, IntegerField, Q, Value, When
from django.utils import timezone

from . import salud
from .models import Contenido, Fuente, Seccion

TIPOS_DEL_RECORRIDO = [Fuente.Tipo.HLS, Fuente.Tipo.DASH, Fuente.Tipo.DIRECTO, Fuente.Tipo.RTSP]
DESCANSO = timedelta(hours=20)
VISTO_HACE_POCO = timedelta(hours=12)
MAXIMO_POR_PEDIDO = 50


def secciones_en_vivo():
    return [Contenido.VIVO, *Seccion.objects.filter(forma=Seccion.Forma.VIVO).values_list('clave', flat=True)]


def _candidatas(ahora, tipos=None):
    tipos = [t for t in (tipos or TIPOS_DEL_RECORRIDO) if t in TIPOS_DEL_RECORRIDO]
    return (Fuente.objects.filter(Q(activa=True) | Q(retirada__isnull=False), tipo__in=tipos,
                                  canal__eliminado_en__isnull=True)
            .filter(Q(canal__activo=True) | Q(canal__motivo_quitado__startswith=salud.QUITADO_POR_LA_LIMPIEZA))
            .exclude(recorrida__gt=ahora - DESCANSO)
            .exclude(anduvo__gt=ahora - VISTO_HACE_POCO))


def pendientes(cantidad=20, tipos=None, ahora=None):
    """Las próximas fuentes para probar, en orden (ver arriba), con su canal."""
    ahora = ahora or timezone.now()
    cantidad = max(1, min(int(cantidad), MAXIMO_POR_PEDIDO))
    return list(
        _candidatas(ahora, tipos).select_related('canal').annotate(
            seccion=Case(When(canal__contenido__in=secciones_en_vivo(), then=Value(0)), default=Value(1),
                         output_field=IntegerField()),
            urgencia=Case(
                When(Q(canal__activo=False) | Q(retirada__isnull=False), then=Value(0)),
                When(fallas_seguidas__gt=0, then=Value(1)),
                When(anduvo__isnull=True, then=Value(2)),
                default=Value(3), output_field=IntegerField(),
            ),
        ).order_by('seccion', 'urgencia', F('recorrida').asc(nulls_first=True), F('anduvo').asc(nulls_first=True),
                   'pk')[:cantidad]
    )


def cuantas_quedan(tipos=None, ahora=None):
    return _candidatas(ahora or timezone.now(), tipos).count()


def anotar(resultados, ahora=None):
    """
    `resultados`: [{"id": 5, "anduvo": true|false, "motivo": "rechazo", "detalle": "..."}].
    Cada uno se suma a la memoria de su fuente (salud.anotar_del_recorrido).
    Si anduvo una fuente de un canal que había quitado la limpieza, el canal
    vuelve a la app ya. Lo que el aparato no pudo probar por no tener
    internet ("sin_internet") no se anota. Devuelve cuántos anotó.
    """
    ahora = ahora or timezone.now()
    por_id = {}
    for resultado in resultados:
        if not isinstance(resultado, dict) or resultado.get('motivo') == 'sin_internet':
            continue
        try:
            por_id[int(resultado['id'])] = resultado
        except (KeyError, TypeError, ValueError):
            continue
    fuentes = list(Fuente.objects.filter(pk__in=por_id, canal__eliminado_en__isnull=True))
    for fuente in fuentes:
        resultado = por_id[fuente.pk]
        anduvo = resultado.get('anduvo') is True
        salud.anotar_del_recorrido(fuente, anduvo, str(resultado.get('motivo', ''))[:20], ahora)
        fuente.recorrida = ahora
        if anduvo and fuente.estado == Fuente.Estado.CAIDA:
            # El servidor no la podía ver, pero desde una casa anda: que la app la vuelva a intentar
            fuente.estado = Fuente.Estado.SIN_VERIFICAR
    Fuente.objects.bulk_update(fuentes, [*salud.CAMPOS, 'recorrida', 'estado'])
    andan = [f for f in fuentes if por_id[f.pk].get('anduvo') is True]
    if andan:
        salud.devolver_senales(ahora, fuentes=[f.pk for f in andan])
        salud.devolver_los_que_andan(ahora, canales=[f.canal_id for f in andan])
    return len(fuentes)
