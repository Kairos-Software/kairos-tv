"""
Los logos de los canales en vivo, parejos: sin el borde vacío que traen
muchos archivos, con un margen chico e igual para todos y achicados, para
que todos queden centrados igual en su tarjeta (imagenes.emparejar). Los
rotos (imgur los borró, 404) no se mandan: la app muestra las iniciales.
"""

import shutil
import tempfile
from io import BytesIO
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image, ImageDraw
from rest_framework.test import APIClient

from api import tokens
from canales import imagenes
from canales.models import Canal, Fuente, LogoParejo
from usuarios.models import Rol, Usuario


def _imagen(ancho, alto, caja, fondo=(0, 0, 0, 0), color=(220, 30, 30, 255)):
    """Una imagen de `ancho`x`alto` con un rectángulo de `color` en `caja` sobre `fondo`."""
    imagen = Image.new('RGBA', (ancho, alto), fondo)
    ImageDraw.Draw(imagen).rectangle([caja[0], caja[1], caja[2] - 1, caja[3] - 1], fill=color)
    return imagen


def _bytes(imagen, formato='PNG'):
    salida = BytesIO()
    imagen.save(salida, formato)
    return salida.getvalue()


class EmparejarTests(TestCase):

    def test_saca_el_borde_transparente_y_deja_un_margen_chico(self):
        # Como Comarca TV: 25 % vacío a cada costado
        parejo = imagenes.emparejar(_imagen(400, 200, (100, 20, 300, 180)), 'PNG')
        margen = round(200 * imagenes.MARGEN_TRANSPARENTE)
        self.assertEqual(parejo.size, (200 + 2 * margen, 160 + 2 * margen))
        self.assertEqual(parejo.getpixel((0, 0))[3], 0)                        # el margen, transparente
        self.assertEqual(parejo.getpixel((margen + 1, margen + 1))[:3], (220, 30, 30))

    def test_un_fondo_de_color_se_achica_pero_no_se_saca(self):
        # Como Encuentro: logo sobre un recuadro blanco grande. Sin el blanco, un logo oscuro no se vería.
        parejo = imagenes.emparejar(_imagen(250, 250, (40, 60, 210, 190), fondo=(255, 255, 255, 255)), 'PNG')
        margen = round(130 * imagenes.MARGEN_DE_COLOR)
        self.assertEqual(parejo.size, (170 + 2 * margen, 130 + 2 * margen))
        self.assertEqual(parejo.getpixel((0, 0)), (255, 255, 255, 255))

    def test_el_que_ya_esta_justo_queda_igual(self):
        self.assertIsNone(imagenes.emparejar(_imagen(250, 56, (0, 0, 250, 56)), 'PNG'))   # como DeporTV

    def test_una_foto_no_se_recorta(self):
        foto = Image.new('RGBA', (300, 200), (255, 255, 255, 255))
        ImageDraw.Draw(foto).rectangle([0, 0, 149, 199], fill=(10, 60, 120, 255))   # esquinas de dos colores
        self.assertIsNone(imagenes.emparejar(foto, 'JPEG'))

    def test_uno_enorme_se_achica(self):
        parejo = imagenes.emparejar(_imagen(3840, 3840, (0, 0, 3840, 3840)), 'PNG')   # como Canal 26
        self.assertEqual(max(parejo.size), imagenes.LADO_PAREJO)

    def test_vacia_no_sirve(self):
        with self.assertRaises(imagenes.LogoNoSirve):
            imagenes.emparejar(Image.new('RGBA', (100, 100), (0, 0, 0, 0)), 'PNG')


class PrepararTests(TestCase):

    def test_prepara_un_webp(self):
        with mock.patch.object(imagenes, '_bajar', return_value=_bytes(_imagen(400, 200, (100, 20, 300, 180)))):
            url, webp, error, roto = imagenes._preparar('https://logos.ejemplo.com/a.png')
        self.assertEqual((error, roto), ('', False))
        self.assertEqual(Image.open(BytesIO(webp)).format, 'WEBP')

    def test_borrado_por_imgur_es_roto(self):
        respuesta = mock.MagicMock()
        respuesta.__enter__.return_value.geturl.return_value = 'https://i.imgur.com/removed.png'
        with mock.patch('urllib.request.urlopen', return_value=respuesta):
            _, webp, error, roto = imagenes._preparar('https://i.imgur.com/6miysb8.png')
        self.assertIsNone(webp)
        self.assertTrue(roto)
        self.assertIn('imgur lo borró', error)

    def test_svg_queda_el_original(self):
        with mock.patch.object(imagenes, '_bajar', return_value=b'<?xml version="1.0"?><svg></svg>'):
            _, webp, error, roto = imagenes._preparar('https://logos.ejemplo.com/a.svg')
        self.assertEqual((webp, roto), (None, False))
        self.assertIn('SVG', error)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix='kairos-logos-'))
class LogosParejosEnLaAppYElPanelTests(TestCase):

    @classmethod
    def tearDownClass(cls):
        from django.conf import settings
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.a24 = self._canal('A24', 'https://logos.ejemplo.com/a24.png')
        self.borrado = self._canal('24/7 Canal de Noticias', 'https://i.imgur.com/6miysb8.png')
        self.justo = self._canal('DeporTV', 'https://logos.ejemplo.com/deportv.png')
        self.pelicula = self._canal('Toy Story', 'https://posters.ejemplo.com/toy.jpg', 'pelicula')

    def _canal(self, nombre, logo, contenido='vivo'):
        canal = Canal.objects.create(nombre=nombre, logo=logo, contenido=contenido)
        Fuente.objects.create(canal=canal, url=f'https://senal.ejemplo.com/{canal.pk}.m3u8',
                              estado=Fuente.Estado.FUNCIONA)
        return canal

    @staticmethod
    def _preparar_falso(url):
        if 'imgur' in url:
            return url, None, 'imgur lo borró.', True
        if 'deportv' in url:
            return url, None, '', False
        return url, _bytes(_imagen(40, 20, (0, 0, 40, 20)), 'WEBP'), '', False

    def _app(self, contenido='vivo'):
        app = APIClient()
        clave, _ = tokens.crear_token(Usuario.objects.create_user(f'cliente-{contenido}', None, 'x'))
        app.credentials(HTTP_AUTHORIZATION=f'Bearer {clave}')
        datos = app.get(reverse('api_v1:canales'), {'contenido': contenido, 'formatos': 'hls'}).json()
        return {c['nombre']: c['logo'] for g in datos['categorias'] for c in g['canales']}

    def test_el_cron_los_prepara_y_la_app_recibe_la_copia(self):
        resultado = imagenes.emparejar_logos(preparar=self._preparar_falso)
        self.assertEqual((resultado['parejos'], resultado['rotos'], resultado['iguales']), (1, 1, 1))
        logos = self._app()
        self.assertRegex(logos['A24'], r'^http://testserver/media/canales/logos/[0-9a-f]{40}\.webp$')
        self.assertEqual(logos['24/7 Canal de Noticias'], '')   # roto: la app pone las iniciales
        self.assertEqual(logos['DeporTV'], 'https://logos.ejemplo.com/deportv.png')   # ya estaba bien
        # Las películas tienen pósters: no se tocan
        self.assertFalse(LogoParejo.objects.filter(url=self.pelicula.logo).exists())
        self.assertEqual(self._app('pelicula')['Toy Story'], 'https://posters.ejemplo.com/toy.jpg')

    def test_no_repite_y_borra_lo_que_ya_no_se_usa(self):
        imagenes.emparejar_logos(preparar=self._preparar_falso)
        llamadas = []
        imagenes.emparejar_logos(preparar=lambda url: llamadas.append(url) or self._preparar_falso(url))
        self.assertEqual(llamadas, [])   # ya estaban todos
        archivo = LogoParejo.objects.get(url=self.a24.logo).archivo
        Canal.objects.filter(pk=self.a24.pk).update(logo='https://logos.ejemplo.com/a24-nuevo.png')
        resultado = imagenes.emparejar_logos(preparar=self._preparar_falso)
        self.assertEqual((resultado['parejos'], resultado['borrados']), (1, 1))
        from django.core.files.storage import default_storage
        self.assertFalse(default_storage.exists(archivo))

    def test_si_cambia_el_logo_la_app_recibe_el_nuevo_hasta_que_se_prepare(self):
        imagenes.emparejar_logos(preparar=self._preparar_falso)
        Canal.objects.filter(pk=self.a24.pk).update(logo='https://logos.ejemplo.com/a24-nuevo.png')
        self.assertEqual(self._app()['A24'], 'https://logos.ejemplo.com/a24-nuevo.png')

    def test_el_panel_muestra_la_copia_y_avisa_el_roto(self):
        imagenes.emparejar_logos(preparar=self._preparar_falso)
        self.client.force_login(Usuario.objects.create_user('marcos', None, 'x', rol=Rol.objects.create(
            nombre='Canales', permisos=['ver_canales', 'importar_canales'])))
        pagina = self.client.get(reverse('canales:organizar'), {'contenido': 'vivo'}).content.decode()
        self.assertIn(f'src="/media/{LogoParejo.objects.get(url=self.a24.logo).archivo}"', pagina)
        self.assertNotIn('src="https://i.imgur.com/6miysb8.png"', pagina)   # roto: iniciales en la tarjeta
        self.assertIn('Roto: imgur lo borr', pagina)                        # y en el panel de detalles

    def test_al_guardar_en_el_panel_se_prepara_en_el_momento(self):
        self.client.force_login(Usuario.objects.create_user('marcos', None, 'x', rol=Rol.objects.create(
            nombre='Canales', permisos=['ver_canales', 'importar_canales'])))
        with mock.patch.object(imagenes, '_preparar', side_effect=self._preparar_falso) as preparar, \
                self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('canales:organizar_editar'), {
                'tipo': 'canal', 'canal': self.a24.pk, 'nombre': 'A24', 'logo': 'https://logos.ejemplo.com/otro.png',
                'contenido': 'vivo', 'categoria': 'ninguna', 'activo': 'on'})
        preparar.assert_called_once_with('https://logos.ejemplo.com/otro.png')
        self.assertTrue(LogoParejo.objects.get(url='https://logos.ejemplo.com/otro.png').archivo)
