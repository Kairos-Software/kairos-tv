"""
Ayudas para las pantallas de canales.

    {% load canales_extras %}
    {{ canal.nombre|iniciales }}   -> 'Canal 26' -> 'C2' (lo que muestra la app si no hay logo)
"""

from django import template

register = template.Library()


@register.filter
def iniciales(nombre):
    return ''.join(palabra[0] for palabra in (nombre or '').split()[:2]).upper() or '?'


# Cuántas señales tienen problemas (la barra de Contenido lo muestra en todas las pantallas: se guarda un rato)
_CLAVE_CUENTA_SENALES = 'canales:senales_con_problemas'
SEGUNDOS_CUENTA_SENALES = 120


@register.inclusion_tag('canales/_barra_contenido.html', takes_context=True)
def barra_contenido(context, activa=''):
    """
    La barra de arriba de todas las pantallas de Contenido: ir de una a otra en un clic (Organizar, Señales,
    Para revisar, Importar...). `activa`: la clave de la pantalla en la que se está.
        {% load canales_extras %}{% barra_contenido 'senales' %}
    """
    from django.core.cache import cache

    from canales import senales

    cuenta = cache.get(_CLAVE_CUENTA_SENALES)
    if cuenta is None:
        cuenta = senales.contar()
        cache.set(_CLAVE_CUENTA_SENALES, cuenta, SEGUNDOS_CUENTA_SENALES)
    permisos = context.get('permisos') or ()
    return {'activa': activa, 'senales_con_problemas': cuenta, 'puede_importar': 'importar_canales' in permisos,
            'ver_estadisticas': 'ver_estadisticas' in permisos}
