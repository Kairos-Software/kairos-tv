from unittest import mock

from django.test import TestCase
from django.urls import reverse

from canales import consultas, servicios
from canales.forms import CanalForm, FuentesFormSet
from canales.models import Canal, Fuente
from canales.verificacion import verificar_url
from usuarios.models import Usuario, Rol


class ReproductorWebTests(TestCase):
    url_web = 'https://reproductor.example/eventos.html?r=canal'

    def setUp(self):
        self.canal = Canal.objects.create(nombre='Canal de prueba')
        usuario = Usuario.objects.create_user('admin_web', None, 'x', rol=Rol.objects.create(
            nombre='Editor web', permisos=['ver_canales', 'importar_canales']))
        self.client.force_login(usuario)

    def test_no_se_declara_reproduccion_sin_probar_en_el_dispositivo(self):
        with mock.patch('urllib.request.urlopen', side_effect=AssertionError('No salir a internet')):
            resultado = verificar_url(self.url_web, 'web', a_fondo=True)
        self.assertEqual((resultado.estado, resultado.tipo), ('sin_verificar', 'web'))
        self.assertFalse(resultado.a_fondo)
        self.assertEqual(verificar_url('file:///tmp/video', 'web').estado, 'caida')

    def test_fuente_web_solo_se_entrega_a_apps_compatibles(self):
        fuente = servicios.agregar_fuente(self.canal, self.url_web, verificar_url, tipo=Fuente.Tipo.WEB)
        self.assertEqual((fuente.tipo, fuente.estado), ('web', 'sin_verificar'))
        self.assertIn(fuente, consultas.fuentes_usables(['web']))
        self.assertNotIn(fuente, consultas.fuentes_usables(['hls', 'pagina']))
        self.assertNotIn(fuente, consultas.fuentes_usables(consultas.tipos_pedidos(None)))

    def test_probar_link_conserva_el_modo_web_al_crear(self):
        url = reverse('canales:probar')
        respuesta = self.client.post(url, {'paso': 'probar', 'url': self.url_web, 'reproductor_web': 'on'})
        self.assertContains(respuesta, 'name="reproductor_web" value="on"')
        self.assertEqual(respuesta.context['resultado'].tipo, 'web')
        respuesta = self.client.post(url, {'paso': 'agregar', 'url': self.url_web,
            'reproductor_web': 'on', 'tipo': 'web', 'estado': 'sin_verificar',
            'nombre': 'Canal web', 'contenido': 'vivo', 'idioma': 'es', 'pais': 'AR'})
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Fuente.objects.get(url=self.url_web).tipo, 'web')

    def test_agregar_web_a_un_canal_existente(self):
        form = CanalForm({'nombre': self.canal.nombre, 'contenido': 'vivo', 'idioma': 'es',
            'pais': 'AR', 'orden': 0, 'activo': 'on', 'nueva_fuente': self.url_web,
            'reproductor_web': 'on'}, instance=self.canal)
        fuentes = FuentesFormSet({'fuentes-TOTAL_FORMS': 0, 'fuentes-INITIAL_FORMS': 0},
            queryset=Fuente.objects.none(), prefix='fuentes')
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(fuentes.is_valid(), fuentes.errors)
        _, nueva = servicios.guardar_canal(form, fuentes, verificar_url=verificar_url)
        self.assertEqual((nueva.tipo, nueva.estado), ('web', 'sin_verificar'))
