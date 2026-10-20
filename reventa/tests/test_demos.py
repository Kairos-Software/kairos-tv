"""
Las demos: pruebas gratis de 1 hora que el revendedor le da a un cliente.
Cada cliente tiene 3; se dan de a una o varias juntas (seguidas) y, usadas
todas, no hay más. No gastan créditos.
"""

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from reventa import servicios
from reventa.models import Cliente, Demo
from reventa.servicios import ReventaError
from usuarios.models import Usuario

LOGIN = reverse('api_v1:cliente_login')
ESTADO = reverse('api_v1:cliente')


class Base(TestCase):

    def setUp(self):
        cache.clear()
        self.juan = servicios.crear_revendedor('juan', 'Clave-segura-2026', precio_pantalla=Decimal('5000'))
        Usuario.objects.update(debe_cambiar_password=False)
        servicios.regalar_creditos(self.juan, 10)
        self.ana = servicios.crear_cliente(self.juan, 'Ana Pérez')

    def fresca(self):
        return Cliente.objects.get(pk=self.ana.pk)

    def entrar(self):
        return APIClient().post(LOGIN, {'codigo': self.ana.codigo, 'dispositivo': 'Celular de Ana'})

    def mas_tarde(self, **cuanto):
        """Para simular que pasó el tiempo."""
        return mock.patch('django.utils.timezone.now', return_value=timezone.now() + timedelta(**cuanto))


class DarDemoTests(Base):

    def test_una_demo_es_una_hora_gratis(self):
        demo = servicios.dar_demo(self.ana, 1)
        ana = self.fresca()
        self.assertAlmostEqual(demo.hasta, timezone.now() + timedelta(hours=1), delta=timedelta(minutes=1))
        self.assertTrue(ana.en_demo)
        self.assertTrue(ana.puede_ver)
        self.assertFalse(ana.vigente)   # una prueba no es un mes pagado
        self.assertEqual((ana.demos_usadas, ana.demos_disponibles), (1, 2))
        # No gasta créditos, ni del revendedor ni del cliente
        self.assertEqual((self.juan.saldo, ana.saldo), (10, 0))
        # Se le crea una pantalla (un aparato) para poder entrar
        self.assertEqual(ana.pantallas.count(), 1)

    def test_las_tres_juntas_son_tres_horas_y_no_queda_ninguna(self):
        demo = servicios.dar_demo(self.ana, 3)
        self.assertAlmostEqual(demo.hasta - demo.desde, timedelta(hours=3), delta=timedelta(seconds=1))
        self.assertEqual(self.fresca().demos_disponibles, 0)
        with self.assertRaisesMessage(ReventaError, 'ya usó sus 3 demos'):
            servicios.dar_demo(self.fresca(), 1)

    def test_de_a_una_hasta_completar_tres(self):
        servicios.dar_demo(self.ana, 1)
        servicios.dar_demo(self.fresca(), 2)
        self.assertEqual(self.fresca().demos_disponibles, 0)
        with self.assertRaises(ReventaError):
            servicios.dar_demo(self.fresca(), 1)

    def test_no_puede_pedir_mas_de_las_que_le_quedan(self):
        servicios.dar_demo(self.ana, 2)
        with self.assertRaisesMessage(ReventaError, 'le queda 1 demo'):
            servicios.dar_demo(self.fresca(), 2)
        with self.assertRaises(ReventaError):
            servicios.dar_demo(self.fresca(), 0)

    def test_si_esta_en_una_prueba_la_nueva_va_despues(self):
        primera = servicios.dar_demo(self.ana, 1)
        segunda = servicios.dar_demo(self.fresca(), 1)
        self.assertEqual(segunda.desde, primera.hasta)
        self.assertEqual(self.fresca().demo_hasta, primera.hasta + timedelta(hours=1))

    def test_si_ya_termino_la_nueva_empieza_ahora(self):
        servicios.dar_demo(self.ana, 1)
        with self.mas_tarde(hours=5):
            demo = servicios.dar_demo(self.fresca(), 1)
            self.assertAlmostEqual(demo.desde, timezone.now(), delta=timedelta(seconds=5))

    def test_no_a_un_cliente_que_ya_paga(self):
        servicios.activar(self.ana, 1)
        with self.assertRaisesMessage(ReventaError, 'ya tiene el servicio activo'):
            servicios.dar_demo(self.fresca(), 1)
        self.assertFalse(Demo.objects.exists())

    def test_no_a_un_suspendido(self):
        Cliente.objects.filter(pk=self.ana.pk).update(suspendido=True)
        with self.assertRaisesMessage(ReventaError, 'suspendido'):
            servicios.dar_demo(self.fresca(), 1)

    def test_despues_se_puede_activar_normal(self):
        servicios.dar_demo(self.ana, 1)
        servicios.activar(self.fresca(), dispositivos=2)
        ana = self.fresca()
        self.assertTrue(ana.vigente)
        self.assertFalse(ana.en_demo)
        self.assertEqual(ana.pantallas.count(), 2)


class AppConDemoTests(Base):

    def test_con_una_demo_entra_a_la_app(self):
        self.assertEqual(self.entrar().status_code, 403)   # sin activar ni demo, no
        servicios.dar_demo(self.ana, 1)
        respuesta = self.entrar()
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.json()['cliente']['demo'])
        self.assertEqual(respuesta.json()['cliente']['pantallas'], 1)

    def test_cuando_termina_la_prueba_la_app_lo_dice(self):
        servicios.dar_demo(self.ana, 1)
        token = self.entrar().json()['token']
        app = APIClient()
        app.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        self.assertEqual(app.get(ESTADO).status_code, 200)
        with self.mas_tarde(minutes=61):
            respuesta = app.get(ESTADO)
        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(respuesta.json()['codigo'], 'servicio_vencido')
        self.assertIn('prueba gratis terminó', respuesta.json()['detalle'])


class PanelDemoTests(Base):

    def setUp(self):
        super().setUp()
        self.client.force_login(self.juan.usuario)

    def test_la_ficha_ofrece_las_demos_que_le_quedan(self):
        pagina = self.client.get(reverse('reventa:cliente', args=[self.ana.pk])).content.decode()
        self.assertIn('Le quedan <strong>3 de 3</strong>', pagina)
        self.assertIn('3 demos (3 horas)', pagina)

    def test_dar_dos_desde_el_panel(self):
        respuesta = self.client.post(reverse('reventa:cliente_demo', args=[self.ana.pk]), {'cantidad': '2'},
                                     follow=True)
        self.assertContains(respuesta, 'Le queda 1 demo.')
        self.assertContains(respuesta, 'En prueba hasta las')
        self.assertEqual(self.fresca().demos_usadas, 2)
        self.assertNotContains(respuesta, '2 demos (2 horas)')   # ya no se ofrecen más de las que quedan

    def test_usadas_todas_no_se_ofrecen_mas(self):
        servicios.dar_demo(self.ana, 3)
        with self.mas_tarde(hours=4):
            pagina = self.client.get(reverse('reventa:cliente', args=[self.ana.pk])).content.decode()
        self.assertIn('Ya usó sus 3 demos', pagina)
        self.assertNotIn('Dar demo', pagina)

    def test_el_filtro_en_prueba(self):
        servicios.dar_demo(self.ana, 1)
        servicios.crear_cliente(self.juan, 'Otro sin demo')
        pagina = self.client.get(reverse('reventa:clientes'), {'estado': 'en_prueba'}).content.decode()
        self.assertIn('Ana Pérez', pagina)
        self.assertNotIn('Otro sin demo', pagina)

    def test_no_puede_darle_demos_a_clientes_de_otro_revendedor(self):
        pedro = servicios.crear_revendedor('pedro', 'Clave-segura-2026')
        ajeno = servicios.crear_cliente(pedro, 'Cliente de Pedro')
        respuesta = self.client.post(reverse('reventa:cliente_demo', args=[ajeno.pk]), {'cantidad': '1'})
        self.assertEqual(respuesta.status_code, 404)
        self.assertFalse(Demo.objects.exists())
