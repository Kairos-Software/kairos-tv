"""
El instalador para PC del analizador de canales (VersionAnalizador): subirlo, publicarlo y quién lo puede bajar.

Subir y publicar es lo mismo que con la app para PC: de a pedazos de 20 MB (descargas/instaladores.py).

Bajar:
  - un superusuario, desde el panel (views.py);
  - un analizador instalado, para actualizarse solo (api/v1/analizador.py). Se presenta con la huella del instalador
    del que salió (la escribe el instalador: instalador_sha256.txt). Solo la tiene quien bajó un instalador del panel,
    que solo pueden bajar los superusuarios, y no se puede adivinar. Además dice su número de instalación: así cada
    PC aparece en el panel (PcConAnalizador) y se la puede desconectar.
"""

import re

from django.db import IntegrityError
from django.utils import timezone

from . import instaladores
from .instaladores import Problema  # noqa: F401  (las vistas y la API lo usan desde acá)
from .models import PcConAnalizador, VersionAnalizador

_HUELLA = re.compile(r'[0-9a-f]{64}')
_INSTALACION = re.compile(r'[0-9a-f-]{36}')


def version_del_nombre(nombre):
    """'KairosAnalizador-2026.11.9.1530.exe' -> '2026.11.9.1530' ('' si el nombre no la dice)."""
    return instaladores.version_del_nombre(instaladores.ANALIZADOR, nombre)


def guardar_pedazo(identificador, desde, pedazo):
    return instaladores.guardar_pedazo(instaladores.ANALIZADOR, identificador, desde, pedazo)


def publicar(identificador, version, notas, usuario):
    return instaladores.publicar(instaladores.ANALIZADOR, identificador, version, notas, usuario)


def presentarse(cabeceras):
    """
    El analizador que pregunta (api/v1/analizador.py): revisa su huella y lo anota (o lo actualiza) en la lista de
    PCs. Devuelve su PcConAnalizador; Problema si no se lo deja.
    """
    huella = (cabeceras.get('X-Kairos-Instalador') or '').strip().lower()
    instalacion = (cabeceras.get('X-Kairos-Instalacion') or '').strip().lower()
    if not _HUELLA.fullmatch(huella) or not VersionAnalizador.objects.filter(sha256=huella).exists():
        raise Problema('Este analizador no salió de un instalador del panel: instalalo con uno bajado de '
                       'Descargas → Analizador para PC.')
    if not _INSTALACION.fullmatch(instalacion):
        raise Problema('Falta el número de instalación del analizador.')
    datos = {'nombre': (cabeceras.get('X-Kairos-Pc') or 'PC').strip()[:100] or 'PC',
             'version': (cabeceras.get('X-Kairos-Version') or '').strip()[:30], 'ultima_vez': timezone.now()}
    try:
        pc, nueva = PcConAnalizador.objects.get_or_create(instalacion=instalacion, defaults=datos)
    except IntegrityError:   # dos pedidos a la vez de la misma PC nueva
        pc, nueva = PcConAnalizador.objects.get(instalacion=instalacion), False
    if pc.desconectada:
        raise Problema('Esta PC fue desconectada desde el panel: ya no recibe versiones nuevas.')
    if not nueva:
        PcConAnalizador.objects.filter(pk=pc.pk).update(**datos)
    return pc


def al_dia(pc, ultima):
    """¿Tiene la última versión publicada?"""
    if ultima is None:
        return True
    try:
        return tuple(int(parte) for parte in pc.version.split('.')) >= ultima.numero
    except ValueError:
        return False
