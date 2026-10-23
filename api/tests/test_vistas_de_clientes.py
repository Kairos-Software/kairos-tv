"""
Lo que puede pedir un cliente que entra a la app con su código (api/permisos.py).

La app 1.2.38 pedía las series a dos vistas nuevas que no estaban en la lista
de los clientes: con el código decía "No tenés permiso para hacer esto" (con
el superusuario andaba, porque no es un cliente). Acá se entra con un código
de verdad, como el celular, y se pide todo lo que pide la app para mirar.
"""

from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from api import permisos, tokens
from api.v1.urls import urlpatterns
from canales.models import Canal, Categoria, Contenido, Fuente
from reventa import servicios

# Las vistas que NO son para los clientes. Una vista nueva tiene que estar acá
# o en permisos.VISTAS_PARA_MIRAR (si la pide la app para mirar).
SOLO_DEL_PANEL = {
    'indice', 'login', 'logout', 'perfil', 'perfil_opciones', 'cambiar_password', 'usuarios', 'usuarios_opciones',
    'usuario', 'usuario_estado', 'usuario_restablecer_password', 'canales_recorrido', 'notificaciones',
    'notificacion_leida', 'notificaciones_marcar_todas',
    # Sin sesión (las usa cualquiera): la última versión de la app y entrar con el código
    'app', 'cliente_login',
}


class VistasDeClientesTests(TestCase):

    def setUp(self):
        cache.clear()
        self.juan = servicios.crear_revendedor('juan', 'Clave-segura-2026', precio_pantalla=Decimal('5000'))
        servicios.regalar_creditos(self.juan, 10)
        cliente = servicios.crear_cliente(self.juan, 'Ana')
        servicios.renovar(cliente, dispositivos=2)
        cliente.refresh_from_db()
        drama = Categoria.objects.create(nombre='Drama', contenido=Contenido.SERIE)
        canal = Canal.objects.create(nombre='Lost S01 E01', contenido=Contenido.SERIE, categoria=drama)
        self.fuente = Fuente.objects.create(canal=canal, url='http://p:8080/series/u/c/1.mp4',
                                            tipo=Fuente.Tipo.DIRECTO)
        entrada = APIClient().post(reverse('api_v1:cliente_login'),
                                   {'codigo': cliente.codigo_legible, 'dispositivo': 'Celular de Ana'})
        self.app = APIClient()
        self.app.credentials(HTTP_AUTHORIZATION=f'Bearer {entrada.json()["token"]}')

    def test_con_el_codigo_ve_las_series(self):
        datos = self.app.get(reverse('api_v1:canales_series'), {'formatos': 'directo'}).json()
        self.assertEqual([s['nombre'] for s in datos['series']], ['Lost'])
        datos = self.app.get(reverse('api_v1:canales_series_capitulos'),
                             {'nombre': 'Lost', 'formatos': 'directo'}).json()
        self.assertEqual([c['nombre'] for g in datos['categorias'] for c in g['canales']], ['Lost S01 E01'])

    def test_con_el_codigo_avisa_los_cortes(self):
        respuesta = self.app.post(reverse('api_v1:fuente_estabilidad', args=[self.fuente.pk]),
                                  {'segundos': 600, 'cortes': 1}, format='json')
        self.assertEqual(respuesta.status_code, 200, respuesta.json())
        self.fuente.refresh_from_db()
        self.assertEqual(self.fuente.segundos_en_aparatos, 600)

    def test_el_revendedor_mira_las_series_con_su_pantalla(self):
        clave, _ = tokens.crear_token(self.juan.usuario)
        panel = APIClient()
        panel.credentials(HTTP_AUTHORIZATION=f'Bearer {clave}')
        respuesta = panel.get(reverse('api_v1:canales_series'))
        self.assertEqual(respuesta.json()['codigo'], 'revendedor_sin_pantalla')

    def test_cada_vista_esta_decidida(self):
        # Si falla: la vista nueva, ¿la pide la app para mirar? Va en permisos.VISTAS_PARA_MIRAR. ¿Es del panel? Acá.
        todas = {f'api_v1:{ruta.name}' for ruta in urlpatterns}
        del_panel = {f'api_v1:{nombre}' for nombre in SOLO_DEL_PANEL}
        self.assertEqual(todas - del_panel, permisos.VISTAS_DE_CLIENTES)
        self.assertFalse(del_panel & permisos.VISTAS_DE_CLIENTES)
