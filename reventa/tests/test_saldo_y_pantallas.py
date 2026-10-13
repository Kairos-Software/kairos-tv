"""
El saldo del cliente (meses pagados que se descuentan solos) y sus
pantallas (nombre, titular, código propio, cortar una, agregar o quitar).
"""

from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from notificaciones.models import Notificacion
from reventa import servicios
from reventa.models import Cliente, CreditoCliente, Dispositivo, Movimiento
from reventa.servicios import ReventaError
from usuarios.models import Usuario

LOGIN = reverse('api_v1:cliente_login')
ESTADO = reverse('api_v1:cliente')


class Base(TestCase):

    def setUp(self):
        cache.clear()
        self.admin = Usuario.objects.create_superuser('admin', 'admin@test.com', 'x')
        self.juan = servicios.crear_revendedor('juan', 'Clave-segura-2026', precio_pantalla=Decimal('5000'))
        Usuario.objects.update(debe_cambiar_password=False)
        servicios.regalar_creditos(self.juan, 50)
        self.familia = servicios.crear_cliente(self.juan, 'Familia López')

    def fresco(self, cliente=None):
        return Cliente.objects.get(pk=(cliente or self.familia).pk)

    def entrar(self, codigo, dispositivo='TV'):
        return APIClient().post(LOGIN, {'codigo': codigo, 'dispositivo': dispositivo})


class SaldoTests(Base):

    def test_tres_pantallas_por_diez_meses(self):
        renovacion = servicios.activar(self.familia, dispositivos=3, meses=10, monto_cobrado=Decimal('150000'))
        familia = self.fresco()
        # Al revendedor le salen los 30 de una (ya los cobró); el cliente gastó el primer mes
        self.assertEqual((self.juan.saldo, familia.saldo, familia.meses_pagos()), (20, 27, 9))
        self.assertEqual((renovacion.pantallas, familia.pantallas.count(), familia.pantallas_vigentes()), (3, 3, 3))
        self.assertAlmostEqual(familia.vence, timezone.now() + timedelta(days=30), delta=timedelta(minutes=1))
        self.assertEqual(familia.creditos.get(tipo=CreditoCliente.Tipo.CARGA).monto_cobrado, Decimal('150000'))

    def test_cada_mes_se_descuenta_solo_hasta_que_no_alcanza(self):
        servicios.activar(self.familia, dispositivos=3, meses=2)
        vence = self.fresco().vence
        # Antes de tiempo, nada
        self.assertIsNone(servicios.renovar_si_toca(self.fresco(), ahora=vence - timedelta(days=5)))
        # Por terminar: empieza el siguiente, pegado al anterior
        renovacion = servicios.renovar_si_toca(self.fresco(), ahora=vence - timedelta(days=1))
        self.assertEqual((renovacion.desde, renovacion.pantallas), (vence, 3))
        self.assertEqual(self.fresco().saldo, 0)
        # Ya no le alcanza: no empieza otro
        self.assertIsNone(servicios.renovar_si_toca(self.fresco(), ahora=vence + timedelta(days=29)))

    def test_la_tarea_diaria_renueva_y_avisa_al_que_no_le_alcanza(self):
        servicios.activar(self.familia, dispositivos=1, meses=2)
        otro = servicios.crear_cliente(self.juan, 'Sin saldo')
        servicios.activar(otro, dispositivos=1, meses=1)
        Cliente.objects.update(vence=timezone.now() + timedelta(hours=12))
        self.assertEqual(servicios.renovar_los_que_tocan(), (1, 1))
        self.assertTrue(Notificacion.objects.filter(destinatario=self.juan.usuario, titulo__contains='Sin saldo').exists())
        self.assertEqual(self.fresco().saldo, 0)

    def test_en_la_app_tambien_se_renueva_si_la_tarea_no_llego(self):
        servicios.activar(self.familia, dispositivos=1, meses=2)
        Cliente.objects.update(vence=timezone.now() - timedelta(minutes=5))
        respuesta = self.entrar(self.familia.codigo)
        self.assertEqual(respuesta.status_code, 200, respuesta.json())
        self.assertTrue(self.fresco().vigente)

    def test_cortesia_y_creditos_de_la_empresa(self):
        servicios.activar(self.familia, dispositivos=3, meses=1, cortesia=True, de_la_empresa=True)
        carga = self.familia.creditos.get(tipo=CreditoCliente.Tipo.CARGA)
        self.assertEqual((carga.cortesia, carga.monto_cobrado, carga.revendedor), (True, 0, None))
        self.assertEqual(self.juan.saldo, 50)   # no tocó los créditos del revendedor
        # La cortesía del revendedor sí usa sus créditos (aunque no cobre)
        otro = servicios.crear_cliente(self.juan, 'Amigo de Juan')
        servicios.activar(otro, dispositivos=1, meses=1, cortesia=True)
        self.assertEqual(self.juan.saldo, 49)

    def test_lo_cargado_no_vuelve_al_revendedor(self):
        servicios.activar(self.familia, dispositivos=1, meses=5)
        servicios.pasar_a_revendedor(self.familia, None)
        self.assertEqual((self.juan.saldo, self.fresco().saldo), (45, 4))

    def test_activo_no_se_vuelve_a_activar(self):
        servicios.activar(self.familia, dispositivos=1)
        with self.assertRaisesMessage(ReventaError, 'Cargar meses'):
            servicios.activar(self.familia, dispositivos=2)

    def test_cargar_meses_a_un_vencido_lo_reactiva(self):
        servicios.activar(self.familia, dispositivos=2)
        Cliente.objects.update(vence=timezone.now() - timedelta(days=3))
        servicios.cargar_meses(self.fresco(), meses=1)
        familia = self.fresco()
        self.assertTrue(familia.vigente)
        self.assertAlmostEqual(familia.vence, timezone.now() + timedelta(days=30), delta=timedelta(minutes=1))

    def test_pasar_un_directo_a_un_revendedor(self):
        directo = servicios.crear_cliente(None, 'Primo')
        servicios.activar(directo, dispositivos=1, cortesia=True)
        servicios.pasar_a_revendedor(directo, self.juan)
        servicios.cargar_meses(self.fresco(directo), meses=2)
        self.assertEqual(self.juan.saldo, 48)   # desde ahora, sus cargas salen de Juan


class PantallasTests(Base):

    def setUp(self):
        super().setUp()
        servicios.activar(self.familia, dispositivos=3, meses=2)
        self.tv, self.celu, self.hija = self.familia.pantallas.all()

    def test_tres_aparatos_con_el_mismo_codigo_y_el_cuarto_no(self):
        for aparato in ('TV', 'Celular de Jorge', 'Celular de Mica'):
            self.assertEqual(self.entrar(self.familia.codigo, aparato).status_code, 200)
        cuarto = self.entrar(self.familia.codigo, 'Tablet')
        self.assertEqual((cuarto.status_code, cuarto.json()['codigo']), (409, 'cuenta_en_uso'))

    def test_codigo_propio_de_una_pantalla(self):
        servicios.codigo_de_pantalla(self.hija)
        self.hija.refresh_from_db()
        # Con el código de la pantalla entra a esa y solo a esa
        self.assertEqual(self.entrar(self.hija.codigo, 'Celular de Mica').status_code, 200)
        self.assertEqual(Dispositivo.objects.get(nombre='Celular de Mica').pantalla, self.hija)
        self.assertEqual(self.entrar(self.hija.codigo, 'Otro').status_code, 409)
        # El código del cliente ocupa las otras dos (nunca la de Mica)
        self.assertEqual(self.entrar(self.familia.codigo, 'TV').status_code, 200)
        self.assertEqual(self.entrar(self.familia.codigo, 'Celular de Jorge').status_code, 200)
        self.assertEqual(self.entrar(self.familia.codigo, 'Tablet').status_code, 409)

    def test_cortar_una_pantalla_castigo(self):
        servicios.codigo_de_pantalla(self.hija)
        self.hija.refresh_from_db()
        mica = APIClient()
        mica.credentials(HTTP_AUTHORIZATION=f'Bearer {self.entrar(self.hija.codigo).json()["token"]}')
        self.assertEqual(mica.get(ESTADO).status_code, 200)
        servicios.cortar_pantalla(self.hija)
        self.assertEqual(mica.get(ESTADO).status_code, 401)   # se desconectó
        de_nuevo = self.entrar(self.hija.codigo)
        self.assertEqual((de_nuevo.status_code, de_nuevo.json()['codigo']), (403, 'pantalla_cortada'))
        # Las demás siguen, y se sigue pagando la cortada (sin devolución)
        self.assertEqual(self.fresco().pantallas_vigentes(), 2)
        self.assertEqual(servicios.renovar_si_toca(self.fresco(), ahora=self.fresco().vence).pantallas, 3)
        # Al habilitarla vuelve a entrar
        servicios.cortar_pantalla(self.hija, cortada=False)
        self.assertEqual(self.entrar(self.hija.codigo).status_code, 200)

    def test_sin_pantallas_libres_para_el_codigo_general(self):
        for pantalla in (self.tv, self.celu, self.hija):
            servicios.codigo_de_pantalla(pantalla)
        respuesta = self.entrar(self.familia.codigo)
        self.assertEqual(respuesta.status_code, 409)
        self.assertIn('propio código', respuesta.json()['detalle'])

    def test_codigo_nuevo_del_cliente_no_desconecta_las_de_codigo_propio(self):
        servicios.codigo_de_pantalla(self.hija)
        self.hija.refresh_from_db()
        self.entrar(self.hija.codigo, 'Celular de Mica')
        self.entrar(self.familia.codigo, 'TV')
        servicios.regenerar_codigo(self.fresco())
        self.assertEqual(list(Dispositivo.objects.values_list('nombre', flat=True)), ['Celular de Mica'])

    def test_agregar_una_a_mitad_de_mes(self):
        vence = self.fresco().vence
        pantalla = servicios.agregar_pantalla(self.familia, monto_cobrado=Decimal('2500'))
        familia = self.fresco()
        self.assertEqual((pantalla.numero, familia.pantallas_vigentes(), familia.vence), (4, 4, vence))
        self.assertEqual(self.juan.saldo, 50 - 6 - 1)
        self.assertEqual(self.entrar(familia.codigo, 'Cuarto aparato').status_code, 200)
        # Desde el mes siguiente se paga con las demás: 4 por mes (y el saldo da para 3 → no alcanza)
        self.assertIsNone(servicios.renovar_si_toca(familia, ahora=vence))
        servicios.cargar_meses(familia, meses=1)
        self.assertEqual(servicios.renovar_si_toca(self.fresco(), ahora=vence).pantallas, 4)

    def test_quitar_una_se_renumeran_y_no_se_devuelve(self):
        servicios.editar_pantalla(self.hija, 'Celular de Mica', 'Mica Giménez')
        servicios.quitar_pantalla(self.celu)
        self.assertEqual([(p.numero, p.nombre) for p in self.familia.pantallas.all()],
                         [(1, ''), (2, 'Celular de Mica')])
        self.assertEqual(self.fresco().saldo, 3)   # 6 − 3 del primer mes; no se devolvió nada
        servicios.quitar_pantalla(self.tv)
        with self.assertRaisesMessage(ReventaError, 'al menos una pantalla'):
            servicios.quitar_pantalla(self.familia.pantallas.get())


class EnElPanelTests(Base):

    def test_el_superusuario_regala_tres_pantallas_a_su_familia(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('reventa:cliente_nuevo'), {'revendedor': '', 'nombre': 'Mi familia'})
        familia = Cliente.objects.get(nombre='Mi familia')
        respuesta = self.client.post(reverse('reventa:cliente_activar', args=[familia.pk]),
                                     {'dispositivos': 3, 'meses': 12, 'cortesia': 'on'}, follow=True)
        self.assertContains(respuesta, 'puede ver en 3 pantalla(s)')
        self.assertContains(respuesta, 'le quedan 11 mes(es) más pagos')
        familia = self.fresco(familia)
        self.assertEqual((familia.pantallas_vigentes(), familia.meses_pagos()), (3, 11))
        self.assertTrue(familia.creditos.get(tipo='carga').cortesia)
        self.assertContains(respuesta, 'Cortesía')
        self.assertContains(respuesta, 'Pasarlo a un revendedor')

    def test_pantallas_desde_la_ficha(self):
        servicios.activar(self.familia, dispositivos=2)
        tv, celu = self.familia.pantallas.all()
        self.client.force_login(self.juan.usuario)
        url = lambda p: reverse('reventa:cliente_pantalla', args=[self.familia.pk, p.pk])   # noqa: E731
        self.client.post(url(tv), {'accion': 'editar', 'nombre': 'TV habitación', 'titular': 'Jorge López'})
        self.client.post(url(celu), {'accion': 'dar_codigo'})
        self.client.post(url(celu), {'accion': 'cortar'})
        tv.refresh_from_db()
        celu.refresh_from_db()
        self.assertEqual((tv.nombre, tv.titular), ('TV habitación', 'Jorge López'))
        self.assertTrue(celu.codigo and celu.cortada)
        ficha = self.client.get(reverse('reventa:cliente', args=[self.familia.pk]))
        self.assertContains(ficha, 'TV habitación')
        self.assertContains(ficha, celu.codigo_legible)
        self.assertContains(ficha, 'Cortada')
        self.assertNotContains(ficha, 'Pasarlo a un revendedor')   # eso es del administrador
        self.assertNotContains(ficha, 'Los pone la empresa')

    def test_el_revendedor_no_toca_pantallas_de_otro(self):
        pepe = servicios.crear_revendedor('pepe', 'Clave-segura-2026')
        Usuario.objects.update(debe_cambiar_password=False)
        servicios.activar(self.familia, dispositivos=1)
        self.client.force_login(pepe.usuario)
        pantalla = self.familia.pantallas.get()
        respuesta = self.client.post(reverse('reventa:cliente_pantalla', args=[self.familia.pk, pantalla.pk]),
                                     {'accion': 'cortar'})
        self.assertEqual(respuesta.status_code, 404)
        self.assertEqual(self.client.post(reverse('reventa:cliente_pasar', args=[self.familia.pk])).status_code, 403)

    def test_el_revendedor_no_puede_hacer_pagar_a_la_empresa(self):
        self.client.force_login(self.juan.usuario)
        self.client.post(reverse('reventa:cliente_activar', args=[self.familia.pk]),
                         {'dispositivos': 1, 'meses': 1, 'de_la_empresa': 'on'})
        self.assertEqual(self.juan.saldo, 49)

    def test_el_administrador_carga_meses_de_la_empresa_a_un_cliente_de_revendedor(self):
        servicios.activar(self.familia, dispositivos=2)
        self.client.force_login(self.admin)
        self.client.post(reverse('reventa:cliente_cargar', args=[self.familia.pk]),
                         {'cargar-meses': 3, 'cargar-cortesia': 'on', 'cargar-de_la_empresa': 'on'})
        self.assertEqual((self.juan.saldo, self.fresco().meses_pagos()), (48, 3))

    def test_pasar_un_directo_desde_la_ficha(self):
        directo = servicios.crear_cliente(None, 'Tía')
        self.client.force_login(self.admin)
        self.client.post(reverse('reventa:cliente_pasar', args=[directo.pk]), {'revendedor': self.juan.pk})
        self.assertEqual(self.fresco(directo).revendedor, self.juan)

    def test_el_alta_de_revendedor_no_pide_precio_y_el_lo_pone_despues(self):
        self.client.force_login(self.admin)
        self.assertNotContains(self.client.get(reverse('reventa:revendedor_nuevo')), 'precio_pantalla')
        self.client.force_login(self.juan.usuario)
        self.client.post(reverse('reventa:mi_precio'), {'precio_pantalla': '4500'})
        self.juan.refresh_from_db()
        self.assertEqual(self.juan.precio_pantalla, Decimal('4500'))

    def test_movimiento_del_revendedor_dice_para_quien(self):
        servicios.activar(self.familia, dispositivos=3, meses=2)
        movimiento = self.juan.movimientos.get(tipo=Movimiento.Tipo.RENOVACION)
        self.assertEqual(movimiento.cantidad, -6)
        self.assertIn('Familia López', movimiento.detalle)
