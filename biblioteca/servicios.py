"""
La biblioteca de cada cuenta: leerla y aplicarle los cambios que manda la app.

    cuenta = cuenta_de(request)        -> {'cliente': c} | {'pantalla': p} | {'usuario': u}
    leer(cuenta)                       -> {'favoritos': [...], 'progresos': [...], 'recientes': [...]}
    aplicar(cuenta, cambios, aparato)  -> lo mismo, ya con los cambios

La app no manda listas enteras: manda CAMBIOS ("agregué este favorito",
"voy por el minuto 43 de esta película"). Así, si la TV y el celular cambian
cosas a la vez (o uno estuvo sin internet), no se pisan: se suman.
"""

from datetime import datetime
from datetime import timezone as tz

from django.db import transaction
from django.utils import timezone

from canales.models import Canal

from .models import Favorito, Progreso, Visto

MAXIMO_FAVORITOS = 500
MAXIMO_PROGRESOS = 60     # como la app
MAXIMO_RECIENTES = 12     # como la app
MINIMO_DE_DURACION = 60   # un vivo o algo muy corto no tiene "por dónde iba" (como la app)


class SinCuenta(Exception):
    """El pedido no es de una cuenta que pueda tener biblioteca."""


def cuenta_de(request):
    """
    De quién es lo que pide la app: un cliente que entró con su código (lo
    comparten sus aparatos), una pantalla con código propio (otra persona) o
    un usuario del panel.
    """
    dispositivo = getattr(request.user, 'dispositivo', None)
    if dispositivo is not None:
        pantalla = dispositivo.pantalla
        if pantalla is not None and pantalla.codigo:
            return {'pantalla': pantalla}
        return {'cliente': dispositivo.cliente}
    if getattr(request.user, 'pk', None):
        return {'usuario': request.user}
    raise SinCuenta()


def _milisegundos(momento):
    return int(momento.timestamp() * 1000)


def _momento(milisegundos):
    """La hora que manda la app (milisegundos), sin pasarse de "ahora" (un reloj adelantado no gana siempre)."""
    try:
        momento = datetime.fromtimestamp(int(milisegundos) / 1000, tz=tz.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return timezone.now()
    return min(momento, timezone.now())


def leer(cuenta):
    return {
        'favoritos': list(Favorito.objects.filter(**cuenta).values_list('clave', flat=True)),
        'progresos': [{'id': p.canal_id, 'p': p.posicion, 'd': p.duracion, 't': _milisegundos(p.cuando),
                       'aparato': p.aparato}
                      for p in Progreso.objects.filter(**cuenta)[:MAXIMO_PROGRESOS]],
        'recientes': [{'id': v.canal_id, 't': _milisegundos(v.cuando), 'aparato': v.aparato}
                      for v in Visto.objects.filter(**cuenta)[:MAXIMO_RECIENTES]],
    }


def _ids_validos(ids):
    """De los ids que manda la app, los de canales que existen (uno borrado o inventado se ignora)."""
    ids = {i for i in ids if isinstance(i, int) and not isinstance(i, bool)}
    return set(Canal.todos.filter(pk__in=ids).values_list('pk', flat=True))


def _lista(cambios, nombre):
    valor = cambios.get(nombre)
    return valor if isinstance(valor, list) else []


@transaction.atomic
def aplicar(cuenta, cambios, aparato=''):
    """
    Aplica los cambios que mandó la app y devuelve la biblioteca como quedó.
    `cambios` (todo opcional):
        agregar:   ["c:12", "s:Pocoyó"]        favoritos nuevos
        quitar:    ["c:12"]                    favoritos que se sacaron
        progresos: [{"id": 5, "p": 2580, "d": 5400, "t": 1760000000000}]
        olvidar:   [5]                         "Continuar viendo" que se sacaron
        vistos:    [{"id": 3, "t": 1760000000000}]
    Si llega un progreso más viejo que el guardado (otro aparato lo siguió
    después), gana el más nuevo.
    """
    aparato = str(aparato or '')[:100]

    quitar = {str(c)[:120] for c in _lista(cambios, 'quitar')}
    Favorito.objects.filter(**cuenta, clave__in=quitar).delete()
    for clave in _lista(cambios, 'agregar'):
        clave = str(clave)[:120]
        if clave and clave not in quitar:
            Favorito.objects.get_or_create(**cuenta, clave=clave)
    sobran = Favorito.objects.filter(**cuenta).order_by('-agregado')[MAXIMO_FAVORITOS:]
    Favorito.objects.filter(pk__in=list(sobran.values_list('pk', flat=True))).delete()

    progresos = [p for p in _lista(cambios, 'progresos') if isinstance(p, dict)]
    validos = _ids_validos([p.get('id') for p in progresos] + _lista(cambios, 'olvidar')
                           + [v.get('id') for v in _lista(cambios, 'vistos') if isinstance(v, dict)])
    Progreso.objects.filter(**cuenta, canal_id__in=validos & set(_lista(cambios, 'olvidar'))).delete()
    for p in progresos:
        try:
            canal, posicion, duracion = p.get('id'), int(p.get('p', 0)), int(p.get('d', 0))
        except (TypeError, ValueError):
            continue
        if canal not in validos or duracion < MINIMO_DE_DURACION or posicion < 0:
            continue
        cuando = _momento(p.get('t'))
        actual = Progreso.objects.filter(**cuenta, canal_id=canal).first()
        if actual is not None and actual.cuando > cuando:
            continue   # otro aparato lo siguió después: gana ese
        Progreso.objects.update_or_create(**cuenta, canal_id=canal, defaults={
            'posicion': min(posicion, duracion), 'duracion': duracion, 'cuando': cuando, 'aparato': aparato})
    _dejar_los_ultimos(Progreso, cuenta, MAXIMO_PROGRESOS)

    for v in _lista(cambios, 'vistos'):
        if not isinstance(v, dict) or v.get('id') not in validos:
            continue
        cuando = _momento(v.get('t'))
        actual = Visto.objects.filter(**cuenta, canal_id=v['id']).first()
        if actual is not None and actual.cuando > cuando:
            continue
        Visto.objects.update_or_create(**cuenta, canal_id=v['id'], defaults={'cuando': cuando, 'aparato': aparato})
    _dejar_los_ultimos(Visto, cuenta, MAXIMO_RECIENTES)

    return leer(cuenta)


def _dejar_los_ultimos(modelo, cuenta, cuantos):
    sobran = modelo.objects.filter(**cuenta).order_by('-cuando').values_list('pk', flat=True)[cuantos:]
    modelo.objects.filter(pk__in=list(sobran)).delete()

