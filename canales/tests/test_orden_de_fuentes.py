"""
Un canal se edita en UN solo lugar, el panel de Organizar: ahí se cambia el
número (el orden) de sus fuentes, se agregan varias a la vez con su número,
y si la app usa ese orden (Canal.orden_fuentes_a_mano). La dirección vieja de
«Más opciones» (canal_editar) lleva a ese panel con el canal solo.
"""

from unittest import mock

from django.test import TestCase
from django.urls import reverse

from api.v1 import catalogo
from canales.models import Canal, Categoria, Contenido, Fuente
from canales.verificacion import CAIDA, FUNCIONA, Resultado
from usuarios.models import Rol, Usuario


def _probar(url, tipo='hls', *args, **kwargs):
    return Resultado(CAIDA, 'No respondió a tiempo.') if '//cae.tv/' in url else Resultado(FUNCIONA, tipo=tipo)


def _editor(nombre='admin'):
    return Usuario.objects.create_user(nombre, None, 'x', rol=Rol.objects.create(
        nombre=f'Canales {nombre}', permisos=['ver_canales', 'importar_canales']))


@mock.patch('canales.verificacion.verificar_url', side_effect=_probar)
class PanelDeFuentesTests(TestCase):

    def setUp(self):
        self.canal = Canal.objects.create(nombre='Canal 26', idioma='es', pais='AR', numero='26')
        self.a = Fuente.objects.create(canal=self.canal, url='https://a.tv/26.m3u8', prioridad=1, estado=FUNCIONA)
        self.b = Fuente.objects.create(canal=self.canal, url='https://b.tv/26.m3u8', prioridad=2, estado=FUNCIONA)
        self.client.force_login(_editor())

    def guardar(self, nuevas=(), numeros=None, **datos):
        """«Guardar» del panel, como lo manda organizar_trabajo.js (JSON, con `completo`)."""
        cuerpo = {'tipo': 'canal', 'canal': self.canal.pk, 'nombre': 'Canal 26', 'logo': '', 'numero': '26',
                  'categoria': 'ninguna', 'contenido': 'vivo', 'activo': 'on', 'completo': '1',
                  'idioma': 'es', 'pais': 'AR', 'orden': '0', 'motivo_quitado': '',
                  'nuevas-TOTAL_FORMS': len(nuevas), 'nuevas-INITIAL_FORMS': 0}
        for posicion, fuente in enumerate([self.a, self.b], start=1):
            cuerpo[f'numero-{fuente.pk}'] = (numeros or {}).get(fuente.pk, posicion)
        for i, (numero, url) in enumerate(nuevas):
            cuerpo.update({f'nuevas-{i}-numero': numero, f'nuevas-{i}-url': url})
        cuerpo.update(datos)
        return self.client.post(reverse('canales:organizar_editar'), cuerpo, HTTP_ACCEPT='application/json')

    def orden(self):
        return [url.split('/')[2] for url in self.canal.fuentes.order_by('prioridad').values_list('url', flat=True)]

    def test_varias_a_la_vez_cada_una_en_su_numero(self, _):
        nuevas = [('1', 'https://x.tv/26.m3u8'), ('', 'https://y.tv/26.m3u8'), ('3', 'https://cae.tv/26.m3u8')]
        respuesta = self.guardar(nuevas, orden_fuentes_a_mano='on')
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        # La 1 y la 3 van en su lugar (las demás se corren); la sin número, al final
        self.assertEqual(self.orden(), ['x.tv', 'a.tv', 'cae.tv', 'b.tv', 'y.tv'])
        self.assertEqual(list(self.canal.fuentes.order_by('prioridad').values_list('prioridad', flat=True)),
                         [1, 2, 3, 4, 5])
        self.assertEqual(Fuente.objects.get(url='https://cae.tv/26.m3u8').estado, 'caida')
        self.canal.refresh_from_db()
        self.assertTrue(self.canal.orden_fuentes_a_mano)
        self.assertIn('La fuente 3 se agregó, pero no funciona: No respondió a tiempo.', respuesta.json()['mensaje'])
        # El panel se vuelve a llenar con lo nuevo: las 5, en ese orden
        self.assertEqual([f['url'].split('/')[2] for f in respuesta.json()['datos']['fuentes']],
                         ['x.tv', 'a.tv', 'cae.tv', 'b.tv', 'y.tv'])

    def test_cambiar_el_numero_de_una_la_pone_en_ese_lugar(self, verificar_url):
        respuesta = self.guardar(numeros={self.b.pk: 1})
        self.assertEqual(self.orden(), ['b.tv', 'a.tv'])
        self.assertIn('Se guardó', respuesta.json()['mensaje'])
        verificar_url.assert_not_called()

    def test_direccion_repetida_no_guarda_nada(self, _):
        respuesta = self.guardar([('', 'https://a.tv/26.m3u8')], nombre='Otro nombre')
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('«https://a.tv/26.m3u8»: Este canal ya tiene esa dirección.', respuesta.json()['error'])
        self.canal.refresh_from_db()
        self.assertEqual(self.canal.nombre, 'Canal 26')
        respuesta = self.guardar([('', 'https://x.tv/26.m3u8'), ('', 'https://x.tv/26.m3u8')])
        self.assertIn('Este canal ya tiene esa dirección.', respuesta.json()['error'])
        self.assertEqual(self.canal.fuentes.count(), 2)

    def test_numero_sin_direccion(self, _):
        self.assertIn('Falta la dirección.', self.guardar([('2', '')]).json()['error'])

    def test_reproductor_web(self, _):
        self.guardar([('', 'https://reproductor.example/eventos.html')], **{'nuevas-0-reproductor_web': 'on'})
        self.assertEqual(Fuente.objects.get(url='https://reproductor.example/eventos.html').tipo, 'web')

    def test_datos_que_antes_estaban_en_mas_opciones(self, _):
        self.guardar(idioma='otro', pais='uy', orden='7', activo='', motivo_quitado='Se ve en otro canal')
        self.canal.refresh_from_db()
        self.assertEqual((self.canal.idioma, self.canal.pais, self.canal.orden, self.canal.activo,
                          self.canal.motivo_quitado), ('otro', 'UY', 7, False, 'Se ve en otro canal'))

    def test_sin_completo_no_toca_lo_que_no_vino(self, _):
        # Lo que no es el panel de un canal (pedidos viejos, otras pantallas): idioma, país y número quedan
        self.client.post(reverse('canales:organizar_editar'), {
            'tipo': 'canal', 'canal': self.canal.pk, 'nombre': 'Canal 26 HD', 'logo': '', 'categoria': 'ninguna',
            'activo': 'on'}, HTTP_ACCEPT='application/json')
        self.canal.refresh_from_db()
        self.assertEqual((self.canal.nombre, self.canal.idioma, self.canal.pais, self.canal.numero),
                         ('Canal 26 HD', 'es', 'AR', '26'))


class UnSoloLugarTests(TestCase):
    """«Más opciones» ya no es otra página: lleva al panel de Organizar con ese canal solo."""

    def setUp(self):
        self.client.force_login(_editor())

    def test_la_direccion_vieja_abre_el_panel_con_el_canal_solo(self):
        canal = Canal.objects.create(nombre='Canal 26')
        Fuente.objects.create(canal=canal, url='https://a.tv/26.m3u8', estado=FUNCIONA)
        Canal.objects.create(nombre='Otro canal')
        respuesta = self.client.get(reverse('canales:canal_editar', args=[canal.pk]), {'volver': '/canales/senales/'})
        self.assertRedirects(respuesta, reverse('canales:organizar') + f'?contenido=vivo&canal={canal.pk}&abrir=c{canal.pk}'
                             '&volver=%2Fcanales%2Fsenales%2F', fetch_redirect_response=False)
        pagina = self.client.get(respuesta.url)
        self.assertEqual([item.pk for item in pagina.context['datos'].pagina], [canal.pk])
        self.assertContains(pagina, 'https://a.tv/26.m3u8')
        self.assertContains(pagina, 'href="/canales/senales/"')   # «Volver»
        self.assertNotContains(pagina, 'Otro canal')

    def test_no_vuelve_a_otro_sitio(self):
        canal = Canal.objects.create(nombre='Canal 26')
        respuesta = self.client.get(reverse('canales:canal_editar', args=[canal.pk]), {'volver': 'https://otro.com/'})
        self.assertNotIn('otro.com', respuesta.url)

    def test_un_capitulo_se_abre_como_capitulo_y_se_guarda(self):
        serie = Categoria.objects.create(nombre='Drama', contenido=Contenido.SERIE)
        capitulo = Canal.objects.create(nombre='Arrow S01 E02', contenido=Contenido.SERIE, categoria=serie)
        Fuente.objects.create(canal=capitulo, url='https://a.tv/arrow102.mkv', tipo='directo', estado=FUNCIONA)
        pagina = self.client.get(reverse('canales:canal_editar', args=[capitulo.pk]), follow=True)
        self.assertEqual(pagina.context['tarjetas'], 'capitulo')
        self.assertContains(pagina, f'data-clave="c{capitulo.pk}"')
        respuesta = self.client.post(reverse('canales:organizar_editar'), {
            'tipo': 'canal', 'canal': capitulo.pk, 'nombre': 'Arrow S01 E02 Honor', 'logo': '',
            'categoria': str(serie.pk), 'activo': 'on', 'completo': '1', 'idioma': 'es', 'pais': '', 'orden': '0',
            'nuevas-TOTAL_FORMS': 0, 'nuevas-INITIAL_FORMS': 0}, HTTP_ACCEPT='application/json')
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertIn(f'data-clave="c{capitulo.pk}"', respuesta.json()['tarjeta'])
        capitulo.refresh_from_db()
        self.assertEqual((capitulo.nombre, capitulo.contenido), ('Arrow S01 E02 Honor', 'serie'))

    def test_si_ya_no_esta_avisa(self):
        canal = Canal.objects.create(nombre='Canal 26')
        canal.eliminar()
        pagina = self.client.get(reverse('canales:organizar'), {'canal': canal.pk}, follow=True)
        self.assertContains(pagina, 'Ese canal ya no está')

    def test_sin_permiso(self):
        self.client.force_login(Usuario.objects.create_user('nadie', None, 'x'))
        self.assertEqual(self.client.get(reverse('canales:canal_editar', args=[1])).status_code, 403)


class OrdenEnLaAppTests(TestCase):
    """Lo que recibe la app: la primera de la lista es su "Fuente 1"."""

    def test_con_el_orden_elegido_manda_el_numero_aunque_se_corte(self):
        canal = Canal.objects.create(nombre='HBO')
        # La 1 se corta seguido en los aparatos; la 2 anda perfecto
        cortada = Fuente.objects.create(canal=canal, url='https://a/hbo.m3u8', prioridad=1, estado=FUNCIONA,
                                        segundos_en_aparatos=3600, cortes_en_aparatos=30)
        buena = Fuente.objects.create(canal=canal, url='https://b/hbo.m3u8', prioridad=2, estado=FUNCIONA,
                                      velocidad=3, alto=1080)

        def en_la_app():
            [categoria] = catalogo.armar(None, 'vivo')['categorias']
            return [fuente['id'] for fuente in categoria['canales'][0]['fuentes']]

        self.assertEqual(en_la_app(), [buena.pk, cortada.pk])   # sin elegir: primero la que mejor anda
        canal.orden_fuentes_a_mano = True
        canal.save()
        self.assertEqual(en_la_app(), [cortada.pk, buena.pk])
