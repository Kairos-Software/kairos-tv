"""
El catálogo de la app armado rápido (api/v1/catalogo.py): tiene que mandar
EXACTAMENTE lo mismo que el serializador de siempre (las apps viejas lo leen
igual), comprimido, con huella (304 si la app ya lo tiene) y guardado un rato.
Y la compresión del resto (core/compresion.py), que no toca las descargas.
"""

import gzip
import json

from django.core.cache import cache
from django.http import FileResponse, HttpResponse, JsonResponse
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from api import tokens
from api.v1 import catalogo
from api.v1.serializers import CanalSerializer
from canales import clasificar, imagenes
from canales.consultas import agrupar_por_categoria, canales_disponibles, tipos_pedidos
from canales.models import Canal, Categoria, Contenido, Fuente, LogoParejo
from core.compresion import ComprimirMiddleware
from usuarios.models import Usuario

TODOS = 'hls,dash,directo,rtsp,youtube,pagina,yt_video'


def canal_llamado(datos, nombre):
    return next(c for g in datos['categorias'] for c in g['canales'] if c['nombre'] == nombre)


def nombres(datos):
    return [c['nombre'] for g in datos['categorias'] for c in g['canales']]


def como_antes(request, tipos, contenido):
    """Lo que armaba la vista antes (con CanalSerializer), para comparar."""
    canales = list(canales_disponibles(tipos, contenido))
    contexto = {'request': request, 'logos': imagenes.logos_parejos(c.logo for c in canales)}
    respuesta = {
        'cantidad': len(canales),
        'categorias': [
            {'id': categoria.pk if categoria else None, 'nombre': categoria.nombre if categoria else 'Otros',
             'canales': CanalSerializer(del_grupo, many=True, context=contexto).data}
            for categoria, del_grupo in agrupar_por_categoria(canales)
        ],
    }
    if contenido == Contenido.SERIE:
        respuesta['portadas'] = imagenes.portadas_de({clasificar.episodio(c.nombre)[0] for c in canales})
    return json.loads(json.dumps(respuesta))


class CatalogoRapidoTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        noticias = Categoria.objects.create(nombre='Noticias', orden=2)
        cine = Categoria.objects.create(nombre='VOD | ACCION', contenido=Contenido.PELICULA, orden=1)
        dibujos = Categoria.objects.create(nombre='Dibujos', contenido=Contenido.SERIE)

        def canal(nombre, contenido=Contenido.VIVO, categoria=None, **datos):
            return Canal.objects.create(nombre=nombre, contenido=contenido, categoria=categoria, **datos)

        # En vivo: varias fuentes (con orden por estabilidad), Xtream sin extensión, sin categoría, logos
        tn = canal('TN', categoria=noticias, numero='26', logo='https://logos.ejemplo.com/tn.png', destacado=True)
        Fuente.objects.create(canal=tn, url='https://a/tn.m3u8', prioridad=2, estado=Fuente.Estado.FUNCIONA)
        Fuente.objects.create(canal=tn, url='http://panel:8080/usu/cla/444', tipo=Fuente.Tipo.DIRECTO,
                              prioridad=1, user_agent='VLC/3.0', referer='https://ref/')
        Fuente.objects.create(canal=tn, url='https://a/tn-se-corta.m3u8', prioridad=0,
                              segundos_en_aparatos=3600, cortes_en_aparatos=60)
        Fuente.objects.create(canal=tn, url='https://a/apagada.m3u8', activa=False)
        Fuente.objects.create(canal=tn, url='https://a/caida.m3u8', estado=Fuente.Estado.CAIDA)
        roto = canal('Roto', categoria=noticias, logo='https://i.imgur.com/borrado.png')
        Fuente.objects.create(canal=roto, url='https://a/roto.m3u8')
        parejo = canal('Parejo', logo='https://logos.ejemplo.com/parejo.png')
        Fuente.objects.create(canal=parejo, url='https://a/parejo.m3u8', codec='h265')
        sin_fuentes = canal('Sin fuentes', categoria=noticias)
        Fuente.objects.create(canal=sin_fuentes, url='https://a/x.m3u8', estado=Fuente.Estado.CAIDA)
        quitado = canal('Quitado', categoria=noticias, activo=False)
        Fuente.objects.create(canal=quitado, url='https://a/q.m3u8')
        yt = canal('Solo YouTube', categoria=noticias)
        Fuente.objects.create(canal=yt, url='https://youtube.com/watch?v=x', tipo=Fuente.Tipo.YOUTUBE)
        LogoParejo.objects.create(clave=imagenes._clave_de(roto.logo), url=roto.logo, roto=True)
        LogoParejo.objects.create(clave=imagenes._clave_de(parejo.logo), url=parejo.logo,
                                  archivo='canales/logos/parejo.webp')

        # Películas y series
        for i, nombre in enumerate(['Toy Story (1995)', 'Ñandú: la película', 'Acción "con comillas"']):
            peli = canal(nombre, Contenido.PELICULA, cine, logo=f'https://posters/{i}.jpg', orden=i)
            Fuente.objects.create(canal=peli, url=f'http://panel:8080/movie/u/c/{i}.mkv', tipo=Fuente.Tipo.DIRECTO)
        for t, e in [(1, 1), (1, 2), (2, 1)]:
            cap = canal(f'Pocoyó S0{t} E0{e}', Contenido.SERIE, dibujos)
            Fuente.objects.create(canal=cap, url=f'http://panel:8080/series/u/c/{t}{e}.mp4',
                                  tipo=Fuente.Tipo.DIRECTO)
        imagenes.poner_portada('Pocoyó', 'https://ejemplo.com/pocoyo.jpg')

    def setUp(self):
        self.app = APIClient()
        clave, _ = tokens.crear_token(Usuario.objects.create_user('cliente', None, 'x'))
        self.app.credentials(HTTP_AUTHORIZATION=f'Bearer {clave}')
        cache.clear()

    def test_manda_exactamente_lo_mismo_que_antes(self):
        pedido = RequestFactory().get('/')
        for contenido in (Contenido.VIVO, Contenido.PELICULA, Contenido.SERIE):
            for formatos in (TODOS, 'hls', ''):
                tipos = tipos_pedidos(formatos)
                with self.subTest(contenido=contenido, formatos=formatos):
                    self.assertEqual(json.loads(json.dumps(catalogo.armar(tipos, contenido, pedido))),
                                     como_antes(pedido, tipos, contenido))

    def test_lo_que_llega_a_la_app(self):
        datos = self.app.get(reverse('api_v1:canales'), {'formatos': TODOS}).json()
        self.assertEqual(datos['cantidad'], 4)
        tn = canal_llamado(datos, 'TN')
        # La que se corta en los aparatos, al final; la Xtream en su forma .ts y con su User-Agent
        self.assertEqual([f['url'] for f in tn['fuentes']],
                         ['https://a/tn.m3u8', 'http://panel:8080/live/usu/cla/444.ts', 'https://a/tn-se-corta.m3u8'])
        self.assertEqual(tn['fuentes'][1]['user_agent'], 'VLC/3.0')
        self.assertTrue(tn['fuentes'][0]['user_agent'].startswith('Mozilla/5.0'))
        logos = {c['nombre']: c['logo'] for g in datos['categorias'] for c in g['canales']}
        self.assertEqual(logos['Roto'], '')
        self.assertEqual(logos['Parejo'], 'http://testserver/media/canales/logos/parejo.webp')
        series = self.app.get(reverse('api_v1:canales'), {'formatos': TODOS, 'contenido': 'serie'}).json()
        self.assertEqual(series['portadas'], {'Pocoyó': 'https://ejemplo.com/pocoyo.jpg'})

    def test_va_comprimido_si_la_app_lo_acepta(self):
        url = reverse('api_v1:canales')
        comprimido = self.app.get(url, {'contenido': 'pelicula', 'formatos': TODOS}, HTTP_ACCEPT_ENCODING='gzip')
        self.assertEqual(comprimido['Content-Encoding'], 'gzip')
        datos = json.loads(gzip.decompress(comprimido.content))
        self.assertEqual(datos['cantidad'], 3)
        self.assertIn('Ñandú: la película', gzip.decompress(comprimido.content).decode())   # acentos tal cual
        sin = self.app.get(url, {'contenido': 'pelicula', 'formatos': TODOS})
        self.assertFalse(sin.has_header('Content-Encoding'))
        self.assertEqual(sin.json(), datos)

    def test_si_la_app_ya_lo_tiene_no_se_manda_de_nuevo(self):
        url = reverse('api_v1:canales')
        primera = self.app.get(url, {'formatos': TODOS})
        huella = primera['ETag']
        otra = self.app.get(url, {'formatos': TODOS}, HTTP_IF_NONE_MATCH=huella)
        self.assertEqual(otra.status_code, 304)
        self.assertEqual(otra.content, b'')
        self.assertEqual(otra['ETag'], huella)
        # Algo cambió en el panel: otra huella y el catálogo nuevo
        Canal.objects.filter(nombre='TN').update(nombre='TN Todo Noticias')
        cambiado = self.app.get(url, {'formatos': TODOS}, HTTP_IF_NONE_MATCH=huella)
        self.assertEqual(cambiado.status_code, 200)
        self.assertNotEqual(cambiado['ETag'], huella)
        self.assertIn('TN Todo Noticias', nombres(cambiado.json()))

    def test_todavia_pide_sesion(self):
        self.assertEqual(APIClient().get(reverse('api_v1:canales')).status_code, 401)

    @override_settings(CATALOGO_APP_SEGUNDOS=60)
    def test_se_guarda_armado_un_rato(self):
        url = reverse('api_v1:canales')
        self.app.get(url, {'formatos': TODOS})
        Canal.objects.filter(nombre='TN').update(nombre='Otro nombre')
        # Dentro del minuto se manda el armado (sin volver a la base por el catálogo)
        self.assertIn('TN', nombres(self.app.get(url, {'formatos': TODOS}).json()))
        # Cada combinación (contenido, formatos) se guarda aparte
        self.assertIn('Otro nombre', nombres(self.app.get(url, {'formatos': 'hls'}).json()))
        cache.clear()
        self.assertIn('Otro nombre', nombres(self.app.get(url, {'formatos': TODOS}).json()))


class ComprimirTests(TestCase):
    """El panel y la API van comprimidos; las descargas (la APK) no."""

    def _pasar(self, respuesta):
        pedido = RequestFactory().get('/', HTTP_ACCEPT_ENCODING='gzip, deflate')
        return ComprimirMiddleware(lambda _: respuesta)(pedido)

    def test_comprime_paginas_y_json(self):
        for respuesta in (HttpResponse('<p>hola</p>' * 200), JsonResponse({'canales': ['TN'] * 300})):
            with self.subTest(tipo=respuesta['Content-Type']):
                self.assertEqual(self._pasar(respuesta)['Content-Encoding'], 'gzip')

    def test_no_toca_las_descargas(self):
        apk = FileResponse(iter([b'PK\x03\x04' * 1000]), content_type='application/vnd.android.package-archive')
        self.assertFalse(self._pasar(apk).has_header('Content-Encoding'))
        imagen = HttpResponse(b'\x89PNG' * 1000, content_type='image/png')
        self.assertFalse(self._pasar(imagen).has_header('Content-Encoding'))
