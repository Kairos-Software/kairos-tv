"""
El instalador para PC del analizador de canales (VersionAnalizador): subirlo, publicarlo y quién lo puede bajar.

Subir: pesa unos cientos de MB y nginx acepta hasta 160 MB por pedido, así que la página lo manda de a pedazos de
20 MB (static/js/subir_analizador.js). guardar_pedazo() los junta en privado/analizador/subiendo/ y publicar() revisa
que sea un programa de Windows, calcula su huella (SHA-256) y lo deja como una versión nueva. Si se corta, se vuelve
a mandar el pedazo que faltó: nunca queda una versión a medias.

Bajar:
  - un superusuario, desde el panel (views.py);
  - un analizador instalado, para actualizarse solo (api/v1/analizador.py). Se presenta con la huella del instalador
    del que salió (la escribe el instalador: instalador_sha256.txt). Solo la tiene quien bajó un instalador del panel,
    que solo pueden bajar los superusuarios, y no se puede adivinar. Además dice su número de instalación: así cada
    PC aparece en el panel (PcConAnalizador) y se la puede desconectar.
"""

import hashlib
import os
import re
import time
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import PcConAnalizador, VersionAnalizador

PEDAZO_MAXIMO = 25 * 1024 * 1024
TAMANIO_MAXIMO = 1536 * 1024 * 1024
_NOMBRE = re.compile(r'KairosAnalizador-(\d+(?:\.\d+){1,3})(?: \(\d+\))?\.exe$', re.IGNORECASE)
_VERSION = re.compile(r'\d+(\.\d+){1,3}')
_IDENTIFICADOR = re.compile(r'[0-9a-f]{32}')
_HUELLA = re.compile(r'[0-9a-f]{64}')
_INSTALACION = re.compile(r'[0-9a-f-]{36}')
VIEJO = timedelta(days=1)


class Problema(Exception):
    """Lo que hay que decirle a quien sube o a quien pide (el texto lo dice)."""


def carpeta():
    return Path(settings.ARCHIVOS_PRIVADOS) / 'analizador'


def _subiendo(identificador):
    if not _IDENTIFICADOR.fullmatch(identificador or ''):
        raise Problema('La subida no tiene un número válido. Volvé a elegir el archivo.')
    return carpeta() / 'subiendo' / f'{identificador}.part'


def version_del_nombre(nombre):
    """'KairosAnalizador-2026.11.9.1530.exe' -> '2026.11.9.1530' ('' si el nombre no la dice)."""
    coincide = _NOMBRE.search(os.path.basename(nombre or ''))
    return coincide.group(1) if coincide else ''


def guardar_pedazo(identificador, desde, pedazo):
    """Agrega un pedazo en su lugar (`desde`, en bytes). Devuelve cuánto lleva recibido."""
    parcial = _subiendo(identificador)
    if desde == 0:
        _limpiar_viejas()
    parcial.parent.mkdir(parents=True, exist_ok=True)
    actual = parcial.stat().st_size if parcial.exists() else 0
    if desde > actual:
        raise Problema('Se perdió un pedazo del archivo. Volvé a elegirlo.')
    if pedazo.size > PEDAZO_MAXIMO:
        raise Problema('Ese pedazo es demasiado grande.')
    if desde + pedazo.size > TAMANIO_MAXIMO:
        raise Problema('El instalador pesa más de 1,5 GB: no parece el del analizador.')
    with parcial.open('r+b' if parcial.exists() else 'wb') as salida:
        salida.truncate(desde)   # si se repite un pedazo (se cortó la respuesta), se reemplaza
        salida.seek(desde)
        for trozo in pedazo.chunks():
            salida.write(trozo)
    return desde + pedazo.size


def publicar(identificador, version, notas, usuario):
    """Deja lo subido como una versión nueva del analizador. Problema si algo no está bien (y lo subido se borra)."""
    parcial = _subiendo(identificador)
    if not parcial.exists():
        raise Problema('No llegó el archivo. Volvé a elegirlo.')
    try:
        version = (version or '').strip()
        if not _VERSION.fullmatch(version):
            raise Problema('La versión tiene que ser como la del nombre del instalador (ej: 2026.11.9.1530).')
        if VersionAnalizador.objects.filter(version=version).exists():
            raise Problema(f'Ya se subió la versión {version}. Armá el instalador de nuevo (cada uno sale con la hora '
                           f'en que se armó).')
        with parcial.open('rb') as entrada:
            if entrada.read(2) != b'MZ':
                raise Problema('El archivo no es un programa de Windows (.exe).')
        huella, tamanio = _huella(parcial)
        if VersionAnalizador.objects.filter(sha256=huella).exists():
            raise Problema('Ese mismo instalador ya está subido con otro número de versión.')
        nombre = f'analizador/KairosAnalizador-{version}.exe'
        final = Path(settings.ARCHIVOS_PRIVADOS) / nombre
        final.parent.mkdir(parents=True, exist_ok=True)
        os.replace(parcial, final)
        try:
            with transaction.atomic():
                return VersionAnalizador.objects.create(version=version, archivo=nombre, tamanio=tamanio,
                                                        sha256=huella, notas=(notas or '').strip(),
                                                        subida_por=usuario)
        except IntegrityError:
            final.unlink(missing_ok=True)
            raise Problema(f'Ya se subió la versión {version}.')
    finally:
        parcial.unlink(missing_ok=True)


def _huella(archivo):
    resumen, tamanio = hashlib.sha256(), 0
    with archivo.open('rb') as entrada:
        for trozo in iter(lambda: entrada.read(1024 * 1024), b''):
            resumen.update(trozo)
            tamanio += len(trozo)
    return resumen.hexdigest(), tamanio


def _limpiar_viejas():
    """Las subidas que quedaron a medias hace más de un día."""
    limite = time.time() - VIEJO.total_seconds()
    for parcial in (carpeta() / 'subiendo').glob('*.part'):
        try:
            if parcial.stat().st_mtime < limite:
                parcial.unlink()
        except OSError:
            pass


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
