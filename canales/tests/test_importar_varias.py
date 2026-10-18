"""
Importar varias listas de una (static/js/importar_varias.js): la página sube
cada lista en su propio pedido y el servidor responde JSON, sin redirigir.
"""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from canales.models import Importacion
from usuarios.models import Rol, Usuario

LISTA = '#EXTM3U\n#EXTINF:-1 group-title="Noticias",{nombre}\nhttps://anda/{nombre}.m3u8\n'
COMO_LA_PAGINA = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}


class ImportarVariasTests(TestCase):

    def setUp(self):
        rol = Rol.objects.create(nombre='Canales', permisos=['ver_canales', 'importar_canales'])
        self.client.force_login(Usuario.objects.create_user('marcos', None, 'x', rol=rol))
        self.url = reverse('canales:inicio')

    def subir(self, nombre, contenido, **opciones):
        return self.client.post(self.url, {'archivo': SimpleUploadedFile(nombre, contenido.encode()),
                                           'descartar_adultos': 'on', **opciones}, **COMO_LA_PAGINA)

    def test_cada_lista_responde_con_su_importacion(self):
        for nombre in ('uno', 'dos'):
            respuesta = self.subir(f'{nombre}.m3u', LISTA.format(nombre=nombre))
            self.assertEqual(respuesta.status_code, 200)
            importacion = Importacion.objects.get(archivo=f'{nombre}.m3u')
            self.assertEqual(respuesta.json(), {'ok': True, 'total': 1,
                                                'url': reverse('canales:importacion', args=[importacion.pk])
                                                + '?empezar=1'})
        self.assertEqual(Importacion.objects.count(), 2)

    def test_un_archivo_que_no_sirve_explica_por_que(self):
        respuesta = self.subir('notas.txt', 'hola')
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(respuesta.json(), {'ok': False, 'error': 'Tiene que ser un archivo .m3u, .m3u8 o .zip.'})
        self.assertFalse(Importacion.objects.exists())

    def test_sin_la_pagina_nueva_sigue_igual(self):
        respuesta = self.client.post(self.url, {'archivo': SimpleUploadedFile('uno.m3u', LISTA.format(nombre='uno')
                                                                              .encode())})
        self.assertRedirects(respuesta, reverse('canales:importacion', args=[Importacion.objects.get().pk])
                             + '?empezar=1', fetch_redirect_response=False)

    def test_la_pantalla_trae_el_script(self):
        self.assertContains(self.client.get(self.url), 'js/importar_varias.js')
