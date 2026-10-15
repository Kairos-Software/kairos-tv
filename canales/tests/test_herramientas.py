"""Probar un link y agregarlo a mano; limpiar los nombres de los canales viejos."""

from unittest import mock

from django.test import TestCase
from django.urls import reverse

from canales.models import Canal, Fuente
from canales.servicios import limpiar_nombres
from canales.verificacion import CAIDA, FUNCIONA, USER_AGENT_VLC, Resultado
from usuarios.models import Rol, Usuario

DIRECCION = 'http://iptv.ejemplo.com:8080/u/p/57485'


class ProbarLinkTests(TestCase):
    URL = reverse('canales:probar')

    def setUp(self):
        self.client.force_login(Usuario.objects.create_user(
            'admin', None, 'x', rol=Rol.objects.create(nombre='Canales', permisos=['ver_canales', 'importar_canales'])))

    @mock.patch('canales.views.verificar_url', return_value=Resultado(FUNCIONA, tipo='directo', user_agent=USER_AGENT_VLC))
    def test_probar_muestra_el_resultado_y_el_formulario(self, verificar_url):
        respuesta = self.client.post(self.URL, {'paso': 'probar', 'url': DIRECCION})
        self.assertContains(respuesta, 'Funciona')
        self.assertContains(respuesta, 'Video directo')
        self.assertContains(respuesta, 'Anda presentándose como VLC')
        self.assertContains(respuesta, 'Agregar canal')

    @mock.patch('canales.views.verificar_url',
                return_value=Resultado(FUNCIONA, tipo='youtube', titulo='ES: TN Todo Noticias', imagen='https://i.ytimg.com/a.jpg'))
    def test_youtube_sugiere_nombre_y_logo(self, verificar_url):
        respuesta = self.client.post(self.URL, {'paso': 'probar', 'url': 'https://www.youtube.com/@tn/live'})
        self.assertContains(respuesta, 'value="TN Todo Noticias"')
        self.assertContains(respuesta, 'https://i.ytimg.com/a.jpg')

    @mock.patch('canales.views.verificar_url', return_value=Resultado(CAIDA, 'No respondió a tiempo.'))
    def test_si_no_anda_se_puede_agregar_igual(self, verificar_url):
        respuesta = self.client.post(self.URL, {'paso': 'probar', 'url': DIRECCION})
        self.assertContains(respuesta, 'No respondió a tiempo.')
        self.assertContains(respuesta, 'Agregar igual')

    def test_agregar_crea_el_canal_con_la_fuente(self):
        respuesta = self.client.post(self.URL, {
            'paso': 'agregar', 'url': DIRECCION, 'user_agent': '', 'referer': '',
            'estado': 'funciona', 'error': '', 'tipo': 'directo', 'ua_que_anduvo': USER_AGENT_VLC,
            'nombre': 'DAZN 1', 'logo': 'https://logos.ejemplo.com/dazn.png', 'numero': '', 'categoria': '',
            'nueva_categoria': 'Deportes', 'contenido': 'vivo', 'idioma': 'es', 'pais': 'es',
        })
        canal = Canal.objects.get()
        self.assertRedirects(respuesta, reverse('canales:canal_editar', args=[canal.pk]), fetch_redirect_response=False)
        self.assertEqual((canal.nombre, canal.categoria.nombre, canal.pais), ('DAZN 1', 'Deportes', 'ES'))
        fuente = canal.fuentes.get()
        self.assertEqual((fuente.url, fuente.tipo, fuente.estado, fuente.user_agent),
                         (DIRECCION, 'directo', 'funciona', USER_AGENT_VLC))

    @mock.patch('canales.views.verificar_url', return_value=Resultado(FUNCIONA, tipo='hls'))
    def test_avisa_si_ya_esta_cargada(self, verificar_url):
        canal = Canal.objects.create(nombre='Canal 26')
        Fuente.objects.create(canal=canal, url=DIRECCION)
        respuesta = self.client.post(self.URL, {'paso': 'probar', 'url': DIRECCION})
        self.assertContains(respuesta, 'ya está cargada en el canal')
        self.assertNotContains(respuesta, 'Agregar canal')

    def test_sin_permiso(self):
        self.client.force_login(Usuario.objects.create_user(
            'mira', None, 'x', rol=Rol.objects.create(nombre='Mira', permisos=['ver_canales'])))
        self.assertEqual(self.client.get(self.URL).status_code, 403)


class LimpiarNombresTests(TestCase):

    def test_renombra_y_junta_los_repetidos(self):
        dazn = Canal.objects.create(nombre='ES: (FHD) DAZN 1', pais='ES')
        Fuente.objects.create(canal=dazn, url='http://a/1', prioridad=1)
        repetido = Canal.objects.create(nombre='ES: DAZN 1 HD', pais='ES', logo='https://logos.ejemplo.com/d.png')
        Fuente.objects.create(canal=repetido, url='http://a/2', prioridad=1)
        Fuente.objects.create(canal=repetido, url='http://a/1', prioridad=2)   # la misma: no se duplica
        otro_pais = Canal.objects.create(nombre='AR: DAZN 1', pais='AR')

        self.assertEqual(limpiar_nombres(), (2, 1))
        dazn.refresh_from_db()
        self.assertEqual((dazn.nombre, dazn.logo), ('DAZN 1', 'https://logos.ejemplo.com/d.png'))
        self.assertEqual(list(dazn.fuentes.values_list('url', flat=True)), ['http://a/1', 'http://a/2'])
        self.assertFalse(Canal.objects.filter(pk=repetido.pk).exists())   # dado de baja
        otro_pais.refresh_from_db()
        self.assertEqual(otro_pais.nombre, 'DAZN 1')   # el de otro país no se junta

    def test_boton_del_panel(self):
        Canal.objects.create(nombre='ES: (HD) Canal')
        self.client.force_login(Usuario.objects.create_user(
            'admin', None, 'x', rol=Rol.objects.create(nombre='Canales', permisos=['ver_canales', 'importar_canales'])))
        respuesta = self.client.post(reverse('canales:limpiar_nombres'), follow=True)
        # El resultado queda en la página: cuántos y qué cambió
        self.assertContains(respuesta, 'Resultado de limpiar nombres')
        self.assertContains(respuesta, '«ES: (HD) Canal» → «Canal»')
        self.assertEqual(Canal.objects.get().nombre, 'Canal')
