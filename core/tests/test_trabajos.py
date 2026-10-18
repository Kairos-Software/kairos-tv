"""
Trabajos pesados en curso: se ven desde cualquier navegador y, mientras
corre uno, los demás esperan su turno.
"""

from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from canales.servicios import crear_importacion
from canales.tests.test_verificacion import LISTA, verificador_falso
from core import trabajos
from core.models import Trabajo
from usuarios.models import Rol, Usuario


class TurnoTests(TestCase):

    def test_el_primero_sigue_y_el_otro_espera(self):
        self.assertIsNone(trabajos.turno('importacion:1', 'Probando la lista «a.m3u»'))
        otro = trabajos.turno('verificacion', 'Verificando todas las fuentes')
        self.assertEqual(otro.clave, 'importacion:1')
        # El mismo trabajo sigue (otra tanda, u otra pestaña con la misma lista)
        self.assertIsNone(trabajos.turno('importacion:1', 'Probando la lista «a.m3u»'))

    def test_al_terminar_le_toca_al_siguiente(self):
        trabajos.turno('importacion:1', 'Probando')
        trabajos.terminar('importacion:1')
        self.assertIsNone(trabajos.turno('verificacion', 'Verificando'))

    def test_si_deja_de_avisar_se_da_por_cortado(self):
        trabajos.turno('importacion:1', 'Probando')   # y cerraron la pestaña
        Trabajo.objects.filter(clave='importacion:1').update(vence=timezone.now() - timedelta(seconds=1))
        self.assertIsNone(trabajos.turno('verificacion', 'Verificando'))
        self.assertEqual([t.clave for t in trabajos.en_curso()], ['verificacion'])

    def test_avance(self):
        trabajos.turno('importacion:1', 'Probando')
        trabajos.avance('importacion:1', 45, '1.230 de 2.700 probados')
        dato = trabajos.como_dato(trabajos.en_curso().get())
        self.assertEqual((dato['porcentaje'], dato['detalle'], dato['quien']),
                         (45, '1.230 de 2.700 probados', 'el servidor'))

    def test_cancelar_no_se_revierte_con_la_respuesta_de_una_tanda_vieja(self):
        trabajos.turno('importacion:1', 'Probando')
        trabajos.cancelar('importacion:1')
        self.assertTrue(trabajos.cancelado('importacion:1'))
        trabajos.avance('importacion:1', 80, 'respuesta tardía')
        self.assertFalse(trabajos.en_curso().exists())


@mock.patch('canales.views.verificar_varias', verificador_falso)
class EnElPanelTests(TestCase):

    def setUp(self):
        self.marcos = Usuario.objects.create_user(
            'marcos', None, 'x', rol=Rol.objects.create(nombre='Canales', permisos=['ver_canales', 'importar_canales']))
        self.client.force_login(self.marcos)
        self.importacion = crear_importacion(LISTA, 'lista.m3u8')

    def test_se_ve_desde_otro_navegador(self):
        trabajos.turno('importacion:9', 'Probando la lista «grande.m3u»', self.marcos, '/canales/importaciones/9/')
        trabajos.avance('importacion:9', 30, '300 de 1.000 probados')
        otro_navegador = self.client_class()
        otro_navegador.force_login(self.marcos)
        pagina = otro_navegador.get(reverse('core:inicio'))
        self.assertContains(pagina, 'trabajos-iniciales')   # el aviso, con sus datos
        self.assertContains(pagina, 'grande.m3u')
        datos = otro_navegador.get(reverse('core:trabajos')).json()['trabajos']
        self.assertEqual([(t['titulo'], t['porcentaje']) for t in datos], [('Probando la lista «grande.m3u»', 30)])

    def test_una_lista_espera_si_hay_otro_trabajo_pesado(self):
        trabajos.anotar('verificacion_programada', 'Verificación automática de las fuentes')
        datos = self.client.post(reverse('canales:importacion_lote', args=[self.importacion.pk])).json()
        self.assertTrue(datos['ocupada'])
        self.assertEqual(datos['esperando'], 'Verificación automática de las fuentes')
        self.assertEqual(datos['pendientes'], 3)   # no probó nada
        trabajos.terminar('verificacion_programada')
        datos = self.client.post(reverse('canales:importacion_lote', args=[self.importacion.pk])).json()
        self.assertTrue(datos['terminada'])
        self.assertFalse(trabajos.en_curso().exists())   # terminó: ya no figura

    def test_mientras_se_prueba_una_lista_figura_en_curso(self):
        lista_larga = LISTA + ''.join(f'#EXTINF:-1,Canal {i}\nhttps://anda/{i}.m3u8\n' for i in range(60))
        larga = crear_importacion(lista_larga, 'larga.m3u8')
        self.client.post(reverse('canales:importacion_lote', args=[larga.pk]))
        trabajo = trabajos.en_curso().get()
        self.assertEqual((trabajo.clave, trabajo.usuario), (f'importacion:{larga.pk}', self.marcos))
        self.assertIn('probados', trabajo.detalle)
        # Verificar todas, desde otra pestaña, espera
        datos = self.client.post(reverse('canales:verificar_lote'), {'desde': 0}).json()
        self.assertTrue(datos['ocupada'])
        self.assertEqual(datos['siguiente'], 0)
