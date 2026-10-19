"""
Pantallas de canales del panel:

  /canales/                         resumen, subir una lista, verificar todas (de a tandas) e importaciones anteriores
  /canales/importaciones/<id>/      la prueba de una lista: el avance, qué es apto, qué no y por qué, y cargar las aptas
  /canales/organizar/               TODO en un lugar: árbol de categorías (con subcategorías) y su contenido para
                                    editar, mover, cambiar el tipo, quitar o eliminar, de dónde salió cada cosa y
                                    los datos técnicos de cada señal (formato, códec, error, cuándo se probó)
  /canales/catalogo/ y /series/     las pantallas viejas: llevan a Organizar contenido con los mismos filtros
  /canales/series/detalle/          temporadas, capítulos, disponibilidad y fuentes de una serie; su categoría y
                                    nombre (series/editar/) y pasar capítulos de una temporada a otra (series/temporada/)
  /canales/canal/<id>/editar/       nombre, logo, categoría... de un canal, y sus fuentes
  /canales/fuentes/<id>/borrar/     borra UNA fuente (POST), desde Organizar o la página del canal
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
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
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
from core import trabajos
from herramientas.excel import TIPO_XLSX
from usuarios.decoradores import requiere_permiso
from usuarios.permisos import chequear_permiso

from . import consultas, estadisticas, exportar, imagenes, organizar, secciones, servicios, youtube
from .clasificar import formato, idioma_y_pais, limpiar_nombre
from .forms import (CanalForm, CanalNuevoForm, EditarDesdeOrganizarForm, FuentesFormSet, ImportarListaForm,
                    ProbarLinkForm, QuitarCanalesForm, TraerDeYoutubeForm)
from .models import (PROPORCION_PANTALLA_COMPLETA, Canal, Categoria, Contenido, EntradaImportada, Fuente, Importacion,
                     Seccion)
from .verificacion import NOMBRES_DE_CODECS, Resultado, verificar_url, verificar_varias

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
        # Varias listas de una (static/js/importar_varias.js): la página las sube de a una y espera JSON
        de_a_varias = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        if form.is_valid():
            # Solo analiza (segundos). Una lista grande ni eso: la pantalla de
            # la importación la lee de a tandas, y después se elige qué probar.
            # La verificación también la va pidiendo la pantalla, de a tandas.
            importacion = servicios.preparar_importacion(
                form.texto, form.cleaned_data['archivo'].name, request.user, **form.opciones())
            url = importacion_url(importacion) if importacion.por_leer else f'{importacion_url(importacion)}?empezar=1'
            if de_a_varias:
                return JsonResponse({'ok': True, 'url': url, 'total': importacion.total})
            return redirect(url)
        if de_a_varias:
            errores = [str(e) for campo in form.errors.values() for e in campo]
            return JsonResponse({'ok': False, 'error': ' '.join(errores) or 'No se pudo subir.'}, status=400)

    return render(request, 'canales/inicio.html', {
        'form': form,
        'resumen': consultas.resumen(),
        'importaciones': consultas.ultimas_importaciones(),
        'puede_importar': chequear_permiso(request.user, 'importar_canales'),
        # Mantenimiento: "Qué revisar" (una sección o una lista) y lo que dio "Limpiar nombres"
        'secciones_para_revisar': secciones.todas(),
        'origenes_para_revisar': consultas.origenes(),
        'resultado_limpieza': request.session.pop('resultado_limpieza', None),
    })


@requiere_permiso('importar_canales')
def traer_de_youtube(request):
    """
    Las películas de un canal oficial de YouTube: se leen sus videos (solo los
    datos) y se arma una importación como la de una lista, que se prueba y se
    carga en la misma pantalla.
    """
    inicial = {}
    if request.GET.get('serie'):
        # Desde la página de una serie ("Agregar capítulos"): ya va elegida, con su categoría y temporada
        existe, suya = organizar.categoria_de_la_serie(request.GET['serie'])
        temporada = request.GET.get('temporada', '')
        inicial = {'es_serie': True, 'nombre_serie': request.GET['serie'][:90], 'minimo_minutos': 5,
                   'temporada': int(temporada) if temporada.isdigit() and 0 < int(temporada) < 100 else 1,
                   'categoria_destino': suya.nombre if existe and suya else ''}
    form = TraerDeYoutubeForm(request.POST or None, initial=inicial)
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
                segun_titulo=bool(form.serie() and datos.get('segun_titulo')),
                minimo_minutos=datos['minimo_minutos'], maximo_minutos=datos.get('maximo_minutos'),
                solo_espanol=datos['solo_espanol'])
            return redirect(f'{importacion_url(importacion)}?empezar=1')
    return render(request, 'canales/youtube.html', {'form': form, 'sugeridos': youtube.SUGERIDOS,
                                                    'arbol_de_series': consultas.arbol_de_series()})


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
    if importacion.por_leer:
        # Una lista grande, todavía leyéndose: solo la barra de avance (la pantalla la va leyendo)
        return render(request, 'canales/importacion_leyendo.html', {
            'importacion': importacion, 'lectura': servicios.lectura(importacion),
            'puede_importar': chequear_permiso(request.user, 'importar_canales'),
        })
    # La parte con la que se trabaja (En vivo / Películas / Series, una categoría, lo buscado):
    # probar, cargar y descartar se hacen sobre ella
    seleccion = servicios.Seleccion.de(request.GET)
    filtros = {
        'texto': seleccion.texto,
        'estado': request.GET.get('estado', ''),
        'causa': request.GET.get('causa', ''),
        'idioma': request.GET.get('idioma', ''),
        'contenido': seleccion.contenido,
        'categoria': seleccion.categoria,
    }
    entradas = seleccion.aplicar(importacion.entradas.select_related('canal'))
    if filtros['estado'] in EntradaImportada.Estado.values:
        entradas = entradas.filter(estado=filtros['estado'])
    if filtros['causa'] in EntradaImportada.Causa.values:
        entradas = entradas.filter(estado=EntradaImportada.Estado.RECHAZADA, causa=filtros['causa'])
    if filtros['idioma'] == 'sin_dato':
        entradas = entradas.filter(idioma='')
    elif filtros['idioma'] in ('es', 'otro'):
        entradas = entradas.filter(idioma=filtros['idioma'])

    avance = servicios.progreso(importacion, seleccion)
    parte = avance['en_la_seleccion']
    # Las pestañas de arriba de la lista: qué pasó con cada uno, con cuántos hay. Las vacías no se muestran,
    # salvo "Pasaron": es la que se mira antes de cargar, y tiene que estar aunque todavía no se haya probado nada.
    # Cambian solo el estado: la búsqueda, el idioma y el contenido elegidos se mantienen.
    sin_estado = request.GET.copy()
    for clave in ('estado', 'causa', 'pagina'):
        sin_estado.pop(clave, None)
    pestanias = [(estado, texto, parte[clave]) for estado, texto, clave in PESTANIAS_DE_LA_IMPORTACION
                 if parte[clave] or estado == EntradaImportada.Estado.APTA]
    por_contenido = servicios.por_contenido(importacion)
    # De la parte elegida, sus categorías (con una sola parte, como una lista de canales, directo esas)
    de_las_categorias = seleccion.contenido or (por_contenido[0][0] if len(por_contenido) == 1 else '')
    pagina = Paginator(entradas, ENTRADAS_POR_PAGINA).get_page(request.GET.get('pagina'))
    se_pueden_elegir = [EntradaImportada.Estado.APTA, *servicios.SE_PUEDEN_CARGAR_IGUAL]
    puede_importar = chequear_permiso(request.user, 'importar_canales')
    return render(request, 'canales/importacion.html', {
        **(_donde_va(importacion, seleccion) if puede_importar and seleccion.contenido else {}),
        'importacion': importacion,
        'avance': avance,
        'parte': parte,
        'seleccion': seleccion,
        'datos_de_la_seleccion': urlencode(seleccion.como_datos()),
        'que_es': servicios.que_es(seleccion),
        'por_contenido': por_contenido,
        'categorias': servicios.categorias_de(importacion, de_las_categorias) if de_las_categorias else [],
        'contenido_de_las_categorias': de_las_categorias,
        'nombre_de_la_parte': secciones.nombre(de_las_categorias) if de_las_categorias else '',
        'sin_categoria': servicios.SIN_CATEGORIA,
        'pestanias': pestanias,
        'sin_estado': sin_estado.urlencode(),
        # Elegir una causa es mirar dentro de "No pasaron la prueba"
        'estado_elegido': EntradaImportada.Estado.RECHAZADA if filtros['causa'] else filtros['estado'],
        'por_causa': servicios.por_causa(importacion),
        'pagina': pagina,
        # Lo que se puede cambiar a mano antes de cargar ("No cargar" / "Cargar igual")
        'se_pueden_elegir': se_pueden_elegir,
        'se_pueden_cargar_igual': servicios.SE_PUEDEN_CARGAR_IGUAL,
        'hay_para_elegir': any(e.estado in se_pueden_elegir for e in pagina),
        'filtros': filtros,
        'hay_filtros': any(filtros.values()),
        'parametros': _parametros_sin_pagina(request),
        'causas': EntradaImportada.Causa.choices,
        'contenidos': EntradaImportada.Contenido.choices,
        'puede_importar': puede_importar,
        'empezar': request.GET.get('empezar') == '1',
        'tamanio_lote': servicios.TAMANIO_LOTE,
        'falta_probar': servicios.falta_probar(importacion, seleccion),
    })


def _donde_va(importacion, seleccion):
    """Para el paso "¿Dónde va?": adónde iría hoy, y las categorías (y series) del panel para elegir."""
    arbol = consultas.arbol_de_series() if seleccion.contenido == Contenido.SERIE else None
    series_del_panel = ({s['nombre'].lower() for c in arbol['categorias'] for s in c['series']}
                        if arbol else None)
    return {
        'como_va': servicios.como_va(importacion, seleccion, series_del_panel),
        'categorias_del_panel': Categoria.objects.filter(contenido=seleccion.contenido).order_by('nombre'),
        'arbol_de_series': arbol,
        # "Recordarlo" solo tiene sentido con una categoría entera de la lista (no lo buscado)
        'se_puede_recordar': (seleccion.categoria and seleccion.categoria != servicios.SIN_CATEGORIA
                              and not seleccion.texto),
    }


@require_POST
@requiere_permiso('importar_canales')
def importacion_destino(request, pk):
    """¿Dónde va?: la categoría (y en Series, la serie) de lo elegido que falta cargar."""
    importacion = get_object_or_404(Importacion, pk=pk)
    seleccion = servicios.Seleccion.de(request.POST)
    categoria = request.POST.get('categoria_nueva', '') if request.POST.get('destino_categoria') == '+nueva' \
        else request.POST.get('destino_categoria', '')
    serie = request.POST.get('serie_nueva', '') if request.POST.get('destino_serie') == '+nueva' \
        else request.POST.get('destino_serie', '')
    temporada = request.POST.get('temporada', '').strip()
    try:
        cantidad, quedo, recordado = servicios.ubicar(
            importacion, seleccion, categoria=categoria, serie=serie,
            temporada=int(temporada) if temporada.isdigit() else None,
            recordar=request.POST.get('recordar') == 'on', usuario=request.user)
    except organizar.NoSePuede as error:
        messages.error(request, str(error))
        return redirect(f'{importacion_url(importacion)}?{urlencode(seleccion.como_datos())}#donde-va')
    destino = ' › '.join(p for p in (quedo.categoria, quedo.texto if serie else '')
                         if p and p != servicios.SIN_CATEGORIA)
    texto = f'Listo: {cantidad:,} van a «{destino}». Entran ahí cuando los cargues.'.replace(',', '.')
    if recordado:
        texto += f' La próxima lista que traiga «{seleccion.categoria}» también va a «{quedo.categoria}».'
    messages.success(request, texto)
    return redirect(f'{importacion_url(importacion)}?{urlencode(quedo.como_datos())}#trabajo')


@require_POST
@requiere_permiso('importar_canales')
def importacion_leer(request, pk):
    """Lee la próxima tanda de una lista grande y responde cuánto va (JSON). La pantalla la llama en bucle."""
    importacion = get_object_or_404(Importacion, pk=pk)
    clave = f'importacion:{importacion.pk}'
    esperar = _esperar_turno(clave, f'Leyendo la lista «{importacion.archivo}»', request,
                             importacion_url(importacion), servicios.lectura(importacion))
    if esperar:
        return esperar
    lectura = servicios.leer_lote(importacion)
    if lectura['terminada']:
        trabajos.terminar(clave)
    else:
        trabajos.avance(clave, lectura['porcentaje'],
                        f'{lectura["leidas"]:,} de {lectura["total"]:,} leídos'.replace(',', '.'))
    return JsonResponse(lectura)


@require_POST
@requiere_permiso('importar_canales')
def importacion_descartar(request, pk):
    """No me interesa esta parte: lo de la selección que todavía no se cargó queda descartado."""
    importacion = get_object_or_404(Importacion, pk=pk)
    seleccion = servicios.Seleccion.de(request.POST)
    cantidad = servicios.descartar(importacion, seleccion, request.user)
    if cantidad:
        messages.success(request, f'Listo: {cantidad:,} de «{servicios.que_es(seleccion)}» quedaron descartados: '
                                  f'no se van a probar ni cargar. Si te arrepentís, están en «Descartados» y se '
                                  f'pueden «Cargar igual».'.replace(',', '.'))
    else:
        messages.info(request, 'No había nada para descartar acá.')
    return redirect(f'{importacion_url(importacion)}?{urlencode(seleccion.como_datos())}#trabajo')


def _esperar_turno(clave, titulo, request, url, avance):
    """
    Si hay OTRO trabajo pesado corriendo (core/trabajos.py), la respuesta
    para que la pantalla espere: "ocupada" (vuelve a pedir en unos segundos)
    y qué se está esperando. Si no, None (y queda anotado como en curso).
    """
    otro = trabajos.turno(clave, titulo, request.user, url)
    if otro is None:
        return None
    return JsonResponse({**avance, 'ocupada': True, 'esperando': otro.titulo})


@require_POST
@requiere_permiso('importar_canales')
def importacion_lote(request, pk):
    """Prueba la próxima tanda y responde el avance (JSON). La pantalla la llama en bucle."""
    importacion = get_object_or_404(Importacion, pk=pk)
    clave = f'importacion:{importacion.pk}'
    esperar = _esperar_turno(clave, f'Probando la lista «{importacion.archivo}»', request,
                             importacion_url(importacion), servicios.progreso(importacion))
    if esperar:
        return esperar
    verificar = partial(verificar_varias, a_fondo=importacion.a_fondo,
                        cancelado=partial(trabajos.cancelado, clave))
    avance = servicios.procesar_lote(importacion, verificar, seleccion=servicios.Seleccion.de(request.POST))
    if trabajos.cancelado(clave):
        avance['cancelada'] = True
    elif avance['terminada']:
        trabajos.terminar(clave)
    else:
        trabajos.avance(clave, avance['porcentaje'],
                        f'{avance["verificadas"]:,} de {avance["para_verificar"]:,} probados'.replace(',', '.'))
    return JsonResponse(avance)


@require_POST
@requiere_permiso('importar_canales')
def importacion_cancelar(request, pk):
    """Cancela la tanda en curso sin perder lo que ya se procesó."""
    importacion = get_object_or_404(Importacion, pk=pk)
    trabajos.cancelar(f'importacion:{importacion.pk}')
    return JsonResponse({'cancelada': True})


@require_POST
@requiere_permiso('importar_canales')
def importacion_cargar(request, pk):
    """Carga la próxima tanda de aptas y responde el avance (JSON). La pantalla la llama en bucle."""
    importacion = get_object_or_404(Importacion, pk=pk)
    clave = f'importacion:{importacion.pk}'
    esperar = _esperar_turno(clave, f'Cargando la lista «{importacion.archivo}»', request,
                             importacion_url(importacion), {**servicios.progreso(importacion), 'canales_nuevos': 0})
    if esperar:
        return esperar
    avance = servicios.cargar_lote(importacion, seleccion=servicios.Seleccion.de(request.POST))
    parte = avance['en_la_seleccion']
    if not parte['aptas'] or parte['pendientes'] > 0:
        trabajos.terminar(clave)
    else:
        hechas = parte['agregadas']
        trabajos.avance(clave, round(100 * hechas / max(1, hechas + parte['aptas'])),
                        f'{hechas:,} cargados, faltan {parte["aptas"]:,}'.replace(',', '.'))
    return JsonResponse(avance)


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
def importacion_elegir(request, pk):
    """Antes de cargar: "Cargar igual" lo que no pasó, o "No cargar" lo que pasó (las entradas marcadas)."""
    importacion = get_object_or_404(Importacion, pk=pk)
    entradas = [valor for valor in request.POST.getlist('entrada') if valor.isdigit()]
    accion = request.POST.get('accion')
    # El botón de una sola entrada ("Cargar igual" / "No cargar" en su ficha)
    for campo, de_una in (('cargar_una', 'cargar'), ('no_cargar_una', 'descartar')):
        if request.POST.get(campo, '').isdigit():
            entradas, accion = [request.POST[campo]], de_una
    if accion == 'cargar':
        cantidad = servicios.cargar_igual(importacion, entradas, request.user)
        texto = f'{cantidad} pasaron a «Pasaron»: entran con el próximo «Cargar».'
    else:
        cantidad = servicios.no_cargar(importacion, entradas, request.user)
        texto = f'{cantidad} pasaron a «Descartados»: no se van a cargar.'
    if cantidad:
        messages.success(request, texto)
    else:
        messages.info(request, 'No había nada elegido para cambiar.')
    volver = request.POST.get('volver', '')
    if not url_has_allowed_host_and_scheme(volver, allowed_hosts={request.get_host()}):
        volver = importacion_url(importacion)
    return redirect(volver)


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
    seccion, origen = _que_revisar(request.POST)
    clave = 'verificacion'
    titulo = f'Verificando {servicios.que_se_revisa(seccion, origen)}'[:150]
    otro = trabajos.turno(clave, titulo, request.user, reverse('canales:inicio'))
    if otro:
        # La pantalla espera y vuelve a pedir (la misma tanda: "siguiente" no avanza)
        return JsonResponse({**servicios.avance_de_la_verificacion(desde, seccion, origen), 'ocupada': True,
                             'esperando': otro.titulo})
    avance = servicios.verificar_lote_de_fuentes(verificar_varias, desde, usuario=request.user, seccion=seccion,
                                                 origen=origen)
    if avance['terminado']:
        trabajos.terminar(clave)
    else:
        trabajos.avance(clave, avance['porcentaje'],
                        f'{avance["verificadas"]:,} de {avance["total"]:,} fuentes'.replace(',', '.'))
    return JsonResponse(avance)


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


def _fecha(momento):
    return date_format(localtime(momento), 'j/m/Y H:i') if momento else ''


def _en_los_aparatos(fuente):
    """Cómo anda en los celulares y TV: 'se vio 3,5 h · se corta 2 veces por hora · imagen cuadrada (4:3)'."""
    partes = []
    if fuente.segundos_en_aparatos >= 60:
        horas = fuente.segundos_en_aparatos / 3600
        partes.append(f'se vio {horas:.1f} h'.replace('.', ',') if horas >= 1
                      else f'se vio {fuente.segundos_en_aparatos // 60} min')
        cortes = fuente.cortes_por_hora
        if cortes is not None:
            partes.append('no se corta' if not cortes else f'se corta {cortes:g} veces por hora'.replace('.', ','))
    if fuente.proporcion:
        partes.append('imagen cuadrada (4:3, con franjas negras)' if fuente.proporcion < PROPORCION_PANTALLA_COMPLETA
                      else 'imagen panorámica')
    return ' · '.join(partes)


def _aviso_de_codec(codec):
    """
    Si el video viene en un códec que no todos los aparatos leen: los que no
    lo leen no muestran esa señal (y si es la única, el canal no les aparece,
    aunque acá diga "se ve en la app").
    """
    if not codec or codec == 'h264':
        return ''
    return (f'Video {NOMBRES_DE_CODECS.get(codec, codec)}: los aparatos que no lo leen (muchas TV y TV box) no usan '
            f'esta señal. Si es la única, en esos aparatos el canal no aparece.')


def _origenes_de(fuentes, importaciones, borrables=True):
    """
    Para el detalle y la edición rápida: cada señal en el orden en que la
    prueba la app (`orden`), de dónde salió (lista, canal de YouTube, a mano),
    el link completo y sus datos técnicos: cómo está, calidad, códec, el
    error, cuándo se probó, cómo anda en los aparatos y si está oculta.
    `borrables`: se puede borrar de a una (en una serie no: cada origen junta
    las de muchos capítulos).
    """
    return [{'id': f.pk, 'orden': orden, 'origen': f.origen or 'No se sabe', 'url': f.url,
             'tipo': f.get_tipo_display(), 'estado': f.get_estado_display(), 'caida': f.estado == Fuente.Estado.CAIDA,
             'codec': f.codec, 'calidad': f.calidad, 'error': f.error, 'activa': f.activa,
             'probada': _fecha(f.verificada), 'aparatos': _en_los_aparatos(f),
             'oculta': (f'Oculta hasta el {_fecha(f.oculta_hasta)} (después vuelve sola): {f.falla_en_aparatos}'
                        if f.oculta_por_aparatos else ''),
             'aviso_codec': _aviso_de_codec(f.codec),
             'borrable': borrables,
             'importacion': importaciones.get(f.origen, '')} for orden, f in enumerate(fuentes, start=1)]


def _nombres_de_usuarios(pagina):
    """{pk: 'Nombre Apellido'} de quienes cargaron o cambiaron lo de la página (de una sola consulta)."""
    ids = {pk for canal in pagina for pk in (canal.creado_por_id, canal.modificado_por_id) if pk}
    return {u.pk: u.get_full_name() or u.username for u in get_user_model().objects.filter(pk__in=ids)}


def _datos_del_canal(canal, usuarios):
    """Todo lo que se sabe de un canal, película o capítulo, para el panel de detalles: [(qué, valor), ...]."""
    def con_quien(momento, pk):
        return f'{_fecha(momento)}' + (f' por {usuarios[pk]}' if pk in usuarios else '')
    filas = [
        ('Sección', secciones.nombre(canal.contenido)),
        ('Categoría', canal.categoria.nombre if canal.categoria else 'Sin categoría («Otros»)'),
        ('Número', canal.numero),
        ('Idioma', canal.get_idioma_display() if canal.idioma else 'No se sabe'),
        ('País', canal.pais),
        ('ID de guía (tvg-id)', canal.tvg_id),
        ('Cargado', con_quien(canal.creado, canal.creado_por_id)),
        ('Último cambio', con_quien(canal.modificado, canal.modificado_por_id)),
        ('Por qué se quitó', '' if canal.activo else canal.motivo_quitado or 'Quitado a mano.'),
    ]
    return [fila for fila in filas if fila[1]]


def _preparar_para_editar(pagina, contenido):
    """
    Le pone a cada cosa de la página sus datos (JSON) para el panel de
    detalles (organizar_detalle.js) y el cuadro de edición rápida.
    """
    importaciones = {archivo: reverse('canales:importacion', args=[pk])
                     for archivo, pk in Importacion.objects.order_by('creada').values_list('archivo', 'pk')}
    if contenido == Contenido.SERIE:
        por_capitulo = {}
        capitulos = [c.canal.pk for serie in pagina for c in serie.capitulos]
        for fuente in Fuente.objects.filter(canal_id__in=capitulos).order_by('prioridad', 'pk'):
            por_capitulo.setdefault(fuente.canal_id, []).append(fuente)
        for serie in pagina:
            serie.logo_ver = serie.logo
            fuentes, vistos = [], set()
            for capitulo in serie.capitulos:
                for fuente in por_capitulo.get(capitulo.canal.pk, []):
                    if fuente.origen not in vistos:   # una vez por origen (no una por capítulo)
                        vistos.add(fuente.origen)
                        fuentes.append(fuente)
            serie.activo = any(c.canal.activo for c in serie.capitulos)
            serie.destacado = any(c.canal.destacado for c in serie.capitulos)
            temporadas = sorted(serie.temporadas)
            serie.datos = json.dumps({
                'tipo': 'serie', 'nombre': serie.nombre, 'logo': serie.logo, 'portada': bool(serie.portada),
                'activo': serie.activo, 'destacado': serie.destacado,
                'categoria': serie.categoria_id or 'ninguna', 'capitulos': serie.cantidad,
                'en_app': serie.completa, 'motivo': serie.por_que_no_se_ve,
                'datos': [
                    ('Sección', 'Series'),
                    ('Categoría', serie.categoria or 'Sin categoría («Otros»)'),
                    ('Temporadas', ', '.join(str(t) for t in temporadas)),
                    ('Capítulos', f'{serie.cantidad} ({serie.en_la_app} se ven en la app)'),
                    ('Portada', 'propia de la serie' if serie.portada else 'la del primer capítulo'),
                ],
                'fuentes': _origenes_de(fuentes, importaciones, borrables=False),
                'mas': f"{reverse('canales:serie_detalle')}?nombre={quote(serie.nombre)}",
            })
        return
    usuarios = _nombres_de_usuarios(pagina)
    # Lo que ve la app: la copia pareja del logo (imagenes.logos_parejos), o nada si está roto
    logos = [canal.logo for canal in pagina]
    parejos, rotos = imagenes.logos_parejos(logos), imagenes.logos_rotos(logos)
    for canal in pagina:
        canal.no_se_ve = consultas.por_que_no_se_ve(canal)
        canal.logo_ver = imagenes.logo_para_mostrar(canal.logo, parejos)
        datos = _datos_del_canal(canal, usuarios)
        if canal.logo in rotos:
            datos.append(('Logo', f'Roto: {rotos[canal.logo]} En la app van las iniciales: poné otro con Editar.'))
        canal.datos = json.dumps({
            'tipo': 'canal', 'pk': canal.pk, 'nombre': canal.nombre, 'logo': canal.logo, 'logo_ver': canal.logo_ver,
            'numero': canal.numero,
            'categoria': canal.categoria_id or 'ninguna', 'contenido': canal.contenido, 'activo': canal.activo,
            'destacado': canal.destacado,
            'en_app': not canal.no_se_ve, 'motivo': canal.no_se_ve,
            'datos': datos,
            'fuentes': _origenes_de(canal.fuentes.all(), importaciones),
            'mas': reverse('canales:canal_editar', args=[canal.pk]),
        })


def _filtros_de_organizar(datos):
    """Los filtros de Organizar contenido (de la dirección, o de un formulario que los repite)."""
    return {
        'texto': datos.get('q', '').strip(),
        'mostrar': datos.get('mostrar') if datos.get('mostrar') in consultas.MOSTRAR else 'todo',
        'origen': datos.get('origen', ''),
        'sin_logo': datos.get('sin_logo') == '1',
        'idioma': datos.get('idioma') if datos.get('idioma') in ('es', 'otro', 'sin_dato') else '',
    }


def _hay_filtros(filtros):
    return bool(filtros['texto'] or filtros['mostrar'] != 'todo' or filtros['origen'] or filtros['sin_logo']
                or filtros['idioma'])


def _capitulos_elegidos(request):
    """
    Los capítulos de las series elegidas en Organizar. Con filtros (por ejemplo,
    "de tal lista"), SOLO los que se ven con esos filtros: la tarjeta muestra
    esos, y una acción nunca puede tocar lo que no se ve (otra lista).
    """
    capitulos = organizar.capitulos_de(request.POST.getlist('serie'))
    filtros = _filtros_de_organizar(request.POST)
    if _hay_filtros(filtros):
        capitulos = capitulos.filter(pk__in=consultas.canales_filtrados(Contenido.SERIE, **filtros).values('pk'))
    return capitulos


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
    filtros = _filtros_de_organizar(request.GET)
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
        'hay_filtros': _hay_filtros(filtros),
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
        # Para "Unir en una sola serie" y "Pasar a Series": Categoría -> Serie -> Temporada (js/destino_serie.js,
        # que pide las series a series_arbol recién cuando se abre una de esas dos)
        'categorias_de_series': (Categoria.objects.filter(contenido=Contenido.SERIE).order_by('orden', 'nombre')
                                 if puede_editar else []),
        # Lo que tiene la categoría elegida SIN filtros (borrarla con todo se lleva eso, no lo que se ve)
        'total_de_la_categoria': next((c.total for c in categorias if nodo and nodo['categoria']
                                       and c.pk == nodo['categoria'].pk), 0),
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
                                             categoria=categoria, activo=datos['activo'],
                                             destacado=datos['destacado'])
            titulo = datos['nombre'] or nombre
        else:
            canal = get_object_or_404(Canal, pk=request.POST.get('canal', '0'))
            categoria = _categoria_elegida(request, datos['contenido'] or canal.contenido)
            extra = {'contenido': datos['contenido']} if datos['contenido'] else {}
            cambios = organizar.editar_canal(canal, request.user, nombre=datos['nombre'], logo=datos['logo'],
                                             categoria=categoria, activo=datos['activo'],
                                             numero=datos['numero'].strip(), destacado=datos['destacado'], **extra)
            if 'logo' in cambios or 'contenido' in cambios:
                imagenes.emparejar_logo_al_guardar(canal)
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
        cantidad = organizar.eliminar_contenido(_capitulos_elegidos(request), request.user)
        for nombre in request.POST.getlist('serie'):
            if not organizar.capitulos_de([nombre]).exists():   # se fue entera (no quedaron de otras listas)
                imagenes.poner_portada(nombre, '')
    else:
        cantidad = organizar.eliminar_contenido(_canales_elegidos(request), request.user)
    if cantidad:
        messages.success(request, f'Se eliminaron {cantidad}. Si fue un error, se recuperan en «Eliminados».')
    else:
        messages.info(request, 'No había nada elegido.')
    return redirect(_volver(request))


@requiere_permiso('importar_canales')
def eliminados(request):
    """Lo eliminado en los últimos 30 días, de a una vez por cada vez que se eliminó, para deshacerlo."""
    if request.method == 'POST':
        muestra = request.POST.get('muestra', '')
        resultado = organizar.restaurar_eliminados(int(muestra) if muestra.isdigit() else 0, request.user)
        partes = [f'Se restauraron {resultado.restaurados}: vuelven a la app con sus señales "sin verificar" '
                  '(la app las intenta y la verificación las prueba).']
        if resultado.ya_estaban:
            partes.append(f'{resultado.ya_estaban} ya estaban de nuevo (se volvieron a importar).')
        if resultado.sin_senales:
            partes.append(f'{resultado.sin_senales} no se pudieron: se habían agregado a mano o se borró el '
                          'informe de su lista, y sus señales no quedaron anotadas.')
        (messages.success if resultado.restaurados else messages.warning)(request, ' '.join(partes))
        return redirect('canales:eliminados')
    return render(request, 'canales/eliminados.html', {'eliminaciones': organizar.eliminados_recientes()})


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
            capitulo.numero_en_el_titulo = _numero_en_el_titulo(capitulo.titulo)
        serie.temporadas_ordenadas.append((numero, capitulos, _como_esta_el_orden(capitulos, numero)))

    numeros = serie.numeros_de_temporada
    return render(request, 'canales/serie_detalle.html', {
        'serie': serie,
        'puede_editar': chequear_permiso(request.user, 'importar_canales'),
        'categorias_de_series': Categoria.objects.filter(contenido=Contenido.SERIE).order_by('orden', 'nombre'),
        'temporada_nueva': (max(numeros) + 1) if numeros else 1,
        'otras_series': [n for n in _nombres_de_series() if n.casefold() != serie.nombre.casefold()],
        'agregar_de_youtube': f"{reverse('canales:youtube')}?{urlencode({'serie': serie.nombre})}",
    })


@requiere_permiso('importar_canales')
def series_arbol(request):
    """Categoría -> serie -> temporadas (JSON) para el selector "Dónde va" de Organizar (consultas.arbol_de_series)."""
    return JsonResponse(consultas.arbol_de_series())


@require_POST
@requiere_permiso('importar_canales')
def serie_editar(request):
    """Desde la página de la serie: su categoría y su nombre (todos los capítulos)."""
    nombre = request.POST.get('nombre', '').strip()
    elegida = ' '.join((request.POST.get('categoria_nueva') or request.POST.get('categoria') or '').split())
    datos = {'categoria': organizar.categoria_por_nombre(elegida, Contenido.SERIE, usuario=request.user)
             if elegida else None}
    if request.POST.get('nuevo_nombre', '').strip():
        datos['nombre'] = request.POST['nuevo_nombre']
    try:
        cambios = organizar.editar_serie(nombre, request.user, **datos)
    except organizar.NoSePuede as error:
        messages.error(request, str(error))
        return redirect(f"{reverse('canales:serie_detalle')}?nombre={quote(nombre)}")
    if 'nombre' in cambios:
        nombre = organizar.nombre_de_serie_valido(datos['nombre'])
    messages.success(request, 'Listo: la serie quedó así.' if cambios else 'No cambió nada.')
    return redirect(f"{reverse('canales:serie_detalle')}?nombre={quote(nombre)}")


@requiere_permiso('importar_canales')
def serie_por_titulos(request):
    """
    Ordenar TODA la serie según lo que dice cada título ("Temporada 3 Capítulo 33" -> T3 E33): primero se ve
    cómo quedaría (temporadas, qué cambia, los que no dicen su número o lo repiten) y después se aplica.
    """
    datos = request.POST if request.method == 'POST' else request.GET
    nombre = datos.get('nombre', '').strip()
    de_corrido = datos.get('de_corrido') == '1'
    pagina = f"{reverse('canales:serie_detalle')}?nombre={quote(nombre)}"
    if request.method == 'POST':
        cantidad = organizar.ordenar_por_titulos(nombre, de_corrido, request.user)
        messages.success(request, f'Listo: {cantidad} capítulo(s) cambiaron de temporada o de número.' if cantidad
                         else 'Ya estaba así: no cambió nada.')
        if not organizar.ultimo_capitulo(nombre, 1) or organizar.plan_por_titulos(nombre).falta_el_1:
            messages.warning(request, 'Ojo: la temporada 1 no arranca en el capítulo 1 y la app no muestra la serie '
                                      'así. Volvé a «Ordenar según los títulos» y marcá «Numerar de corrido».')
        return redirect(pagina)
    plan = organizar.plan_por_titulos(nombre, de_corrido)
    if not plan.capitulos:
        raise Http404('No se encontró la serie.')
    cambian = plan.cambian
    return render(request, 'canales/serie_titulos.html', {
        'nombre': nombre, 'plan': plan, 'cambian': cambian, 'mostrados': cambian[:400],
        'de_corrido': de_corrido, 'pagina_de_la_serie': pagina,
    })


@require_POST
@requiere_permiso('importar_canales')
def serie_eliminar_capitulos(request):
    """Elimina los capítulos elegidos de una serie (la temporada se renumera sin huecos)."""
    nombre = request.POST.get('nombre', '').strip()
    pagina = f"{reverse('canales:serie_detalle')}?nombre={quote(nombre)}"
    try:
        cantidad = organizar.eliminar_capitulos(nombre, request.POST.getlist('elegido'), request.user)
    except organizar.NoSePuede as error:
        messages.error(request, str(error))
        return redirect(pagina)
    if not organizar.capitulos_de([nombre]).exists():
        imagenes.poner_portada(nombre, '')   # se fue entera: la portada no queda suelta
        messages.success(request, f'Se eliminaron {cantidad} capítulo(s): eran todos, la serie ya no está. Si fue '
                                  f'un error, se recupera en «Eliminados».')
        return redirect(f"{reverse('canales:organizar')}?contenido={Contenido.SERIE}")
    messages.success(request, f'Se eliminaron {cantidad} capítulo(s) y los que quedan se renumeraron sin huecos. Si '
                              f'fue un error, se recuperan en «Eliminados».')
    if not organizar.ultimo_capitulo(nombre, 1):
        messages.warning(request, 'Ojo: la temporada 1 quedó vacía. La app muestra la serie recién cuando tiene '
                                  'su temporada 1.')
    return redirect(pagina)


@require_POST
@requiere_permiso('importar_canales')
def serie_temporada(request):
    """Pasa los capítulos elegidos de una serie a otra temporada (una que tiene o una nueva)."""
    nombre = request.POST.get('nombre', '').strip()
    destino = request.POST.get('a_temporada', '')
    try:
        cantidad = organizar.mover_a_temporada(nombre, request.POST.getlist('elegido'), destino, request.user)
    except organizar.NoSePuede as error:
        messages.error(request, str(error))
        return redirect(f"{reverse('canales:serie_detalle')}?nombre={quote(nombre)}")
    messages.success(request, f'Listo: {cantidad} capítulo(s) pasaron a la temporada {destino}, al final. Las '
                              f'temporadas de donde salieron se renumeraron sin huecos.')
    if not organizar.ultimo_capitulo(nombre, 1):
        messages.warning(request, 'Ojo: la temporada 1 quedó vacía. La app muestra la serie recién cuando tiene '
                                  'su temporada 1: pasá capítulos a la 1 (o renumerá las temporadas).')
    return redirect(f"{reverse('canales:serie_detalle')}?nombre={quote(nombre)}#temporada-{destino}")


def _nombres_de_series():
    """Todas las series (para elegir a cuál pasar capítulos: la lista que se despliega al escribir)."""
    return sorted({serie['nombre'] for categoria in consultas.arbol_de_series()['categorias']
                   for serie in categoria['series']}, key=str.casefold)


@requiere_permiso('importar_canales')
def serie_separar(request):
    """
    Separar en OTRA serie lo que vino mezclado ("Yu-Gi-Oh" con los de GX): GET con `dice` muestra los
    capítulos cuyo título lo dice (todos tildados) y el nombre sugerido; POST los pasa (también desde la barra
    de una temporada, con los tildados a mano). Vuelve a la serie de origen para seguir separando.
    """
    datos = request.POST if request.method == 'POST' else request.GET
    nombre = datos.get('nombre', '').strip()
    pagina = f"{reverse('canales:serie_detalle')}?nombre={quote(nombre)}"
    if request.method == 'POST':
        if not datos.get('a_serie', '').strip():
            messages.error(request, 'Escribí a qué serie pasan los capítulos elegidos.')
            return redirect(pagina)
        try:
            cantidad, destino = organizar.mover_a_otra_serie(
                nombre, datos.getlist('elegido'), datos['a_serie'], datos.get('temporada_destino') or 1,
                request.user)
        except organizar.NoSePuede as error:
            messages.error(request, str(error))
            return redirect(pagina)
        if not organizar.capitulos_de([nombre]).exists():
            messages.success(request, f'Listo: los {cantidad} capítulos pasaron a «{destino}». Eran todos: '
                                      f'«{nombre}» ya no está.')
            return redirect(f"{reverse('canales:serie_detalle')}?nombre={quote(destino)}")
        messages.success(request, f'Listo: {cantidad} capítulo(s) pasaron a la serie «{destino}» (está en Series, '
                                  f'con su nombre). Acá quedan los demás, renumerados sin huecos.')
        if not organizar.ultimo_capitulo(nombre, 1):
            messages.warning(request, 'Ojo: acá la temporada 1 quedó vacía. La app muestra la serie recién cuando '
                                      'tiene su temporada 1.')
        return redirect(pagina)

    dice = ' '.join(datos.get('dice', '').split())
    if not dice:
        messages.error(request, 'Escribí qué dicen los títulos de los capítulos que querés separar (ej: GX).')
        return redirect(pagina)
    encontrados = organizar.capitulos_que_dicen(nombre, dice)
    if not encontrados and not organizar.capitulos_de([nombre]).exists():
        raise Http404('No se encontró la serie.')
    return render(request, 'canales/serie_separar.html', {
        'nombre': nombre, 'dice': dice, 'encontrados': encontrados, 'pagina_de_la_serie': pagina,
        'sugerido': organizar.nombre_sugerido([titulo for _, _, _, titulo in encontrados], dice, nombre),
        'series': [n for n in _nombres_de_series() if n.casefold() != nombre.casefold()],
        'total': organizar.capitulos_de([nombre]).count(),
    })


def _como_esta_el_orden(capitulos, temporada):
    """
    {'desordenada': True} si la mayoría de los títulos dicen su número
    ("Capítulo 12") y no van en orden: la página lo avisa y ofrece ordenarlos.
    'de_otra_temporada': cuántos dicen en el título que son de OTRA temporada
    ("Temporada 3 Capitulo 33" en la 1: vino mezclado de YouTube). Ahí ordenar
    esta temporada no alcanza: la página ofrece "Ordenar todo según los títulos".
    """
    numeros = [c.numero_en_el_titulo for c in capitulos if c.numero_en_el_titulo is not None]
    alcanza = len(capitulos) > 1 and len(numeros) >= len(capitulos) / 2
    de_otra = sum(1 for c in capitulos if (organizar.temporada_y_numero_del_titulo(c.titulo) or (0, 0))[0]
                  not in (0, temporada))
    return {'desordenada': alcanza and numeros != sorted(numeros), 'de_otra_temporada': de_otra}


def _numero_en_el_titulo(titulo):
    """
    El número de capítulo que dice el título ("Capítulo 12", "EP 12", "12 - El
    regreso"), para el botón "Por el número del título" (None si no dice).
    """
    dice = organizar.temporada_y_numero_del_titulo(titulo)
    return dice[1] if dice else None


@require_POST
@requiere_permiso('importar_canales')
def serie_ordenar(request):
    """Guarda el orden de los capítulos de una temporada (los renumera 1, 2, 3...)."""
    nombre = request.POST.get('nombre', '').strip()
    temporada = request.POST.get('temporada', '')
    temporada = int(temporada) if temporada.isdigit() else 1
    try:
        cambiados = organizar.ordenar_capitulos(nombre, temporada, request.POST.getlist('capitulo'), request.user)
        messages.success(request, f'Listo: {cambiados} capítulo(s) cambiaron de número. La app los muestra en este '
                                  f'orden.' if cambiados else 'Ya estaban en ese orden: no cambió nada.')
    except organizar.NoSePuede as error:
        messages.error(request, str(error))
    return redirect(f"{reverse('canales:serie_detalle')}?nombre={quote(nombre)}#temporada-{temporada}")


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
        messages.success(request, f'{cantidad} vuelven a la app. Sus señales caídas o escondidas se prueban de nuevo '
                                  f'en los aparatos.')
    else:
        messages.info(request, _NADA_PARA_MOSTRAR)
    return _volver_al_catalogo(request)


_NADA_PARA_MOSTRAR = ('Lo elegido ya se podía ver: no estaba quitado ni tenía señales caídas o escondidas. Si tiene '
                      'las fuentes apagadas a mano, se prenden desde Editar.')


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


def _categoria_de_la_serie_elegida(request, nombre_serie):
    """
    La categoría de Series elegida en el selector "Dónde va" (o la de la serie,
    si ya existe: organizar.destino_de_serie). NoSePuede si no se entiende.
    """
    organizar.nombre_de_serie_valido(nombre_serie)   # antes de crear una categoría por nada
    elegida = request.POST.get('serie_categoria_nueva', '').strip() or request.POST.get('serie_categoria', '')
    return organizar.destino_de_serie(nombre_serie, elegida, request.user)


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
        destino = {}
        if contenido == Contenido.SERIE and nombre_serie:
            destino['categoria'] = _categoria_de_la_serie_elegida(request, nombre_serie)
        cantidad = organizar.cambiar_contenido(_canales_elegidos(request), contenido, nombre_serie, temporada,
                                               request.user, **destino)
    except organizar.NoSePuede as error:
        messages.error(request, str(error))
        return _volver_al_catalogo(request)
    _avisar_cambio_de_tipo(request, cantidad, contenido, nombre_serie)
    return _volver_al_catalogo(request)


@require_POST
@requiere_permiso('importar_canales')
def series_acciones(request):
    """
    Sobre las series elegidas: moverlas de categoría, pasarlas a películas,
    unirlas, quitarlas o mostrarlas. Con filtros, solo los capítulos que se ven.
    """
    capitulos = _capitulos_elegidos(request)
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
            categoria = _categoria_de_la_serie_elegida(request, nombre_serie)
            cantidad = organizar.unir_en_una_serie(request.POST.getlist('serie'), nombre_serie, temporada,
                                                   request.user, capitulos=capitulos, categoria=categoria)
            _avisar_cambio_de_tipo(request, cantidad, Contenido.SERIE, nombre_serie)
        elif request.POST.get('accion') == 'quitar':
            cantidad = servicios.quitar_canales(capitulos, request.POST.get('motivo', ''), request.user)
            messages.success(request, f'Se quitaron de la app {cantidad} capítulo(s).' if cantidad
                             else 'Ya estaban quitadas.')
        elif request.POST.get('accion') == 'mostrar':
            cantidad = servicios.mostrar_canales(capitulos, request.user)
            if cantidad:
                messages.success(request, f'{cantidad} capítulo(s) vuelven a la app.')
            else:
                messages.info(request, _NADA_PARA_MOSTRAR)
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
            return (f'Se borró "{categoria}" con todo su contenido ({cantidad} eliminados). Si fue un error, se '
                    'recupera en «Eliminados».')
        return f'Se borró "{categoria}"' + (f' y {cantidad} quedaron sin categoría.' if cantidad else '.')
    if accion == 'eliminar_filtrados':
        # Con filtros: solo lo de esta categoría que se ve (la categoría y lo demás quedan)
        categoria = get_object_or_404(Categoria, pk=request.POST.get('categoria', '0'))
        filtros = _filtros_de_organizar(request.POST)
        if not _hay_filtros(filtros):
            raise organizar.NoSePuede('Sin filtros, para eliminar todo usá «Con todo lo que tiene».')
        canales = consultas.canales_filtrados(categoria.contenido, **filtros).filter(categoria=categoria)
        cantidad = organizar.eliminar_contenido(Canal.objects.filter(pk__in=canales.values('pk')), request.user)
        return (f'Se eliminaron {cantidad} de "{categoria}" (los que se veían con el filtro). Lo demás de la '
                'categoría sigue. Si fue un error, se recupera en «Eliminados».')
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
        imagenes.emparejar_logo_al_guardar(canal)   # si ya la tiene, no hace nada
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
        'logo_ver': imagenes.logo_para_mostrar(canal.logo, imagenes.logos_parejos([canal.logo])),
        'form': form,
        'fuentes': fuentes,
        'volver': _volver(request, canal.contenido),
    })


@require_POST
@requiere_permiso('importar_canales')
def fuente_borrar(request, pk):
    """
    Borra UNA fuente (la que no anda) desde Organizar o la página del canal, y
    vuelve a donde se estaba. En Organizar se vuelve con el panel de detalles
    de ese canal abierto (#ver-<id>).
    """
    fuente = get_object_or_404(Fuente.objects.select_related('canal'), pk=pk)
    canal = fuente.canal
    quedan = servicios.borrar_fuente(fuente, request.user)
    if quedan:
        messages.success(request, f'Se borró la señal de «{canal.nombre}». Le quedan {quedan}.')
    else:
        messages.warning(request, f'Se borró la señal de «{canal.nombre}». Era la única: no se va a ver en la app '
                                  f'hasta que le agregues otra.')
    # "despues": la página del canal (vuelve a ella); si no, Organizar con su detalle abierto
    despues = request.POST.get('despues', '')
    if despues and url_has_allowed_host_and_scheme(despues, allowed_hosts={request.get_host()}):
        return redirect(despues)
    return redirect(f'{_volver(request, canal.contenido).split("#")[0]}#ver-{canal.pk}')


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
    """
    Limpia los nombres (todos, o los de una sección o una lista: "Qué revisar"
    en Mantenimiento). El detalle de lo que cambió queda en la sesión y la
    página lo muestra al volver (`resultado_limpieza`).
    """
    seccion, origen = _que_revisar(request.POST)
    cambios = []
    renombrados, juntados = servicios.limpiar_nombres(request.user, seccion, origen, cambios)
    request.session['resultado_limpieza'] = {
        'que': servicios.que_se_revisa(seccion, origen, 'canales'),
        'renombrados': renombrados, 'juntados': juntados,
        'cambios': cambios[:MAXIMO_CAMBIOS_A_LA_VISTA], 'mas': max(0, len(cambios) - MAXIMO_CAMBIOS_A_LA_VISTA),
    }
    return redirect(f"{reverse('canales:inicio')}#mantenimiento-contenido")


# Cuántos cambios de "Limpiar nombres" se muestran (el resto: "y N más")
MAXIMO_CAMBIOS_A_LA_VISTA = 200


def _que_revisar(datos):
    """La sección y la lista de origen elegidas en "Qué revisar" ('' = todas)."""
    seccion = datos.get('seccion', '')
    return (seccion if secciones.es_valida(seccion) else ''), datos.get('origen', '').strip()[:150]


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
