"""
Comprueba si las fuentes responden (capa Base, no toca la base de datos).

Hace lo mismo que el reproductor de la app, pero desde el servidor:

  1. Pide la dirección y mira QUÉ devuelve (como VLC, no confía en la
     extensión): una lista HLS (#EXTM3U), un manifiesto DASH (<MPD>) o video
     "directo" (MPEG-TS, MP4, MKV, FLV...: lo que mandan las listas "Xtream",
     las direcciones sin extensión tipo http://servidor:8080/usuario/clave/123).
  2. Si es HLS "maestra" (la que ofrece varias calidades), pide la primera
     calidad: muchas veces la maestra responde y la señal no.
  3. En HLS, pide el pedazo de video MÁS RECIENTE (por ahí arranca el
     reproductor): hay servidores que entregan la lista pero rechazan el video.

En HLS se presenta igual que el reproductor de la app (USER_AGENT_REPRODUCTOR,
o el User-Agent / Referer propio de la fuente); si el servidor lo rechaza,
prueba como VLC. Los archivos directos se piden primero como VLC y con Range,
igual que un reproductor: hay paneles Xtream que dejan esperando a un navegador
o intentan enviar el MKV completo. Si así anda, el resultado trae ese User-Agent
para guardarlo en la fuente (y la app lo usa).

De paso averigua el CÓDEC del video (h264, h265, mpeg2...): en HLS lo dice
la lista maestra (CODECS=...) o, si no, el pedazo de video; en video directo,
los primeros bytes (ver detectar_codec). No todos los aparatos saben mostrar
todos los códecs (muchos TV box no leen MPEG-2, muchos celulares no leen
H.265): la app lo compara con lo que sabe su aparato y no muestra lo que no
puede ver. Así se evita la "imagen verde o negra con sonido".

También distingue el video de 10 BITS (h264_10: H.264 "Hi10P", muy común en
anime; h265_10: H.265 "Main 10"): casi ningún TV box decodifica H.264 de 10
bits, y lo muestra con franjas verdes y la imagen rota (ver perfil_10_bits).

PRUEBA A FONDO (a_fondo=True, la usa la importación): además de ver que
responda, baja hasta BYTES_A_FONDO del video y averigua (ver analisis.py):

  - si tiene SONIDO, de qué tipo y en qué IDIOMA (si el video lo dice);
  - la RESOLUCIÓN (cuántas líneas: 1080, 720...);
  - si llega FLUIDO: cuántos segundos de video llegan por segundo
    (`velocidad`: 1 = justo, menos de 1 = se va a cortar);
  - en vivo por HLS, si la señal AVANZA: vuelve a pedir la lista después de
    un rato y mira que tenga pedazos nuevos (si no, está CONGELADA).

Esta capa solo junta los datos; qué se acepta y qué no lo decide
servicios.juzgar (según lo que se eligió al subir la lista).

YouTube y las páginas de video (Twitch, Dailymotion...) se comprueban con
yt-dlp (ver paginas.py). Si una dirección cualquiera responde con una página
web, también se prueba si adentro hay un video. RTSP se comprueba con un
pedido OPTIONS. RTMP la app no lo reproduce.

Cada pedido espera como máximo TIEMPO_MAXIMO segundos; se verifican HILOS
fuentes a la vez, pero nunca más de POR_SERVIDOR al mismo servidor. Los videos
directos van de a uno: las cuentas IPTV suelen permitir una sola reproducción.

    from canales.verificacion import verificar_url, verificar_varias
    verificar_url('https://.../playlist.m3u8')        -> Resultado('funciona', tipo='hls')
    verificar_url(url, a_fondo=True)                  -> ... alto=1080, con_audio=True, idiomas=('es',), velocidad=3.2
    verificar_varias({url: 'hls', url2: 'youtube'})   -> {url: Resultado, ...}
"""

import http.client
import re
import socket
import ssl
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

from . import analisis

TIEMPO_MAXIMO = 9         # segundos por pedido (el HTML usa 9)
HILOS = 10                # fuentes verificadas a la vez
POR_SERVIDOR = 2          # ...pero como mucho estas al mismo servidor
POR_SERVIDOR_DIRECTO = 1  # las cuentas Xtream suelen permitir un solo video a la vez
BYTES_INICIALES = 64 * 1024   # para saber qué es alcanza con el principio
MAX_BYTES = 512 * 1024    # una lista .m3u8 pesa pocos KB: no hace falta leer más
BYTES_DE_VIDEO = 32 * 1024    # del pedazo de video alcanza con ver que empieza a llegar

# Prueba a fondo: cuánto video se baja de cada fuente (como mucho), y cuánto
# tiempo se mira una señal en vivo "directa" (que llega a la velocidad en
# que se reproduce). Con menos de BYTES_PARA_MEDIR no se juzga la velocidad.
BYTES_A_FONDO = 1024 * 1024
SEGUNDOS_DE_MUESTRA = 6
BYTES_PARA_MEDIR = 192 * 1024
# Una película de la que no se sabe la calidad tiene que llegar al menos a
# esta velocidad (bits por segundo): la de un 1080p común.
VELOCIDAD_DE_UNA_PELICULA = 3_000_000
# Cuánto se espera, como máximo, para ver si una señal en vivo avanza.
ESPERA_MAXIMA_EN_VIVO = 10

# Cómo se presenta el reproductor de la app (la API se lo manda junto con
# cada fuente). Como un navegador de celular: hay servidores de canales que
# rechazan a "ExoPlayer" (el reproductor de Android) con error 403.
USER_AGENT_REPRODUCTOR = ('Mozilla/5.0 (Linux; Android 14; K) AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/124.0.0.0 Mobile Safari/537.36')
# El segundo intento: hay paneles IPTV que solo atienden a reproductores conocidos
USER_AGENT_VLC = 'VLC/3.0.21 LibVLC/3.0.21'

# Los paneles Xtream suelen servir los archivos directos solo a reproductores
# conocidos. Algunos no responden con error al User-Agent de navegador: dejan
# la conexión esperando hasta el timeout. Probar VLC primero evita nueve
# segundos perdidos por cada capítulo y permite guardar esa cabecera para la app.
_EXTENSIONES_DE_VIDEO_DIRECTO = ('.mkv', '.mp4', '.avi', '.mov', '.wmv', '.webm', '.m4v', '.mpeg', '.mpg')

FUNCIONA = 'funciona'
CAIDA = 'caida'
SIN_VERIFICAR = 'sin_verificar'


@dataclass
class Resultado:
    estado: str           # FUNCIONA, CAIDA o SIN_VERIFICAR
    error: str = ''       # por qué falló (para mostrar en el panel)
    tipo: str = ''        # el formato que se encontró: hls, dash, directo, rtsp, youtube, pagina ('' = no se sabe)
    user_agent: str = ''  # si anduvo con otro User-Agent (ej: el de VLC), cuál
    rechazo: bool = False  # el servidor respondió pero no entregó la señal (vale la pena probar como VLC)
    es_pagina: bool = False  # respondió una página web (puede tener un video adentro)
    titulo: str = ''      # YouTube / páginas: el título del video o canal (para sugerir el nombre)
    imagen: str = ''      # ...y su miniatura (para sugerir el logo)
    codec: str = ''       # el códec del video: h264, h265, h264_10, h265_10, mpeg2, mpeg4, vc1, av1, vp9 ('' = no se sabe)
    # Lo que averigua la prueba a fondo (vacío o None = no se sabe)
    a_fondo: bool = False  # se hizo la prueba a fondo
    alto: int = 0          # líneas de la imagen: 1080, 720...
    con_audio: bool | None = None
    audios: tuple = ()     # códecs de audio: aac, ac3...
    idiomas: tuple = ()    # idiomas del audio: es, en...
    velocidad: float = 0   # segundos de video que llegan por segundo (menos de 1: se corta)
    se_corto: bool = False  # dejó de llegar mientras se bajaba
    congelada: bool = False  # en vivo: la lista no avanza

    def calidad(self):
        """Lo que se sabe de la imagen y el sonido, para el panel: '1080p · H.264 · audio AAC (es, en) · fluido'."""
        partes = []
        if self.alto:
            partes.append(f'{self.alto}p')
        if self.codec:
            partes.append(NOMBRES_DE_CODECS.get(self.codec, self.codec.upper()))
        if self.con_audio is False:
            partes.append('sin sonido')
        elif self.audios or self.idiomas:
            audio = 'audio ' + '/'.join(a.upper() for a in self.audios) if self.audios else 'audio'
            partes.append(f'{audio} ({", ".join(self.idiomas)})' if self.idiomas else audio)
        if self.velocidad:
            partes.append(f'llega x{self.velocidad:.1f}')
        return ' · '.join(partes)[:80]


NOMBRES_DE_CODECS = {'h264': 'H.264', 'h265': 'H.265', 'h264_10': 'H.264 10 bits', 'h265_10': 'H.265 10 bits',
                     'mpeg2': 'MPEG-2', 'mpeg4': 'MPEG-4', 'vc1': 'VC-1', 'av1': 'AV1', 'vp9': 'VP9'}


@dataclass
class Bajada:
    """Un pedazo de video bajado, y cuánto tardó en llegar."""
    datos: bytes
    final: str              # la dirección después de las redirecciones
    tipo_contenido: str
    largo: int = 0          # lo que dice el servidor que mide todo (Content-Length; 0 = no lo dice)
    segundos: float = 0     # lo que tardó en llegar (desde que empezó a responder)
    se_corto: bool = False  # dejó de llegar a mitad de camino


def cabeceras_para(user_agent='', referer=''):
    """Las cabeceras con que se pide la señal (las mismas que usa la app)."""
    cabeceras = {'User-Agent': user_agent or USER_AGENT_REPRODUCTOR}
    if referer:
        cabeceras['Referer'] = referer
    return cabeceras


def _cabeceras_para_video_directo(user_agent='', referer='', a_fondo=False):
    """Como un reproductor: pide solo el comienzo del archivo, no el MKV/MP4 completo."""
    cabeceras = cabeceras_para(user_agent, referer)
    maximo = BYTES_A_FONDO if a_fondo else BYTES_INICIALES
    cabeceras['Range'] = f'bytes=0-{maximo - 1}'
    return cabeceras


def _descargar(url, cabeceras, maximo=MAX_BYTES):
    """(bytes, dirección final después de redirecciones, Content-Type)."""
    pedido = urllib.request.Request(url, headers=cabeceras)
    with urllib.request.urlopen(pedido, timeout=TIEMPO_MAXIMO) as respuesta:
        return respuesta.read(maximo), respuesta.geturl(), respuesta.headers.get('Content-Type', '') or ''


def _bajar(url, cabeceras, maximo=BYTES_A_FONDO, segundos=SEGUNDOS_DE_MUESTRA):
    """
    Baja hasta `maximo` bytes (o lo que llegue en `segundos`) midiendo cuánto
    tarda. Si deja de llegar a mitad de camino, lo marca (`se_corto`).
    """
    pedido = urllib.request.Request(url, headers=cabeceras)
    with urllib.request.urlopen(pedido, timeout=TIEMPO_MAXIMO) as respuesta:
        inicio = time.monotonic()
        partes, total, se_corto = [], 0, False
        while total < maximo and time.monotonic() - inicio < segundos:
            try:
                parte = respuesta.read(min(64 * 1024, maximo - total))
            except (TimeoutError, socket.timeout):
                if not total:
                    raise
                se_corto = True
                break
            if not parte:
                break
            partes.append(parte)
            total += len(parte)
        rango = re.search(r'/(\d+)$', respuesta.headers.get('Content-Range') or '')
        try:
            # Con Range, Content-Length es solo el pedazo. Para medir la
            # velocidad hace falta el tamaño del archivo completo.
            largo = int(rango.group(1) if rango else respuesta.headers.get('Content-Length') or 0)
        except ValueError:
            largo = 0
        return Bajada(b''.join(partes), respuesta.geturl(), respuesta.headers.get('Content-Type', '') or '',
                      largo, time.monotonic() - inicio, se_corto)


def _esperar(segundos):
    time.sleep(segundos)


def _texto(datos):
    return datos.decode('utf-8', errors='replace')


def _es_lista_hls(datos):
    return datos.lstrip(b'\xef\xbb\xbf \r\n\t').startswith(b'#EXTM3U')


def _es_mpeg_ts(datos):
    return analisis.es_mpeg_ts(datos)


def detectar_formato(datos, tipo_contenido=''):
    """
    Qué es lo que respondió el servidor, mirando los primeros bytes:
    'hls', 'dash', 'directo' (video o audio que se reproduce tal cual) o '' (otra cosa).
    """
    if _es_lista_hls(datos):
        return 'hls'
    tipo_contenido = tipo_contenido.lower()
    if b'<MPD' in datos[:4096]:
        return 'dash'
    if (_es_mpeg_ts(datos)
            or datos[4:8] == b'ftyp'                 # MP4
            or datos[:4] == b'\x1aE\xdf\xa3'         # MKV / WebM
            or datos[:3] in (b'FLV', b'ID3')         # FLV / MP3
            or tipo_contenido.startswith(('video/', 'audio/'))):
        return 'directo'
    if 'mpegurl' in tipo_contenido:
        return 'hls'
    return ''


# ── Códec del video ──────────────────────────────────────────────────

# MKV (CodecID) y MP4 / HLS con fMP4 (nombre de la "caja" de la pista de video)
_MARCAS_DE_CODEC = [
    (b'V_MPEGH/ISO/HEVC', 'h265'), (b'V_MPEG4/ISO/AVC', 'h264'), (b'V_MPEG2', 'mpeg2'),
    (b'V_AV1', 'av1'), (b'V_VP9', 'vp9'),
    (b'hvc1', 'h265'), (b'hev1', 'h265'), (b'avc1', 'h264'), (b'avc3', 'h264'), (b'av01', 'av1'),
    (b'vp09', 'vp9'),
]

# HLS: el atributo CODECS de la lista maestra
_PREFIJOS_HLS = [('hvc1', 'h265'), ('hev1', 'h265'), ('avc1', 'h264'), ('avc3', 'h264'), ('av01', 'av1'),
                 ('vp09', 'vp9'), ('mp4v.20', 'mpeg4')]


def _codec_mpeg_ts(datos):
    """El códec de la primera pista de video, según las tablas PAT y PMT del MPEG-TS."""
    return next((pista.codec for pista in analisis.pistas_ts(datos) if pista.clase == 'video'), '')


# Los "perfiles" de 10 bits (o más). H.264: High 10 (110), High 4:2:2 (122), High 4:4:4 (244).
# H.265: Main 10 (2) y Range Extensions (4).
_PERFILES_10_BITS = {'h264': {110, 122, 244}, 'h265': {2, 4}}
_PERFILES_H264 = {66, 77, 88, 100, 110, 118, 122, 128, 144, 244, 44}


def _perfil_en_registro(datos, inicio, codec):
    """El perfil en un registro avcC / hvcC (empieza con la versión 1, el perfil es el byte siguiente)."""
    if inicio + 2 > len(datos) or datos[inicio] != 1:
        return None
    return datos[inicio + 1] & (0x1F if codec == 'h265' else 0xFF)


def _perfil_en_sps(datos, codec):
    """El perfil leyendo el SPS del video "crudo" (MPEG-TS, pedazos de HLS): 00 00 01 + encabezado."""
    i = datos.find(b'\x00\x00\x01')
    while 0 <= i < len(datos) - 6:
        encabezado = datos[i + 3]
        if codec == 'h264' and encabezado & 0x1F == 7 and datos[i + 4] in _PERFILES_H264:
            return datos[i + 4]
        if codec == 'h265' and (encabezado >> 1) & 0x3F == 33:   # el SPS de H.265
            return datos[i + 6] & 0x1F
        i = datos.find(b'\x00\x00\x01', i + 3)
    return None


def perfil_10_bits(datos, codec):
    """
    Si el video es de 10 bits (o más): mira el perfil del códec. En MP4 está en
    la "caja" avcC / hvcC; en MKV, en el CodecPrivate (el mismo registro); en
    MPEG-TS, en el SPS (los datos de arranque del video). Si no lo encuentra, False.
    """
    if codec not in _PERFILES_10_BITS:
        return False
    perfil = None
    caja = datos.find(b'avcC' if codec == 'h264' else b'hvcC')
    if caja >= 0:
        perfil = _perfil_en_registro(datos, caja + 4, codec)
    if perfil is None:
        marca = datos.find(b'V_MPEG4/ISO/AVC' if codec == 'h264' else b'V_MPEGH/ISO/HEVC')
        privado = datos.find(b'\x63\xa2', marca) if marca >= 0 else -1   # CodecPrivate de MKV
        if privado >= 0 and privado + 2 < len(datos):
            primero = datos[privado + 2]
            largo_del_tamanio = next((n for n in range(1, 9) if primero & (0x80 >> (n - 1))), 8)
            perfil = _perfil_en_registro(datos, privado + 2 + largo_del_tamanio, codec)
    if perfil is None:
        perfil = _perfil_en_sps(datos, codec)
    return perfil in _PERFILES_10_BITS[codec]


def detectar_codec(datos):
    """El códec del video mirando los primeros bytes (MPEG-TS, MKV o MP4). '' = no se sabe."""
    if not datos:
        return ''
    codec = ''
    if _es_mpeg_ts(datos):
        codec = _codec_mpeg_ts(datos)
    else:
        codec = next((codec for marca, codec in _MARCAS_DE_CODEC if marca in datos), '')
    if perfil_10_bits(datos, codec):
        return f'{codec}_10'
    return codec


def _perfil_hls(parte, codec):
    """El perfil en el CODECS de HLS: avc1.6E0028 -> 0x6E = 110; hvc1.2.4.L120 -> 2 (puede venir como A2, B2...)."""
    try:
        if codec == 'h264':
            return int(parte.split('.')[1][:2], 16)
        return int(re.sub(r'^[A-Ca-c]', '', parte.split('.')[1]))
    except (IndexError, ValueError):
        return None


# Del que más aparatos leen al que menos (para elegir entre las calidades de una lista HLS)
CODECS_DEL_MAS_COMPATIBLE = ['h264', 'h265', 'mpeg4', 'h265_10', 'h264_10', 'vp9', 'av1', 'mpeg2', 'vc1']


def _codec_de_la_calidad(codecs):
    """'avc1.64001f,mp4a.40.2' -> 'h264' (el del video; '' si no lo dice)."""
    for parte in codecs.split(','):
        parte = parte.strip()
        for prefijo, codec in _PREFIJOS_HLS:
            if parte.lower().startswith(prefijo):
                if _perfil_hls(parte, codec) in _PERFILES_10_BITS.get(codec, ()):
                    return f'{codec}_10'
                return codec
    return ''


def codec_de_hls(texto):
    """
    El códec de una lista maestra (CODECS="avc1.64001f,mp4a.40.2"). Si ofrece
    varias calidades con distinto códec, el MÁS COMPATIBLE
    (CODECS_DEL_MAS_COMPATIBLE): el reproductor del aparato elige solo una
    calidad que sabe mostrar, así que con que haya una en H.264 alcanza (antes
    se anotaba la primera, y una TV que no lee H.265 de 10 bits escondía el
    canal aunque tuviera también calidades en H.264).
    """
    encontrados = []
    for linea in texto.splitlines():
        codecs = re.search(r'CODECS="([^"]*)"', linea) if linea.startswith('#EXT-X-STREAM-INF') else None
        codec = _codec_de_la_calidad(codecs.group(1)) if codecs else ''
        if codec:
            encontrados.append(codec)
    orden = {codec: posicion for posicion, codec in enumerate(CODECS_DEL_MAS_COMPATIBLE)}
    return min(encontrados, key=lambda c: orden.get(c, len(orden)), default='')


def _duracion_del_ultimo(texto):
    """Cuántos segundos dura el último pedazo de una lista HLS (#EXTINF:6.0,)."""
    duraciones = re.findall(r'#EXTINF:\s*([\d.]+)', texto)
    try:
        return float(duraciones[-1]) if duraciones else 0
    except ValueError:
        return 0


def _marca_de_la_lista(texto):
    """Lo que cambia cuando una lista en vivo avanza: su número de secuencia y el último pedazo."""
    secuencia = re.search(r'#EXT-X-MEDIA-SEQUENCE:\s*(\d+)', texto)
    pedazos = _direcciones(texto)
    return (secuencia.group(1) if secuencia else '', pedazos[-1] if pedazos else '')


def _sigue_avanzando(url, texto, cabeceras, desde):
    """
    En vivo: vuelve a pedir la lista cuando ya tendría que haber un pedazo
    nuevo (#EXT-X-TARGETDURATION después de la primera vez) y mira si cambió.
    Si no se puede pedir, no se juzga (True).
    """
    objetivo = re.search(r'#EXT-X-TARGETDURATION:\s*(\d+)', texto)
    espera = min(max(int(objetivo.group(1)) if objetivo else 6, 2), ESPERA_MAXIMA_EN_VIVO) + 1
    _esperar(max(0, desde + espera - time.monotonic()))
    try:
        datos, _, _ = _descargar(url, cabeceras, MAX_BYTES)
    except (OSError, ValueError, http.client.HTTPException):
        return True
    return _marca_de_la_lista(_texto(datos)) != _marca_de_la_lista(texto)


def _velocidad(analizado, bajada, duracion=0):
    """
    Cuántos segundos de video llegan por cada segundo de espera (1 = justo;
    menos de 1 = se va a cortar). 0 = no se pudo medir.
      - MPEG-TS: por las marcas de tiempo del video que llegó (lo más preciso).
      - Si se sabe cuánto dura (el pedazo de HLS, o la película) y cuánto pesa:
        lo que llega por segundo contra lo que hace falta por segundo.
      - Una película de la que no se sabe nada: contra VELOCIDAD_DE_UNA_PELICULA.
    """
    llegaron = len(bajada.datos)
    if llegaron < BYTES_PARA_MEDIR and not (bajada.se_corto and llegaron):
        return 0
    segundos = max(bajada.segundos, 0.05)
    if analizado.segundos >= 0.5:
        return round(analizado.segundos / segundos, 2)
    duracion = duracion or analizado.duracion
    if duracion and bajada.largo:
        return round((llegaron / segundos) / (bajada.largo / duracion), 2)
    if bajada.largo > 50 * 1024 * 1024:   # un archivo grande: una película
        return round((llegaron / segundos) / (VELOCIDAD_DE_UNA_PELICULA / 8), 2)
    return 0


def _completar(resultado, bajada, duracion=0, maestra=None):
    """Le suma al resultado lo que dice el pedazo de video (y la lista maestra, si hay)."""
    analizado = analisis.analizar(bajada.datos, resultado.codec)
    resultado.a_fondo = True
    resultado.alto = (maestra.alto if maestra else 0) or analizado.alto
    resultado.con_audio = True if maestra and maestra.audio_aparte else analizado.con_audio
    resultado.audios = tuple(analizado.audios)
    resultado.idiomas = tuple(dict.fromkeys([*(maestra.idiomas if maestra else []), *analizado.idiomas]))
    resultado.velocidad = _velocidad(analizado, bajada, duracion)
    resultado.se_corto = bajada.se_corto
    return resultado


def _direcciones(texto):
    return [linea.strip() for linea in texto.splitlines() if linea.strip() and not linea.strip().startswith('#')]


def _primera_calidad(texto, base):
    """En una lista maestra, la dirección de la primera calidad (o None si no es maestra)."""
    lineas = [linea.strip() for linea in texto.splitlines()]
    for i, linea in enumerate(lineas):
        if linea.startswith('#EXT-X-STREAM-INF'):
            for siguiente in lineas[i + 1:]:
                if siguiente and not siguiente.startswith('#'):
                    return urljoin(base, siguiente)  # puede ser relativa a la maestra
    return None


def _error_http(error, que):
    if error.code in (401, 403):
        return Resultado(CAIDA, f'El canal no entrega {que} al reproductor (error {error.code}).', rechazo=True)
    return Resultado(CAIDA, f'El servidor respondió con error {error.code} al pedir {que}.',
                     rechazo=400 <= error.code < 500)


def _probar(url, cabeceras, a_fondo=False):
    """Una prueba completa con estas cabeceras (a fondo: ver el principio)."""
    que = 'la lista'
    try:
        if a_fondo:
            bajada = _bajar(url, cabeceras)
            datos, final, tipo_contenido = bajada.datos, bajada.final, bajada.tipo_contenido
        else:
            datos, final, tipo_contenido = _descargar(url, cabeceras, BYTES_INICIALES)
        tipo = detectar_formato(datos, tipo_contenido)
        if tipo == 'directo':
            if not datos:
                return Resultado(CAIDA, 'No llegó video.')
            resultado = Resultado(FUNCIONA, tipo='directo', codec=detectar_codec(datos))
            return _completar(resultado, bajada) if a_fondo else resultado
        if tipo == 'dash':
            return Resultado(FUNCIONA, tipo='dash')
        if tipo != 'hls':
            if b'<html' in datos[:2048].lower() or b'<!doctype' in datos[:2048].lower():
                return Resultado(CAIDA, 'Responde, pero con una página web, no con video.', rechazo=True,
                                 es_pagina=True)
            return Resultado(CAIDA, 'Responde, pero no es un formato de video conocido.', rechazo=True)

        if not a_fondo and len(datos) >= BYTES_INICIALES:   # una lista larga: se pide entera
            datos, final, _ = _descargar(url, cabeceras, MAX_BYTES)
        texto = _texto(datos)
        codec = codec_de_hls(texto)
        maestra = analisis.de_la_maestra(texto) if a_fondo else None
        calidad = _primera_calidad(texto, final)
        if calidad:
            datos, final, _ = _descargar(calidad, cabeceras, MAX_BYTES)
            if not _es_lista_hls(datos):
                return Resultado(CAIDA, 'La lista responde, pero la señal no.', tipo='hls')
            texto = _texto(datos)
        pedazos = _direcciones(texto)
        if not pedazos:
            return Resultado(CAIDA, 'La lista no tiene video (está vacía).', tipo='hls')
        que = 'el video'
        lista, cuando = final, time.monotonic()
        if not a_fondo:
            pedazo, _, _ = _descargar(urljoin(final, pedazos[-1]), cabeceras, BYTES_DE_VIDEO)   # el más reciente
            if not pedazo:
                return Resultado(CAIDA, 'La lista responde, pero no llega video.', tipo='hls')
            return Resultado(FUNCIONA, tipo='hls', codec=codec or detectar_codec(pedazo))
        bajada = _bajar(urljoin(final, pedazos[-1]), cabeceras)
        if not bajada.datos:
            return Resultado(CAIDA, 'La lista responde, pero no llega video.', tipo='hls')
        resultado = Resultado(FUNCIONA, tipo='hls', codec=codec or detectar_codec(bajada.datos))
        _completar(resultado, bajada, _duracion_del_ultimo(texto), maestra)
        if '#EXT-X-ENDLIST' not in texto:   # en vivo: ¿avanza?
            resultado.congelada = not _sigue_avanzando(lista, texto, cabeceras, cuando)
        return resultado
    except urllib.error.HTTPError as error:
        return _error_http(error, que)
    except urllib.error.URLError as error:
        if isinstance(error.reason, TimeoutError):
            return Resultado(CAIDA, 'No respondió a tiempo.')
        if isinstance(error.reason, ssl.SSLCertVerificationError):
            # El reproductor de Android también la rechazaría
            return Resultado(CAIDA, 'Certificado de seguridad inválido.')
        if isinstance(error.reason, socket.gaierror):
            return Resultado(CAIDA, 'El servidor ya no existe (dirección desconocida).')
        if isinstance(error.reason, ConnectionRefusedError):
            return Resultado(CAIDA, 'El servidor rechazó la conexión.')
        return Resultado(CAIDA, f'No se pudo conectar ({error.reason}).'[:200])
    except TimeoutError:
        return Resultado(CAIDA, 'No respondió a tiempo.')
    except (ConnectionResetError, http.client.RemoteDisconnected):
        # Algunos paneles cortan la conexión a los reproductores que no conocen
        return Resultado(CAIDA, 'El servidor cortó la conexión.', rechazo=True)
    except (OSError, ValueError, http.client.HTTPException) as error:
        return Resultado(CAIDA, f'Error: {error}'[:200])


def _verificar_rtsp(url):
    """RTSP no es http: se le pregunta OPTIONS y se espera "RTSP/1.0 200"."""
    partes = urlsplit(url)
    try:
        with socket.create_connection((partes.hostname, partes.port or 554), timeout=TIEMPO_MAXIMO) as conexion:
            conexion.sendall(f'OPTIONS {url} RTSP/1.0\r\nCSeq: 1\r\nUser-Agent: {USER_AGENT_VLC}\r\n\r\n'.encode())
            respuesta = conexion.recv(512).decode('latin-1')
    except TimeoutError:
        return Resultado(CAIDA, 'No respondió a tiempo.', tipo='rtsp')
    except OSError as error:
        return Resultado(CAIDA, f'No se pudo conectar ({error}).'[:200], tipo='rtsp')
    if respuesta.startswith('RTSP/1.0 200'):
        return Resultado(FUNCIONA, tipo='rtsp')
    return Resultado(CAIDA, f'El servidor RTSP respondió: {respuesta.splitlines()[0] if respuesta else "nada"}'[:200],
                     tipo='rtsp')


def _conviene_vlc_primero(url, tipo):
    """Los archivos directos de paneles IPTV suelen requerir un reproductor conocido."""
    ruta = urlsplit(url).path.lower()
    return tipo == 'directo' or ruta.endswith(_EXTENSIONES_DE_VIDEO_DIRECTO) or _es_stream_de_xtream(url)


def _es_stream_de_xtream(url):
    """Una señal Xtream: /usuario/clave/id o /live|series|movie/usuario/clave/id.ext."""
    direccion = urlsplit(url)
    partes = [parte for parte in direccion.path.lower().split('/') if parte]
    con_prefijo = bool(partes and partes[0] in ('live', 'series', 'movie'))
    if con_prefijo:
        partes = partes[1:]
    if len(partes) != 3:
        return False
    identificador = partes[-1].rsplit('.', 1)[0]
    # Sin /live/, la forma se parece a cualquier ruta web de tres partes. Los
    # paneles que la usan (como iptvpremium:55577) se reconocen por su puerto.
    return bool(partes[0] and partes[1] and identificador.isdigit()
                and (con_prefijo or direccion.port is not None))


def url_xtream_para_reproductor(url):
    """
    La forma corta de un vivo Xtream (``/usuario/clave/id``) funciona en VLC,
    pero no le da a Android ninguna pista sobre el contenedor. Los mismos
    paneles exponen la forma canónica ``/live/usuario/clave/id.ts``; conservar
    la URL en la base y transformar solamente lo que recibe la app permite que
    ExoPlayer reconozca MPEG-TS sin tener que adivinarlo.

    Solo se transforma la forma inequívoca que usa un puerto explícito. Las
    películas y series ya vienen bajo /movie/ o /series/ y no se tocan.
    """
    direccion = urlsplit(url)
    partes = [parte for parte in direccion.path.split('/') if parte]
    if (direccion.port is None or len(partes) != 3 or not partes[-1].isdigit()):
        return url
    ruta = '/live/' + '/'.join((*partes[:2], f'{partes[-1]}.ts'))
    return direccion._replace(path=ruta).geturl()


_MENSAJE_XTREAM_SIN_VERIFICAR = (
    'El proveedor no permite comprobar esta señal desde el servidor; se cargará sin verificar.'
)


def _xtream_sin_verificar(user_agent=USER_AGENT_VLC):
    return Resultado(
        SIN_VERIFICAR, _MENSAJE_XTREAM_SIN_VERIFICAR,
        tipo='directo', user_agent=user_agent or USER_AGENT_VLC,
    )


def _probar_video_directo(url, cabeceras, a_fondo=False, intentos=3):
    """Los paneles Xtream son intermitentes: reintenta solo cuando agotan el tiempo."""
    for intento in range(intentos):
        resultado = _probar(url, cabeceras, a_fondo)
        if resultado.error != 'No respondió a tiempo.' or intento == intentos - 1:
            return resultado
        _esperar(.25)


def verificar_url(url, tipo='hls', user_agent='', referer='', a_fondo=False):
    if tipo == 'yt_video':
        from . import youtube
        return youtube.verificar_video(url)
    if tipo in ('youtube', 'pagina'):
        from . import paginas
        return paginas.verificar(url, youtube=tipo == 'youtube')
    esquema = urlsplit(url).scheme.lower()
    if esquema.startswith('rtmp'):
        return Resultado(CAIDA, 'Es RTMP: la app todavía no reproduce ese formato.')
    if esquema in ('rtsp', 'rtsps'):
        return _verificar_rtsp(url)

    if _conviene_vlc_primero(url, tipo):
        agente = user_agent or USER_AGENT_VLC
        resultado = _probar_video_directo(
            url, _cabeceras_para_video_directo(agente, referer, a_fondo), a_fondo)
        if resultado.estado == FUNCIONA:
            if not user_agent:
                resultado.user_agent = USER_AGENT_VLC
            return resultado
        # Si el panel rechazó a VLC, todavía puede aceptar el reproductor de
        # la app. Para errores de red definitivos no se duplica la espera.
        if resultado.rechazo and not user_agent:
            return _probar_video_directo(
                url, _cabeceras_para_video_directo('', referer, a_fondo), a_fondo)
        if resultado.error == 'No respondió a tiempo.' and _es_stream_de_xtream(url):
            # Algunos proveedores reproducen en VLC y en la app, pero bloquean
            # las IP de datacenter para impedir restreaming. El VPS no puede
            # afirmar que el archivo esté caído: se carga sin verificar y la
            # app lo pide directamente desde la conexión del cliente.
            return _xtream_sin_verificar(agente)
        return resultado

    resultado = _probar(url, cabeceras_para(user_agent, referer), a_fondo)
    if resultado.estado == CAIDA and resultado.rechazo and not user_agent:
        como_vlc = _probar(url, cabeceras_para(USER_AGENT_VLC, referer), a_fondo)
        if como_vlc.estado == FUNCIONA:
            como_vlc.user_agent = USER_AGENT_VLC
            return como_vlc
    if resultado.es_pagina:
        # Una página web: puede ser de un sitio de videos que yt-dlp sabe leer
        from . import paginas
        en_la_pagina = paginas.verificar(url, youtube=False)
        if en_la_pagina.estado == FUNCIONA:
            return en_la_pagina
    return resultado


def verificar_varias(fuentes, cabeceras=None, hasta=None, a_fondo=False, cancelado=None):
    """
    {url: tipo} -> {url: Resultado}. Verifica varias a la vez.
    `cabeceras`: {url: (user_agent, referer)} para las fuentes que tienen las suyas.
    `hasta`: momento (time.monotonic()) a partir del cual no se empieza ninguna
    más; las que no llegaron a probarse NO vienen en el resultado (quedan para
    la próxima tanda). Así un pedido del panel nunca tarda demasiado.
    `a_fondo`: la prueba a fondo (ver el principio).
    `cancelado`: función que permite cortar una tanda desde otro pedido. Las
    fuentes que todavía no empezaron quedan pendientes para poder retomarlas.
    """
    if not fuentes:
        return {}
    cabeceras = cabeceras or {}
    por_servidor = {}
    servidores_xtream_bloqueados = set()
    candado = threading.Lock()
    # Si una tanda trae MKV/MP4 de un panel, todo ese host se prueba de a uno.
    # Muchas cuentas Xtream permiten una sola reproducción simultánea: con dos,
    # una conexión funciona y la otra queda esperando hasta el timeout.
    servidores_con_video_directo = {
        (urlsplit(url).hostname or '').lower()
        for url, tipo in fuentes.items()
        if _conviene_vlc_primero(url, tipo)
    }

    def turno(url):
        servidor = (urlsplit(url).hostname or '').lower()
        limite = POR_SERVIDOR_DIRECTO if servidor in servidores_con_video_directo else POR_SERVIDOR
        with candado:
            return por_servidor.setdefault(servidor, threading.Semaphore(limite))

    def una(par):
        url, tipo = par
        with turno(url):
            if cancelado and cancelado():
                return None
            if hasta is not None and time.monotonic() >= hasta:
                return None
            servidor = (urlsplit(url).hostname or '').lower()
            if _es_stream_de_xtream(url):
                with candado:
                    bloqueado = servidor in servidores_xtream_bloqueados
                if bloqueado:
                    return _xtream_sin_verificar(cabeceras.get(url, ('', ''))[0])
            resultado = verificar_url(url, tipo, *cabeceras.get(url, ('', '')), a_fondo=a_fondo)
            if (resultado.estado == SIN_VERIFICAR and resultado.error == _MENSAJE_XTREAM_SIN_VERIFICAR
                    and _es_stream_de_xtream(url)):
                with candado:
                    servidores_xtream_bloqueados.add(servidor)
            return resultado

    with ThreadPoolExecutor(max_workers=HILOS) as hilos:
        resultados = dict(zip(fuentes, hilos.map(una, fuentes.items())))
    return {url: resultado for url, resultado in resultados.items() if resultado is not None}
