"""
El "modo revisión" de la app (canales/recorrido.py): qué fuentes le toca
probar al aparato y qué pasa con lo que encuentra.
"""

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from api import tokens
from canales import recorrido, salud
from canales.models import Canal, Contenido, Fuente, Seccion
from usuarios.models import Rol, Usuario

Estado = Fuente.Estado
AHORA = timezone.now()
LIMPIEZA = f'{salud.QUITADO_POR_LA_LIMPIEZA}: ninguna fuente anduvo en 7 días.'


class Base(TestCase):

    def setUp(self):
        cache.clear()

    def fuente(self, nombre, contenido=Contenido.VIVO, activo=True, motivo='', **datos):
        canal = Canal.objects.create(nombre=nombre, contenido=contenido, activo=activo, motivo_quitado=motivo)
        datos.setdefault('tipo', 'directo')
        return Fuente.objects.create(canal=canal, url=f'http://x/live/u/c/{canal.pk}.ts', **datos)


class PendientesTests(Base):

    def test_el_orden_y_lo_que_no_se_prueba(self):
        pelicula = self.fuente('Película sin datos', Contenido.PELICULA)
        anda = self.fuente('Anda (visto hace 3 días)', anduvo=AHORA - timedelta(days=3))
        sin_datos = self.fuente('Sin datos')
        falla = self.fuente('Falla', fallas_seguidas=2, falla_desde=AHORA - timedelta(days=1), anduvo=AHORA - timedelta(days=2))
        quitado = self.fuente('Quitado por la limpieza', activo=False, motivo=LIMPIEZA, fallas_seguidas=9)
        radio = Seccion.objects.create(clave='radio', nombre='Radio', forma=Seccion.Forma.VIVO)
        en_radio = self.fuente('Radio sin datos', radio.clave)
        # Lo que no se prueba
        self.fuente('Visto hoy por un cliente', anduvo=AHORA - timedelta(hours=1))
        self.fuente('Ya lo probó el modo revisión', recorrida=AHORA - timedelta(hours=2))
        self.fuente('Apagada a mano', activa=False)
        self.fuente('Quitado a mano', activo=False, motivo='No interesa')
        self.fuente('YouTube', tipo='youtube')

        orden = recorrido.pendientes(50, ahora=AHORA)

        self.assertEqual(orden, [quitado, falla, sin_datos, en_radio, anda, pelicula])
        self.assertEqual(recorrido.cuantas_quedan(ahora=AHORA), 6)
        self.assertEqual(len(recorrido.pendientes(2, ahora=AHORA)), 2)


class AnotarTests(Base):

    def test_anduvo_en_una_casa(self):
        # El servidor la ve caída (los Xtream bloquean al VPS), pero desde una casa anda
        fuente = self.fuente('Quitado', activo=False, motivo=LIMPIEZA, estado=Estado.CAIDA, fallas_seguidas=9,
                             falla_desde=AHORA - timedelta(days=9), historial='-' * 9)
        self.assertEqual(recorrido.anotar([{'id': fuente.pk, 'anduvo': True}], AHORA), 1)
        fuente.refresh_from_db()
        self.assertEqual((fuente.historial[-1], fuente.fallas_seguidas, fuente.estado, fuente.recorrida),
                         ('*', 0, Estado.SIN_VERIFICAR, AHORA))
        fuente.canal.refresh_from_db()
        self.assertTrue(fuente.canal.activo)   # vuelve a la app en el momento

    def test_fallo_y_lo_que_no_se_cuenta(self):
        rechaza = self.fuente('Rechaza')
        formato = self.fuente('Formato')
        sin_internet = self.fuente('Sin internet')
        anotados = recorrido.anotar([
            {'id': rechaza.pk, 'anduvo': False, 'motivo': 'rechazo', 'detalle': 'Response code: 403'},
            {'id': formato.pk, 'anduvo': False, 'motivo': 'formato'},
            {'id': sin_internet.pk, 'anduvo': False, 'motivo': 'sin_internet'},
            {'id': 'basura'}, 'cualquier cosa',
        ], AHORA)
        self.assertEqual(anotados, 2)
        rechaza.refresh_from_db()
        formato.refresh_from_db()
        sin_internet.refresh_from_db()
        self.assertEqual((rechaza.historial, rechaza.fallas_seguidas, rechaza.por_que_falla), ('x', 1, 'rechaza'))
        self.assertEqual((formato.historial, formato.fallas_seguidas, formato.por_que_falla), ('f', 0, 'formato'))
        self.assertEqual((sin_internet.historial, sin_internet.recorrida), ('', None))


class ApiTests(Base):

    def cliente_api(self, permisos):
        rol = Rol.objects.create(nombre=f'Rol {len(permisos)}', permisos=permisos)
        clave, _ = tokens.crear_token(Usuario.objects.create_user(f'u{len(permisos)}', None, 'x', rol=rol))
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f'Bearer {clave}')
        return api

    def test_pedir_y_contar(self):
        fuente = self.fuente('Telefe', user_agent='VLC/3.0')
        api = self.cliente_api(['ver_canales', 'importar_canales'])
        datos = api.get(reverse('api_v1:canales_recorrido'), {'cantidad': 5, 'formatos': 'hls,directo'}).json()
        self.assertEqual(datos['quedan'], 1)
        self.assertEqual(datos['fuentes'][0] | {'url': ''}, {
            'id': fuente.pk, 'url': '', 'tipo': 'directo', 'codec': '', 'user_agent': 'VLC/3.0', 'referer': '',
            'canal': 'Telefe', 'logo': '', 'en_vivo': True})
        respuesta = api.post(reverse('api_v1:canales_recorrido'),
                             {'resultados': [{'id': fuente.pk, 'anduvo': True}]}, format='json')
        self.assertEqual(respuesta.json(), {'anotados': 1})
        self.assertEqual(api.get(reverse('api_v1:canales_recorrido')).json()['fuentes'], [])   # hoy ya está
        self.assertEqual(api.post(reverse('api_v1:canales_recorrido'), {}, format='json').status_code, 400)

    def test_solo_con_permiso(self):
        api = self.cliente_api(['ver_canales'])
        self.assertEqual(api.get(reverse('api_v1:canales_recorrido')).status_code, 403)
