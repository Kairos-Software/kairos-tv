"""La app de los clientes: entrar con el código y sesión única (1 dispositivo por pantalla)."""

from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from canales.servicios import importar_m3u
from reventa import servicios
from reventa.models import HORAS_SIN_SENAL, Cliente, Dispositivo
from usuarios.models import Usuario

LOGIN = reverse('api_v1:cliente_login')
ESTADO = reverse('api_v1:cliente')
SALIR = reverse('api_v1:cliente_logout')
CANALES = reverse('api_v1:canales')


class Base(TestCase):

    def setUp(self):
        cache.clear()   # los intentos fallidos se cuentan en la caché
        self.admin = Usuario.objects.create_superuser('admin', 'admin@test.com', 'x')
        self.juan = servicios.crear_revendedor('juan', 'Clave-segura-2026', precio_pantalla=Decimal('5000'))
        servicios.regalar_creditos(self.juan, 10)
        self.cliente = servicios.crear_cliente(self.juan, 'Ana')
        servicios.renovar(self.cliente, dispositivos=2)
        self.cliente.refresh_from_db()
        importar_m3u('#EXTM3U\n#EXTINF:-1,Canal 26\nhttps://x/c26.m3u8\n')

    def entrar(self, codigo=None, dispositivo='TV del living'):
        return APIClient().post(LOGIN, {'codigo': codigo or self.cliente.codigo_legible, 'dispositivo': dispositivo})

    def con_token(self, respuesta):
        cliente = APIClient()
        cliente.credentials(HTTP_AUTHORIZATION=f'Bearer {respuesta.json()["token"]}')
        return cliente


class EntrarTests(Base):

    def test_entra_con_el_codigo_y_ve_canales(self):
        respuesta = self.entrar()
        self.assertEqual(respuesta.status_code, 200, respuesta.json())
        self.assertTrue(respuesta.json()['token'].startswith('c_'))
        self.assertEqual(respuesta.json()['cliente']['pantallas'], 2)
        app = self.con_token(respuesta)
        self.assertEqual(app.get(CANALES).json()['cantidad'], 1)
        # y las secciones nuevas del panel (Música, Radio...), que la app pide junto con los canales
        self.assertEqual(app.get(reverse('api_v1:canales_secciones')).status_code, 200)
        self.assertEqual(app.get(ESTADO).json()['nombre'], 'Ana')
        self.assertEqual(app.get(ESTADO).json()['codigo'], self.cliente.codigo_legible)
        self.assertEqual(Dispositivo.objects.get().nombre, 'TV del living')

    def test_codigo_con_espacios_o_guiones(self):
        codigo = self.cliente.codigo
        self.assertEqual(self.entrar(f'{codigo[:4]}-{codigo[4:]}').status_code, 200)

    def test_codigo_equivocado(self):
        respuesta = self.entrar('00000000' if self.cliente.codigo != '00000000' else '11111111')
        self.assertEqual((respuesta.status_code, respuesta.json()['codigo']), (400, 'codigo_invalido'))

    def test_bloquea_tras_muchos_codigos_equivocados(self):
        for _ in range(10):
            respuesta = self.entrar('12345678' if self.cliente.codigo != '12345678' else '87654321')
        self.assertEqual((respuesta.status_code, respuesta.json()['codigo']), (429, 'login_bloqueado'))
        # Ni con el código correcto, hasta que pase el bloqueo
        self.assertEqual(self.entrar().status_code, 429)

    def test_vencido_o_suspendido_no_entra(self):
        Cliente.objects.filter(pk=self.cliente.pk).update(vence=timezone.now() - timedelta(days=1))
        datos = self.entrar().json()
        self.assertEqual(datos['codigo'], 'servicio_vencido')
        # La app muestra a quién pedirle la renovación
        self.assertEqual(datos['vendedor']['nombre'], str(self.juan))
        Cliente.objects.filter(pk=self.cliente.pk).update(vence=timezone.now() + timedelta(days=1), suspendido=True)
        self.assertEqual(self.entrar().json()['codigo'], 'suspendido')

    def test_sin_activar_no_entra(self):
        nuevo = servicios.crear_cliente(self.juan, 'Beto')
        self.assertEqual(self.entrar(nuevo.codigo).json()['codigo'], 'servicio_vencido')


class SesionUnicaTests(Base):

    def test_no_mas_dispositivos_que_pantallas(self):
        self.assertEqual(self.entrar(dispositivo='TV').status_code, 200)
        self.assertEqual(self.entrar(dispositivo='Celular').status_code, 200)
        tercero = self.entrar(dispositivo='Otra TV')
        self.assertEqual((tercero.status_code, tercero.json()['codigo']), (409, 'cuenta_en_uso'))
        self.assertEqual(Dispositivo.objects.count(), 2)

    def test_cerrar_sesion_libera_la_pantalla(self):
        primero = self.con_token(self.entrar())
        self.entrar()
        self.assertEqual(self.entrar().status_code, 409)
        self.assertEqual(primero.post(SALIR).status_code, 204)
        self.assertEqual(self.entrar().status_code, 200)

    def test_sin_senal_se_libera_sola(self):
        self.entrar()
        viejo = self.con_token(self.entrar())
        Dispositivo.objects.update(ultima_senal=timezone.now() - timedelta(hours=HORAS_SIN_SENAL, minutes=1))
        self.assertEqual(self.entrar().status_code, 200)
        # El viejo ya no sirve: vuelve a la pantalla del código
        self.assertEqual(viejo.get(ESTADO).status_code, 401)

    def test_la_senal_mantiene_ocupada_la_pantalla(self):
        app = self.con_token(self.entrar())
        Dispositivo.objects.update(ultima_senal=timezone.now() - timedelta(minutes=30))
        app.get(ESTADO)
        self.assertGreater(Dispositivo.objects.get().ultima_senal, timezone.now() - timedelta(minutes=1))

    def test_liberar_desde_el_panel(self):
        app = self.con_token(self.entrar())
        self.entrar()
        self.client.force_login(self.admin)
        dispositivo = Dispositivo.objects.order_by('pk').first()
        self.client.post(reverse('reventa:cliente_liberar', args=[self.cliente.pk]), {'dispositivo': dispositivo.pk})
        self.assertEqual(Dispositivo.objects.count(), 1)
        self.assertEqual(app.get(ESTADO).status_code, 401)
        self.client.post(reverse('reventa:cliente_liberar', args=[self.cliente.pk]))
        self.assertEqual(Dispositivo.objects.count(), 0)

    def test_regenerar_codigo_desconecta_todo(self):
        app = self.con_token(self.entrar())
        servicios.regenerar_codigo(self.cliente)
        self.assertEqual(app.get(ESTADO).status_code, 401)

    def test_lo_pagado_para_el_mes_que_viene_no_suma_hoy(self):
        servicios.renovar(self.cliente, dispositivos=3)   # el próximo mes, 3; este mes siguen siendo 2
        self.entrar()
        self.entrar()
        self.assertEqual(self.entrar().status_code, 409)


class VenceDuranteLaSesionTests(Base):

    def test_si_vence_la_app_se_entera(self):
        app = self.con_token(self.entrar())
        Cliente.objects.filter(pk=self.cliente.pk).update(vence=timezone.now() - timedelta(minutes=1))
        respuesta = app.get(CANALES)
        self.assertEqual((respuesta.status_code, respuesta.json()['codigo']), (403, 'servicio_vencido'))
        self.assertEqual(app.post(SALIR).status_code, 204)   # cerrar sesión se puede igual

    def test_si_lo_suspenden_la_app_se_entera(self):
        app = self.con_token(self.entrar())
        Cliente.objects.filter(pk=self.cliente.pk).update(suspendido=True)
        self.assertEqual(app.get(ESTADO).json()['codigo'], 'suspendido')


class SeguridadTests(Base):

    def test_un_cliente_no_usa_la_api_del_panel(self):
        app = self.con_token(self.entrar())
        for nombre in ('perfil', 'usuarios', 'notificaciones'):
            self.assertEqual(app.get(reverse(f'api_v1:{nombre}')).status_code, 403, nombre)

    def test_un_usuario_del_panel_no_usa_lo_de_clientes(self):
        from api import tokens
        clave, _ = tokens.crear_token(self.admin)
        app = APIClient()
        app.credentials(HTTP_AUTHORIZATION=f'Bearer {clave}')
        self.assertEqual(app.get(CANALES).status_code, 200)   # el superusuario ve canales sin créditos
        self.assertIn(app.get(ESTADO).status_code, (401, 403))

    def test_token_inventado(self):
        app = APIClient()
        app.credentials(HTTP_AUTHORIZATION='Bearer c_inventado')
        self.assertEqual(app.get(CANALES).status_code, 401)


class ClientesDirectosTests(Base):

    def test_directo_no_gasta_creditos_de_ningun_revendedor_y_entra(self):
        directo = servicios.crear_cliente(None, 'Prueba del dueño')
        saldo = self.juan.saldo
        renovacion = servicios.renovar(directo, monto_cobrado=Decimal('0'))
        self.assertEqual(renovacion.creditos, 1)   # su mes usa 1 crédito, que pone la empresa
        self.assertIsNone(directo.creditos.get(tipo='carga').revendedor)
        self.assertEqual(self.juan.saldo, saldo)
        self.assertEqual(self.entrar(directo.codigo).status_code, 200)

    def test_el_administrador_crea_un_directo_desde_el_panel(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('reventa:cliente_nuevo'), {'revendedor': '', 'nombre': 'Directo'})
        directo = Cliente.objects.get(nombre='Directo')
        self.assertIsNone(directo.revendedor)
        self.client.post(reverse('reventa:cliente_activar', args=[directo.pk]), {'dispositivos': 1, 'meses': 1})
        directo.refresh_from_db()
        self.assertTrue(directo.vigente)
        self.assertEqual(self.client.get(reverse('reventa:cliente', args=[directo.pk])).status_code, 200)

    def test_el_revendedor_no_ve_los_directos(self):
        directo = servicios.crear_cliente(None, 'Directo')
        Usuario.objects.update(debe_cambiar_password=False)
        self.client.force_login(self.juan.usuario)
        self.assertEqual(self.client.get(reverse('reventa:cliente', args=[directo.pk])).status_code, 404)
