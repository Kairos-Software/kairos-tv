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
"""

import gzip
import hashlib
import json

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, HttpResponseNotModified

from canales import clasificar, imagenes
from canales.consultas import canales_disponibles, fuentes_usables, ordenadas_por_estabilidad
from canales.models import Contenido
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


def armar(tipos, contenido, request=None):
    """El catálogo como dict (lo mismo que mandaba CanalSerializer, agrupado por categoría)."""
    canales = list(canales_disponibles(tipos, contenido).prefetch_related(None).values(*_CAMPOS_CANAL))
    fuentes_de = {canal['id']: [] for canal in canales}
    # En el orden en que la app las prueba (el mismo del Prefetch de canales_disponibles)
    fuentes = (ordenadas_por_estabilidad(fuentes_usables(tipos))
               .filter(canal__activo=True, canal__contenido=contenido).values(*_CAMPOS_FUENTE))
    for fuente in fuentes.iterator(chunk_size=5000):
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


def _armado(tipos, contenido, request):
    """(huella, catálogo comprimido), del guardado si está."""
    clave = 'catalogo_app:' + ':'.join([contenido, ','.join(sorted(tipos)), request.build_absolute_uri('/')])
    segundos = _segundos()
    guardado = cache.get(clave) if segundos else None
    if guardado:
        return guardado
    # Igual que el JSON de DRF (UNICODE_JSON y COMPACT_JSON): sin á y sin espacios
    texto = json.dumps(armar(tipos, contenido, request), ensure_ascii=False, separators=(',', ':')).encode()
    armado = (f'"{hashlib.sha1(texto).hexdigest()[:24]}"', gzip.compress(texto, compresslevel=6))
    if segundos:
        cache.set(clave, armado, segundos)
    return armado


def respuesta(request, tipos, contenido):
    """La respuesta HTTP: 304 si la app ya lo tiene; si no, comprimido (o no, si no lo acepta)."""
    huella, comprimido = _armado(tipos, contenido, request)
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
