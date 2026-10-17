"""
Qué eventos se muestran y dónde (lo usan el panel y la API de la app).
"""

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from canales.models import Canal, Contenido
from canales import secciones

from .models import DURACION_SIN_FIN, Evento

# La app muestra lo que empieza en estas próximas dos semanas
DIAS_HACIA_ADELANTE = 14


def canales_en_vivo():
    """Los canales que se pueden elegir para un evento: los en vivo y las radios (secciones "en vivo")."""
    vivas = [s.clave for s in secciones.nuevas() if s.forma == Contenido.VIVO]
    return Canal.objects.filter(Q(contenido=Contenido.VIVO) | Q(contenido__in=vivas)).order_by('nombre')


def _que_no_terminaron(eventos, ahora):
    """Los que todavía no terminaron (los sin fin cargado, 2 horas después de empezar)."""
    return eventos.filter(
        Q(termina__gt=ahora) | Q(termina__isnull=True, empieza__gt=ahora - DURACION_SIN_FIN),
    )


def para_la_app(ahora=None):
    """Lo que va a la app: con canal, que no terminó y que empieza en las próximas dos semanas."""
    ahora = ahora or timezone.now()
    eventos = Evento.objects.filter(canal__isnull=False, canal__eliminado_en__isnull=True,
                                    empieza__lt=ahora + timedelta(days=DIAS_HACIA_ADELANTE))
    return _que_no_terminaron(eventos, ahora).select_related('canal')


def para_el_panel(ahora=None, pasados=False):
    """
    Los de la lista del panel. Sin `pasados`: lo que no terminó (lo próximo
    primero). Con `pasados`: lo que ya terminó (lo más reciente primero).
    """
    ahora = ahora or timezone.now()
    eventos = Evento.objects.select_related('canal')
    proximos = _que_no_terminaron(eventos, ahora)
    if not pasados:
        return proximos
    return eventos.exclude(pk__in=proximos.values('pk')).order_by('-empieza')


def en_json(evento):
    """Un evento como lo lee la app (ver api/v1/agenda.py)."""
    return {
        'id': evento.pk,
        'titulo': evento.titulo,
        'detalle': evento.detalle,
        'tipo': evento.tipo,
        'canal': evento.canal_id,
        'empieza': evento.empieza.isoformat(),
        'termina': evento.fin.isoformat(),
    }
