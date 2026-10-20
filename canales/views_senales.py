"""
"Señales" (/canales/senales/): todas las fuentes con problemas, una por una,
aunque su canal se siga viendo con otras. Ver senales.py.

  /canales/senales/          la lista (?problema=, ?contenido=, ?origen=, ?q=, ?canal=<pk>)
  /canales/senales/accion/   POST: probar, quitar, volver a mostrar o borrar las elegidas (fuente=<pk>, varias)
"""

from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from usuarios.decoradores import requiere_permiso
from usuarios.permisos import chequear_permiso

from . import consultas, secciones, senales, servicios
from .models import Canal, Fuente
from .verificacion import verificar_varias


def _filtros(datos):
    contenido = datos.get('contenido', '')
    canal = datos.get('canal', '')
    return {
        'problema': datos.get('problema', '') if datos.get('problema', '') in [*senales.PROBLEMAS, 'cualquiera']
        else 'todas',
        'contenido': contenido if secciones.es_valida(contenido) else '',
        'origen': datos.get('origen', ''),
        'texto': datos.get('q', '').strip(),
        'canal': int(canal) if canal.isdigit() else None,
    }


@requiere_permiso('ver_canales')
def lista(request):
    filtros = _filtros(request.GET)
    filas, cuentas = senales.armar(filtros['contenido'], filtros['problema'], filtros['origen'], filtros['texto'],
                                   filtros['canal'])
    parametros = request.GET.copy()
    parametros.pop('pagina', None)
    sin_problema = parametros.copy()
    sin_problema.pop('problema', None)
    return render(request, 'canales/senales.html', {
        'pagina': Paginator(filas, senales.POR_PAGINA).get_page(request.GET.get('pagina')),
        'filtros': filtros,
        'cuentas': cuentas,
        'problemas': [(clave, nombre, ayuda, cuentas[clave]) for clave, (nombre, ayuda) in senales.PROBLEMAS.items()],
        'secciones': secciones.todas(),
        'origenes': consultas.origenes(filtros['contenido']),
        'canal': Canal.objects.filter(pk=filtros['canal']).first() if filtros['canal'] else None,
        'hay_filtros': any([filtros['contenido'], filtros['origen'], filtros['texto'], filtros['canal']]),
        'parametros': parametros.urlencode(),
        'sin_problema': sin_problema.urlencode(),
        'puede_editar': chequear_permiso(request.user, 'importar_canales'),
    })


def _volver(request):
    volver = request.POST.get('volver', '')
    if not url_has_allowed_host_and_scheme(volver, allowed_hosts={request.get_host()}):
        volver = reverse('canales:senales')
    return redirect(volver)


@require_POST
@requiere_permiso('importar_canales')
def accion(request):
    # El botón de una fila manda "una=probar:123" (y no cuenta lo tildado); la barra de abajo, accion + lo tildado
    una = request.POST.get('una', '')
    if ':' in una:
        que, pk = una.split(':', 1)
        pks = [pk] if pk.isdigit() else []
    else:
        que, pks = request.POST.get('accion'), [pk for pk in request.POST.getlist('fuente') if pk.isdigit()]
    fuentes = Fuente.objects.filter(pk__in=pks, canal__eliminado_en__isnull=True).select_related('canal')
    if not fuentes:
        messages.info(request, 'No elegiste ninguna señal.')
    elif que == 'probar':
        andan, probadas = senales.probar(fuentes.order_by('canal__nombre', 'prioridad'), verificar_varias)
        if not probadas:
            messages.info(request, 'No se llegó a probar ninguna (tardaron demasiado). Probá con menos, o de nuevo en '
                                   'un rato.')
        else:
            resto = len(pks) - probadas
            texto = f'Se probaron {probadas}: {andan} andan ahora' + (' (las retiradas que andan ya volvieron a la app)'
                                                                      if andan else '') + '.'
            if resto > 0:
                texto += f' Quedaron {resto} sin probar: volvé a tocar «Probar».'
            (messages.success if andan else messages.warning)(request, texto)
    elif que == 'quitar':
        for fuente in fuentes:
            servicios.quitar_fuente(fuente, request.user)
        messages.success(request, f'Se quitaron {len(fuentes)} señal(es): la app deja de usarlas. No se borraron: '
                                  f'«Volver a mostrar» las devuelve.')
    elif que == 'mostrar':
        for fuente in fuentes:
            servicios.mostrar_fuente(fuente, request.user)
        messages.success(request, f'{len(fuentes)} señal(es) vuelven a la app. Si en una semana siguen sin andar, la '
                                  f'limpieza las vuelve a retirar.')
    elif que == 'borrar':
        sin_senal = []
        for fuente in fuentes:
            canal = fuente.canal
            if not servicios.borrar_fuente(fuente, request.user):
                sin_senal.append(canal.nombre)
        texto = f'Se borraron {len(fuentes)} señal(es). Las direcciones quedaron anotadas en la Actividad.'
        if sin_senal:
            messages.warning(request, texto + f' Quedaron SIN señales (no se ven): {", ".join(sin_senal[:10])}'
                                              + (f' y {len(sin_senal) - 10} más' if len(sin_senal) > 10 else '') + '.')
        else:
            messages.success(request, texto)
    else:
        messages.error(request, 'No se entendió qué hacer.')
    return _volver(request)
