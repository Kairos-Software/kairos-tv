"""
Las series de Organizar armadas rápido (consultas.series(ligero=True)): con
decenas de miles de capítulos, entrar a Organizar > Series tardaba 30
segundos. Tienen que dar EXACTAMENTE lo mismo que las de siempre.
"""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from canales import consultas, imagenes
from canales.models import Canal, Categoria, Contenido, Fuente
from usuarios.models import Usuario


def _resumen(lista):
    """Todo lo que Organizar muestra de cada serie y de cada capítulo."""
    return [
        (s.nombre, s.categoria, s.categoria_id, s.logo, s.portada, s.cantidad, s.en_la_app, s.fuera, s.completa,
         s.por_que_no_se_ve, s.numeros_de_temporada,
         [(c.canal.pk, c.canal.nombre, c.canal.logo, c.canal.activo, c.canal.destacado, c.canal.categoria_id,
           bool(c.canal.tiene_usable), c.canal.fuentes_fuera, c.temporada, c.numero, c.titulo) for c in s.capitulos])
        for s in lista
    ]


class SeriesRapidasTests(TestCase):

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
        imagenes.poner_portada('Arrow', 'https://img/arrow.jpg')
        # Otra lista, para el filtro por origen
        otra = capitulo('Pocoyó S01 E03', dibujos, [])
        Fuente.objects.create(canal=otra, url='https://y/3.mp4', tipo=Fuente.Tipo.DIRECTO, origen='lista_b.m3u')

    def test_dan_lo_mismo_que_las_de_siempre(self):
        for filtros in ({}, {'texto': 'pocoy'}, {'origen': 'lista_b.m3u'}, {'sin_logo': True},
                        {'categoria': 'ninguna'}, {'estado': 'en_app'}, {'estado': 'fuera'},
                        {'estado': 'incompleta'}, {'idioma': 'sin_dato'}):
            with self.subTest(**filtros):
                self.assertEqual(_resumen(consultas.series(ligero=True, **filtros)), _resumen(consultas.series(**filtros)))

    def test_lo_que_dice_de_cada_una(self):
        series = {s.nombre: s for s in consultas.series(ligero=True)}
        self.assertTrue(series['Pocoyó'].completa)
        self.assertEqual(series['Pocoyó'].cantidad, 4)
        self.assertIn('Falta el capítulo 1', series['Arrow'].por_que_no_se_ve)
        self.assertEqual(series['Arrow'].logo, 'https://img/arrow.jpg')
        self.assertEqual(series['Lost'].por_que_no_se_ve, 'No se ve ningún capítulo.')
        self.assertEqual(series['Rara'].en_la_app, 0)

    def test_los_chips_dan_lo_mismo_con_las_series_ya_armadas(self):
        armadas = consultas.series(ligero=True)
        for categoria in ('todas', 'ninguna', str(Categoria.objects.get(nombre='Dibujos').pk)):
            with self.subTest(categoria=categoria):
                self.assertEqual(
                    consultas.cuentas_de_organizar(Contenido.SERIE, categoria=categoria, series_armadas=armadas),
                    consultas.cuentas_de_organizar(Contenido.SERIE, categoria=categoria))

    def test_la_pagina_de_organizar_series_anda(self):
        self.client.force_login(Usuario.objects.create_superuser('admin', None, 'x'))
        for mostrar in ('todo', 'app', 'fuera', 'caidos', 'quitados', 'senales', 'destacados'):
            with self.subTest(mostrar=mostrar):
                respuesta = self.client.get(reverse('canales:organizar'), {'contenido': 'serie', 'mostrar': mostrar})
                self.assertEqual(respuesta.status_code, 200)
        respuesta = self.client.get(reverse('canales:organizar'), {'contenido': 'serie'})
        self.assertContains(respuesta, 'Pocoyó')
        self.assertContains(respuesta, '4 capítulos')
        respuesta = self.client.get(reverse('canales:organizar'), {'contenido': 'serie', 'sin_logo': '1'})
        self.assertEqual(respuesta.status_code, 200)

    def test_series_vecinas(self):
        self.assertEqual(consultas.series_vecinas('Lost'), ('Arrow', 'Sin señales'))
