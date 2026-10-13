"""Estadísticas: mes a mes, ranking y números de cada cliente."""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from reventa import estadisticas, servicios
from reventa.models import Paquete, Renovacion
from usuarios.models import Usuario


class EstadisticasTests(TestCase):

    def setUp(self):
        self.admin = Usuario.objects.create_superuser('admin', 'admin@test.com', 'x')
        self.juan = servicios.crear_revendedor('juan', 'Clave-segura-2026', precio_pantalla=Decimal('5000'))
        self.pepe = servicios.crear_revendedor('pepe', 'Clave-segura-2026')
        Usuario.objects.update(debe_cambiar_password=False)
        paquete = Paquete.objects.create(nombre='Diez', creditos=10, precio=Decimal('20000'))
        servicios.registrar_compra_pagada(self.juan, paquete)          # ingreso 20000, +10
        servicios.regalar_creditos(self.pepe, 3)
        self.ana = servicios.crear_cliente(self.juan, 'Ana')
        servicios.renovar(self.ana, dispositivos=2, monto_cobrado=Decimal('9000'))     # −2, cobró 9000
        servicios.renovar(servicios.crear_cliente(self.pepe, 'Beto'))  # −1
        directo = servicios.crear_cliente(None, 'Directo')
        servicios.renovar(directo, monto_cobrado=Decimal('7000'))      # ingreso directo 7000

    def test_mes_actual_del_negocio(self):
        filas = estadisticas.por_mes()
        self.assertEqual(len(filas), 12)
        actual = filas[0]
        self.assertEqual(actual['mes'], timezone.localdate().replace(day=1))
        # El directo también usa 1 crédito por mes: lo pone la empresa
        self.assertEqual((actual['clientes_nuevos'], actual['renovaciones'], actual['creditos_usados']), (3, 3, 4))
        self.assertEqual((actual['creditos_comprados'], actual['creditos_regalados']), (10, 3))
        self.assertEqual((actual['invertido'], actual['cobrado_directos'], actual['ingresos']),
                         (Decimal('20000'), Decimal('7000'), Decimal('27000')))
        self.assertEqual(filas[1]['renovaciones'], 0)

    def test_renovacion_de_meses_anteriores_cae_en_su_mes(self):
        Renovacion.objects.filter(cliente=self.ana).update(fecha=timezone.now() - timedelta(days=40))
        filas = estadisticas.por_mes(self.juan)
        self.assertEqual(filas[0]['renovaciones'], 0)
        self.assertEqual(sum(f['renovaciones'] for f in filas[1:3]), 1)

    def test_lo_del_revendedor(self):
        actual = estadisticas.por_mes(self.juan)[0]
        self.assertEqual((actual['renovaciones'], actual['creditos_usados'], actual['cobrado']), (1, 2, Decimal('9000')))
        self.assertEqual(actual['ganancia'], Decimal('-11000'))
        self.assertNotIn('ingresos', actual)
        self.assertEqual(estadisticas.totales(estadisticas.por_mes(self.juan))['renovaciones'], 1)

    def test_ranking(self):
        ranking = estadisticas.ranking_revendedores()
        self.assertEqual([n['revendedor'] for n in ranking], [self.juan, self.pepe])
        self.assertEqual((ranking[0]['usados'], ranking[0]['usados_este_mes']), (2, 2))

    def test_numeros_del_cliente(self):
        numeros = estadisticas.numeros_cliente(self.ana)
        self.assertEqual((numeros['renovaciones'], numeros['creditos'], numeros['cobrado']), (1, 2, Decimal('9000')))
        self.assertIsNotNone(numeros['activo_desde'])

    def test_pantallas(self):
        self.client.force_login(self.admin)
        respuesta = self.client.get(reverse('reventa:estadisticas'))
        self.assertContains(respuesta, 'Ranking de revendedores')
        self.assertTrue(respuesta.context['es_negocio'])
        self.client.force_login(self.juan.usuario)
        respuesta = self.client.get(reverse('reventa:estadisticas'))
        self.assertNotContains(respuesta, 'Ranking de revendedores')
        self.assertEqual(respuesta.context['total']['cobrado'], Decimal('9000'))
        self.client.force_login(Usuario.objects.create_user('nadie', None, 'x'))
        self.assertEqual(self.client.get(reverse('reventa:estadisticas')).status_code, 403)
