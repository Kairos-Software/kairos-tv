"""
La app Android para descargar.

    /descargar/          -> PÚBLICA: baja la última APK publicada. Es corta a
                            propósito: se escribe con el control remoto en la
                            app "Downloader" de la TV. Sin un código de cliente
                            válido la app no sirve, por eso no pide sesión.
    /app-android/        -> (con sesión) la página del panel: link, instrucciones
                            y, con el permiso publicar_app, subir versiones.
    /app-android/?ver=analizador  -> SOLO SUPERUSUARIOS: el analizador de canales
                            para PC (bajar el instalador, publicar versiones y
                            las PCs donde está instalado). Ver analizador.py.
"""

from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from actividad.models import Accion
from actividad.registro import registrar
from usuarios.permisos import chequear_permiso

from . import analizador
from .forms import VersionAppForm
from .models import PcConAnalizador, VersionAnalizador, VersionApp

TIPO_APK = 'application/vnd.android.package-archive'
TIPO_EXE = 'application/vnd.microsoft.portable-executable'


def solo_superusuarios(vista):
    """Lo del analizador para PC: ni los revendedores ni los otros roles lo ven."""
    @wraps(vista)
    @login_required
    def envuelta(request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied
        return vista(request, *args, **kwargs)
    return envuelta


def descargar(request, pk=None):
    if pk:
        # Una versión puntual: las ocultas solo para quien publica
        versiones = VersionApp.objects.all()
        if not chequear_permiso(request.user, 'publicar_app'):
            versiones = versiones.filter(publicada=True)
        version = get_object_or_404(versiones, pk=pk)
    else:
        version = VersionApp.ultima()
    if version is None or not version.archivo:
        raise Http404('Todavía no hay una versión de la app para descargar.')
    try:
        archivo = version.archivo.open('rb')
    except FileNotFoundError:
        raise Http404('No se encontró el archivo de la app.')
    return FileResponse(archivo, as_attachment=True, filename=version.nombre_descarga, content_type=TIPO_APK)


@login_required
def pagina(request):
    if request.user.is_superuser and request.GET.get('ver') == 'analizador':
        return _pagina_del_analizador(request)
    puede_publicar = chequear_permiso(request.user, 'publicar_app')
    form = VersionAppForm()
    if request.method == 'POST':
        if not puede_publicar:
            raise PermissionDenied
        form = VersionAppForm(request.POST, request.FILES)
        if form.is_valid():
            version = form.save(commit=False)
            version.subida_por = request.user
            version.save()
            registrar(request.user, Accion.CREAR, f'Publicó la versión {version.version} de la app', objeto=version,
                      modulo='descargas')
            messages.success(request, f'Versión {version.version} publicada: desde ahora es la que se descarga.')
            return redirect('descargas:pagina')

    return render(request, 'descargas/pagina.html', {
        'ultima': VersionApp.ultima(),
        'versiones': VersionApp.objects.all()[:20] if puede_publicar else None,
        'form': form,
        'puede_publicar': puede_publicar,
        'link': request.build_absolute_uri('/descargar/'),
    })


@require_POST
@login_required
def cambiar_publicada(request, pk):
    if not chequear_permiso(request.user, 'publicar_app'):
        raise PermissionDenied
    version = get_object_or_404(VersionApp, pk=pk)
    version.publicada = not version.publicada
    version.save(update_fields=['publicada'])
    registrar(request.user, Accion.EDITAR,
              f'{"Publicó" if version.publicada else "Despublicó"} la versión {version.version} de la app',
              objeto=version, modulo='descargas')
    messages.success(request, f'Versión {version.version} {"publicada" if version.publicada else "despublicada"}.')
    return redirect('descargas:pagina')


# ── El analizador de canales para PC (solo superusuarios) ─────────────

def _pagina_del_analizador(request):
    ultima = VersionAnalizador.ultima()
    pcs = list(PcConAnalizador.objects.all())
    for pc in pcs:
        pc.al_dia = analizador.al_dia(pc, ultima)
    return render(request, 'descargas/pagina.html', {
        'ver': 'analizador',
        'analizador': ultima,
        'versiones_analizador': VersionAnalizador.objects.select_related('subida_por')[:20],
        'pcs': pcs,
        'pedazo_maximo': 20 * 1024 * 1024,
    })


def _de_la_pagina_del_analizador():
    return f'{reverse("descargas:pagina")}?ver=analizador'


@require_POST
@solo_superusuarios
def analizador_pedazo(request):
    """Un pedazo del instalador (subir_analizador.js): {recibido} o {error}."""
    try:
        desde = int(request.POST.get('desde', ''))
        pedazo = request.FILES['pedazo']
        recibido = analizador.guardar_pedazo(request.POST.get('id', ''), desde, pedazo)
    except (ValueError, KeyError):
        return JsonResponse({'error': 'Faltan datos del pedazo. Volvé a elegir el archivo.'}, status=400)
    except analizador.Problema as error:
        return JsonResponse({'error': str(error)}, status=400)
    return JsonResponse({'recibido': recibido})


@require_POST
@solo_superusuarios
def analizador_publicar(request):
    """Ya llegaron todos los pedazos: queda como la versión nueva. {url} para volver a la página, o {error}."""
    try:
        version = analizador.publicar(request.POST.get('id', ''), request.POST.get('version', ''),
                                      request.POST.get('notas', ''), request.user)
    except analizador.Problema as error:
        return JsonResponse({'error': str(error)}, status=400)
    registrar(request.user, Accion.CREAR, f'Publicó la versión {version.version} del analizador de canales',
              objeto=version, modulo='descargas')
    messages.success(request, f'Versión {version.version} del analizador publicada. Los analizadores instalados la '
                              f'van a bajar e instalar solos (preguntan cada hora).')
    return JsonResponse({'url': _de_la_pagina_del_analizador()})


@require_GET
@solo_superusuarios
def analizador_descargar(request, pk=None):
    if pk:
        version = get_object_or_404(VersionAnalizador, pk=pk)
    else:
        version = VersionAnalizador.ultima()
    if version is None or not version.archivo:
        raise Http404('Todavía no hay un instalador del analizador.')
    return entregar_instalador(version)


def entregar_instalador(version):
    try:
        archivo = version.archivo.open('rb')
    except FileNotFoundError:
        raise Http404('No se encontró el instalador.')
    return FileResponse(archivo, as_attachment=True, filename=version.nombre_descarga, content_type=TIPO_EXE)


@require_POST
@solo_superusuarios
def analizador_publicada(request, pk):
    version = get_object_or_404(VersionAnalizador, pk=pk)
    version.publicada = not version.publicada
    version.save(update_fields=['publicada'])
    registrar(request.user, Accion.EDITAR,
              f'{"Publicó" if version.publicada else "Ocultó"} la versión {version.version} del analizador',
              objeto=version, modulo='descargas')
    messages.success(request, f'Versión {version.version} {"publicada" if version.publicada else "oculta"}.')
    return redirect(_de_la_pagina_del_analizador())


@require_POST
@solo_superusuarios
def analizador_pc(request, pk):
    """Desconectar una PC (deja de recibir versiones nuevas) o volver a conectarla."""
    pc = get_object_or_404(PcConAnalizador, pk=pk)
    pc.desconectada = not pc.desconectada
    pc.save(update_fields=['desconectada'])
    registrar(request.user, Accion.EDITAR,
              f'{"Desconectó" if pc.desconectada else "Volvió a conectar"} la PC «{pc.nombre}» del analizador',
              objeto=pc, modulo='descargas')
    messages.success(request, f'«{pc.nombre}» {"ya no recibe" if pc.desconectada else "vuelve a recibir"} '
                              f'versiones nuevas del analizador.')
    return redirect(_de_la_pagina_del_analizador())
