"""
Contenido → Mantenimiento: revisar solo una sección o lo que vino de una lista
(verificar y limpiar nombres), y ver el resultado: qué se cayó y qué volvió.
"""

from unittest import mock

from django.test import TestCase
from django.urls import reverse

from canales.models import Canal, Fuente
from canales.servicios import limpiar_nombres, verificar_lote_de_fuentes
from canales.verificacion import CAIDA, FUNCIONA, Resultado
from usuarios.models import Rol, Usuario


def verificador(fuentes, cabeceras=None, hasta=None):
    """Anda todo lo de 'anda'; lo demás se cae."""
    return {url: Resultado(FUNCIONA, tipo='hls') if '//anda' in url else Resultado(CAIDA, 'No respondió a tiempo.')
            for url in fuentes}


class RevisarUnaParteTests(TestCase):

    def setUp(self):
        self.client.force_login(Usuario.objects.create_user('marcos', None, 'x', rol=Rol.objects.create(
            nombre='Canales', permisos=['ver_canales', 'importar_canales'])))
        self.disney = self.canal('Disney', 'vivo', 'https://anda/disney.m3u8', 'lista_vivo.m3u', Fuente.Estado.CAIDA)
        self.next = self.canal('Next', 'vivo', 'https://caida/next.m3u8', 'lista_vivo.m3u', Fuente.Estado.FUNCIONA)
        self.capitulo = self.canal('Bluey S01 E01', 'serie', 'https://caida/bluey.mp4', 'series.m3u',
                                   Fuente.Estado.FUNCIONA)

    def canal(self, nombre, contenido, url, origen, estado):
        canal = Canal.objects.create(nombre=nombre, contenido=contenido)
        Fuente.objects.create(canal=canal, url=url, origen=origen, estado=estado)
        return canal

    def estado(self, canal):
        return canal.fuentes.get().estado

    def test_solo_una_seccion(self):
        avance = verificar_lote_de_fuentes(verificador, seccion='serie')
        self.assertEqual((avance['total'], avance['terminado']), (1, True))
        self.assertEqual(self.estado(self.capitulo), CAIDA)
        self.assertEqual(self.estado(self.next), FUNCIONA)   # no se tocó: es de En vivo

    def test_solo_lo_de_una_lista_y_dice_que_se_cayo_y_que_volvio(self):
        avance = verificar_lote_de_fuentes(verificador, origen='lista_vivo.m3u')
        self.assertEqual(avance['total'], 2)
        self.assertEqual([c['canal'] for c in avance['volvieron']], ['Disney'])
        self.assertEqual([(c['canal'], c['error']) for c in avance['se_cayeron']], [('Next', 'No respondió a tiempo.')])
        self.assertEqual(self.estado(self.capitulo), FUNCIONA)   # otra lista: no se tocó

    @mock.patch('canales.views.verificar_varias', side_effect=verificador)
    def test_desde_la_pantalla(self, _):
        datos = self.client.post(reverse('canales:verificar_lote'), {'desde': 0, 'seccion': 'vivo'}).json()
        self.assertEqual(datos['total'], 2)
        self.assertEqual(datos['volvieron'][0]['pk'], self.disney.pk)   # para el link a su página
        # Una sección que no existe = todas
        self.assertEqual(self.client.post(reverse('canales:verificar_lote'),
                                          {'desde': 0, 'seccion': 'inventada'}).json()['total'], 3)

    def test_la_pantalla_ofrece_que_revisar(self):
        respuesta = self.client.get(reverse('canales:inicio'))
        self.assertContains(respuesta, 'Qué revisar')
        self.assertContains(respuesta, '<option value="serie">Solo Series</option>', html=True)
        self.assertContains(respuesta, 'Solo de «series.m3u»')
        self.assertContains(respuesta, 'id="resultado-verificacion"')
        self.assertContains(respuesta, 'js/mantenimiento.js')

    def test_limpiar_nombres_de_una_sola_lista(self):
        Canal.objects.filter(pk=self.next.pk).update(nombre='AR: (HD) Next')
        Canal.objects.filter(pk=self.capitulo.pk).update(nombre='ES: Bluey S01 E01')
        cambios = []
        self.assertEqual(limpiar_nombres(origen='lista_vivo.m3u', cambios=cambios), (1, 0))
        self.assertEqual(cambios, [('renombrado', 'AR: (HD) Next', 'Next')])
        self.capitulo.refresh_from_db()
        self.assertEqual(self.capitulo.nombre, 'ES: Bluey S01 E01')   # otra lista: no se tocó
        # Desde la pantalla: el resultado queda a la vista, con qué se revisó
        respuesta = self.client.post(reverse('canales:limpiar_nombres'), {'seccion': 'serie'}, follow=True)
        self.assertContains(respuesta, 'Se revisaron los canales de Series')
        self.assertContains(respuesta, '«ES: Bluey S01 E01» → «Bluey S01 E01»')


class AvisoDeCodecTests(TestCase):
    """En el panel de detalles: una señal en un códec que no todos leen lo dice."""

    def test_avisa_cuando_no_todos_los_aparatos_lo_leen(self):
        from canales.views import _aviso_de_codec
        self.assertEqual(_aviso_de_codec('h264'), '')
        self.assertEqual(_aviso_de_codec(''), '')
        self.assertIn('H.265 10 bits', _aviso_de_codec('h265_10'))
        self.assertIn('el canal no aparece', _aviso_de_codec('mpeg2'))


class TuCatalogoLlevaAOrganizarTests(TestCase):
    """Los números de "Tu catálogo" abren Organizar ya filtrado: lo que se ve y lo que no se ve."""

    def setUp(self):
        self.client.force_login(Usuario.objects.create_user('marcos', None, 'x', rol=Rol.objects.create(
            nombre='Canales', permisos=['ver_canales'])))
        quitado = Canal.objects.create(nombre='Quitado', contenido='vivo', activo=False)
        Fuente.objects.create(canal=quitado, url='https://anda/q.m3u8', estado=Fuente.Estado.FUNCIONA)

    def test_cuenta_lo_que_no_se_ve_y_lleva_ahi(self):
        from canales.consultas import resumen_de
        vivo = resumen_de('vivo')
        self.assertEqual(vivo['no_se_ven'], vivo['cargados'] - vivo['en_la_app'])
        self.assertGreaterEqual(vivo['no_se_ven'], 1)
        html = self.client.get(reverse('canales:inicio')).content.decode()
        self.assertIn('?contenido=vivo&amp;mostrar=fuera', html)
        self.assertIn('?contenido=vivo&amp;mostrar=app', html)
        # Lo que no tiene nada que mirar no lleva link
        self.assertNotIn('?contenido=pelicula&amp;mostrar=fuera', html)
