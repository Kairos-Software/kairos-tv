"""
El catálogo que pide la app (GET /api/v1/canales/), armado rápido.

Con miles de películas y capítulos, armarlo con el serializador de siempre
(CanalSerializer) tardaba: medido con 5.000 películas, 2 s y 2 MB por pedido,
y cada TV y celular lo pide al abrir la app y cada 15 minutos. Ahora:

  1. Se piden a la base solo las columnas que van a la app (`values`), sin
     armar los objetos completos de cada canal y cada fuente.
  2. Se guarda ya armado y comprimido (gzip) un rato (`_segundos`):
     si diez aparatos lo piden juntos, se arma una sola vez.
  3. Va comprimido (unas 5 a 10 veces menos datos: las direcciones se
     repiten mucho) y con su huella (ETag). Si la app ya tiene ese mismo
     catálogo, avisa con la huella (If-None-Match) y se le contesta 304 sin
     mandar nada.

Lo que recibe la app es EXACTAMENTE lo mismo que armaba CanalSerializer (lo
prueban los tests: test_catalogo_rapido.py), así las versiones viejas de la
app siguen andando igual.

Series a pedido (desde la app 1.2.38): con decenas de miles de capítulos, que
cada TV bajara y tuviera en memoria TODOS (?contenido=serie) ya no entraba en
un TV box. La app nueva pide:
  - la lista de series sin sus capítulos (armar_series: nombre, categoría,
    imagen, cuántos capítulos por temporada...), y
  - los capítulos de una serie recién cuando se abre (armar_capitulos).
Las series se arman con la MISMA regla que la app (clasificar.episodio: la
serie anotada en cada capítulo, Canal.serie) y solo van las que la app
mostraría (las que tienen el T1:E1).
"""

import gzip
import hashlib
import json

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, HttpResponseNotModified

from django.db.models import Count, Min, Q

from canales import clasificar, consultas, imagenes
from canales.consultas import anotar_series, canales_disponibles, fuentes_usables, ordenadas_por_estabilidad
from canales.models import Categoria, Contenido
from canales.verificacion import USER_AGENT_REPRODUCTOR, url_xtream_para_reproductor


def _segundos():
    """
    Cuánto se guarda armado (settings.CATALOGO_APP_SEGUNDOS; 60 si no dice).
    Un cambio en el panel llega a la app a lo sumo este rato después (la app
    igual lo pide al abrir y cada 15 minutos). En los tests, 0: no se guarda.
    """
    return getattr(settings, 'CATALOGO_APP_SEGUNDOS', 60)


_CAMPOS_CANAL = ('id', 'nombre', 'numero', 'logo', 'destacado', 'categoria_id', 'categoria__nombre')
_CAMPOS_FUENTE = ('id', 'canal_id', 'url', 'tipo', 'codec', 'user_agent', 'referer')


def _logos(canales, request):
    """La función que da el logo para mostrar de cada canal (la copia pareja, en dirección completa)."""
    parejos = imagenes.logos_parejos(canal['logo'] for canal in canales)
    absolutas = {}

    def logo(original):
        if original not in parejos:
            return original
        mostrar = parejos[original]
        if not (mostrar and request):
            return mostrar
        if mostrar not in absolutas:
            absolutas[mostrar] = request.build_absolute_uri(mostrar)
        return absolutas[mostrar]
    return logo


def armar(tipos, contenido, request=None, ids=None):
    """
    El catálogo como dict (lo mismo que mandaba CanalSerializer, agrupado por categoría).
    `ids`: solo esos canales (los capítulos de algunas series: armar_capitulos).
    """
    canales = canales_disponibles(tipos, contenido).prefetch_related(None)
    fuentes = (ordenadas_por_estabilidad(fuentes_usables(tipos))
               .filter(canal__activo=True, canal__contenido=contenido))
    if ids is not None:
        canales, fuentes = canales.filter(pk__in=ids), fuentes.filter(canal_id__in=ids)
    canales = list(canales.values(*_CAMPOS_CANAL))
    fuentes_de = {canal['id']: [] for canal in canales}
    # En el orden en que la app las prueba (el mismo del Prefetch de canales_disponibles)
    for fuente in fuentes.values(*_CAMPOS_FUENTE).iterator(chunk_size=5000):
        lista = fuentes_de.get(fuente['canal_id'])
        if lista is not None:
            lista.append({
                'id': fuente['id'],
                'url': url_xtream_para_reproductor(fuente['url']),
                'tipo': fuente['tipo'],
                'codec': fuente['codec'],
                'user_agent': fuente['user_agent'] or USER_AGENT_REPRODUCTOR,
                'referer': fuente['referer'],
            })

    logo = _logos(canales, request)
    grupos = {}
    for canal in canales:
        grupo = grupos.get(canal['categoria_id'])
        if grupo is None:
            grupo = grupos[canal['categoria_id']] = {
                'id': canal['categoria_id'],
                'nombre': canal['categoria__nombre'] if canal['categoria_id'] else 'Otros',
                'canales': [],
            }
        grupo['canales'].append({
            'id': canal['id'],
            'nombre': canal['nombre'],
            'numero': canal['numero'],
            'logo': logo(canal['logo']),
            'destacado': canal['destacado'],
            'fuentes': fuentes_de[canal['id']],
        })

    respuesta = {'cantidad': len(canales), 'categorias': list(grupos.values())}
    if contenido == Contenido.SERIE:
        respuesta['portadas'] = imagenes.portadas_de({clasificar.episodio(c['nombre'])[0] for c in canales})
    return respuesta


def armar_series(tipos, request=None):
    """
    La lista de series para la app, SIN sus capítulos (los pide al abrir una: armar_capitulos):
      {"cantidad": 2, "series": [{"nombre": "Pocoyó", "categoria": "Infantiles", "imagen": "https://...",
        "capitulos": 52, "temporadas": [[1, 26], [2, 26]], "destacada": false, "codecs": ["h264"]}, ...]}
    Por categoría (en el orden de la app, con la categoría del primer capítulo: la de la serie) y, en cada
    una, por el orden que se les dio y por nombre. Con la portada propia o la imagen del primer capítulo
    que tenga, y solo las que se pueden empezar (tienen el T1:E1). "codecs": los de sus señales ('' = no
    se sabe), para que cada aparato esconda las que no puede mostrar. Cuenta los capítulos que manda el
    servidor (un aparato puede ver alguno menos).
    La base agrupa los capítulos por su serie (Canal.serie): con 75.000 capítulos, traerlos todos
    ordenados por nombre y agruparlos acá tardaba 4 segundos.
    """
    anotar_series()
    capitulos = canales_disponibles(tipos, Contenido.SERIE).prefetch_related(None).select_related(None).order_by()
    filas = [fila for fila in capitulos.values('serie').annotate(
        un_capitulo=Min('pk'), cantidad=Count('pk'), primeros=Count('pk', filter=Q(temporada=1, capitulo=1)),
        destacados=Count('pk', filter=Q(destacado=True)), orden=Min('orden'), imagen=consultas.primera_imagen())
        if fila['primeros']]   # la app no muestra series que no se pueden empezar
    categorias, temporadas, codecs = {}, {}, {}
    for serie, categoria_id in capitulos.values_list('serie', 'categoria_id').distinct():
        categorias.setdefault(serie, set()).add(categoria_id)
    for serie, temporada, cuantos in capitulos.values('serie', 'temporada').annotate(n=Count('pk')).values_list(
            'serie', 'temporada', 'n'):
        temporadas.setdefault(serie, []).append([temporada, cuantos])
    for serie, codec in (fuentes_usables(tipos).filter(canal__in=capitulos.values('pk')).order_by()
                         .values_list('canal__serie', 'codec').distinct()):
        codecs.setdefault(serie, set()).add(codec)
    nombres = consultas.series_de_los_capitulos(filas)
    primeras = consultas.imagenes_primeras(filas)
    orden = consultas.orden_de_categorias()
    nombres_de_categorias = dict(Categoria.objects.values_list('pk', 'nombre'))
    portadas = imagenes.portadas_de(list(nombres.values()))
    logo = _logos([{'logo': imagen} for imagen in primeras.values()], request)
    lista = []
    for fila in filas:
        nombre = nombres[fila['serie']]
        categoria_id = consultas.primera_categoria(categorias.get(fila['serie']), orden)
        lista.append(((orden.get(categoria_id, len(orden)), fila['orden'], clasificar.sin_acentos(nombre), nombre), {
            'nombre': nombre,
            'categoria': nombres_de_categorias.get(categoria_id) or 'Otros',
            'imagen': portadas.get(nombre) or (logo(primeras[fila['serie']]) if fila['serie'] in primeras else ''),
            'capitulos': fila['cantidad'],
            'temporadas': sorted(temporadas.get(fila['serie'], [])),
            'destacada': fila['destacados'] > 0,
            'codecs': sorted(codecs.get(fila['serie'], set())),
        }))
    lista.sort(key=lambda par: par[0])
    return {'cantidad': len(lista), 'series': [serie for _, serie in lista]}


# Cuántas series (o capítulos sueltos) se pueden pedir juntas
MAXIMO_A_PEDIR = 50


def armar_capitulos(tipos, nombres=(), ids=(), request=None):
    """
    Los capítulos de las series `nombres` y de las series de los capítulos `ids` (para "Continuar
    viendo": la app sabe el capítulo, no la serie), con el mismo formato que el catálogo (armar).
    """
    anotar_series()
    capitulos = canales_disponibles(tipos, Contenido.SERIE).prefetch_related(None).order_by()
    buscadas = {n.strip().lower() for n in nombres if n.strip()}
    if ids:
        buscadas |= set(capitulos.filter(pk__in=ids).values_list('serie', flat=True))
    if not buscadas:
        return {'cantidad': 0, 'categorias': [], 'portadas': {}}
    # Por la serie anotada en cada capítulo (Canal.serie: la misma regla que la app)
    elegidos = list(capitulos.filter(serie__in=buscadas).values_list('pk', flat=True))
    return armar(tipos, Contenido.SERIE, request, ids=elegidos)


def _armado(tipos, contenido, request, construir=None):
    """(huella, catálogo comprimido), del guardado si está. `construir`: otra cosa para armar (las series)."""
    clave = 'catalogo_app:' + ':'.join([contenido, ','.join(sorted(tipos)), request.build_absolute_uri('/')])
    segundos = _segundos()
    guardado = cache.get(clave) if segundos else None
    if guardado:
        return guardado
    datos = construir() if construir else armar(tipos, contenido, request)
    # Igual que el JSON de DRF (UNICODE_JSON y COMPACT_JSON): sin á y sin espacios
    texto = json.dumps(datos, ensure_ascii=False, separators=(',', ':')).encode()
    armado = (f'"{hashlib.sha1(texto).hexdigest()[:24]}"', gzip.compress(texto, compresslevel=6))
    if segundos:
        cache.set(clave, armado, segundos)
    return armado


def respuesta(request, tipos, contenido, construir=None):
    """La respuesta HTTP: 304 si la app ya lo tiene; si no, comprimido (o no, si no lo acepta)."""
    huella, comprimido = _armado(tipos, contenido, request, construir)
    if huella in request.headers.get('If-None-Match', ''):
        no_cambio = HttpResponseNotModified()
        no_cambio['ETag'] = huella
        return no_cambio
    if 'gzip' in request.headers.get('Accept-Encoding', ''):
        http = HttpResponse(comprimido, content_type='application/json')
        http['Content-Encoding'] = 'gzip'
    else:
        http = HttpResponse(gzip.decompress(comprimido), content_type='application/json')
    http['ETag'] = huella
    http['Vary'] = 'Accept-Encoding'
    # Que nadie en el medio lo guarde por su cuenta: la app pregunta cada vez (con la huella)
    http['Cache-Control'] = 'private, no-cache'
    return http
