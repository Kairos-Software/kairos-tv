"""
"¿Dónde va?" en una lista importada: antes de cargar, lo elegido va a una
categoría del panel (o una nueva) y, en Series, a una serie (existente o
nueva). Y al cargar, un capítulo que la serie ya tiene suma una fuente en vez
de quedar repetido, y los capítulos nuevos de una serie que ya existe van a
la categoría de esa serie.
"""

from unittest import mock

from django.test import TestCase
from django.urls import reverse

from canales import organizar, servicios
from canales.models import Canal, Categoria, EntradaImportada, Fuente
from canales.servicios import Seleccion
from canales.tests.test_verificacion import verificador_falso
from usuarios.models import Rol, Usuario

Estado = EntradaImportada.Estado

LISTA = '''#EXTM3U
#EXTINF:-1 group-title="SERIES CARTOON",Boruto Next Generations S01 E01
https://anda/series/u/c/1.mkv
#EXTINF:-1 group-title="SERIES CARTOON",Boruto Next Generations S01 E02
https://anda/series/u/c/2.mkv
#EXTINF:-1 group-title="SERIES CARTOON",Boruto Next Generations S01 E03
https://anda/series/u/c/3.mkv
#EXTINF:-1 group-title="SERIES CARTOON",Otra serie S01 E01
https://anda/series/u/c/4.mkv
#EXTINF:-1 group-title="SERIES CARTOON",Otra serie S01 E02
https://anda/series/u/c/5.mkv
#EXTINF:-1 group-title="SERIES CARTOON",Otra serie S01 E03
https://anda/series/u/c/6.mkv
#EXTINF:-1 group-title="Acción",Película uno (2020)
https://anda/movie/u/c/1.mp4
'''

BORUTO = Seleccion('serie', 'SERIES CARTOON', 'boruto')


class DondeVaTests(TestCase):

    def setUp(self):
        # En el panel ya está "Boruto", en Anime, con su capítulo 1
        self.anime = Categoria.objects.create(nombre='Anime', contenido='serie')
        self.capitulo_1 = Canal.objects.create(nombre='Boruto S01 E01', contenido='serie', categoria=self.anime)
        Fuente.objects.create(canal=self.capitulo_1, url='https://anda/panel/b1.mkv', estado=Fuente.Estado.FUNCIONA)
        self.cine = Categoria.objects.create(nombre='Cine', contenido='pelicula')
        self.importacion = servicios.crear_importacion(LISTA, 'proveedor.m3u')

    def probar_y_cargar(self, seleccion):
        servicios.procesar_lote(self.importacion, verificador_falso, seleccion=seleccion)
        return servicios.cargar_lote(self.importacion, seleccion=seleccion)

    def test_como_va_hoy(self):
        va = servicios.como_va(self.importacion, Seleccion('serie'))
        self.assertEqual(va['categorias'], [{'nombre': 'SERIES CARTOON', 'cantidad': 6, 'va_a': ''}])
        self.assertEqual(va['nuevas'], 1)
        # "Boruto Next Generations" no se llama como la del panel: hoy sería otra serie
        self.assertEqual(va['series'], {'total': 2, 'existen': 0})
        self.assertEqual(servicios.como_va(self.importacion, Seleccion('pelicula'))['series'], None)

    def test_a_una_serie_que_ya_existe(self):
        cantidad, quedo, _ = servicios.ubicar(self.importacion, BORUTO, serie='Boruto')
        self.assertEqual(cantidad, 3)
        # Va en la categoría de la serie, aunque no se eligió ninguna
        self.assertEqual(quedo, Seleccion('serie', 'Anime', 'Boruto'))
        self.assertEqual(sorted(self.importacion.entradas.filter(categoria='Anime').values_list('nombre', flat=True)),
                         ['Boruto S01 E01', 'Boruto S01 E02', 'Boruto S01 E03'])
        self.probar_y_cargar(quedo)
        capitulos = Canal.objects.filter(nombre__startswith='Boruto')
        self.assertEqual(capitulos.count(), 3)   # el capítulo 1 no quedó repetido...
        self.assertEqual(self.capitulo_1.fuentes.count(), 2)   # ...sumó la dirección como otra fuente
        self.assertEqual(set(capitulos.values_list('categoria', flat=True)), {self.anime.pk})

    def test_una_serie_existente_no_cambia_de_categoria(self):
        Categoria.objects.create(nombre='Infantiles', contenido='serie')
        with self.assertRaises(organizar.NoSePuede):
            servicios.ubicar(self.importacion, BORUTO, serie='Boruto', categoria='Infantiles')

    def test_a_una_serie_nueva_en_una_temporada(self):
        _, quedo, _ = servicios.ubicar(self.importacion, Seleccion('serie', 'SERIES CARTOON', 'otra serie'),
                                       serie='La otra', categoria='Dibujos', temporada=2)
        self.assertEqual(quedo.categoria, 'Dibujos')
        self.assertEqual(sorted(self.importacion.entradas.filter(nombre__startswith='La otra')
                                .values_list('nombre', flat=True)),
                         ['La otra S02 E01', 'La otra S02 E02', 'La otra S02 E03'])

    def test_los_que_no_traen_numero_siguen_despues_del_ultimo(self):
        Canal.objects.create(nombre='Boruto S01 E07', contenido='serie', categoria=self.anime)
        sueltos = [EntradaImportada(nombre='Boruto especial', categoria='SERIES CARTOON', contenido='serie')]
        servicios._a_la_serie(sueltos, 'Boruto')
        self.assertEqual(sueltos[0].nombre, 'Boruto S01 E08 especial')

    def test_la_serie_incompleta_se_completa_con_la_del_panel(self):
        # Sin el capítulo 1 en la lista: al terminar de probar, "Boruto Next Generations" no pasa...
        self.importacion.entradas.filter(nombre__endswith='E01', nombre__startswith='Boruto').delete()
        servicios.procesar_lote(self.importacion, verificador_falso, seleccion=BORUTO)
        self.assertEqual(self.importacion.entradas.filter(causa=EntradaImportada.Causa.SERIE_INCOMPLETA).count(), 2)
        # ...pero en "Boruto" del panel está el capítulo 1: ahí sí se muestra
        _, quedo, _ = servicios.ubicar(self.importacion, BORUTO, serie='Boruto')
        self.assertEqual(servicios.progreso(self.importacion, quedo)['en_la_seleccion']['aptas'], 2)

    def test_una_categoria_del_panel_y_recordarla(self):
        accion = Seleccion('pelicula', 'Acción')
        cantidad, quedo, recordado = servicios.ubicar(self.importacion, accion, categoria='cine', recordar=True)
        self.assertEqual((cantidad, quedo.categoria, recordado), (1, 'Cine', True))   # escrita como en el panel
        self.probar_y_cargar(quedo)
        self.assertEqual(Canal.objects.get(nombre='Película uno (2020)').categoria, self.cine)
        # La próxima lista que traiga "Acción" va directo a Cine
        self.assertEqual(organizar.categoria_existente('Acción', 'pelicula'), self.cine)

    def test_no_se_recuerda_si_ya_hay_una_categoria_con_ese_nombre(self):
        Categoria.objects.create(nombre='Acción', contenido='pelicula')
        _, _, recordado = servicios.ubicar(self.importacion, Seleccion('pelicula', 'Acción'), categoria='Cine',
                                           recordar=True)
        self.assertFalse(recordado)

    def test_sin_ubicar_un_capitulo_va_a_la_categoria_de_su_serie(self):
        servicios.crear_importacion('#EXTM3U\n'
                                    '#EXTINF:-1 group-title="SERIES CARTOON",Boruto S01 E02\n'
                                    'https://anda/series/u/c/8.mkv\n'
                                    '#EXTINF:-1 group-title="SERIES CARTOON",Boruto S01 E03\n'
                                    'https://anda/series/u/c/9.mkv\n', 'otra.m3u')
        otra = servicios.Importacion.objects.get(archivo='otra.m3u')
        servicios.procesar_lote(otra, verificador_falso)
        servicios.cargar_lote(otra)
        self.assertEqual(Canal.objects.get(nombre='Boruto S01 E02').categoria, self.anime)
        self.assertFalse(Categoria.objects.filter(nombre='SERIES CARTOON').exists())

    def test_lo_que_no_se_puede(self):
        with self.assertRaises(organizar.NoSePuede):
            servicios.ubicar(self.importacion, Seleccion(), categoria='Cine')   # sin elegir la parte
        with self.assertRaises(organizar.NoSePuede):
            servicios.ubicar(self.importacion, Seleccion('pelicula'), serie='Boruto')   # una película no
        with self.assertRaises(organizar.NoSePuede):
            servicios.ubicar(self.importacion, Seleccion('pelicula'))   # nada elegido


@mock.patch('canales.views.verificar_varias', verificador_falso)
class PantallaDondeVaTests(TestCase):

    def setUp(self):
        rol = Rol.objects.create(nombre='Canales', permisos=['ver_canales', 'importar_canales'])
        self.client.force_login(Usuario.objects.create_user('marcos', None, 'x', rol=rol))
        anime = Categoria.objects.create(nombre='Anime', contenido='serie')
        Canal.objects.create(nombre='Boruto S01 E01', contenido='serie', categoria=anime)
        self.importacion = servicios.crear_importacion(LISTA, 'proveedor.m3u')
        self.url = reverse('canales:importacion', args=[self.importacion.pk])

    def test_el_paso_aparece_al_elegir_una_parte(self):
        self.assertContains(self.client.get(self.url), 'Elegí arriba una parte')
        pagina = self.client.get(self.url, {'contenido': 'serie', 'categoria': 'SERIES CARTOON'})
        self.assertContains(pagina, '¿Dónde va?')
        self.assertContains(pagina, '«SERIES CARTOON» <span class="chip">nueva</span>', html=False)
        self.assertContains(pagina, '<option value="Boruto" data-categoria="Anime">Boruto</option>', html=True)
        self.assertContains(pagina, 'Recordarlo')

    def test_mandarlo_a_una_serie(self):
        respuesta = self.client.post(reverse('canales:importacion_destino', args=[self.importacion.pk]), {
            'contenido': 'serie', 'categoria': 'SERIES CARTOON', 'q': 'boruto', 'destino_serie': 'Boruto'},
            follow=True)
        self.assertContains(respuesta, 'Listo: 3 van a «Anime › Boruto»')
        self.assertEqual(respuesta.redirect_chain[-1][0],
                         f'{self.url}?contenido=serie&categoria=Anime&q=Boruto#trabajo')

    def test_una_categoria_nueva(self):
        self.client.post(reverse('canales:importacion_destino', args=[self.importacion.pk]), {
            'contenido': 'pelicula', 'destino_categoria': '+nueva', 'categoria_nueva': 'Estrenos'})
        self.assertEqual(self.importacion.entradas.get(contenido='pelicula').categoria, 'Estrenos')

    def test_un_error_se_explica(self):
        respuesta = self.client.post(reverse('canales:importacion_destino', args=[self.importacion.pk]),
                                     {'contenido': 'pelicula'}, follow=True)
        self.assertContains(respuesta, 'Elegí la categoría o la serie donde va.')
