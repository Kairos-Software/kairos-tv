"""
"Para revisar" (/canales/revisar/): la bandeja con solo lo que necesita una
decisión, lo más visto primero, y cómo está cada lista de origen. Ver bandeja.py.

  /canales/revisar/                 la bandeja de una sección (?contenido=vivo|pelicula|serie|...; ?grupo= ve todos)
  /canales/revisar/decidir/         POST: quitar, volver a mostrar, dejar así o probar de nuevo (canal=<pk>, varios)
  /canales/revisar/lista/           POST: apagar o volver a prender todas las fuentes de una lista de origen
  /canales/fuentes/<id>/accion/     POST: una SEÑAL sola, desde Organizar → Detalles: quitar, volver a mostrar
                                    o probar ahora (vuelve con el panel de detalles de ese canal abierto)
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from usuarios.decoradores import requiere_permiso
from usuarios.permisos import chequear_permiso

from . import bandeja, salud, secciones, servicios
from .models import Canal, Contenido, Fuente
from .verificacion import FUNCIONA, SIN_VERIFICAR, verificar_url, verificar_varias


def _seccion(valor):
    return valor if secciones.es_valida(valor or '') else Contenido.VIVO


@requiere_permiso('ver_canales')
def revisar(request):
    contenido = _seccion(request.GET.get('contenido'))
    abierto = request.GET.get('grupo', '')
    grupos, cuentas = bandeja.armar(contenido)
    for grupo in grupos:
        grupo.mostrados = grupo.casos if grupo.clave == abierto else grupo.casos[:bandeja.CASOS_POR_GRUPO]
    pendientes = sum(g.cantidad for g in grupos)
    return render(request, 'canales/revisar.html', {
        'contenido': contenido,
        'nombre_seccion': secciones.nombre(contenido),
        'secciones': secciones.todas(),
        'grupos': grupos,
        'pendientes': pendientes,
        'estados': [(estado.label, cuentas.get(estado, 0), estado.value) for estado in salud.Salud
                    if estado != salud.Salud.MUERTA],
        'quitados': cuentas.get(None, 0),
        'listas': bandeja.listas(contenido),
        'puede_decidir': chequear_permiso(request.user, 'importar_canales'),
        'dias_para_quitar': salud.DIAS_PARA_QUITAR,
        'es_serie': contenido == Contenido.SERIE,
    })


def _volver(request, contenido):
    volver = request.POST.get('volver', '')
    if not url_has_allowed_host_and_scheme(volver, allowed_hosts={request.get_host()}):
        volver = f"{reverse('canales:revisar')}?contenido={contenido}"
    return redirect(volver)


@require_POST
@requiere_permiso('importar_canales')
def decidir(request):
    contenido = _seccion(request.POST.get('contenido'))
    pks = [pk for pk in request.POST.getlist('canal') if pk.isdigit()]
    canales = Canal.objects.filter(pk__in=pks)
    accion = request.POST.get('accion')
    if not pks:
        messages.info(request, 'No se eligió nada.')
    elif accion == 'quitar':
        cantidad = servicios.quitar_canales(canales, 'Quitado desde Para revisar.', request.user)
        messages.success(request, f'Se quitaron {cantidad} de la app. Están en Organizar → «Quitado a mano», por si '
                                  f'te arrepentís.')
    elif accion == 'mostrar':
        cantidad = servicios.mostrar_canales(canales, request.user)
        messages.success(request, f'{cantidad} vuelven a la app. Si en una semana siguen sin andar, la limpieza los '
                                  f'vuelve a quitar.')
    elif accion == 'borrar_retiradas':
        cantidad = bandeja.borrar_retiradas(canales, request.user)
        messages.success(request, f'Se borraron {cantidad} señal(es) retiradas. Los canales siguen con sus otras '
                                  f'señales. Las direcciones quedaron anotadas en la Actividad.')
    elif accion == 'dejar':
        cantidad = bandeja.dejar_asi(canales, request.user)
        messages.success(request, f'Listo: {cantidad} no vuelven a aparecer acá mientras sigan igual.')
    elif accion == 'probar':
        andan, probadas = bandeja.probar_de_nuevo(canales, verificar_varias)
        if not probadas:
            messages.info(request, 'No se llegó a probar ninguna fuente (no tiene fuentes prendidas, o tardaron '
                                   'demasiado). Probá de nuevo en un rato.')
        elif andan:
            messages.success(request, f'De {probadas} fuente(s) probadas, {andan} andan ahora: ya vuelven a la app.')
        else:
            messages.warning(request, f'Se probaron {probadas} fuente(s) y ninguna anda desde el servidor. Si es un '
                                      f'panel Xtream, el servidor puede no poder probarlo: miralo en un aparato.')
    else:
        messages.error(request, 'No se entendió qué hacer.')
    return _volver(request, contenido)


@require_POST
@requiere_permiso('importar_canales')
def lista(request):
    contenido = _seccion(request.POST.get('contenido'))
    origen = request.POST.get('origen', '')
    prender = request.POST.get('accion') == 'prender'
    if not origen:
        messages.error(request, 'Esa lista no tiene nombre: sus fuentes se apagan de a una, desde Organizar.')
        return _volver(request, contenido)
    cantidad = bandeja.prender_o_apagar_lista(origen, prender, contenido, request.user)
    if prender:
        messages.success(request, f'Se prendieron {cantidad} fuentes de «{origen}».')
    else:
        messages.success(request, f'Se apagaron {cantidad} fuentes de «{origen}». Los canales que tienen otra fuente '
                                  f'buena siguen andando. Para deshacerlo, «Volver a prender» en la misma lista.')
    return _volver(request, contenido)


@require_POST
@requiere_permiso('importar_canales')
def fuente_accion(request, pk):
    fuente = get_object_or_404(Fuente.objects.select_related('canal'), pk=pk)
    canal = fuente.canal
    accion = request.POST.get('accion')
    if accion == 'quitar':
        servicios.quitar_fuente(fuente, request.user)
        messages.success(request, f'Se quitó esa señal de «{canal.nombre}»: la app deja de usarla. No se borró: '
                                  f'«Volver a mostrar esta señal» la devuelve.')
    elif accion == 'mostrar':
        servicios.mostrar_fuente(fuente, request.user)
        messages.success(request, f'Esa señal de «{canal.nombre}» vuelve a la app. Si en una semana sigue sin andar, '
                                  f'la limpieza la vuelve a retirar.')
    elif accion == 'probar':
        resultado = servicios.probar_fuente(fuente, verificar_url)
        if resultado.estado == FUNCIONA:
            messages.success(request, f'Esa señal de «{canal.nombre}» anda ahora.')
        elif resultado.estado == SIN_VERIFICAR:
            messages.info(request, f'El servidor no puede probar esa señal ({resultado.error or "no se sabe"}). Si es '
                                   f'un panel Xtream, probala en un aparato o con el modo revisión de la app.')
        else:
            messages.warning(request, f'Esa señal de «{canal.nombre}» no anda desde el servidor: {resultado.error}')
    else:
        messages.error(request, 'No se entendió qué hacer.')
    volver = request.POST.get('volver', '')
    if not url_has_allowed_host_and_scheme(volver, allowed_hosts={request.get_host()}):
        volver = f"{reverse('canales:organizar')}?contenido={canal.contenido}"
    return redirect(f'{volver.split("#")[0]}#ver-{canal.pk}')
