"""
"Volver a mostrar" (Organizar contenido): lo elegido vuelve a la app aunque no
se viera por señales caídas o escondidas por fallar en los aparatos, no solo
si estaba quitado. Lo apagado a mano no se toca.
"""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from canales import servicios
from canales.consultas import fuentes_usables
from canales.models import Canal, Fuente
from usuarios.models import Rol, Usuario

Estado = Fuente.Estado


def _se_ve(canal):
    return fuentes_usables().filter(canal=canal, canal__activo=True).exists()


class VolverAMostrarTests(TestCase):

    def setUp(self):
        self.canal = Canal.objects.create(nombre='Canal Xtream')

    def fuente(self, **datos):
        return Fuente.objects.create(canal=self.canal, url=f'http://x/live/u/c/{Fuente.objects.count()}.ts',
                                     tipo='directo', **datos)

    def mostrar(self):
        return servicios.mostrar_canales(Canal.objects.filter(pk=self.canal.pk))

    def test_escondida_por_fallar_en_los_aparatos(self):
        fuente = self.fuente(estado=Estado.FUNCIONA, oculta_desde=timezone.now(),
                             oculta_hasta=timezone.now() + timedelta(days=1), veces_oculta=2,
                             falla_en_aparatos='Source error')
        self.assertFalse(_se_ve(self.canal))
        self.assertEqual(self.mostrar(), 1)
        fuente.refresh_from_db()
        self.assertTrue(_se_ve(self.canal))
        # Otra oportunidad entera: si vuelve a fallar, se esconde poco (como la primera vez)
        self.assertEqual((fuente.oculta_hasta, fuente.veces_oculta, fuente.falla_en_aparatos), (None, 0, ''))

    def test_caida(self):
        fuente = self.fuente(estado=Estado.CAIDA)
        self.assertFalse(_se_ve(self.canal))
        self.assertEqual(self.mostrar(), 1)
        fuente.refresh_from_db()
        self.assertEqual(fuente.estado, Estado.SIN_VERIFICAR)   # la app la intenta y la verificación la reprueba
        self.assertTrue(_se_ve(self.canal))

    def test_quitado(self):
        self.fuente(estado=Estado.FUNCIONA)
        Canal.objects.filter(pk=self.canal.pk).update(activo=False, motivo_quitado='Quitado a mano.')
        self.assertEqual(self.mostrar(), 1)
        self.canal.refresh_from_db()
        self.assertTrue(self.canal.activo)

    def test_lo_apagado_a_mano_y_lo_que_ya_se_ve_no_cambia(self):
        apagada = self.fuente(estado=Estado.CAIDA, activa=False)
        self.assertEqual(self.mostrar(), 0)
        apagada.refresh_from_db()
        self.assertEqual((apagada.estado, apagada.activa), (Estado.CAIDA, False))
        self.fuente(estado=Estado.FUNCIONA)
        self.assertEqual(self.mostrar(), 0)   # ya se veía

    def test_desde_organizar(self):
        rol = Rol.objects.create(nombre='Canales', permisos=['ver_canales', 'importar_canales'])
        self.client.force_login(Usuario.objects.create_user('marcos', None, 'x', rol=rol))
        self.fuente(estado=Estado.CAIDA)
        respuesta = self.client.post(reverse('canales:catalogo_mostrar'), {'canal': [self.canal.pk]}, follow=True)
        self.assertContains(respuesta, '1 vuelven a la app')
        self.assertTrue(_se_ve(self.canal))
