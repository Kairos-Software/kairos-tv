"""
Eliminar clientes, revendedores y paquetes aunque tengan créditos en uso o
pagados: con advertencia y confirmación, sin romper las cuentas del negocio y
con vuelta atrás (la papelera).
"""

from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from reventa import consultas, servicios
from reventa.models import Cliente, Compra, Dispositivo, Movimiento, Paquete, Revendedor
from usuarios.models import Usuario

LOGIN = reverse('api_v1:cliente_login')
ESTADO = reverse('api_v1:cliente')


class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = Usuario.objects.create_superuser('admin', None, 'Clave-segura-2026')
        self.juan = servicios.crear_revendedor('juan', 'Clave-segura-2026', first_name='Juan', por=self.admin)
        self.pedro = servicios.crear_revendedor('pedro', 'Clave-segura-2026', first_name='Pedro', por=self.admin)
        Usuario.objects.update(debe_cambiar_password=False)
        servicios.regalar_creditos(self.juan, 10)
        self.ana = servicios.crear_cliente(self.juan, 'Ana Pérez')
        # Pagó 3 meses de 1 pantalla: uno en uso y dos cargados
        servicios.activar(self.ana, dispositivos=1, meses=3, monto_cobrado=Decimal('15000'))
        self.client.force_login(self.admin)

    def entrar(self, codigo=None):
        return APIClient().post(LOGIN, {'codigo': codigo or self.ana.codigo, 'dispositivo': 'Tele de Ana'})

    def eliminar_ana(self, **datos):
        return self.client.post(reverse('reventa:cliente_eliminar', args=[self.ana.pk]), datos)


class EliminarClienteTests(Base):
    def test_avisa_lo_que_esta_en_juego(self):
        self.assertEqual(self.entrar().status_code, 200)
        pagina = self.client.get(reverse('reventa:cliente_eliminar', args=[self.ana.pk])).content.decode()
        self.assertIn('Tiene el servicio activo', pagina)
        self.assertIn('se le corta ya', pagina)
        self.assertIn('1 aparato', pagina)
        self.assertIn('2 créditos', pagina)
        self.assertIn('15.000,00', pagina)
        self.assertTrue(Cliente.objects.filter(pk=self.ana.pk).exists())   # mirar la página no elimina nada

    def test_sin_la_confirmacion_no_se_elimina(self):
        for datos in ({}, {'confirmacion': 'Ana', 'entiendo': 'on'}, {'confirmacion': 'Ana Pérez'},
                      {'entiendo': 'on'}):
            with self.subTest(datos):
                respuesta = self.eliminar_ana(**datos)
                self.assertEqual(respuesta.status_code, 200)
                self.assertTrue(Cliente.objects.filter(pk=self.ana.pk).exists())

    def test_el_nombre_se_acepta_sin_importar_mayusculas_ni_espacios(self):
        self.assertRedirects(self.eliminar_ana(confirmacion='  ana   PÉREZ ', entiendo='on'),
                             reverse('reventa:clientes'))
        self.assertFalse(Cliente.objects.filter(pk=self.ana.pk).exists())

    def test_se_corta_el_acceso_ya(self):
        token = self.entrar().json()['token']
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        self.assertEqual(api.get(ESTADO).status_code, 200)
        self.eliminar_ana(confirmacion='Ana Pérez', entiendo='on')
        self.assertEqual(api.get(ESTADO).status_code, 401)   # el aparato que estaba conectado
        self.assertEqual(self.entrar().status_code, 400)     # y el código ya no vale
        self.assertFalse(Dispositivo.objects.filter(cliente_id=self.ana.pk).exists())

    def test_no_cambian_las_cuentas_del_negocio(self):
        antes = consultas.resumen_revendedor(self.juan)
        self.eliminar_ana(confirmacion='Ana Pérez', entiendo='on')
        despues = consultas.resumen_revendedor(self.juan)
        for dato in ('saldo', 'usados', 'cobrado', 'invertido', 'ganancia'):
            self.assertEqual(antes[dato], despues[dato], dato)
        self.assertEqual(self.juan.saldo, 7)   # lo cargado no vuelve solo al revendedor

    def test_no_se_le_sigue_descontando_ni_se_ve_en_las_listas(self):
        self.eliminar_ana(confirmacion='Ana Pérez', entiendo='on')
        Cliente.todos.filter(pk=self.ana.pk).update(vence=timezone.now() - timedelta(days=1))
        servicios.renovar_los_que_tocan()
        self.assertEqual(Cliente.todos.get(pk=self.ana.pk).saldo, 2)
        self.client.get(reverse('reventa:clientes'))   # (esta muestra el aviso de que se eliminó)
        self.assertNotContains(self.client.get(reverse('reventa:clientes')), 'Ana Pérez')
        self.assertEqual(self.client.get(reverse('reventa:cliente', args=[self.ana.pk])).status_code, 404)

    def test_le_avisa_al_revendedor(self):
        self.eliminar_ana(confirmacion='Ana Pérez', entiendo='on')
        self.assertTrue(self.juan.usuario.notificaciones.filter(titulo__contains='Ana Pérez').exists())

    def test_uno_sin_nada_en_uso_no_pide_lo_de_entender(self):
        nueva = servicios.crear_cliente(self.juan, 'Beto')
        url = reverse('reventa:cliente_eliminar', args=[nueva.pk])
        self.assertNotContains(self.client.get(url), 'name="entiendo"')
        self.client.post(url, {'confirmacion': 'beto'})
        self.assertFalse(Cliente.objects.filter(pk=nueva.pk).exists())

    def test_un_revendedor_no_puede_eliminar_ni_a_los_suyos(self):
        self.client.force_login(self.juan.usuario)
        self.assertEqual(self.client.get(reverse('reventa:cliente_eliminar', args=[self.ana.pk])).status_code, 403)
        self.assertEqual(self.eliminar_ana(confirmacion='Ana Pérez', entiendo='on').status_code, 403)
        self.assertTrue(Cliente.objects.filter(pk=self.ana.pk).exists())
        self.assertNotContains(self.client.get(reverse('reventa:cliente', args=[self.ana.pk])), 'Eliminar este cliente')

    def test_el_administrador_ve_el_boton_en_la_ficha(self):
        self.assertContains(self.client.get(reverse('reventa:cliente', args=[self.ana.pk])),
                            reverse('reventa:cliente_eliminar', args=[self.ana.pk]))


class RestaurarClienteTests(Base):
    def test_vuelve_como_estaba(self):
        codigo, vence = self.ana.codigo, Cliente.objects.get(pk=self.ana.pk).vence
        servicios.eliminar_cliente(self.ana, por=self.admin)
        self.assertContains(self.client.get(reverse('reventa:papelera')), 'Ana Pérez')
        self.client.post(reverse('reventa:papelera_restaurar', args=['cliente', self.ana.pk]))
        ana = Cliente.objects.get(pk=self.ana.pk)
        self.assertEqual((ana.codigo, ana.vence, ana.saldo), (codigo, vence, 2))
        self.assertEqual(self.entrar().status_code, 200)
        self.client.get(reverse('reventa:papelera'))   # (esta muestra el aviso de que volvió)
        self.assertNotContains(self.client.get(reverse('reventa:papelera')), 'Ana Pérez')

    def test_si_su_revendedor_esta_en_la_papelera_avisa(self):
        servicios.eliminar_revendedor(self.juan, 'eliminar', por=self.admin)
        respuesta = self.client.post(reverse('reventa:papelera_restaurar', args=['cliente', self.ana.pk]), follow=True)
        self.assertContains(respuesta, 'restauralo primero')
        self.assertFalse(Cliente.objects.filter(pk=self.ana.pk).exists())

    def test_solo_el_administrador_ve_la_papelera(self):
        self.client.force_login(self.juan.usuario)
        self.assertEqual(self.client.get(reverse('reventa:papelera')).status_code, 403)
        self.assertEqual(self.client.post(reverse('reventa:papelera_restaurar', args=['cliente', 1])).status_code, 403)

    def test_restaurar_no_se_hace_con_un_simple_enlace(self):
        servicios.eliminar_cliente(self.ana, por=self.admin)
        url = reverse('reventa:papelera_restaurar', args=['cliente', self.ana.pk])
        self.assertEqual(self.client.get(url).status_code, 405)


class EliminarRevendedorTests(Base):
    def url(self):
        return reverse('reventa:revendedor_eliminar', args=[self.juan.pk])

    def eliminar_juan(self, **datos):
        return self.client.post(self.url(), {'confirmacion': 'Juan', 'entiendo': 'on', **datos})

    def test_avisa_lo_que_esta_en_juego(self):
        servicios.pedir_compra(self.juan, Paquete.objects.create(nombre='Chico', creditos=5, precio=100))
        pagina = self.client.get(self.url()).content.decode()
        self.assertIn('1 cliente', pagina)
        self.assertIn('7 créditos sin usar', pagina)
        self.assertIn('1 compra pendiente', pagina)
        self.assertIn('¿Qué pasa con sus clientes?', pagina)

    def test_hay_que_elegir_que_pasa_con_sus_clientes(self):
        self.assertEqual(self.eliminar_juan().status_code, 200)
        self.assertEqual(self.eliminar_juan(que_hacer='pasar').status_code, 200)   # a quién
        self.assertEqual(self.eliminar_juan(que_hacer='pasar', destino=self.juan.pk).status_code, 200)   # a él mismo no
        self.assertTrue(Revendedor.objects.filter(pk=self.juan.pk).exists())

    def test_pasarlos_a_otro_siguen_viendo(self):
        self.entrar()
        self.assertRedirects(self.eliminar_juan(que_hacer='pasar', destino=self.pedro.pk),
                             reverse('reventa:revendedores'))
        ana = Cliente.objects.get(pk=self.ana.pk)
        self.assertEqual(ana.revendedor_id, self.pedro.pk)
        self.assertEqual((ana.puede_ver, ana.saldo, ana.dispositivos.count()), (True, 2, 1))
        self.assertFalse(Revendedor.objects.filter(pk=self.juan.pk).exists())

    def test_dejarlos_directos_siguen_viendo(self):
        self.eliminar_juan(que_hacer='directos')
        ana = Cliente.objects.get(pk=self.ana.pk)
        self.assertIsNone(ana.revendedor_id)
        self.assertTrue(ana.puede_ver)

    def test_eliminarlos_tambien_les_corta_el_servicio(self):
        self.entrar()
        self.eliminar_juan(que_hacer='eliminar')
        self.assertFalse(Cliente.objects.filter(pk=self.ana.pk).exists())
        self.assertFalse(Dispositivo.objects.filter(cliente_id=self.ana.pk).exists())
        self.assertEqual(self.entrar().status_code, 400)

    def test_se_le_cierra_el_panel_y_se_cancelan_sus_compras(self):
        compra = servicios.pedir_compra(self.juan, Paquete.objects.create(nombre='Chico', creditos=5, precio=100))
        self.eliminar_juan(que_hacer='directos')
        self.assertFalse(Usuario.objects.get(pk=self.juan.usuario_id).is_active)
        self.assertFalse(self.client.login(username='juan', password='Clave-segura-2026'))
        compra.refresh_from_db()
        self.assertEqual(compra.estado, Compra.Estado.CANCELADA)

    def test_su_pantalla_propia_se_va_con_el(self):
        propia = servicios.pantalla_propia(self.juan)
        self.eliminar_juan(que_hacer='pasar', destino=self.pedro.pk)
        self.assertFalse(Cliente.objects.filter(pk=propia.pk).exists())
        self.assertEqual(Cliente.todos.get(pk=propia.pk).revendedor_id, self.juan.pk)

    def test_no_cambia_lo_que_ya_entro_ni_la_libreta(self):
        paquete = Paquete.objects.create(nombre='Chico', creditos=5, precio=Decimal('100'))
        servicios.registrar_compra_pagada(self.juan, paquete, por=self.admin)
        ingresos = consultas.resumen_general()['ingresos']
        libreta = Movimiento.objects.filter(revendedor_id=self.juan.pk).count()
        self.eliminar_juan(que_hacer='directos')
        self.assertEqual(consultas.resumen_general()['ingresos'], ingresos)
        self.assertEqual(Movimiento.objects.filter(revendedor_id=self.juan.pk).count(), libreta)

    def test_sin_clientes_no_pregunta_por_ellos(self):
        self.assertNotContains(self.client.get(reverse('reventa:revendedor_eliminar', args=[self.pedro.pk])),
                               'name="que_hacer"')
        self.client.post(reverse('reventa:revendedor_eliminar', args=[self.pedro.pk]), {'confirmacion': 'pedro'})
        self.assertFalse(Revendedor.objects.filter(pk=self.pedro.pk).exists())

    def test_no_se_puede_eliminar_a_uno_mismo(self):
        yo = servicios.hacer_revendedor(self.admin)
        respuesta = self.client.post(reverse('reventa:revendedor_eliminar', args=[yo.pk]),
                                     {'confirmacion': str(yo)}, follow=True)
        self.assertContains(respuesta, 'No podés eliminarte a vos mismo')
        self.assertTrue(Revendedor.objects.filter(pk=yo.pk).exists())
        self.assertTrue(Usuario.objects.get(pk=self.admin.pk).is_active)

    def test_un_revendedor_no_puede(self):
        self.client.force_login(self.pedro.usuario)
        self.assertEqual(self.eliminar_juan(que_hacer='eliminar').status_code, 403)
        self.assertTrue(Revendedor.objects.filter(pk=self.juan.pk).exists())

    def test_restaurar_trae_su_saldo_su_panel_y_los_que_se_fueron_con_el(self):
        vieja = servicios.crear_cliente(self.juan, 'Eliminada antes')
        servicios.eliminar_cliente(vieja, por=self.admin)
        self.eliminar_juan(que_hacer='eliminar')
        self.client.post(reverse('reventa:papelera_restaurar', args=['revendedor', self.juan.pk]))
        juan = Revendedor.objects.get(pk=self.juan.pk)
        self.assertEqual(juan.saldo, 7)
        self.assertTrue(juan.usuario.is_active)
        self.assertTrue(self.client.login(username='juan', password='Clave-segura-2026'))
        self.assertTrue(Cliente.objects.filter(pk=self.ana.pk).exists())
        self.assertFalse(Cliente.objects.filter(pk=vieja.pk).exists())   # esa se eliminó antes, por su lado

    def test_desde_usuarios_lleva_a_eliminarlo_como_revendedor(self):
        respuesta = self.client.get(reverse('usuarios:eliminar', args=[self.juan.usuario_id]))
        self.assertRedirects(respuesta, self.url())
        respuesta = self.client.post(reverse('usuarios:eliminar', args=[self.juan.usuario_id]))
        self.assertRedirects(respuesta, self.url())
        self.assertTrue(Usuario.objects.filter(pk=self.juan.usuario_id).exists())

    def test_un_usuario_comun_se_sigue_eliminando_como_siempre(self):
        comun = Usuario.objects.create_user('comun', None, 'Clave-segura-2026')
        self.client.post(reverse('usuarios:eliminar', args=[comun.pk]))
        self.assertFalse(Usuario.objects.filter(pk=comun.pk).exists())

    def test_su_nombre_de_usuario_avisa_que_esta_en_la_papelera(self):
        self.eliminar_juan(que_hacer='directos')
        respuesta = self.client.post(reverse('reventa:revendedor_nuevo'), {
            'username': 'juan', 'first_name': 'Otro', 'password': 'Clave-segura-2026'})
        self.assertContains(respuesta, 'está en la papelera')


class EliminarPaqueteTests(Base):
    def setUp(self):
        super().setUp()
        self.paquete = Paquete.objects.create(nombre='Chico', creditos=5, precio=Decimal('100'))

    def test_deja_de_ofrecerse_y_las_compras_no_cambian(self):
        compra = servicios.registrar_compra_pagada(self.juan, self.paquete, por=self.admin)
        url = reverse('reventa:paquete_eliminar', args=[self.paquete.pk])
        self.client.post(url, {'confirmacion': 'otro'})
        self.assertTrue(Paquete.objects.filter(pk=self.paquete.pk).exists())
        self.client.post(url, {'confirmacion': 'chico'})
        self.assertFalse(Paquete.objects.filter(pk=self.paquete.pk).exists())
        self.client.get(reverse('reventa:paquetes'))   # (esta muestra el aviso de que se eliminó)
        self.assertNotContains(self.client.get(reverse('reventa:paquetes')), 'Chico')
        compra.refresh_from_db()
        self.assertEqual((compra.creditos, compra.precio, compra.paquete.nombre), (5, Decimal('100'), 'Chico'))

    def test_se_restaura(self):
        servicios.eliminar_paquete(self.paquete, por=self.admin)
        self.client.post(reverse('reventa:papelera_restaurar', args=['paquete', self.paquete.pk]))
        self.assertTrue(Paquete.objects.filter(pk=self.paquete.pk).exists())
