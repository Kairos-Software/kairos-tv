"""
Ordenar el contenido desde el panel: las categorías y el tipo de cada cosa.

Cada categoría es de UNA sección de la app: En vivo, Películas o Series (la
"Infantil" de los canales no es la "Infantil" de las películas).

Las categorías salen solas del "group-title" de cada lista, así que con
varias listas se juntan muchas parecidas ("Kids", "Infantil", "Animation;Kids").
Acá se crean, renombran, JUNTAN, borran y ordenan. Lo que se junta o renombra
no se pierde: el nombre viejo queda en `otros_nombres`, y la próxima lista
que diga "Kids" va directo a la categoría donde se juntó "Kids" (ver
categoria_por_nombre, que usa la importación).

También se cambia el tipo (en vivo / película / serie) de lo que se importó
mal, y se juntan películas sueltas (o series de un capítulo) como UNA serie
numerada.

    from canales import organizar
    organizar.categoria_por_nombre('Kids', 'vivo')                -> Categoria (la crea si no existe)
    organizar.juntar_categorias([kids, infantil], 'Infantil')      -> Categoria "Infantil"
    organizar.mover_a_categoria(canales, noticias)                 -> cuántos se movieron
    organizar.cambiar_contenido(canales, 'serie', nombre_serie='Pocoyó')
    organizar.ordenar_capitulos('Pocoyó', 1, [pk, pk, ...])        -> los renumera 1, 2, 3... en ese orden
    organizar.categorias_parecidas(categorias)                     -> [[cat, cat], ...] posibles repetidas
    organizar.borrar_categoria(infantil, con_contenido=True)       -> la borra con todo lo de adentro
    organizar.eliminar_contenido(canales)                          -> los borra (si se vuelven a importar, vuelven)
    organizar.eliminados_recientes() / restaurar_eliminados(pk)    -> deshacer una eliminación
"""

import re
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Min, Q
from django.utils import timezone

from actividad.models import Accion
from actividad.registro import registrar

from . import clasificar, imagenes, secciones
from .models import Canal, Categoria, Contenido, EntradaImportada, Fuente, medidas_de_calidad


class NoSePuede(Exception):
    """Algo que se pidió no tiene sentido (se le muestra el mensaje a la persona)."""


def _clave(nombre):
    """Para comparar nombres: sin acentos, sin mayúsculas, sin espacios de más."""
    return ' '.join(clasificar.sin_acentos(nombre or '').split())


def _limpio(nombre, largo=80):
    return ' '.join((nombre or '').split())[:largo]


def _otros(categoria):
    return [n for n in (categoria.otros_nombres or '').splitlines() if n.strip()]


def _sumar_otros(categoria, nombres):
    """Agrega nombres a `otros_nombres` (sin repetir, ni el nombre actual)."""
    actuales = _otros(categoria)
    vistos = {_clave(n) for n in actuales} | {_clave(categoria.nombre)}
    for nombre in nombres:
        if nombre.strip() and _clave(nombre) not in vistos:
            actuales.append(nombre.strip())
            vistos.add(_clave(nombre))
    categoria.otros_nombres = '\n'.join(actuales)


def _usuario(usuario):
    return usuario if getattr(usuario, 'pk', None) else None


def nombre_de_seccion(contenido):
    return secciones.nombre(contenido)


# ── Encontrar (o crear) una categoría por nombre ─────────────────────

def indice_de_categorias():
    """{(sección, nombre comparable): Categoria}, con sus nombres y sus otros nombres."""
    indice = {}
    todas = list(Categoria.objects.all())
    for categoria in todas:
        for nombre in _otros(categoria):
            indice.setdefault((categoria.contenido, _clave(nombre)), categoria)
    for categoria in todas:   # el nombre propio manda sobre un "otro nombre" de otra
        indice[(categoria.contenido, _clave(categoria.nombre))] = categoria
    return indice


def categoria_por_nombre(nombre, contenido=Contenido.VIVO, indice=None, usuario=None):
    """
    La categoría de esa sección que se llama así (sin importar mayúsculas ni
    acentos) o que lo tiene entre sus otros nombres. Si no hay, la crea.
    `indice`: el de indice_de_categorias(), para no consultarlo cada vez (se actualiza solo).
    """
    nombre = _limpio(nombre)
    if not nombre:
        return None
    if indice is None:
        indice = indice_de_categorias()
    categoria = indice.get((contenido, _clave(nombre)))
    if categoria is None:
        categoria = Categoria(nombre=nombre, contenido=contenido)
        categoria.marcar_autor(usuario)
        categoria.save()
        indice[(contenido, _clave(nombre))] = categoria
    return categoria


# ── Las categorías ───────────────────────────────────────────────────

def categorias_con_cantidades(contenido=None):
    """Las categorías (de una sección, o todas) con cuántas cosas tienen (sin contar lo borrado)."""
    categorias = Categoria.objects.annotate(
        total=Count('canales', filter=Q(canales__eliminado_en__isnull=True)))
    if contenido:
        categorias = categorias.filter(contenido=contenido)
    return categorias.order_by('orden', 'nombre')


def crear_categoria(nombre, contenido=Contenido.VIVO, usuario=None):
    nombre = _limpio(nombre)
    if not nombre:
        raise NoSePuede('Escribí el nombre de la categoría.')
    if (contenido, _clave(nombre)) in indice_de_categorias():
        raise NoSePuede(f'Ya hay una categoría "{nombre}" en {nombre_de_seccion(contenido)} (o una que se llamaba así).')
    categoria = categoria_por_nombre(nombre, contenido, usuario=usuario)
    registrar(usuario, Accion.CREAR, f'Creó la categoría "{categoria}" en {nombre_de_seccion(contenido)}.',
              objeto=categoria, modulo='canales')
    return categoria


@transaction.atomic
def renombrar_categoria(categoria, nuevo, usuario=None):
    """
    Le cambia el nombre (el viejo queda como "otro nombre": las listas que lo
    traigan siguen yendo acá). Si en la misma sección ya hay otra con el nombre
    nuevo, se juntan.
    """
    nuevo = _limpio(nuevo)
    if not nuevo:
        raise NoSePuede('Escribí el nombre nuevo.')
    otra = next((c for c in Categoria.objects.filter(contenido=categoria.contenido).exclude(pk=categoria.pk)
                 if _clave(c.nombre) == _clave(nuevo)), None)
    if otra is not None:
        return juntar_categorias([categoria, otra], otra.nombre, usuario)
    viejo = categoria.nombre
    categoria.nombre = nuevo
    _sumar_otros(categoria, [viejo])
    categoria.marcar_autor(usuario)
    categoria.save()
    registrar(usuario, Accion.EDITAR, f'Renombró la categoría "{viejo}" a "{nuevo}".', objeto=categoria,
              modulo='canales')
    return categoria


@transaction.atomic
def juntar_categorias(categorias, destino, usuario=None):
    """
    Pasa todo lo de `categorias` (de la misma sección) a la categoría
    `destino` (un nombre: una de ellas, otra que ya existe o una nueva) y
    borra las demás. Sus nombres quedan como "otros nombres" del destino: las
    listas futuras que los traigan van al destino.
    """
    categorias = [c for c in categorias if c is not None]
    destino_nombre = _limpio(destino)
    if not destino_nombre:
        raise NoSePuede('Escribí o elegí en qué categoría juntarlas.')
    if not categorias or (len(categorias) < 2 and _clave(destino_nombre) == _clave(categorias[0].nombre)):
        raise NoSePuede('Elegí al menos dos categorías para juntar.')
    de_que_secciones = {c.contenido for c in categorias}
    if len(de_que_secciones) > 1:
        raise NoSePuede('Solo se pueden juntar categorías de la misma sección.')
    contenido = de_que_secciones.pop()
    final = next((c for c in categorias if _clave(c.nombre) == _clave(destino_nombre)), None)
    if final is None:
        final = (next((c for c in Categoria.objects.filter(contenido=contenido)
                       if _clave(c.nombre) == _clave(destino_nombre)), None)
                 or categoria_por_nombre(destino_nombre, contenido, usuario=usuario))
    juntadas = []
    for categoria in categorias:
        if categoria.pk == final.pk:
            continue
        Canal.todos.filter(categoria=categoria).update(categoria=final, modificado=timezone.now())
        _sumar_otros(final, [categoria.nombre, *_otros(categoria)])
        categoria.eliminar(usuario)
        juntadas.append(categoria.nombre)
    if final.nombre != destino_nombre and _clave(final.nombre) == _clave(destino_nombre):
        final.nombre = destino_nombre   # mismo nombre con otras mayúsculas: queda como lo escribió
    final.marcar_autor(usuario)
    final.save()
    if juntadas:
        registrar(usuario, Accion.EDITAR, f'Juntó las categorías {", ".join(juntadas)} en "{final}".',
                  objeto=final, modulo='canales')
    return final


@transaction.atomic
def borrar_categoria(categoria, usuario=None, con_contenido=False):
    """
    La borra. Sin `con_contenido`, lo que tenía queda "Sin categoría" (en la
    app, en "Otros"). Con `con_contenido`, se elimina también todo lo que
    tenía. Devuelve cuántos tenía.
    """
    if con_contenido:
        cantidad = eliminar_contenido(Canal.objects.filter(categoria=categoria), usuario)
    else:
        cantidad = Canal.todos.filter(categoria=categoria).update(categoria=None, modificado=timezone.now())
    categoria.eliminar(usuario)
    detalle = (f'con todo su contenido ({cantidad} eliminados)' if con_contenido
               else f'({cantidad} quedaron sin categoría)')
    registrar(usuario, Accion.ELIMINAR, f'Borró la categoría "{categoria}" {detalle}.', objeto=categoria,
              modulo='canales')
    return cantidad


def ordenar_categorias(ordenes, usuario=None):
    """{pk: orden} -> guarda el orden (menor = aparece primero en la app). Devuelve cuántas cambiaron."""
    cambiadas = 0
    for categoria in Categoria.objects.filter(pk__in=list(ordenes)):
        orden = max(0, int(ordenes[categoria.pk]))
        if categoria.orden != orden:
            categoria.orden = orden
            categoria.marcar_autor(usuario)
            categoria.save(update_fields=['orden', 'modificado', 'modificado_por'])
            cambiadas += 1
    if cambiadas:
        registrar(usuario, Accion.EDITAR, f'Cambió el orden de {cambiadas} categoría(s).', modulo='canales')
    return cambiadas


# Para sugerir categorías repetidas: palabras que no cambian de qué se trata,
# y nombres en inglés que son lo mismo que uno en castellano.
_RELLENO = {'hd', 'fhd', 'uhd', 'sd', '4k', 'tv', 'canal', 'canales', 'channel', 'channels', 'vod', 'de', 'del',
            'y', 'and', 'the', 'la', 'las', 'los', 'el', 'en', 'vivo', 'live', '24', '7', 'h', 'ar', 'arg', 'es',
            'mx', 'co', 'cl', 'pe', 'us', 'usa', 'uk', 've', 'uy', 'py', 'bo', 'ec', 'latam', 'latino', 'latin'}
_SINONIMOS = {'kids': 'infantil', 'kid': 'infantil', 'ninos': 'infantil', 'nino': 'infantil', 'infantiles': 'infantil',
              'sports': 'deporte', 'sport': 'deporte', 'deportes': 'deporte', 'deportivo': 'deporte',
              'news': 'noticia', 'noticias': 'noticia', 'informativo': 'noticia', 'movies': 'pelicula',
              'movie': 'pelicula', 'peliculas': 'pelicula', 'cine': 'pelicula', 'films': 'pelicula',
              'music': 'musica', 'musical': 'musica', 'documentary': 'documental', 'documentales': 'documental',
              'entertainment': 'entretenimiento', 'series': 'serie', 'religious': 'religion', 'religiosos': 'religion',
              'religioso': 'religion', 'cultura': 'cultural', 'culture': 'cultural', 'general': 'general',
              'animation': 'infantil', 'animacion': 'infantil', 'dibujos': 'infantil', 'comedy': 'comedia',
              'novelas': 'novela', 'telenovelas': 'novela', 'telenovela': 'novela'}


def clave_parecida(nombre):
    """'DEPORTES HD' / 'Sports' / 'AR | Deportes' -> 'deporte'. '' si no queda nada que comparar."""
    palabras = re.split(r'[^a-z0-9]+', clasificar.sin_acentos(nombre or ''))
    utiles = []
    for palabra in palabras:
        if not palabra or palabra in _RELLENO:
            continue
        palabra = _SINONIMOS.get(palabra, palabra)
        if len(palabra) > 4 and palabra.endswith('s') and palabra not in ('series',):
            palabra = palabra[:-1]
        if palabra not in utiles:
            utiles.append(palabra)
    return ' '.join(sorted(utiles))


def categorias_parecidas(categorias):
    """
    Grupos de categorías (de una misma sección) que parecen la misma:
    [[Infantil, Kids, Animation;Kids], ...]. "Animation;Kids" cuenta como
    parecida a "Kids" porque comparten de qué se tratan.
    """
    grupos = {}
    for categoria in categorias:
        clave = clave_parecida(categoria.nombre.replace(';', ' '))
        for palabra in clave.split() if clave else []:
            grupos.setdefault((categoria.contenido, palabra), []).append(categoria)
    # Un grupo por palabra; se descartan los de una sola y los que repiten otro grupo
    vistos, resultado = set(), []
    for grupo in sorted(grupos.values(), key=len, reverse=True):
        ids = frozenset(c.pk for c in grupo)
        if len(ids) > 1 and not any(ids <= otro for otro in vistos):
            vistos.add(ids)
            resultado.append(grupo)
    return resultado


# ── Mover y cambiar de tipo ──────────────────────────────────────────

def mover_a_categoria(canales, categoria, usuario=None):
    """
    Pone los elegidos en `categoria` (None = sin categoría). Solo mueve los de
    la misma sección que la categoría. Devuelve cuántos.
    """
    if categoria is not None:
        canales = canales.filter(contenido=categoria.contenido)
    cantidad = canales.exclude(categoria=categoria).update(
        categoria=categoria, modificado=timezone.now(), modificado_por=_usuario(usuario))
    if cantidad:
        registrar(usuario, Accion.EDITAR,
                  f'Movió {cantidad} a la categoría "{categoria or "Sin categoría"}".', modulo='canales')
    return cantidad


def _orden_natural(texto):
    """'Capítulo 10' va después de 'Capítulo 9' (los números se comparan como números)."""
    return [int(parte) if parte.isdigit() else parte for parte in re.split(r'(\d+)', clasificar.sin_acentos(texto))]


def titulo_del_capitulo(nombre, nombre_serie):
    """Lo que queda del nombre para usarlo como título del capítulo (sin la serie ni "S01 E02")."""
    serie, _, _, titulo = clasificar.episodio(nombre)
    titulo = titulo if titulo or serie != nombre else nombre
    titulo = re.sub(re.escape(nombre_serie), ' ', titulo, flags=re.I)
    titulo = re.sub(r'\(\s*\d{4}\s*\)', ' ', titulo)
    return ' '.join(titulo.split()).strip(' -:|.')


def nombre_de_serie_valido(nombre):
    """
    El nombre limpio para una serie nueva o unida. NoSePuede si está vacío o
    si tiene algo que la app tomaría como número de capítulo ("4x4 Aventuras",
    "Flash S2 E3"): los capítulos quedarían mal agrupados.
    """
    nombre = _limpio(nombre, 90).strip(' -:|._')
    if not nombre:
        raise NoSePuede('Escribí el nombre de la serie.')
    serie, temporada, numero, _ = clasificar.episodio(f'{nombre} S01 E01')
    if serie != nombre or (temporada, numero) != (1, 1):
        raise NoSePuede(f'El nombre "{nombre}" tiene algo que la app confundiría con un número de capítulo '
                        f'(como "S2 E5" o "4x4"). Escribilo de otra forma.')
    return nombre


def nombre_de_capitulo(nombre_serie, temporada, numero, titulo=''):
    """'Masha y el Oso', 1, 5, 'Sin amigos' -> 'Masha y el Oso S01 E05 Sin amigos' (como lo lee la app)."""
    return f'{nombre_serie} S{int(temporada):02d} E{int(numero):02d}{f" {titulo}" if titulo else ""}'[:120]


def ultimo_capitulo(nombre_serie, temporada=1, excluir=()):
    """
    El número de capítulo más alto que ya existe en esa temporada de la serie
    (0 si no hay ninguno), para seguir numerando desde ahí y no repetir.
    Compara el nombre como la app (sin mayúsculas, CON acentos: para la app
    "Pocoyo" y "Pocoyó" son dos series distintas).
    """
    buscada, ultimo = nombre_serie.strip().lower(), 0
    candidatos = (Canal.objects.filter(contenido=Contenido.SERIE, nombre__istartswith=nombre_serie.strip())
                  .exclude(pk__in=list(excluir)).values_list('nombre', flat=True))
    for nombre in candidatos:
        serie, de_temporada, numero, _ = clasificar.episodio(nombre)
        if serie.lower() == buscada and de_temporada == int(temporada) and numero:
            ultimo = max(ultimo, numero)
    return ultimo


@transaction.atomic
def cambiar_contenido(canales, contenido, nombre_serie='', temporada=1, usuario=None):
    """
    Cambia el tipo (en vivo / película / serie) de los elegidos. Pasan a esa
    sección con una categoría del mismo nombre (la crea si no existe).

    A serie con `nombre_serie`: además los renombra como capítulos de esa
    serie, numerados en el orden de sus nombres ("Pocoyó S01 E01 El tornado"...),
    para que la app los arme como UNA serie. Sin nombre solo se puede si ya
    dicen temporada y capítulo ("Arrow S02 E05"): si no, quedarían sin un
    T1:E1 identificable y la app no los mostraría.

    Devuelve cuántos cambiaron.
    """
    if not secciones.es_valida(contenido):
        raise NoSePuede('Esa sección no existe.')
    if contenido == Contenido.SERIE and _limpio(nombre_serie):
        nombre_serie = nombre_de_serie_valido(nombre_serie)
    else:
        nombre_serie = ''
    elegidos = sorted(canales.select_related('categoria'), key=lambda c: _orden_natural(c.nombre))
    if not elegidos:
        return 0
    if contenido == Contenido.SERIE and not nombre_serie:
        sueltos = [c.nombre for c in elegidos if clasificar.episodio(c.nombre)[2] is None]
        if sueltos:
            raise NoSePuede(f'Escribí el nombre de la serie: {len(sueltos)} de los elegidos no dicen temporada y '
                            f'capítulo (ej. "{sueltos[0][:40]}") y quedarían sin un T1:E1 que la app pueda mostrar.')
    ahora, quien, indice = timezone.now(), _usuario(usuario), indice_de_categorias()
    # Si la serie ya tiene capítulos (de otra tanda o importación), se sigue desde el último
    primero = ultimo_capitulo(nombre_serie, temporada, excluir=[c.pk for c in elegidos]) + 1 if nombre_serie else 1
    for numero, canal in enumerate(elegidos, start=primero):
        if canal.categoria is not None and canal.categoria.contenido != contenido:
            canal.categoria = categoria_por_nombre(canal.categoria.nombre, contenido, indice, usuario)
        canal.contenido = contenido
        if nombre_serie:
            canal.nombre = nombre_de_capitulo(nombre_serie, temporada, numero,
                                              titulo_del_capitulo(canal.nombre, nombre_serie))
        canal.modificado, canal.modificado_por = ahora, quien
    Canal.objects.bulk_update(elegidos, ['contenido', 'nombre', 'categoria', 'modificado', 'modificado_por'])
    detalle = f' como la serie "{nombre_serie}" (temporada {temporada})' if nombre_serie else ''
    registrar(usuario, Accion.EDITAR, f'Pasó {len(elegidos)} a {secciones.nombre(contenido)}{detalle}.',
              modulo='canales')
    return len(elegidos)


def capitulos_de(nombres_de_series):
    """Los capítulos (Canal) de esas series, por nombre de serie (como las arma la app)."""
    buscados = {_clave(n) for n in nombres_de_series if n.strip()}
    pks = [canal.pk for canal in Canal.objects.filter(contenido=Contenido.SERIE).only('pk', 'nombre')
           if _clave(clasificar.episodio(canal.nombre)[0]) in buscados]
    return Canal.objects.filter(pk__in=pks)


def unir_en_una_serie(nombres_de_series, nombre_serie, temporada=1, usuario=None, capitulos=None):
    """
    Junta varias series (por ejemplo, 239 "series" de un capítulo que eran
    videos sueltos) en UNA serie: todos sus capítulos quedan numerados en orden.
    `capitulos`: solo esos (los que se ven con un filtro); sin decirlo, todos los de esas series.
    """
    if not _limpio(nombre_serie):
        raise NoSePuede('Escribí el nombre de la serie que va a juntarlas.')
    if capitulos is None:
        capitulos = capitulos_de(nombres_de_series)
    cantidad = cambiar_contenido(capitulos, Contenido.SERIE, nombre_serie, temporada, usuario)
    for nombre in nombres_de_series:
        # Si alguna tenía portada, la serie unida se queda con ella (solo si pasó entera: si no, sigue siendo suya)
        if _clave(nombre) == _clave(nombre_serie) or not capitulos_de([nombre]).exists():
            imagenes.mover_portada(nombre, nombre_serie)
    return cantidad


@transaction.atomic
def eliminar_contenido(canales, usuario=None):
    """
    Elimina canales, películas o capítulos: dejan de existir en el panel y en
    la app (quedan en la base solo para las estadísticas). Sus direcciones se
    borran: si se vuelve a importar la lista, entran como nuevos. (Para que NO
    vuelvan, en vez de eliminarlos hay que "quitarlos".) Devuelve cuántos.
    """
    elegidos = list(canales.filter(eliminado_en__isnull=True))
    if not elegidos:
        return 0
    Fuente.objects.filter(canal__in=elegidos).delete()
    Canal.objects.filter(pk__in=[c.pk for c in elegidos]).update(
        eliminado_en=timezone.now(), eliminado_por=_usuario(usuario), modificado=timezone.now())
    nombres = ', '.join(c.nombre for c in elegidos[:3]) + (f' y {len(elegidos) - 3} más' if len(elegidos) > 3 else '')
    registrar(usuario, Accion.ELIMINAR, f'Eliminó {len(elegidos)}: {nombres}.', modulo='canales')
    return len(elegidos)


@dataclass
class Eliminacion:
    """Una vez que se eliminó contenido (todo lo que se eliminó junto tiene el mismo momento)."""
    muestra: int             # pk de uno de los eliminados: identifica a todos los de esa vez
    cuando: object
    quien: str
    cantidad: int
    nombres: list            # algunos, para reconocerla
    por_seccion: dict        # {nombre de la sección: cuántos}
    recuperables: int        # cuántos tienen sus señales anotadas en el informe de alguna lista


def eliminados_recientes(dias=30, limite=60):
    """Lo eliminado en los últimos `dias`, agrupado por cada vez que se eliminó (lo más nuevo primero)."""
    desde = timezone.now() - timedelta(days=dias)
    grupos = (Canal.todos.filter(eliminado_en__gte=desde).values('eliminado_en')
              .annotate(cantidad=Count('pk'), muestra=Min('pk')).order_by('-eliminado_en')[:limite])
    resultado = []
    for grupo in grupos:
        canales = Canal.todos.filter(eliminado_en=grupo['eliminado_en'])
        primero = canales.select_related('eliminado_por').first()
        por_seccion = {}
        for contenido, cantidad in canales.order_by().values_list('contenido').annotate(Count('pk')):
            por_seccion[secciones.nombre(contenido) or contenido] = cantidad
        resultado.append(Eliminacion(
            muestra=grupo['muestra'], cuando=grupo['eliminado_en'], cantidad=grupo['cantidad'],
            quien=str(primero.eliminado_por or 'alguien'),
            nombres=list(canales.order_by('nombre').values_list('nombre', flat=True)[:6]),
            por_seccion=por_seccion,
            recuperables=EntradaImportada.objects.filter(canal__in=canales, estado=EntradaImportada.Estado.AGREGADA)
            .values('canal').distinct().count(),
        ))
    return resultado


@dataclass
class Restauracion:
    restaurados: int = 0
    ya_estaban: int = 0      # se volvieron a importar después: ya hay uno igual
    sin_senales: int = 0     # agregados a mano (o con el informe de la lista borrado): sus señales no quedaron


@transaction.atomic
def restaurar_eliminados(muestra, usuario=None):
    """
    Deshace una eliminación (todo lo eliminado junto con `muestra`). Al
    eliminar, las señales se borran; se rearman con lo que quedó anotado en
    el informe de cada lista importada (dirección, formato, User-Agent...) y
    quedan "sin verificar": la app las intenta y la verificación las prueba.
    Si la categoría también se había borrado, vuelve (o, si ya hay otra con
    ese nombre, van a esa).
    """
    momento = Canal.todos.filter(pk=muestra, eliminado_en__isnull=False).values_list('eliminado_en', flat=True).first()
    resultado = Restauracion()
    if momento is None:
        return resultado
    en_uso = set(Fuente.objects.values_list('url', flat=True))
    activos = {(_clave(c.nombre), c.contenido) for c in Canal.objects.only('nombre', 'contenido')}
    categorias = {}
    for canal in Canal.todos.filter(eliminado_en=momento).select_related('categoria').order_by('pk'):
        if (_clave(canal.nombre), canal.contenido) in activos:
            resultado.ya_estaban += 1
            continue
        fuentes = []
        entradas = (EntradaImportada.objects.filter(canal=canal, estado=EntradaImportada.Estado.AGREGADA)
                    .select_related('importacion').order_by('importacion__creada', 'posicion'))
        for entrada in entradas:
            if entrada.url in en_uso:
                continue
            en_uso.add(entrada.url)
            fuentes.append(Fuente(canal=canal, url=entrada.url, tipo=entrada.tipo or Fuente.Tipo.HLS,
                                  prioridad=len(fuentes) + 1, origen=entrada.importacion.archivo[:150],
                                  user_agent=entrada.user_agent, referer=entrada.referer, codec=entrada.codec,
                                  calidad=entrada.calidad, **medidas_de_calidad(entrada.calidad),
                                  estado=Fuente.Estado.SIN_VERIFICAR))
        if not fuentes:
            resultado.sin_senales += 1
            continue
        categoria = canal.categoria
        if categoria is not None and categoria.eliminado_en is not None:
            if categoria.pk not in categorias:
                otra = Categoria.objects.filter(contenido=categoria.contenido, nombre=categoria.nombre).first()
                if otra is None:
                    categoria.restaurar(usuario)
                categorias[categoria.pk] = otra or categoria
            canal.categoria = categorias[categoria.pk]
        canal.eliminado_en, canal.eliminado_por = None, None
        canal.marcar_autor(usuario)
        canal.save()
        Fuente.objects.bulk_create(fuentes)
        activos.add((_clave(canal.nombre), canal.contenido))
        resultado.restaurados += 1
    registrar(usuario, Accion.EDITAR, f'Restauró {resultado.restaurados} eliminados el '
                                      f'{timezone.localtime(momento):%d/%m %H:%M}.', modulo='canales')
    return resultado


@transaction.atomic
def renombrar_serie(nombre, nuevo, usuario=None):
    """
    Le cambia el nombre a una serie: a cada capítulo ("Viejo S01 E02 Título"
    -> "Nuevo S01 E02 Título"). Si ya hay OTRA serie con ese nombre no se
    puede (quedarían dos capítulos 1): para eso está "Unir en una sola serie".
    """
    nuevo = nombre_de_serie_valido(nuevo)
    capitulos = list(capitulos_de([nombre]))
    propios = [canal.pk for canal in capitulos]
    temporadas = {clasificar.episodio(canal.nombre)[1] for canal in capitulos}
    if any(ultimo_capitulo(nuevo, temporada, excluir=propios) for temporada in temporadas):
        raise NoSePuede(f'Ya hay otra serie "{nuevo}": sus capítulos se pisarían con estos. Para juntarlas, '
                        f'elegí las dos y usá "Unir en una sola serie".')
    for canal in capitulos:
        _, temporada, numero, titulo = clasificar.episodio(canal.nombre)
        if numero is None:
            continue
        canal.nombre = nombre_de_capitulo(nuevo, temporada, numero, titulo)
        canal.marcar_autor(usuario)
    Canal.objects.bulk_update(capitulos, ['nombre', 'modificado_por'])
    imagenes.mover_portada(nombre, nuevo)
    if capitulos:
        registrar(usuario, Accion.EDITAR, f'Renombró la serie "{nombre}" a "{nuevo}" ({len(capitulos)} capítulos).',
                  modulo='canales')
    return len(capitulos)


@transaction.atomic
def ordenar_capitulos(nombre_serie, temporada, en_orden, usuario=None):
    """
    Ordena los capítulos de una temporada: `en_orden` son los pk de TODOS sus
    capítulos, del que va primero al último. Quedan numerados 1, 2, 3... (el
    número va en el nombre, "Serie S01 E05 Título", que es lo que lee la app);
    cada uno conserva su título. Devuelve cuántos cambiaron de número.
    """
    temporada = int(temporada)
    capitulos = {canal.pk: canal for canal in capitulos_de([nombre_serie])
                 if clasificar.episodio(canal.nombre)[1] == temporada}
    try:
        en_orden = [int(pk) for pk in en_orden]
    except (TypeError, ValueError):
        raise NoSePuede('El orden que llegó no se entiende: volvé a cargar la página.') from None
    if not capitulos or sorted(en_orden) != sorted(capitulos):
        raise NoSePuede('La temporada cambió mientras la ordenabas (se agregó o se quitó un capítulo): volvé a '
                        'cargar la página y ordenala de nuevo.')
    ahora, cambiados = timezone.now(), []
    for numero, pk in enumerate(en_orden, start=1):
        canal = capitulos[pk]
        serie, _, viejo, titulo = clasificar.episodio(canal.nombre)
        if viejo == numero:
            continue
        canal.nombre = nombre_de_capitulo(serie, temporada, numero, titulo)
        canal.modificado = ahora
        canal.marcar_autor(usuario)
        cambiados.append(canal)
    Canal.objects.bulk_update(cambiados, ['nombre', 'modificado', 'modificado_por'])
    if cambiados:
        registrar(usuario, Accion.EDITAR, f'Ordenó los capítulos de "{nombre_serie}" (temporada {temporada}): '
                                          f'{len(cambiados)} cambiaron de número.', modulo='canales')
    return len(cambiados)


# ── Editar desde "Organizar contenido" ───────────────────────────────

@transaction.atomic
def editar_canal(canal, usuario=None, **datos):
    """
    Cambia lo que vino en `datos` (nombre, logo, numero, categoria, contenido,
    activo) de un canal, película o capítulo. Si cambia de sección, su
    categoría pasa a la del mismo nombre en la sección nueva. Devuelve los
    nombres de lo que cambió.
    """
    if datos.get('contenido') == Contenido.SERIE and canal.contenido != Contenido.SERIE:
        raise NoSePuede('Para pasar algo a serie, elegilo y usá "Pasar a serie" en la barra de abajo: ahí se le '
                        'pone el nombre de la serie y el número de capítulo.')
    cambios = []
    logo_viejo = canal.logo
    for campo in ('nombre', 'logo', 'numero', 'categoria', 'contenido', 'activo'):
        if campo in datos and getattr(canal, campo) != datos[campo]:
            setattr(canal, campo, datos[campo])
            cambios.append(campo)
    if canal.categoria is not None and canal.categoria.contenido != canal.contenido:
        canal.categoria = categoria_por_nombre(canal.categoria.nombre, canal.contenido, usuario=usuario)
    if 'activo' in cambios:
        canal.motivo_quitado = '' if canal.activo else 'Quitado a mano.'
    if cambios:
        canal.marcar_autor(usuario)
        canal.save()
        registrar(usuario, Accion.EDITAR, f'Editó "{canal.nombre}" ({", ".join(cambios)}).', objeto=canal,
                  modulo='canales')
    if 'logo' in cambios:
        imagenes.soltar(logo_viejo)   # si era una subida y nadie más la usa, se borra
    return cambios


def primera_imagen(serie):
    """La imagen del primer capítulo que tenga (la que usa la serie si no tiene portada)."""
    from .consultas import series   # consultas importa este módulo
    encontrada = next((s for s in series(texto=serie) if _clave(s.nombre) == _clave(serie)), None)
    if encontrada is None:
        return ''
    return next((c.canal.logo for c in sorted(encontrada.capitulos, key=lambda c: (c.temporada, c.numero or 0))
                 if c.canal.logo), '')


@transaction.atomic
def editar_serie(serie, usuario=None, **datos):
    """
    Lo mismo para una serie entera (todos sus capítulos): nombre (los
    renombra), logo, categoria y activo. Devuelve los nombres de lo que cambió.
    El logo es la PORTADA de la serie (imagenes.PortadaDeSerie): los
    capítulos conservan cada uno su imagen. Vacío = sin portada (la app usa
    la del primer capítulo).
    """
    capitulos = capitulos_de([serie])
    if not capitulos.exists():
        raise NoSePuede(f'No se encontró la serie "{serie}".')
    if datos.get('categoria') is not None and datos['categoria'].contenido != Contenido.SERIE:
        raise NoSePuede('Esa categoría no es de Series.')
    cambios = []
    ahora, quien = timezone.now(), _usuario(usuario)
    if 'logo' in datos and datos['logo'] != (imagenes.portada_de(serie) or primera_imagen(serie)):
        if imagenes.poner_portada(serie, datos['logo']):
            cambios.append('portada')
    if 'categoria' in datos and capitulos.exclude(categoria=datos['categoria']).exists():
        capitulos.update(categoria=datos['categoria'], modificado=ahora, modificado_por=quien)
        cambios.append('categoria')
    if 'activo' in datos and capitulos.exclude(activo=datos['activo']).exists():
        capitulos.update(activo=datos['activo'], motivo_quitado='' if datos['activo'] else 'Quitado a mano.',
                         modificado=ahora, modificado_por=quien)
        cambios.append('activo')
    # Con comparar el texto alcanza: así también se puede corregir un acento ("Pocoyo" -> "Pocoyó")
    if datos.get('nombre') and _limpio(datos['nombre'], 90) != _limpio(serie, 90):
        renombrar_serie(serie, datos['nombre'], usuario)
        cambios.append('nombre')
    elif cambios:
        registrar(usuario, Accion.EDITAR, f'Editó la serie "{serie}" ({", ".join(cambios)}).', modulo='canales')
    return cambios
