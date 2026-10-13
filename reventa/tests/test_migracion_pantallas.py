"""
La migración al modelo de pantallas y saldo (reventa 0005 a 0007) con
datos como los de producción: no se pierde lo cobrado ni los aparatos conectados.
"""

from datetime import timedelta
from decimal import Decimal

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone

ANTES = [('reventa', '0004_pantalla_propia')]
DESPUES = [('reventa', '0007_renovacion_sin_monto')]


class MigracionTests(TransactionTestCase):

    def migrar(self, destino):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(destino)
        return executor.loader.project_state(destino).apps

    def tearDown(self):
        # Deja la base como estaba (con todas las migraciones) para las demás pruebas
        self.migrar(MigrationExecutor(connection).loader.graph.leaf_nodes())

    def test_pasa_dispositivos_y_cobros(self):
        apps = self.migrar(ANTES)
        Usuario = apps.get_model('usuarios', 'Usuario')
        Revendedor = apps.get_model('reventa', 'Revendedor')
        Cliente = apps.get_model('reventa', 'Cliente')
        Renovacion = apps.get_model('reventa', 'Renovacion')
        Movimiento = apps.get_model('reventa', 'Movimiento')
        Dispositivo = apps.get_model('reventa', 'Dispositivo')
        ahora = timezone.now()
        juan = Revendedor.objects.create(usuario=Usuario.objects.create(username='juan'))
        ana = Cliente.objects.create(revendedor=juan, nombre='Ana', codigo='11112222', vence=ahora + timedelta(days=10))
        renovacion = Renovacion.objects.create(cliente=ana, pantallas=2, creditos=2, monto_cobrado=Decimal('9000'),
                                               desde=ahora - timedelta(days=20), hasta=ana.vence)
        Movimiento.objects.create(revendedor=juan, cantidad=-2, tipo='renovacion', renovacion=renovacion)
        for numero in range(3):   # uno de más (no debería pasar, pero que no rompa)
            Dispositivo.objects.create(cliente=ana, clave_hash=f'h{numero}', ultima_senal=ahora)
        Cliente.objects.create(nombre='Sin activar', codigo='33334444')

        apps = self.migrar(DESPUES)
        Cliente = apps.get_model('reventa', 'Cliente')
        CreditoCliente = apps.get_model('reventa', 'CreditoCliente')
        ana = Cliente.objects.get(nombre='Ana')
        self.assertEqual(ana.pantallas.count(), 2)
        self.assertEqual(sorted(ana.dispositivos.values_list('pantalla__numero', flat=True)), [1, 2])
        carga = CreditoCliente.objects.get(cliente=ana, tipo='carga')
        self.assertEqual((carga.cantidad, carga.monto_cobrado, carga.revendedor_id), (2, Decimal('9000'), juan.pk))
        self.assertIsNotNone(carga.movimiento_id)
        self.assertEqual(sum(CreditoCliente.objects.filter(cliente=ana).values_list('cantidad', flat=True)), 0)
        self.assertEqual(Cliente.objects.get(nombre='Sin activar').pantallas.count(), 0)
