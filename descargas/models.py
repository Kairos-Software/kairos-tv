"""
Lo que se descarga desde el panel:

- VersionApp: la app Android (la APK). Cada vez que se compila una versión
  nueva, el administrador la sube acá. /descargar/ siempre entrega la ÚLTIMA
  versión publicada.
- VersionAnalizador: el instalador para PC del analizador de canales. Solo lo
  ven y lo bajan los superusuarios; no está en media/ (que nginx sirve a
  cualquiera) sino en privado/analizador/. Los analizadores instalados lo bajan
  solos para actualizarse (api/v1/analizador.py).
- PcConAnalizador: cada PC donde hay un analizador instalado, con su versión y
  la última vez que preguntó por una nueva.
"""

import os
from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models


class VersionApp(models.Model):
    version = models.CharField('versión', max_length=30, help_text='Ej: 1.0.3 (la de pubspec.yaml).')
    archivo = models.FileField('APK', upload_to='apk/')
    notas = models.TextField('qué cambió', blank=True)
    publicada = models.BooleanField(default=True, help_text='Las no publicadas no se descargan.')
    subida = models.DateTimeField(auto_now_add=True)
    subida_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')

    class Meta:
        verbose_name = 'versión de la app'
        verbose_name_plural = 'versiones de la app'
        ordering = ['-subida', '-pk']

    def __str__(self):
        return f'Kairos TV {self.version}'

    @property
    def nombre_descarga(self):
        return f'KairosTV-{self.version}.apk'

    @classmethod
    def ultima(cls):
        return cls.objects.filter(publicada=True).first()


class Privado(FileSystemStorage):
    """
    settings.ARCHIVOS_PRIVADOS, fuera de media/: nginx no lo sirve, solo sale por las vistas que revisan quién lo
    pide. La carpeta se lee cada vez (y no una sola al arrancar): así las pruebas usan una temporal.
    """

    @property
    def base_location(self):
        return Path(settings.ARCHIVOS_PRIVADOS)

    @property
    def location(self):
        return os.path.abspath(self.base_location)


def privado():
    return Privado()


class VersionAnalizador(models.Model):
    version = models.CharField('versión', max_length=30, unique=True,
                               help_text='La del nombre del instalador (KairosAnalizador-2026.11.9.1530.exe).')
    archivo = models.FileField('instalador', upload_to='analizador/', storage=privado)
    tamanio = models.PositiveBigIntegerField('tamaño (bytes)', default=0)
    sha256 = models.CharField('huella SHA-256', max_length=64, unique=True)
    notas = models.TextField('qué cambió', blank=True)
    publicada = models.BooleanField(default=True, help_text='Las no publicadas no se descargan ni se instalan solas.')
    subida = models.DateTimeField(auto_now_add=True)
    subida_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')

    class Meta:
        verbose_name = 'versión del analizador'
        verbose_name_plural = 'versiones del analizador'
        ordering = ['-subida', '-pk']

    def __str__(self):
        return f'Analizador {self.version}'

    @property
    def nombre_descarga(self):
        return f'KairosAnalizador-{self.version}.exe'

    @property
    def numero(self):
        return tuple(int(parte) for parte in self.version.split('.'))

    @classmethod
    def ultima(cls):
        """La publicada con el número más alto (no la última subida: se puede volver a publicar una vieja)."""
        publicadas = list(cls.objects.filter(publicada=True).exclude(archivo=''))
        return max(publicadas, key=lambda version: version.numero, default=None)


class PcConAnalizador(models.Model):
    """Una PC con el analizador instalado. La anota sola el analizador cada vez que pregunta por una versión nueva."""

    instalacion = models.CharField('número de instalación', max_length=36, unique=True)
    nombre = models.CharField('PC', max_length=100)
    version = models.CharField('versión', max_length=30)
    primera_vez = models.DateTimeField(auto_now_add=True)
    ultima_vez = models.DateTimeField()
    desconectada = models.BooleanField(default=False, help_text='Ya no recibe versiones nuevas.')

    class Meta:
        verbose_name = 'PC con el analizador'
        verbose_name_plural = 'PCs con el analizador'
        ordering = ['desconectada', '-ultima_vez']

    def __str__(self):
        return f'{self.nombre} ({self.version})'
