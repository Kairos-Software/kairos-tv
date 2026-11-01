"""
Editar canal: agregar varias fuentes a la vez, cada una con su número, y que
la app use ese orden cuando el canal lo pide (Canal.orden_fuentes_a_mano).
"""

from unittest import mock

from django.test import TestCase
from django.urls import reverse

from api.v1 import catalogo
from canales.models import Canal, Fuente
from canales.verificacion import CAIDA, FUNCIONA, Resultado
from usuarios.models import Rol, Usuario


def _probar(url, tipo='hls', *args, **kwargs):
    return Resultado(CAIDA, 'No respondió a tiempo.') if '//cae.tv/' in url else Resultado(FUNCIONA, tipo='hls')


@mock.patch('canales.verificacion.verificar_url', side_effect=_probar)
class AgregarFuentesTests(TestCase):

    def setUp(self):
        self.canal = Canal.objects.create(nombre='Canal 26', idioma='es', pais='AR')
        self.a = Fuente.objects.create(canal=self.canal, url='https://a.tv/26.m3u8', prioridad=1, estado=FUNCIONA)
        self.b = Fuente.objects.create(canal=self.canal, url='https://b.tv/26.m3u8', prioridad=2, estado=FUNCIONA)
        self.url = reverse('canales:canal_editar', args=[self.canal.pk])
        self.client.force_login(Usuario.objects.create_user(
            'admin', None, 'x', rol=Rol.objects.create(nombre='Canales', permisos=['ver_canales', 'importar_canales'])))

    def guardar(self, nuevas=(), numeros=None, a_mano=False):
        """Manda Editar canal como el navegador: las fuentes que ya tiene (con su número) y las filas nuevas."""
        datos = {'nombre': 'Canal 26', 'logo': '', 'numero': '', 'categoria': '', 'nueva_categoria': '',
                 'contenido': 'vivo', 'idioma': 'es', 'pais': 'AR', 'orden': 0, 'activo': 'on', 'motivo_quitado': '',
                 'fuentes-TOTAL_FORMS': 2, 'fuentes-INITIAL_FORMS': 2,
                 'nuevas-TOTAL_FORMS': max(len(nuevas), 1), 'nuevas-INITIAL_FORMS': 0}
        if a_mano:
            datos['orden_fuentes_a_mano'] = 'on'
        for i, fuente in enumerate([self.a, self.b]):
            datos.update({f'fuentes-{i}-id': fuente.pk, f'fuentes-{i}-activa': 'on',
                          f'fuentes-{i}-prioridad': (numeros or {}).get(fuente.pk, fuente.prioridad)})
        for i, (numero, url) in enumerate(nuevas):
            datos.update({f'nuevas-{i}-numero': numero, f'nuevas-{i}-url': url})
        return self.client.post(self.url, datos)

    def orden(self):
        return [url.split('/')[2] for url in self.canal.fuentes.order_by('prioridad').values_list('url', flat=True)]

    def test_varias_a_la_vez_cada_una_en_su_numero(self, _):
        nuevas = [('1', 'https://x.tv/26.m3u8'), ('', 'https://y.tv/26.m3u8'), ('3', 'https://cae.tv/26.m3u8')]
        respuesta = self.guardar(nuevas, a_mano=True)
        self.assertEqual(respuesta.status_code, 302)
        # La 1 y la 3 van en su lugar (las demás se corren); la sin número, al final
        self.assertEqual(self.orden(), ['x.tv', 'a.tv', 'cae.tv', 'b.tv', 'y.tv'])
        self.assertEqual(list(self.canal.fuentes.order_by('prioridad').values_list('prioridad', flat=True)),
                         [1, 2, 3, 4, 5])
        self.assertEqual(Fuente.objects.get(url='https://cae.tv/26.m3u8').estado, 'caida')
        self.canal.refresh_from_db()
        self.assertTrue(self.canal.orden_fuentes_a_mano)
        avisos = [str(m) for m in respuesta.wsgi_request._messages]
        self.assertIn('La fuente 3 se agregó, pero no funciona: No respondió a tiempo.', avisos)

    def test_cambiar_el_numero_de_una_la_pone_en_ese_lugar(self, _):
        self.guardar(numeros={self.b.pk: 1})
        self.assertEqual(self.orden(), ['b.tv', 'a.tv'])   # antes quedaba empatada con la 1 y ganaba la más vieja

    def test_direccion_repetida(self, _):
        respuesta = self.guardar([('', 'https://a.tv/26.m3u8')])
        self.assertContains(respuesta, 'Este canal ya tiene esa dirección.')
        respuesta = self.guardar([('', 'https://x.tv/26.m3u8'), ('', 'https://x.tv/26.m3u8')])
        self.assertContains(respuesta, 'Este canal ya tiene esa dirección.')
        self.assertEqual(self.canal.fuentes.count(), 2)

    def test_numero_sin_direccion(self, _):
        self.assertContains(self.guardar([('2', '')]), 'Falta la dirección.')

    def test_fila_vacia_no_agrega_nada(self, verificar_url):
        self.assertEqual(self.guardar([('', '')]).status_code, 302)
        self.assertEqual(self.orden(), ['a.tv', 'b.tv'])
        verificar_url.assert_not_called()


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
