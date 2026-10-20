"""
Cambiar el título de un capítulo ahí mismo, en la página de la serie (sin entrar a "Editar"): la serie, la
temporada y el número quedan igual.
"""

from django.test import TestCase
from django.urls import reverse

from canales import clasificar
from canales.models import Canal, Fuente
from usuarios.models import Rol, Usuario


class TituloDeCapituloTests(TestCase):

    def setUp(self):
        rol = Rol.objects.create(nombre='Canales', permisos=['ver_canales', 'importar_canales'])
        self.client.force_login(Usuario.objects.create_user('marcos', None, 'x', rol=rol))
        self.capitulo = Canal.objects.create(nombre='Masha S01 E05 Capítulo 5', contenido='serie')
        Fuente.objects.create(canal=self.capitulo, url='https://x/5.mp4', estado=Fuente.Estado.FUNCIONA)

    def titular(self, titulo, capitulo=None):
        return self.client.post(reverse('canales:capitulo_titulo', args=[(capitulo or self.capitulo).pk]),
                                {'titulo': titulo})

    def test_cambia_solo_el_titulo(self):
        respuesta = self.titular('  La   nieve ')
        self.assertEqual(respuesta.json(), {'titulo': 'La nieve', 'nombre': 'Masha S01 E05 La nieve'})
        self.capitulo.refresh_from_db()
        self.assertEqual(self.capitulo.nombre, 'Masha S01 E05 La nieve')

    def test_sin_titulo_queda_el_numero(self):
        self.titular('')
        self.capitulo.refresh_from_db()
        self.assertEqual(self.capitulo.nombre, 'Masha S01 E05')

    def test_un_titulo_con_numeros_no_lo_cambia_de_capitulo(self):
        # La app lee el primer "S01 E05": lo que diga el título después no lo mueve de lugar
        self.titular('S02 E03 Otro')
        self.capitulo.refresh_from_db()
        self.assertEqual(self.capitulo.nombre, 'Masha S01 E05 S02 E03 Otro')
        self.assertEqual(clasificar.episodio(self.capitulo.nombre)[:3], ('Masha', 1, 5))

    def test_la_pagina_de_la_serie_lo_ofrece(self):
        pagina = self.client.get(reverse('canales:serie_detalle'), {'nombre': 'Masha'}).content.decode()
        self.assertIn(f'data-titulo-url="{reverse("canales:capitulo_titulo", args=[self.capitulo.pk])}"', pagina)

    def test_solo_capitulos_y_con_permiso(self):
        pelicula = Canal.objects.create(nombre='Una película', contenido='pelicula')
        self.assertEqual(self.titular('x', pelicula).status_code, 404)
        rol = Rol.objects.create(nombre='Mirar', permisos=['ver_canales'])
        self.client.force_login(Usuario.objects.create_user('mira', None, 'x', rol=rol))
        self.assertEqual(self.titular('x').status_code, 403)
