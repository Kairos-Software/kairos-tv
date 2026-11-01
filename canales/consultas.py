"""
Lo que el sistema BUSCA de los canales (capa Base).
"""

from dataclasses import dataclass, field
from functools import cached_property

from django.db import connection, transaction
from django.db.models import (BigIntegerField, Case, Count, Exists, F, Max, Min, OuterRef, Prefetch, Q, Value,
                              When)
from django.db.models.functions import Cast, Coalesce
from django.utils import timezone

from . import clasificar, imagenes, secciones, youtube
from .models import (CORTES_POR_HORA_TOLERABLES, MINIMO_VISTO_PARA_JUZGAR, PROPORCION_PANTALLA_COMPLETA,
                     VELOCIDAD_SOBRADA, Canal, Categoria, Contenido, Fuente, Importacion)

# Lo que el reproductor de la app sabe reproducir. La app nueva lo dice al
# pedir los canales (?formatos=hls,dash,directo,rtsp,youtube,pagina); la
# 1.0.0 no dice nada y solo sabe HLS: a esa se le manda solo HLS (si no,
# mostraría canales que no puede abrir).
TIPOS_QUE_REPRODUCE_LA_APP = [Fuente.Tipo.HLS, Fuente.Tipo.DASH, Fuente.Tipo.DIRECTO, Fuente.Tipo.RTSP,
                              Fuente.Tipo.YOUTUBE, Fuente.Tipo.PAGINA, Fuente.Tipo.YT_VIDEO, Fuente.Tipo.WEB]
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

    @cached_property
    def capitulos(self):
        """Se arma la primera vez que se pide (series() ya terminó de llenar las temporadas)."""
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


def anotar_series(tanda=2000):
    """
    Anota en los canales que cambiaron de nombre desde la última vez de qué serie, temporada y
    capítulo son (Canal.serie: lo que dice clasificar.episodio). Se llama antes de cada consulta
    que agrupa por serie: casi siempre no hay ninguno (preguntarlo usa un índice que tiene solo
    esos) y, después de importar o renombrar, son los de ese cambio. También los borrados: si se
    restauran, ya están anotados.
    `skip_locked`: si dos pedidos anotan a la vez, cada uno hace los que el otro no está haciendo.
    """
    ultimo = 0
    while True:
        with transaction.atomic():
            pendientes = list(Canal.todos.select_for_update(skip_locked=True).exclude(serie_leida_de=F('nombre'))
                              .filter(pk__gt=ultimo).order_by('pk').values_list('pk', 'nombre')[:tanda])
            if not pendientes:
                return
            guardar_anotaciones(connection, Canal._meta.db_table, pendientes)
        if len(pendientes) < tanda:
            return
        ultimo = pendientes[-1][0]


def guardar_anotaciones(conexion, tabla, canales):
    """
    Anota [(pk, nombre), ...] con un solo UPDATE ... FROM (VALUES ...). Con bulk_update (un CASE por
    canal en cada campo) anotar 77.000 canales tardaba 2 minutos. Usa la tabla y no el modelo: así la
    puede usar también la migración 0030 (que tiene el modelo de ese momento).
    """
    filas = []
    for pk, nombre in canales:
        serie, temporada, capitulo, _ = clasificar.episodio(nombre)
        filas.extend([pk, serie.lower()[:120], temporada, capitulo, nombre])
    valores = ', '.join(['(%s::bigint, %s, %s::smallint, %s::integer, %s)'] * len(canales))
    tabla = conexion.ops.quote_name(tabla)
    with conexion.cursor() as cursor:
        cursor.execute(f'UPDATE {tabla} AS c SET serie = v.serie, temporada = v.temporada, capitulo = v.capitulo, '
                       f'serie_leida_de = v.nombre FROM (VALUES {valores}) '
                       f'AS v(id, serie, temporada, capitulo, nombre) WHERE c.id = v.id', filas)


def series(texto='', estado='', categoria='', idioma='', origen='', sin_logo=False, clave=None):
    """
    Las series armadas a partir de los capítulos sueltos ("Show S01 E02"),
    con la misma regla que la app (clasificar.episodio), con CADA capítulo y
    sus números del catálogo (fuentes, cuáles andan, si la app lo ve). Para
    una sola serie (`clave`: su nombre, sin importar mayúsculas) o pocas: para
    listarlas todas está resumen_de_series, que no arma cada capítulo.
      estado: 'en_app' (la app la muestra: ver Serie.completa) | 'incompleta' (se ven
              capítulos, pero la app no la muestra) | 'fuera' (no se ve ninguno) | '' (todas)
      categoria, idioma, origen, sin_logo: como en el catálogo (se aplican a los capítulos)
    """
    capitulos = catalogo(contenido=Contenido.SERIE, texto=texto, categoria=categoria, idioma=idioma, origen=origen,
                         sin_logo=sin_logo).prefetch_related(None)
    if clave is not None:
        anotar_series()
        capitulos = capitulos.filter(serie=clave.strip().lower())
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
    return _con_estado(resultado, estado)


def _con_estado(series_, estado):
    """Las de ese `estado` (ver series())."""
    if estado == 'en_app':
        return [s for s in series_ if s.completa]
    if estado == 'incompleta':
        return [s for s in series_ if s.en_la_app and not s.completa]
    if estado == 'fuera':
        return [s for s in series_ if not s.en_la_app]
    return series_


@dataclass
class SerieResumida:
    """
    Una serie con lo que Organizar muestra de ella, sin sus capítulos (ver
    resumen_de_series). Los mismos nombres que Serie.
    """
    nombre: str
    clave: str                  # el nombre en minúsculas (Canal.serie)
    categoria: str              # la de su primer capítulo (en el orden de las categorías de la app)
    categoria_id: int | None
    logo: str                   # la portada, o la imagen del primer capítulo que tenga
    portada: str
    cantidad: int
    en_la_app: int              # cuántos capítulos ve la app
    tiene_el_primero: bool      # entre los que se ven está el T1:E1
    activo: bool                # alguno se muestra en la app (si no, está quitada)
    destacado: bool             # alguno está destacado en la TV
    senales_fuera: bool         # algún capítulo tiene señales que la app no recibe
    capitulos_sin_imagen: bool
    numeros_de_temporada: list

    @property
    def fuera(self):
        return self.cantidad - self.en_la_app

    @property
    def completa(self):
        """La app la muestra si entre los capítulos que se ven está el T1:E1."""
        return not self.por_que_no_se_ve

    @property
    def por_que_no_se_ve(self):
        """Por qué la app no muestra la serie ('' = sí la muestra). Igual que Serie.por_que_no_se_ve."""
        if not self.en_la_app:
            return 'No se ve ningún capítulo.'
        if not self.tiene_el_primero:
            return 'Falta el capítulo 1 de la temporada 1: la app no muestra series que no se pueden empezar.'
        return ''


def capitulos_filtrados(texto='', categoria='', idioma='', origen='', sin_logo=False, clave=None):
    """Los capítulos (Canal) con los filtros del catálogo, sin sus números (como catalogo(), pero sin armarlos)."""
    capitulos = Canal.objects.filter(contenido=Contenido.SERIE)
    if texto:
        capitulos = capitulos.filter(_buscar(texto))
    if categoria == 'ninguna':
        capitulos = capitulos.filter(categoria__isnull=True)
    elif categoria:
        capitulos = capitulos.filter(categoria_id=categoria)
    if idioma == 'sin_dato':
        capitulos = capitulos.filter(idioma='')
    elif idioma:
        capitulos = capitulos.filter(idioma=idioma)
    if sin_logo:
        capitulos = capitulos.filter(logo='')
    if origen:
        capitulos = capitulos.filter(pk__in=Fuente.objects.filter(origen=origen).values('canal'))
    if clave is not None:
        capitulos = capitulos.filter(serie=clave.strip().lower())
    return capitulos


def series_de_los_capitulos(filas):
    """
    {serie: su nombre como está escrito en el capítulo} de las filas agrupadas por serie (con el pk de uno
    de sus capítulos en 'un_capitulo'). Las consultas que agrupan piden el pk de un capítulo de cada serie
    y no su nombre: comparar nombres con las reglas del idioma (MIN(nombre)) era lo que más tardaba en la
    base. Si ese capítulo se borró justo en el medio, queda la serie en minúsculas.
    """
    filas = list(filas)
    escritos = dict(Canal.todos.filter(pk__in=[fila['un_capitulo'] for fila in filas]).values_list('pk', 'nombre'))
    return {fila['serie']: clasificar.episodio(escritos[fila['un_capitulo']])[0] if fila['un_capitulo'] in escritos
            else fila['serie'] for fila in filas}


# Para la primera imagen: el lugar de un capítulo en su serie como UN número (temporada, número y pk)
_POR_TEMPORADA, _POR_PK = 100_000, 1_000_000_000


def primera_imagen():
    """
    Para agrupar por serie: cuál es el primer capítulo con imagen (por temporada y número; los sin número
    al final, como en series()), como un número que después lee imagenes_primeras. Es el MÍNIMO de
    (temporada, número, pk) escritos como un solo número: así la base no tiene que ordenar los capítulos
    (con un ARRAY_AGG ordenado, con 300.000 capítulos ordenaba en el disco y tardaba segundos).
    """
    lugar = ((Cast('temporada', BigIntegerField()) * _POR_TEMPORADA + Coalesce('capitulo', _POR_TEMPORADA - 1))
             * _POR_PK + F('pk'))
    return Min(lugar, filter=~Q(logo=''), output_field=BigIntegerField())


def imagenes_primeras(filas):
    """{serie: imagen} de las filas agrupadas con primera_imagen() en 'imagen' (sin imagen: no está)."""
    pks = {fila['serie']: fila['imagen'] % _POR_PK for fila in filas if fila['imagen'] is not None}
    logos = dict(Canal.todos.filter(pk__in=list(pks.values())).values_list('pk', 'logo'))
    return {serie: logos[pk] for serie, pk in pks.items() if logos.get(pk)}


def primera_categoria(categorias, orden):
    """
    De las categorías de los capítulos de una serie, la primera en el orden de la app (sin categoría: la
    última). Es la de la serie: la de su primer capítulo, como en series().
    """
    return min(categorias or [None], key=lambda pk: orden.get(pk, len(orden)))


def orden_de_categorias():
    """{pk: lugar} de todas las categorías, en el orden de la app (ORDEN_DE_CATEGORIAS)."""
    return {pk: i for i, pk in enumerate(Categoria.objects.order_by('orden', 'nombre').values_list('pk', flat=True))}


def _categorias_y_temporadas(capitulos):
    """({serie: {categorías de sus capítulos}}, {serie: {sus temporadas}}) de esos capítulos."""
    categorias, temporadas = {}, {}
    for serie, categoria_id, temporada in capitulos.values_list('serie', 'categoria_id', 'temporada').distinct():
        categorias.setdefault(serie, set()).add(categoria_id)
        temporadas.setdefault(serie, set()).add(temporada)
    return categorias, temporadas


def resumen_de_series(texto='', estado='', categoria='', idioma='', origen='', sin_logo=False, clave=None):
    """
    Las series (SerieResumida) con lo mismo que series() dice de cada una, pero sin armar cada capítulo:
    la base agrupa los capítulos por su serie (Canal.serie, ver anotar_series) y devuelve una fila por
    serie con sus números. Con decenas de miles de capítulos, traerlos todos para agruparlos acá
    tardaba segundos (y crecía con cada capítulo cargado). Los mismos filtros que series().
    """
    anotar_series()
    ahora = timezone.now()
    capitulos = capitulos_filtrados(texto, categoria, idioma, origen, sin_logo, clave).order_by()
    filas = list(capitulos.values('serie').annotate(
        un_capitulo=Min('pk'), cantidad=Count('pk'), activos=Count('pk', filter=Q(activo=True)),
        destacados=Count('pk', filter=Q(destacado=True)), sin_imagen=Count('pk', filter=Q(logo='')),
        imagen=primera_imagen()))
    # Los que ve la app y los que tienen señales que no recibe, en consultas aparte (WHERE pk IN ...): así la
    # base cruza los capítulos con las fuentes de una vez. Dentro de un COUNT(...) FILTER, "pk IN (fuentes)"
    # recorría la lista entera por cada capítulo si no entraba en la memoria de trabajo (con 300.000
    # capítulos, más de una hora) y "tiene alguna" (EXISTS) era una búsqueda por capítulo (segundos)
    vistos = {fila['serie']: fila for fila in capitulos.filter(activo=True, pk__in=fuentes_usables().values('canal_id'))
              .values('serie').annotate(en_la_app=Count('pk'), primeros=Count('pk', filter=Q(temporada=1, capitulo=1)))}
    # Las señales que la app no recibe (como fuentes_fuera de catalogo()): apagadas, caídas u ocultas
    fuera = Fuente.objects.filter(Q(activa=False) | Q(estado=Fuente.Estado.CAIDA) | Q(oculta_hasta__gt=ahora))
    con_senales_fuera = set(capitulos.filter(pk__in=fuera.values('canal_id')).values_list('serie', flat=True)
                            .distinct())
    # Las categorías y las temporadas de cada una, aparte: como listas (ARRAY_AGG) en la misma consulta, la
    # base tardaba el doble que con todo lo demás junto
    categorias, temporadas = _categorias_y_temporadas(capitulos)
    nombres_de_series = series_de_los_capitulos(filas)
    primeras = imagenes_primeras(filas)
    orden = orden_de_categorias()
    nombres = dict(Categoria.objects.values_list('pk', 'nombre'))
    resultado = []
    for fila in filas:
        # .get(): si justo entre una consulta y la otra se importó o borró algo, no falla
        categoria_id = primera_categoria(categorias.get(fila['serie']), orden)
        resultado.append(SerieResumida(
            nombre=nombres_de_series[fila['serie']], clave=fila['serie'],
            categoria=nombres.get(categoria_id, ''), categoria_id=categoria_id, logo=primeras.get(fila['serie'], ''),
            portada='', cantidad=fila['cantidad'], en_la_app=vistos.get(fila['serie'], {}).get('en_la_app', 0),
            tiene_el_primero=vistos.get(fila['serie'], {}).get('primeros', 0) > 0,
            activo=fila['activos'] > 0, destacado=fila['destacados'] > 0,
            senales_fuera=fila['serie'] in con_senales_fuera, capitulos_sin_imagen=fila['sin_imagen'] > 0,
            numeros_de_temporada=sorted(temporadas.get(fila['serie'], ()))))
    resultado.sort(key=lambda s: s.nombre.lower())
    portadas = imagenes.portadas_de([s.nombre for s in resultado])
    for serie in resultado:
        serie.portada = portadas.get(serie.nombre, '')
        serie.logo = serie.portada or serie.logo
    if sin_logo:
        resultado = [s for s in resultado if not s.portada]
    return _con_estado(resultado, estado)


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
    anotar_series()
    capitulos = Canal.objects.filter(contenido=Contenido.SERIE).order_by()
    filas = list(capitulos.values('serie').annotate(un_capitulo=Min('pk')))
    nombres = series_de_los_capitulos(filas)
    series = {fila['serie']: {'nombre': nombres[fila['serie']], 'categorias': {}, 'temporadas': []} for fila in filas}
    # Si justo entre una consulta y la otra se importó una serie, no está en `series`: se saltea
    for fila in capitulos.values('serie', 'categoria_id').annotate(cantidad=Count('pk')):
        if fila['serie'] in series:
            series[fila['serie']]['categorias'][fila['categoria_id']] = fila['cantidad']
    for fila in (capitulos.values('serie', 'temporada').annotate(cantidad=Count('pk'), ultimo=Max('capitulo'))
                 .order_by('temporada')):
        if fila['serie'] in series:
            series[fila['serie']]['temporadas'].append([fila['temporada'], fila['cantidad'], fila['ultimo'] or 0])
    grupos = {c.pk: {'nombre': c.nombre, 'series': []}
              for c in Categoria.objects.filter(contenido=Contenido.SERIE).order_by('orden', 'nombre')}
    sin_categoria = {'nombre': '', 'series': []}
    orden = orden_de_categorias()
    for datos in sorted(series.values(), key=lambda d: d['nombre'].lower()):
        # La de la mayoría de sus capítulos (si empatan, la primera en el orden de la app)
        categoria = min(datos['categorias'] or [None],
                        key=lambda pk: (-datos['categorias'].get(pk, 0), orden.get(pk, len(orden))))
        grupos.get(categoria, sin_categoria)['series'].append(
            {'nombre': datos['nombre'], 'temporadas': datos['temporadas']})
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
    'senales': 'Se ve, pero tiene señales que no andan',
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
    elif mostrar == 'senales':
        canales = canales.filter(activo=True, tiene_usable=True, fuentes_fuera__gt=0)
    return canales


def organizar_contenido(contenido=Contenido.VIVO, mostrar='todo', texto='', origen='', sin_logo=False, idioma='',
                        categoria='', pagina=None, por_pagina=120, series_armadas=None):
    """
    Todo lo cargado de una sección (en vivo, películas o series), por categoría:
      mostrar: una de MOSTRAR ('fuera' = 'caidos' + 'quitados')
      idioma: 'es' | 'otro' | 'sin_dato' | '' (todos)
      categoria: 'todas' | 'ninguna' | pk ('' = todas)
      series_armadas: en Series, las de resumen_de_series(texto, origen, idioma) si ya se
                      armaron (la vista las arma una vez para esto y para los chips de arriba)
    """
    from django.core.paginator import Paginator

    if contenido == Contenido.SERIE:
        if series_armadas is None or sin_logo:
            items = resumen_de_series(texto=texto, origen=origen, sin_logo=sin_logo, idioma=idioma)
        else:
            items = list(series_armadas)
        if mostrar == 'app':
            items = [s for s in items if s.completa]
        elif mostrar == 'fuera':
            items = [s for s in items if not s.completa]
        elif mostrar == 'caidos':
            items = [s for s in items if not s.completa and s.activo]
        elif mostrar == 'quitados':
            items = [s for s in items if not s.activo]
        elif mostrar == 'destacados':
            items = [s for s in items if s.destacado]
        elif mostrar == 'senales':
            items = [s for s in items if s.completa and s.senales_fuera]
        pares = [(s, s.categoria_id) for s in items]
    else:
        canales = canales_filtrados(contenido, mostrar, texto=texto, origen=origen, sin_logo=sin_logo, idioma=idioma)
        pares = list(canales.values_list('pk', 'categoria_id'))

    cuantos = {}
    for _, categoria_id in pares:
        cuantos[categoria_id] = cuantos.get(categoria_id, 0) + 1
    # Sin order_by(): con el orden de siempre (por nombre), el DISTINCT comparaba los nombres de todo el
    # catálogo (con 77.000 canales, 1,2 segundos en cada página de Organizar)
    con_algo = set(Canal.objects.exclude(categoria=None).order_by().values_list('categoria_id', flat=True)
                   .distinct())
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


def cuentas_de_organizar(contenido=Contenido.VIVO, texto='', origen='', idioma='', categoria='todas',
                         series_armadas=None):
    """
    Cuántos hay de cada filtro de arriba de Organizar (los chips: lo que queda por hacer), con la búsqueda y la
    categoría que se están viendo. Cada número es lo que se ve al tocar ese chip:
      {'todo': 120, 'app': 100, 'fuera': 7, 'caidos': 4, 'quitados': 3, 'senales': 12, 'destacados': 4, 'sin_logo': 34}
    """
    if contenido == Contenido.SERIE:
        todas = (list(series_armadas) if series_armadas is not None
                 else resumen_de_series(texto=texto, origen=origen, idioma=idioma))
        if categoria == 'ninguna':
            todas = [s for s in todas if not s.categoria_id]
        elif str(categoria).isdigit():
            todas = [s for s in todas if s.categoria_id == int(categoria)]
        return {
            'todo': len(todas),
            'app': sum(1 for s in todas if s.completa),
            'fuera': sum(1 for s in todas if not s.completa),
            'caidos': sum(1 for s in todas if not s.completa and s.activo),
            'quitados': sum(1 for s in todas if not s.activo),
            'senales': sum(1 for s in todas if s.completa and s.senales_fuera),
            'destacados': sum(1 for s in todas if s.destacado),
            # Como el filtro "Solo sin imagen": sin portada y con capítulos sin imagen
            'sin_logo': sum(1 for s in todas if not s.portada and s.capitulos_sin_imagen),
        }

    def de_la_categoria(canales):
        if categoria == 'ninguna':
            return canales.filter(categoria__isnull=True)
        if str(categoria).isdigit():
            return canales.filter(categoria_id=int(categoria))
        return canales
    filtros = {'texto': texto, 'origen': origen, 'idioma': idioma}
    cuentas = {mostrar: de_la_categoria(canales_filtrados(contenido, mostrar, **filtros)).count() for mostrar in MOSTRAR}
    cuentas['sin_logo'] = de_la_categoria(canales_filtrados(contenido, sin_logo=True, **filtros)).count()
    return cuentas


def nombres_de_series():
    """
    [(nombre, categoría), ...] de cada serie, por nombre (como Organizar), sin armar las series: la base
    agrupa los capítulos por serie (Canal.serie). La categoría es la de su primer capítulo, como en series().
    """
    anotar_series()
    series = {}   # {serie: (el primer capítulo, {sus categorías})}
    for fila in (Canal.objects.filter(contenido=Contenido.SERIE).order_by().values('serie', 'categoria_id')
                 .annotate(un_capitulo=Min('pk'))):
        primero, categorias = series.get(fila['serie'], (fila['un_capitulo'], set()))
        series[fila['serie']] = (min(primero, fila['un_capitulo']), categorias | {fila['categoria_id']})
    nombres = series_de_los_capitulos({'serie': serie, 'un_capitulo': primero}
                                      for serie, (primero, _) in series.items())
    orden = orden_de_categorias()
    vistas = [(nombres[serie], primera_categoria(categorias, orden)) for serie, (_, categorias) in series.items()]
    return sorted(vistas, key=lambda par: par[0].lower())


def series_vecinas(nombre, nombres=None):
    """
    La serie anterior y la siguiente de la MISMA categoría, en el orden de Organizar (por nombre): para pasar de
    una a otra sin volver a la lista. (anterior, siguiente), cada una el nombre o ''.
    `nombres`: los de nombres_de_series(), si ya se pidieron.
    """
    todas = nombres_de_series() if nombres is None else nombres
    actual = next(((n, c) for n, c in todas if n.lower() == (nombre or '').lower()), None)
    if actual is None:
        return '', ''
    hermanas = [n for n, c in todas if c == actual[1]]
    posicion = hermanas.index(actual[0])
    return (hermanas[posicion - 1] if posicion else '',
            hermanas[posicion + 1] if posicion + 1 < len(hermanas) else '')


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
            # Las señales que la app no recibe: apagadas (a mano o retiradas por la limpieza), caídas u ocultas
            fuentes_fuera=Count('fuentes', filter=Q(fuentes__activa=False) | Q(fuentes__estado=Fuente.Estado.CAIDA)
                                | Q(fuentes__oculta_hasta__gt=timezone.now()), distinct=True),
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
