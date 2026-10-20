"""
Una lista grande (la de un proveedor: en vivo, películas y series juntos) se
trabaja por partes: se lee de a tandas (un servidor chico no la lee de una), y
se prueba, se carga o se descarta solo una parte (En vivo, una categoría, lo
buscado), sin esperar a probar todo.
"""

import tempfile
from pathlib import Path
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from canales import servicios
from canales.models import Canal, EntradaImportada, Importacion
from canales.servicios import Seleccion
from canales.tests.test_verificacion import verificador_falso
from usuarios.models import Rol, Usuario

Estado = EntradaImportada.Estado

LISTA = '''#EXTM3U
#EXTINF:-1 group-title="Noticias",Canal 26
https://anda/vivo/c26.m3u8
#EXTINF:-1 group-title="Noticias",Encuentro
https://anda/vivo/encuentro.m3u8
#EXTINF:-1 group-title="Deportes",Deportivo
https://caida/vivo/dep.m3u8
#EXTINF:-1 group-title="Acción",Película uno (2020)
https://anda/movie/u/c/1.mp4
#EXTINF:-1 group-title="Acción",Película dos (2021)
https://anda/movie/u/c/2.mp4
#EXTINF:-1 group-title="Novelas",La novela S01 E01
https://anda/series/u/c/1.mkv
#EXTINF:-1 group-title="Novelas",La novela S01 E02
https://anda/series/u/c/2.mkv
#EXTINF:-1 group-title="Novelas",La novela S01 E03
https://anda/series/u/c/3.mkv
#EXTINF:-1 group-title="Novelas",A medias S01 E02
https://anda/series/u/c/4.mkv
#EXTINF:-1 group-title="Novelas",A medias S01 E03
https://anda/series/u/c/5.mkv
#EXTINF:-1 group-title="Novelas",A medias S01 E04
https://anda/series/u/c/6.mkv
#EXTINF:-1,Sin grupo
https://anda/vivo/suelto.m3u8
#EXTINF:-1 group-title="Noticias",Canal 26 repetido
https://anda/vivo/c26.m3u8
'''


def _cuantas(importacion, **filtro):
    return importacion.entradas.filter(**filtro).count()


class PorPartesTests(TestCase):

    def setUp(self):
        self.importacion = servicios.crear_importacion(LISTA, 'proveedor.m3u')

    def test_que_trae_la_lista_por_partes_y_categorias(self):
        partes = [(clave, nombre, cuentas['total']) for clave, nombre, cuentas in
                  servicios.por_contenido(self.importacion)]
        # Siempre en el mismo orden (no por tamaño): se encuentran siempre en el mismo lugar
        self.assertEqual(partes, [('vivo', 'En vivo', 5), ('pelicula', 'Películas', 2), ('serie', 'Series', 6)])
        categorias = servicios.categorias_de(self.importacion, 'vivo')
        self.assertEqual([(c['nombre'], c['total'], c['pendientes'], c['repetidas']) for c in categorias],
                         [('Noticias', 3, 2, 1), ('Deportes', 1, 1, 0), ('Sin categoría', 1, 1, 0)])
        self.assertEqual(categorias[2]['clave'], servicios.SIN_CATEGORIA)

    def test_probar_y_cargar_una_categoria_sin_esperar_al_resto(self):
        noticias = Seleccion('vivo', 'Noticias')
        avance = servicios.procesar_lote(self.importacion, verificador_falso, seleccion=noticias)
        self.assertTrue(avance['terminada'])   # esa parte ya está probada...
        self.assertEqual(avance['en_la_seleccion']['aptas'], 2)
        self.assertEqual(avance['pendientes'], 10)   # ...aunque falte el resto de la lista
        self.assertFalse(servicios.falta_probar(self.importacion, noticias))
        avance = servicios.cargar_lote(self.importacion, seleccion=noticias)
        self.assertEqual(set(Canal.objects.values_list('nombre', flat=True)), {'Canal 26', 'Encuentro'})
        self.assertEqual(avance['en_la_seleccion']['agregadas'], 2)
        self.assertIsNone(Importacion.objects.get().cargada)   # la lista no terminó

    def test_no_se_carga_una_parte_que_falta_probar(self):
        en_vivo = Seleccion('vivo')
        servicios.procesar_lote(self.importacion, verificador_falso, seleccion=Seleccion('vivo', 'Noticias'))
        self.assertTrue(servicios.falta_probar(self.importacion, en_vivo))   # falta Deportes
        servicios.cargar_lote(self.importacion, seleccion=en_vivo)
        self.assertFalse(Canal.objects.exists())

    def test_las_series_se_revisan_al_terminar_su_parte(self):
        series = Seleccion('serie')
        avance = servicios.procesar_lote(self.importacion, verificador_falso, seleccion=series)
        # "A medias" no tiene el capítulo 1: la app no la mostraría
        self.assertEqual(avance['en_la_seleccion']['aptas'], 3)
        self.assertEqual(_cuantas(self.importacion, estado=Estado.RECHAZADA,
                                  causa=EntradaImportada.Causa.SERIE_INCOMPLETA), 3)
        servicios.cargar_lote(self.importacion, seleccion=series)
        self.assertEqual(Canal.objects.filter(nombre__startswith='La novela').count(), 3)

    def test_buscar_tambien_elige_la_parte(self):
        buscada = Seleccion(texto='a medias')   # busca en el nombre y en la categoría
        self.assertEqual(servicios.progreso(self.importacion, buscada)['en_la_seleccion']['total'], 3)

    def test_descartar_una_parte(self):
        cantidad = servicios.descartar(self.importacion, Seleccion('pelicula'))
        self.assertEqual(cantidad, 2)
        self.assertEqual(_cuantas(self.importacion, contenido='pelicula', estado=Estado.DESCARTADA), 2)
        avance = servicios.progreso(self.importacion)
        self.assertEqual(avance['pendientes'], 10)
        self.assertEqual(avance['para_verificar'], 10)   # el avance ya no cuenta lo que se descartó


class ListaGrandeTests(TestCase):
    """Más de LEER_DE_UNA entradas: se guarda y se lee de a tandas."""

    def setUp(self):
        carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(carpeta.cleanup)
        self.carpeta = Path(carpeta.name)
        for nombre, valor in (('LEER_DE_UNA', 5), ('CARPETA_DE_LISTAS', self.carpeta)):
            parche = mock.patch.object(servicios, nombre, valor)
            parche.start()
            self.addCleanup(parche.stop)

    def test_se_lee_de_a_tandas(self):
        importacion = servicios.preparar_importacion(LISTA, 'grande.m3u')
        self.assertEqual((importacion.total, importacion.por_leer, importacion.entradas.count()), (13, 13, 0))
        self.assertTrue(any(self.carpeta.iterdir()))
        vueltas = 0
        while not servicios.leer_lote(importacion, tamanio=4)['terminada']:
            vueltas += 1
        self.assertEqual(vueltas, 3)
        importacion.refresh_from_db()
        self.assertEqual((importacion.por_leer, importacion.entradas.count()), (0, 13))
        self.assertEqual(list(importacion.entradas.values_list('posicion', flat=True)), list(range(1, 14)))
        # La dirección repetida se reconoce aunque la primera vez haya sido en otra tanda
        self.assertEqual(importacion.entradas.get(posicion=13).estado, Estado.REPETIDA)
        self.assertEqual(importacion.para_verificar, 12)
        self.assertFalse(any(self.carpeta.iterdir()))   # la lista guardada se borra al terminar

    def test_una_lista_chica_se_lee_de_una(self):
        importacion = servicios.preparar_importacion('#EXTM3U\n#EXTINF:-1,Uno\nhttps://anda/1.m3u8\n', 'chica.m3u')
        self.assertEqual((importacion.por_leer, importacion.entradas.count()), (0, 1))

    def test_no_se_prueba_mientras_se_lee(self):
        importacion = servicios.preparar_importacion(LISTA, 'grande.m3u')
        servicios.procesar_lote(importacion, verificador_falso)
        servicios.cargar_lote(importacion)
        self.assertFalse(Canal.objects.exists())


@mock.patch('canales.views.verificar_varias', verificador_falso)
class PantallaPorPartesTests(TestCase):

    def setUp(self):
        rol = Rol.objects.create(nombre='Canales', permisos=['ver_canales', 'importar_canales'])
        self.client.force_login(Usuario.objects.create_user('marcos', None, 'x', rol=rol))
        carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(carpeta.cleanup)
        for nombre, valor in (('LEER_DE_UNA', 5), ('CARPETA_DE_LISTAS', Path(carpeta.name))):
            parche = mock.patch.object(servicios, nombre, valor)
            parche.start()
            self.addCleanup(parche.stop)

    def test_subir_una_lista_grande_leerla_y_trabajar_por_partes(self):
        respuesta = self.client.post(reverse('canales:inicio'), {
            'archivo': SimpleUploadedFile('proveedor.m3u', LISTA.encode()), 'descartar_adultos': 'on'})
        importacion = Importacion.objects.get()
        url = reverse('canales:importacion', args=[importacion.pk])
        self.assertRedirects(respuesta, url)   # sin ?empezar=1: no se prueba todo de una
        leyendo = self.client.get(url)
        self.assertContains(leyendo, 'Leyendo la lista')
        self.assertContains(leyendo, 'data-accion="cancelar-lectura"')
        leida = self.client.post(reverse('canales:importacion_leer', args=[importacion.pk])).json()
        self.assertTrue(leida['terminada'])

        pagina = self.client.get(url)
        self.assertContains(pagina, 'Qué trae esta lista')
        for parte in ('En vivo', 'Películas', 'Series'):
            self.assertContains(pagina, parte)
        # Sin elegir una parte, las categorías de toda la lista (cada una dice de qué parte es)
        self.assertContains(pagina, 'Categorías de toda la lista')
        self.assertContains(pagina, 'href="?contenido=pelicula&amp;categoria=')

        pagina = self.client.get(url, {'contenido': 'vivo'})
        self.assertContains(pagina, 'Categorías de En vivo')
        self.assertContains(pagina, 'href="?contenido=vivo&amp;categoria=Noticias#trabajo"')

        datos = {'contenido': 'vivo', 'categoria': 'Noticias'}
        avance = self.client.post(reverse('canales:importacion_lote', args=[importacion.pk]), datos).json()
        self.assertEqual((avance['terminada'], avance['en_la_seleccion']['aptas']), (True, 2))
        pagina = self.client.get(url, datos)
        self.assertContains(pagina, 'Estás trabajando con')
        self.assertContains(pagina, 'Cargar los 2 que pasaron')
        self.client.post(reverse('canales:importacion_cargar', args=[importacion.pk]), datos)
        self.assertEqual(Canal.objects.count(), 2)

        respuesta = self.client.post(reverse('canales:importacion_descartar', args=[importacion.pk]),
                                     {'contenido': 'pelicula'}, follow=True)
        self.assertContains(respuesta, 'quedaron descartados')
        self.assertEqual(importacion.entradas.filter(contenido='pelicula', estado=Estado.DESCARTADA).count(), 2)
