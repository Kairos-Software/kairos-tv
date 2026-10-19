from pathlib import Path

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from actividad.models import RegistroActividad
from api import tokens
from canales import clasificar
from canales.m3u import leer_m3u, normalizar
from canales.models import Canal, Categoria, EntradaImportada, Fuente
from canales.servicios import importar_m3u
from usuarios.models import Usuario

LISTA = '''#EXTM3U x-tvg-url="https://epg/guia.xml.gz"
#EXTINF:-1 tvg-id="Canal26.ar" tvg-name="Canal 26" tvg-logo="https://logo/26.png" tvg-chno="26" tvg-country="AR" group-title="Noticias",Canal 26
https://servidor-a/canal26/main.m3u8
#EXTINF:-1 tvg-logo="https://logo/enc.png" group-title="Cultura",Encuentro Ⓨ
https://www.youtube.com/user/encuentro/live
#EXTINF:0,Sin atributos
http://servidor-b/sin/playlist.m3u8|User-Agent=VLC
#EXTINF:-1,Sin dirección
#EXTVLCOPT:http-referrer=https://x
'''


class LectorM3UTests(TestCase):

    def test_lee_los_datos(self):
        entradas = leer_m3u(LISTA)
        self.assertEqual([e.nombre for e in entradas], ['Canal 26', 'Encuentro', 'Sin atributos'])
        canal26 = entradas[0]
        self.assertEqual(canal26.logo, 'https://logo/26.png')
        self.assertEqual(canal26.categoria, 'Noticias')
        self.assertEqual(canal26.numero, '26')
        self.assertEqual(canal26.tvg_id, 'Canal26.ar')
        self.assertEqual(canal26.pais, 'AR')
        self.assertEqual(canal26.tipo, 'hls')
        self.assertEqual(entradas[1].tipo, 'youtube')
        # Las opciones después de "|" no son parte de la dirección
        self.assertEqual(entradas[2].url, 'http://servidor-b/sin/playlist.m3u8')

    def test_lee_user_agent_y_referer(self):
        lista = ('#EXTM3U\n#EXTINF:-1,Uno\n#EXTVLCOPT:http-user-agent=Navegador/1.0\n'
                 '#EXTVLCOPT:http-referrer=https://canal.com/\nhttps://a/uno.m3u8\n'
                 '#EXTINF:-1,Dos\nhttps://a/dos.m3u8|User-Agent=Otro/2.0&Referer=https://dos.com/\n'
                 '#EXTINF:-1,Tres\nhttps://a/tres.m3u8\n')
        uno, dos, tres = leer_m3u(lista)
        self.assertEqual((uno.user_agent, uno.referer), ('Navegador/1.0', 'https://canal.com/'))
        self.assertEqual((dos.url, dos.user_agent, dos.referer), ('https://a/dos.m3u8', 'Otro/2.0', 'https://dos.com/'))
        self.assertEqual((tres.user_agent, tres.referer), ('', ''))
        importar_m3u(lista)
        self.assertEqual(Fuente.objects.get(url='https://a/uno.m3u8').user_agent, 'Navegador/1.0')

    def test_lee_rtsp_y_el_idioma(self):
        lista = '#EXTM3U\n#EXTINF:-1 tvg-language="Spanish",Cámara\nrtsp://camara:554/vivo\n'
        entrada, = leer_m3u(lista)
        self.assertEqual((entrada.tipo, entrada.idioma), ('rtsp', 'Spanish'))

    def test_normalizar(self):
        self.assertEqual(normalizar('Canal 26 HD Ⓨ'), 'canal 26')
        self.assertEqual(normalizar('Telefé (720p)'), 'telefe')
        # Las variantes de una lista "Xtream" son el mismo canal
        self.assertEqual(normalizar('ES: (HD REPUESTO) DAZN F1'), normalizar('ES: DAZN F1 FHD'))


class ClasificarTests(TestCase):

    def test_nombre_limpio(self):
        self.assertEqual(clasificar.limpiar_nombre('ES: (HD REPUESTO) DAZN LALIGA'), 'DAZN LALIGA')
        self.assertEqual(clasificar.limpiar_nombre('13Max Televisión (1080p)'), '13Max Televisión')
        self.assertEqual(clasificar.limpiar_nombre('5TV (Corrientes) [Not 24/7]'), '5TV (Corrientes)')
        self.assertEqual(clasificar.limpiar_nombre('M+ DEPORTES'), 'M+ DEPORTES')

    def test_idioma_y_pais(self):
        self.assertEqual(clasificar.idioma_y_pais('Canal 26', pais='AR'), ('es', 'AR'))
        self.assertEqual(clasificar.idioma_y_pais('CO: RCN', 'LAME | COLOMBIA'), ('es', 'CO'))
        self.assertEqual(clasificar.idioma_y_pais('ES: DAZN 1', 'ES | DEPORTES'), ('es', 'ES'))
        self.assertEqual(clasificar.idioma_y_pais('Algo', 'LAME | LATINO'), ('es', ''))
        self.assertEqual(clasificar.idioma_y_pais('USA: NBC', 'USA | VIP-A'), ('otro', 'US'))
        # "AR:" en una categoría árabe NO es Argentina
        self.assertEqual(clasificar.idioma_y_pais('AR: KUWAIT QURAIN', 'ARAB | KUWAIT')[0], 'otro')
        self.assertEqual(clasificar.idioma_y_pais('Telefe', tvg_id='Telefe.ar@SD'), ('es', 'AR'))
        self.assertEqual(clasificar.idioma_y_pais('Canal raro'), ('', ''))
        self.assertEqual(clasificar.idioma_y_pais('X', idioma='English'), ('otro', ''))

    def test_contenido_y_formato(self):
        self.assertEqual(clasificar.contenido('http://x:8080/movie/u/p/1.mkv'), 'pelicula')
        self.assertEqual(clasificar.contenido('http://x:8080/series/u/p/1.mp4'), 'serie')
        self.assertEqual(clasificar.contenido('http://x:8080/u/p/57485'), 'vivo')
        self.assertEqual(clasificar.formato('http://x:8080/u/p/57485'), '')   # lo averigua la verificación
        self.assertEqual(clasificar.formato('https://x/a.m3u8?token=1'), 'hls')
        self.assertEqual(clasificar.formato('https://x/manifest.mpd'), 'dash')
        self.assertEqual(clasificar.formato('http://x/live/1.ts'), 'directo')
        self.assertEqual(clasificar.formato('rtmp://x/live'), 'rtmp')
        self.assertEqual(clasificar.formato('https://www.youtube.com/@tn/live'), 'youtube')
        self.assertEqual(clasificar.formato('https://youtu.be/abc'), 'youtube')
        self.assertEqual(clasificar.formato('https://www.twitch.tv/canal'), 'pagina')
        self.assertEqual(clasificar.formato('https://noesyoutube.com/a.m3u8'), 'hls')

    def test_para_adultos(self):
        self.assertTrue(clasificar.para_adultos('XXX: Algo', ''))
        self.assertTrue(clasificar.para_adultos('Canal', 'XXX-VIP [ 18+ ]'))
        self.assertFalse(clasificar.para_adultos('TN', 'Noticias'))

    def test_aviso_de_la_lista(self):
        self.assertIn('Not 24/7', clasificar.aviso_de_la_lista('Canal 8 Mar del Plata (720p) [Not 24/7]'))
        self.assertIn('Geo-blocked', clasificar.aviso_de_la_lista('Adult Swim Latin America (1080p) [Geo-blocked]'))
        self.assertEqual(clasificar.aviso_de_la_lista('A24 (1080p)'), '')
        self.assertEqual(clasificar.aviso_de_la_lista('TN [HD]'), '')


class ImportarTests(TestCase):

    def test_crea_canales_categorias_y_fuentes(self):
        resultado = importar_m3u(LISTA, origen='prueba.m3u8')
        self.assertEqual(resultado.canales_nuevos, 3)
        self.assertEqual(Canal.objects.count(), 3)
        self.assertEqual(set(Categoria.objects.values_list('nombre', flat=True)), {'Noticias', 'Cultura'})
        canal26 = Canal.objects.get(tvg_id='Canal26.ar')
        self.assertEqual((canal26.categoria.nombre, canal26.idioma), ('Noticias', 'es'))
        self.assertTrue(RegistroActividad.objects.filter(modulo='canales').exists())

    def test_reimportar_no_duplica(self):
        importar_m3u(LISTA)
        resultado = importar_m3u(LISTA)
        self.assertEqual((resultado.canales_nuevos, resultado.fuentes_nuevas, resultado.repetidas), (0, 0, 3))
        self.assertEqual(Fuente.objects.count(), 3)

    def test_el_mismo_canal_en_otra_lista_suma_una_alternativa(self):
        importar_m3u(LISTA)
        otra = ('#EXTM3U\n#EXTINF:-1 tvg-id="canal26.ar",AR: Canal 26 HD\nhttps://servidor-c/c26.m3u8\n'
                '#EXTINF:-1,Sin Atributos\nhttps://servidor-d/otra.m3u8\n')
        resultado = importar_m3u(otra)
        self.assertEqual((resultado.canales_nuevos, resultado.fuentes_nuevas), (0, 2))
        canal26 = Canal.objects.get(tvg_id='Canal26.ar')
        self.assertEqual(list(canal26.fuentes.values_list('url', flat=True)),
                         ['https://servidor-a/canal26/main.m3u8', 'https://servidor-c/c26.m3u8'])

    def test_mismo_tvg_id_pero_otro_canal_no_se_mezcla(self):
        """Hay listas que le ponen el mismo tvg-id a canales distintos."""
        lista = ('#EXTM3U\n#EXTINF:-1 tvg-id="IberaliaTV.es",ES: DAZN LALIGA\nhttp://x/1\n'
                 '#EXTINF:-1 tvg-id="IberaliaTV.es",ES: M+ DEPORTES\nhttp://x/2\n')
        importar_m3u(lista)
        self.assertEqual(set(Canal.objects.values_list('nombre', flat=True)), {'DAZN LALIGA', 'M+ DEPORTES'})

    def test_descarta_lo_que_no_sirve_con_el_motivo(self):
        lista = ('#EXTM3U\n'
                 '#EXTINF:-1 group-title="VOD | SPAIN",Una película\nhttp://x/movie/u/p/1.mkv\n'
                 '#EXTINF:-1 group-title="USA | VIP-A",USA: NBC\nhttp://x/u/p/2\n'
                 '#EXTINF:-1 group-title="LAME | ARGENTINA",AR: Telefe\nhttp://x/u/p/3\n'
                 '#EXTINF:-1 group-title="XXX-VIP [ 18+ ]",XXX: Algo\nhttp://x/u/p/4\n'
                 '#EXTINF:-1,\nhttp://x/u/p/5\n'
                 '#EXTINF:-1,Repetido\nhttp://x/u/p/3\n'
                 '#EXTINF:-1,Por RTMP\nrtmp://x/vivo\n'
                 '#EXTINF:-1,Canal 8 (720p) [Not 24/7]\nhttp://x/u/p/8\n')
        importar_m3u(lista, solo_espanol=True, descartar_vod=True)
        motivos = dict(EntradaImportada.objects.values_list('posicion', 'motivo'))
        estados = dict(EntradaImportada.objects.values_list('posicion', 'estado'))
        self.assertEqual(motivos[1], 'Es una película, no un canal en vivo.')
        self.assertEqual(motivos[2], 'No está en español (país: US).')
        self.assertEqual(estados[3], EntradaImportada.Estado.AGREGADA)
        self.assertEqual(motivos[4], 'Es contenido para adultos.')
        self.assertEqual(motivos[5], 'No tiene un nombre definido.')
        self.assertEqual(estados[6], EntradaImportada.Estado.REPETIDA)
        self.assertIn('RTMP', motivos[7])
        self.assertIn('Not 24/7', motivos[8])
        self.assertEqual(list(Canal.objects.values_list('nombre', flat=True)), ['Telefe'])

    def test_por_defecto_importa_peliculas_y_series(self):
        lista = ('#EXTM3U\n#EXTINF:-1 group-title="VOD | SPAIN",6 Guns (2010)\nhttp://x/movie/u/p/1.mkv\n'
                 '#EXTINF:-1 group-title="SERIES | HBO",Show S01 E01\nhttp://x/series/u/p/2.mkv\n'
                 '#EXTINF:-1 group-title="SERIES | HBO",Show S01 E02\nhttp://x/series/u/p/4.mkv\n'
                 '#EXTINF:-1 group-title="SERIES | HBO",Show S01 E03\nhttp://x/series/u/p/5.mkv\n'
                 '#EXTINF:-1,6 Guns (2010)\nhttp://x/u/p/3\n')
        importar_m3u(lista)
        contenidos = dict(Canal.objects.values_list('nombre', 'contenido'))
        # La película y el "en vivo" con el mismo nombre no se mezclan
        self.assertEqual(Canal.objects.filter(nombre='6 Guns (2010)').count(), 2)
        self.assertEqual(contenidos['Show S01 E01'], 'serie')

    def test_no_vuelve_a_meter_un_canal_quitado(self):
        importar_m3u(LISTA)
        Canal.objects.filter(nombre='Canal 26').update(activo=False, motivo_quitado='No interesa')
        importar_m3u('#EXTM3U\n#EXTINF:-1 tvg-country="AR",Canal 26\nhttps://otro/c26.m3u8\n')
        entrada = EntradaImportada.objects.get(url='https://otro/c26.m3u8')
        self.assertEqual(entrada.estado, EntradaImportada.Estado.DESCARTADA)
        self.assertIn('quitado', entrada.motivo)

    def test_comando(self):
        archivo = Path(__file__).resolve().parent.parent / 'datos' / 'canales_prueba.m3u8'
        call_command('importar_m3u', str(archivo), '--sin-verificar', stdout=open('nul' if __import__('os').name == 'nt' else '/dev/null', 'w'))
        self.assertEqual(Canal.objects.count(), 3)


class ApiCanalesTests(TestCase):
    URL = reverse('api_v1:canales')

    def setUp(self):
        importar_m3u(LISTA)
        self.client = APIClient()
        usuario = Usuario.objects.create_user('cliente', None, 'x')
        clave, _ = tokens.crear_token(usuario)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {clave}')

    def test_pide_sesion(self):
        self.assertEqual(APIClient().get(self.URL).status_code, 401)

    def test_agrupados_por_categoria(self):
        datos = self.client.get(self.URL).json()
        # Encuentro solo tiene YouTube: la app no lo sabe reproducir, no se manda
        self.assertEqual(datos['cantidad'], 2)
        por_categoria = {c['nombre']: [canal['nombre'] for canal in c['canales']] for c in datos['categorias']}
        self.assertEqual(por_categoria, {'Noticias': ['Canal 26'], 'Otros': ['Sin atributos']})
        canal26 = datos['categorias'][0]['canales'][0]
        self.assertEqual(canal26['fuentes'][0]['url'], 'https://servidor-a/canal26/main.m3u8')
        self.assertEqual(canal26['logo'], 'https://logo/26.png')

    def test_la_app_vieja_solo_recibe_hls(self):
        """La 1.0.0 no manda ?formatos= y solo sabe HLS: no recibe video directo."""
        Fuente.objects.filter(canal__nombre='Sin atributos').update(tipo=Fuente.Tipo.DIRECTO)
        self.assertEqual(self.client.get(self.URL).json()['cantidad'], 1)
        datos = self.client.get(self.URL, {'formatos': 'hls,dash,directo,rtsp'}).json()
        self.assertEqual(datos['cantidad'], 2)

    def test_la_app_recibe_la_forma_ts_de_un_vivo_xtream_sin_extension(self):
        fuente = Fuente.objects.get(canal__nombre='Canal 26')
        fuente.url = 'http://panel:55577/usuario/clave/444969'
        fuente.tipo = Fuente.Tipo.DIRECTO
        fuente.save(update_fields=['url', 'tipo'])

        datos = self.client.get(self.URL, {'formatos': 'hls,directo'}).json()
        canal = next(c for categoria in datos['categorias'] for c in categoria['canales']
                     if c['nombre'] == 'Canal 26')
        self.assertEqual(canal['fuentes'][0]['url'],
                         'http://panel:55577/live/usuario/clave/444969.ts')
        # La dirección original queda intacta para el panel, las verificaciones
        # y las exportaciones; solo se adapta al entregársela al reproductor.
        fuente.refresh_from_db()
        self.assertEqual(fuente.url, 'http://panel:55577/usuario/clave/444969')

    def test_peliculas_aparte(self):
        importar_m3u('#EXTM3U\n#EXTINF:-1,Una película\nhttp://x/movie/u/p/1.mp4\n')
        formatos = {'formatos': 'hls,directo'}
        self.assertEqual(self.client.get(self.URL, formatos).json()['cantidad'], 2)   # solo los en vivo
        datos = self.client.get(self.URL, {**formatos, 'contenido': 'pelicula'}).json()
        self.assertEqual([c['nombre'] for g in datos['categorias'] for c in g['canales']], ['Una película'])

    def test_youtube_le_llega_a_la_app_nueva(self):
        datos = self.client.get(self.URL, {'formatos': 'hls,youtube'}).json()
        self.assertEqual(datos['cantidad'], 3)

    def test_no_muestra_inactivos_ni_sin_fuentes(self):
        Canal.objects.filter(nombre='Canal 26').update(activo=False)
        Fuente.objects.filter(canal__nombre='Sin atributos').update(activa=False)
        Fuente.objects.filter(canal__nombre='Encuentro').update(tipo='hls')   # para que solo cuente lo inactivo
        datos = self.client.get(self.URL).json()
        self.assertEqual(datos['cantidad'], 1)

    def test_fuentes_en_orden_de_prioridad(self):
        canal = Canal.objects.get(nombre='Canal 26')
        Fuente.objects.create(canal=canal, url='https://primera/x.m3u8', prioridad=0)
        datos = self.client.get(self.URL).json()
        noticias = next(c for c in datos['categorias'] if c['nombre'] == 'Noticias')
        self.assertEqual(noticias['canales'][0]['fuentes'][0]['url'], 'https://primera/x.m3u8')
