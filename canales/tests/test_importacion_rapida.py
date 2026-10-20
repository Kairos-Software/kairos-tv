"""
La pantalla de una lista importada sin recargar (canales/views_importacion.py, static/js/importacion_trabajo.js):
las categorías de toda la lista, descartar varias de una y «Deshacer», y «No cargar» / «Cargar igual» que
contestan las filas redibujadas.
"""

import json
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from canales import servicios
from canales.models import EntradaImportada
from canales.servicios import Seleccion
from canales.tests.test_importar_por_partes import LISTA
from canales.tests.test_verificacion import verificador_falso
from usuarios.models import Rol, Usuario

Estado = EntradaImportada.Estado


class CategoriasDeTodaLaListaTests(TestCase):

    def test_sin_parte_vienen_las_de_todas_con_su_parte(self):
        importacion = servicios.crear_importacion(LISTA, 'proveedor.m3u')
        filas = {(c['contenido'], c['nombre']): c['total'] for c in servicios.categorias_de(importacion)}
        self.assertEqual(filas, {('vivo', 'Noticias'): 3, ('vivo', 'Deportes'): 1, ('vivo', 'Sin categoría'): 1,
                                 ('pelicula', 'Acción'): 2, ('serie', 'Novelas'): 6})


class DeshacerElDescarteTests(TestCase):

    def setUp(self):
        self.importacion = servicios.crear_importacion(LISTA, 'proveedor.m3u')

    def test_vuelve_cada_una_a_como_estaba(self):
        noticias = Seleccion('vivo', 'Noticias')
        servicios.procesar_lote(self.importacion, verificador_falso, seleccion=noticias)   # 2 pasan
        en_vivo = Seleccion('vivo')
        self.assertEqual(servicios.descartar(self.importacion, en_vivo), 4)   # 2 que pasaron + 2 sin probar
        self.assertEqual(servicios.progreso(self.importacion)['para_verificar'], 10)   # 12 menos las 2 sin probar

        self.assertEqual(servicios.recuperar(self.importacion, en_vivo), 4)
        estados = dict(self.importacion.entradas.filter(contenido='vivo').values_list('nombre', 'estado'))
        self.assertEqual(estados, {'Canal 26': Estado.APTA, 'Encuentro': Estado.APTA, 'Deportivo': Estado.PENDIENTE,
                                   'Sin grupo': Estado.PENDIENTE, 'Canal 26 repetido': Estado.REPETIDA})
        self.assertEqual(servicios.progreso(self.importacion)['para_verificar'], 12)

    def test_no_toca_lo_descartado_de_otra_forma(self):
        servicios.procesar_lote(self.importacion, verificador_falso, seleccion=Seleccion('pelicula'))
        servicios.no_cargar(self.importacion, list(self.importacion.entradas.filter(contenido='pelicula')
                                                   .values_list('pk', flat=True)))
        # «No cargar» de a una se vuelve atrás con «Cargar igual», no con este «Deshacer»
        self.assertEqual(servicios.recuperar(self.importacion, Seleccion('pelicula')), 0)


@mock.patch('canales.views.verificar_varias', verificador_falso)
class PantallaSinRecargarTests(TestCase):

    def setUp(self):
        rol = Rol.objects.create(nombre='Canales', permisos=['ver_canales', 'importar_canales'])
        self.client.force_login(Usuario.objects.create_user('marcos', None, 'x', rol=rol))
        self.importacion = servicios.crear_importacion(LISTA, 'proveedor.m3u')
        self.url = reverse('canales:importacion', args=[self.importacion.pk])
        self.partes = reverse('canales:importacion_partes', args=[self.importacion.pk])

    def test_la_pantalla_trae_todas_las_categorias_con_su_proximo_paso(self):
        pagina = self.client.get(self.url)
        self.assertContains(pagina, 'Categorías de toda la lista')
        self.assertContains(pagina, 'data-contenido="serie" data-categoria="Novelas"')
        self.assertContains(pagina, 'data-fila-accion="probar"')
        self.assertContains(pagina, 'Probar y cargar')
        self.assertContains(pagina, 'js/importacion_trabajo.js')

    def test_descartar_varias_categorias_y_deshacer(self):
        datos = {'accion': 'descartar', 'contenido': ['vivo', 'pelicula'], 'categoria': ['Deportes', 'Acción']}
        r = self.client.post(self.partes, datos).json()
        self.assertEqual((r['ok'], r['cantidad']), (True, 3))
        self.assertIn('2 categorías', r['mensaje'])
        self.assertEqual([(f['categoria'], f['cuentas']['descartadas']) for f in r['filas']],
                         [('Deportes', 1), ('Acción', 2)])
        self.assertEqual(self.importacion.entradas.filter(estado=Estado.DESCARTADA).count(), 3)

        r = self.client.post(self.partes, {**datos, 'accion': 'recuperar'}).json()
        self.assertEqual(r['cantidad'], 3)
        self.assertFalse(self.importacion.entradas.filter(estado=Estado.DESCARTADA).exists())

    def test_sin_categorias_o_sin_permiso(self):
        self.assertEqual(self.client.post(self.partes, {'accion': 'descartar'}).status_code, 400)
        rol = Rol.objects.create(nombre='Mira', permisos=['ver_canales'])
        self.client.force_login(Usuario.objects.create_user('mira', None, 'x', rol=rol))
        respuesta = self.client.post(self.partes, {'accion': 'descartar', 'contenido': 'vivo', 'categoria': 'Deportes'})
        self.assertEqual(respuesta.status_code, 403)

    def test_no_cargar_contesta_la_fila_redibujada(self):
        self.client.post(reverse('canales:importacion_lote', args=[self.importacion.pk]))
        entrada = self.importacion.entradas.get(nombre='Canal 26')
        respuesta = self.client.post(reverse('canales:importacion_elegir', args=[self.importacion.pk]),
                                     {'no_cargar_una': entrada.pk, 'volver': self.url},
                                     HTTP_ACCEPT='application/json')
        r = respuesta.json()
        self.assertEqual((r['ok'], r['cantidad']), (True, 1))
        fila = r['filas'][str(entrada.pk)]
        self.assertIn(f'data-entrada="{entrada.pk}"', fila)
        self.assertIn(f'name="cargar_una" value="{entrada.pk}"', fila)   # ahora ofrece volver atrás
        entrada.refresh_from_db()
        self.assertEqual(entrada.estado, Estado.DESCARTADA)
        self.assertEqual(json.loads(respuesta.content)['mensaje'], '1 pasaron a «Descartados»: no se van a cargar.')
