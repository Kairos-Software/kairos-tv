"""
Ordenar los capítulos de una serie desde el panel (página de la serie): al
guardar quedan numerados 1, 2, 3... en el orden elegido, cada uno con su título.
"""

from django.test import TestCase
from django.urls import reverse

from canales import organizar
from canales.models import Canal, Fuente
from canales.views import _numero_en_el_titulo
from usuarios.models import Rol, Usuario


class OrdenarCapitulosTests(TestCase):

    def setUp(self):
        rol = Rol.objects.create(nombre='Canales', permisos=['ver_canales', 'importar_canales'])
        self.client.force_login(Usuario.objects.create_user('marcos', None, 'x', rol=rol))
        # Subida desordenada: el "primero" es el capítulo 12
        self.doce = self.capitulo('Masha S01 E01 Capítulo 12')
        self.uno = self.capitulo('Masha S01 E02 Capítulo 1')
        self.dos = self.capitulo('Masha S01 E03 Capítulo 2')
        self.otra_temporada = self.capitulo('Masha S02 E01 La nieve')

    def capitulo(self, nombre):
        canal = Canal.objects.create(nombre=nombre, contenido='serie')
        Fuente.objects.create(canal=canal, url=f'https://series.ejemplo.com/{canal.pk}.mp4',
                              estado=Fuente.Estado.FUNCIONA)
        return canal

    def nombres(self):
        return list(Canal.objects.filter(contenido='serie').order_by('nombre').values_list('nombre', flat=True))

    def ordenar(self, *capitulos, temporada=1, nombre='Masha'):
        return self.client.post(reverse('canales:serie_ordenar'), {
            'nombre': nombre, 'temporada': temporada, 'capitulo': [c.pk for c in capitulos]})

    def test_quedan_numerados_en_el_orden_elegido(self):
        respuesta = self.ordenar(self.uno, self.dos, self.doce)
        self.assertRedirects(respuesta, f"{reverse('canales:serie_detalle')}?nombre=Masha#temporada-1",
                             fetch_redirect_response=False)
        self.assertEqual(self.nombres(), ['Masha S01 E01 Capítulo 1', 'Masha S01 E02 Capítulo 2',
                                          'Masha S01 E03 Capítulo 12', 'Masha S02 E01 La nieve'])
        # Son los mismos capítulos (con sus fuentes y lo visto), solo cambió el número
        self.uno.refresh_from_db()
        self.assertEqual(self.uno.nombre, 'Masha S01 E01 Capítulo 1')

    def test_si_falta_un_capitulo_no_toca_nada(self):
        antes = self.nombres()
        respuesta = self.ordenar(self.uno, self.dos)
        self.assertEqual(self.nombres(), antes)
        mensajes = [str(m) for m in respuesta.wsgi_request._messages]
        self.assertIn('volvé a cargar la página', mensajes[0])

    def test_no_mezcla_capitulos_de_otra_temporada(self):
        with self.assertRaises(organizar.NoSePuede):
            organizar.ordenar_capitulos('Masha', 1, [self.uno.pk, self.dos.pk, self.otra_temporada.pk])

    def test_mismo_orden_no_cambia_nada(self):
        self.assertEqual(organizar.ordenar_capitulos('Masha', 1, [self.doce.pk, self.uno.pk, self.dos.pk]), 0)

    def test_la_pagina_de_la_serie_ofrece_ordenar(self):
        respuesta = self.client.get(reverse('canales:serie_detalle'), {'nombre': 'Masha'})
        self.assertContains(respuesta, 'Guardar orden')
        self.assertContains(respuesta, 'cap-agarre')   # se arrastra ahí mismo, sin abrir nada
        self.assertContains(respuesta, 'data-numero-en-el-titulo="12"')
        self.assertContains(respuesta, 'js/ordenar_capitulos.js')
        # El primero dice "Capítulo 12": avisa que están desordenados y ofrece arreglarlo
        self.assertContains(respuesta, 'Ordenarlos por el número del título')
        # Ya ordenados, no avisa
        self.ordenar(self.uno, self.dos, self.doce)
        respuesta = self.client.get(reverse('canales:serie_detalle'), {'nombre': 'Masha'})
        self.assertNotContains(respuesta, 'Ordenarlos por el número del título')
        # Desde Organizar contenido se llega con un clic
        organizar_pagina = self.client.get(reverse('canales:organizar'), {'contenido': 'serie'})
        self.assertContains(organizar_pagina, f"{reverse('canales:serie_detalle')}?nombre=Masha")

    def test_sin_permiso_de_editar_no_se_ordena(self):
        rol = Rol.objects.create(nombre='Solo ver', permisos=['ver_canales'])
        self.client.force_login(Usuario.objects.create_user('mirar', None, 'x', rol=rol))
        self.assertEqual(self.ordenar(self.uno, self.dos, self.doce).status_code, 403)
        pagina = self.client.get(reverse('canales:serie_detalle'), {'nombre': 'Masha'})
        self.assertContains(pagina, 'Capítulo 12')   # ve los capítulos
        self.assertNotContains(pagina, 'Guardar orden')
        self.assertNotContains(pagina, 'cap-agarre')

    def test_numero_que_dice_el_titulo(self):
        self.assertEqual(_numero_en_el_titulo('Capítulo 12'), 12)
        self.assertEqual(_numero_en_el_titulo('Episodio 3 completo'), 3)
        self.assertEqual(_numero_en_el_titulo('EP07 La playa'), 7)
        self.assertEqual(_numero_en_el_titulo('12 - El regreso'), 12)
        self.assertIsNone(_numero_en_el_titulo('Piloto'))
