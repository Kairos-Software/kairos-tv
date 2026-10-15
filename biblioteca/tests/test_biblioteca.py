"""
Favoritos, "Continuar viendo" y últimos canales vistos son de la CUENTA, no
del aparato: lo de un cliente lo ven todos sus aparatos (y no otro cliente
que entre en la misma TV); una pantalla con código propio tiene lo suyo.
"""

from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from api import tokens
from biblioteca.models import Favorito, Progreso
from biblioteca.servicios import MAXIMO_RECIENTES
from canales.models import Canal
from reventa import servicios
from usuarios.models import Usuario

BIBLIOTECA = reverse('api_v1:biblioteca')
LOGIN = reverse('api_v1:cliente_login')


def _ms(momento):
    return int(momento.timestamp() * 1000)


class BibliotecaDeLaCuentaTests(TestCase):

    def setUp(self):
        cache.clear()
        juan = servicios.crear_revendedor('juan', 'Clave-segura-2026', precio_pantalla=Decimal('5000'))
        servicios.regalar_creditos(juan, 20)
        self.ana = servicios.crear_cliente(juan, 'Ana')
        servicios.renovar(self.ana, dispositivos=3)
        self.luis = servicios.crear_cliente(juan, 'Luis')
        servicios.renovar(self.luis, dispositivos=1)
        self.pelicula = Canal.objects.create(nombre='Toy Story', contenido='pelicula')
        self.tn = Canal.objects.create(nombre='TN', contenido='vivo')

    def _entrar(self, codigo, aparato):
        respuesta = APIClient().post(LOGIN, {'codigo': codigo, 'dispositivo': aparato})
        self.assertEqual(respuesta.status_code, 200, respuesta.json())
        app = APIClient()
        app.credentials(HTTP_AUTHORIZATION=f'Bearer {respuesta.json()["token"]}')
        return app

    def test_lo_de_un_cliente_lo_ven_todos_sus_aparatos(self):
        tv = self._entrar(self.ana.codigo, 'TV del living')
        celular = self._entrar(self.ana.codigo, 'Celular de Ana')
        tv.post(BIBLIOTECA, {'aparato': 'TV del living', 'agregar': [f'c:{self.pelicula.pk}', 's:Pocoyó'],
                             'progresos': [{'id': self.pelicula.pk, 'p': 2580, 'd': 5400, 't': _ms(timezone.now())}],
                             'vistos': [{'id': self.tn.pk, 't': _ms(timezone.now())}]}, format='json')
        datos = celular.get(BIBLIOTECA).json()
        self.assertEqual(sorted(datos['favoritos']), sorted([f'c:{self.pelicula.pk}', 's:Pocoyó']))
        self.assertEqual(datos['progresos'][0]['id'], self.pelicula.pk)
        self.assertEqual((datos['progresos'][0]['p'], datos['progresos'][0]['aparato']), (2580, 'TV del living'))
        self.assertEqual(datos['recientes'][0]['id'], self.tn.pk)

    def test_otro_cliente_en_la_misma_tv_no_ve_lo_del_anterior(self):
        self._entrar(self.ana.codigo, 'TV del living').post(
            BIBLIOTECA, {'agregar': [f'c:{self.pelicula.pk}']}, format='json')
        luis = self._entrar(self.luis.codigo, 'TV del living')
        self.assertEqual(luis.get(BIBLIOTECA).json(), {'favoritos': [], 'progresos': [], 'recientes': []})

    def test_una_pantalla_con_codigo_propio_tiene_lo_suyo(self):
        pantalla = self.ana.pantallas.order_by('numero').last()
        servicios.codigo_de_pantalla(pantalla, propio=True)
        pantalla.refresh_from_db()
        mica = self._entrar(pantalla.codigo, 'TV de Mica')
        mica.post(BIBLIOTECA, {'agregar': ['s:Bluey']}, format='json')
        ana = self._entrar(self.ana.codigo, 'TV del living')
        self.assertEqual(ana.get(BIBLIOTECA).json()['favoritos'], [])
        self.assertEqual(mica.get(BIBLIOTECA).json()['favoritos'], ['s:Bluey'])
        self.assertEqual(Favorito.objects.get().pantalla, pantalla)

    def test_un_usuario_del_panel_tiene_lo_suyo(self):
        app = APIClient()
        clave, _ = tokens.crear_token(Usuario.objects.create_user('marcos', None, 'x'))
        app.credentials(HTTP_AUTHORIZATION=f'Bearer {clave}')
        app.post(BIBLIOTECA, {'agregar': ['c:1']}, format='json')
        self.assertEqual(app.get(BIBLIOTECA).json()['favoritos'], ['c:1'])
        self.assertEqual(Favorito.objects.get().usuario.username, 'marcos')

    def test_cambios_de_dos_aparatos_a_la_vez_no_se_pisan(self):
        tv = self._entrar(self.ana.codigo, 'TV')
        celular = self._entrar(self.ana.codigo, 'Celular')
        tv.post(BIBLIOTECA, {'agregar': ['c:1']}, format='json')
        celular.post(BIBLIOTECA, {'agregar': ['s:Bluey']}, format='json')   # el celular no sabía del de la TV
        tv.post(BIBLIOTECA, {'quitar': ['c:1']}, format='json')
        self.assertEqual(celular.get(BIBLIOTECA).json()['favoritos'], ['s:Bluey'])

    def test_gana_el_progreso_mas_nuevo(self):
        tv = self._entrar(self.ana.codigo, 'TV')
        ahora = timezone.now()
        tv.post(BIBLIOTECA, {'aparato': 'Celular', 'progresos': [
            {'id': self.pelicula.pk, 'p': 3000, 'd': 5400, 't': _ms(ahora)}]}, format='json')
        # Llega tarde algo de la TV que estuvo sin internet: es de antes, no pisa
        tv.post(BIBLIOTECA, {'aparato': 'TV', 'progresos': [
            {'id': self.pelicula.pk, 'p': 600, 'd': 5400, 't': _ms(ahora - timedelta(hours=1))}]}, format='json')
        progreso = Progreso.objects.get()
        self.assertEqual((progreso.posicion, progreso.aparato), (3000, 'Celular'))
        # Un reloj adelantado no gana para siempre: cuenta como "ahora"
        tv.post(BIBLIOTECA, {'progresos': [
            {'id': self.pelicula.pk, 'p': 100, 'd': 5400, 't': _ms(ahora + timedelta(days=30))}]}, format='json')
        self.assertLessEqual(Progreso.objects.get().cuando, timezone.now())

    def test_olvidar_y_lo_que_no_sirve_se_ignora(self):
        tv = self._entrar(self.ana.codigo, 'TV')
        datos = tv.post(BIBLIOTECA, {'progresos': [
            {'id': self.pelicula.pk, 'p': 10, 'd': 5400, 't': 1},
            {'id': 999999, 'p': 10, 'd': 5400},             # un canal que no existe
            {'id': self.tn.pk, 'p': 10, 'd': 30},            # un vivo (muy corto): no tiene "por dónde iba"
            {'id': 'x', 'p': 'y'},
            'cualquier cosa',
        ]}, format='json').json()
        self.assertEqual([p['id'] for p in datos['progresos']], [self.pelicula.pk])
        self.assertEqual(tv.post(BIBLIOTECA, {'olvidar': [self.pelicula.pk]}, format='json').json()['progresos'], [])
        self.assertEqual(tv.post(BIBLIOTECA, 'no es un objeto', format='json').status_code, 200)

    def test_guarda_los_ultimos_canales_nomas(self):
        tv = self._entrar(self.ana.codigo, 'TV')
        canales = [Canal.objects.create(nombre=f'Canal {i}', contenido='vivo') for i in range(MAXIMO_RECIENTES + 3)]
        ahora = timezone.now()
        datos = tv.post(BIBLIOTECA, {'vistos': [{'id': c.pk, 't': _ms(ahora - timedelta(minutes=i))}
                                                for i, c in enumerate(canales)]}, format='json').json()
        self.assertEqual([v['id'] for v in datos['recientes']], [c.pk for c in canales[:MAXIMO_RECIENTES]])

    def test_sin_sesion_no(self):
        self.assertEqual(APIClient().get(BIBLIOTECA).status_code, 401)
