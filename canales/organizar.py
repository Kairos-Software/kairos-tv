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
    organizar.mover_a_temporada('Pocoyó', [pk, ...], 2)           -> esos capítulos pasan a la temporada 2
    organizar.eliminar_capitulos('Pocoyó', [pk, ...])             -> los elimina y renumera sin huecos
    organizar.plan_por_titulos('Casi Ángeles')                     -> cómo quedaría según "Temporada 3 Capítulo 33"
    organizar.ordenar_por_titulos('Casi Ángeles')                  -> lo aplica
    organizar.destino_de_serie('Pocoyó', 'Infantiles')             -> la categoría donde van sus capítulos nuevos
    organizar.categorias_parecidas(categorias)                     -> [[cat, cat], ...] posibles repetidas
    organizar.borrar_categoria(infantil, con_contenido=True)       -> la borra con todo lo de adentro
    organizar.eliminar_contenido(canales)                          -> los borra (si se vuelven a importar, vuelven)
    organizar.eliminados_recientes() / restaurar_eliminados(pk)    -> deshacer una eliminación
"""

import re
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Max, Min, Q
from django.utils import timezone

from actividad.models import Accion
from actividad.registro import registrar

from . import clasificar, consultas, imagenes, secciones, youtube
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


def categoria_existente(nombre, contenido=Contenido.VIVO, indice=None):
    """Como categoria_por_nombre, pero sin crearla: None si no hay ninguna que se llame (o se llamara) así."""
    if indice is None:
        indice = indice_de_categorias()
    return indice.get((contenido, _clave(_limpio(nombre))))


def recordar_nombre(categoria, nombre):
    """
    La próxima lista que traiga la categoría `nombre` la manda a `categoria`
    (queda entre sus otros nombres, como al juntar). Si otra categoría lo tenía
    como otro nombre, deja de tenerlo. False si en esa sección ya hay una
    categoría que SE LLAMA así: manda la suya (para eso, juntarlas en Categorías).
    """
    nombre = _limpio(nombre)
    clave = _clave(nombre)
    if not nombre or clave == _clave(categoria.nombre):
        return bool(nombre)
    otras = list(Categoria.objects.filter(contenido=categoria.contenido).exclude(pk=categoria.pk))
    if any(_clave(otra.nombre) == clave for otra in otras):
        return False
    for otra in otras:
        otros = _otros(otra)
        if any(_clave(n) == clave for n in otros):
            otra.otros_nombres = '\n'.join(n for n in otros if _clave(n) != clave)
            otra.save(update_fields=['otros_nombres', 'modificado'])
    _sumar_otros(categoria, [nombre])
    categoria.save(update_fields=['otros_nombres', 'modificado'])
    return True


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
    consultas.anotar_series()
    return (Canal.objects.filter(contenido=Contenido.SERIE, serie=nombre_serie.strip().lower(),
                                 temporada=int(temporada))
            .exclude(pk__in=list(excluir)).aggregate(ultimo=Max('capitulo'))['ultimo'] or 0)


_SIN_ELEGIR = object()


@transaction.atomic
def cambiar_contenido(canales, contenido, nombre_serie='', temporada=1, usuario=None, categoria=_SIN_ELEGIR):
    """
    Cambia el tipo (en vivo / película / serie) de los elegidos. Pasan a esa
    sección con una categoría del mismo nombre (la crea si no existe).

    A serie con `nombre_serie`: además los renombra como capítulos de esa
    serie, numerados en el orden de sus nombres ("Pocoyó S01 E01 El tornado"...),
    para que la app los arme como UNA serie. Sin nombre solo se puede si ya
    dicen temporada y capítulo ("Arrow S02 E05"): si no, quedarían sin un
    T1:E1 identificable y la app no los mostraría.

    `categoria` (a Series): la de la serie, para todos (None = sin categoría;
    ver destino_de_serie). Sin decirla, cada uno a la del mismo nombre.

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
        if categoria is not _SIN_ELEGIR and contenido == Contenido.SERIE:
            canal.categoria = categoria
        elif canal.categoria is not None and canal.categoria.contenido != contenido:
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
    """
    Los capítulos (Canal) de esas series, por nombre de serie (sin acentos ni mayúsculas: "Pocoyo" trae
    también los de "Pocoyó"). Con la serie de cada capítulo ya anotada (Canal.serie), se comparan los
    nombres de las series (unos miles) y no los de todos los capítulos. Los capítulos que son ahora: si
    después se les cambia el nombre, la lista sigue siendo la misma.
    """
    buscados = {_clave(n) for n in nombres_de_series if n.strip()}
    consultas.anotar_series()
    capitulos = Canal.objects.filter(contenido=Contenido.SERIE)
    series = [serie for serie in capitulos.order_by().values_list('serie', flat=True).distinct()
              if _clave(serie) in buscados]
    return Canal.objects.filter(pk__in=list(capitulos.filter(serie__in=series).values_list('pk', flat=True)))


def unir_en_una_serie(nombres_de_series, nombre_serie, temporada=1, usuario=None, capitulos=None,
                      categoria=_SIN_ELEGIR):
    """
    Junta varias series (por ejemplo, 239 "series" de un capítulo que eran
    videos sueltos) en UNA serie: todos sus capítulos quedan numerados en orden.
    `capitulos`: solo esos (los que se ven con un filtro); sin decirlo, todos los de esas series.
    """
    if not _limpio(nombre_serie):
        raise NoSePuede('Escribí el nombre de la serie que va a juntarlas.')
    if capitulos is None:
        capitulos = capitulos_de(nombres_de_series)
    cantidad = cambiar_contenido(capitulos, Contenido.SERIE, nombre_serie, temporada, usuario, categoria)
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


def _hacer_lugar(serie, temporada, numero, usuario=None):
    """
    Para devolver un capítulo eliminado a su lugar: al eliminarlo, los de su
    temporada se renumeraron sin huecos (eliminar_capitulos). Si su número ya
    lo tiene otro, ese y los siguientes se corren uno (si no, habría dos).
    """
    capitulos = [(canal, clasificar.episodio(canal.nombre)) for canal in capitulos_de([serie])]
    de_la_temporada = [(canal, partes) for canal, partes in capitulos if partes[1] == temporada]
    if not any(partes[2] == numero for _, partes in de_la_temporada):
        return
    corridos = []
    for canal, (nombre, _, viejo, titulo) in de_la_temporada:
        if viejo is not None and viejo >= numero:
            canal.nombre = nombre_de_capitulo(nombre, temporada, viejo + 1, titulo)
            canal.marcar_autor(usuario)
            corridos.append(canal)
    Canal.objects.bulk_update(corridos, ['nombre', 'modificado_por'])


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
    # Los capítulos, de a temporada y en orden: cada uno vuelve a su lugar (ver _hacer_lugar)
    def en_orden(canal):
        _, temporada, numero, _ = clasificar.episodio(canal.nombre)
        es_capitulo = canal.contenido == Contenido.SERIE
        return (not es_capitulo, temporada if es_capitulo else 0, (numero or 0) if es_capitulo else 0, canal.pk)

    for canal in sorted(Canal.todos.filter(eliminado_en=momento).select_related('categoria'), key=en_orden):
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
        if canal.contenido == Contenido.SERIE:
            serie, temporada, numero, _ = clasificar.episodio(canal.nombre)
            if numero:
                _hacer_lugar(serie, temporada, numero, usuario)
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
def titular_capitulo(capitulo, titulo, usuario=None):
    """
    Le cambia el TÍTULO a un capítulo ("Masha S01 E05 Sin amigos" -> "Masha S01 E05 La nieve"): la serie, la
    temporada y el número quedan igual. NoSePuede si el título nuevo haría que la app lo lea como otro capítulo
    (por ejemplo, si dice "S02 E03"). Devuelve el título como quedó.
    """
    serie, temporada, numero, _ = clasificar.episodio(capitulo.nombre)
    if numero is None:
        raise NoSePuede('Este capítulo no tiene número: cambiale el nombre desde «Editar».')
    titulo = _limpio(titulo, 100).strip(' -:|.')
    nombre = nombre_de_capitulo(serie, temporada, numero, titulo)
    if clasificar.episodio(nombre)[:3] != (serie, temporada, numero):
        raise NoSePuede('Ese título tiene algo que la app leería como otro número de capítulo (como "S2 E5" o '
                        '"3x04"). Escribilo de otra forma.')
    editar_canal(capitulo, usuario, nombre=nombre)
    return clasificar.episodio(capitulo.nombre)[3]


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


@transaction.atomic
def mover_a_temporada(nombre_serie, pks, temporada, usuario=None):
    """
    Pasa esos capítulos de la serie a otra temporada (una que ya tiene o una
    nueva): van al final de esa temporada, en el orden en que estaban. Las
    temporadas de donde salieron se renumeran 1, 2, 3... (sin huecos: la app
    arranca cada temporada en su capítulo 1). Devuelve cuántos pasaron.
    """
    try:
        temporada, pks = int(temporada), {int(pk) for pk in pks}
    except (TypeError, ValueError):
        raise NoSePuede('Lo que llegó no se entiende: volvé a cargar la página.') from None
    if not 1 <= temporada <= 99:
        raise NoSePuede('La temporada tiene que ser del 1 al 99.')
    capitulos = list(capitulos_de([nombre_serie]))
    if not capitulos:
        raise NoSePuede(f'No se encontró la serie "{nombre_serie}".')
    partes = {canal.pk: clasificar.episodio(canal.nombre) for canal in capitulos}
    serie = partes[capitulos[0].pk][0]   # como está escrita en sus capítulos

    def en_orden(canal):
        _, de_temporada, numero, _ = partes[canal.pk]
        return de_temporada, numero is None, numero or 0, canal.nombre

    elegidos = sorted((c for c in capitulos if c.pk in pks and partes[c.pk][1] != temporada), key=en_orden)
    if not elegidos:
        raise NoSePuede(f'Elegí al menos un capítulo que no sea de la temporada {temporada}.')
    siguiente = max((partes[c.pk][2] or 0 for c in capitulos if partes[c.pk][1] == temporada), default=0)
    cambiados = {}
    for canal in elegidos:
        siguiente += 1
        canal.nombre = nombre_de_capitulo(serie, temporada, siguiente, partes[canal.pk][3])
        cambiados[canal.pk] = canal
    _renumerar_sin_huecos(capitulos, {partes[c.pk][1] for c in elegidos}, usuario, ya_cambiados=cambiados)
    registrar(usuario, Accion.EDITAR, f'Pasó {len(elegidos)} capítulo(s) de "{serie}" a la temporada {temporada}.',
              modulo='canales')
    return len(elegidos)


@transaction.atomic
def eliminar_capitulos(nombre_serie, pks, usuario=None):
    """
    Elimina esos capítulos de la serie (se recuperan en "Eliminados", como
    todo lo eliminado) y renumera sin huecos las temporadas de donde salieron:
    si se borraba el capítulo 1, la temporada arrancaba en el 2 y la app
    escondía la serie. Devuelve cuántos se eliminaron.
    """
    try:
        pks = {int(pk) for pk in pks}
    except (TypeError, ValueError):
        raise NoSePuede('Lo que llegó no se entiende: volvé a cargar la página.') from None
    capitulos = list(capitulos_de([nombre_serie]))
    elegidos = [canal for canal in capitulos if canal.pk in pks]
    if not elegidos:
        raise NoSePuede('Elegí al menos un capítulo de esta serie.')
    temporadas = {clasificar.episodio(canal.nombre)[1] for canal in elegidos}
    cantidad = eliminar_contenido(Canal.objects.filter(pk__in=[c.pk for c in elegidos]), usuario)
    _renumerar_sin_huecos([c for c in capitulos if c.pk not in pks], temporadas, usuario)
    return cantidad


def _en_orden_de_la_serie(partes):
    """Para ordenar capítulos como los muestra la app: temporada, número (los sin número al final)."""

    def clave(canal):
        _, temporada, numero, _ = partes[canal.pk]
        return temporada, numero is None, numero or 0, canal.nombre
    return clave


def capitulos_que_dicen(nombre_serie, texto):
    """
    Los capítulos de la serie cuyo título dice `texto` (sin importar mayúsculas
    ni acentos), en el orden de la serie: para separar lo que vino mezclado
    ("Yu-Gi-Oh" con los de GX y 5D's). Cada uno: (canal, temporada, número, título).
    """
    buscado = clasificar.sin_acentos(' '.join(texto.split()))
    if not buscado:
        return []
    capitulos = list(capitulos_de([nombre_serie]))
    partes = {canal.pk: clasificar.episodio(canal.nombre) for canal in capitulos}
    return [(canal, partes[canal.pk][1], partes[canal.pk][2], partes[canal.pk][3] or canal.nombre)
            for canal in sorted(capitulos, key=_en_orden_de_la_serie(partes))
            if buscado in clasificar.sin_acentos(partes[canal.pk][3] or canal.nombre)]


def nombre_sugerido(titulos, texto, nombre_serie=''):
    """
    El nombre para la serie aparte, sacado de cómo empiezan los títulos hasta la
    palabra que dice `texto`: "Yu-Gi-Oh! GX Episodio 5" con "gx" -> "Yu-Gi-Oh! GX".
    Si los títulos no empiezan así ("Capítulo 5 - ..."), "<serie> <texto>".
    """
    buscado = clasificar.sin_acentos(' '.join(texto.split()))
    candidatos = Counter()
    for titulo in titulos:
        donde = clasificar.sin_acentos(titulo).find(buscado)
        if donde < 0 or len(clasificar.sin_acentos(titulo)) != len(titulo):
            continue
        fin = donde + len(buscado)
        while fin < len(titulo) and not titulo[fin].isspace():
            fin += 1
        candidato = titulo[:fin].strip(' -:|.,')
        if len(candidato) > 50 or re.match(r'(?i)(cap|ep|temporada|t\d|s\d|\d)', clasificar.sin_acentos(candidato)):
            continue
        try:
            candidatos[nombre_de_serie_valido(candidato)] += 1
        except NoSePuede:
            continue
    if candidatos:
        return candidatos.most_common(1)[0][0]
    return _limpio(f'{nombre_serie} {" ".join(texto.split())}'.strip(), 90)


@transaction.atomic
def mover_a_otra_serie(nombre_serie, pks, destino, temporada=1, usuario=None):
    """
    Pasa esos capítulos a OTRA serie (una que ya existe o una nueva): para
    separar lo que vino mezclado en una ("Yu-Gi-Oh" -> "Yu-Gi-Oh! GX"). Van a
    esa temporada de la otra serie, al final y en el orden en que estaban. Si
    la serie es nueva, queda en la misma categoría; si ya existía, en la suya.
    Las temporadas de donde salieron se renumeran sin huecos.
    Devuelve (cuántos pasaron, el nombre de la otra serie como quedó).
    """
    destino = nombre_de_serie_valido(destino)
    if _clave(destino) == _clave(nombre_serie):
        raise NoSePuede('Esa es esta misma serie. Para pasarlos a otra temporada de acá, usá «pasarlos a» '
                        'la temporada.')
    try:
        temporada, pks = int(temporada), {int(pk) for pk in pks}
    except (TypeError, ValueError):
        raise NoSePuede('Lo que llegó no se entiende: volvé a cargar la página.') from None
    if not 1 <= temporada <= 99:
        raise NoSePuede('La temporada tiene que ser del 1 al 99.')
    capitulos = list(capitulos_de([nombre_serie]))
    partes = {canal.pk: clasificar.episodio(canal.nombre) for canal in capitulos}
    elegidos = sorted((c for c in capitulos if c.pk in pks), key=_en_orden_de_la_serie(partes))
    if not elegidos:
        raise NoSePuede('Elegí al menos un capítulo de esta serie.')
    existe, suya = categoria_de_la_serie(destino)
    if existe:
        destino = next(iter(capitulos_de([destino])), None)
        destino = clasificar.episodio(destino.nombre)[0]   # como está escrita en sus capítulos
        categoria = suya
    else:
        categoria = categoria_de_la_serie(nombre_serie)[1]
    siguiente = ultimo_capitulo(destino, temporada)
    ahora = timezone.now()
    for canal in elegidos:
        siguiente += 1
        canal.nombre = nombre_de_capitulo(destino, temporada, siguiente, partes[canal.pk][3])
        canal.categoria = categoria
        canal.modificado = ahora
        canal.marcar_autor(usuario)
    Canal.objects.bulk_update(elegidos, ['nombre', 'categoria', 'modificado', 'modificado_por'])
    quedan = [c for c in capitulos if c.pk not in pks]
    _renumerar_sin_huecos(quedan, {partes[c.pk][1] for c in elegidos}, usuario)
    if not quedan:
        # Se fue entera: es como cambiarle el nombre (la portada va con ella, si la otra no tenía)
        imagenes.mover_portada(nombre_serie, destino)
    registrar(usuario, Accion.EDITAR, f'Pasó {len(elegidos)} capítulo(s) de "{nombre_serie}" a la serie '
                                      f'"{destino}" (temporada {temporada}).', modulo='canales')
    return len(elegidos), destino


def _renumerar_sin_huecos(capitulos, temporadas, usuario=None, ya_cambiados=None):
    """
    Deja esas temporadas numeradas 1, 2, 3... en el orden en que estaban (cada
    capítulo conserva su título). `capitulos`: los de la serie que quedan.
    Guarda los que cambian (y los de `ya_cambiados`) y devuelve cuántos guardó.
    """
    cambiados = dict(ya_cambiados or {})
    partes = {canal.pk: clasificar.episodio(canal.nombre) for canal in capitulos}
    for temporada in temporadas:
        quedan = sorted((c for c in capitulos if partes[c.pk][1] == temporada and c.pk not in cambiados),
                        key=lambda c: (partes[c.pk][2] is None, partes[c.pk][2] or 0, c.nombre))
        for numero, canal in enumerate(quedan, start=1):
            serie, _, viejo, titulo = partes[canal.pk]
            if viejo != numero:
                canal.nombre = nombre_de_capitulo(serie, temporada, numero, titulo)
                cambiados[canal.pk] = canal
    ahora = timezone.now()
    for canal in cambiados.values():
        canal.modificado = ahora
        canal.marcar_autor(usuario)
    Canal.objects.bulk_update(list(cambiados.values()), ['nombre', 'modificado', 'modificado_por'])
    return len(cambiados)


def categoria_de_la_serie(nombre_serie):
    """
    (existe, categoría) de la serie con ese nombre. Una serie va en UNA
    categoría: la de la mayoría de sus capítulos (None = sin categoría).
    """
    cuantos = Counter(capitulos_de([nombre_serie]).values_list('categoria', flat=True))
    if not cuantos:
        return False, None
    pk = cuantos.most_common(1)[0][0]
    return True, (Categoria.objects.filter(pk=pk).first() if pk else None)


def categoria_para_la_serie(nombre_serie, nombre_categoria):
    """
    El NOMBRE de la categoría donde van los capítulos que se suman a la serie
    (Traer de YouTube, Unir, Pasar a Series). Si la serie ya existe, la SUYA:
    elegir otra la partiría en dos categorías, así que eso se explica
    (NoSePuede). Si es nueva, la elegida ('' si no se eligió ninguna).
    """
    existe, suya = categoria_de_la_serie(nombre_serie)
    nombre_categoria = _limpio(nombre_categoria)
    if existe and suya is not None:
        if nombre_categoria and _clave(nombre_categoria) != _clave(suya.nombre):
            raise NoSePuede(f'"{_limpio(nombre_serie, 90)}" ya está en la categoría "{suya.nombre}": sus capítulos '
                            f'nuevos van ahí. Elegí "{suya.nombre}", o cambiale la categoría a la serie desde su '
                            f'página (Temporadas y capítulos).')
        return suya.nombre
    return nombre_categoria


def destino_de_serie(nombre_serie, nombre_categoria, usuario=None):
    """La Categoria de categoria_para_la_serie (la crea si es nueva). Sin ninguna, NoSePuede."""
    nombre = categoria_para_la_serie(nombre_serie, nombre_categoria)
    if not nombre:
        raise NoSePuede(f'Elegí en qué categoría de Series va "{_limpio(nombre_serie, 90)}" (o escribí una nueva).')
    return categoria_por_nombre(nombre, Contenido.SERIE, usuario=usuario)


# ── Editar desde "Organizar contenido" ───────────────────────────────

@transaction.atomic
def editar_canal(canal, usuario=None, **datos):
    """
    Cambia lo que vino en `datos` (nombre, logo, numero, categoria, contenido,
    activo, destacado) de un canal, película o capítulo. Si cambia de sección, su
    categoría pasa a la del mismo nombre en la sección nueva. Devuelve los
    nombres de lo que cambió.
    """
    if datos.get('contenido') == Contenido.SERIE and canal.contenido != Contenido.SERIE:
        raise NoSePuede('Para pasar algo a serie, elegilo y usá "Pasar a serie" en la barra de abajo: ahí se le '
                        'pone el nombre de la serie y el número de capítulo.')
    cambios = []
    logo_viejo = canal.logo
    for campo in ('nombre', 'logo', 'numero', 'categoria', 'contenido', 'activo', 'destacado'):
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
    renombra), logo, categoria, activo y destacado (en la app, la serie está
    destacada si lo está algún capítulo). Devuelve los nombres de lo que cambió.
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
    if 'destacado' in datos and capitulos.exclude(destacado=datos['destacado']).exists():
        capitulos.update(destacado=datos['destacado'], modificado=ahora, modificado_por=quien)
        cambios.append('destacado')
    # Con comparar el texto alcanza: así también se puede corregir un acento ("Pocoyo" -> "Pocoyó")
    if datos.get('nombre') and _limpio(datos['nombre'], 90) != _limpio(serie, 90):
        renombrar_serie(serie, datos['nombre'], usuario)
        cambios.append('nombre')
    elif cambios:
        registrar(usuario, Accion.EDITAR, f'Editó la serie "{serie}" ({", ".join(cambios)}).', modulo='canales')
    return cambios


# ── Ordenar una serie según lo que dicen los títulos ────────────────

_NUMERO_AL_PRINCIPIO = re.compile(r'^\s*#?(\d{1,4})\b')


def temporada_y_numero_del_titulo(titulo):
    """
    (temporada, capítulo) que dice un título: 'Temporada 3 Capitulo 33 Un lugar...' -> (3, 33),
    'S02 E26' -> (2, 26), 'Capítulo 12' -> (0, 12), '12 - El regreso' -> (0, 12). 0 = no dice la
    temporada. None si no dice el capítulo.
    """
    dice = youtube.numero_de_capitulo(titulo)
    if dice:
        return dice
    al_principio = _NUMERO_AL_PRINCIPIO.match(titulo or '')
    return (0, int(al_principio.group(1))) if al_principio else None


@dataclass
class CapituloEnElPlan:
    canal: Canal
    titulo: str
    antes: tuple          # (temporada, capítulo) de ahora
    despues: tuple = (0, 0)
    problema: str = ''    # '' | 'sin_numero' (no dice su número) | 'repetido' (otro dice el mismo)

    @property
    def cambia(self):
        return self.antes != self.despues


@dataclass
class PlanPorTitulos:
    capitulos: list
    de_corrido: bool

    def de_la_temporada(self, temporada):
        return [c for c in self.capitulos if c.despues[0] == temporada]

    @property
    def temporadas(self):
        """[(temporada, cuántos, primero, último)] como quedarían."""
        resultado = []
        for temporada in sorted({c.despues[0] for c in self.capitulos}):
            numeros = [c.despues[1] for c in self.de_la_temporada(temporada)]
            resultado.append((temporada, len(numeros), min(numeros), max(numeros)))
        return resultado

    @property
    def cambian(self):
        return [c for c in self.capitulos if c.cambia]

    @property
    def sin_numero(self):
        return [c for c in self.capitulos if c.problema == 'sin_numero']

    @property
    def repetidos(self):
        return [c for c in self.capitulos if c.problema == 'repetido']

    @property
    def con_numero(self):
        return len(self.capitulos) - len(self.sin_numero)

    @property
    def falta_el_1(self):
        """La temporada 1 no arrancaría en el capítulo 1: la app no mostraría la serie."""
        return not any(c.despues == (1, 1) for c in self.capitulos)


def plan_por_titulos(nombre_serie, de_corrido=False):
    """
    Cómo quedaría la serie si cada capítulo va a la temporada y al número que
    dice su título ("Temporada 3 Capítulo 33" -> T3 E33). Sirve para ordenar
    de una vez lo que vino mezclado de un canal de YouTube (numerado por fecha
    de subida, todo en una temporada).
      - Si el título no dice la temporada, se queda en la que está.
      - Si no dice el número, va al final de su temporada (en el orden de ahora).
      - Si dos dicen el mismo número, el primero se queda con ese y el otro va
        al final (suelen ser subidas repetidas: conviene revisarlos).
      - de_corrido: numerados 1, 2, 3... sin huecos, en ese orden (si en
        YouTube falta un capítulo, el siguiente toma su número).
    Si el nombre ya no tiene el título entero, usa el que traía de YouTube.
    """
    capitulos = list(capitulos_de([nombre_serie]))
    originales = dict(EntradaImportada.objects.filter(canal__in=capitulos)
                      .order_by('importacion__creada').values_list('canal', 'nombre_original'))
    items = []
    for canal in capitulos:
        _, temporada, numero, titulo = clasificar.episodio(canal.nombre)
        dice = temporada_y_numero_del_titulo(titulo)
        if dice is None and canal.pk in originales:
            dice = temporada_y_numero_del_titulo(originales[canal.pk])
        item = CapituloEnElPlan(canal, titulo, (temporada, numero or 0))
        item.dice = dice
        items.append(item)
    por_temporada = {}
    for item in items:
        destino = item.dice[0] if item.dice and item.dice[0] else item.antes[0]
        por_temporada.setdefault(destino, []).append(item)
    for temporada, lista in por_temporada.items():
        con = sorted((i for i in lista if i.dice), key=lambda i: (i.dice[1], i.antes))
        sin = sorted((i for i in lista if not i.dice), key=lambda i: i.antes)
        usados, al_final = set(), []
        for item in con:
            if item.dice[1] in usados or item.dice[1] < 1:
                item.problema = 'repetido'
                al_final.append(item)
            else:
                usados.add(item.dice[1])
                item.despues = (temporada, item.dice[1])
        for item in sin:
            item.problema = 'sin_numero'
        siguiente = max(usados, default=0)
        for item in al_final + sin:
            siguiente += 1
            item.despues = (temporada, siguiente)
        if de_corrido:
            for numero, item in enumerate(sorted(lista, key=lambda i: i.despues[1]), start=1):
                item.despues = (temporada, numero)
    items.sort(key=lambda i: i.despues)
    return PlanPorTitulos(items, de_corrido)


@transaction.atomic
def ordenar_por_titulos(nombre_serie, de_corrido=False, usuario=None):
    """Aplica plan_por_titulos: renombra los capítulos que cambian. Devuelve cuántos cambiaron."""
    plan = plan_por_titulos(nombre_serie, de_corrido)
    ahora, cambiados = timezone.now(), []
    for item in plan.cambian:
        serie = clasificar.episodio(item.canal.nombre)[0]
        item.canal.nombre = nombre_de_capitulo(serie, item.despues[0], item.despues[1], item.titulo)
        item.canal.modificado = ahora
        item.canal.marcar_autor(usuario)
        cambiados.append(item.canal)
    Canal.objects.bulk_update(cambiados, ['nombre', 'modificado', 'modificado_por'])
    if cambiados:
        registrar(usuario, Accion.EDITAR, f'Ordenó "{nombre_serie}" según los títulos: {len(cambiados)} capítulos '
                                          f'cambiaron de temporada o de número.', modulo='canales')
    return len(cambiados)


# ── Para ir más rápido en Organizar: cambiar nombres de a muchos e imágenes que ya existen ──

_PALABRAS_CHICAS = {'de', 'del', 'la', 'las', 'el', 'los', 'y', 'e', 'en', 'a', 'al', 'o', 'u', 'con', 'por',
                    'para', 'un', 'una', 'the', 'of', 'and'}


def mayuscula_inicial(texto):
    """
    'LA CASA DE PAPEL' -> 'La Casa de Papel'. Si el nombre mezcla mayúsculas y minúsculas, lo que está todo en
    mayúsculas se deja (es una sigla: 'ESPN', 'TV'); lo que tiene números también ('S01', '4K', '(2019)').
    """
    todo_en_mayusculas = texto.upper() == texto
    palabras = []
    for posicion, palabra in enumerate(texto.split()):
        if any(letra.isdigit() for letra in palabra):
            palabras.append(palabra)
        elif not todo_en_mayusculas and palabra.isupper() and len(palabra) > 1:
            palabras.append(palabra)
        elif posicion and palabra.lower() in _PALABRAS_CHICAS:
            palabras.append(palabra.lower())
        else:
            palabras.append(palabra[:1].upper() + palabra[1:].lower())
    return ' '.join(palabras)


def nombre_con_reglas(nombre, sacar='', reemplazar='', por='', limpiar=False, mayusculas=False, largo=120):
    """
    El nombre después de aplicarle las reglas de «Cambiar nombres» (Organizar, con varios elegidos):
      limpiar: como al importar (sin país, calidad ni "REPUESTO": clasificar.limpiar_nombre)
      sacar: un texto que se borra donde aparezca (sin importar mayúsculas)
      reemplazar / por: un texto que se cambia por otro
      mayusculas: Mayúscula Inicial (ver mayuscula_inicial)
    Si no queda nada, devuelve el nombre como estaba.
    """
    texto = nombre or ''
    if limpiar:
        texto = clasificar.limpiar_nombre(texto)
    if sacar.strip():
        texto = re.sub(re.escape(sacar), ' ', texto, flags=re.I)
    if reemplazar.strip():
        texto = re.sub(re.escape(reemplazar), lambda _: por, texto, flags=re.I)
    if mayusculas:
        texto = mayuscula_inicial(texto)
    texto = ' '.join(texto.split()).strip(' -|:·')[:largo].strip()
    return texto or nombre


@dataclass
class CambioDeNombre:
    clave: str          # 'c<pk>' (canal, película...) o 's:<nombre>' (una serie entera)
    antes: str
    despues: str
    error: str = ''


def cambios_de_nombre(canales=(), series=(), **reglas):
    """Cómo quedarían los nombres (solo los que cambian), sin tocar nada: la vista previa de «Cambiar nombres»."""
    cambios = []
    for canal in canales:
        nuevo = nombre_con_reglas(canal.nombre, **reglas)
        if nuevo != canal.nombre:
            cambios.append(CambioDeNombre(f'c{canal.pk}', canal.nombre, nuevo))
    for serie in series:
        nuevo = nombre_con_reglas(serie, largo=90, **reglas)
        if nuevo != serie:
            cambios.append(CambioDeNombre(f's:{serie}', serie, nuevo))
    return cambios


def renombrar_en_lote(canales=(), series=(), usuario=None, **reglas):
    """
    Aplica las reglas a lo elegido. Una serie se renombra entera (todos sus capítulos: renombrar_serie). Lo que
    no se puede (una serie que se pisaría con otra) se saltea y queda en `error`. Devuelve los cambios.
    """
    canales = list(canales)
    por_pk = {canal.pk: canal for canal in canales}
    cambios = cambios_de_nombre(canales, series, **reglas)
    for cambio in cambios:
        try:
            with transaction.atomic():
                if cambio.clave.startswith('s:'):
                    renombrar_serie(cambio.antes, cambio.despues, usuario)
                else:
                    editar_canal(por_pk[int(cambio.clave[1:])], usuario, nombre=cambio.despues)
        except NoSePuede as error:
            cambio.error = str(error)
    return cambios


def imagenes_parecidas(nombre, contenido='', excluir=None, limite=12):
    """
    Imágenes que YA tienen otras cosas con el mismo nombre, para elegir una con un clic en vez de buscarla:
    las de otras listas importadas (aunque no se hayan cargado) y las de otros canales o películas del panel.
    En Series, `nombre` es la serie: sirven las de sus capítulos en otras listas.
      [{'url': 'https://...', 'de': 'lista_amigo.m3u'}, ...]   (las de nombre idéntico primero)
    """
    clave = _clave(nombre)
    palabras = sorted((p for p in re.split(r'\W+', nombre or '') if len(p) >= 3), key=len, reverse=True)
    if not clave or not palabras:
        return []
    es_serie = contenido == Contenido.SERIE

    def puntaje(otro):
        if es_serie:
            otro = clasificar.episodio(otro)[0]
        otra = _clave(otro)
        if otra == clave:
            return 0
        if clasificar.limpiar_nombre(otra).lower() == clasificar.limpiar_nombre(clave).lower():
            return 1
        return 2 if otra.startswith(clave) or clave.startswith(otra) else None

    candidatas = []
    entradas = (EntradaImportada.objects.filter(nombre__icontains=palabras[0]).exclude(logo='')
                .select_related('importacion').order_by('-pk')[:400])
    for entrada in entradas:
        valor = puntaje(entrada.nombre)
        if valor is not None:
            candidatas.append((valor, entrada.logo, entrada.importacion.archivo))
    otros = Canal.objects.filter(nombre__icontains=palabras[0]).exclude(logo='').order_by('-pk')
    if excluir:
        otros = otros.exclude(pk=excluir)
    for canal in otros[:400]:
        valor = puntaje(canal.nombre)
        if valor is not None:
            candidatas.append((valor, canal.logo, f'En el panel: {canal.nombre}'))
    vistas, resultado = set(), []
    for _, url, de in sorted(candidatas, key=lambda c: c[0]):
        if url in vistas or not url.startswith(('http://', 'https://')):
            continue
        vistas.add(url)
        resultado.append({'url': url, 'de': de})
        if len(resultado) >= limite:
            break
    return resultado
