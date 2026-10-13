"""Las reglas del negocio de reventa: créditos, compras, renovaciones y números."""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from reventa import consultas, servicios
from reventa.models import Cliente, Compra, Movimiento, Paquete
from reventa.servicios import ReventaError
from usuarios.models import Usuario


class Base(TestCase):

    def setUp(self):
        self.admin = Usuario.objects.create_superuser('admin', 'admin@test.com', 'x')
        self.revendedor = servicios.hacer_revendedor(
            Usuario.objects.create_user('juan', None, 'x', first_name='Juan'), precio_pantalla=Decimal('5000'))
        self.paquete = Paquete.objects.create(nombre='Diez', creditos=10, precio=Decimal('20000'))


class CreditosTests(Base):

    def test_saldo_es_la_suma_de_la_libreta(self):
        self.assertEqual(self.revendedor.saldo, 0)
        servicios.regalar_creditos(self.revendedor, 5, por=self.admin)
        servicios.ajustar_creditos(self.revendedor, -2, por=self.admin, detalle='Se cargaron de más')
        self.assertEqual(self.revendedor.saldo, 3)
        self.assertEqual(self.revendedor.movimientos.count(), 2)

    def test_regalo_tiene_que_ser_positivo(self):
        with self.assertRaises(ReventaError):
            servicios.regalar_creditos(self.revendedor, 0)

    def test_ajuste_no_deja_saldo_negativo_y_pide_motivo(self):
        servicios.regalar_creditos(self.revendedor, 1)
        with self.assertRaisesMessage(ReventaError, 'negativo'):
            servicios.ajustar_creditos(self.revendedor, -2, detalle='x')
        with self.assertRaisesMessage(ReventaError, 'motivo'):
            servicios.ajustar_creditos(self.revendedor, 1, detalle='  ')

    def test_hacer_revendedor_dos_veces_devuelve_el_mismo(self):
        self.assertEqual(servicios.hacer_revendedor(self.revendedor.usuario), self.revendedor)


class ComprasTests(Base):

    def test_pedida_no_suma_hasta_confirmar(self):
        compra = servicios.pedir_compra(self.revendedor, self.paquete, por=self.revendedor.usuario)
        self.assertEqual((compra.estado, self.revendedor.saldo), (Compra.Estado.PENDIENTE, 0))
        servicios.confirmar_compra(compra, por=self.admin)
        self.assertEqual(self.revendedor.saldo, 10)

    def test_no_se_confirma_dos_veces(self):
        compra = servicios.registrar_compra_pagada(self.revendedor, self.paquete, por=self.admin)
        with self.assertRaisesMessage(ReventaError, 'pagada'):
            servicios.confirmar_compra(compra)
        self.assertEqual(self.revendedor.saldo, 10)

    def test_cancelada_no_suma_ni_se_puede_confirmar(self):
        compra = servicios.cancelar_compra(servicios.pedir_compra(self.revendedor, self.paquete))
        with self.assertRaises(ReventaError):
            servicios.confirmar_compra(compra)
        self.assertEqual(self.revendedor.saldo, 0)

    def test_la_compra_guarda_el_precio_de_ese_momento(self):
        compra = servicios.pedir_compra(self.revendedor, self.paquete)
        self.paquete.precio = Decimal('99999')
        self.paquete.save()
        compra.refresh_from_db()
        self.assertEqual(compra.precio, Decimal('20000'))

    def test_avisos_en_la_campanita(self):
        from notificaciones.models import Notificacion
        compra = servicios.pedir_compra(self.revendedor, self.paquete, por=self.revendedor.usuario)
        self.assertTrue(Notificacion.objects.filter(destinatario=self.admin, titulo__contains='pidió 10').exists())
        servicios.confirmar_compra(compra, por=self.admin)
        self.assertTrue(Notificacion.objects.filter(destinatario=self.revendedor.usuario,
                                                    titulo__contains='tus 10 créditos').exists())

    def test_paquete_inactivo_no_se_compra(self):
        self.paquete.activo = False
        with self.assertRaises(ReventaError):
            servicios.pedir_compra(self.revendedor, self.paquete)


class RenovarTests(Base):

    def setUp(self):
        super().setUp()
        servicios.regalar_creditos(self.revendedor, 10)
        self.cliente = servicios.crear_cliente(self.revendedor, 'Ana')

    def test_crear_no_gasta_creditos(self):
        self.assertEqual(self.revendedor.saldo, 10)
        self.assertFalse(self.cliente.vigente)
        self.assertEqual(len(self.cliente.codigo), 8)
        self.assertTrue(self.cliente.codigo.isdigit())

    def test_activar_gasta_un_credito_por_dispositivo_por_30_dias(self):
        renovacion = servicios.renovar(self.cliente, dispositivos=2)
        self.cliente.refresh_from_db()
        self.assertEqual(renovacion.creditos, 2)
        self.assertEqual(self.revendedor.saldo, 8)
        self.assertTrue(self.cliente.vigente)
        self.assertAlmostEqual(self.cliente.vence, timezone.now() + timedelta(days=30), delta=timedelta(minutes=1))
        self.assertEqual(self.cliente.pantallas_vigentes(), 2)
        # Sin monto: se propone precio por pantalla × pantallas
        self.assertEqual(self.cliente.creditos.get(tipo='carga').monto_cobrado, Decimal('10000'))

    def test_renovar_vigente_carga_un_mes_que_sigue_pegado_al_actual(self):
        servicios.renovar(self.cliente)
        self.cliente.refresh_from_db()
        vence = self.cliente.vence
        servicios.renovar(self.cliente, monto_cobrado=Decimal('8000'))
        self.cliente.refresh_from_db()
        self.assertEqual((self.cliente.vence, self.cliente.saldo), (vence, 1))   # queda en su saldo
        # Cuando termina el mes, el siguiente empieza pegado
        servicios.renovar_si_toca(self.cliente, ahora=vence - timedelta(hours=1))
        self.cliente.refresh_from_db()
        self.assertEqual((self.cliente.vence, self.cliente.saldo), (vence + timedelta(days=30), 0))

    def test_se_pueden_pagar_varios_meses_por_adelantado(self):
        servicios.renovar(self.cliente)
        servicios.renovar(self.cliente)
        servicios.renovar(self.cliente)
        self.assertEqual((self.revendedor.saldo, self.cliente.meses_pagos()), (7, 2))

    def test_renovar_vencido_arranca_hoy(self):
        servicios.renovar(self.cliente)
        Cliente.objects.filter(pk=self.cliente.pk).update(vence=timezone.now() - timedelta(days=5))
        renovacion = servicios.renovar(self.cliente)
        self.assertAlmostEqual(renovacion.desde, timezone.now(), delta=timedelta(minutes=1))

    def test_sin_saldo_no_renueva_ni_gasta(self):
        with self.assertRaisesMessage(ReventaError, 'hacen falta 12 y quedan 10'):
            servicios.renovar(self.cliente, dispositivos=12)
        self.assertEqual(self.revendedor.saldo, 10)
        self.assertFalse(Movimiento.objects.filter(tipo=Movimiento.Tipo.RENOVACION).exists())

    def test_al_renovar_se_eligen_otros_dispositivos(self):
        servicios.renovar(self.cliente, dispositivos=2)
        self.assertEqual(self.cliente.ultimos_dispositivos(), 2)   # se propone lo mismo
        servicios.renovar(self.cliente, dispositivos=3)            # activo: carga un mes de las que tiene
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.pantallas_vigentes(), 2)     # para más, "Agregar pantalla"

    def test_suspendido_no_esta_vigente(self):
        servicios.renovar(self.cliente, dispositivos=2)
        Cliente.objects.filter(pk=self.cliente.pk).update(suspendido=True)
        self.cliente.refresh_from_db()
        self.assertEqual((self.cliente.vigente, self.cliente.pantallas_vigentes()), (False, 0))

    def test_regenerar_codigo(self):
        anterior = self.cliente.codigo
        servicios.regenerar_codigo(self.cliente)
        self.assertNotEqual(Cliente.objects.get(pk=self.cliente.pk).codigo, anterior)


class NumerosTests(Base):

    def test_resumen_del_revendedor(self):
        servicios.registrar_compra_pagada(self.revendedor, self.paquete)      # +10, pagó 20000
        servicios.regalar_creditos(self.revendedor, 2)                        # +2
        ana = servicios.crear_cliente(self.revendedor, 'Ana')
        servicios.renovar(ana, dispositivos=2, monto_cobrado=Decimal('9000'))                 # −2, cobró 9000
        servicios.crear_cliente(self.revendedor, 'Beto')
        datos = consultas.resumen_revendedor(self.revendedor)
        self.assertEqual((datos['saldo'], datos['comprados'], datos['regalados'], datos['usados']), (10, 10, 2, 2))
        self.assertEqual((datos['cobrado'], datos['invertido'], datos['ganancia']),
                         (Decimal('9000'), Decimal('20000'), Decimal('-11000')))
        self.assertEqual((datos['clientes']['total'], datos['clientes']['vigentes'],
                          datos['clientes']['sin_activar']), (2, 1, 1))

    def test_resumen_general_y_lista(self):
        otro = servicios.hacer_revendedor(Usuario.objects.create_user('pepe', None, 'x'))
        servicios.registrar_compra_pagada(self.revendedor, self.paquete)
        servicios.regalar_creditos(otro, 3)
        servicios.pedir_compra(otro, self.paquete)
        for nombre in ('A', 'B'):
            servicios.renovar(servicios.crear_cliente(self.revendedor, nombre))
        general = consultas.resumen_general()
        self.assertEqual((general['ingresos'], general['creditos_vendidos'], general['creditos_regalados']),
                         (Decimal('20000'), 10, 3))
        self.assertEqual((general['creditos_usados'], general['creditos_sin_usar'], general['compras_pendientes']),
                         (2, 11, 1))
        # La lista no multiplica el saldo por la cantidad de clientes
        juan = consultas.revendedores_con_numeros().get(pk=self.revendedor.pk)
        self.assertEqual((juan.saldo_actual, juan.clientes_vigentes), (8, 2))
