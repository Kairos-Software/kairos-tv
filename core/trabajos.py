"""
Los trabajos pesados en curso (capa Base).

Probar una lista, cargarla o volver a verificar todas las fuentes lleva
mucho (a veces horas) y le pide mucho al servidor. Para que nadie empiece
otro sin saber que ya hay uno corriendo:

  - Cada tanda de un trabajo pide su TURNO (`turno`): si hay OTRO trabajo
    pesado corriendo, espera (la pantalla vuelve a pedir en unos segundos,
    como cuando dos pestañas procesan la misma lista); si no, sigue y queda
    anotado como "en curso".
  - Todos los que entran al panel, en cualquier navegador o aparato, ven
    arriba qué está corriendo, quién lo empezó y cuánto va (`en_curso`,
    parciales/_trabajos.html, que se actualiza solo).
  - Si un trabajo deja de avisar (cerraron la pestaña, se cortó internet),
    a los pocos minutos se da por cortado y deja de frenar a los demás.

    otro = trabajos.turno('importacion:7', 'Probando la lista «x.m3u»', usuario, url)
    if otro: ...esperar (otro.titulo)...
    trabajos.avance('importacion:7', 45, '1.230 de 2.700')
    trabajos.terminar('importacion:7')
"""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import Trabajo

# Si una tanda no avisa en este tiempo, el trabajo se da por cortado. Una
# tanda tarda como mucho ~1 minuto (canales.servicios.SEGUNDOS_POR_LOTE).
MARGEN = timedelta(minutes=3)

# Una fila que nunca está "en curso": se bloquea para que dos trabajos que
# arrancan al mismo tiempo no pasen los dos (uno espera al otro).
_TURNO = '__turno__'


def en_curso():
    """Los trabajos que están corriendo ahora, del más viejo al más nuevo."""
    return Trabajo.objects.filter(vence__gt=timezone.now()).exclude(clave=_TURNO).select_related('usuario')


def turno(clave, titulo, usuario=None, url='', margen=MARGEN):
    """
    El trabajo `clave` quiere seguir. Si hay OTRO corriendo, lo devuelve (hay
    que esperar). Si no, lo anota como en curso (o le renueva el plazo) y
    devuelve None.
    """
    ahora = timezone.now()
    with transaction.atomic():
        Trabajo.objects.get_or_create(clave=_TURNO, defaults={'titulo': '', 'vence': ahora - timedelta(days=1)})
        Trabajo.objects.select_for_update().get(clave=_TURNO)
        otro = en_curso().exclude(clave=clave).first()
        if otro:
            return otro
        anotar(clave, titulo, usuario, url, margen)
    return None


def anotar(clave, titulo, usuario=None, url='', margen=MARGEN):
    """
    Lo anota como en curso sin esperar a nadie. Lo usa lo que corre solo en
    el servidor (la verificación programada): no puede esperar, pero que se vea
    y que los trabajos del panel esperen a que termine.
    """
    ahora = timezone.now()
    trabajo, creado = Trabajo.objects.get_or_create(
        clave=clave,
        defaults={'titulo': titulo[:150], 'usuario': _usuario(usuario), 'url': url[:300], 'vence': ahora + margen},
    )
    if not creado:
        if trabajo.vence <= ahora:   # se había cortado: vuelve a empezar
            trabajo.empezado = ahora
            trabajo.porcentaje, trabajo.detalle = 0, ''
        trabajo.titulo, trabajo.url, trabajo.vence = titulo[:150], url[:300], ahora + margen
        trabajo.usuario = _usuario(usuario) or trabajo.usuario
        trabajo.save()


def avance(clave, porcentaje, detalle='', margen=MARGEN):
    """Cuánto va (y que sigue vivo)."""
    # Un trabajo cancelado queda con el plazo vencido. La respuesta de una
    # tanda que ya estaba dentro del servidor no debe volver a activarlo.
    Trabajo.objects.filter(clave=clave, vence__gt=timezone.now()).update(
        porcentaje=max(0, min(100, int(porcentaje))), detalle=detalle[:150], vence=timezone.now() + margen,
    )


def cancelar(clave):
    """Marca un trabajo para que la tanda que está corriendo se detenga."""
    # Borrarlo también evita que una respuesta de una versión anterior del
    # servidor (todavía terminando durante un despliegue) pueda reactivarlo.
    return Trabajo.objects.filter(clave=clave).delete()


def cancelado(clave):
    """Si el trabajo fue cancelado (o ya no existe)."""
    return not Trabajo.objects.filter(clave=clave, vence__gt=timezone.now()).exists()


def terminar(clave):
    Trabajo.objects.filter(clave=clave).delete()


def como_dato(trabajo):
    """Para la pantalla (JSON)."""
    quien = trabajo.usuario.get_full_name() or trabajo.usuario.username if trabajo.usuario else 'el servidor'
    return {
        'clave': trabajo.clave,
        'titulo': trabajo.titulo,
        'detalle': trabajo.detalle,
        'porcentaje': trabajo.porcentaje,
        'url': trabajo.url,
        'quien': quien,
        'desde': timezone.localtime(trabajo.empezado).strftime('%H:%M'),
    }


def _usuario(usuario):
    return usuario if getattr(usuario, 'pk', None) else None
