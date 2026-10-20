"""
Una lista importada sin recargar la página (lo usa static/js/importacion_trabajo.js):

  /canales/importaciones/<id>/partes/   descartar varias categorías de una (o «Deshacer»: recuperarlas) y
                                        devolver cómo quedó cada una, para redibujar su fila

Probar y cargar siguen yendo de a tandas por views.importacion_lote / importacion_cargar (una categoría
por vez: la pantalla las encola). «No cargar» / «Cargar igual» de las entradas (views.importacion_elegir)
también contestan JSON si se les pide, con las filas redibujadas (filas_de_entradas).
"""

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from usuarios.decoradores import requiere_permiso

from . import servicios
from .models import EntradaImportada, Importacion


def _elegidas(datos):
    """Las categorías que mandó la pantalla: pares contenido / categoría (pueden ser de partes distintas)."""
    pares = zip(datos.getlist('contenido'), datos.getlist('categoria'))
    return [servicios.Seleccion(contenido.strip(), categoria.strip()) for contenido, categoria in pares
            if contenido.strip() and categoria.strip()]


@require_POST
@requiere_permiso('importar_canales')
def partes(request, pk):
    """
    accion=descartar | recuperar, con las categorías elegidas. Contesta
      {'ok': True, 'mensaje': ..., 'cantidad': 40,
       'filas': [{'contenido': 'vivo', 'categoria': 'AR | DEPORTES', 'cuentas': {...como categorias_de}}]}
    """
    importacion = get_object_or_404(Importacion, pk=pk)
    elegidas = _elegidas(request.POST)
    accion = request.POST.get('accion')
    if not elegidas or accion not in ('descartar', 'recuperar'):
        return JsonResponse({'ok': False, 'error': 'Elegí al menos una categoría.'}, status=400)
    hacer = servicios.descartar if accion == 'descartar' else servicios.recuperar
    cantidad = sum(hacer(importacion, seleccion, request.user) for seleccion in elegidas)
    que = f'«{elegidas[0].categoria}»' if len(elegidas) == 1 else f'{len(elegidas)} categorías'
    que = que.replace(f'«{servicios.SIN_CATEGORIA}»', '«Sin categoría»')
    if not cantidad:
        mensaje = 'No había nada para descartar ahí.' if accion == 'descartar' else 'No había nada para recuperar.'
    elif accion == 'descartar':
        mensaje = f'Descartados {cantidad:,} de {que}: no se prueban ni se cargan.'.replace(',', '.')
    else:
        mensaje = f'Volvieron {cantidad:,} de {que}.'.replace(',', '.')
    filas = [{'contenido': s.contenido, 'categoria': s.categoria,
              'cuentas': servicios._por_estado(s.aplicar(importacion.entradas.all()))} for s in elegidas]
    return JsonResponse({'ok': True, 'mensaje': mensaje, 'cantidad': cantidad, 'filas': filas})


def filas_de_entradas(request, importacion, pks, volver, puede_importar=True):
    """{pk: '<li class="entrada">…'} de esas entradas, con el mismo parcial que la página."""
    contexto = {
        'puede_importar': puede_importar,
        'se_pueden_elegir': [EntradaImportada.Estado.APTA, *servicios.SE_PUEDEN_CARGAR_IGUAL],
        'se_pueden_cargar_igual': servicios.SE_PUEDEN_CARGAR_IGUAL,
        'volver': volver,
    }
    return {str(e.pk): render_to_string('canales/_importacion_entrada.html', {**contexto, 'e': e}, request)
            for e in importacion.entradas.filter(pk__in=pks).select_related('canal')}
