"""
Datos de la marca (y, para superusuarios, el aviso de mantenimiento) en todos
los templates. Con sesión iniciada, también los trabajos pesados en curso
(core/trabajos.py, parciales/_trabajos.html).
"""

from django.conf import settings

from . import trabajos
from .mantenimiento import estado_actual


def sistema(request):
    datos = {
        'NOMBRE_SISTEMA': settings.NOMBRE_SISTEMA,
        'NOMBRE_EMPRESA': settings.NOMBRE_EMPRESA,
    }
    usuario = getattr(request, 'user', None)
    if usuario is not None and usuario.is_authenticated:
        datos['trabajos_en_curso'] = [trabajos.como_dato(t) for t in trabajos.en_curso()]
        if usuario.is_superuser:
            # Para mostrarle al superusuario que el sistema está en mantenimiento
            datos['mantenimiento_activo'] = estado_actual()['activo']
    return datos
