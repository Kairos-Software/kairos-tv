"""
Exportar el contenido cargado (capa Base): una lista M3U8 o una planilla de
Excel, con lo que se elija en Organizar contenido.

  - Lista M3U8: la abre VLC (u otra app de listas) y se puede volver a
    importar acá. Un canal con varias señales sale una vez por señal, con el
    mismo nombre: al importarla se juntan de nuevo en un canal con sus
    fuentes. Lleva el nombre, el logo, la categoría (group-title), el número,
    el país, el idioma, el User-Agent / Referer que pida cada señal y la
    sección (kairos-seccion: así vuelve a la misma, ver m3u.py).
  - Excel: dos hojas. "Contenido", una fila por canal, película o capítulo
    (con si la ve la app y, si no, por qué) y "Fuentes", una fila por señal
    (estado, formato, códec, error, cuándo se probó, de qué lista salió...).

Lo de YouTube (los videos del reproductor oficial y los vivos de YouTube) NO
se exporta: no son direcciones de video que otra app pueda abrir.

    eleccion = Eleccion(secciones=['vivo'], filtros={'mostrar': 'app'})
    exportacion = elegir(eleccion)
    texto = lista_m3u(exportacion)        # o: planilla_excel(exportacion) -> bytes
"""

from dataclasses import dataclass, field
from functools import reduce
from operator import or_

from django.db.models import Count, Q
from django.utils import timezone
from django.utils.timezone import localtime

from herramientas.excel import planilla

from . import clasificar, consultas, imagenes, organizar, secciones
from .models import Canal, Contenido, Fuente

# Las señales de YouTube no se exportan (las abre solo el reproductor de YouTube)
TIPOS_DE_YOUTUBE = {Fuente.Tipo.YT_VIDEO, Fuente.Tipo.YOUTUBE}

# Los filtros de Organizar contenido que se pueden aplicar (ver consultas.canales_filtrados)
FILTROS = ('texto', 'mostrar', 'origen', 'sin_logo', 'idioma')


@dataclass
class Eleccion:
    """
    Qué exportar: se junta todo lo que se pida (secciones enteras, categorías,
    lo sin categoría de una sección, canales y series sueltos) y después se le
    aplican los filtros, si hay.
    """
    secciones: list = field(default_factory=list)       # claves: 'vivo', 'pelicula', 'musica'...
    categorias: list = field(default_factory=list)      # pks
    sin_categoria: list = field(default_factory=list)   # claves de sección: lo que ahí no tiene categoría
    canales: list = field(default_factory=list)         # pks (canales, películas o capítulos sueltos)
    series: list = field(default_factory=list)          # nombres de series (todos sus capítulos)
    filtros: dict = field(default_factory=dict)         # los de Organizar (FILTROS)
    solo_las_que_andan: bool = False                    # solo las señales que la app puede usar

    @property
    def vacia(self):
        return not (self.secciones or self.categorias or self.sin_categoria or self.canales or self.series)


@dataclass
class Exportacion:
    canales: list            # [(canal, [fuentes que se exportan]), ...] en el orden de la app
    sin_senales: int = 0     # los que quedaron afuera: sin señales para exportar (solo de YouTube, o ninguna andaba)
    nombres_de_secciones: dict = field(default_factory=dict)
    portadas: dict = field(default_factory=dict)        # {nombre de la serie: portada propia}

    @property
    def cantidad_de_senales(self):
        return sum(len(fuentes) for _, fuentes in self.canales)


@dataclass
class SeccionParaElegir:
    clave: str
    nombre: str
    total: int
    categorias: list         # [(valor, nombre, cuántos tiene)]: valor = pk o "ninguna:<sección>"


def para_elegir():
    """Las secciones con sus categorías y cuántos tiene cada una, para el cuadro "Exportar"."""
    por_seccion = {}
    for categoria in organizar.categorias_con_cantidades():
        if categoria.total:
            por_seccion.setdefault(categoria.contenido, []).append((str(categoria.pk), categoria.nombre,
                                                                   categoria.total))
    totales = dict(Canal.objects.order_by().values_list('contenido').annotate(cantidad=Count('pk')))
    sin_categoria = dict(Canal.objects.filter(categoria__isnull=True).order_by().values_list('contenido')
                         .annotate(cantidad=Count('pk')))
    resultado = []
    for clave, nombre in secciones.todas():
        categorias = por_seccion.get(clave, [])
        if sin_categoria.get(clave):
            categorias.append((f'ninguna:{clave}', 'Sin categoría', sin_categoria[clave]))
        resultado.append(SeccionParaElegir(clave, nombre, totales.get(clave, 0), categorias))
    return resultado


def es_de_youtube(fuente):
    return fuente.tipo in TIPOS_DE_YOUTUBE or clasificar.formato(fuente.url) == 'youtube'


def _se_exporta(fuente, solo_las_que_andan):
    if es_de_youtube(fuente):
        return False
    return not solo_las_que_andan or (fuente.usable() and fuente.tipo in consultas.TIPOS_QUE_REPRODUCE_LA_APP)


def elegir(eleccion):
    """Lo elegido, con sus señales, en el orden en que lo muestra la app. Ver Eleccion."""
    pedidos = []
    if eleccion.secciones:
        pedidos.append(Q(contenido__in=eleccion.secciones))
    if eleccion.categorias:
        pedidos.append(Q(categoria_id__in=eleccion.categorias))
    for clave in eleccion.sin_categoria:
        pedidos.append(Q(contenido=clave, categoria__isnull=True))
    if eleccion.canales:
        pedidos.append(Q(pk__in=eleccion.canales))
    if eleccion.series:
        pedidos.append(Q(pk__in=organizar.capitulos_de(eleccion.series).values('pk')))
    nombres = dict(secciones.todas())
    if not pedidos:
        return Exportacion([], nombres_de_secciones=nombres)

    filtros = {clave: valor for clave, valor in eleccion.filtros.items() if clave in FILTROS and valor}
    canales = consultas.canales_filtrados(**filtros).filter(reduce(or_, pedidos))
    orden_de_secciones = {clave: posicion for posicion, clave in enumerate(nombres)}

    def orden(canal):
        serie, temporada, numero = '', 0, 0
        if canal.contenido == Contenido.SERIE:
            serie, temporada, numero, _ = clasificar.episodio(canal.nombre)
        categoria = canal.categoria
        return (orden_de_secciones.get(canal.contenido, len(orden_de_secciones)), categoria is None,
                categoria.orden if categoria else 0, categoria.nombre.lower() if categoria else '',
                serie.lower(), temporada or 0, numero or 0, canal.orden, canal.nombre.lower())

    elegidos, sin_senales = [], 0
    for canal in sorted(canales, key=orden):
        fuentes = [f for f in canal.fuentes.all() if _se_exporta(f, eleccion.solo_las_que_andan)]
        if fuentes:
            elegidos.append((canal, fuentes))
        else:
            sin_senales += 1
    series_ = {clasificar.episodio(c.nombre)[0] for c, _ in elegidos if c.contenido == Contenido.SERIE}
    return Exportacion(elegidos, sin_senales, nombres, imagenes.portadas_de(sorted(series_)))


# ── Lista M3U8 ───────────────────────────────────────────────────────

def _atributo(valor):
    """Un valor que va entre comillas en la línea #EXTINF (sin comillas ni saltos de línea adentro)."""
    return ' '.join(str(valor).replace('"', "'").split())


def lista_m3u(exportacion):
    """El texto de la lista (UTF-8). Una entrada por señal: las de un mismo canal llevan el mismo nombre."""
    ahora = localtime(timezone.now())
    lineas = ['#EXTM3U',
              f'# Kairos TV · exportada el {ahora:%d/%m/%Y %H:%M} · {len(exportacion.canales)} canales, '
              f'películas o capítulos con {exportacion.cantidad_de_senales} señales (sin lo de YouTube)']
    for canal, fuentes in exportacion.canales:
        atributos = [
            ('tvg-id', canal.tvg_id),
            ('tvg-name', canal.nombre),
            ('tvg-logo', canal.logo),
            ('tvg-chno', canal.numero),
            ('tvg-country', canal.pais),
            ('tvg-language', 'Spanish' if canal.idioma == 'es' else ''),
            ('group-title', canal.categoria.nombre if canal.categoria else ''),
            ('kairos-seccion', canal.contenido),
        ]
        extinf = ' '.join(f'{clave}="{_atributo(valor)}"' for clave, valor in atributos if valor)
        nombre = ' '.join(canal.nombre.split())
        for fuente in fuentes:
            lineas.append(f'#EXTINF:-1 {extinf},{nombre}')
            if fuente.user_agent:
                lineas.append(f'#EXTVLCOPT:http-user-agent={" ".join(fuente.user_agent.split())}')
            if fuente.referer:
                lineas.append(f'#EXTVLCOPT:http-referrer={" ".join(fuente.referer.split())}')
            lineas.append(fuente.url.strip())
    return '\n'.join(lineas) + '\n'


# ── Planilla de Excel ────────────────────────────────────────────────

COLUMNAS_DE_CONTENIDO = ['Sección', 'Categoría', 'Serie', 'Temporada', 'Capítulo', 'Nombre', 'Número',
                         'Imagen', 'Portada de la serie', 'Idioma', 'País', 'Se ve en la app', 'Por qué no se ve',
                         'Señales']
COLUMNAS_DE_FUENTES = ['Sección', 'Categoría', 'Nombre', 'Orden', 'Dirección', 'Formato', 'Estado',
                       'Encendida', 'Códec', 'Calidad', 'Error', 'Probada', 'Cargada', 'De dónde salió',
                       'User-Agent', 'Referer']
_IDIOMAS = {'es': 'Español', 'otro': 'Otro idioma'}


def _fecha(momento):
    return localtime(momento) if momento else None


def planilla_excel(exportacion):
    """Los bytes del .xlsx: hojas "Contenido" y "Fuentes"."""
    contenido, senales = [], []
    for canal, fuentes in exportacion.canales:
        seccion = exportacion.nombres_de_secciones.get(canal.contenido, canal.contenido)
        categoria = canal.categoria.nombre if canal.categoria else ''
        serie, temporada, numero = '', None, None
        if canal.contenido == Contenido.SERIE:
            serie, temporada, numero, _ = clasificar.episodio(canal.nombre)
        motivo = consultas.por_que_no_se_ve(canal)
        contenido.append([seccion, categoria, serie, temporada, numero, canal.nombre, canal.numero, canal.logo,
                          exportacion.portadas.get(serie, '') if serie else '', _IDIOMAS.get(canal.idioma, ''),
                          canal.pais, not motivo, motivo, len(fuentes)])
        for orden, fuente in enumerate(fuentes, start=1):
            senales.append([seccion, categoria, canal.nombre, orden, fuente.url, fuente.get_tipo_display(),
                            fuente.get_estado_display(), fuente.activa, fuente.codec, fuente.calidad, fuente.error,
                            _fecha(fuente.verificada), _fecha(fuente.creado), fuente.origen, fuente.user_agent,
                            fuente.referer])
    return planilla([('Contenido', COLUMNAS_DE_CONTENIDO, contenido), ('Fuentes', COLUMNAS_DE_FUENTES, senales)])
