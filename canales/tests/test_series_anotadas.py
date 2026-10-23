"""
Las series de Organizar armadas en la base: cada capítulo tiene anotada su
serie, temporada y número (Canal.serie, consultas.anotar_series) y la base
los agrupa (consultas.resumen_de_series). Con decenas de miles de capítulos,
entrar a Organizar > Series tardaba 30 segundos. Tienen que dar EXACTAMENTE lo
mismo que las series armadas capítulo por capítulo (consultas.series), y la
anotación tiene que seguir al nombre se cambie por donde se cambie.
"""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from canales import consultas, imagenes, organizar
from canales.models import Canal, Categoria, Contenido, Fuente
from usuarios.models import Usuario


def _resumen(lista):
    """Todo lo que Organizar muestra de cada serie."""
    return [(s.nombre, s.categoria, s.categoria_id, s.logo, s.portada, s.cantidad, s.en_la_app, s.fuera, s.completa,
             s.por_que_no_se_ve, s.numeros_de_temporada) for s in lista]


def _armadas(**filtros):
    """Lo mismo, de las series armadas capítulo por capítulo (con lo que las resumidas traen aparte)."""
    series = consultas.series(**filtros)
    return [(*fila, any(c.canal.activo for c in s.capitulos), any(c.canal.destacado for c in s.capitulos),
             any(c.canal.fuentes_fuera for c in s.capitulos), any(not c.canal.logo for c in s.capitulos))
            for fila, s in zip(_resumen(series), series)]


def _resumidas(**filtros):
    series = consultas.resumen_de_series(**filtros)
    return [(*fila, s.activo, s.destacado, s.senales_fuera, s.capitulos_sin_imagen)
            for fila, s in zip(_resumen(series), series)]


class SeriesAnotadasTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        ahora = timezone.now()
        dibujos = Categoria.objects.create(nombre='Dibujos', contenido=Contenido.SERIE, orden=2)
        drama = Categoria.objects.create(nombre='SERIES | DRAMA', contenido=Contenido.SERIE, orden=1)

        def capitulo(nombre, categoria=None, fuentes=(), **datos):
            canal = Canal.objects.create(nombre=nombre, contenido=Contenido.SERIE, categoria=categoria, **datos)
            for i, fuente in enumerate(fuentes):
                Fuente.objects.create(canal=canal, url=f'https://x/{canal.pk}/{i}.mp4', origen='lista_a.m3u',
                                      **{'tipo': Fuente.Tipo.DIRECTO, **fuente})
            return canal

        bien = {}
        # Pocoyó: completa, con una señal caída en un capítulo y un capítulo destacado
        capitulo('Pocoyó S01 E01', dibujos, [bien, {'estado': Fuente.Estado.CAIDA}], logo='https://img/p1.jpg')
        capitulo('Pocoyó S01 E02 La pelota', dibujos, [bien], destacado=True)
        capitulo('Pocoyó S02 E01', dibujos, [{'oculta_hasta': ahora - timedelta(hours=1)}])   # ya volvió
        # Arrow: le falta el primero (el E01 solo tiene una oculta por fallar en los aparatos)
        capitulo('Arrow S01 E01', drama, [{'oculta_hasta': ahora + timedelta(hours=3)}])
        capitulo('Arrow S01 E02', drama, [bien, {'activa': False}])
        # Lost: quitada a mano; y otra sin fuentes; y una con una señal que la app no abre
        capitulo('Lost S01 E01', drama, [bien], activo=False)
        capitulo('Sin señales S01 E01', drama)
        capitulo('Rara S01 E01', None, [{'tipo': 'otro'}], logo='https://img/rara.jpg')
        # Un video suelto cargado como serie (sin "S01 E01")
        capitulo('Especial de Navidad', dibujos, [bien])
        # Masha: la imagen es la del primer capítulo que tenga (por temporada y número), en dos categorías
        capitulo('Masha S02 E01', drama, [bien], logo='https://img/m21.jpg')
        capitulo('Masha S01 E03', dibujos, [bien], logo='https://img/m13.jpg')
        capitulo('Masha S01 E01', dibujos, [bien])
        imagenes.poner_portada('Arrow', 'https://img/arrow.jpg')
        # Otra lista, para el filtro por origen
        otra = capitulo('Pocoyó S01 E03', dibujos, [])
        Fuente.objects.create(canal=otra, url='https://y/3.mp4', tipo=Fuente.Tipo.DIRECTO, origen='lista_b.m3u')

    def test_dan_lo_mismo_que_las_armadas_capitulo_por_capitulo(self):
        for filtros in ({}, {'texto': 'pocoy'}, {'origen': 'lista_b.m3u'}, {'sin_logo': True},
                        {'categoria': 'ninguna'}, {'estado': 'en_app'}, {'estado': 'fuera'},
                        {'estado': 'incompleta'}, {'idioma': 'sin_dato'}, {'clave': 'POCOYÓ'}):
            with self.subTest(**filtros):
                self.assertEqual(_resumidas(**filtros), _armadas(**filtros))

    def test_lo_que_dice_de_cada_una(self):
        series = {s.nombre: s for s in consultas.resumen_de_series()}
        self.assertTrue(series['Pocoyó'].completa)
        self.assertEqual(series['Pocoyó'].cantidad, 4)
        self.assertIn('Falta el capítulo 1', series['Arrow'].por_que_no_se_ve)
        self.assertEqual(series['Arrow'].logo, 'https://img/arrow.jpg')
        self.assertEqual(series['Lost'].por_que_no_se_ve, 'No se ve ningún capítulo.')
        self.assertFalse(series['Lost'].activo)
        self.assertEqual(series['Rara'].en_la_app, 0)
        masha = next(s for s in consultas.resumen_de_series() if s.clave == 'masha')
        self.assertEqual((masha.logo, masha.categoria, masha.numeros_de_temporada),
                         ('https://img/m13.jpg', 'SERIES | DRAMA', [1, 2]))

    def test_los_chips_dan_lo_mismo_con_las_series_ya_armadas(self):
        armadas = consultas.resumen_de_series()
        for categoria in ('todas', 'ninguna', str(Categoria.objects.get(nombre='Dibujos').pk)):
            with self.subTest(categoria=categoria):
                self.assertEqual(
                    consultas.cuentas_de_organizar(Contenido.SERIE, categoria=categoria, series_armadas=armadas),
                    consultas.cuentas_de_organizar(Contenido.SERIE, categoria=categoria))
        self.assertEqual(consultas.cuentas_de_organizar(Contenido.SERIE),
                         {'todo': 7, 'app': 2, 'fuera': 5, 'caidos': 4, 'quitados': 1, 'senales': 1, 'destacados': 1,
                          'sin_logo': 5})

    def test_la_pagina_de_organizar_series_anda(self):
        self.client.force_login(Usuario.objects.create_superuser('admin', None, 'x'))
        for mostrar in ('todo', 'app', 'fuera', 'caidos', 'quitados', 'senales', 'destacados'):
            with self.subTest(mostrar=mostrar):
                respuesta = self.client.get(reverse('canales:organizar'), {'contenido': 'serie', 'mostrar': mostrar})
                self.assertEqual(respuesta.status_code, 200)
        respuesta = self.client.get(reverse('canales:organizar'), {'contenido': 'serie'})
        self.assertContains(respuesta, 'Pocoyó')
        self.assertContains(respuesta, '4 capítulos')
        # Las señales de la serie, una por cada lista de donde salió
        self.assertContains(respuesta, 'lista_a.m3u')
        self.assertContains(respuesta, 'lista_b.m3u')
        respuesta = self.client.get(reverse('canales:organizar'), {'contenido': 'serie', 'sin_logo': '1'})
        self.assertEqual(respuesta.status_code, 200)

    def test_la_pagina_de_una_serie_trae_solo_esa(self):
        Canal.objects.create(nombre='Pocoyó Especial S01 E01', contenido=Contenido.SERIE)
        self.client.force_login(Usuario.objects.create_superuser('admin', None, 'x'))
        respuesta = self.client.get(reverse('canales:serie_detalle'), {'nombre': 'pocoyó'})
        self.assertEqual(respuesta.context['serie'].cantidad, 4)

    def test_series_vecinas_y_nombres(self):
        self.assertEqual(consultas.series_vecinas('Lost'), ('Arrow', 'Masha'))
        self.assertEqual([n for n, _ in consultas.nombres_de_series()],
                         ['Arrow', 'Especial de Navidad', 'Lost', 'Masha', 'Pocoyó', 'Rara', 'Sin señales'])

    def test_el_arbol_de_donde_va(self):
        arbol = {c['nombre']: c['series'] for c in consultas.arbol_de_series()['categorias']}
        # Masha: 2 de sus 3 capítulos están en Dibujos; en la temporada 1 hay 2 y el número más alto es el 3
        self.assertIn({'nombre': 'Masha', 'temporadas': [[1, 2, 3], [2, 1, 1]]}, arbol['Dibujos'])
        self.assertEqual(arbol[''], [{'nombre': 'Rara', 'temporadas': [[1, 1, 1]]}])


class AnotarSeriesTests(TestCase):
    """La serie anotada sigue al nombre, se cambie por donde se cambie."""

    def test_al_guardarlo_ya_queda_anotado(self):
        canal = Canal.objects.create(nombre='Lost S02 E05 El regreso', contenido=Contenido.SERIE)
        canal.refresh_from_db()
        self.assertEqual((canal.serie, canal.temporada, canal.capitulo, canal.serie_leida_de),
                         ('lost', 2, 5, 'Lost S02 E05 El regreso'))
        # Guardando solo el nombre, también
        canal.nombre = 'Arrow S01 E02'
        canal.save(update_fields=['nombre'])
        canal.refresh_from_db()
        self.assertEqual((canal.serie, canal.temporada, canal.capitulo), ('arrow', 1, 2))

    def test_sin_numero(self):
        canal = Canal.objects.create(nombre='Especial de Navidad', contenido=Contenido.SERIE)
        consultas.anotar_series()
        canal.refresh_from_db()
        self.assertEqual((canal.serie, canal.temporada, canal.capitulo), ('especial de navidad', 1, None))

    def test_un_cambio_de_nombre_sin_save(self):
        """Ej: un update() o un bulk_update de una herramienta nueva, que no pasa por el modelo."""
        canal = Canal.objects.create(nombre='Lost S01 E01', contenido=Contenido.SERIE)
        self.assertEqual([s.nombre for s in consultas.resumen_de_series()], ['Lost'])
        Canal.objects.filter(pk=canal.pk).update(nombre='Arrow S01 E01')
        self.assertEqual([s.nombre for s in consultas.resumen_de_series()], ['Arrow'])
        self.assertEqual(list(organizar.capitulos_de(['Arrow'])), [canal])
        self.assertFalse(organizar.capitulos_de(['Lost']).exists())

    def test_renombrar_una_serie_y_seguir_trabajando_con_ella(self):
        for numero in (1, 2):
            Canal.objects.create(nombre=f'Pocoyo S01 E0{numero}', contenido=Contenido.SERIE)
        organizar.renombrar_serie('Pocoyo', 'Pocoyó')
        self.assertEqual([(s.nombre, s.cantidad) for s in consultas.resumen_de_series()], [('Pocoyó', 2)])
        self.assertEqual(organizar.ultimo_capitulo('pocoyó'), 2)

    def test_de_a_tandas(self):
        Canal.objects.bulk_create([Canal(nombre=f'Masha S01 E{i:02d}', contenido=Contenido.SERIE) for i in range(1, 8)])
        consultas.anotar_series(tanda=3)
        self.assertEqual(sorted(Canal.objects.values_list('capitulo', flat=True)), list(range(1, 8)))

    def test_tambien_los_borrados_y_lo_que_no_es_serie(self):
        borrado = Canal.objects.create(nombre='Lost S01 E01', contenido=Contenido.SERIE)
        borrado.eliminar()
        pelicula = Canal.objects.create(nombre='Volver al futuro', contenido=Contenido.PELICULA)
        consultas.anotar_series()
        self.assertEqual(Canal.todos.get(pk=borrado.pk).serie, 'lost')
        self.assertEqual(Canal.objects.get(pk=pelicula.pk).serie, 'volver al futuro')
        # Pasarla a Series no cambia nada: ya está anotada
        Canal.objects.filter(pk=pelicula.pk).update(contenido=Contenido.SERIE)
        self.assertEqual([s.nombre for s in consultas.resumen_de_series()], ['Volver al futuro'])

    def test_la_app_pide_los_capitulos_de_una_serie_renombrada(self):
        from api.v1 import catalogo

        canal = Canal.objects.create(nombre='Lost S01 E01', contenido=Contenido.SERIE)
        Fuente.objects.create(canal=canal, url='https://x/1.mp4', tipo=Fuente.Tipo.DIRECTO)
        tipos = consultas.TIPOS_QUE_REPRODUCE_LA_APP
        self.assertEqual(catalogo.armar_capitulos(tipos, ['lost'])['cantidad'], 1)
        Canal.objects.filter(pk=canal.pk).update(nombre='Arrow S01 E01')
        self.assertEqual(catalogo.armar_capitulos(tipos, ['Lost'])['cantidad'], 0)
        self.assertEqual(catalogo.armar_capitulos(tipos, ['Arrow'])['cantidad'], 1)
        self.assertEqual(catalogo.armar_capitulos(tipos, ids=[canal.pk])['cantidad'], 1)
