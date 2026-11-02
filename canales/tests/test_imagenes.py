"""Imágenes puestas a mano: subirlas desde la compu y la portada propia de cada serie."""

import shutil
import tempfile
from io import BytesIO
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from PIL import Image, ImageDraw
from rest_framework.test import APIClient

from api import tokens
from canales import consultas, imagenes, organizar
from canales.models import Canal, Categoria, Contenido, Fuente, PortadaDeSerie
from usuarios.models import Usuario

MEDIA_TEMPORAL = tempfile.mkdtemp()


def _imagen(nombre='poster.png', tamano=(2400, 3600), modo='RGB', formato='PNG'):
    buffer = BytesIO()
    Image.new(modo, tamano, (200, 30, 30, 0) if modo == 'RGBA' else 'orange').save(buffer, formato)
    return SimpleUploadedFile(nombre, buffer.getvalue(), content_type=f'image/{formato.lower()}')


def _capitulo(nombre, logo='', categoria=None):
    canal = Canal.objects.create(nombre=nombre, contenido=Contenido.SERIE, logo=logo, categoria=categoria)
    Fuente.objects.create(canal=canal, url=f'https://x/{nombre.replace(" ", "")}.m3u8')
    return canal


def _pocoyo():
    for n in (1, 2, 3):
        _capitulo(f'Pocoyó S01 E0{n} Título', logo=f'https://i.ytimg.com/{n}.jpg')


def _archivos():
    return sorted(p.name for p in (Path(MEDIA_TEMPORAL) / imagenes.CARPETA).glob('*'))


@override_settings(MEDIA_ROOT=MEDIA_TEMPORAL)
class SubirImagenTests(TestCase):

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA_TEMPORAL, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        shutil.rmtree(Path(MEDIA_TEMPORAL) / imagenes.CARPETA, ignore_errors=True)
        self.client.force_login(Usuario.objects.create_superuser('admin', 'admin@test.com', 'x'))
        self.pelicula = Canal.objects.create(nombre='EL REGRESO (2019) Película completa', contenido=Contenido.PELICULA,
                                             logo='https://i.ytimg.com/vi/abc/hq.jpg')

    def _editar(self, follow=False, **datos):
        return self.client.post(reverse('canales:organizar_editar'), {
            'tipo': 'canal', 'canal': self.pelicula.pk, 'nombre': self.pelicula.nombre, 'logo': self.pelicula.logo,
            'contenido': 'pelicula', 'categoria': 'ninguna', 'activo': 'on', **datos}, follow=follow)

    def test_subida_se_achica_y_queda_como_imagen(self):
        self._editar(nombre='El regreso', imagen=_imagen())
        self.pelicula.refresh_from_db()
        self.assertEqual(self.pelicula.nombre, 'El regreso')
        self.assertRegex(self.pelicula.logo, r'^http://testserver/media/canales/imagenes/[0-9a-f]{32}\.jpg$')
        archivo, = _archivos()
        with Image.open(Path(MEDIA_TEMPORAL) / imagenes.CARPETA / archivo) as guardada:
            self.assertEqual((guardada.format, guardada.size), ('JPEG', (1067, 1600)))   # no más de 1600 de lado

    def test_un_logo_transparente_queda_png(self):
        self._editar(imagen=_imagen(tamano=(300, 300), modo='RGBA'))
        self.pelicula.refresh_from_db()
        self.assertTrue(self.pelicula.logo.endswith('.png'))

    def test_al_cambiarla_la_subida_vieja_se_borra(self):
        self._editar(imagen=_imagen())
        self.pelicula.refresh_from_db()
        self.assertEqual(len(_archivos()), 1)
        self._editar(logo='https://ejemplo.com/otra.jpg')
        self.assertEqual(_archivos(), [])

    def test_si_otro_la_usa_no_se_borra(self):
        self._editar(imagen=_imagen())
        self.pelicula.refresh_from_db()
        Canal.objects.create(nombre='Otra', contenido=Contenido.PELICULA, logo=self.pelicula.logo)
        self._editar(logo='https://ejemplo.com/otra.jpg')
        self.assertEqual(len(_archivos()), 1)

    def test_lo_que_no_es_imagen_no_se_guarda(self):
        respuesta = self._editar(nombre='Otro nombre',
                                 imagen=SimpleUploadedFile('virus.png', b'MZ no soy una imagen', 'image/png'),
                                 follow=True)
        self.assertContains(respuesta, 'no es una imagen')
        self.pelicula.refresh_from_db()
        self.assertEqual((self.pelicula.nombre, self.pelicula.logo),
                         ('EL REGRESO (2019) Película completa', 'https://i.ytimg.com/vi/abc/hq.jpg'))
        self.assertEqual(_archivos(), [])

    def test_el_dialogo_permite_subir(self):
        respuesta = self.client.get(reverse('canales:organizar'), {'contenido': 'pelicula'})
        self.assertContains(respuesta, 'enctype="multipart/form-data"')
        self.assertContains(respuesta, 'name="imagen"')


def _cuadritos(lado=320, cuadro=16, claro=(255, 255, 255), oscuro=(204, 204, 204)):
    """Un "PNG sin fondo" de internet: un logo rojo con los cuadritos PINTADOS (y un gris igual adentro)."""
    imagen = Image.new('RGB', (lado, lado), claro)
    dibujo = ImageDraw.Draw(imagen)
    for y in range(0, lado, cuadro):
        for x in range(0, lado, cuadro):
            if (x // cuadro + y // cuadro) % 2:
                dibujo.rectangle([x, y, x + cuadro - 1, y + cuadro - 1], fill=oscuro)
    dibujo.ellipse([lado // 4, lado // 4, 3 * lado // 4, 3 * lado // 4], fill=(220, 20, 20))
    dibujo.rectangle([lado // 2 - 8, lado // 2 - 8, lado // 2 + 8, lado // 2 + 8], fill=oscuro)
    return imagen


class FondoDeCuadritosTests(TestCase):

    def test_los_cuadritos_pintados_pasan_a_transparente(self):
        limpia = imagenes.sacar_cuadritos(_cuadritos())
        self.assertEqual(limpia.mode, 'RGBA')
        self.assertEqual(limpia.getpixel((0, 0))[3], 0)            # el fondo
        self.assertEqual(limpia.getpixel((319, 170))[3], 0)
        self.assertEqual(limpia.getpixel((100, 160))[3], 255)      # el logo
        self.assertEqual(limpia.getpixel((160, 160))[3], 255)      # el gris de adentro del logo se queda

    def test_tambien_los_oscuros_y_en_jpg(self):
        buffer = BytesIO()
        _cuadritos(claro=(60, 60, 60), oscuro=(40, 40, 40)).save(buffer, 'JPEG', quality=80)
        buffer.seek(0)
        with Image.open(buffer) as jpg:
            self.assertEqual(imagenes.sacar_cuadritos(jpg).getpixel((0, 0))[3], 0)

    def test_lo_que_no_es_cuadritos_no_se_toca(self):
        blanca = Image.new('RGB', (300, 300), 'white')
        ImageDraw.Draw(blanca).ellipse([50, 50, 250, 250], fill='blue')
        franjas = Image.new('RGB', (300, 300), 'white')
        ImageDraw.Draw(franjas).rectangle([0, 150, 300, 300], fill=(204, 204, 204))
        transparente = Image.new('RGBA', (300, 300), (0, 0, 0, 0))
        for imagen in (blanca, franjas, transparente, Image.new('RGB', (8, 8), 'gray')):
            self.assertIs(imagenes.sacar_cuadritos(imagen), imagen)

    @override_settings(MEDIA_ROOT=MEDIA_TEMPORAL)
    def test_al_subirla_queda_png_transparente(self):
        buffer = BytesIO()
        _cuadritos().save(buffer, 'PNG')
        url = imagenes.guardar_subida(SimpleUploadedFile('logo.png', buffer.getvalue(), 'image/png'),
                                      RequestFactory().get('/'))
        self.assertTrue(url.endswith('.png'))
        with Image.open(Path(MEDIA_TEMPORAL) / imagenes._archivo_subido(url)) as guardada:
            self.assertEqual(guardada.getpixel((0, 0))[3], 0)

    @override_settings(MEDIA_ROOT=MEDIA_TEMPORAL)
    def test_un_png_con_color_transparente_no_pierde_la_transparencia(self):
        # PNG "RGB" con un color marcado como transparente (tRNS): antes quedaba JPG con ese color de fondo
        buffer = BytesIO()
        imagen = Image.new('RGB', (100, 100), (0, 255, 0))
        ImageDraw.Draw(imagen).ellipse([20, 20, 80, 80], fill='red')
        imagen.save(buffer, 'PNG', transparency=(0, 255, 0))
        url = imagenes.guardar_subida(SimpleUploadedFile('logo.png', buffer.getvalue(), 'image/png'),
                                      RequestFactory().get('/'))
        with Image.open(Path(MEDIA_TEMPORAL) / imagenes._archivo_subido(url)) as guardada:
            self.assertEqual((guardada.format, guardada.getpixel((0, 0))[3]), ('PNG', 0))


@override_settings(MEDIA_ROOT=MEDIA_TEMPORAL)
class PortadaDeSerieTests(TestCase):

    def setUp(self):
        self.client.force_login(Usuario.objects.create_superuser('admin', 'admin@test.com', 'x'))
        self.infantiles = Categoria.objects.create(nombre='Series Infantiles', contenido=Contenido.SERIE)
        _pocoyo()

    def _editar(self, serie='Pocoyó', **datos):
        return self.client.post(reverse('canales:organizar_editar'), {
            'tipo': 'serie', 'serie': serie, 'nombre': serie, 'logo': '', 'categoria': self.infantiles.pk,
            'activo': 'on', **datos})

    def test_la_portada_no_pisa_las_imagenes_de_los_capitulos(self):
        self._editar(logo='https://ejemplo.com/pocoyo.jpg')
        self.assertEqual(imagenes.portada_de('pocoyo'), 'https://ejemplo.com/pocoyo.jpg')
        self.assertEqual(sorted(Canal.objects.values_list('logo', flat=True)),
                         [f'https://i.ytimg.com/{n}.jpg' for n in (1, 2, 3)])
        serie, = consultas.series()
        self.assertEqual((serie.logo, serie.portada), ('https://ejemplo.com/pocoyo.jpg', 'https://ejemplo.com/pocoyo.jpg'))

    def test_sin_tocar_la_imagen_no_se_crea_portada(self):
        # El cuadro muestra la del primer capítulo: guardar sin cambiarla no la vuelve portada
        self._editar(logo='https://i.ytimg.com/1.jpg', categoria='ninguna')
        self.assertFalse(PortadaDeSerie.objects.exists())

    def test_borrarla_vuelve_a_la_del_primer_capitulo(self):
        imagenes.poner_portada('Pocoyó', 'https://ejemplo.com/pocoyo.jpg')
        self._editar(logo='')
        self.assertFalse(PortadaDeSerie.objects.exists())
        self.assertEqual(consultas.series()[0].logo, 'https://i.ytimg.com/1.jpg')

    def test_subida_desde_la_compu(self):
        self._editar(imagen=_imagen())
        self.assertRegex(imagenes.portada_de('Pocoyó'), r'/media/canales/imagenes/[0-9a-f]{32}\.jpg$')

    def test_va_con_la_serie_al_renombrarla_y_al_unirla(self):
        imagenes.poner_portada('Pocoyó', 'https://ejemplo.com/pocoyo.jpg')
        self._editar(nombre='Pocoyó y sus amigos', logo='https://ejemplo.com/pocoyo.jpg')   # como la manda el cuadro
        self.assertEqual(imagenes.portada_de('Pocoyó y sus amigos'), 'https://ejemplo.com/pocoyo.jpg')
        self.assertEqual(imagenes.portada_de('Pocoyó'), '')
        _capitulo('Pato S01 E01 Solo')
        organizar.unir_en_una_serie(['Pato', 'Pocoyó y sus amigos'], 'Pocoyó Todo')
        self.assertEqual(imagenes.portada_de('Pocoyó Todo'), 'https://ejemplo.com/pocoyo.jpg')
        self.assertEqual(PortadaDeSerie.objects.count(), 1)

    def test_pasarla_a_pelicula_y_volver_no_pierde_ninguna_imagen(self):
        imagenes.poner_portada('Pocoyó', 'https://ejemplo.com/serie.jpg')
        capitulos = organizar.capitulos_de(['Pocoyó'])
        organizar.cambiar_contenido(capitulos, Contenido.PELICULA)
        # Como película muestra su propia imagen; la portada de la serie queda guardada aparte
        Canal.objects.filter(nombre__startswith='Pocoyó S01 E01').update(logo='https://ejemplo.com/peli.jpg')
        self.assertEqual(imagenes.portada_de('Pocoyó'), 'https://ejemplo.com/serie.jpg')
        organizar.cambiar_contenido(Canal.objects.all(), Contenido.SERIE, 'Pocoyó')
        serie, = consultas.series()
        self.assertEqual(serie.logo, 'https://ejemplo.com/serie.jpg')
        self.assertEqual(Canal.objects.get(nombre__startswith='Pocoyó S01 E01').logo, 'https://ejemplo.com/peli.jpg')

    def test_eliminar_la_serie_le_saca_la_portada(self):
        imagenes.poner_portada('Pocoyó', 'https://ejemplo.com/pocoyo.jpg')
        self.client.post(reverse('canales:organizar_eliminar'), {'serie': 'Pocoyó'})
        self.assertFalse(PortadaDeSerie.objects.exists())

    def test_la_api_la_manda_aparte(self):
        imagenes.poner_portada('pocoyo', 'https://ejemplo.com/pocoyo.jpg')
        cliente = APIClient()
        clave, _ = tokens.crear_token(Usuario.objects.create_user('cliente', None, 'x'))
        cliente.credentials(HTTP_AUTHORIZATION=f'Bearer {clave}')
        datos = cliente.get(reverse('api_v1:canales'), {'contenido': 'serie'}).json()
        self.assertEqual(datos['portadas'], {'Pocoyó': 'https://ejemplo.com/pocoyo.jpg'})
        self.assertEqual([c['logo'] for g in datos['categorias'] for c in g['canales']],
                         [f'https://i.ytimg.com/{n}.jpg' for n in (1, 2, 3)])
        self.assertNotIn('portadas', cliente.get(reverse('api_v1:canales'), {'contenido': 'pelicula'}).json())

    def test_el_panel_muestra_la_portada(self):
        imagenes.poner_portada('Pocoyó', 'https://ejemplo.com/pocoyo.jpg')
        respuesta = self.client.get(reverse('canales:organizar'), {'contenido': 'serie'})
        self.assertContains(respuesta, 'src="https://ejemplo.com/pocoyo.jpg"')
        self.assertContains(respuesta, '&quot;portada&quot;: true')
