"""
Lector de listas M3U / M3U8 (capa Base, no toca la base de datos).

Una lista M3U es texto. Cada canal ocupa dos líneas:

    #EXTINF:-1 tvg-id="Canal26.ar" tvg-logo="https://..." tvg-chno="26" group-title="Noticias",Canal 26
    https://servidor/canal26/playlist.m3u8

La primera tiene los datos (atributos clave="valor" y, después de la coma,
el nombre); la segunda, la dirección de la señal.

Algunas señales solo se entregan si el reproductor se presenta de cierta
forma (User-Agent) o dice desde qué página viene (Referer). Las listas lo
indican de dos maneras, y las dos se leen:

    #EXTVLCOPT:http-user-agent=Mozilla/5.0 ...
    #EXTVLCOPT:http-referrer=https://pagina-del-canal.com/
    https://servidor/canal/playlist.m3u8|User-Agent=Mozilla/5.0&Referer=https://...

Las listas que exporta este sistema (exportar.py) llevan además la sección
de cada cosa (kairos-seccion="pelicula"), para que al volver a importarlas
vaya a la misma aunque la dirección no diga si es una película.

    from canales.m3u import leer_m3u
    for entrada in leer_m3u(texto):
        entrada.nombre, entrada.url, entrada.categoria, ...
"""

import re
from dataclasses import dataclass

from .clasificar import formato, limpiar_nombre, sin_acentos

_ATRIBUTO = re.compile(r'([\w-]+)\s*=\s*"([^"]*)"')
# Marcas que algunas listas agregan al nombre (Ⓨ = YouTube, Ⓖ = geobloqueado...)
_MARCAS = re.compile(r'[ⓎⒼⓈ]')


@dataclass
class EntradaM3U:
    nombre: str
    url: str
    logo: str = ''
    categoria: str = ''
    numero: str = ''
    tvg_id: str = ''
    pais: str = ''
    user_agent: str = ''
    referer: str = ''
    idioma: str = ''   # el tvg-language tal cual viene ("Spanish", "es"...)
    seccion: str = ''  # kairos-seccion: la sección que tenía al exportarla de este sistema

    @property
    def tipo(self):
        """
        El formato que parece por la dirección. Si no se sabe (ej: las listas
        "Xtream", sin extensión) queda HLS hasta que la verificación averigüe
        el real. Puede ser 'rtmp', que la app no reproduce.
        """
        return formato(self.url) or 'hls'


def normalizar(texto):
    """'ES: Canal 26 HD Ⓨ' -> 'canal 26': para reconocer el mismo canal escrito distinto."""
    return ' '.join(sin_acentos(limpiar_nombre(texto)).split())


def leer_m3u(texto):
    """Devuelve la lista de EntradaM3U de una lista M3U (ignora lo que no entiende)."""
    entradas = []
    pendiente = None
    for linea in (texto or '').lstrip('﻿').splitlines():
        linea = linea.strip()
        if not linea:
            continue
        if linea.upper().startswith('#EXTINF'):
            atributos = dict(_ATRIBUTO.findall(linea))
            # El nombre va después de la coma que sigue al último atributo
            fin_atributos = linea.rfind('",')
            if fin_atributos >= 0:
                nombre = linea[fin_atributos + 2:].strip()
            else:
                nombre = linea.split(',', 1)[1].strip() if ',' in linea else ''
            nombre = _MARCAS.sub('', atributos.get('tvg-name') or nombre).strip()   # '' = sin nombre
            pendiente = EntradaM3U(
                nombre=nombre,
                url='',
                logo=atributos.get('tvg-logo', ''),
                categoria=atributos.get('group-title', '').strip(),
                numero=atributos.get('tvg-chno', '').strip(),
                tvg_id=atributos.get('tvg-id', '').strip(),
                pais=atributos.get('tvg-country', '').strip().upper()[:2],
                idioma=atributos.get('tvg-language', '').strip(),
                seccion=atributos.get('kairos-seccion', '').strip()[:10],
            )
        elif linea.upper().startswith('#EXTVLCOPT:') and pendiente is not None:
            opcion, _, valor = linea[len('#EXTVLCOPT:'):].partition('=')
            opcion = opcion.strip().lower()
            if opcion == 'http-user-agent':
                pendiente.user_agent = valor.strip()
            elif opcion in ('http-referrer', 'http-referer'):
                pendiente.referer = valor.strip()
        elif linea.startswith('#'):
            continue   # otras directivas (#EXTM3U...) no se usan por ahora
        elif pendiente is not None:
            # Algunas listas agregan cabeceras después de "|": dir|User-Agent=...&Referer=...
            direccion, _, opciones = linea.partition('|')
            pendiente.url = direccion.strip()
            for opcion in opciones.split('&') if opciones else []:
                clave, _, valor = opcion.partition('=')
                clave = clave.strip().lower()
                if clave == 'user-agent':
                    pendiente.user_agent = valor.strip()
                elif clave in ('referer', 'referrer'):
                    pendiente.referer = valor.strip()
            if pendiente.url.lower().startswith(('http://', 'https://', 'rtsp://', 'rtsps://', 'rtmp')):
                entradas.append(pendiente)
            pendiente = None
    return entradas
