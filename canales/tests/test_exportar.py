"""Exportar desde Organizar contenido: qué se elige, la lista M3U8 (y volver a importarla) y la planilla de Excel."""

import zipfile
from io import BytesIO

from django.test import TestCase
from django.urls import reverse

from canales import exportar, imagenes, secciones
from canales.m3u import leer_m3u
from canales.models import Canal, Categoria, Contenido, Fuente, Importacion, Seccion
from canales.servicios import importar_m3u
from herramientas.excel import TIPO_XLSX
from usuarios.models import Rol, Usuario


def _canal(nombre, categoria=None, contenido=Contenido.VIVO, fuentes=1, **datos):
    canal = Canal.objects.create(nombre=nombre, categoria=categoria, contenido=contenido, **datos)
    for numero in range(1, fuentes + 1):
        Fuente.objects.create(canal=canal, url=f'https://x/{nombre.replace(" ", "")}-{numero}.m3u8', prioridad=numero,
                              origen='lista.m3u')
    return canal


def _nombres(exportacion):
    return [canal.nombre for canal, _ in exportacion.canales]


class ElegirTests(TestCase):

    def setUp(self):
        self.noticias = Categoria.objects.create(nombre='Noticias', orden=1)
        self.deportes = Categoria.objects.create(nombre='Deportes', orden=2)
        self.accion = Categoria.objects.create(nombre='Acción', contenido=Contenido.PELICULA)
        self.infantiles = Categoria.objects.create(nombre='Series Infantiles', contenido=Contenido.SERIE)
        _canal('TN', self.noticias)
        _canal('Canal 26', self.noticias, idioma='es')
        _canal('TyC Sports', self.deportes)
        _canal('Suelto')
        _canal('Duro de matar', self.accion, Contenido.PELICULA)
        for numero in (10, 2, 1):   # los capítulos salen en orden aunque se hayan cargado salteados
            _canal(f'Pocoyó S01 E{numero:02d}', self.infantiles, Contenido.SERIE)

    def test_todo_en_el_orden_de_la_app(self):
        todo = exportar.elegir(exportar.Eleccion(secciones=['vivo', 'pelicula', 'serie']))
        self.assertEqual(_nombres(todo), ['Canal 26', 'TN', 'TyC Sports', 'Suelto', 'Duro de matar',
                                          'Pocoyó S01 E01', 'Pocoyó S01 E02', 'Pocoyó S01 E10'])

    def test_una_seccion_varias_categorias_o_lo_sin_categoria(self):
        self.assertEqual(_nombres(exportar.elegir(exportar.Eleccion(secciones=['pelicula']))), ['Duro de matar'])
        varias = exportar.Eleccion(categorias=[self.deportes.pk, self.accion.pk])
        self.assertEqual(_nombres(exportar.elegir(varias)), ['TyC Sports', 'Duro de matar'])
        self.assertEqual(_nombres(exportar.elegir(exportar.Eleccion(sin_categoria=['vivo']))), ['Suelto'])

    def test_un_canal_o_una_serie_en_particular(self):
        tn = Canal.objects.get(nombre='TN')
        eleccion = exportar.Eleccion(canales=[tn.pk], series=['Pocoyó'])
        self.assertEqual(_nombres(exportar.elegir(eleccion)), ['TN', 'Pocoyó S01 E01', 'Pocoyó S01 E02',
                                                               'Pocoyó S01 E10'])

    def test_con_los_filtros_de_organizar(self):
        Canal.objects.filter(nombre='TN').update(activo=False)
        eleccion = exportar.Eleccion(secciones=['vivo'], filtros={'mostrar': 'app', 'texto': 'c'})
        self.assertEqual(_nombres(exportar.elegir(eleccion)), ['Canal 26', 'TyC Sports'])
        eleccion.filtros = {'idioma': 'es'}
        self.assertEqual(_nombres(exportar.elegir(eleccion)), ['Canal 26'])

    def test_lo_de_youtube_no_sale(self):
        pelicula = _canal('Tormenta Blanca', self.accion, Contenido.PELICULA, fuentes=0)
        Fuente.objects.create(canal=pelicula, url='https://www.youtube.com/watch?v=abcdefghijk',
                              tipo=Fuente.Tipo.YT_VIDEO)
        mixto = Canal.objects.get(nombre='TN')
        Fuente.objects.create(canal=mixto, url='https://www.youtube.com/@tn/live', tipo=Fuente.Tipo.YOUTUBE,
                              prioridad=0)
        resultado = exportar.elegir(exportar.Eleccion(secciones=['vivo', 'pelicula']))
        self.assertNotIn('Tormenta Blanca', _nombres(resultado))
        self.assertEqual(resultado.sin_senales, 1)
        tn = dict(resultado.canales)[mixto]
        self.assertEqual([f.url for f in tn], ['https://x/TN-1.m3u8'])   # sale con la que no es de YouTube

    def test_solo_las_senales_que_andan(self):
        canal = _canal('Dos señales', self.noticias, fuentes=2)
        canal.fuentes.filter(prioridad=1).update(estado=Fuente.Estado.CAIDA)
        eleccion = exportar.Eleccion(canales=[canal.pk])
        self.assertEqual(len(exportar.elegir(eleccion).canales[0][1]), 2)
        eleccion.solo_las_que_andan = True
        self.assertEqual([f.url for f in exportar.elegir(eleccion).canales[0][1]], ['https://x/Dosseñales-2.m3u8'])

    def test_sin_elegir_nada_no_sale_nada(self):
        self.assertTrue(exportar.Eleccion().vacia)
        self.assertEqual(exportar.elegir(exportar.Eleccion()).canales, [])


class ListaM3UTests(TestCase):

    def test_cada_senal_con_sus_datos(self):
        noticias = Categoria.objects.create(nombre='Noticias')
        canal = _canal('Canal "26"', noticias, fuentes=2, logo='https://img/26.png', numero='26', pais='AR',
                       idioma='es', tvg_id='Canal26.ar')
        canal.fuentes.filter(prioridad=2).update(user_agent='VLC/3.0', referer='https://canal26.com.ar/')
        texto = exportar.lista_m3u(exportar.elegir(exportar.Eleccion(canales=[canal.pk])))
        lineas = texto.splitlines()
        self.assertEqual(lineas[0], '#EXTM3U')
        self.assertIn('#EXTINF:-1 tvg-id="Canal26.ar" tvg-name="Canal \'26\'" tvg-logo="https://img/26.png" '
                      'tvg-chno="26" tvg-country="AR" tvg-language="Spanish" group-title="Noticias" '
                      'kairos-seccion="vivo",Canal "26"', lineas)
        self.assertIn('#EXTVLCOPT:http-user-agent=VLC/3.0', lineas)
        self.assertIn('#EXTVLCOPT:http-referrer=https://canal26.com.ar/', lineas)
        # Otra app la lee: dos entradas con el mismo canal, cada una con su dirección
        leidas = leer_m3u(texto)
        self.assertEqual([(e.nombre, e.url, e.user_agent) for e in leidas],
                         [("Canal '26'", 'https://x/Canal"26"-1.m3u8', ''),
                          ("Canal '26'", 'https://x/Canal"26"-2.m3u8', 'VLC/3.0')])

    def test_exportar_borrar_y_volver_a_importar_deja_todo_igual(self):
        secciones.crear('Música', Seccion.Forma.A_DEMANDA)
        cine = Categoria.objects.create(nombre='Cine', contenido=Contenido.PELICULA)
        rock = Categoria.objects.create(nombre='Rock', contenido='musica')
        _canal('Canal 26', Categoria.objects.create(nombre='Noticias'), fuentes=2, logo='https://img/26.png',
               numero='26')
        # Una película y un video de música con dirección de "en vivo": sin la sección anotada volverían a En vivo
        _canal('Matrix (1999)', cine, Contenido.PELICULA)
        _canal('Soda Stereo - Persiana americana', rock, 'musica')
        # Una serie nueva de UN capítulo: en una lista cualquiera no entraría (pide 3), en una de acá sí
        _canal('Electro Andes S01 E01', Categoria.objects.create(nombre='Series', contenido=Contenido.SERIE),
               Contenido.SERIE)
        antes = sorted(Canal.objects.values_list('nombre', 'contenido', 'categoria__nombre', 'logo', 'numero'))
        texto = exportar.lista_m3u(exportar.elegir(exportar.Eleccion(secciones=['vivo', 'pelicula', 'serie',
                                                                                'musica'])))

        Canal.todos.all().delete()
        importar_m3u(texto, 'kairos-tv-todo.m3u8')

        self.assertTrue(Importacion.objects.get().de_kairos)
        self.assertEqual(sorted(Canal.objects.values_list('nombre', 'contenido', 'categoria__nombre', 'logo',
                                                          'numero')), antes)
        self.assertEqual(Canal.objects.get(nombre='Canal 26').fuentes.count(), 2)   # se juntaron en uno

    def test_una_lista_cualquiera_sigue_pidiendo_3_capitulos(self):
        importar_m3u('#EXTM3U\n#EXTINF:-1 group-title="Series",Electro Andes S01 E01\n'
                     'https://x/series/electro-1.mkv\n', 'otra.m3u')
        self.assertFalse(Importacion.objects.get().de_kairos)
        self.assertFalse(Canal.objects.exists())


class PlanillaTests(TestCase):

    def test_dos_hojas_contenido_y_fuentes(self):
        infantiles = Categoria.objects.create(nombre='Series Infantiles', contenido=Contenido.SERIE)
        for numero in (1, 2):
            _canal(f'Pocoyó S01 E0{numero} El tornado', infantiles, Contenido.SERIE)
        imagenes.poner_portada('Pocoyó', 'https://img/pocoyo.jpg')
        Canal.objects.get(nombre__contains='E02').fuentes.update(estado=Fuente.Estado.CAIDA, error='No responde')
        datos = exportar.planilla_excel(exportar.elegir(exportar.Eleccion(series=['Pocoyó'])))

        with zipfile.ZipFile(BytesIO(datos)) as libro:
            hojas = libro.read('xl/workbook.xml').decode()
            contenido = libro.read('xl/worksheets/hoja1.xml').decode()
            fuentes = libro.read('xl/worksheets/hoja2.xml').decode()
        self.assertIn('name="Contenido"', hojas)
        self.assertIn('name="Fuentes"', hojas)
        for texto in ('Series', 'Series Infantiles', 'Pocoyó', 'Pocoyó S01 E01 El tornado', 'https://img/pocoyo.jpg',
                      'Todas sus fuentes están caídas.'):
            self.assertIn(f'>{texto}<', contenido)
        self.assertIn('<v>2</v>', contenido)   # el número de capítulo, como número
        for texto in ('https://x/PocoyóS01E02Eltornado-1.m3u8', 'Caída', 'No responde', 'lista.m3u'):
            self.assertIn(f'>{texto}<', fuentes)


class PantallaTests(TestCase):

    def setUp(self):
        self.client.force_login(Usuario.objects.create_superuser('admin', 'admin@test.com', 'x'))
        self.noticias = Categoria.objects.create(nombre='Noticias')
        self.tn = _canal('TN', self.noticias)

    def test_el_cuadro_esta_en_organizar(self):
        respuesta = self.client.get(reverse('canales:organizar'), {'categoria': self.noticias.pk, 'q': 'tn'})
        self.assertContains(respuesta, 'id="form-exportar"')
        self.assertContains(respuesta, 'Con los filtros de arriba: busca «tn»')
        # La categoría que se está viendo viene marcada
        self.assertRegex(respuesta.content.decode(),
                         rf'value="{self.noticias.pk}" id="exp-vivo-1"\s+data-de="vivo" checked')

    def test_baja_la_lista(self):
        respuesta = self.client.post(reverse('canales:organizar_exportar'), {'seccion': 'vivo', 'formato': 'm3u'})
        self.assertEqual(respuesta['Content-Type'], 'audio/x-mpegurl; charset=utf-8')
        self.assertRegex(respuesta['Content-Disposition'],
                         r'attachment; filename="kairos-tv-en-vivo-\d{4}-\d\d-\d\d\.m3u8"')
        self.assertIn(b'https://x/TN-1.m3u8', respuesta.content)

    def test_baja_el_excel_de_lo_elegido(self):
        respuesta = self.client.post(reverse('canales:organizar_exportar'),
                                     {'que': 'elegido', 'canal': [self.tn.pk], 'formato': 'excel'})
        self.assertEqual(respuesta['Content-Type'], TIPO_XLSX)
        self.assertIn('kairos-tv-eleccion-', respuesta['Content-Disposition'])
        self.assertTrue(zipfile.is_zipfile(BytesIO(respuesta.content)))

    def test_los_filtros_se_aplican_solo_si_se_pide(self):
        _canal('Canal 26', self.noticias)
        datos = {'seccion': 'vivo', 'q': '26', 'mostrar': 'todo'}
        self.assertIn(b'TN', self.client.post(reverse('canales:organizar_exportar'), datos).content)
        con_filtros = self.client.post(reverse('canales:organizar_exportar'), {**datos, 'con_filtros': '1'}).content
        self.assertNotIn(b'TN', con_filtros)
        self.assertIn(b'Canal 26', con_filtros)

    def test_sin_nada_para_exportar_avisa(self):
        respuesta = self.client.post(reverse('canales:organizar_exportar'), {'seccion': 'pelicula'}, follow=True)
        self.assertContains(respuesta, 'No hay nada para exportar con esa elección.')
        respuesta = self.client.post(reverse('canales:organizar_exportar'), {}, follow=True)
        self.assertContains(respuesta, 'Elegí qué exportar')

    def test_quien_solo_mira_no_puede_exportar(self):
        solo_ve = Usuario.objects.create_user(
            'mira', None, 'x', rol=Rol.objects.create(nombre='Mira', permisos=['ver_canales']))
        self.client.force_login(solo_ve)
        self.assertNotContains(self.client.get(reverse('canales:organizar')), 'id="form-exportar"')
        self.assertEqual(self.client.post(reverse('canales:organizar_exportar'), {'seccion': 'vivo'}).status_code, 403)
