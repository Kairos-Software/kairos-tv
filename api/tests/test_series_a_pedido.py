"""
Series a pedido (app 1.2.38+): la lista de series SIN capítulos
(GET /api/v1/canales/series/) y los capítulos de una al abrirla
(GET /api/v1/canales/series/capitulos/). La app vieja sigue pidiendo todo con
?contenido=serie y recibe lo mismo de siempre.
"""

import gzip
import json

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from api import tokens
from canales import imagenes
from canales.models import Canal, Categoria, Contenido, Fuente
from usuarios.models import Usuario

TODOS = 'hls,dash,directo,rtsp,youtube,pagina,yt_video'


class SeriesAPedidoTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        infantiles = Categoria.objects.create(nombre='Infantiles', contenido=Contenido.SERIE, orden=1)
        drama = Categoria.objects.create(nombre='Drama', contenido=Contenido.SERIE, orden=2)

        def capitulo(nombre, categoria, logo='', codec='', destacado=False, caida=False):
            canal = Canal.objects.create(nombre=nombre, contenido=Contenido.SERIE, categoria=categoria, logo=logo,
                                         destacado=destacado)
            Fuente.objects.create(canal=canal, url=f'http://p:8080/series/u/c/{nombre.replace(" ", "")}.mp4',
                                  tipo=Fuente.Tipo.DIRECTO, codec=codec,
                                  estado=Fuente.Estado.CAIDA if caida else Fuente.Estado.SIN_VERIFICAR)
            return canal

        cls.e1 = capitulo('Pocoyó S01 E01', infantiles, codec='h264')
        capitulo('Pocoyó S01 E02', infantiles, logo='https://img/p2.jpg', codec='h264', destacado=True)
        cls.t2 = capitulo('Pocoyó S02 E01', infantiles, codec='h265')
        capitulo('Pocoyó Especial S01 E01', infantiles)   # otra serie, aunque empiece igual
        capitulo('Lost S01 E01', drama, logo='https://img/lost.jpg')
        capitulo('Lost S01 E02', drama, caida=True)        # caída: no se manda ni se cuenta
        capitulo('A medias S01 E02', drama)                # sin el T1:E1: la app no la muestra
        capitulo('Especial de Navidad', drama)             # sin "S01 E01": tampoco
        imagenes.poner_portada('Lost', 'https://img/portada-lost.jpg')

    def setUp(self):
        self.app = APIClient()
        clave, _ = tokens.crear_token(Usuario.objects.create_user('cliente', None, 'x'))
        self.app.credentials(HTTP_AUTHORIZATION=f'Bearer {clave}')
        cache.clear()

    def test_la_lista_de_series_sin_capitulos(self):
        datos = self.app.get(reverse('api_v1:canales_series'), {'formatos': TODOS}).json()
        self.assertEqual(datos['cantidad'], 3)
        # Por categoría (en el orden de la app) y por nombre de la serie
        self.assertEqual([s['nombre'] for s in datos['series']], ['Pocoyó', 'Pocoyó Especial', 'Lost'])
        pocoyo, especial, lost = datos['series']
        self.assertEqual(pocoyo, {
            'nombre': 'Pocoyó', 'categoria': 'Infantiles', 'imagen': 'https://img/p2.jpg', 'capitulos': 3,
            'temporadas': [[1, 2], [2, 1]], 'destacada': True, 'codecs': ['h264', 'h265'],
        })
        self.assertEqual(especial['nombre'], 'Pocoyó Especial')
        self.assertEqual(especial['codecs'], [''])   # no se sabe el códec
        self.assertEqual((lost['imagen'], lost['capitulos'], lost['categoria']),
                         ('https://img/portada-lost.jpg', 1, 'Drama'))
        self.assertNotIn('canales', json.dumps(datos))   # ni un capítulo

    def test_va_comprimida_y_con_huella(self):
        url = reverse('api_v1:canales_series')
        primera = self.app.get(url, {'formatos': TODOS}, HTTP_ACCEPT_ENCODING='gzip')
        self.assertEqual(primera['Content-Encoding'], 'gzip')
        self.assertEqual(json.loads(gzip.decompress(primera.content))['cantidad'], 3)
        otra = self.app.get(url, {'formatos': TODOS}, HTTP_IF_NONE_MATCH=primera['ETag'])
        self.assertEqual(otra.status_code, 304)

    def test_los_capitulos_de_una_serie(self):
        datos = self.app.get(reverse('api_v1:canales_series_capitulos'), {'formatos': TODOS, 'nombre': 'pocoyó'}).json()
        nombres = [c['nombre'] for g in datos['categorias'] for c in g['canales']]
        self.assertEqual(sorted(nombres), ['Pocoyó S01 E01', 'Pocoyó S01 E02', 'Pocoyó S02 E01'])
        # Con sus señales, como en el catálogo de siempre
        canal = datos['categorias'][0]['canales'][0]
        self.assertEqual(set(canal), {'id', 'nombre', 'numero', 'logo', 'destacado', 'fuentes'})
        self.assertTrue(canal['fuentes'][0]['url'].startswith('http://p:8080/series/'))

    def test_las_series_de_unos_capitulos_para_continuar_viendo(self):
        datos = self.app.get(reverse('api_v1:canales_series_capitulos'),
                             {'formatos': TODOS, 'ids': f'{self.t2.pk},999999'}).json()
        nombres = sorted(c['nombre'] for g in datos['categorias'] for c in g['canales'])
        self.assertEqual(nombres, ['Pocoyó S01 E01', 'Pocoyó S01 E02', 'Pocoyó S02 E01'])

    def test_varias_series_juntas_y_nada(self):
        url = reverse('api_v1:canales_series_capitulos')
        datos = self.app.get(f'{url}?formatos={TODOS}&nombre=Lost&nombre=Pocoyó Especial').json()
        self.assertEqual(sorted(c['nombre'] for g in datos['categorias'] for c in g['canales']),
                         ['Lost S01 E01', 'Pocoyó Especial S01 E01'])
        self.assertEqual(self.app.get(url, {'formatos': TODOS}).json()['cantidad'], 0)

    def test_la_app_vieja_sigue_recibiendo_todos_los_capitulos(self):
        datos = self.app.get(reverse('api_v1:canales'), {'formatos': TODOS, 'contenido': 'serie'}).json()
        self.assertEqual(datos['cantidad'], 7)
        self.assertIn('portadas', datos)

    def test_piden_sesion(self):
        self.assertEqual(APIClient().get(reverse('api_v1:canales_series')).status_code, 401)
        self.assertEqual(APIClient().get(reverse('api_v1:canales_series_capitulos')).status_code, 401)
