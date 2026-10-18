"""
Verificación de fuentes, importación de a tandas y pantallas del panel.
Nunca sale a internet: se reemplaza la descarga (o el verificador entero)
por uno de mentira.
"""

import threading
import time
import urllib.error
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from api import tokens
from canales import paginas, verificacion
from canales.models import Canal, EntradaImportada, Fuente, Importacion
from canales.servicios import (crear_importacion, importar_m3u, procesar_lote, verificar_fuentes_guardadas,
                               verificar_lote_de_fuentes)
from canales.verificacion import CAIDA, FUNCIONA, SIN_VERIFICAR, USER_AGENT_VLC, Resultado
from core import trabajos
from usuarios.models import Rol, Usuario

LISTA = '''#EXTM3U
#EXTINF:-1 tvg-id="Canal26.ar" group-title="Noticias",Canal 26
https://anda/c26.m3u8
#EXTINF:-1 group-title="Noticias",Telemax
https://caida/telemax.m3u8
#EXTINF:-1,Encuentro
https://www.youtube.com/user/encuentro/live
'''

TS = (b'\x47' + b'\x00' * 187) * 4   # cuatro paquetes MPEG-TS


def verificador_falso(fuentes, cabeceras=None, hasta=None, a_fondo=False, cancelado=None):
    """Funciona todo lo de 'anda', se cae todo lo de 'caida', YouTube sin verificar."""
    def uno(url, tipo):
        if tipo == 'youtube':
            return Resultado(SIN_VERIFICAR, 'YouTube', tipo='youtube')
        return Resultado(FUNCIONA, tipo='hls') if '//anda' in url else Resultado(CAIDA, 'No respondió a tiempo.')
    return {url: uno(url, tipo) for url, tipo in fuentes.items()}


class VerificarUrlTests(TestCase):

    def respuestas(self, por_url):
        """
        Reemplaza la descarga: devuelve el contenido según la dirección (o
        lanza el error). Anota qué se pidió y con qué cabeceras en self.pedidos.
        """
        self.pedidos = []

        def descargar(url, cabeceras, maximo=None):
            self.pedidos.append((url, cabeceras))
            valor = por_url[url]
            if callable(valor):
                valor = valor(cabeceras)
            if isinstance(valor, Exception):
                raise valor
            return (valor.encode() if isinstance(valor, str) else valor), url, ''
        return mock.patch.object(verificacion, '_descargar', side_effect=descargar)

    def test_lista_simple(self):
        with self.respuestas({'https://x/a.m3u8': '#EXTM3U\n#EXTINF:6,\nseg1.ts\n', 'https://x/seg1.ts': 'video'}):
            resultado = verificacion.verificar_url('https://x/a.m3u8')
        self.assertEqual((resultado.estado, resultado.tipo), (FUNCIONA, 'hls'))
        # Se presenta como el reproductor de la app
        self.assertEqual(self.pedidos[0][1]['User-Agent'], verificacion.USER_AGENT_REPRODUCTOR)

    def test_prueba_el_pedazo_de_video_mas_reciente(self):
        lista = '#EXTM3U\n#EXTINF:6,\nviejo.ts\n#EXTINF:6,\nnuevo.ts\n'
        with self.respuestas({'https://x/a.m3u8': lista, 'https://x/nuevo.ts': 'video'}):
            self.assertEqual(verificacion.verificar_url('https://x/a.m3u8').estado, FUNCIONA)
        self.assertEqual(self.pedidos[-1][0], 'https://x/nuevo.ts')

    def test_lista_bien_pero_el_video_rechazado(self):
        """El caso de América: entrega la lista, pero el video responde 403 (también como VLC)."""
        rechazo = urllib.error.HTTPError('https://x/seg1.ts', 403, 'no', {}, None)
        with self.respuestas({'https://x/a.m3u8': '#EXTM3U\n#EXTINF:6,\nseg1.ts\n', 'https://x/seg1.ts': rechazo}):
            resultado = verificacion.verificar_url('https://x/a.m3u8')
        self.assertEqual((resultado.estado, resultado.error), (CAIDA, 'El canal no entrega el video al reproductor (error 403).'))

    def test_usa_las_cabeceras_propias_de_la_fuente(self):
        with self.respuestas({'https://x/a.m3u8': '#EXTM3U\n#EXTINF:6,\nseg1.ts\n', 'https://x/seg1.ts': 'video'}):
            verificacion.verificar_url('https://x/a.m3u8', 'hls', 'MiReproductor/1.0', 'https://canal.com/')
        self.assertEqual(self.pedidos[0][1], {'User-Agent': 'MiReproductor/1.0', 'Referer': 'https://canal.com/'})

    def test_lista_vacia(self):
        with self.respuestas({'https://x/a.m3u8': '#EXTM3U\n#EXT-X-VERSION:3\n'}):
            self.assertEqual(verificacion.verificar_url('https://x/a.m3u8').estado, CAIDA)

    def test_lista_maestra_prueba_la_primera_calidad(self):
        maestra = '#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=800000\n720/index.m3u8\n'
        caida = urllib.error.HTTPError('https://x/live/720/index.m3u8', 404, 'no', {}, None)
        with self.respuestas({'https://x/live/master.m3u8': maestra, 'https://x/live/720/index.m3u8': caida}):
            resultado = verificacion.verificar_url('https://x/live/master.m3u8')
        self.assertEqual((resultado.estado, resultado.error),
                         (CAIDA, 'El servidor respondió con error 404 al pedir la lista.'))

    def test_video_directo_como_vlc(self):
        """Las listas "Xtream" (sin extensión) mandan MPEG-TS directo: funciona, y se avisa el formato."""
        with self.respuestas({'http://x:8080/u/p/57485': TS}):
            resultado = verificacion.verificar_url('http://x:8080/u/p/57485')
        self.assertEqual((resultado.estado, resultado.tipo), (FUNCIONA, 'directo'))

    def test_archivo_directo_de_xtream_prueba_vlc_primero(self):
        """Hay paneles que dejan esperando al navegador pero entregan el MKV a VLC."""
        def segun_quien(cabeceras):
            if cabeceras['User-Agent'] == USER_AGENT_VLC:
                return b'\x1aE\xdf\xa3video'
            return urllib.error.URLError(TimeoutError())

        url = 'http://x:8080/series/usuario/clave/446965.mkv'
        with self.respuestas({url: segun_quien}):
            resultado = verificacion.verificar_url(url, 'directo')
        self.assertEqual((resultado.estado, resultado.tipo, resultado.user_agent),
                         (FUNCIONA, 'directo', USER_AGENT_VLC))
        self.assertEqual(len(self.pedidos), 1)
        self.assertEqual(self.pedidos[0][1]['User-Agent'], USER_AGENT_VLC)
        self.assertEqual(self.pedidos[0][1]['Range'], 'bytes=0-65535')

    def test_archivo_directo_pide_un_rango_como_el_reproductor(self):
        def solo_con_rango(cabeceras):
            if cabeceras.get('Range') == 'bytes=0-65535':
                return b'\x1aE\xdf\xa3video'
            return urllib.error.URLError(TimeoutError())

        url = 'http://x:8080/series/usuario/clave/446961.mkv'
        with self.respuestas({url: solo_con_rango}):
            resultado = verificacion.verificar_url(url, 'directo')
        self.assertEqual(resultado.estado, FUNCIONA)

    def test_archivo_directo_reintenta_timeouts_intermitentes(self):
        intentos = 0

        def intermitente(_cabeceras):
            nonlocal intentos
            intentos += 1
            if intentos < 3:
                return urllib.error.URLError(TimeoutError())
            return b'\x1aE\xdf\xa3video'

        url = 'http://x:8080/series/usuario/clave/446961.mkv'
        with self.respuestas({url: intermitente}), mock.patch.object(verificacion, '_esperar'):
            resultado = verificacion.verificar_url(url, 'directo')
        self.assertEqual(resultado.estado, FUNCIONA)
        self.assertEqual(intentos, 3)

    def test_xtream_bloqueado_desde_el_vps_se_carga_sin_verificar(self):
        timeout = urllib.error.URLError(TimeoutError())
        url = 'http://panel:8080/series/usuario/clave/446961.mkv'
        with self.respuestas({url: timeout}), mock.patch.object(verificacion, '_esperar'):
            resultado = verificacion.verificar_url(url, 'directo')
        self.assertEqual((resultado.estado, resultado.tipo, resultado.user_agent),
                         (SIN_VERIFICAR, 'directo', USER_AGENT_VLC))
        self.assertIn('se cargará sin verificar', resultado.error)
        self.assertEqual(len(self.pedidos), 3)

    def test_un_mkv_comun_que_no_responde_sigue_caido(self):
        timeout = urllib.error.URLError(TimeoutError())
        url = 'https://cdn.ejemplo.com/pelicula.mkv'
        with self.respuestas({url: timeout}), mock.patch.object(verificacion, '_esperar'):
            resultado = verificacion.verificar_url(url, 'directo')
        self.assertEqual(resultado.estado, CAIDA)

    def test_detectar_formato(self):
        self.assertEqual(verificacion.detectar_formato(b'\xef\xbb\xbf#EXTM3U\n'), 'hls')
        self.assertEqual(verificacion.detectar_formato(b'<?xml?><MPD xmlns="x">'), 'dash')
        self.assertEqual(verificacion.detectar_formato(b'\x00' * 5 + TS), 'directo')
        self.assertEqual(verificacion.detectar_formato(b'\x00\x00\x00\x18ftypmp42'), 'directo')
        self.assertEqual(verificacion.detectar_formato(b'cualquier cosa', 'video/mp2t'), 'directo')
        self.assertEqual(verificacion.detectar_formato(b'<html>Hola</html>', 'text/html'), '')

    def test_si_rechaza_al_navegador_prueba_como_vlc(self):
        def segun_quien(cabeceras):
            if cabeceras['User-Agent'] == USER_AGENT_VLC:
                return TS
            return urllib.error.HTTPError('http://x/1', 403, 'no', {}, None)
        with self.respuestas({'http://x/1': segun_quien}):
            resultado = verificacion.verificar_url('http://x/1')
        self.assertEqual((resultado.estado, resultado.user_agent), (FUNCIONA, USER_AGENT_VLC))

    def test_pagina_web_en_vez_de_video(self):
        with self.respuestas({'https://x/a.m3u8': '<html>Not found</html>'}):
            resultado = verificacion.verificar_url('https://x/a.m3u8')
        self.assertEqual((resultado.estado, resultado.error), (CAIDA, 'Responde, pero con una página web, no con video.'))

    def test_tiempo_agotado(self):
        with self.respuestas({'https://x/a.m3u8': urllib.error.URLError(TimeoutError())}):
            self.assertEqual(verificacion.verificar_url('https://x/a.m3u8').error, 'No respondió a tiempo.')
        self.assertEqual(len(self.pedidos), 1)   # un tiempo agotado no se reintenta como VLC

    def test_rtmp_no_sirve(self):
        self.assertEqual(verificacion.verificar_url('rtmp://x/vivo').estado, CAIDA)

    def test_youtube_y_paginas_se_verifican_con_yt_dlp(self):
        with mock.patch.object(paginas, '_extraer', return_value={'id': 'abc', 'live_status': 'is_live'}):
            resultado = verificacion.verificar_url('https://www.youtube.com/@tn/live', 'youtube')
        self.assertEqual((resultado.estado, resultado.tipo), (FUNCIONA, 'youtube'))
        no_vivo = Exception('ERROR: [youtube] xyz: The channel is not currently live')
        with mock.patch.object(paginas, '_extraer', side_effect=no_vivo):
            resultado = verificacion.verificar_url('https://www.youtube.com/@tn/live', 'youtube')
        self.assertEqual((resultado.estado, resultado.error), (CAIDA, 'El canal no está transmitiendo en vivo ahora.'))
        robot = Exception("ERROR: Sign in to confirm you are not a bot")
        with mock.patch.object(paginas, '_extraer', side_effect=robot):
            self.assertEqual(verificacion.verificar_url('https://youtu.be/x', 'youtube').estado, SIN_VERIFICAR)

    def test_una_pagina_web_con_video_adentro(self):
        con_video = {'url': 'https://cdn/x.m3u8', 'protocol': 'm3u8'}
        with self.respuestas({'https://sitio.com/vivo': '<!DOCTYPE html><html>...'}), \
                mock.patch.object(paginas, '_extraer', return_value=con_video):
            resultado = verificacion.verificar_url('https://sitio.com/vivo')
        self.assertEqual((resultado.estado, resultado.tipo), (FUNCIONA, 'pagina'))

    def test_resolver_una_pagina(self):
        informacion = {'url': 'https://cdn/x.m3u8', 'protocol': 'm3u8_native',
                       'http_headers': {'User-Agent': 'UA', 'Accept': '*/*', 'Referer': 'https://twitch.tv/'}}
        with mock.patch.object(paginas, '_extraer', return_value=informacion):
            resuelto = paginas.resolver('https://www.twitch.tv/canal')
        self.assertEqual((resuelto.url, resuelto.tipo), ('https://cdn/x.m3u8', 'hls'))
        self.assertEqual(resuelto.cabeceras, {'User-Agent': 'UA', 'Referer': 'https://twitch.tv/'})

    def test_varias_a_la_vez(self):
        with mock.patch.object(verificacion, 'verificar_url', side_effect=lambda url, tipo, *cabeceras, **_: Resultado(FUNCIONA)):
            resultados = verificacion.verificar_varias({'https://a': 'hls', 'https://b': 'hls'})
        self.assertEqual(set(resultados), {'https://a', 'https://b'})

    def test_varias_directas_del_mismo_servidor_se_prueban_de_a_una(self):
        activas = 0
        maximo = 0
        candado = threading.Lock()

        def probar(*_args, **_kwargs):
            nonlocal activas, maximo
            with candado:
                activas += 1
                maximo = max(maximo, activas)
            time.sleep(.02)
            with candado:
                activas -= 1
            return Resultado(FUNCIONA)

        fuentes = {f'http://panel:8080/series/u/p/{numero}.mkv': 'directo' for numero in range(4)}
        with mock.patch.object(verificacion, 'verificar_url', side_effect=probar):
            verificacion.verificar_varias(fuentes)
        self.assertEqual(maximo, 1)

    def test_si_el_vps_esta_bloqueado_no_espera_por_cada_capitulo(self):
        bloqueada = Resultado(
            SIN_VERIFICAR, verificacion._MENSAJE_XTREAM_SIN_VERIFICAR,
            tipo='directo', user_agent=USER_AGENT_VLC,
        )
        fuentes = {f'http://panel:8080/series/u/p/{numero}.mkv': 'directo' for numero in range(4)}
        with mock.patch.object(verificacion, 'verificar_url', return_value=bloqueada) as verificar_url:
            resultados = verificacion.verificar_varias(fuentes)
        self.assertEqual(verificar_url.call_count, 1)
        self.assertEqual({resultado.estado for resultado in resultados.values()}, {SIN_VERIFICAR})

    def test_pasado_el_tiempo_no_empieza_mas(self):
        with mock.patch.object(verificacion, 'verificar_url', return_value=Resultado(FUNCIONA)) as verificar_url:
            resultados = verificacion.verificar_varias({'https://a': 'hls'}, hasta=time.monotonic() - 1)
        self.assertEqual(resultados, {})
        verificar_url.assert_not_called()

    def test_cancelada_no_empieza_mas(self):
        with mock.patch.object(verificacion, 'verificar_url', return_value=Resultado(FUNCIONA)) as verificar_url:
            resultados = verificacion.verificar_varias({'https://a': 'hls'}, cancelado=lambda: True)
        self.assertEqual(resultados, {})
        verificar_url.assert_not_called()


def _paquete_ts(pid, carga, inicio_de_tabla=True):
    """Un paquete MPEG-TS de 188 bytes (cabecera + pointer field + la tabla, relleno con 0xFF)."""
    cabecera = bytes([0x47, (0x40 if inicio_de_tabla else 0) | (pid >> 8), pid & 0xFF, 0x10])
    cuerpo = (b'\x00' + carga) if inicio_de_tabla else carga
    return (cabecera + cuerpo).ljust(188, b'\xff')


def _video_ts(tipo_de_video):
    """Un pedazo de MPEG-TS: PAT (programa 1 en el PID 0x100) + PMT (video del tipo pedido + audio AAC)."""
    pat = bytes([0x00, 0xB0, 13, 0x00, 0x01, 0xC1, 0x00, 0x00, 0x00, 0x01, 0xE1, 0x00]) + b'CRC!'
    pistas = bytes([tipo_de_video, 0xE1, 0x01, 0xF0, 0x00, 0x0F, 0xE1, 0x02, 0xF0, 0x00])
    pmt = bytes([0x02, 0xB0, 9 + len(pistas) + 4, 0x00, 0x01, 0xC1, 0x00, 0x00, 0xE1, 0x01, 0xF0, 0x00])
    return _paquete_ts(0, pat) + _paquete_ts(0x100, pmt + pistas + b'CRC!') + _paquete_ts(0x1FFF, b'', False)


class CodecTests(TestCase):
    """El códec del video: el aparato lo compara con los que sabe mostrar."""

    def test_mpeg_ts(self):
        self.assertEqual(verificacion.detectar_codec(_video_ts(0x1B)), 'h264')
        self.assertEqual(verificacion.detectar_codec(_video_ts(0x24)), 'h265')
        self.assertEqual(verificacion.detectar_codec(_video_ts(0x02)), 'mpeg2')

    def test_mkv_y_mp4(self):
        self.assertEqual(verificacion.detectar_codec(b'\x1aE\xdf\xa3...V_MPEGH/ISO/HEVC...'), 'h265')
        self.assertEqual(verificacion.detectar_codec(b'\x00\x00\x00\x18ftypisom...avc1...'), 'h264')
        self.assertEqual(verificacion.detectar_codec(b'cualquier cosa'), '')

    def test_lista_maestra_hls(self):
        texto = '#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=800000,CODECS="mp4a.40.2,hvc1.1.6.L93.B0"\nalta.m3u8\n'
        self.assertEqual(verificacion.codec_de_hls(texto), 'h265')
        self.assertEqual(verificacion.codec_de_hls('#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1\na.m3u8\n'), '')

    def test_video_de_10_bits(self):
        mp4 = b'\x00\x00\x00\x18ftypisom..avc1..'
        # MP4: la caja avcC con el perfil 110 (0x6E, High 10 o "Hi10P") o 100 (0x64, High: 8 bits)
        self.assertEqual(verificacion.detectar_codec(mp4 + b'avcC\x01\x6e\x00\x1e'), 'h264_10')
        self.assertEqual(verificacion.detectar_codec(mp4 + b'avcC\x01\x64\x00\x1e'), 'h264')
        # ...y la hvcC con Main 10 (2)
        self.assertEqual(verificacion.detectar_codec(b'\x00\x00\x00\x18ftyp..hvc1..hvcC\x01\x02\x20'), 'h265_10')
        # MKV: el CodecPrivate (63 A2 + tamaño) después del CodecID
        mkv = b'\x1aE\xdf\xa3..V_MPEG4/ISO/AVC\x63\xa2\x90\x01\x6e\x00\x1e'
        self.assertEqual(verificacion.detectar_codec(mkv), 'h264_10')
        # MPEG-TS: el SPS del video (00 00 01 67 + perfil)
        self.assertEqual(verificacion.detectar_codec(_video_ts(0x1B) + b'\x00\x00\x01\x67\x6e\x00\x1e\x00'), 'h264_10')
        self.assertEqual(verificacion.detectar_codec(_video_ts(0x1B) + b'\x00\x00\x01\x67\x4d\x00\x1e\x00'), 'h264')
        # HLS: el CODECS de la lista maestra
        maestra = '#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1,CODECS="{}"\na.m3u8\n'
        self.assertEqual(verificacion.codec_de_hls(maestra.format('avc1.6E0028,mp4a.40.2')), 'h264_10')
        self.assertEqual(verificacion.codec_de_hls(maestra.format('hvc1.2.4.L120.B0')), 'h265_10')
        self.assertEqual(verificacion.codec_de_hls(maestra.format('avc1.64001f')), 'h264')
        # Con varias calidades, la más compatible (el reproductor del aparato elige una que sabe mostrar)
        varias = ('#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=9,CODECS="hvc1.2.4.L150.B0,mp4a.40.2"\nhd.m3u8\n'
                  '#EXT-X-STREAM-INF:BANDWIDTH=3,CODECS="avc1.64001f,mp4a.40.2"\nsd.m3u8\n')
        self.assertEqual(verificacion.codec_de_hls(varias), 'h264')
        self.assertEqual(verificacion.codec_de_hls(varias.replace('avc1.64001f', 'hvc1.1.6.L93')), 'h265')

    def test_la_verificacion_lo_guarda(self):
        lista = '#EXTM3U\n#EXTINF:6,\nseg1.ts\n'
        datos = {'https://x/a.m3u8': lista.encode(), 'https://x/seg1.ts': _video_ts(0x02)}
        with mock.patch.object(verificacion, '_descargar', side_effect=lambda url, *_a, **_k: (datos[url], url, '')):
            resultado = verificacion.verificar_url('https://x/a.m3u8')
        self.assertEqual((resultado.estado, resultado.codec), (FUNCIONA, 'mpeg2'))
        # Y la API se lo manda a la app
        canal = Canal.objects.create(nombre='Canal 26')
        fuente = Fuente.objects.create(canal=canal, url='https://x/a.m3u8', estado=Fuente.Estado.FUNCIONA,
                                       codec=resultado.codec)
        from api.v1.serializers import FuenteSerializer
        self.assertEqual(FuenteSerializer(fuente).data['codec'], 'mpeg2')


class ImportarDeATandasTests(TestCase):

    def test_solo_agrega_las_que_funcionan(self):
        resultado = importar_m3u(LISTA, verificar=verificador_falso)
        self.assertEqual((resultado.funcionan, resultado.caidas, resultado.sin_verificar), (1, 1, 1))
        self.assertFalse(Canal.objects.filter(nombre='Telemax').exists())
        telemax = EntradaImportada.objects.get(nombre='Telemax')
        self.assertEqual((telemax.estado, telemax.motivo), (EntradaImportada.Estado.CAIDA, 'No respondió a tiempo.'))

    def test_de_a_tandas_con_avance(self):
        importacion = crear_importacion(LISTA, 'lista.m3u8')
        self.assertEqual(importacion.para_verificar, 3)
        avance = procesar_lote(importacion, verificador_falso, tamanio=2)
        self.assertEqual((avance['verificadas'], avance['pendientes'], avance['porcentaje'], avance['terminada']),
                         (2, 1, 67, False))
        avance = procesar_lote(importacion, verificador_falso, tamanio=2)
        self.assertEqual((avance['porcentaje'], avance['terminada'], avance['aptas'], avance['caidas']),
                         (100, True, 2, 1))
        self.assertEqual(Fuente.objects.count(), 0)   # probar no carga nada: hay que cargar las aptas
        importacion.refresh_from_db()
        self.assertIsNotNone(importacion.terminada)

    def test_lo_que_no_llego_a_probarse_queda_para_la_proxima(self):
        importacion = crear_importacion(LISTA, 'lista.m3u8')
        avance = procesar_lote(importacion, lambda fuentes, cabeceras=None, hasta=None: {})
        self.assertEqual(avance['pendientes'], 3)
        self.assertEqual(Fuente.objects.count(), 0)

    def test_guarda_el_formato_real_y_el_user_agent_que_anduvo(self):
        def como_vlc(fuentes, cabeceras=None, hasta=None):
            return {url: Resultado(FUNCIONA, tipo='directo', user_agent=USER_AGENT_VLC) for url in fuentes}
        importar_m3u('#EXTM3U\n#EXTINF:-1,Xtream\nhttp://x:8080/u/p/1\n', verificar=como_vlc)
        fuente = Fuente.objects.get()
        self.assertEqual((fuente.tipo, fuente.user_agent), (Fuente.Tipo.DIRECTO, USER_AGENT_VLC))

    def test_importa_xtream_aunque_el_vps_no_pueda_comprobarlo(self):
        lista = '#EXTM3U\n' + ''.join(
            f'#EXTINF:-1 group-title="SERIES",Show S01 E{numero:02}\n'
            f'http://panel:8080/series/usuario/clave/{numero}.mkv\n'
            for numero in range(1, 4)
        )
        importacion = crear_importacion(lista, 'serie.m3u')
        timeout = urllib.error.URLError(TimeoutError())
        with mock.patch.object(verificacion, '_descargar', side_effect=timeout), \
                mock.patch.object(verificacion, '_esperar'):
            avance = procesar_lote(importacion, verificacion.verificar_varias, tamanio=3, segundos=0)
        self.assertEqual((avance['aptas'], avance['caidas'], avance['rechazadas']), (3, 0, 0))
        self.assertEqual(set(importacion.entradas.values_list('user_agent', flat=True)), {USER_AGENT_VLC})

    def test_no_vuelve_a_verificar_lo_que_ya_estaba(self):
        importar_m3u(LISTA, verificar=verificador_falso)
        pedidas = []
        importar_m3u(LISTA, verificar=lambda fuentes, cabeceras=None, hasta=None: pedidas.append(fuentes) or {})
        # Solo pide la que no se había agregado (y como no responde nada, deja de insistir)
        self.assertEqual({url for pedido in pedidas for url in pedido}, {'https://caida/telemax.m3u8'})

    def test_la_app_no_muestra_canales_con_todas_las_fuentes_caidas(self):
        importar_m3u(LISTA, verificar=verificador_falso)
        Fuente.objects.filter(canal__nombre='Canal 26').update(estado=Fuente.Estado.CAIDA)
        cliente = APIClient()
        clave, _ = tokens.crear_token(Usuario.objects.create_user('cliente', None, 'x'))
        cliente.credentials(HTTP_AUTHORIZATION=f'Bearer {clave}')
        self.assertEqual(cliente.get(reverse('api_v1:canales')).json()['cantidad'], 0)


class VerificarGuardadasTests(TestCase):

    def setUp(self):
        importar_m3u(LISTA)   # sin verificar: quedan las 3

    def test_verificar_todas_revive_y_corrige_el_formato(self):
        Fuente.objects.filter(url='https://caida/telemax.m3u8').update(estado=Fuente.Estado.CAIDA)

        def ahora_anda_todo(fuentes, cabeceras=None, hasta=None):
            return {url: Resultado(FUNCIONA, tipo='directo') if tipo != 'youtube' else Resultado(SIN_VERIFICAR)
                    for url, tipo in fuentes.items()}

        resultado = verificar_fuentes_guardadas(ahora_anda_todo)
        self.assertEqual((resultado.revividas, resultado.funcionan), (1, 2))
        telemax = Fuente.objects.get(canal__nombre='Telemax')
        self.assertEqual((telemax.estado, telemax.tipo), (Fuente.Estado.FUNCIONA, Fuente.Tipo.DIRECTO))

    def test_de_a_tandas(self):
        primera = verificar_lote_de_fuentes(verificador_falso, tamanio=2)
        self.assertEqual((primera['verificadas'], primera['total'], primera['terminado']), (2, 3, False))
        segunda = verificar_lote_de_fuentes(verificador_falso, desde=primera['siguiente'], tamanio=2)
        self.assertEqual((segunda['porcentaje'], segunda['terminado']), (100, True))


@mock.patch('canales.views.verificar_varias', verificador_falso)
class PantallaCanalesTests(TestCase):
    URL = reverse('canales:inicio')

    def setUp(self):
        self.admin = Usuario.objects.create_user(
            'admin', None, 'x', rol=Rol.objects.create(nombre='Canales', permisos=['ver_canales', 'importar_canales']))
        self.solo_ve = Usuario.objects.create_user(
            'mira', None, 'x', rol=Rol.objects.create(nombre='Mira', permisos=['ver_canales']))
        self.client.force_login(self.admin)

    def subir(self, nombre='lista.m3u8', contenido=LISTA, **opciones):
        return self.client.post(self.URL, {'archivo': SimpleUploadedFile(nombre, contenido.encode()), **opciones})

    def test_subir_analiza_y_lleva_al_avance(self):
        respuesta = self.subir()
        importacion = Importacion.objects.get()
        self.assertRedirects(respuesta, reverse('canales:importacion', args=[importacion.pk]) + '?empezar=1')
        self.assertEqual(Canal.objects.count(), 0)   # todavía no verificó nada
        pagina = self.client.get(reverse('canales:importacion', args=[importacion.pk]))
        self.assertContains(pagina, 'Probar los 3 que faltan')
        self.assertContains(pagina, 'Telemax')

    def test_las_tandas_responden_el_avance(self):
        self.subir()
        importacion = Importacion.objects.get()
        datos = self.client.post(reverse('canales:importacion_lote', args=[importacion.pk])).json()
        self.assertEqual((datos['porcentaje'], datos['terminada'], datos['aptas']), (100, True, 2))
        pagina = self.client.get(reverse('canales:importacion', args=[importacion.pk]), {'estado': 'caida'})
        self.assertContains(pagina, 'No respondió a tiempo.')
        self.assertContains(pagina, 'Volver a probar las que fallaron')
        # Probar no cargó nada: las aptas se cargan con otro botón
        self.assertEqual(Canal.objects.count(), 0)
        self.assertContains(pagina, 'Cargar los 2 que pasaron')
        datos = self.client.post(reverse('canales:importacion_cargar', args=[importacion.pk])).json()
        self.assertEqual((datos['aptas'], datos['agregadas']), (0, 2))
        self.assertEqual(set(Canal.objects.values_list('nombre', flat=True)), {'Canal 26', 'Encuentro'})
        pagina = self.client.get(reverse('canales:importacion', args=[importacion.pk]))
        self.assertContains(pagina, 'Ya se cargaron 2.')

    def test_cancelar_detiene_el_trabajo_y_permite_retomarlo(self):
        self.subir()
        importacion = Importacion.objects.get()
        clave = f'importacion:{importacion.pk}'
        trabajos.turno(clave, 'Probando la lista', self.admin)
        pagina = self.client.get(reverse('canales:importacion', args=[importacion.pk]))
        self.assertContains(pagina, 'data-accion="cancelar-prueba"')

        respuesta = self.client.post(reverse('canales:importacion_cancelar', args=[importacion.pk]))
        self.assertEqual(respuesta.json(), {'cancelada': True})
        self.assertTrue(trabajos.cancelado(clave))
        self.assertFalse(trabajos.en_curso().exists())

        # Retomar crea un turno nuevo y sigue desde las entradas pendientes.
        datos = self.client.post(reverse('canales:importacion_lote', args=[importacion.pk])).json()
        self.assertTrue(datos['terminada'])
        self.assertNotIn('cancelada', datos)

    def test_pestanias_para_ver_las_que_pasaron(self):
        self.subir()
        importacion = Importacion.objects.get()
        url = reverse('canales:importacion', args=[importacion.pk])
        # Antes de probar ya está la pestaña "Pasaron" (vacía), y dice qué falta
        self.assertContains(self.client.get(url), 'Pasaron (falta cargar) <span class="pestania-numero">0</span>')
        self.assertContains(self.client.get(url, {'estado': 'apta'}), 'Todavía faltan probar 3.')
        self.client.post(reverse('canales:importacion_lote', args=[importacion.pk]))
        url = reverse('canales:importacion', args=[importacion.pk])
        pagina = self.client.get(url, {'idioma': 'es'})
        # Solo las pestañas que tienen algo, con cuántos hay; cambiar de pestaña conserva los otros filtros
        self.assertContains(pagina, 'Pasaron (falta cargar) <span class="pestania-numero">2</span>')
        self.assertContains(pagina, 'No responden <span class="pestania-numero">1</span>')
        self.assertNotContains(pagina, 'Ya estaban <span')
        self.assertContains(pagina, 'href="?idioma=es&amp;estado=apta#entradas"')
        self.assertContains(pagina, 'Cargar los 2 que pasaron')
        aptas = self.client.get(url, {'estado': 'apta'})
        self.assertContains(aptas, 'Canal 26')
        self.assertContains(aptas, 'Encuentro')
        self.assertNotContains(aptas, 'Telemax')
        self.assertContains(aptas, 'class="activa" aria-current="page">Pasaron')
        # La dirección completa, sin cortar
        caidas = self.client.get(url, {'estado': 'caida'})
        self.assertContains(caidas, '<div class="direccion">https://caida/telemax.m3u8</div>')

    def test_elegir_a_mano_que_se_carga_y_que_no(self):
        self.subir()
        importacion = Importacion.objects.get()
        self.client.post(reverse('canales:importacion_lote', args=[importacion.pk]))
        entrada = {e.nombre: e for e in importacion.entradas.all()}
        url, elegir = reverse('canales:importacion', args=[importacion.pk]), reverse('canales:importacion_elegir',
                                                                                     args=[importacion.pk])
        pagina = self.client.get(url)
        self.assertContains(pagina, f'name="no_cargar_una" value="{entrada["Canal 26"].pk}"')
        self.assertContains(pagina, f'name="cargar_una" value="{entrada["Telemax"].pk}"')

        # Canal 26 pasó, pero no interesa; Telemax no respondió, pero se quiere igual
        respuesta = self.client.post(elegir, {'no_cargar_una': entrada['Canal 26'].pk, 'volver': f'{url}?estado=apta'})
        self.assertRedirects(respuesta, f'{url}?estado=apta')
        self.client.post(elegir, {'cargar_una': entrada['Telemax'].pk})
        estados = dict(importacion.entradas.values_list('nombre', 'estado'))
        Estado = EntradaImportada.Estado
        self.assertEqual(estados, {'Canal 26': Estado.DESCARTADA, 'Telemax': Estado.APTA, 'Encuentro': Estado.APTA})
        self.assertTrue(importacion.entradas.get(nombre='Canal 26').motivo.startswith('Descartada a mano'))

        self.client.post(reverse('canales:importacion_cargar', args=[importacion.pk]))
        self.assertEqual(set(Canal.objects.values_list('nombre', flat=True)), {'Telemax', 'Encuentro'})
        # La que no respondía entra sin verificar: la app la intenta y la verificación la vuelve a probar
        self.assertEqual(Canal.objects.get(nombre='Telemax').fuentes.get().estado, Fuente.Estado.SIN_VERIFICAR)

    def test_elegir_varias_cambia_solo_las_que_corresponden(self):
        self.subir()
        importacion = Importacion.objects.get()
        self.client.post(reverse('canales:importacion_lote', args=[importacion.pk]))
        todas = list(importacion.entradas.values_list('pk', flat=True))
        elegir = reverse('canales:importacion_elegir', args=[importacion.pk])
        respuesta = self.client.post(elegir, {'accion': 'cargar', 'entrada': todas}, follow=True)
        self.assertContains(respuesta, '1 pasaron a «Pasaron»')   # solo Telemax: las otras ya habían pasado
        respuesta = self.client.post(elegir, {'accion': 'descartar', 'entrada': todas}, follow=True)
        self.assertContains(respuesta, '3 pasaron a «Descartados»')
        # Quien solo mira no puede
        self.client.force_login(self.solo_ve)
        self.assertEqual(self.client.post(elegir, {'accion': 'cargar', 'entrada': todas}).status_code, 403)
        self.assertNotContains(self.client.get(reverse('canales:importacion', args=[importacion.pk])),
                               'name="cargar_una"')

    def test_acepta_un_zip(self):
        import io
        import zipfile
        archivo = io.BytesIO()
        with zipfile.ZipFile(archivo, 'w') as comprimido:
            comprimido.writestr('adentro/lista.m3u', LISTA)
        respuesta = self.client.post(self.URL, {'archivo': SimpleUploadedFile('lista.zip', archivo.getvalue())})
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Importacion.objects.get().total, 3)

    def test_rechaza_otros_archivos(self):
        self.assertContains(self.subir('foto.png'), 'Tiene que ser un archivo .m3u, .m3u8 o .zip.')
        self.assertContains(self.subir(contenido='hola'), 'No se encontró ningún canal')
        self.assertEqual(Importacion.objects.count(), 0)

    def test_verificar_todas_de_a_tandas(self):
        importar_m3u(LISTA)
        datos = self.client.post(reverse('canales:verificar_lote'), {'desde': 0}).json()
        self.assertEqual((datos['terminado'], datos['caidas']), (True, 1))

    def test_sin_permiso_de_importar_solo_ve(self):
        self.subir()
        importacion = Importacion.objects.get()
        self.client.force_login(self.solo_ve)
        respuesta = self.client.get(self.URL)
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, 'Subir y analizar')
        self.assertEqual(self.subir().status_code, 403)
        self.assertEqual(self.client.post(reverse('canales:verificar_lote')).status_code, 403)
        self.assertEqual(self.client.post(reverse('canales:importacion_lote', args=[importacion.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse('canales:importacion_cancelar', args=[importacion.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse('canales:organizar')).status_code, 200)
        self.assertEqual(self.client.post(reverse('canales:catalogo_quitar')).status_code, 403)

    def test_sin_permiso_de_ver(self):
        self.client.force_login(Usuario.objects.create_user('otro', None, 'x'))
        self.assertEqual(self.client.get(self.URL).status_code, 403)
        self.assertEqual(self.client.get(reverse('canales:catalogo')).status_code, 403)


class CatalogoTests(TestCase):
    """Los datos técnicos y los filtros que eran del catálogo: ahora en Organizar contenido."""
    URL = reverse('canales:organizar')

    def setUp(self):
        importar_m3u(LISTA + '#EXTINF:-1 group-title="USA | VIP-A",USA: NBC\nhttps://anda/nbc.m3u8\n',
                     verificar=verificador_falso)
        admin = Usuario.objects.create_user(
            'admin', None, 'x', rol=Rol.objects.create(nombre='Canales', permisos=['ver_canales', 'importar_canales']))
        self.client.force_login(admin)

    def test_muestra_los_canales_y_por_que_no_se_ven(self):
        Fuente.objects.filter(canal__nombre='Canal 26').update(estado=Fuente.Estado.CAIDA)
        respuesta = self.client.get(self.URL)
        self.assertContains(respuesta, 'Canal 26')
        self.assertContains(respuesta, 'Encuentro')
        self.assertContains(respuesta, 'Todas sus fuentes están caídas.')

    def test_filtrar_por_idioma(self):
        respuesta = self.client.get(self.URL, {'idioma': 'otro'})
        self.assertContains(respuesta, 'NBC')
        self.assertNotContains(respuesta, 'Canal 26')

    def test_cada_pestana_ofrece_solo_sus_categorias(self):
        from canales.models import Categoria
        series = Categoria.objects.create(nombre='SERIES | NETFLIX')
        Canal.objects.create(nombre='Lost S01 E01', contenido='serie', categoria=series)
        borrado = Canal.objects.create(nombre='Viejo', categoria=Categoria.objects.create(nombre='Borrada'))
        borrado.eliminar()
        en_vivo = [n['categoria'].nombre for n in self.client.get(self.URL).context['datos'].nodos if n['categoria']]
        self.assertNotIn('SERIES | NETFLIX', en_vivo)
        self.assertIn('Noticias', en_vivo)
        con_filtro = self.client.get(self.URL, {'idioma': 'es'}).context['datos'].nodos
        self.assertNotIn('Borrada', [n['categoria'].nombre for n in con_filtro if n['categoria']])

    def test_filtrar_por_estado(self):
        Fuente.objects.filter(canal__nombre='Canal 26').update(estado=Fuente.Estado.CAIDA)
        Canal.objects.filter(nombre='NBC').update(activo=False)
        caidos = self.client.get(self.URL, {'mostrar': 'caidos'})
        self.assertContains(caidos, 'Canal 26')
        self.assertNotContains(caidos, 'NBC')
        quitados = self.client.get(self.URL, {'mostrar': 'quitados'})
        self.assertContains(quitados, 'NBC')
        self.assertNotContains(quitados, 'Canal 26')

    def test_el_cuadro_editar_trae_los_datos_tecnicos(self):
        Fuente.objects.filter(canal__nombre='Canal 26').update(estado=Fuente.Estado.CAIDA, codec='mpeg2',
                                                               error='No respondió a tiempo.')
        respuesta = self.client.get(self.URL)
        self.assertContains(respuesta, '&quot;codec&quot;: &quot;mpeg2&quot;')
        self.assertContains(respuesta, 'a tiempo.')   # (en el JSON la tilde va escapada)
        self.assertContains(respuesta, '&quot;probada&quot;: &quot;')

    def test_la_direccion_vieja_lleva_a_organizar_con_los_filtros(self):
        respuesta = self.client.get(reverse('canales:catalogo'), {'contenido': 'pelicula', 'estado': 'fuera',
                                                                   'idioma': 'otro', 'q': 'nbc'})
        self.assertRedirects(respuesta, self.URL + '?contenido=pelicula&q=nbc&idioma=otro&mostrar=caidos',
                             fetch_redirect_response=False)
        self.assertRedirects(self.client.get(reverse('canales:series'), {'estado': 'en_app'}),
                             self.URL + '?contenido=serie&mostrar=app', fetch_redirect_response=False)

    def test_quitar_y_volver_a_mostrar(self):
        canal = Canal.objects.get(nombre='Canal 26')
        self.client.post(reverse('canales:catalogo_quitar'), {'canal': canal.pk, 'motivo': 'No interesa'})
        canal.refresh_from_db()
        self.assertEqual((canal.activo, canal.motivo_quitado), (False, 'No interesa'))
        self.client.post(reverse('canales:catalogo_mostrar'), {'canal': canal.pk})
        canal.refresh_from_db()
        self.assertTrue(canal.activo)

    def test_quitar_todos_los_del_filtro(self):
        respuesta = self.client.post(reverse('canales:catalogo_quitar'),
                                     {'todos_del_filtro': '1', 'idioma': 'otro', 'motivo': 'No está en español',
                                      'volver': '/canales/catalogo/?idioma=otro'})
        self.assertRedirects(respuesta, '/canales/catalogo/?idioma=otro', fetch_redirect_response=False)
        self.assertEqual(list(Canal.objects.filter(activo=False).values_list('nombre', flat=True)), ['NBC'])

    def test_volver_solo_a_este_sitio(self):
        respuesta = self.client.post(reverse('canales:catalogo_mostrar'), {'volver': 'https://otro-sitio.com/'})
        self.assertRedirects(respuesta, reverse('canales:organizar') + '?contenido=vivo', fetch_redirect_response=False)


@mock.patch('api.v1.canales.verificar_url')
class AvisoDeFallaTests(TestCase):
    """La app avisa que una fuente no anda; el servidor la vuelve a probar."""

    def setUp(self):
        cache.clear()
        importar_m3u(LISTA, verificar=verificador_falso)
        self.fuente = Fuente.objects.get(canal__nombre='Canal 26')
        self.app = APIClient()
        clave, _ = tokens.crear_token(Usuario.objects.create_user('cliente', None, 'x'))
        self.app.credentials(HTTP_AUTHORIZATION=f'Bearer {clave}')

    def avisar(self, fuente=None):
        return self.app.post(reverse('api_v1:fuente_falla', args=[(fuente or self.fuente).pk]))

    def test_si_al_servidor_tambien_le_falla_deja_de_mandarla(self, verificar_url):
        verificar_url.return_value = Resultado(CAIDA, 'No respondió a tiempo.')
        self.assertEqual(self.avisar().json()['estado'], CAIDA)
        self.assertEqual(self.app.get(reverse('api_v1:canales')).json()['cantidad'], 0)

    def test_si_al_servidor_le_anda_la_sigue_mandando(self, verificar_url):
        verificar_url.return_value = Resultado(FUNCIONA)
        self.assertEqual(self.avisar().json()['estado'], FUNCIONA)
        self.assertEqual(self.app.get(reverse('api_v1:canales')).json()['cantidad'], 1)

    def test_no_la_reprueba_muchas_veces_seguidas(self, verificar_url):
        verificar_url.return_value = Resultado(FUNCIONA)
        for _ in range(5):
            self.avisar()
        self.assertEqual(verificar_url.call_count, 1)

    def avisar_desde(self, quien, motivo='formato'):
        """Un aviso desde otra sesión (otro aparato)."""
        app = APIClient()
        clave, _ = tokens.crear_token(Usuario.objects.create_user(quien, None, 'x'))
        app.credentials(HTTP_AUTHORIZATION=f'Bearer {clave}')
        return app.post(reverse('api_v1:fuente_falla', args=[self.fuente.pk]),
                        {'motivo': motivo, 'detalle': 'Decoder init failed'}, format='json')

    def test_si_falla_en_varios_aparatos_se_oculta_aunque_al_servidor_le_ande(self, verificar_url):
        verificar_url.return_value = Resultado(FUNCIONA)
        # Con dos aparatos distintos alcanza (AVISOS_PARA_OCULTAR)
        self.assertEqual(self.avisar_desde('a').json()['estado'], FUNCIONA)
        self.assertEqual(self.avisar_desde('b').json()['estado'], CAIDA)
        self.assertEqual(self.app.get(reverse('api_v1:canales')).json()['cantidad'], 0)
        self.fuente.refresh_from_db()
        self.assertIn('no puede leer el formato', self.fuente.falla_en_aparatos)
        self.assertEqual(self.fuente.estado, FUNCIONA)   # para el servidor sigue andando
        # Pasado el tiempo de castigo, la app la vuelve a recibir
        Fuente.objects.filter(pk=self.fuente.pk).update(oculta_hasta=timezone.now() - timedelta(minutes=1))
        self.assertEqual(self.app.get(reverse('api_v1:canales')).json()['cantidad'], 1)

    def test_el_mismo_aparato_reintentando_no_la_oculta(self, verificar_url):
        verificar_url.return_value = Resultado(FUNCIONA)
        for _ in range(4):
            self.avisar()
        self.fuente.refresh_from_db()
        self.assertEqual(self.fuente.avisos_de_aparatos, 1)   # el de setUp cuenta una sola vez
        self.assertIsNone(self.fuente.oculta_desde)

    def test_solo_fuentes_que_la_app_recibe(self, verificar_url):
        apagada = Fuente.objects.get(canal__nombre='Encuentro')
        apagada.activa = False
        apagada.save()
        self.assertEqual(self.avisar(apagada).status_code, 404)
        verificar_url.assert_not_called()


class ResolverPaginaTests(TestCase):
    """La app pide la dirección real de una fuente de Twitch, Dailymotion..."""

    def setUp(self):
        cache.clear()
        importar_m3u('#EXTM3U\n#EXTINF:-1,Twitch\nhttps://www.twitch.tv/canal\n#EXTINF:-1,HLS\nhttps://x/a.m3u8\n')
        self.app = APIClient()
        clave, _ = tokens.crear_token(Usuario.objects.create_user('cliente', None, 'x'))
        self.app.credentials(HTTP_AUTHORIZATION=f'Bearer {clave}')

    def resolver(self, url):
        return self.app.get(reverse('api_v1:fuente_resolver', args=[Fuente.objects.get(url=url).pk]))

    def test_devuelve_la_direccion_real(self):
        resuelto = paginas.Resuelto('https://cdn/x.m3u8', 'hls', {'Referer': 'https://twitch.tv/'})
        with mock.patch.object(paginas, 'resolver', return_value=resuelto) as resolver:
            datos = self.resolver('https://www.twitch.tv/canal').json()
            self.resolver('https://www.twitch.tv/canal')   # la segunda vez usa la guardada
        self.assertEqual(datos, {'url': 'https://cdn/x.m3u8', 'tipo': 'hls',
                                 'cabeceras': {'Referer': 'https://twitch.tv/'}})
        self.assertEqual(resolver.call_count, 1)

    def test_si_no_se_puede_dice_por_que(self):
        error = paginas.NoSePudo('El canal no está transmitiendo en vivo ahora.')
        with mock.patch.object(paginas, 'resolver', side_effect=error):
            respuesta = self.resolver('https://www.twitch.tv/canal')
        self.assertEqual((respuesta.status_code, respuesta.json()['detalle']),
                         (422, 'El canal no está transmitiendo en vivo ahora.'))

    def test_solo_paginas(self):
        self.assertEqual(self.resolver('https://x/a.m3u8').status_code, 404)

    def test_tambien_un_cliente_que_entra_con_el_codigo(self):
        """Antes le daba 403: los canales de Twitch, Dailymotion... no le andaban a ningún cliente."""
        from decimal import Decimal

        from reventa import servicios as reventa
        juan = reventa.crear_revendedor('juan', 'Clave-segura-2026', precio_pantalla=Decimal('5000'))
        reventa.regalar_creditos(juan, 5)
        cliente = reventa.crear_cliente(juan, 'Ana')
        reventa.renovar(cliente, dispositivos=1)
        cliente.refresh_from_db()
        token = APIClient().post(reverse('api_v1:cliente_login'),
                                 {'codigo': cliente.codigo_legible, 'dispositivo': 'TV'}).json()['token']
        self.app.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        resuelto = paginas.Resuelto('https://cdn/x.m3u8', 'hls', {})
        with mock.patch.object(paginas, 'resolver', return_value=resuelto):
            respuesta = self.resolver('https://www.twitch.tv/canal')
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertEqual(respuesta.json()['url'], 'https://cdn/x.m3u8')


class EditarCanalTests(TestCase):

    def setUp(self):
        importar_m3u(LISTA, verificar=verificador_falso)
        self.canal = Canal.objects.get(nombre='Canal 26')
        self.url = reverse('canales:canal_editar', args=[self.canal.pk])
        admin = Usuario.objects.create_user(
            'admin', None, 'x', rol=Rol.objects.create(nombre='Canales', permisos=['ver_canales', 'importar_canales']))
        self.client.force_login(admin)

    def datos(self, **cambios):
        fuente = self.canal.fuentes.get()
        datos = {
            'nombre': 'Canal 26', 'logo': '', 'numero': '26', 'categoria': self.canal.categoria_id or '',
            'nueva_categoria': '', 'contenido': 'vivo', 'idioma': 'es', 'pais': 'ar', 'orden': 0, 'activo': 'on',
            'motivo_quitado': '', 'nueva_fuente': '',
            'fuentes-TOTAL_FORMS': 1, 'fuentes-INITIAL_FORMS': 1, 'fuentes-MIN_NUM_FORMS': 0,
            'fuentes-MAX_NUM_FORMS': 1000,
            'fuentes-0-id': fuente.pk, 'fuentes-0-prioridad': 1, 'fuentes-0-activa': 'on',
        }
        datos.update(cambios)
        return datos

    def test_se_ve(self):
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, 'Así se ve en la app')
        self.assertContains(respuesta, 'https://anda/c26.m3u8')

    def test_cambiar_nombre_logo_y_categoria_nueva(self):
        respuesta = self.client.post(self.url, self.datos(nombre='Canal 26 Noticias', logo='https://logos.ejemplo.com/nuevo.png',
                                                          nueva_categoria='Argentina'))
        self.assertRedirects(respuesta, reverse('canales:organizar') + '?contenido=vivo', fetch_redirect_response=False)
        self.canal.refresh_from_db()
        self.assertEqual((self.canal.nombre, self.canal.logo, self.canal.categoria.nombre, self.canal.pais),
                         ('Canal 26 Noticias', 'https://logos.ejemplo.com/nuevo.png', 'Argentina', 'AR'))

    @mock.patch('canales.views.verificar_url', return_value=Resultado(FUNCIONA, tipo='directo'))
    def test_agregar_una_fuente_y_borrar_otra(self, verificar_url):
        self.client.post(self.url, self.datos(**{'nueva_fuente': 'http://iptv.ejemplo.com:8080/u/p/9', 'fuentes-0-DELETE': 'on'}))
        fuente = self.canal.fuentes.get()
        self.assertEqual((fuente.url, fuente.tipo, fuente.estado), ('http://iptv.ejemplo.com:8080/u/p/9', 'directo', 'funciona'))

    def test_logo_invalido(self):
        respuesta = self.client.post(self.url, self.datos(logo='no es una direccion'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Canal.objects.get(pk=self.canal.pk).logo, '')

    def test_sin_permiso(self):
        self.client.force_login(Usuario.objects.create_user(
            'mira', None, 'x', rol=Rol.objects.create(nombre='Mira', permisos=['ver_canales'])))
        self.assertEqual(self.client.get(self.url).status_code, 403)


class ResumenYSeriesTests(TestCase):
    """El panel separa en vivo, películas y series; las series se agrupan como en la app."""

    def capitulo(self, nombre, estado=Fuente.Estado.FUNCIONA, contenido='serie'):
        canal = Canal.objects.create(nombre=nombre, contenido=contenido)
        Fuente.objects.create(canal=canal, url=f'https://x/{canal.pk}.mkv', tipo='directo', estado=estado)
        return canal

    def test_resumen_separado(self):
        from canales import consultas
        self.capitulo('Canal 26', contenido='vivo')
        self.capitulo('Matrix (1999)', contenido='pelicula')
        self.capitulo('Arrow S01 E01')
        self.capitulo('Arrow S01 E02', estado=Fuente.Estado.CAIDA)
        resumen = consultas.resumen()
        self.assertEqual(resumen['canales'], 1)   # antes sumaba también películas y capítulos
        series = {r['contenido']: r for r in resumen['por_contenido']}['serie']
        self.assertEqual((series['cargados'], series['en_la_app'], series['caidas']), (2, 1, 1))

    def test_series_agrupadas(self):
        from canales import consultas
        from canales.clasificar import episodio
        self.assertEqual(episodio('Arrow S02 E05 El regreso'), ('Arrow', 2, 5, 'El regreso'))
        self.assertEqual(episodio('The Office 1x05'), ('The Office', 1, 5, ''))
        self.assertEqual(episodio('Especial'), ('Especial', 1, None, ''))
        for nombre in ['Arrow S01 E02', 'Arrow S01 E01', 'arrow S02E01', 'Lucifer S01 E01']:
            self.capitulo(nombre)
        self.capitulo('Lucifer S01 E02', estado=Fuente.Estado.CAIDA)
        arrow, lucifer = consultas.series()
        self.assertEqual((arrow.nombre, arrow.numeros_de_temporada, arrow.cantidad), ('Arrow', [1, 2], 3))
        self.assertEqual([c.numero for c in arrow.temporadas[1]], [1, 2])   # ordenados
        self.assertEqual((lucifer.en_la_app, lucifer.fuera), (1, 1))
        self.capitulo('Rota S01 E01', estado=Fuente.Estado.CAIDA)
        self.assertEqual([s.nombre for s in consultas.series(estado='fuera')], ['Rota'])
