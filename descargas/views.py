"""
La app Android para descargar.

    /descargar/          -> PÚBLICA: baja la última APK publicada. Es corta a
                            propósito: se escribe con el control remoto en la
                            app "Downloader" de la TV. Sin un código de cliente
                            válido la app no sirve, por eso no pide sesión.
    /app-android/        -> (con sesión) la página del panel: link, instrucciones
                            y, con el permiso publicar_app, subir versiones.
    /app-android/?ver=pc  -> (con sesión) la app de Kairos TV para PC (Windows):
                            link, cómo instalarla y, con publicar_app, subir
                            versiones (de a pedazos, como el analizador).
    /descargar/pc/       -> PÚBLICA, como /descargar/: el instalador de la app
                            para PC. Las apps instaladas lo bajan solas para
                            actualizarse (api/v1/app_pc.py).
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

from . import analizador, instaladores
from .forms import VersionAppForm
from .models import PcConAnalizador, VersionAnalizador, VersionApp, VersionPc

#: Cada pedazo de la subida de un instalador (static/js/subir_instalador.js): nginx acepta hasta 160 MB por pedido.
PEDAZO = 20 * 1024 * 1024

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


def solo_quien_publica(vista):
    """Subir y ocultar versiones de la app (la APK o la de PC): el permiso publicar_app."""
    @wraps(vista)
    @login_required
    def envuelta(request, *args, **kwargs):
        if not chequear_permiso(request.user, 'publicar_app'):
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
    if request.GET.get('ver') == 'pc':
        return _pagina_de_la_pc(request)
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


# ── La app de Kairos TV para PC (Windows) ─────────────────────────────

def _pagina_de_la_pc(request):
    puede_publicar = chequear_permiso(request.user, 'publicar_app')
    return render(request, 'descargas/pagina.html', {
        'ver': 'pc',
        'app_pc': VersionPc.ultima(),
        'versiones_pc': VersionPc.objects.select_related('subida_por')[:20] if puede_publicar else None,
        'puede_publicar': puede_publicar,
        'link_pc': request.build_absolute_uri(reverse('descargas:descargar_pc')),
        'pedazo_maximo': PEDAZO,
    })


def _de_la_pagina_de_la_pc():
    return f'{reverse("descargas:pagina")}?ver=pc'


def descargar_pc(request, pk=None):
    """PÚBLICA, como la APK: sin un código de cliente la app no sirve."""
    if pk:
        # Una versión puntual: las ocultas solo para quien publica
        versiones = VersionPc.objects.all()
        if not chequear_permiso(request.user, 'publicar_app'):
            versiones = versiones.filter(publicada=True)
        version = get_object_or_404(versiones, pk=pk)
    else:
        version = VersionPc.ultima()
    if version is None or not version.archivo:
        raise Http404('Todavía no hay una versión de la app para PC.')
    return entregar_instalador(version)


@require_POST
@solo_quien_publica
def pc_pedazo(request):
    """Un pedazo del instalador (subir_instalador.js): {recibido} o {error}."""
    return _pedazo(request, instaladores.APP_PC)


@require_POST
@solo_quien_publica
def pc_publicar(request):
    """Ya llegaron todos los pedazos: queda como la versión nueva. {url} para volver a la página, o {error}."""
    try:
        version = instaladores.publicar(instaladores.APP_PC, request.POST.get('id', ''),
                                        request.POST.get('version', ''), request.POST.get('notas', ''), request.user)
    except instaladores.Problema as error:
        return JsonResponse({'error': str(error)}, status=400)
    registrar(request.user, Accion.CREAR, f'Publicó la versión {version.version} de la app para PC',
              objeto=version, modulo='descargas')
    messages.success(request, f'Versión {version.version} de la app para PC publicada: desde ahora es la que se '
                              f'descarga, y las PCs con Kairos TV la ofrecen al abrirse.')
    return JsonResponse({'url': _de_la_pagina_de_la_pc()})


@require_POST
@solo_quien_publica
def pc_publicada(request, pk):
    version = get_object_or_404(VersionPc, pk=pk)
    version.publicada = not version.publicada
    version.save(update_fields=['publicada'])
    registrar(request.user, Accion.EDITAR,
              f'{"Publicó" if version.publicada else "Ocultó"} la versión {version.version} de la app para PC',
              objeto=version, modulo='descargas')
    messages.success(request, f'Versión {version.version} {"publicada" if version.publicada else "oculta"}.')
    return redirect(_de_la_pagina_de_la_pc())


def _pedazo(request, tipo):
    """Un pedazo de un instalador ([tipo]: el de la app para PC o el del analizador): {recibido} o {error}."""
    try:
        desde = int(request.POST.get('desde', ''))
        pedazo = request.FILES['pedazo']
        recibido = instaladores.guardar_pedazo(tipo, request.POST.get('id', ''), desde, pedazo)
    except (ValueError, KeyError):
        return JsonResponse({'error': 'Faltan datos del pedazo. Volvé a elegir el archivo.'}, status=400)
    except instaladores.Problema as error:
        return JsonResponse({'error': str(error)}, status=400)
    return JsonResponse({'recibido': recibido})


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
        'pedazo_maximo': PEDAZO,
    })


def _de_la_pagina_del_analizador():
    return f'{reverse("descargas:pagina")}?ver=analizador'


@require_POST
@solo_superusuarios
def analizador_pedazo(request):
    """Un pedazo del instalador (subir_instalador.js): {recibido} o {error}."""
    return _pedazo(request, instaladores.ANALIZADOR)


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
