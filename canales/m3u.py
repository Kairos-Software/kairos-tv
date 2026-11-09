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
vaya a la misma aunque la dirección no diga si es una película, y qué tipo
de señal es (kairos-tipo="web", "yt_video", "hls"...: EntradaM3U.tipo_lista),
para que vuelva como lo que es aunque la dirección no lo diga.

Las listas limpias del ANALIZADOR DE CANALES (el programa de la PC que mira
cada señal un minuto y medio: KAIROS TV\\analizador-canales) traen al final,
en comentarios que las otras apps no leen, las señales que no sirven:

    #KAIROS-NO-SIRVE url="http://servidor/canal.m3u8" motivo="Se cortó a los 40 s y no volvió"

Esas las lee leer_las_que_no_sirven (y servicios.quitar_las_que_no_sirven las
saca de la app al importar la lista).

Desde su versión 4 trae también lo que midió de cada señal que va en la lista
(leer_analisis), y las que fallaron una sola vez con otra marca (un panel
viejo, que apaga las NO-SIRVE sin preguntar, no la lee):

    #KAIROS-ANALISIS version="5" fecha="2026-11-08T21:30:00-03:00"
    #KAIROS-ANDA url="http://servidor/canal.m3u8" medida="2026-11-08T21:00:00-03:00" version="5" estado="anda" vence=""
                 tipo="hls" codec="h264" calidad="1080p · H.264 · audio AAC (es)" idioma="es"
    #KAIROS-POR-CONFIRMAR url="http://servidor/otro.m3u8" motivo="Falló una vez: error 403" causa="otro_horario"

estado: anda, a_mano (aprobada a mano), dudosa, sin_confirmar (una página que
la PC no pudo mirar entera) o sin_juzgar (sin lugar en la cuenta, sin medir),
con su motivo si no es "anda". Lo que anda o no anda lo decide el analizador:
con esto el panel no la vuelve a juzgar. Una lista sin esas líneas se importa
como siempre.

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
# Una señal que el analizador de canales dio como que no sirve (ver arriba)
NO_SIRVE = '#KAIROS-NO-SIRVE'
POR_CONFIRMAR = '#KAIROS-POR-CONFIRMAR'
ANALISIS = '#KAIROS-ANALISIS'
ANDA = '#KAIROS-ANDA'
# Lo que trae cada #KAIROS-ANDA, además de la dirección
_DEL_SELLO = ('medida', 'estado', 'vence', 'motivo', 'tipo', 'codec', 'calidad', 'idioma')


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
    tipo_lista: str = ''   # kairos-tipo: el tipo de señal que tenía acá (Fuente.Tipo: 'hls', 'web', 'yt_video'...)

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
                tipo_lista=atributos.get('kairos-tipo', '').strip().lower()[:10],
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


def leer_las_que_no_sirven(texto):
    """{dirección: motivo} de las líneas #KAIROS-NO-SIRVE de una lista limpia del analizador (ver arriba)."""
    malas = {}
    for linea in (texto or '').splitlines():
        linea = linea.strip()
        if linea.upper().startswith(NO_SIRVE):
            atributos = dict(_ATRIBUTO.findall(linea))
            url = atributos.get('url', '').strip()
            if url:
                malas[url] = atributos.get('motivo', '').strip()
    return malas


def leer_analisis(texto):
    """
    Lo que midió el analizador de canales, o None si la lista no lo trae (se importa como siempre):
    {'version': 5, 'fecha': '...',
     'anda': {dirección: {medida, version, estado, vence, motivo, tipo, codec, calidad, idioma}},  (las de la lista)
     'no_sirven': {dirección: {motivo, causa}}, 'por_confirmar': {dirección: {motivo, causa}}}.
    """
    analisis = None
    anda, no_sirven, por_confirmar = {}, {}, {}
    for linea in (texto or '').splitlines():
        linea = linea.strip()
        if not linea.startswith('#KAIROS-'):
            continue
        atributos = dict(_ATRIBUTO.findall(linea))
        url = atributos.get('url', '').strip()
        marca = linea.upper().split(' ', 1)[0]
        if marca == ANALISIS:
            version = atributos.get('version', '')
            analisis = {'version': int(version) if version.isdigit() else 0, 'fecha': atributos.get('fecha', '')}
        elif marca == ANDA and url:
            version = atributos.get('version', '')
            anda[url] = {**{clave: atributos.get(clave, '').strip() for clave in _DEL_SELLO},
                         'version': int(version) if version.isdigit() else 0}
        elif marca in (NO_SIRVE, POR_CONFIRMAR) and url:
            (no_sirven if marca == NO_SIRVE else por_confirmar)[url] = {
                'motivo': atributos.get('motivo', '').strip(), 'causa': atributos.get('causa', '').strip()}
    if analisis is None:
        return None
    return {**analisis, 'anda': anda, 'no_sirven': no_sirven, 'por_confirmar': por_confirmar}
