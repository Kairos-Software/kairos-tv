"""
Los instaladores para Windows que se suben al panel: el del analizador de canales (VersionAnalizador, solo
superusuarios) y el de la app Kairos TV para PC (VersionPc, como la APK). Cada uno es un [Tipo].

Subir: pesan cientos de MB y nginx acepta hasta 160 MB por pedido, así que la página los manda de a pedazos de
20 MB (static/js/subir_instalador.js). guardar_pedazo() los junta en privado/<carpeta>/subiendo/ y publicar()
revisa que sea un programa de Windows, calcula su huella (SHA-256) y lo deja como una versión nueva. Si se corta,
se vuelve a mandar el pedazo que faltó: nunca queda una versión a medias.

Los archivos van a privado/ (settings.ARCHIVOS_PRIVADOS), no a media/: salen solo por las vistas.
"""

import hashlib
import os
import re
import time
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import IntegrityError, transaction

from .models import VersionAnalizador, VersionPc

PEDAZO_MAXIMO = 25 * 1024 * 1024
TAMANIO_MAXIMO = 1536 * 1024 * 1024
_VERSION = re.compile(r'\d+(\.\d+){1,3}')
_IDENTIFICADOR = re.compile(r'[0-9a-f]{32}')
VIEJO = timedelta(days=1)


class Problema(Exception):
    """Lo que hay que decirle a quien sube o a quien pide (el texto lo dice)."""


@dataclass(frozen=True)
class Tipo:
    """Un instalador: su modelo, su carpeta en privado/ y cómo se lo nombra en los mensajes."""

    modelo: type
    carpeta: str
    #: "del analizador" / "de la app para PC"
    de_que: str

    @property
    def prefijo(self):
        return self.modelo.PREFIJO

    def directorio(self):
        return Path(settings.ARCHIVOS_PRIVADOS) / self.carpeta


ANALIZADOR = Tipo(VersionAnalizador, 'analizador', 'del analizador')
APP_PC = Tipo(VersionPc, 'pc', 'de la app para PC')


def version_del_nombre(tipo, nombre):
    """'KairosTV-2026.11.10.1530.exe' -> '2026.11.10.1530' ('' si el nombre no la dice)."""
    patron = re.compile(rf'{re.escape(tipo.prefijo)}-(\d+(?:\.\d+){{1,3}})(?: \(\d+\))?\.exe$', re.IGNORECASE)
    coincide = patron.search(os.path.basename(nombre or ''))
    return coincide.group(1) if coincide else ''


def _subiendo(tipo, identificador):
    if not _IDENTIFICADOR.fullmatch(identificador or ''):
        raise Problema('La subida no tiene un número válido. Volvé a elegir el archivo.')
    return tipo.directorio() / 'subiendo' / f'{identificador}.part'


def guardar_pedazo(tipo, identificador, desde, pedazo):
    """Agrega un pedazo en su lugar (`desde`, en bytes). Devuelve cuánto lleva recibido."""
    parcial = _subiendo(tipo, identificador)
    if desde == 0:
        _limpiar_viejas(tipo)
    parcial.parent.mkdir(parents=True, exist_ok=True)
    actual = parcial.stat().st_size if parcial.exists() else 0
    if desde > actual:
        raise Problema('Se perdió un pedazo del archivo. Volvé a elegirlo.')
    if pedazo.size > PEDAZO_MAXIMO:
        raise Problema('Ese pedazo es demasiado grande.')
    if desde + pedazo.size > TAMANIO_MAXIMO:
        raise Problema(f'El instalador pesa más de 1,5 GB: no parece el {tipo.de_que}.')
    with parcial.open('r+b' if parcial.exists() else 'wb') as salida:
        salida.truncate(desde)   # si se repite un pedazo (se cortó la respuesta), se reemplaza
        salida.seek(desde)
        for trozo in pedazo.chunks():
            salida.write(trozo)
    return desde + pedazo.size


def publicar(tipo, identificador, version, notas, usuario):
    """Deja lo subido como una versión nueva. Problema si algo no está bien (y lo subido se borra)."""
    parcial = _subiendo(tipo, identificador)
    if not parcial.exists():
        raise Problema('No llegó el archivo. Volvé a elegirlo.')
    try:
        version = (version or '').strip()
        if not _VERSION.fullmatch(version):
            raise Problema('La versión tiene que ser como la del nombre del instalador (ej: 2026.11.9.1530).')
        if tipo.modelo.objects.filter(version=version).exists():
            raise Problema(f'Ya se subió la versión {version}. Armá el instalador de nuevo (cada uno sale con la hora '
                           f'en que se armó).')
        with parcial.open('rb') as entrada:
            if entrada.read(2) != b'MZ':
                raise Problema('El archivo no es un programa de Windows (.exe).')
        huella, tamanio = _huella(parcial)
        if tipo.modelo.objects.filter(sha256=huella).exists():
            raise Problema('Ese mismo instalador ya está subido con otro número de versión.')
        nombre = f'{tipo.carpeta}/{tipo.prefijo}-{version}.exe'
        final = Path(settings.ARCHIVOS_PRIVADOS) / nombre
        final.parent.mkdir(parents=True, exist_ok=True)
        os.replace(parcial, final)
        try:
            with transaction.atomic():
                return tipo.modelo.objects.create(version=version, archivo=nombre, tamanio=tamanio, sha256=huella,
                                                  notas=(notas or '').strip(), subida_por=usuario)
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


def _limpiar_viejas(tipo):
    """Las subidas que quedaron a medias hace más de un día."""
    limite = time.time() - VIEJO.total_seconds()
    for parcial in (tipo.directorio() / 'subiendo').glob('*.part'):
        try:
            if parcial.stat().st_mtime < limite:
                parcial.unlink()
        except OSError:
            pass
