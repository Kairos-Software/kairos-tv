"""Planillas de Excel sin librerías (herramientas/excel.py)."""

import zipfile
from datetime import datetime
from io import BytesIO

from django.test import SimpleTestCase

from herramientas.excel import columna, planilla


def _abrir(datos):
    with zipfile.ZipFile(BytesIO(datos)) as libro:
        return {nombre: libro.read(nombre).decode() for nombre in libro.namelist()}


class PlanillaTests(SimpleTestCase):

    def test_nombres_de_columna(self):
        self.assertEqual([columna(n) for n in (0, 25, 26, 27, 701, 702)], ['A', 'Z', 'AA', 'AB', 'ZZ', 'AAA'])

    def test_texto_numeros_si_no_y_fechas(self):
        archivos = _abrir(planilla([('Clientes', ['Nombre', 'Saldo', 'Activo', 'Alta'],
                                     [['Ana & <Beto>', 1500, True, datetime(2026, 10, 11, 9, 5)],
                                      ['Sin datos', None, False, None]])]))
        hoja = archivos['xl/worksheets/hoja1.xml']
        self.assertIn('<c r="A1" t="inlineStr" s="1"><is><t xml:space="preserve">Nombre</t></is></c>', hoja)
        self.assertIn('>Ana &amp; &lt;Beto&gt;<', hoja)       # escapado: no rompe el XML
        self.assertIn('<c r="B2"><v>1500</v></c>', hoja)       # número de verdad (se puede sumar)
        self.assertIn('>Sí<', hoja)
        self.assertIn('>No<', hoja)
        self.assertIn('>11/10/2026 09:05<', hoja)
        self.assertNotIn('r="B3"', hoja)                       # None = celda vacía
        self.assertIn('<autoFilter ref="A1:D3"/>', hoja)
        self.assertIn('state="frozen"', hoja)

    def test_nombres_de_hoja_validos_y_sin_repetir(self):
        archivos = _abrir(planilla([('Ventas: 2026/10', ['A'], []), ('Ventas: 2026/10', ['A'], [])]))
        self.assertIn('name="Ventas  2026 10"', archivos['xl/workbook.xml'])
        self.assertIn('name="Ventas  2026 10 2"', archivos['xl/workbook.xml'])
        self.assertIn('xl/worksheets/hoja2.xml', archivos)

    def test_saca_lo_que_excel_no_acepta(self):
        hoja = _abrir(planilla([('H', ['A'], [['con\x01control']])]))['xl/worksheets/hoja1.xml']
        self.assertIn('>concontrol<', hoja)
