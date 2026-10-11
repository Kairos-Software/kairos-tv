"""
La prueba a fondo: qué trae cada video (sonido, idioma, resolución, cuánto
dura), si llega fluido y si la señal avanza, y qué se acepta al importar.
Nunca sale a internet: los videos se arman acá, byte a byte.
"""

import struct
from unittest import mock

from django.test import TestCase

from canales import analisis, verificacion
from canales.models import Canal, EntradaImportada, Importacion
from canales.servicios import crear_importacion, importar_m3u, juzgar, por_causa, procesar_lote
from canales.verificacion import CAIDA, FUNCIONA, Bajada, Resultado

Causa = EntradaImportada.Causa
Estado = EntradaImportada.Estado


# ── Videos de mentira ────────────────────────────────────────────────

class _Escritor:
    """Escribe bits y números Exp-Golomb (para armar el SPS de un video)."""

    def __init__(self):
        self.bits = []

    def poner(self, valor, cantidad):
        self.bits += [(valor >> i) & 1 for i in range(cantidad - 1, -1, -1)]
        return self

    def ue(self, valor):
        valor += 1
        largo = valor.bit_length()
        return self.poner(0, largo - 1).poner(valor, largo)

    def bytes(self):
        bits = self.bits + [1] + [0] * (-(len(self.bits) + 1) % 8)   # el bit de cierre
        return bytes(int(''.join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8))


def sps_h264(ancho, alto, perfil=66):
    """El SPS de un video H.264 de ancho x alto (con recorte si no es múltiplo de 16)."""
    e = _Escritor().poner(perfil, 8).poner(0, 8).poner(40, 8).ue(0)
    if perfil == 100:
        e.ue(1).ue(0).ue(0).poner(0, 1).poner(0, 1)   # 4:2:0, 8 bits, sin matrices
    e.ue(0).ue(0).ue(0).ue(1).poner(0, 1)
    bloques = -(-alto // 16)
    e.ue(ancho // 16 - 1).ue(bloques - 1).poner(1, 1).poner(1, 1)
    recorte = (bloques * 16 - alto) // 2
    e.poner(1 if recorte else 0, 1)
    if recorte:
        e.ue(0).ue(0).ue(0).ue(recorte)
    e.poner(0, 1)   # sin VUI
    return b'\x00\x00\x00\x01\x67' + e.bytes()


def sps_h265(ancho, alto):
    e = _Escritor().poner(0, 4).poner(0, 3).poner(1, 1).poner(0, 88).poner(93, 8)
    e.ue(0).ue(1).ue(ancho).ue(alto).poner(0, 1)
    return b'\x00\x00\x00\x01\x42\x01' + e.bytes()


def _paquete(pid, carga, inicio=True):
    cabecera = bytes([0x47, (0x40 if inicio else 0) | (pid >> 8), pid & 0xFF, 0x10])
    return (cabecera + carga).ljust(188, b'\xff')


def _pts(valor):
    return bytes([0x21 | ((valor >> 29) & 0x0E), (valor >> 22) & 0xFF, ((valor >> 14) & 0xFE) | 1,
                  (valor >> 7) & 0xFF, ((valor << 1) & 0xFE) | 1])


def video_ts(audios=(('spa', 0x0F),), segundos=2, sps=None, tipo_de_video=0x1B, relleno=0):
    """
    Un pedazo de MPEG-TS: PAT, PMT (video + las pistas de audio pedidas, con
    su idioma), dos paquetes de video separados `segundos` (con el SPS en el
    primero) y `relleno` paquetes vacíos (para que pese lo que haría falta).
    """
    pat = bytes([0x00, 0x00, 0xB0, 13, 0x00, 0x01, 0xC1, 0x00, 0x00, 0x00, 0x01, 0xE1, 0x00]) + b'CRC!'
    pistas = bytes([tipo_de_video, 0xE1, 0x01, 0xF0, 0x00])
    for n, (idioma, tipo) in enumerate(audios):
        descriptor = bytes([0x0A, 4]) + idioma.encode() + b'\x00' if idioma else b''
        pistas += bytes([tipo, 0xE1, 0x02 + n, 0xF0, len(descriptor)]) + descriptor
    pmt = bytes([0x00, 0x02, 0xB0, 9 + len(pistas) + 4, 0x00, 0x01, 0xC1, 0x00, 0x00, 0xE1, 0x01, 0xF0, 0x00])
    pes = b'\x00\x00\x01\xe0\x00\x00\x80\x80\x05'
    sps = sps if sps is not None else sps_h264(1920, 1080)
    return (_paquete(0, pat) + _paquete(0x100, pmt + pistas + b'CRC!')
            + _paquete(0x101, pes + _pts(0) + sps) + _paquete(0x101, pes + _pts(segundos * 90000))
            + _paquete(0x1FFF, b'', False) * relleno)


def _ebml(etiqueta, contenido):
    return etiqueta + bytes([0x80 | len(contenido)]) + contenido


def video_mkv(idioma_del_audio=b'ara', alto=1080):
    info = _ebml(b'\x2a\xd7\xb1', (1_000_000).to_bytes(3, 'big')) + _ebml(b'\x44\x89', struct.pack('>f', 5_400_000))
    video = (_ebml(b'\xd7', b'\x01') + _ebml(b'\x86', b'V_MPEG4/ISO/AVC')
             + _ebml(b'\xe0', _ebml(b'\xb0', (1920).to_bytes(2, 'big')) + _ebml(b'\xba', alto.to_bytes(2, 'big'))))
    audio = _ebml(b'\xd7', b'\x02') + _ebml(b'\x22\xb5\x9c', idioma_del_audio) + _ebml(b'\x86', b'A_AAC')
    pistas = _ebml(b'\xae', video) + _ebml(b'\xae', audio)
    return b'\x1aE\xdf\xa3\x84....' + info + b'\x16\x54\xae\x6b\x80' + pistas


def _idioma_mp4(codigo):
    return struct.pack('>H', sum((ord(letra) - 0x60) << corrido for letra, corrido in zip(codigo, (10, 5, 0))))


def video_mp4(con_audio=True):
    def pista(idioma, manejador, entrada):
        mdhd = b'mdhd' + b'\x00' * 12 + struct.pack('>II', 1000, 7_200_000) + _idioma_mp4(idioma) + b'\x00\x00'
        hdlr = b'hdlr' + b'\x00' * 8 + manejador
        return b'\x00\x00\x00\x00trak' + mdhd + hdlr + b'stsd' + b'\x00' * 8 + b'\x00\x00\x00\x00' + entrada

    avc1 = b'avc1' + b'\x00' * 24 + struct.pack('>HH', 1280, 720)
    mvhd = b'mvhd' + b'\x00' * 12 + struct.pack('>II', 1000, 7_200_000)
    moov = b'\x00\x00\x00\x00moov' + mvhd + pista('und', b'vide', avc1)
    if con_audio:
        moov += pista('spa', b'soun', b'mp4a' + b'\x00' * 28)
    return b'\x00\x00\x00\x18ftypisom' + b'\x00' * 12 + moov


# ── Qué trae cada video ──────────────────────────────────────────────

class AnalisisTests(TestCase):

    def test_mpeg_ts(self):
        resultado = analisis.analizar(video_ts(audios=(('spa', 0x0F), ('eng', 0x81))), 'h264')
        self.assertEqual((resultado.alto, resultado.con_audio, resultado.segundos), (1080, True, 2))
        self.assertEqual((resultado.audios, resultado.idiomas), (['aac', 'ac3'], ['es', 'en']))

    def test_mpeg_ts_sin_sonido(self):
        resultado = analisis.analizar(video_ts(audios=()), 'h264')
        self.assertIs(resultado.con_audio, False)

    def test_la_resolucion_por_el_sps(self):
        self.assertEqual(analisis.alto_en_el_video(sps_h264(1280, 720), 'h264'), 720)
        self.assertEqual(analisis.alto_en_el_video(sps_h264(1920, 1080, perfil=100), 'h264'), 1080)
        self.assertEqual(analisis.alto_en_el_video(sps_h264(320, 240), 'h264_10'), 240)
        self.assertEqual(analisis.alto_en_el_video(sps_h265(3840, 2160), 'h265'), 2160)
        self.assertEqual(analisis.alto_en_el_video(b'\x00\x00\x01\x67\xff', 'h264'), 0)   # roto: no se sabe
        self.assertEqual(analisis.alto_en_el_video(sps_h264(1280, 720), 'mpeg2'), 0)

    def test_mkv(self):
        resultado = analisis.analizar(video_mkv())
        self.assertEqual((resultado.alto, resultado.con_audio, resultado.audios, resultado.idiomas),
                         (1080, True, ['aac'], ['ar']))
        self.assertAlmostEqual(resultado.duracion, 5400)

    def test_mp4(self):
        resultado = analisis.analizar(video_mp4())
        self.assertEqual((resultado.alto, resultado.con_audio, resultado.audios, resultado.idiomas),
                         (720, True, ['aac'], ['es']))
        self.assertEqual(resultado.duracion, 7200)
        self.assertIs(analisis.analizar(video_mp4(con_audio=False)).con_audio, False)
        # Con el índice al final no se sabe nada (y no se dice que no tiene sonido)
        self.assertIsNone(analisis.analizar(b'\x00\x00\x00\x18ftypisom' + b'\x00' * 100).con_audio)

    def test_lista_maestra(self):
        maestra = analisis.de_la_maestra(
            '#EXTM3U\n#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="a",LANGUAGE="es-419",URI="es.m3u8"\n'
            '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="a",LANGUAGE="en",URI="en.m3u8"\n'
            '#EXT-X-STREAM-INF:BANDWIDTH=1,RESOLUTION=640x360\nbaja.m3u8\n'
            '#EXT-X-STREAM-INF:BANDWIDTH=2,RESOLUTION=1920x1080\nalta.m3u8\n')
        self.assertEqual((maestra.alto, maestra.idiomas, maestra.audio_aparte), (1080, ['es', 'en'], True))

    def test_idiomas(self):
        codigos = ('spa', 'ESP', 'es-419', 'lat', 'eng', 'ara', 'und', 'qaa', '', 'xyz')
        self.assertEqual([analisis.idioma_corto(c) for c in codigos],
                         ['es', 'es', 'es', 'es', 'en', 'ar', '', '', '', 'xyz'])


# ── La prueba a fondo, punta a punta ─────────────────────────────────

MAESTRA = ('#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=4000000,RESOLUTION=1920x1080,CODECS="avc1.64002a,mp4a.40.2"\n'
           'senal.m3u8\n')


def _lista(secuencia):
    return (f'#EXTM3U\n#EXT-X-TARGETDURATION:6\n#EXT-X-MEDIA-SEQUENCE:{secuencia}\n'
            f'#EXTINF:6.0,\nseg{secuencia}.ts\n#EXTINF:6.0,\nseg{secuencia + 1}.ts\n')


class PruebaAFondoTests(TestCase):

    def probar(self, listas, video, segundos=0.5, url='https://x/maestra.m3u8'):
        """
        `listas`: {url: [respuesta, respuesta...]} (cada pedido se lleva la
        siguiente). `video`: lo que llega al bajar el pedazo de video, y
        tarda `segundos`.
        """
        def descargar(direccion, cabeceras, maximo=None):
            respuestas = listas[direccion]
            return (respuestas.pop(0) if len(respuestas) > 1 else respuestas[0]).encode(), direccion, ''

        def bajar(direccion, cabeceras, maximo=None, segundos_maximos=None):
            if direccion in listas:
                datos, final, tipo = descargar(direccion, cabeceras)
                return Bajada(datos, final, tipo)
            return Bajada(video, direccion, 'video/mp2t', len(video), segundos)

        with mock.patch.object(verificacion, '_descargar', side_effect=descargar), \
                mock.patch.object(verificacion, '_bajar', side_effect=bajar), \
                mock.patch.object(verificacion, '_esperar') as esperar:
            resultado = verificacion.verificar_url(url, a_fondo=True)
        self.esperar = esperar
        return resultado

    def test_en_vivo_bien(self):
        video = video_ts(relleno=1100)   # unos 200 KB con 2 segundos de video
        resultado = self.probar({'https://x/maestra.m3u8': [MAESTRA],
                                 'https://x/senal.m3u8': [_lista(10), _lista(11)]}, video)
        self.assertEqual((resultado.estado, resultado.codec, resultado.alto, resultado.con_audio),
                         (FUNCIONA, 'h264', 1080, True))
        self.assertEqual((resultado.idiomas, resultado.velocidad, resultado.congelada), (('es',), 4.0, False))
        self.esperar.assert_called_once()   # esperó a que hubiera un pedazo nuevo
        self.assertEqual(resultado.calidad(), '1080p · H.264 · audio AAC (es) · llega x4.0')
        self.assertEqual(juzgar(resultado, Importacion(solo_espanol=True)), ('', ''))

    def test_congelada(self):
        resultado = self.probar({'https://x/maestra.m3u8': [MAESTRA], 'https://x/senal.m3u8': [_lista(10)]},
                                video_ts(relleno=1100))
        self.assertTrue(resultado.congelada)
        self.assertEqual(juzgar(resultado, Importacion())[0], Causa.SE_CORTA)

    def test_lenta(self):
        # Directo: tarda 4 segundos en llegar lo que se reproduce en 2
        resultado = self.probar({}, video_ts(relleno=1100), segundos=4, url='http://x:8080/u/p/1')
        self.assertEqual((resultado.tipo, resultado.velocidad), ('directo', 0.5))
        self.assertEqual(juzgar(resultado, Importacion())[0], Causa.LENTA)

    def test_una_pelicula_en_otro_idioma(self):
        resultado = self.probar({}, video_mkv(b'ara'), url='http://x/movie/u/p/1.mkv')
        self.assertEqual(resultado.idiomas, ('ar',))
        causa, motivo = juzgar(resultado, Importacion(solo_espanol=True))
        self.assertEqual((causa, motivo), (Causa.IDIOMA, 'El audio está en árabe (no trae español).'))
        # Sin "solo en español", pasa
        self.assertEqual(juzgar(resultado, Importacion(solo_espanol=False)), ('', ''))

    def test_se_corta_mientras_baja(self):
        respuesta = mock.MagicMock()
        respuesta.__enter__.return_value = respuesta
        respuesta.read.side_effect = [b'\x47' * 1000, TimeoutError()]
        respuesta.headers = {}
        respuesta.geturl.return_value = 'http://x/1'
        with mock.patch('urllib.request.urlopen', return_value=respuesta):
            bajada = verificacion._bajar('http://x/1', {})
        self.assertEqual((len(bajada.datos), bajada.se_corto), (1000, True))


class JuzgarTests(TestCase):

    def test_que_no_pasa(self):
        importacion = Importacion(solo_espanol=True)

        def causa(**datos):
            return juzgar(Resultado(FUNCIONA, a_fondo=True, **datos), importacion)[0]

        self.assertEqual(causa(codec='mpeg2'), Causa.FORMATO)
        self.assertEqual(causa(codec='h264_10'), Causa.FORMATO)
        self.assertEqual(causa(con_audio=False), Causa.SIN_SONIDO)
        self.assertEqual(causa(audios=('dts',)), Causa.SIN_SONIDO)
        self.assertEqual(causa(idiomas=('en', 'fr')), Causa.IDIOMA)
        self.assertEqual(causa(alto=240), Causa.BAJA_CALIDAD)
        self.assertEqual(causa(velocidad=0.6), Causa.LENTA)
        self.assertEqual(causa(se_corto=True), Causa.SE_CORTA)

    def test_que_pasa(self):
        importacion = Importacion(solo_espanol=True)
        for datos in ({'idiomas': ('en', 'es')}, {'alto': 576}, {'codec': 'h265_10'}, {'audios': ('ac3', 'dts')},
                      {'velocidad': 1.4}, {}):
            self.assertEqual(juzgar(Resultado(FUNCIONA, a_fondo=True, **datos), importacion), ('', ''), datos)
        # Sin la prueba a fondo solo se mira el formato
        self.assertEqual(juzgar(Resultado(FUNCIONA, con_audio=False), importacion), ('', ''))


# ── Importar: probar primero, cargar después ─────────────────────────

LISTA = '''#EXTM3U
#EXTINF:-1 group-title="Noticias",Canal 26
http://x/bien.m3u8
#EXTINF:-1 group-title="Noticias",Senal Nueve
http://x/arabe.m3u8
#EXTINF:-1 group-title="Deportes",Canal Mudo
http://x/mudo.m3u8
#EXTINF:-1 group-title="SERIES",Lost S01 E01
http://x/series/u/p/1.mkv
#EXTINF:-1 group-title="SERIES",Lost S01 E02
http://x/series/u/p/2.mkv
#EXTINF:-1 group-title="SERIES",Lost S01 E03
http://x/series/u/p/3.mkv
#EXTINF:-1 group-title="SERIES",Arrow S01 E02
http://x/series/u/p/4.mkv
#EXTINF:-1 group-title="SERIES",Arrow S01 E03
http://x/series/u/p/5.mkv
#EXTINF:-1 group-title="SERIES",Arrow S01 E04
http://x/series/u/p/6.mkv
#EXTINF:-1,Caido
http://x/caido.m3u8
'''


def verificador_a_fondo(fuentes, cabeceras=None, hasta=None):
    def uno(url):
        if 'caido' in url:
            return Resultado(CAIDA, 'No respondió a tiempo.')
        resultado = Resultado(FUNCIONA, tipo='hls', codec='h264', a_fondo=True, alto=1080, con_audio=True,
                              audios=('aac',), idiomas=('es',), velocidad=3)
        if 'arabe' in url:
            resultado.idiomas = ('ar',)
        if 'mudo' in url:
            resultado.con_audio, resultado.audios, resultado.idiomas = False, (), ()
        return resultado
    return {url: uno(url) for url in fuentes}


class ImportarConPruebaTests(TestCase):

    def test_en_una_lista_una_serie_de_menos_de_3_capitulos_no_entra(self):
        # En las listas suelen venir series a medias. (Traída de YouTube como serie, sí entra: test_youtube)
        lista = '''#EXTM3U
#EXTINF:-1 group-title="SERIES",Electro Andes S01 E01
http://x/series/u/p/electro-andes-1.mkv
'''
        importacion = crear_importacion(lista, 'serie-nueva.m3u', a_fondo=True)
        avance = procesar_lote(importacion, verificador_a_fondo)
        entrada = importacion.entradas.get()

        self.assertTrue(avance['terminada'])
        self.assertEqual((entrada.estado, entrada.causa), (Estado.RECHAZADA, Causa.SERIE_INCOMPLETA))
        self.assertIn('al menos 3 capítulos', entrada.motivo)

    def test_solo_quedan_aptas_las_que_pasan_todo(self):
        importacion = crear_importacion(LISTA, 'lista.m3u', solo_espanol=True, a_fondo=True)
        avance = procesar_lote(importacion, verificador_a_fondo)
        self.assertEqual((avance['terminada'], avance['aptas'], avance['rechazadas'], avance['caidas']),
                         (True, 4, 5, 1))
        self.assertFalse(Canal.objects.exists())   # todavía no se cargó nada
        estados = {e.nombre: (e.estado, e.causa) for e in importacion.entradas.all()}
        self.assertEqual(estados['Canal 26'], (Estado.APTA, ''))
        self.assertEqual(estados["Senal Nueve"], (Estado.RECHAZADA, Causa.IDIOMA))
        self.assertEqual(estados['Canal Mudo'], (Estado.RECHAZADA, Causa.SIN_SONIDO))
        self.assertEqual(estados['Lost S01 E02'], (Estado.APTA, ''))
        # Arrow no tiene el capítulo 1: la app no la mostraría
        self.assertEqual(estados['Arrow S01 E02'], (Estado.RECHAZADA, Causa.SERIE_INCOMPLETA))
        self.assertEqual(dict((c, n) for c, _, n in por_causa(importacion)),
                         {Causa.SERIE_INCOMPLETA: 3, Causa.IDIOMA: 1, Causa.SIN_SONIDO: 1})
        self.assertIn('1080p', importacion.entradas.get(nombre='Canal 26').calidad)

    def test_importar_de_una_carga_las_aptas_con_su_calidad(self):
        importar_m3u(LISTA, verificar=verificador_a_fondo, solo_espanol=True, a_fondo=True)
        self.assertEqual(set(Canal.objects.values_list('nombre', flat=True)),
                         {'Canal 26', 'Lost S01 E01', 'Lost S01 E02', 'Lost S01 E03'})
        fuente = Canal.objects.get(nombre='Canal 26').fuentes.get()
        self.assertEqual(fuente.calidad, '1080p · H.264 · audio AAC (es) · llega x3.0')
