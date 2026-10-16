"""
Lo que el sistema BUSCA de los canales (capa Base).
"""

from collections import Counter
from dataclasses import dataclass, field

from django.db.models import Case, Count, Exists, F, OuterRef, Prefetch, Q, Value, When
from django.utils import timezone

from . import clasificar, imagenes, secciones, youtube
from .models import (CORTES_POR_HORA_TOLERABLES, MINIMO_VISTO_PARA_JUZGAR, PROPORCION_PANTALLA_COMPLETA,
                     VELOCIDAD_SOBRADA, Canal, Categoria, Contenido, Fuente, Importacion)

# Lo que el reproductor de la app sabe reproducir. La app nueva lo dice al
# pedir los canales (?formatos=hls,dash,directo,rtsp,youtube,pagina); la
# 1.0.0 no dice nada y solo sabe HLS: a esa se le manda solo HLS (si no,
# mostraría canales que no puede abrir).
TIPOS_QUE_REPRODUCE_LA_APP = [Fuente.Tipo.HLS, Fuente.Tipo.DASH, Fuente.Tipo.DIRECTO, Fuente.Tipo.RTSP,
                              Fuente.Tipo.YOUTUBE, Fuente.Tipo.PAGINA, Fuente.Tipo.YT_VIDEO]
TIPOS_DE_LA_APP_VIEJA = [Fuente.Tipo.HLS]

# El orden de las categorías en la app: por su número de orden y su nombre.
# Lo sin categoría ("Otros") va al final.
ORDEN_DE_CATEGORIAS = ('categoria__orden', 'categoria__nombre')


def tipos_pedidos(texto):
    """'hls,directo,cualquiera' -> los que existen. Vacío -> los de la app vieja."""
    pedidos = [t.strip() for t in (texto or '').split(',') if t.strip() in Fuente.Tipo.values]
    return pedidos or TIPOS_DE_LA_APP_VIEJA


def fuentes_usables(tipos=None):
    """
    Las que la app puede usar: activas, no caídas, no ocultas por fallar en
    los aparatos y de un tipo que sabe reproducir. Las "sin verificar" sí
    (todavía no se sabe que fallen).
    """
    return (Fuente.objects.filter(activa=True, tipo__in=tipos or TIPOS_QUE_REPRODUCE_LA_APP)
            .exclude(estado=Fuente.Estado.CAIDA)
            .exclude(oculta_hasta__gt=timezone.now()))


# El orden en que la app prueba las fuentes de un canal (ver ordenadas_por_estabilidad)
ESTABLE, SIN_DATOS, SE_CORTA = 0, 1, 2


def ordenadas_por_estabilidad(fuentes):
    """
    Las fuentes de un canal en el orden en que conviene probarlas (la app
    arranca por la primera):

      1. Al final, las que en los APARATOS se cortan seguido
         (CORTES_POR_HORA_TOLERABLES o más). Ej: si en HBO la 1 se traba, en
         poco tiempo deja de ser la primera en todos los aparatos.
      2. Primero, las que llenan la pantalla: las "cuadradas" (4:3, con
         franjas negras a los costados; lo cuentan los aparatos) después.
      3. Lo que midió la PRUEBA A FONDO (al importar y, de madrugada, la
         verificación programada): las verificadas que andan antes que las
         sin verificar; las que llegan sobradas (VELOCIDAD_SOBRADA) antes que
         las no medidas, y esas antes que las que llegan justas; a igual
         fluidez, la de mejor imagen (1080p antes que 720p).
      4. Las que ya se vieron un buen rato sin cortarse antes que las que
         todavía no se vieron.
      5. La prioridad del panel (el orden en que se cargaron).

    Que "se vio bien" no pase por delante de la prueba es a propósito: si no,
    la primera que anduvo quedaría siempre primera y las otras nunca se
    verían (nunca se sabría si alguna es mejor).
    """
    # cortes por hora >= tolerables  <=>  segundos <= cortes * (3600 / tolerables)
    se_corta = Q(segundos_en_aparatos__lte=F('cortes_en_aparatos') * (3600 // CORTES_POR_HORA_TOLERABLES))
    return fuentes.annotate(
        estabilidad=Case(
            When(segundos_en_aparatos__lt=MINIMO_VISTO_PARA_JUZGAR, then=Value(SIN_DATOS)),
            When(se_corta, then=Value(SE_CORTA)),
            default=Value(ESTABLE),
        ),
        se_corta=Case(
            When(Q(segundos_en_aparatos__gte=MINIMO_VISTO_PARA_JUZGAR) & se_corta, then=Value(1)),
            default=Value(0),
        ),
        cuadrada=Case(
            When(proporcion__gt=0, proporcion__lt=PROPORCION_PANTALLA_COMPLETA, then=Value(1)),
            default=Value(0),
        ),
        verificada_que_anda=Case(When(estado=Fuente.Estado.FUNCIONA, then=Value(0)), default=Value(1)),
        fluidez=Case(
            When(velocidad__gte=VELOCIDAD_SOBRADA, then=Value(0)),
            When(velocidad=0, then=Value(1)),
            default=Value(2),
        ),
    ).order_by('se_corta', 'cuadrada', 'verificada_que_anda', 'fluidez', '-alto', 'estabilidad', 'prioridad', 'pk')


def canales_disponibles(tipos=None, contenido=Contenido.VIVO):
    """
    Canales que la app puede mostrar: activos, del contenido pedido (en vivo,
    películas o series) y con al menos una fuente usable. Trae esas fuentes
    (las que no se cortan primero, ver ordenadas_por_estabilidad) y su categoría.

    Más adelante acá se va a filtrar según el plan / los créditos del
    dispositivo que pregunta.
    """
    fuentes = ordenadas_por_estabilidad(fuentes_usables(tipos))
    return (
        Canal.objects
        .filter(activo=True, contenido=contenido, pk__in=fuentes_usables(tipos).values('canal'))
        .select_related('categoria')
        .prefetch_related(Prefetch('fuentes', queryset=fuentes, to_attr='fuentes_activas'))
        .order_by(*ORDEN_DE_CATEGORIAS, 'orden', 'nombre')
    )


def agrupar_por_categoria(canales):
    """[(categoría o None, [canales]), ...] en el orden en que vienen."""
    grupos = {}
    for canal in canales:
        grupos.setdefault(canal.categoria_id, (canal.categoria, []))[1].append(canal)
    return list(grupos.values())


# Cómo se llama cada tipo de contenido en el resumen (en plural)
NOMBRES_EN_PLURAL = {Contenido.VIVO: 'En vivo', Contenido.PELICULA: 'Películas', Contenido.SERIE: 'Series'}


def resumen_de(contenido, nombre=''):
    """
    Los números de una sección (en vivo, películas, series o una nueva, como Música):
    cuántos hay cargados, cuántos ve la app, quitados, y sus fuentes por estado.
    En series se cuenta por capítulo (cada capítulo es un Canal).
    """
    fuentes = Fuente.objects.filter(canal__eliminado_en__isnull=True, canal__contenido=contenido).order_by()
    por_estado = dict(fuentes.values_list('estado').annotate(cantidad=Count('pk')))
    cargados = Canal.objects.filter(contenido=contenido).count()
    en_la_app = canales_disponibles(contenido=contenido).count()
    return {
        'contenido': contenido,
        'nombre': nombre or NOMBRES_EN_PLURAL[contenido],
        'unidad': 'capítulos' if contenido == Contenido.SERIE else 'cargados',
        'cargados': cargados,
        'en_la_app': en_la_app,
        'no_se_ven': max(cargados - en_la_app, 0),   # caídos o quitados: lo que hay que mirar
        'quitados': Canal.objects.filter(contenido=contenido, activo=False).count(),
        'funcionan': por_estado.get(Fuente.Estado.FUNCIONA, 0),
        'caidas': por_estado.get(Fuente.Estado.CAIDA, 0),
        'sin_verificar': por_estado.get(Fuente.Estado.SIN_VERIFICAR, 0),
        'ocultas': fuentes.filter(oculta_hasta__gt=timezone.now()).count(),
        'fuentes': sum(por_estado.values()),
    }


def resumen():
    """
    Números para la pantalla de canales del panel. Las claves sueltas
    (canales, funcionan, caidas...) son SOLO de los canales en vivo: antes
    sumaban también películas y capítulos, y "7262 canales" confundía.
    `por_contenido`: lo mismo para en vivo, películas y series (resumen_de).
    """
    por_contenido = [*(resumen_de(c) for c in Contenido.values),
                     *(resumen_de(s.clave, s.nombre) for s in secciones.nuevas())]
    vivo = por_contenido[0]
    return {
        'canales': vivo['cargados'],
        'canales_en_la_app': vivo['en_la_app'],
        # Ya no quedan apps 1.0.0 (solo HLS): igual al total, así el aviso viejo no aparece
        'canales_en_la_app_vieja': vivo['en_la_app'],
        'quitados': vivo['quitados'],
        'peliculas': por_contenido[1]['cargados'],
        'series': por_contenido[2]['cargados'],
        'funcionan': vivo['funcionan'],
        'caidas': vivo['caidas'],
        'sin_verificar': vivo['sin_verificar'],
        'fuentes': vivo['fuentes'],
        'por_contenido': por_contenido,
    }


# ── Series: los capítulos agrupados por serie y temporada ────────────

@dataclass
class Capitulo:
    canal: Canal
    temporada: int
    numero: int | None
    titulo: str


@dataclass
class Serie:
    nombre: str
    categoria: str = ''
    logo: str = ''   # la portada, o la imagen del primer capítulo que tenga
    temporadas: dict = field(default_factory=dict)   # {número: [Capitulo, ...]}
    portada: str = ''   # la propia de la serie (imagenes.PortadaDeSerie)
    categoria_id: int | None = None

    @property
    def capitulos(self):
        return [c for lista in self.temporadas.values() for c in lista]

    @property
    def cantidad(self):
        return len(self.capitulos)

    @property
    def en_la_app(self):
        """Cuántos capítulos ve la app."""
        return sum(1 for c in self.capitulos if c.canal.activo and c.canal.tiene_usable)

    @property
    def fuera(self):
        return self.cantidad - self.en_la_app

    @property
    def completa(self):
        """La app la muestra si entre los capítulos que se ven está el T1:E1."""
        return not self.por_que_no_se_ve

    @property
    def por_que_no_se_ve(self):
        """Por qué la app no muestra la serie ('' = sí la muestra)."""
        vistos = [c for c in self.capitulos if c.canal.activo and c.canal.tiene_usable]
        if not vistos:
            return 'No se ve ningún capítulo.'
        if not any(c.temporada == 1 and c.numero == 1 for c in vistos):
            return 'Falta el capítulo 1 de la temporada 1: la app no muestra series que no se pueden empezar.'
        return ''

    @property
    def numeros_de_temporada(self):
        return sorted(self.temporadas)


def series(texto='', estado='', categoria='', idioma='', origen='', sin_logo=False):
    """
    Las series armadas a partir de los capítulos sueltos ("Show S01 E02"),
    con la misma regla que la app (clasificar.episodio). Cada capítulo trae
    los números del catálogo (fuentes, cuáles andan, si la app lo ve).
      estado: 'en_app' (la app la muestra: ver Serie.completa) | 'incompleta' (se ven
              capítulos, pero la app no la muestra) | 'fuera' (no se ve ninguno) | '' (todas)
      categoria, idioma, origen, sin_logo: como en el catálogo (se aplican a los capítulos)
    """
    capitulos = catalogo(texto=texto, contenido=Contenido.SERIE, categoria=categoria, idioma=idioma,
                         origen=origen, sin_logo=sin_logo).prefetch_related(None)
    por_nombre = {}
    for canal in capitulos:
        nombre, temporada, numero, titulo = clasificar.episodio(canal.nombre)
        serie = por_nombre.setdefault(nombre.lower(), Serie(
            nombre=nombre, categoria=canal.categoria.nombre if canal.categoria else '',
            categoria_id=canal.categoria_id))
        serie.logo = serie.logo or canal.logo
        serie.temporadas.setdefault(temporada, []).append(Capitulo(canal, temporada, numero, titulo))
    resultado = sorted(por_nombre.values(), key=lambda s: s.nombre.lower())
    portadas = imagenes.portadas_de([s.nombre for s in resultado])
    for serie in resultado:
        for lista in serie.temporadas.values():
            lista.sort(key=lambda c: (c.numero is None, c.numero or 0, c.canal.nombre))
        primero = next((c.canal.logo for t in sorted(serie.temporadas) for c in serie.temporadas[t] if c.canal.logo),
                       '')
        serie.portada = portadas.get(serie.nombre, '')
        serie.logo = serie.portada or primero   # como la app: la portada, o la imagen del primer capítulo
    if sin_logo:
        resultado = [s for s in resultado if not s.portada]
    if estado == 'en_app':
        resultado = [s for s in resultado if s.completa]
    elif estado == 'incompleta':
        resultado = [s for s in resultado if s.en_la_app and not s.completa]
    elif estado == 'fuera':
        resultado = [s for s in resultado if not s.en_la_app]
    return resultado


def arbol_de_series():
    """
    Categoría -> serie -> temporadas de la sección Series, para el selector
    "Dónde va" (Traer de YouTube, Unir, Pasar a Series y la página de cada
    serie): que se vea qué hay antes de elegir.
      {'categorias': [{'nombre': 'Disney', 'series': [{'nombre': 'Buena suerte Charlie',
                       'temporadas': [[1, 26, 26], [2, 30, 30]]}]}]}
    Cada temporada: [número, cuántos capítulos, el número más alto]. La serie
    va en la categoría de la mayoría de sus capítulos; las sin categoría, en
    una de nombre '' (en la app, "Otros"). Las series se agrupan como en la
    app (sin mayúsculas).
    """
    series = {}
    for nombre, categoria_id in Canal.objects.filter(contenido=Contenido.SERIE).values_list('nombre', 'categoria_id'):
        serie, temporada, numero, _ = clasificar.episodio(nombre)
        datos = series.setdefault(serie.lower(), {'nombre': serie, 'categorias': Counter(), 'temporadas': {}})
        datos['categorias'][categoria_id] += 1
        cantidad, ultimo = datos['temporadas'].get(temporada, (0, 0))
        datos['temporadas'][temporada] = (cantidad + 1, max(ultimo, numero or 0))
    grupos = {c.pk: {'nombre': c.nombre, 'series': []}
              for c in Categoria.objects.filter(contenido=Contenido.SERIE).order_by('orden', 'nombre')}
    sin_categoria = {'nombre': '', 'series': []}
    for datos in sorted(series.values(), key=lambda d: d['nombre'].lower()):
        grupo = grupos.get(datos['categorias'].most_common(1)[0][0], sin_categoria)
        grupo['series'].append({'nombre': datos['nombre'], 'temporadas': [
            [temporada, cantidad, ultimo] for temporada, (cantidad, ultimo) in sorted(datos['temporadas'].items())]})
    return {'categorias': [*grupos.values(), *([sin_categoria] if sin_categoria['series'] else [])]}


# ── Como en la app: lo que ve un cliente, categoría por categoría ────

def nombre_en_la_app(nombre):
    """
    El nombre de la categoría como lo muestra la app (categoriaLegible en
    lib/movil/datos.dart): 'AR | DEPORTES' -> 'Deportes'. Sin nombre -> 'Otros'.
    """
    partes = [p.strip() for p in (nombre or '').split('|') if p.strip()]
    ultima = partes[-1] if partes else (nombre or '').strip()
    if not ultima:
        return 'Otros'
    if ultima == ultima.upper() and len(ultima) > 3:
        return ultima[0] + ultima[1:].lower()
    return ultima


@dataclass
class SerieEnLaApp:
    nombre: str
    categoria: Categoria | None = None
    logo: str = ''
    capitulos: int = 0
    tiene_el_primero: bool = False

    @property
    def completa(self):
        """Como Serie.completa: la app muestra las que se pueden empezar desde T1:E1."""
        return self.tiene_el_primero


def como_en_la_app(contenido=Contenido.VIVO):
    """
    Lo que ve un cliente en la app, con sus mismas reglas: solo lo que se
    puede reproducir, agrupado por categoría y en el mismo orden. En series,
    las series completas (no los capítulos sueltos).
      -> [(categoría o None, [canales o SerieEnLaApp]), ...]
    Cada aparato puede mostrar un poco menos (lo que ya le falló, códecs que no tiene).
    """
    canales = canales_disponibles(TIPOS_QUE_REPRODUCE_LA_APP, contenido).prefetch_related(None)
    if contenido != Contenido.SERIE:
        return agrupar_por_categoria(canales)
    por_nombre = {}
    for canal in canales:
        nombre, temporada, numero, _ = clasificar.episodio(canal.nombre)
        serie = por_nombre.setdefault(nombre.lower(), SerieEnLaApp(nombre, canal.categoria))
        serie.logo = serie.logo or canal.logo
        serie.capitulos += 1
        serie.tiene_el_primero = serie.tiene_el_primero or (temporada, numero) == (1, 1)
    portadas = imagenes.portadas_de([s.nombre for s in por_nombre.values()])
    grupos = {}
    for serie in por_nombre.values():
        serie.logo = portadas.get(serie.nombre) or serie.logo
        if serie.completa:
            grupos.setdefault(serie.categoria.pk if serie.categoria else None, (serie.categoria, []))[1].append(serie)
    for _, series_del_grupo in grupos.values():
        series_del_grupo.sort(key=lambda s: s.nombre.lower())
    return list(grupos.values())


# ── Organizar: todo el contenido de una sección, por categoría ───────

def categorias_de(contenido):
    """Las categorías de una sección (En vivo, Películas o Series), en el orden de la app."""
    return Categoria.objects.filter(contenido=contenido).order_by('orden', 'nombre')


@dataclass
class Organizacion:
    """Lo que muestra la pantalla Organizar (ver organizar_contenido)."""
    nodos: list            # las categorías de la izquierda: [{'clave', 'categoria', 'total', 'vacia'}, ...]
    elegida: str           # 'todas', 'ninguna' o el pk de la categoría
    pagina: object         # la página de lo elegido (canales o Serie)
    grupos: list           # la página agrupada: [(categoría o None, [items]), ...]
    total: int             # cuántos hay en esta sección (con los filtros)


# Lo que se puede elegir en "Qué mostrar" de Organizar
MOSTRAR = {
    'todo': 'Todo lo cargado',
    'app': 'Solo lo que ve la app',
    'fuera': 'Lo que NO se ve (caído o quitado)',
    'caidos': 'No se ve porque sus señales no andan',
    'quitados': 'Quitado a mano',
    'destacados': 'Destacado en la TV (★)',
}


def canales_filtrados(contenido='', mostrar='todo', texto='', origen='', sin_logo=False, idioma=''):
    """
    El catálogo con los filtros de Organizar (`mostrar`: uno de MOSTRAR).
    Sin `contenido`, de todas las secciones (lo usa la exportación).
    """
    estado = {'app': 'en_app', 'caidos': 'fuera', 'quitados': 'quitados'}.get(mostrar, '')
    canales = catalogo(texto=texto, contenido=contenido, origen=origen, sin_logo=sin_logo, idioma=idioma,
                       estado=estado)
    if mostrar == 'fuera':
        canales = canales.filter(Q(activo=False) | Q(tiene_usable=False))
    elif mostrar == 'destacados':
        canales = canales.filter(destacado=True)
    return canales


def organizar_contenido(contenido=Contenido.VIVO, mostrar='todo', texto='', origen='', sin_logo=False, idioma='',
                        categoria='', pagina=None, por_pagina=120):
    """
    Todo lo cargado de una sección (en vivo, películas o series), por categoría:
      mostrar: una de MOSTRAR ('fuera' = 'caidos' + 'quitados')
      idioma: 'es' | 'otro' | 'sin_dato' | '' (todos)
      categoria: 'todas' | 'ninguna' | pk ('' = todas)
    """
    from django.core.paginator import Paginator

    if contenido == Contenido.SERIE:
        items = series(texto=texto, origen=origen, sin_logo=sin_logo, idioma=idioma,
                       estado='en_app' if mostrar == 'app' else '')
        def alguno_activo(serie):
            return any(c.canal.activo for c in serie.capitulos)
        if mostrar == 'fuera':
            items = [s for s in items if not s.completa]
        elif mostrar == 'caidos':
            items = [s for s in items if not s.completa and alguno_activo(s)]
        elif mostrar == 'quitados':
            items = [s for s in items if not alguno_activo(s)]
        elif mostrar == 'destacados':
            items = [s for s in items if any(c.canal.destacado for c in s.capitulos)]
        pares = [(s, s.categoria_id) for s in items]
    else:
        canales = canales_filtrados(contenido, mostrar, texto=texto, origen=origen, sin_logo=sin_logo, idioma=idioma)
        pares = list(canales.values_list('pk', 'categoria_id'))

    cuantos = {}
    for _, categoria_id in pares:
        cuantos[categoria_id] = cuantos.get(categoria_id, 0) + 1
    con_algo = set(Canal.objects.exclude(categoria=None).values_list('categoria_id', flat=True).distinct())
    nodos = [{'clave': str(c.pk), 'categoria': c, 'total': cuantos.get(c.pk, 0), 'vacia': c.pk not in con_algo}
             for c in categorias_de(contenido)]
    # Sin filtros se ven todas (también las vacías, para llenarlas); con filtros, solo las que tienen algo
    hay_filtros = texto or origen or sin_logo or idioma or mostrar != 'todo'
    nodos = [n for n in nodos if n['total'] or (n['vacia'] and not hay_filtros)]
    if cuantos.get(None):
        nodos.append({'clave': 'ninguna', 'categoria': None, 'total': cuantos[None], 'vacia': False})

    elegida = categoria or 'todas'
    if elegida not in ('todas', 'ninguna') and not any(n['clave'] == elegida for n in nodos):
        elegida = 'todas'
    posicion = {n['categoria'].pk if n['categoria'] else None: i for i, n in enumerate(nodos)}
    if contenido == Contenido.SERIE:
        elegidos = [s for s, categoria_id in pares
                    if elegida == 'todas' or str(categoria_id) == elegida or (elegida == 'ninguna' and not categoria_id)]
        elegidos.sort(key=lambda s: (posicion.get(s.categoria_id, len(posicion)), s.nombre.lower()))
    elif elegida == 'todas':
        elegidos = canales
    elif elegida == 'ninguna':
        elegidos = canales.filter(categoria=None)
    else:
        elegidos = canales.filter(categoria_id=int(elegida))
    pagina_elegida = Paginator(elegidos, por_pagina).get_page(pagina)

    categorias = {n['categoria'].pk: n['categoria'] for n in nodos if n['categoria']}
    grupos = {}
    for item in pagina_elegida:
        grupos.setdefault(item.categoria_id, (categorias.get(item.categoria_id), []))[1].append(item)
    grupos = sorted(grupos.items(), key=lambda par: posicion.get(par[0], len(posicion)))
    return Organizacion(nodos=nodos, elegida=elegida, pagina=pagina_elegida, grupos=[g for _, g in grupos],
                        total=len(pares))


def ultimas_importaciones(limite=10):
    return Importacion.objects.select_related('usuario')[:limite]


# ── Catálogo: todos los canales, como los ve la app ──────────────────

def _buscar(texto):
    """
    Lo que encuentra el buscador: el nombre o el ID de guía. Pegando el link
    de un video de YouTube (o su ID), lo que lo tenga como señal; pegando
    cualquier otro link, lo que tenga esa señal. Así se encuentra dónde quedó
    algo que una importación dice que "ya estaba".
    """
    texto = texto.strip()
    video = youtube.id_de_video(texto)
    if video:
        return Q(tvg_id=video) | Q(pk__in=Fuente.objects.filter(url__contains=video).values('canal'))
    if '://' in texto:
        return Q(pk__in=Fuente.objects.filter(url=texto).values('canal'))
    return Q(nombre__icontains=texto) | Q(tvg_id__icontains=texto)


def catalogo(texto='', categoria='', idioma='', estado='', sin_logo=False, origen='', contenido=''):
    """
    Todos los canales con sus números (cuántas fuentes, cuántas andan) y si
    la app los muestra. Filtros:
      estado: 'en_app' | 'fuera' (no se ven: sin fuentes que anden) | 'quitados' | '' (todos)
      idioma: 'es' | 'otro' | 'sin_dato'
      contenido: 'vivo' | 'pelicula' | 'serie' | '' (todo)
    """
    usables = fuentes_usables().filter(canal=OuterRef('pk'))
    canales = (
        Canal.objects.select_related('categoria')
        .annotate(
            fuentes_total=Count('fuentes', distinct=True),
            fuentes_funcionan=Count('fuentes', filter=Q(fuentes__estado=Fuente.Estado.FUNCIONA), distinct=True),
            fuentes_caidas=Count('fuentes', filter=Q(fuentes__estado=Fuente.Estado.CAIDA), distinct=True),
            tiene_usable=Exists(usables),
            fuentes_ocultas=Count('fuentes', filter=Q(fuentes__oculta_hasta__gt=timezone.now()), distinct=True),
        )
        .prefetch_related(Prefetch('fuentes', queryset=Fuente.objects.order_by('prioridad', 'pk')))
        .order_by(*ORDEN_DE_CATEGORIAS, 'orden', 'nombre')
    )
    if texto:
        canales = canales.filter(_buscar(texto))
    if categoria == 'ninguna':
        canales = canales.filter(categoria__isnull=True)
    elif categoria:
        canales = canales.filter(categoria_id=categoria)
    if idioma == 'sin_dato':
        canales = canales.filter(idioma='')
    elif idioma:
        canales = canales.filter(idioma=idioma)
    if estado == 'en_app':
        canales = canales.filter(activo=True, tiene_usable=True)
    elif estado == 'fuera':
        canales = canales.filter(activo=True, tiene_usable=False)
    elif estado == 'quitados':
        canales = canales.filter(activo=False)
    if contenido and secciones.es_valida(contenido):
        canales = canales.filter(contenido=contenido)
    if sin_logo:
        canales = canales.filter(logo='')
    if origen:
        canales = canales.filter(fuentes__origen=origen).distinct()
    return canales


def por_que_no_se_ve(canal):
    """Para el catálogo: '' si la app lo muestra, si no, el motivo."""
    if not canal.activo:
        return f'Quitado: {canal.motivo_quitado}' if canal.motivo_quitado else 'Quitado a mano.'
    if canal.tiene_usable:
        return ''
    if not canal.fuentes_total:
        return 'No tiene fuentes.'
    if canal.fuentes_caidas == canal.fuentes_total:
        return 'Todas sus fuentes están caídas.'
    if canal.fuentes_ocultas:
        oculta = next((f for f in canal.fuentes.all() if f.oculta_por_aparatos), None)
        if oculta:
            vuelve = timezone.localtime(oculta.vuelve_a_probarse)
            return (f'Oculto un rato porque no se reproduce en los aparatos ({oculta.falla_en_aparatos}). '
                    f'Vuelve solo a la app el {vuelve:%d/%m} a las {vuelve:%H:%M}.')
    return 'Sus fuentes están apagadas a mano o son de un formato que la app no reproduce.'


def categorias_con_canales(contenido=''):
    """
    Las categorías que tienen algo (sin contar lo borrado), con cuántos.
    Con `contenido`, solo las de ese contenido: en la pestaña "En vivo" no
    aparece "SERIES | NETFLIX" (no tiene ningún canal en vivo).
    """
    filtro = Q(canales__eliminado_en__isnull=True)
    if contenido:
        filtro &= Q(canales__contenido=contenido)
    return Categoria.objects.annotate(cantidad=Count('canales', filter=filtro)).filter(cantidad__gt=0)


def origenes(contenido=''):
    """De qué listas vinieron las fuentes (para filtrar el catálogo); con `contenido`, solo las que trajeron eso."""
    fuentes = Fuente.objects.exclude(origen='').filter(canal__eliminado_en__isnull=True)
    if contenido:
        fuentes = fuentes.filter(canal__contenido=contenido)
    return fuentes.order_by('origen').values_list('origen', flat=True).distinct()
