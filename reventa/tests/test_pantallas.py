"""Pantallas de reventa: que cada uno vea y haga solo lo que le corresponde."""

from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from reventa import servicios
from reventa.models import Cliente, Compra, Paquete, Revendedor
from usuarios.models import Usuario


class Base(TestCase):

    def setUp(self):
        self.admin = Usuario.objects.create_superuser('admin', 'admin@test.com', 'x')
        self.juan = servicios.crear_revendedor('juan', 'Clave-segura-2026', first_name='Juan',
                                               precio_pantalla=Decimal('5000'))
        self.pepe = servicios.crear_revendedor('pepe', 'Clave-segura-2026', first_name='Pepe')
        # Como si ya hubieran cambiado la contraseña inicial (si no, el panel los manda a cambiarla)
        Usuario.objects.update(debe_cambiar_password=False)
        self.cliente_de_pepe = servicios.crear_cliente(self.pepe, 'Cliente de Pepe')
        self.paquete = Paquete.objects.create(nombre='Diez', creditos=10, precio=Decimal('20000'))

    def entrar(self, usuario):
        self.client.force_login(usuario)


class AccesoTests(Base):

    def test_un_usuario_comun_no_entra(self):
        self.entrar(Usuario.objects.create_user('nadie', None, 'x'))
        self.assertEqual(self.client.get(reverse('reventa:inicio')).status_code, 403)
        self.assertEqual(self.client.get(reverse('reventa:clientes')).status_code, 403)

    def test_el_revendedor_solo_ve_sus_clientes(self):
        servicios.crear_cliente(self.juan, 'Cliente de Juan')
        self.entrar(self.juan.usuario)
        respuesta = self.client.get(reverse('reventa:clientes'))
        self.assertContains(respuesta, 'Cliente de Juan')
        self.assertNotContains(respuesta, 'Cliente de Pepe')
        # Ni cambiando el número en la URL
        pk = self.cliente_de_pepe.pk
        self.assertEqual(self.client.get(reverse('reventa:cliente', args=[pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('reventa:cliente_activar', args=[pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('reventa:cliente_cargar', args=[pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('reventa:cliente_codigo', args=[pk])).status_code, 404)

    def test_el_revendedor_no_entra_a_lo_del_administrador(self):
        self.entrar(self.juan.usuario)
        for nombre, args in [('revendedores', []), ('revendedor', [self.pepe.pk]), ('paquetes', [])]:
            self.assertEqual(self.client.get(reverse(f'reventa:{nombre}', args=args)).status_code, 403, nombre)
        respuesta = self.client.post(reverse('reventa:revendedor_accion', args=[self.juan.pk]),
                                     {'accion': 'regalar', 'cantidad': 100})
        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(self.juan.saldo, 0)

    def test_el_revendedor_no_confirma_su_propia_compra(self):
        compra = servicios.pedir_compra(self.juan, self.paquete)
        self.entrar(self.juan.usuario)
        respuesta = self.client.post(reverse('reventa:compra_resolver', args=[compra.pk]), {'accion': 'confirmar'})
        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(self.juan.saldo, 0)
        # Cancelar la suya sí puede
        self.client.post(reverse('reventa:compra_resolver', args=[compra.pk]), {'accion': 'cancelar'})
        compra.refresh_from_db()
        self.assertEqual(compra.estado, Compra.Estado.CANCELADA)

    def test_no_cancela_la_compra_de_otro(self):
        compra = servicios.pedir_compra(self.pepe, self.paquete)
        self.entrar(self.juan.usuario)
        self.assertEqual(self.client.post(reverse('reventa:compra_resolver', args=[compra.pk]),
                                          {'accion': 'cancelar'}).status_code, 403)

    def test_volver_no_redirige_afuera(self):
        compra = servicios.pedir_compra(self.juan, self.paquete)
        self.entrar(self.admin)
        respuesta = self.client.post(reverse('reventa:compra_resolver', args=[compra.pk]),
                                     {'accion': 'cancelar', 'volver': 'https://malo.com'})
        self.assertEqual(respuesta.url, reverse('reventa:compras'))


class FlujoCompletoTests(Base):

    def test_administrador_crea_revendedor(self):
        self.entrar(self.admin)
        respuesta = self.client.post(reverse('reventa:revendedor_nuevo'), {
            'username': 'ana', 'first_name': 'Ana', 'password': 'Clave-segura-2026'})
        ana = Revendedor.objects.get(usuario__username='ana')
        self.assertRedirects(respuesta, reverse('reventa:revendedor', args=[ana.pk]))
        self.assertTrue(ana.usuario.debe_cambiar_password)
        self.assertEqual(ana.usuario.rol.nombre, 'Revendedor')

    def test_regalar_comprar_activar_y_ver_numeros(self):
        # 1. El administrador le regala 2 créditos y arma un paquete
        self.entrar(self.admin)
        self.client.post(reverse('reventa:revendedor_accion', args=[self.juan.pk]),
                         {'accion': 'regalar', 'cantidad': 2, 'detalle': 'Bienvenida'})
        self.assertEqual(self.juan.saldo, 2)

        # 2. Juan pide un paquete; no suma hasta que se confirme
        self.entrar(self.juan.usuario)
        self.client.post(reverse('reventa:pedir_compra'), {'paquete': self.paquete.pk})
        compra = Compra.objects.get(revendedor=self.juan)
        self.assertEqual(self.juan.saldo, 2)

        # 3. El administrador confirma el pago
        self.entrar(self.admin)
        self.client.post(reverse('reventa:compra_resolver', args=[compra.pk]), {'accion': 'confirmar'})
        self.assertEqual(self.juan.saldo, 12)

        # 4. Juan crea un cliente y lo activa con 2 pantallas por 1 mes cobrando 9000
        self.entrar(self.juan.usuario)
        self.client.post(reverse('reventa:cliente_nuevo'), {'nombre': 'Ana'})
        ana = Cliente.objects.get(nombre='Ana')
        self.assertEqual(ana.revendedor, self.juan)
        respuesta = self.client.post(reverse('reventa:cliente_activar', args=[ana.pk]),
                                     {'dispositivos': 2, 'meses': 1, 'monto_cobrado': '9000'}, follow=True)
        self.assertContains(respuesta, 'puede ver en 2 pantalla(s)')
        self.assertContains(respuesta, 'Este mes va hasta el')
        self.assertEqual(self.juan.saldo, 10)

        # 5. Los números
        inicio = self.client.get(reverse('reventa:inicio'))
        self.assertEqual(inicio.context['mio']['ganancia'], Decimal('-11000'))
        self.assertContains(self.client.get(reverse('reventa:creditos')), 'Compra de paquete')

    def test_renovar_sin_saldo_muestra_el_error(self):
        cliente = servicios.crear_cliente(self.juan, 'Ana')
        self.entrar(self.juan.usuario)
        respuesta = self.client.post(reverse('reventa:cliente_activar', args=[cliente.pk]),
                                     {'dispositivos': 1, 'meses': 1}, follow=True)
        self.assertContains(respuesta, 'No alcanzan los créditos')

    def test_administrador_crea_cliente_eligiendo_revendedor(self):
        self.entrar(self.admin)
        self.client.post(reverse('reventa:cliente_nuevo'),
                         {'revendedor': self.pepe.pk, 'nombre': 'Nuevo'})
        self.assertEqual(Cliente.objects.get(nombre='Nuevo').revendedor, self.pepe)

    def test_paquetes(self):
        self.entrar(self.admin)
        self.client.post(reverse('reventa:paquete_nuevo'), {'nombre': 'Cien', 'creditos': 100, 'precio': '150000',
                                                            'activo': 'on'})
        self.assertTrue(Paquete.objects.filter(nombre='Cien', creditos=100).exists())
        self.assertContains(self.client.get(reverse('reventa:paquetes')), 'Cien')

    def test_todas_las_pantallas_abren(self):
        cliente = servicios.crear_cliente(self.juan, 'Ana')
        servicios.pedir_compra(self.juan, self.paquete)
        self.entrar(self.admin)
        for nombre, args in [('inicio', []), ('revendedores', []), ('revendedor', [self.juan.pk]),
                             ('clientes', []), ('cliente', [cliente.pk]), ('cliente_editar', [cliente.pk]),
                             ('cliente_nuevo', []), ('paquetes', []), ('paquete_nuevo', []), ('compras', []),
                             ('revendedor_nuevo', [])]:
            self.assertEqual(self.client.get(reverse(f'reventa:{nombre}', args=args)).status_code, 200, nombre)
        self.entrar(self.juan.usuario)
        for nombre in ['inicio', 'clientes', 'creditos', 'compras', 'cliente_nuevo']:
            self.assertEqual(self.client.get(reverse(f'reventa:{nombre}')).status_code, 200, nombre)


class MiPantallaTests(Base):
    """El revendedor no ve la app gratis: se activa a sí mismo con sus créditos, como a un cliente."""

    def test_crea_su_pantalla_una_sola_vez_y_se_activa_con_creditos(self):
        self.entrar(self.juan.usuario)
        respuesta = self.client.post(reverse('reventa:mi_pantalla'))
        pantalla = Cliente.objects.get(revendedor=self.juan, propio=True)
        self.assertRedirects(respuesta, reverse('reventa:cliente', args=[pantalla.pk]))
        self.client.post(reverse('reventa:mi_pantalla'))
        self.assertEqual(Cliente.objects.filter(revendedor=self.juan, propio=True).count(), 1)   # no la duplica
        # Se activa como cualquier cliente: gasta sus créditos
        servicios.regalar_creditos(self.juan, 2)
        servicios.renovar(pantalla, dispositivos=1)
        self.assertEqual(self.juan.saldo, 1)

    def test_solo_revendedores_y_por_post(self):
        self.entrar(self.juan.usuario)
        self.assertEqual(self.client.get(reverse('reventa:mi_pantalla')).status_code, 405)
        self.entrar(self.admin)   # el administrador no es revendedor: no tiene "mi pantalla"
        self.assertEqual(self.client.post(reverse('reventa:mi_pantalla')).status_code, 403)

    def test_con_su_usuario_del_panel_no_ve_los_canales(self):
        from rest_framework.test import APIClient

        from api import tokens

        def canales(usuario):
            app = APIClient()
            clave, _ = tokens.crear_token(usuario)
            app.credentials(HTTP_AUTHORIZATION=f'Bearer {clave}')
            return app.get(reverse('api_v1:canales'))

        respuesta = canales(self.juan.usuario)
        self.assertEqual(respuesta.status_code, 403)
        self.assertIn('Mi pantalla', str(respuesta.json()))
        self.assertEqual(canales(self.admin).status_code, 200)   # el administrador sí, para probar
