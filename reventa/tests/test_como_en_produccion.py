"""
Las pantallas de reventa como corren en producción: SIN la transacción que
TestCase pone alrededor de cada prueba. Ahí se ven los errores de bloqueo
(select_for_update fuera de una transacción) que las otras pruebas tapan.
"""

from decimal import Decimal

from django.test import TransactionTestCase
from django.urls import reverse

from reventa import servicios
from reventa.models import Cliente
from usuarios.models import Usuario


class ActivarComoEnProduccionTests(TransactionTestCase):

    def setUp(self):
        self.admin = Usuario.objects.create_superuser('admin', 'admin@test.com', 'x')
        self.juan = servicios.crear_revendedor('juan', 'Clave-segura-2026', precio_pantalla=Decimal('5000'))
        Usuario.objects.update(debe_cambiar_password=False)
        self.client.raise_request_exception = True

    def activar(self, cliente, monto='0'):
        respuesta = self.client.post(reverse('reventa:cliente_activar', args=[cliente.pk]),
                                     {'dispositivos': '1', 'meses': '1', 'monto_cobrado': monto})
        self.assertEqual(respuesta.status_code, 302)
        return Cliente.objects.get(pk=cliente.pk)

    def test_el_superusuario_regala_un_mes_a_un_cliente_directo(self):
        self.client.force_login(self.admin)
        self.assertTrue(self.activar(servicios.crear_cliente(None, 'Regalo')).vigente)

    def test_el_revendedor_activa_con_sus_creditos(self):
        servicios.regalar_creditos(self.juan, 2)
        self.client.force_login(self.juan.usuario)
        self.assertTrue(self.activar(servicios.crear_cliente(self.juan, 'Cliente de Juan'), monto='5000').vigente)
        self.juan.refresh_from_db()
        self.assertEqual(self.juan.saldo, 1)
