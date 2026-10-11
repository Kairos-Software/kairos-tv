"""
Planillas de Excel (.xlsx) sin instalar nada.

Un .xlsx es un .zip con unos archivos XML adentro: este módulo los escribe.
Alcanza para exportar datos (texto y números, una o varias hojas, la primera
fila en negrita y fija, con filtros y columnas de un ancho cómodo). Para
fórmulas, colores o gráficos haría falta una librería (openpyxl).

    from herramientas.excel import TIPO_XLSX, planilla

    contenido = planilla([
        ('Clientes', ['Nombre', 'Saldo'], [['Ana', 1500], ['Beto', 0]]),
        ('Pagos', ['Cliente', 'Fecha', 'Monto'], [...]),
    ])
    return HttpResponse(contenido, content_type=TIPO_XLSX,
                        headers={'Content-Disposition': 'attachment; filename="clientes.xlsx"'})

Cada valor puede ser texto, número, True/False (sale "Sí" / "No"), una
fecha (sale como texto dd/mm/aaaa) o None (celda vacía).
"""

import re
import zipfile
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape

TIPO_XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

# Lo que Excel no acepta en una celda (caracteres de control) y su máximo de letras por celda
_INVALIDOS = re.compile('[\x00-\x08\x0b\x0c\x0e-\x1f]')
_MAXIMO_POR_CELDA = 32767
# El nombre de una hoja: hasta 31 letras y sin estos caracteres
_NO_VAN_EN_EL_NOMBRE = re.compile(r'[\[\]:*?/\\]')

_ESPACIOS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" ' \
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
_ENCABEZADO_XML = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'


def columna(numero):
    """0 -> 'A', 25 -> 'Z', 26 -> 'AA' (como se llaman las columnas en Excel)."""
    letras = ''
    numero += 1
    while numero:
        numero, resto = divmod(numero - 1, 26)
        letras = chr(65 + resto) + letras
    return letras


def _como_texto(valor):
    if isinstance(valor, bool):
        return 'Sí' if valor else 'No'
    if isinstance(valor, datetime):
        return valor.strftime('%d/%m/%Y %H:%M')
    if isinstance(valor, date):
        return valor.strftime('%d/%m/%Y')
    return str(valor)


def _celda(referencia, valor, negrita=False):
    if valor is None or valor == '':
        return ''
    estilo = ' s="1"' if negrita else ''
    if isinstance(valor, (int, float, Decimal)) and not isinstance(valor, bool):
        return f'<c r="{referencia}"{estilo}><v>{valor}</v></c>'
    texto = escape(_INVALIDOS.sub('', _como_texto(valor))[:_MAXIMO_POR_CELDA])
    return f'<c r="{referencia}" t="inlineStr"{estilo}><is><t xml:space="preserve">{texto}</t></is></c>'


def _ancho(titulo, filas, indice):
    """Un ancho cómodo para la columna: el de lo más largo, entre 8 y 60."""
    largos = [len(_como_texto(titulo))]
    largos += [len(_como_texto(f[indice])) for f in filas[:500] if indice < len(f) and f[indice] is not None]
    return min(max(max(largos) + 2, 8), 60)


def _hoja(titulos, filas):
    ultima = f'{columna(max(len(titulos), 1) - 1)}{len(filas) + 1}'
    columnas = ''.join(f'<col min="{i + 1}" max="{i + 1}" width="{_ancho(t, filas, i)}" customWidth="1"/>'
                       for i, t in enumerate(titulos))
    encabezado = ''.join(_celda(f'{columna(i)}1', titulo, negrita=True) for i, titulo in enumerate(titulos))
    renglones = [f'<row r="1">{encabezado}</row>']
    for numero, fila in enumerate(filas, start=2):
        celdas = ''.join(_celda(f'{columna(i)}{numero}', valor) for i, valor in enumerate(fila))
        renglones.append(f'<row r="{numero}">{celdas}</row>')
    return (f'{_ENCABEZADO_XML}<worksheet {_ESPACIOS}>'
            # La primera fila queda fija al bajar
            '<sheetViews><sheetView workbookViewId="0">'
            '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
            '</sheetView></sheetViews>'
            + (f'<cols>{columnas}</cols>' if columnas else '')
            + f'<sheetData>{"".join(renglones)}</sheetData><autoFilter ref="A1:{ultima}"/></worksheet>')


def _nombre_de_hoja(nombre, usados):
    limpio = _NO_VAN_EN_EL_NOMBRE.sub(' ', nombre).strip()[:31] or 'Hoja'
    final, numero = limpio, 2
    while final.lower() in usados:   # Excel no acepta dos hojas con el mismo nombre
        final = f'{limpio[:28]} {numero}'
        numero += 1
    usados.add(final.lower())
    return final


def planilla(hojas):
    """
    hojas: [(nombre, [títulos de las columnas], [[valores de una fila], ...]), ...]
    Devuelve los bytes del .xlsx.
    """
    usados = set()
    hojas = [(_nombre_de_hoja(nombre, usados), list(titulos), [list(f) for f in filas])
             for nombre, titulos, filas in hojas] or [('Hoja', [], [])]
    archivo = BytesIO()
    with zipfile.ZipFile(archivo, 'w', zipfile.ZIP_DEFLATED) as zip_:
        zip_.writestr('[Content_Types].xml', _ENCABEZADO_XML + (
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/styles.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            + ''.join(f'<Override PartName="/xl/worksheets/hoja{i}.xml" '
                      'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                      for i in range(1, len(hojas) + 1))
            + '</Types>'))
        zip_.writestr('_rels/.rels', _ENCABEZADO_XML + (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/></Relationships>'))
        # Los filtros de cada hoja también se anotan en el libro (si no, Excel los arregla al abrir)
        filtros = ''.join(
            f'<definedName name="_xlnm._FilterDatabase" localSheetId="{i}" hidden="1">'
            f"'{escape(nombre).replace(chr(39), chr(39) * 2)}'!$A$1:"
            f'${columna(max(len(titulos), 1) - 1)}${len(filas) + 1}</definedName>'
            for i, (nombre, titulos, filas) in enumerate(hojas))
        zip_.writestr('xl/workbook.xml', _ENCABEZADO_XML + (
            f'<workbook {_ESPACIOS}><sheets>'
            + ''.join(f'<sheet name="{escape(nombre, {chr(34): "&quot;"})}" sheetId="{i}" r:id="rId{i}"/>'
                      for i, (nombre, _, _) in enumerate(hojas, start=1))
            + f'</sheets><definedNames>{filtros}</definedNames></workbook>'))
        zip_.writestr('xl/_rels/workbook.xml.rels', _ENCABEZADO_XML + (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + ''.join(f'<Relationship Id="rId{i}" '
                      'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                      f'Target="worksheets/hoja{i}.xml"/>' for i in range(1, len(hojas) + 1))
            + f'<Relationship Id="rId{len(hojas) + 1}" '
              'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
              'Target="styles.xml"/></Relationships>'))
        # Dos estilos: 0 = normal, 1 = negrita (los títulos)
        zip_.writestr('xl/styles.xml', _ENCABEZADO_XML + (
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
            '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<fills count="2"><fill><patternFill patternType="none"/></fill>'
            '<fill><patternFill patternType="gray125"/></fill></fills>'
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
            '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
            '</styleSheet>'))
        for i, (_, titulos, filas) in enumerate(hojas, start=1):
            zip_.writestr(f'xl/worksheets/hoja{i}.xml', _hoja(titulos, filas))
    return archivo.getvalue()
