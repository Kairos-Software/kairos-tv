"""
Pantallas de canales del panel:

  /canales/                         resumen, subir una lista, verificar todas (de a tandas) e importaciones anteriores
  /canales/importaciones/<id>/      la prueba de una lista: el avance, qué es apto, qué no y por qué, y cargar las aptas
  /canales/organizar/               TODO en un lugar: árbol de categorías (con subcategorías) y su contenido para
                                    editar, mover, cambiar el tipo, quitar o eliminar, de dónde salió cada cosa y
                                    los datos técnicos de cada señal (formato, códec, error, cuándo se probó)
  /canales/catalogo/ y /series/     las pantallas viejas: llevan a Organizar contenido con los mismos filtros
  /canales/series/detalle/          temporadas, capítulos, disponibilidad y fuentes de una serie
  /canales/canal/<id>/editar/       nombre, logo, categoría... de un canal, y sus fuentes
  /canales/youtube/                 traer las películas de un canal oficial de YouTube (se prueban y cargan como una lista)
  /canales/probar/                  probar una dirección suelta y, si anda, agregarla como canal
  /canales/lo-mas-visto/            lo más visto (canales, películas y series), sin datos de clientes
  /canales/categorias/              ordenar las categorías: crear, renombrar, juntar, borrar y el orden en la app
  /canales/secciones/               crear, cambiar y borrar secciones nuevas de la app (Música, Radio...)

Lo que tarda (verificar) se hace de a tandas: la página llama una y otra
vez a las direcciones ".../lote/" (responden JSON) y va mostrando el avance.
"""

import json
from functools import partial
from urllib.parse import quote, urlencode

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.formats import date_format
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.text import slugify
from django.utils.timezone import localtime
from django.views.decorators.http import require_POST

from actividad.models import Accion
from actividad.registro import registrar
from herramientas.excel import TIPO_XLSX
from usuarios.decoradores import requiere_permiso
from usuarios.permisos import chequear_permiso

from . import consultas, estadisticas, exportar, imagenes, organizar, secciones, servicios, youtube
from .clasificar import formato, idioma_y_pais, limpiar_nombre
from .forms import (CanalForm, CanalNuevoForm, EditarDesdeOrganizarForm, FuentesFormSet, ImportarListaForm,
                    ProbarLinkForm, QuitarCanalesForm, TraerDeYoutubeForm)
from .models import Canal, Categoria, Contenido, EntradaImportada, Fuente, Importacion, Seccion
from .verificacion import Resultado, verificar_url, verificar_varias

ENTRADAS_POR_PAGINA = 100


def _parametros_sin_pagina(request):
    parametros = request.GET.copy()
    parametros.pop('pagina', None)
    return parametros.urlencode()


@requiere_permiso('ver_canales')
def inicio(request):
    form = ImportarListaForm()
    if request.method == 'POST':
        if not chequear_permiso(request.user, 'importar_canales'):
            raise PermissionDenied
        form = ImportarListaForm(request.POST, request.FILES)
        if form.is_valid():
            # Solo analiza (segundos). La verificación la va pidiendo la
            # pantalla de la importación, de a tandas.
            importacion = servicios.crear_importacion(
                form.texto, form.cleaned_data['archivo'].name, request.user, **form.opciones())
            return redirect(f'{importacion_url(importacion)}?empezar=1')

    return render(request, 'canales/inicio.html', {
        'form': form,
        'resumen': consultas.resumen(),
        'importaciones': consultas.ultimas_importaciones(),
        'puede_importar': chequear_permiso(request.user, 'importar_canales'),
    })


@requiere_permiso('importar_canales')
def traer_de_youtube(request):
    """
    Las películas de un canal oficial de YouTube: se leen sus videos (solo los
    datos) y se arma una importación como la de una lista, que se prueba y se
    carga en la misma pantalla.
    """
    form = TraerDeYoutubeForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        datos = form.cleaned_data
        try:
            listado = youtube.videos_del_canal(datos['url'])
        except youtube.NoSePudo as error:
            form.add_error('url', str(error))
        else:
            importacion = servicios.crear_importacion_de_youtube(
                listado, request.user, categoria=form.categoria(), serie=form.serie(),
                temporada=datos.get('temporada') or 1, seccion=form.seccion(),
                minimo_minutos=datos['minimo_minutos'], maximo_minutos=datos.get('maximo_minutos'),
                solo_espanol=datos['solo_espanol'])
            return redirect(f'{importacion_url(importacion)}?empezar=1')
    return render(request, 'canales/youtube.html', {'form': form, 'sugeridos': youtube.SUGERIDOS})


def importacion_url(importacion):
    return reverse('canales:importacion', args=[importacion.pk])


# ── Una importación ──────────────────────────────────────────────────

# (estado, cómo se llama la pestaña, su número en servicios.progreso), en el orden de las pestañas
PESTANIAS_DE_LA_IMPORTACION = [
    (EntradaImportada.Estado.APTA, 'Pasaron (falta cargar)', 'aptas'),
    (EntradaImportada.Estado.AGREGADA, 'Cargados', 'agregadas'),
    (EntradaImportada.Estado.RECHAZADA, 'No pasaron la prueba', 'rechazadas'),
    (EntradaImportada.Estado.CAIDA, 'No responden', 'caidas'),
    (EntradaImportada.Estado.DESCARTADA, 'Descartados', 'descartadas'),
    (EntradaImportada.Estado.REPETIDA, 'Ya estaban', 'repetidas'),
    (EntradaImportada.Estado.PENDIENTE, 'Por probar', 'pendientes'),
]


@requiere_permiso('ver_canales')
def importacion(request, pk):
    importacion = get_object_or_404(Importacion.objects.select_related('usuario'), pk=pk)
    filtros = {
        'texto': request.GET.get('q', '').strip(),
        'estado': request.GET.get('estado', ''),
        'causa': request.GET.get('causa', ''),
        'idioma': request.GET.get('idioma', ''),
        'contenido': request.GET.get('contenido', ''),
    }
    entradas = importacion.entradas.select_related('canal')
    if filtros['texto']:
        entradas = entradas.filter(Q(nombre__icontains=filtros['texto']) | Q(nombre_original__icontains=filtros['texto'])
                                   | Q(categoria__icontains=filtros['texto']))
    if filtros['estado'] in EntradaImportada.Estado.values:
        entradas = entradas.filter(estado=filtros['estado'])
    if filtros['causa'] in EntradaImportada.Causa.values:
        entradas = entradas.filter(estado=EntradaImportada.Estado.RECHAZADA, causa=filtros['causa'])
    if filtros['idioma'] == 'sin_dato':
        entradas = entradas.filter(idioma='')
    elif filtros['idioma'] in ('es', 'otro'):
        entradas = entradas.filter(idioma=filtros['idioma'])
    if filtros['contenido'] in EntradaImportada.Contenido.values:
        entradas = entradas.filter(contenido=filtros['contenido'])

    avance = servicios.progreso(importacion)
    # Las pestañas de arriba de la lista: qué pasó con cada uno, con cuántos hay (las vacías no se muestran).
    # Cambian solo el estado: la búsqueda, el idioma y el contenido elegidos se mantienen.
    sin_estado = request.GET.copy()
    for clave in ('estado', 'causa', 'pagina'):
        sin_estado.pop(clave, None)
    pestanias = [(estado, texto, avance[clave]) for estado, texto, clave in PESTANIAS_DE_LA_IMPORTACION
                 if avance[clave]]
    return render(request, 'canales/importacion.html', {
        'importacion': importacion,
        'avance': avance,
        'pestanias': pestanias,
        'sin_estado': sin_estado.urlencode(),
        # Elegir una causa es mirar dentro de "No pasaron la prueba"
        'estado_elegido': EntradaImportada.Estado.RECHAZADA if filtros['causa'] else filtros['estado'],
        'por_causa': servicios.por_causa(importacion),
        'pagina': Paginator(entradas, ENTRADAS_POR_PAGINA).get_page(request.GET.get('pagina')),
        'filtros': filtros,
        'hay_filtros': any(filtros.values()),
        'parametros': _parametros_sin_pagina(request),
        'causas': EntradaImportada.Causa.choices,
        'contenidos': EntradaImportada.Contenido.choices,
        'puede_importar': chequear_permiso(request.user, 'importar_canales'),
        'empezar': request.GET.get('empezar') == '1',
        'tamanio_lote': servicios.TAMANIO_LOTE,
    })


@require_POST
@requiere_permiso('importar_canales')
def importacion_lote(request, pk):
    """Prueba la próxima tanda y responde el avance (JSON). La pantalla la llama en bucle."""
    importacion = get_object_or_404(Importacion, pk=pk)
    verificar = partial(verificar_varias, a_fondo=True) if importacion.a_fondo else verificar_varias
    return JsonResponse(servicios.procesar_lote(importacion, verificar))


@require_POST
@requiere_permiso('importar_canales')
def importacion_cargar(request, pk):
    """Carga la próxima tanda de aptas y responde el avance (JSON). La pantalla la llama en bucle."""
    importacion = get_object_or_404(Importacion, pk=pk)
    return JsonResponse(servicios.cargar_lote(importacion))


@require_POST
@requiere_permiso('importar_canales')
def importacion_reintentar(request, pk):
    importacion = get_object_or_404(Importacion, pk=pk)
    cantidad = servicios.reintentar_caidas(importacion, request.user)
    if not cantidad:
        messages.info(request, 'No hay nada para volver a probar.')
        return redirect(importacion_url(importacion))
    return redirect(f'{importacion_url(importacion)}?empezar=1')


@require_POST
@requiere_permiso('importar_canales')
def importacion_borrar(request, pk):
    """Borra el informe. Los canales que se agregaron con esa lista quedan."""
    importacion = get_object_or_404(Importacion, pk=pk)
    importacion.delete()
    messages.success(request, f'Se borró el informe de "{importacion.archivo}". Los canales agregados siguen cargados.')
    return redirect('canales:inicio')


# ── Volver a verificar todas las fuentes, de a tandas ────────────────

@require_POST
@requiere_permiso('importar_canales')
def verificar_lote(request):
    try:
        desde = int(request.POST.get('desde', 0))
    except ValueError:
        desde = 0
    return JsonResponse(servicios.verificar_lote_de_fuentes(verificar_varias, desde, usuario=request.user))


# ── Catálogo ─────────────────────────────────────────────────────────

def _filtros_catalogo(datos):
    return {
        'texto': datos.get('q', '').strip(),
        'categoria': datos.get('categoria', ''),
        'idioma': datos.get('idioma', ''),
        'estado': datos.get('estado', ''),
        'sin_logo': datos.get('sin_logo') == '1',
        'origen': datos.get('origen', ''),
        'contenido': datos.get('contenido', ''),
    }


# El catálogo (datos técnicos) y la lista de Series eran pantallas aparte: ahora
# todo está en Organizar contenido. Sus direcciones viejas (links guardados,
# el panel en otra pestaña) llevan ahí con los mismos filtros.
_MOSTRAR_DEL_CATALOGO = {'en_app': 'app', 'fuera': 'caidos', 'quitados': 'quitados', 'incompleta': 'fuera'}


def _a_organizar(request, contenido):
    filtros = _filtros_catalogo(request.GET)
    parametros = {'contenido': contenido, 'q': filtros['texto'], 'idioma': filtros['idioma'],
                  'origen': filtros['origen'], 'categoria': filtros['categoria'],
                  'mostrar': _MOSTRAR_DEL_CATALOGO.get(filtros['estado'], ''), 'sin_logo': '1' if filtros['sin_logo'] else ''}
    return redirect(f"{reverse('canales:organizar')}?{urlencode({k: v for k, v in parametros.items() if v})}")


@requiere_permiso('ver_canales')
def catalogo(request):
    contenido = request.GET.get('contenido', '')
    return _a_organizar(request, contenido if secciones.es_valida(contenido) else Contenido.VIVO)


@requiere_permiso('ver_canales')
def series(request):
    return _a_organizar(request, Contenido.SERIE)


def como_en_la_app(request):
    """La vista vieja "Como en la app": ahora es parte de Organizar contenido."""
    return redirect(f"{reverse('canales:organizar')}?{request.GET.urlencode()}")


def _origenes_de(fuentes, importaciones):
    """
    Para la edición rápida: cada señal en el orden en que la prueba la app, de
    dónde salió (lista, canal de YouTube, a mano) y sus datos técnicos: cómo
    está, el códec, el error y cuándo se probó.
    """
    return [{'origen': f.origen or 'No se sabe', 'url': f.url, 'tipo': f.get_tipo_display(),
             'estado': f.get_estado_display(), 'caida': f.estado == Fuente.Estado.CAIDA,
             'codec': f.codec, 'error': f.error, 'activa': f.activa,
             'probada': date_format(localtime(f.verificada), 'j/m/Y H:i') if f.verificada else '',
             'importacion': importaciones.get(f.origen, '')} for f in fuentes]


def _preparar_para_editar(pagina, contenido):
    """Le pone a cada cosa de la página sus datos (JSON) para el cuadro de edición rápida."""
    importaciones = {archivo: reverse('canales:importacion', args=[pk])
                     for archivo, pk in Importacion.objects.order_by('creada').values_list('archivo', 'pk')}
    if contenido == Contenido.SERIE:
        por_capitulo = {}
        capitulos = [c.canal.pk for serie in pagina for c in serie.capitulos]
        for fuente in Fuente.objects.filter(canal_id__in=capitulos).order_by('prioridad', 'pk'):
            por_capitulo.setdefault(fuente.canal_id, []).append(fuente)
        for serie in pagina:
            fuentes, vistos = [], set()
            for capitulo in serie.capitulos:
                for fuente in por_capitulo.get(capitulo.canal.pk, []):
                    if fuente.origen not in vistos:   # una vez por origen (no una por capítulo)
                        vistos.add(fuente.origen)
                        fuentes.append(fuente)
            serie.activo = any(c.canal.activo for c in serie.capitulos)
            serie.datos = json.dumps({
                'tipo': 'serie', 'nombre': serie.nombre, 'logo': serie.logo, 'portada': bool(serie.portada),
                'activo': serie.activo,
                'categoria': serie.categoria_id or 'ninguna', 'capitulos': serie.cantidad,
                'en_app': serie.completa, 'motivo': serie.por_que_no_se_ve,
                'fuentes': _origenes_de(fuentes, importaciones),
                'mas': f"{reverse('canales:serie_detalle')}?nombre={quote(serie.nombre)}",
            })
        return
    for canal in pagina:
        canal.no_se_ve = consultas.por_que_no_se_ve(canal)
        canal.datos = json.dumps({
            'tipo': 'canal', 'pk': canal.pk, 'nombre': canal.nombre, 'logo': canal.logo, 'numero': canal.numero,
            'categoria': canal.categoria_id or 'ninguna', 'contenido': canal.contenido, 'activo': canal.activo,
            'en_app': not canal.no_se_ve, 'motivo': canal.no_se_ve,
            'fuentes': _origenes_de(canal.fuentes.all(), importaciones),
            'mas': reverse('canales:canal_editar', args=[canal.pk]),
        })


@requiere_permiso('ver_canales')
def organizar_contenido(request):
    """
    Todas las herramientas en un lugar: a la izquierda el árbol de categorías
    (con subcategorías) y cuántos tiene cada una; a la derecha su contenido,
    para editar uno (nombre, logo, categoría, tipo, de dónde salió) o muchos
    (mover, cambiar el tipo, quitar, eliminar). Ver consultas.organizar_contenido.
    """
    contenido = request.GET.get('contenido', '')
    if not secciones.es_valida(contenido):
        contenido = Contenido.VIVO
    filtros = {
        'texto': request.GET.get('q', '').strip(),
        'mostrar': request.GET.get('mostrar') if request.GET.get('mostrar') in consultas.MOSTRAR else 'todo',
        'origen': request.GET.get('origen', ''),
        'sin_logo': request.GET.get('sin_logo') == '1',
        'idioma': request.GET.get('idioma') if request.GET.get('idioma') in ('es', 'otro', 'sin_dato') else '',
    }
    datos = consultas.organizar_contenido(contenido, categoria=request.GET.get('categoria', ''),
                                          pagina=request.GET.get('pagina'), **filtros)
    _preparar_para_editar(datos.pagina, contenido)
    nodo = next((n for n in datos.nodos if n['clave'] == datos.elegida), None)
    categorias = list(organizar.categorias_con_cantidades(contenido))
    # Los filtros de ahora, para los links del árbol (que cambian solo la categoría)
    base = request.GET.copy()
    for clave in ('categoria', 'pagina'):
        base.pop(clave, None)
    base['contenido'] = contenido
    puede_editar = chequear_permiso(request.user, 'importar_canales')
    return render(request, 'canales/organizar.html', {
        'contenido': contenido,
        'datos': datos,
        'nodo': nodo,
        'filtros': filtros,
        'hay_filtros': bool(filtros['texto'] or filtros['mostrar'] != 'todo' or filtros['origen']
                            or filtros['sin_logo'] or filtros['idioma']),
        'que_mostrar': consultas.MOSTRAR.items(),
        'origenes': consultas.origenes(contenido),
        'categorias': categorias,
        'parecidas': organizar.categorias_parecidas([c for c in categorias if c.total]),
        'seccion': organizar.nombre_de_seccion(contenido),
        # La sección nueva que se está viendo (para cambiarla o borrarla) y todas, para las pestañas y "Pasar a…"
        'seccion_nueva': Seccion.objects.filter(clave=contenido).first(),
        'forma': secciones.forma(contenido),
        'secciones_nuevas': secciones.nuevas(),
        'formas': Seccion.Forma.choices,
        'iconos': Seccion.Icono.choices,
        'parametros': _parametros_sin_pagina(request),
        'base': base.urlencode(),
        'puede_editar': puede_editar,
        # El cuadro "Exportar": todas las secciones con sus categorías, la que se está viendo y los filtros
        'para_exportar': exportar.para_elegir() if puede_editar else [],
        'exportar_elegida': f'ninguna:{contenido}' if datos.elegida == 'ninguna' else datos.elegida,
        'descripcion_filtros': _descripcion_de_filtros(filtros),
    })


def _descripcion_de_filtros(filtros):
    """'busca «arr» · Solo lo que ve la app · en español' (para el cuadro Exportar)."""
    partes = []
    if filtros['texto']:
        partes.append(f'busca «{filtros["texto"]}»')
    if filtros['mostrar'] != 'todo':
        partes.append(consultas.MOSTRAR[filtros['mostrar']])
    if filtros['idioma']:
        idiomas = {'es': 'en español', 'otro': 'en otro idioma', 'sin_dato': 'idioma: no se sabe'}
        partes.append(idiomas[filtros['idioma']])
    if filtros['origen']:
        partes.append(f'de «{filtros["origen"]}»')
    if filtros['sin_logo']:
        partes.append('sin imagen')
    return ' · '.join(partes)


@require_POST
@requiere_permiso('importar_canales')
def organizar_editar(request):
    """La edición rápida de una cosa (o de una serie entera) desde Organizar contenido."""
    form = EditarDesdeOrganizarForm(request.POST)
    if not form.is_valid():
        errores = '; '.join(f'{campo}: {" ".join(lista)}' for campo, lista in form.errors.items())
        messages.error(request, f'No se guardó: {errores}')
        return redirect(_volver(request))
    datos = form.cleaned_data
    if request.FILES.get('imagen'):
        # Una imagen subida desde la compu gana sobre el link
        try:
            datos['logo'] = imagenes.guardar_subida(request.FILES['imagen'], request)
        except imagenes.ImagenInvalida as error:
            messages.error(request, f'No se guardó: {error}')
            return redirect(_volver(request))
    try:
        if request.POST.get('tipo') == 'serie':
            categoria = _categoria_elegida(request, Contenido.SERIE)
            nombre = request.POST.get('serie', '')
            cambios = organizar.editar_serie(nombre, request.user, nombre=datos['nombre'], logo=datos['logo'],
                                             categoria=categoria, activo=datos['activo'])
            titulo = datos['nombre'] or nombre
        else:
            canal = get_object_or_404(Canal, pk=request.POST.get('canal', '0'))
            categoria = _categoria_elegida(request, datos['contenido'] or canal.contenido)
            extra = {'contenido': datos['contenido']} if datos['contenido'] else {}
            cambios = organizar.editar_canal(canal, request.user, nombre=datos['nombre'], logo=datos['logo'],
                                             categoria=categoria, activo=datos['activo'],
                                             numero=datos['numero'].strip(), **extra)
            titulo = canal.nombre
    except organizar.NoSePuede as error:
        messages.error(request, str(error))
        return redirect(_volver(request))
    messages.success(request, f'Se guardó "{titulo}".' if cambios else f'"{titulo}" no tenía cambios.')
    return redirect(_volver(request))


@require_POST
@requiere_permiso('importar_canales')
def organizar_eliminar(request):
    """Elimina lo elegido (canales/películas/capítulos, o series enteras)."""
    if request.POST.getlist('serie'):
        canales = organizar.capitulos_de(request.POST.getlist('serie'))
        for nombre in request.POST.getlist('serie'):
            imagenes.poner_portada(nombre, '')
    else:
        canales = _canales_elegidos(request)
    cantidad = organizar.eliminar_contenido(canales, request.user)
    messages.success(request, f'Se eliminaron {cantidad}.' if cantidad else 'No había nada elegido.')
    return redirect(_volver(request))


def _eleccion_para_exportar(request):
    """Lo que se eligió en el cuadro "Exportar" de Organizar (ver exportar.Eleccion)."""
    datos = request.POST
    eleccion = exportar.Eleccion(solo_las_que_andan=datos.get('solo_las_que_andan') == '1')
    if datos.get('que') == 'elegido':
        eleccion.canales = [pk for pk in datos.getlist('canal') if pk.isdigit()]
        eleccion.series = [nombre for nombre in datos.getlist('serie') if nombre.strip()]
    else:
        validas = {clave for clave, _ in secciones.todas()}
        eleccion.secciones = [clave for clave in datos.getlist('seccion') if clave in validas]
        for valor in datos.getlist('categoria'):
            if valor.isdigit():
                eleccion.categorias.append(int(valor))
            elif valor.startswith('ninguna:') and valor[len('ninguna:'):] in validas:
                eleccion.sin_categoria.append(valor[len('ninguna:'):])
    if datos.get('con_filtros') == '1':
        eleccion.filtros = {
            'texto': datos.get('q', '').strip(),
            'mostrar': datos.get('mostrar') if datos.get('mostrar') in consultas.MOSTRAR else '',
            'origen': datos.get('origen', ''),
            'sin_logo': datos.get('sin_logo') == '1',
            'idioma': datos.get('idioma') if datos.get('idioma') in ('es', 'otro', 'sin_dato') else '',
        }
    return eleccion


def _nombre_de_la_exportacion(eleccion, nombres_de_secciones):
    if eleccion.canales or eleccion.series:
        parte = 'eleccion'
    elif eleccion.categorias or eleccion.sin_categoria:
        parte = 'categorias'
    elif set(eleccion.secciones) == set(nombres_de_secciones):
        parte = 'todo'
    else:
        parte = '-'.join(slugify(nombres_de_secciones[clave]) for clave in eleccion.secciones)
    return f'kairos-tv-{parte}-{localtime():%Y-%m-%d}'


@require_POST
@requiere_permiso('importar_canales')
def organizar_exportar(request):
    """Baja lo elegido como lista M3U8 o planilla de Excel (ver exportar.py)."""
    eleccion = _eleccion_para_exportar(request)
    if eleccion.vacia:
        messages.warning(request, 'Elegí qué exportar: una sección, una categoría o tarjetas de la página.')
        return redirect(_volver(request))
    resultado = exportar.elegir(eleccion)
    if not resultado.canales:
        motivo = ': lo que había es de YouTube o no tiene señales que anden' if resultado.sin_senales else ''
        messages.warning(request, f'No hay nada para exportar con esa elección{motivo}.')
        return redirect(_volver(request))
    nombre = _nombre_de_la_exportacion(eleccion, resultado.nombres_de_secciones)
    if request.POST.get('formato') == 'excel':
        archivo, tipo, extension = exportar.planilla_excel(resultado), TIPO_XLSX, 'xlsx'
    else:
        archivo, tipo, extension = exportar.lista_m3u(resultado).encode(), 'audio/x-mpegurl; charset=utf-8', 'm3u8'
    registrar(request.user, Accion.OTRO,
              f'Exportó {len(resultado.canales)} canales, películas o capítulos ({resultado.cantidad_de_senales} '
              f'señales) como {"Excel" if extension == "xlsx" else "lista M3U8"}.', modulo='canales')
    return HttpResponse(archivo, content_type=tipo,
                        headers={'Content-Disposition': f'attachment; filename="{nombre}.{extension}"'})


@requiere_permiso('ver_canales')
def serie_detalle(request):
    nombre = request.GET.get('nombre', '').strip()
    if not nombre:
        raise Http404('Falta el nombre de la serie.')

    serie = next(
        (item for item in consultas.series(texto=nombre) if item.nombre.casefold() == nombre.casefold()),
        None,
    )
    if serie is None:
        raise Http404('No se encontró la serie.')

    serie.temporadas_ordenadas = []
    for numero in serie.numeros_de_temporada:
        capitulos = serie.temporadas[numero]
        for capitulo in capitulos:
            capitulo.no_se_ve = consultas.por_que_no_se_ve(capitulo.canal)
        serie.temporadas_ordenadas.append((numero, capitulos))

    return render(request, 'canales/serie_detalle.html', {
        'serie': serie,
        'puede_editar': chequear_permiso(request.user, 'importar_canales'),
    })


def _canales_elegidos(request):
    """Los canales marcados, o todos los que coinciden con el filtro (si se pidió "todos")."""
    if request.POST.get('todos_del_filtro') == '1':
        pks = consultas.catalogo(**_filtros_catalogo(request.POST)).values_list('pk', flat=True)
    else:
        pks = [pk for pk in request.POST.getlist('canal') if pk.isdigit()]
    return Canal.objects.filter(pk__in=list(pks))


def _volver(request, contenido=Contenido.VIVO):
    """A dónde volver (la misma página y filtros de antes). Solo direcciones de este sitio."""
    volver = request.POST.get('volver') or request.GET.get('volver') or ''
    if not url_has_allowed_host_and_scheme(volver, allowed_hosts={request.get_host()}):
        volver = f"{reverse('canales:organizar')}?contenido={contenido}"
    return volver


def _volver_al_catalogo(request):
    return redirect(_volver(request))


@require_POST
@requiere_permiso('importar_canales')
def catalogo_quitar(request):
    form = QuitarCanalesForm(request.POST)
    motivo = form.cleaned_data['motivo'] if form.is_valid() else ''
    cantidad = servicios.quitar_canales(_canales_elegidos(request), motivo, request.user)
    if cantidad:
        messages.success(request, f'Se quitaron {cantidad} canal(es) de la app.')
    else:
        messages.info(request, 'No se quitó ningún canal (no había ninguno elegido, o ya estaban quitados).')
    return _volver_al_catalogo(request)


@require_POST
@requiere_permiso('importar_canales')
def catalogo_mostrar(request):
    cantidad = servicios.mostrar_canales(_canales_elegidos(request), request.user)
    if cantidad:
        messages.success(request, f'{cantidad} canal(es) vuelven a la app (si tienen alguna fuente que ande).')
    else:
        messages.info(request, 'No había ningún canal quitado entre los elegidos.')
    return _volver_al_catalogo(request)


def _seccion_pedida(request):
    """De qué sección se está hablando (los formularios lo mandan en "seccion")."""
    seccion = request.POST.get('seccion') or request.GET.get('contenido') or ''
    return seccion if secciones.es_valida(seccion) else Contenido.VIVO


def _categoria_elegida(request, contenido=None):
    """
    La categoría de destino: una nueva (si se escribió; se crea en `contenido`,
    o en la sección que mandó el formulario) o una de la lista. None = sin categoría.
    """
    nueva = request.POST.get('nueva_categoria', '').strip()
    if nueva:
        return organizar.categoria_por_nombre(nueva, contenido or _seccion_pedida(request), usuario=request.user)
    elegida = request.POST.get('categoria', '')
    if elegida == 'ninguna':
        return None
    if not elegida.isdigit():
        raise organizar.NoSePuede('Elegí una categoría o escribí una nueva.')
    return get_object_or_404(Categoria, pk=elegida)


@require_POST
@requiere_permiso('importar_canales')
def catalogo_categoria(request):
    """Mueve lo elegido a otra categoría (o a una nueva)."""
    try:
        categoria = _categoria_elegida(request)
    except organizar.NoSePuede as error:
        messages.error(request, str(error))
        return _volver_al_catalogo(request)
    cantidad = organizar.mover_a_categoria(_canales_elegidos(request), categoria, request.user)
    messages.success(request, f'Se movieron {cantidad} a "{categoria or "Sin categoría"}".' if cantidad
                     else 'No se movió nada (ya estaban en esa categoría, o no había ninguno elegido).')
    return _volver_al_catalogo(request)


def _avisar_cambio_de_tipo(request, cantidad, contenido, nombre_serie=''):
    if not cantidad:
        messages.info(request, 'No había ninguno elegido.')
        return
    if contenido == Contenido.SERIE and nombre_serie:
        messages.success(request, f'Listo: {cantidad} quedaron como capítulos de la serie "{nombre_serie}" '
                                  f'(los ves en la sección Series).')
        return
    messages.success(request, f'{cantidad} pasaron a la sección {secciones.nombre(contenido)}.')


@require_POST
@requiere_permiso('importar_canales')
def catalogo_contenido(request):
    """Cambia el tipo de lo elegido: en vivo, película o serie (con nombre de serie: los numera)."""
    contenido = request.POST.get('contenido', '')
    try:
        temporada = max(1, min(int(request.POST.get('temporada') or 1), 99))
    except ValueError:
        messages.error(request, 'La temporada tiene que ser un número.')
        return _volver_al_catalogo(request)
    nombre_serie = request.POST.get('nombre_serie', '').strip()
    try:
        cantidad = organizar.cambiar_contenido(_canales_elegidos(request), contenido, nombre_serie, temporada,
                                               request.user)
    except organizar.NoSePuede as error:
        messages.error(request, str(error))
        return _volver_al_catalogo(request)
    _avisar_cambio_de_tipo(request, cantidad, contenido, nombre_serie)
    return _volver_al_catalogo(request)


@require_POST
@requiere_permiso('importar_canales')
def series_acciones(request):
    """Sobre series enteras (todos sus capítulos): moverlas de categoría o pasarlas a películas."""
    capitulos = organizar.capitulos_de(request.POST.getlist('serie'))
    try:
        if request.POST.get('accion') == 'mover':
            categoria = _categoria_elegida(request, Contenido.SERIE)
            cantidad = organizar.mover_a_categoria(capitulos, categoria, request.user)
            messages.success(request, f'Se movieron {cantidad} capítulo(s) a "{categoria or "Sin categoría"}".'
                             if cantidad else 'No se movió nada (ya estaban en esa categoría).')
        elif request.POST.get('accion') == 'a_peliculas':
            cantidad = organizar.cambiar_contenido(capitulos, Contenido.PELICULA, usuario=request.user)
            _avisar_cambio_de_tipo(request, cantidad, Contenido.PELICULA)
        elif request.POST.get('accion') == 'unir':
            nombre_serie = request.POST.get('nombre_serie', '').strip()
            try:
                temporada = max(1, min(int(request.POST.get('temporada') or 1), 99))
            except ValueError:
                temporada = 1
            cantidad = organizar.unir_en_una_serie(request.POST.getlist('serie'), nombre_serie, temporada,
                                                   request.user)
            _avisar_cambio_de_tipo(request, cantidad, Contenido.SERIE, nombre_serie)
        elif request.POST.get('accion') == 'quitar':
            cantidad = servicios.quitar_canales(capitulos, request.POST.get('motivo', ''), request.user)
            messages.success(request, f'Se quitaron de la app {cantidad} capítulo(s).' if cantidad
                             else 'Ya estaban quitadas.')
        elif request.POST.get('accion') == 'mostrar':
            cantidad = servicios.mostrar_canales(capitulos, request.user)
            messages.success(request, f'{cantidad} capítulo(s) vuelven a la app.' if cantidad
                             else 'No había ninguna quitada.')
    except organizar.NoSePuede as error:
        messages.error(request, str(error))
    return redirect(_volver(request, Contenido.SERIE))


# ── Categorías ───────────────────────────────────────────────────────

def _accion_de_categorias(request):
    """Hace lo que se pidió con las categorías y devuelve el mensaje (o lanza NoSePuede)."""
    accion = request.POST.get('accion', '')
    if accion == 'crear':
        contenido = _seccion_pedida(request)
        categoria = organizar.crear_categoria(request.POST.get('nombre', ''), contenido, request.user)
        return (f'Se creó la categoría "{categoria}" en {organizar.nombre_de_seccion(contenido)}. Para llenarla, '
                f'elegí cosas y usá "Mover a…", o importá directo en ella.')
    if accion == 'renombrar':
        categoria = get_object_or_404(Categoria, pk=request.POST.get('categoria', '0'))
        viejo = categoria.nombre
        final = organizar.renombrar_categoria(categoria, request.POST.get('nombre', ''), request.user)
        return f'"{viejo}" ahora se llama "{final}".' if final.pk == categoria.pk else f'Ya existía "{final}": se juntaron.'
    if accion == 'juntar':
        elegidas = list(Categoria.objects.filter(
            pk__in=[pk for pk in request.POST.getlist('elegida') if pk.isdigit()]))
        destino = request.POST.get('destino', '').strip()
        if not destino and request.POST.get('destino_pk', '').isdigit():
            destino = get_object_or_404(Categoria, pk=request.POST['destino_pk']).nombre
        juntadas = [c.nombre for c in elegidas if c.nombre != destino]
        final = organizar.juntar_categorias(elegidas, destino, request.user)
        return (f'Listo: {", ".join(juntadas)} ya no existen y todo su contenido está en "{final}". Si una lista '
                f'nueva trae esos nombres, también va a "{final}".')
    if accion == 'borrar':
        categoria = get_object_or_404(Categoria, pk=request.POST.get('categoria', '0'))
        con_contenido = request.POST.get('con_contenido') == '1'
        cantidad = organizar.borrar_categoria(categoria, request.user, con_contenido=con_contenido)
        if con_contenido:
            return f'Se borró "{categoria}" con todo su contenido ({cantidad} eliminados).'
        return f'Se borró "{categoria}"' + (f' y {cantidad} quedaron sin categoría.' if cantidad else '.')
    if accion == 'ordenar':
        ordenes = {int(clave[6:]): int(valor or 0) for clave, valor in request.POST.items()
                   if clave.startswith('orden_') and clave[6:].isdigit() and (valor or '0').isdigit()}
        cantidad = organizar.ordenar_categorias(ordenes, request.user)
        return f'Se guardó el orden ({cantidad} cambiaron).' if cantidad else 'El orden ya estaba así.'
    raise organizar.NoSePuede('No se entendió qué hacer.')


@requiere_permiso('importar_canales')
def categorias(request):
    """Crear, renombrar, juntar, borrar y ordenar las categorías (los formularios están en Organizar contenido)."""
    if request.method == 'POST':
        try:
            messages.success(request, _accion_de_categorias(request))
        except organizar.NoSePuede as error:
            messages.error(request, str(error))
        volver = request.POST.get('volver') or ''
        if not url_has_allowed_host_and_scheme(volver, allowed_hosts={request.get_host()}):
            volver = reverse('canales:categorias')
        return redirect(volver)

    return redirect('canales:organizar')


# ── Secciones nuevas de la app (Música, Radio...) ────────────────────

@require_POST
@requiere_permiso('importar_canales')
def secciones_acciones(request):
    """Crear, cambiar (nombre, ícono, orden) o borrar una sección nueva. Ver canales/secciones.py."""
    accion = request.POST.get('accion', '')
    volver = reverse('canales:organizar')
    try:
        if accion == 'crear':
            seccion = secciones.crear(request.POST.get('nombre', ''), request.POST.get('forma', ''),
                                      request.POST.get('icono', ''), request.user)
            messages.success(request, f'Se creó la sección "{seccion}". Ahora creale categorías (a la izquierda) e '
                                      f'importá en ella. En la app aparece en el menú (versión 1.2.11 o más nueva) '
                                      f'cuando tenga algo que se pueda ver.')
            volver += f'?contenido={seccion.clave}'
        elif accion in ('editar', 'borrar'):
            seccion = get_object_or_404(Seccion, pk=request.POST.get('seccion_pk', '0'))
            if accion == 'editar':
                secciones.editar(seccion, request.POST.get('nombre', ''), request.POST.get('icono', ''),
                                 request.POST.get('orden') or 0, request.user)
                messages.success(request, f'Se guardó la sección "{seccion}".')
                volver += f'?contenido={seccion.clave}'
            else:
                con_contenido = request.POST.get('con_contenido') == '1'
                cantidad = secciones.borrar(seccion, request.user, con_contenido=con_contenido)
                messages.success(request, f'Se borró la sección "{seccion}"' +
                                 (f' con todo lo que tenía ({cantidad}).' if cantidad else '.'))
        else:
            raise secciones.NoSePuede('No se entendió qué hacer.')
    except (secciones.NoSePuede, ValueError) as error:
        messages.error(request, str(error) if isinstance(error, secciones.NoSePuede)
                       else 'El orden tiene que ser un número.')
        actual = request.POST.get('volver') or ''
        if url_has_allowed_host_and_scheme(actual, allowed_hosts={request.get_host()}):
            volver = actual
    return redirect(volver)


# ── Editar un canal ──────────────────────────────────────────────────

@requiere_permiso('importar_canales')
def canal_editar(request, pk):
    canal = get_object_or_404(Canal.objects.select_related('categoria'), pk=pk)
    logo_viejo = canal.logo
    form = CanalForm(request.POST or None, request.FILES or None, instance=canal)
    fuentes = FuentesFormSet(request.POST or None, queryset=canal.fuentes.all(), prefix='fuentes')
    if request.method == 'POST' and form.is_valid() and fuentes.is_valid() and _subir_logo(request, form):
        canal, nueva = servicios.guardar_canal(form, fuentes, request.user, verificar_url)
        if canal.logo != logo_viejo:
            imagenes.soltar(logo_viejo)   # si era una subida y nadie más la usa, se borra
        messages.success(request, f'Se guardó "{canal.nombre}".')
        volver = _volver(request, canal.contenido)
        if nueva is not None:
            if nueva.estado == nueva.Estado.CAIDA:
                messages.warning(request, f'La fuente nueva se agregó, pero no funciona: {nueva.error}')
            else:
                messages.success(request, f'Fuente nueva agregada ({nueva.get_tipo_display()}, '
                                          f'{nueva.get_estado_display().lower()}).')
        return redirect(volver)
    return render(request, 'canales/editar.html', {
        'canal': canal,
        'form': form,
        'fuentes': fuentes,
        'volver': _volver(request, canal.contenido),
    })


def _subir_logo(request, form):
    """Si se subió una imagen, la guarda y la deja como logo. False si no sirve (el error queda en el form)."""
    archivo = form.cleaned_data.get('imagen')
    if not archivo:
        return True
    try:
        form.instance.logo = imagenes.guardar_subida(archivo, request)
    except imagenes.ImagenInvalida as error:
        form.add_error('imagen', str(error))
        return False
    return True


# ── Probar un link y agregarlo a mano ────────────────────────────────

@requiere_permiso('importar_canales')
def probar(request):
    """
    Paso 1: se pega una dirección y se prueba (igual que al importar: formato
    real, como la app y como VLC, YouTube y páginas con yt-dlp).
    Paso 2: si anda (o si se quiere agregar igual), se completan nombre,
    logo, categoría... y se crea el canal.
    """
    prueba = ProbarLinkForm(request.POST if request.POST.get('paso') == 'probar' else None)
    resultado = canal_form = None
    motivo = ''
    ya_cargada = None

    if request.POST.get('paso') == 'agregar':
        prueba = ProbarLinkForm(request.POST)
        if prueba.is_valid():
            datos = prueba.cleaned_data
            resultado = Resultado(estado=request.POST.get('estado', Fuente.Estado.SIN_VERIFICAR),
                                  error=request.POST.get('error', '')[:200], tipo=request.POST.get('tipo', ''),
                                  user_agent=request.POST.get('ua_que_anduvo', '')[:300])
            canal_form = CanalNuevoForm(request.POST)
            if canal_form.is_valid():
                canal = servicios.crear_canal_a_mano(canal_form, datos['url'], resultado, datos['user_agent'],
                                                     datos['referer'], request.user)
                messages.success(request, f'Se agregó "{canal.nombre}".')
                return redirect(reverse('canales:canal_editar', args=[canal.pk]))
    elif prueba.is_bound and prueba.is_valid():
        datos = prueba.cleaned_data
        ya_cargada = Fuente.objects.filter(url=datos['url'], canal__eliminado_en__isnull=True).select_related('canal').first()
        resultado = verificar_url(datos['url'], formato(datos['url']) or 'hls', datos['user_agent'], datos['referer'],
                                  a_fondo=True)
        causa, motivo = servicios.juzgar(resultado, Importacion(solo_espanol=True))
        # Sugerencias para el canal: lo que dijo YouTube / la página, o lo que se deduce de la dirección
        nombre = limpiar_nombre(resultado.titulo) if resultado.titulo else ''
        idioma, pais = idioma_y_pais(nombre)
        canal_form = CanalNuevoForm(initial={'nombre': nombre, 'logo': resultado.imagen, 'idioma': idioma,
                                             'pais': pais, 'contenido': Contenido.VIVO})

    return render(request, 'canales/probar.html', {
        'prueba': prueba,
        'resultado': resultado,
        'canal_form': canal_form,
        'ya_cargada': ya_cargada,
        'tipo_texto': dict(Fuente.Tipo.choices).get(resultado.tipo, resultado.tipo) if resultado else '',
        'no_pasa': motivo if prueba.is_bound and resultado and resultado.estado != Fuente.Estado.CAIDA else '',
    })


@require_POST
@requiere_permiso('importar_canales')
def limpiar_nombres(request):
    renombrados, juntados = servicios.limpiar_nombres(request.user)
    if renombrados or juntados:
        messages.success(request, f'Listo: {renombrados} canal(es) renombrado(s) y {juntados} repetido(s) '
                                  f'juntado(s) con su canal (sus fuentes quedaron como alternativas).')
    else:
        messages.info(request, 'Los nombres ya estaban limpios.')
    return redirect('canales:inicio')


# ── Lo más visto ─────────────────────────────────────────────────────

_PESTANIAS_VISTO = [
    ('vivo', 'En vivo', 'bi-broadcast'),
    ('pelicula', 'Películas', 'bi-film'),
    ('serie', 'Series', 'bi-collection-play'),
]


@requiere_permiso('ver_estadisticas')
def lo_mas_visto(request):
    try:
        dias = int(request.GET.get('dias', 30))
    except ValueError:
        dias = 30
    if dias not in estadisticas.PERIODOS:
        dias = 30
    tipo = request.GET.get('tipo', 'vivo')
    if tipo not in Contenido.values:
        tipo = 'vivo'
    ranking = estadisticas.lo_mas_visto(dias)
    return render(request, 'canales/lo_mas_visto.html', {
        'dias': dias,
        'periodos': estadisticas.PERIODOS,
        'tipo': tipo,
        'pestanias': [(clave, nombre, icono, ranking.totales[clave]) for clave, nombre, icono in _PESTANIAS_VISTO],
        'filas': getattr(ranking, tipo),
        'total': ranking.totales[tipo],
        'puestos': estadisticas.PUESTOS,
        'puede_editar': chequear_permiso(request.user, 'importar_canales'),
    })
