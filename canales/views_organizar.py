"""
Organizar sin recargar la página (lo usa static/js/organizar_trabajo.js):

  /canales/organizar/cambiar/      cambia UN dato de una tarjeta (nombre, categoría, se muestra, destacado o
                                   imagen) y devuelve la tarjeta redibujada: la lista como planilla, arrastrar
                                   una imagen arriba de una tarjeta, la portada en la página de una serie
  /canales/organizar/imagenes/     imágenes que YA tienen otras cosas con ese nombre (otras listas, el panel)
  /canales/organizar/renombrar/    «Cambiar nombres» de lo elegido: la vista previa (JSON) y aplicarlo

El cuadro de edición completo guarda en views.organizar_editar, que también contesta JSON si se le pide
(Accept: application/json), con la misma tarjeta (tarjeta_json).
"""

import json

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.views.decorators.http import require_GET, require_POST

from usuarios.decoradores import requiere_permiso
from usuarios.permisos import chequear_permiso

from . import consultas, imagenes, organizar, secciones
from .models import Canal, Categoria, Contenido

CAMPOS = ('nombre', 'categoria', 'activo', 'destacado', 'logo')


def quiere_json(request):
    """Si la página pidió la respuesta en JSON (guardar sin recargar)."""
    return 'application/json' in request.headers.get('Accept', '')


def _canal_para_tarjeta(pk):
    """El canal con los números de la lista (cuántas señales, cuántas andan...), como lo arma Organizar."""
    return consultas.catalogo().filter(pk=pk).first()


def _serie_para_tarjeta(nombre):
    clave = (nombre or '').strip().lower()
    return next((s for s in consultas.series(texto=nombre) if s.nombre.lower() == clave), None)


def tarjeta_json(request, item, contenido, mensaje='', status=200):
    """
    La tarjeta redibujada (el mismo parcial que la página) y sus datos, para reemplazarla sin recargar:
      {'ok': True, 'mensaje': ..., 'tarjeta': '<article ...>', 'datos': {...}}
    `item` None (se borró o ya no existe): {'ok': True, 'mensaje': ..., 'tarjeta': ''}.
    """
    from .views import _preparar_para_editar   # views importa este módulo

    if item is None:
        return JsonResponse({'ok': True, 'mensaje': mensaje, 'tarjeta': '', 'datos': None})
    _preparar_para_editar([item], contenido)
    html = render_to_string('canales/_organizar_tarjeta.html', {
        'item': item, 'contenido': contenido, 'forma': secciones.forma(contenido),
        'puede_editar': chequear_permiso(request.user, 'importar_canales'),
    }, request=request)
    return JsonResponse({'ok': True, 'mensaje': mensaje, 'tarjeta': html, 'datos': json.loads(item.datos)},
                        status=status)


def _error(mensaje, status=400):
    return JsonResponse({'ok': False, 'error': mensaje}, status=status)


def _si(valor):
    return str(valor).lower() in ('1', 'true', 'on', 'si', 'sí')


def _categoria(request, contenido):
    """La categoría pedida: 'ninguna' (sin categoría), el número de una de esa sección, o una nueva (`nueva`)."""
    nueva = request.POST.get('nueva', '').strip()
    if nueva:
        return organizar.categoria_por_nombre(nueva, contenido, usuario=request.user)
    valor = request.POST.get('valor', '')
    if valor == 'ninguna':
        return None
    if not valor.isdigit():
        raise organizar.NoSePuede('Elegí una categoría.')
    categoria = get_object_or_404(Categoria, pk=valor)
    if categoria.contenido != contenido:
        raise organizar.NoSePuede('Esa categoría es de otra sección.')
    return categoria


def revisar_link_de_imagen(valor):
    """NoSePuede si `valor` no sirve como link de una imagen (vacío sí sirve: queda sin imagen)."""
    if not valor:
        return valor
    if len(valor) > 500:
        raise organizar.NoSePuede('Ese link es demasiado largo: guardá la imagen y subila desde la compu.')
    try:
        URLValidator(schemes=['http', 'https'])(valor)
    except ValidationError:
        raise organizar.NoSePuede('Eso no es el link de una imagen (tiene que empezar con http).')
    return valor


def _logo(request):
    """La imagen nueva: un archivo (gana) o un link. Vacío = sin imagen."""
    if request.FILES.get('imagen'):
        return imagenes.guardar_subida(request.FILES['imagen'], request)
    return revisar_link_de_imagen(request.POST.get('valor', '').strip())


def _datos_del_cambio(request, campo, contenido):
    if campo == 'nombre':
        nombre = organizar._limpio(request.POST.get('valor', ''), 90 if contenido == Contenido.SERIE else 120)
        if not nombre:
            raise organizar.NoSePuede('El nombre no puede quedar vacío.')
        return {'nombre': nombre}
    if campo == 'categoria':
        return {'categoria': _categoria(request, contenido)}
    if campo == 'logo':
        return {'logo': _logo(request)}
    return {campo: _si(request.POST.get('valor'))}


_QUE_CAMBIO = {'nombre': 'el nombre', 'categoria': 'la categoría', 'activo': 'si se muestra',
               'destacado': 'el destacado', 'logo': 'la imagen', 'portada': 'la portada'}


@require_POST
@requiere_permiso('importar_canales')
def cambiar(request):
    """
    Cambia UN dato de un canal, película o capítulo (`canal`: su número) o de una serie entera (`serie`: su
    nombre). `campo`: nombre | categoria | activo | destacado | logo; `valor` (o `nueva`: una categoría nueva;
    `imagen`: un archivo). Contesta la tarjeta redibujada (tarjeta_json) o {'ok': False, 'error'}.
    """
    campo = request.POST.get('campo', '')
    if campo not in CAMPOS:
        return _error('Eso no se puede cambiar desde acá.')
    try:
        if request.POST.get('tipo') == 'serie':
            nombre = request.POST.get('serie', '').strip()
            datos = _datos_del_cambio(request, campo, Contenido.SERIE)
            cambios = organizar.editar_serie(nombre, request.user, **datos)
            if 'nombre' in cambios:
                nombre = organizar.nombre_de_serie_valido(datos['nombre'])
            item, contenido, titulo = _serie_para_tarjeta(nombre), Contenido.SERIE, nombre
        else:
            canal = get_object_or_404(Canal, pk=request.POST.get('canal', '0') or 0)
            datos = _datos_del_cambio(request, campo, canal.contenido)
            cambios = organizar.editar_canal(canal, request.user, **datos)
            if 'logo' in cambios:
                imagenes.emparejar_logo_al_guardar(canal)
            item, contenido, titulo = _canal_para_tarjeta(canal.pk), canal.contenido, canal.nombre
    except (organizar.NoSePuede, imagenes.ImagenInvalida) as error:
        return _error(str(error))
    if cambios:
        mensaje = f'«{titulo}»: se cambió {" y ".join(_QUE_CAMBIO.get(c, c) for c in cambios)}.'
    else:
        mensaje = f'«{titulo}» ya estaba así.'
    if request.POST.get('tipo') != 'serie' and contenido == Contenido.SERIE:
        # Un capítulo (desde la página de su serie): en Organizar no tiene tarjeta propia, va su dato
        return JsonResponse({'ok': True, 'mensaje': mensaje, 'tarjeta': '',
                             'datos': {'tipo': 'capitulo', 'pk': canal.pk, 'nombre': canal.nombre, 'logo': canal.logo}})
    return tarjeta_json(request, item, contenido, mensaje)


@require_GET
@requiere_permiso('ver_canales')
def imagenes_sugeridas(request):
    """{'imagenes': [{'url', 'de'}]}: las que ya tienen otras cosas con ese nombre (organizar.imagenes_parecidas)."""
    excluir = request.GET.get('canal', '')
    return JsonResponse({'imagenes': organizar.imagenes_parecidas(
        request.GET.get('nombre', ''), request.GET.get('contenido', ''),
        excluir=int(excluir) if excluir.isdigit() else None)})


def _reglas(request):
    return {
        'sacar': request.POST.get('sacar', '')[:60],
        'reemplazar': request.POST.get('reemplazar', '')[:60],
        'por': request.POST.get('por', '')[:60],
        'limpiar': _si(request.POST.get('limpiar')),
        'mayusculas': _si(request.POST.get('mayusculas')),
    }


@require_POST
@requiere_permiso('importar_canales')
def renombrar(request):
    """
    «Cambiar nombres» de lo elegido en Organizar (`canal`: números; `serie`: nombres) con las reglas de
    organizar.nombre_con_reglas. Con `vista_previa`: cómo quedarían (JSON), sin tocar nada.
    """
    from .views import _volver   # views importa este módulo

    canales = Canal.objects.filter(pk__in=[pk for pk in request.POST.getlist('canal') if pk.isdigit()]).order_by('nombre')
    series = sorted({nombre.strip() for nombre in request.POST.getlist('serie') if nombre.strip()}, key=str.lower)
    reglas = _reglas(request)
    if request.POST.get('vista_previa'):
        cambios = organizar.cambios_de_nombre(canales, series, **reglas)
        return JsonResponse({'ok': True, 'cambios': [{'antes': c.antes, 'despues': c.despues} for c in cambios],
                             'elegidos': len(canales) + len(series)})
    cambios = organizar.renombrar_en_lote(canales, series, request.user, **reglas)
    hechos = [c for c in cambios if not c.error]
    if hechos:
        messages.success(request, f'Se cambió el nombre de {len(hechos)}.')
    elif not cambios:
        messages.info(request, 'Con esas reglas no cambia ningún nombre de lo elegido.')
    for cambio in (c for c in cambios if c.error):
        messages.error(request, f'«{cambio.antes}» no se cambió: {cambio.error}')
    return redirect(_volver(request, request.POST.get('seccion') or Contenido.VIVO))
