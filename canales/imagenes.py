"""
Las imágenes que se ponen a mano desde el panel: logos y pósters subidos
desde la compu, y la portada propia de cada serie.

Subidas: se achican (como mucho LADO_MAXIMO de lado), se guardan en
media/canales/imagenes/ con un nombre al azar y lo que queda en `logo` es su
dirección completa (https://.../media/canales/imagenes/....jpg), igual que un
link pegado: la app las carga directo, como cualquier otra. Son fotos, no
video (el video nunca pasa por el servidor).

    from canales import imagenes
    imagenes.guardar_subida(archivo, request)          -> 'https://.../media/canales/imagenes/ab12.jpg'
    imagenes.soltar(url_vieja)                         -> borra el archivo si era subido y ya nadie lo usa
    imagenes.portada_de('Pocoyó')                      -> '' si no tiene
    imagenes.portadas_de(['Pocoyó', 'Masha'])          -> {'Pocoyó': 'https://...'}  (solo las que tienen)
    imagenes.poner_portada('Pocoyó', url)              -> '' la saca (vuelve a la del primer capítulo)
    imagenes.mover_portada('Pocoyo', 'Pocoyó')         -> al renombrar o unir series
"""

import hashlib
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import BytesIO

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from PIL import Image, ImageChops, ImageDraw, ImageOps, UnidentifiedImageError

from . import clasificar
from .models import Canal, PortadaDeSerie

CARPETA = 'canales/imagenes/'
PESO_MAXIMO = 8 * 1024 * 1024   # 8 MB: una foto de celular entra de sobra
LADO_MAXIMO = 1600              # alcanza para la vidriera de la TV (1920 de ancho, con margen)
FORMATOS = {'JPEG', 'PNG', 'WEBP', 'GIF'}


class ImagenInvalida(Exception):
    """El archivo no sirve como imagen (se le muestra el mensaje a la persona)."""


def guardar_subida(archivo, request):
    """Guarda la imagen subida (achicada) y devuelve su dirección completa."""
    if archivo.size > PESO_MAXIMO:
        raise ImagenInvalida(f'La imagen pesa {archivo.size / 1024 / 1024:.0f} MB: como mucho '
                             f'{PESO_MAXIMO // 1024 // 1024} MB.')
    try:
        imagen = Image.open(archivo)
        formato = imagen.format
        imagen.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ImagenInvalida('Ese archivo no es una imagen (tiene que ser JPG, PNG o WEBP).') from None
    if formato not in FORMATOS:
        raise ImagenInvalida(f'Las imágenes {formato} no se aceptan: tiene que ser JPG, PNG o WEBP.')

    if _tiene_transparencia(imagen):
        imagen = imagen.convert('RGBA')        # antes de girarla: si no, se pierde lo transparente
    imagen = ImageOps.exif_transpose(imagen)   # las fotos de celular vienen "acostadas" con un dato aparte
    imagen.thumbnail((LADO_MAXIMO, LADO_MAXIMO))
    imagen = sacar_cuadritos(imagen)
    salida = BytesIO()
    if _tiene_transparencia(imagen):
        # Un logo con fondo transparente: PNG, para que no quede un recuadro negro
        imagen.convert('RGBA').save(salida, 'PNG', optimize=True)
        extension = 'png'
    else:
        imagen.convert('RGB').save(salida, 'JPEG', quality=85, optimize=True)
        extension = 'jpg'
    nombre = default_storage.save(f'{CARPETA}{uuid.uuid4().hex}.{extension}', ContentFile(salida.getvalue()))
    return request.build_absolute_uri(default_storage.url(nombre))


def _tiene_transparencia(imagen):
    return imagen.mode in ('RGBA', 'LA', 'PA') or 'transparency' in imagen.info


# ── El fondo "de cuadritos" falso ────────────────────────────────────
# Muchos "PNG sin fondo" que se bajan de internet NO son transparentes: tienen
# los cuadritos grises y blancos pintados (son parte de la imagen). Se
# reconocen en el borde: dos grises que se alternan una y otra vez. Ese fondo
# (lo que está pegado al borde y es de esos dos grises) pasa a transparente.

TOLERANCIA = 8           # cuánto puede variar cada gris (compresión JPG)
MINIMO_DE_CAMBIOS = 6    # cuántas veces tienen que alternarse en un lado para ser cuadritos


def sacar_cuadritos(imagen):
    """La imagen con el fondo de cuadritos pintado vuelto transparente (o la misma, si no lo tiene)."""
    grises = _grises_de_cuadritos(imagen)
    if grises is None:
        return imagen
    imagen = imagen.convert('RGBA')
    ancho, alto = imagen.size
    # Los puntos que son de alguno de los dos grises (sin color)
    luz = imagen.convert('L')
    parecidos = luz.point(lambda v: 255 if any(abs(v - g) <= TOLERANCIA for g in grises) else 0)
    sin_color = imagen.convert('RGB').convert('HSV').getchannel('S').point(lambda v: 255 if v <= 24 else 0)
    candidatos = ImageChops.multiply(parecidos, sin_color)
    # De esos, solo los pegados al borde (el fondo): un gris adentro del logo se queda
    for x, y in _borde(ancho, alto):
        if candidatos.getpixel((x, y)) == 255:
            ImageDraw.floodfill(candidatos, (x, y), 128, thresh=0)
    fondo = candidatos.point(lambda v: 255 if v == 128 else 0)
    imagen.putalpha(ImageChops.subtract(imagen.getchannel('A'), fondo))
    return imagen


def _borde(ancho, alto):
    yield from ((x, y) for y in (0, alto - 1) for x in range(ancho))
    yield from ((x, y) for x in (0, ancho - 1) for y in range(1, alto - 1))


def _grises_de_cuadritos(imagen):
    """Los dos grises del fondo de cuadritos, si el borde lo tiene; si no, None."""
    if imagen.width < 16 or imagen.height < 16:
        return None
    rgba = imagen.convert('RGBA')
    lados = [
        [rgba.getpixel((x, 0)) for x in range(rgba.width)],
        [rgba.getpixel((x, rgba.height - 1)) for x in range(rgba.width)],
        [rgba.getpixel((0, y)) for y in range(rgba.height)],
        [rgba.getpixel((rgba.width - 1, y)) for y in range(rgba.height)],
    ]
    puntos = [p for lado in lados for p in lado]
    # Grises opacos (lo transparente de verdad no cuenta: esa imagen ya está bien)
    grises = [p[0] for p in puntos if p[3] == 255 and max(p[:3]) - min(p[:3]) <= 12]
    if len(grises) < len(puntos) * 0.8:
        return None
    # Los dos tonos más comunes, separados entre sí
    cuantos = {}
    for g in grises:
        cuantos[g // 4] = cuantos.get(g // 4, 0) + 1
    tonos = sorted(cuantos, key=cuantos.get, reverse=True)
    primero = tonos[0] * 4 + 2
    segundo = next((t * 4 + 2 for t in tonos[1:] if abs(t * 4 + 2 - primero) > 2 * TOLERANCIA), None)
    if segundo is None:
        return None
    de_cada_uno = [sum(1 for g in grises if abs(g - tono) <= TOLERANCIA) for tono in (primero, segundo)]
    if min(de_cada_uno) < len(puntos) * 0.2 or sum(de_cada_uno) < len(puntos) * 0.75:
        return None
    # Y que se alternen a lo largo de los lados (cuadritos, no dos franjas)
    def cambios(lado):
        tonos_del_lado = [0 if abs(p[0] - primero) <= TOLERANCIA else 1 if abs(p[0] - segundo) <= TOLERANCIA else None
                          for p in lado]
        conocidos = [t for t in tonos_del_lado if t is not None]
        return sum(1 for a, b in zip(conocidos, conocidos[1:]) if a != b)
    if sum(1 for lado in lados if cambios(lado) >= MINIMO_DE_CAMBIOS) < 2:
        return None
    return primero, segundo


def _archivo_subido(url):
    """El nombre en media/ si `url` es una imagen subida acá ('' si es un link de afuera)."""
    marca = f'{settings.MEDIA_URL}{CARPETA}'
    if marca not in (url or ''):
        return ''
    return CARPETA + url.split(marca, 1)[1].split('?')[0]


def soltar(url):
    """Si `url` era una imagen subida y ya no la usa nadie, borra el archivo (no se acumulan)."""
    nombre = _archivo_subido(url)
    if not nombre or '/' in nombre[len(CARPETA):] or '..' in nombre:
        return
    if Canal.todos.filter(logo=url).exists() or PortadaDeSerie.objects.filter(imagen=url).exists():
        return
    default_storage.delete(nombre)


# ── Logos parejos ────────────────────────────────────────────────────
# Los logos de los canales vienen de cualquier lado: unos con mucho borde
# vacío (transparente o de color), otros justo al borde, de 100 px o de
# 3840. Centrados "tal cual", unos se ven chiquitos y corridos y otros
# enormes. Para cada dirección se guarda una copia pareja (LogoParejo):
#   - se recorta lo que sobra alrededor: lo transparente, o el fondo de un
#     solo color (en ese caso queda un margen de ese color: si se lo sacara,
#     un logo oscuro sobre blanco no se vería en la tarjeta oscura);
#   - queda un margen chico e igual para todos;
#   - se achica a LADO_PAREJO como mucho (a un TV box le pesa uno de 3840).
# La API y el panel mandan la copia en vez del original (la app no cambia).
# Lo hace el cron (verificar_fuentes) y, al cambiar un logo en el panel, en
# el momento. Si no hace falta tocarlo, o no se puede (SVG, no existe...),
# queda el original.

CARPETA_PAREJOS = 'canales/logos/'
LADO_PAREJO = 512
PESO_MAXIMO_LOGO = 5 * 1024 * 1024
MARGEN_TRANSPARENTE = 0.03   # de lo que mide el logo (lado más largo)
MARGEN_DE_COLOR = 0.08       # el recuadro de color queda con este margen alrededor del logo
DIFERENCIA_DE_FONDO = 32     # cuánto puede variar el "fondo de un color" (compresión JPG)
REINTENTAR_FALLADOS = timedelta(days=7)
SEGUNDOS_PARA_LOGOS = 4 * 60   # en cada pasada del cron
A_LA_VEZ = 8


class LogoNoSirve(Exception):
    """No se pudo bajar o abrir el logo (queda el original)."""


class LogoRoto(LogoNoSirve):
    """La dirección ya no tiene el logo (borrado o 404): mejor las iniciales."""


def _clave_de(url):
    return hashlib.sha1(url.encode('utf-8')).hexdigest()


def tiene_logo_parejo(contenido):
    """Los canales en vivo y las secciones "en vivo" (radios) muestran logos; películas y series, pósters."""
    from .models import Contenido
    from . import secciones
    return contenido == Contenido.VIVO or secciones.forma(contenido) == 'vivo'


def _caja_del_logo(imagen):
    """
    (caja, color_de_fondo): lo que ocupa el logo de verdad. color_de_fondo es
    None si el fondo es transparente (o si no hay un fondo parejo: caja = todo).
    """
    alfa = imagen.getchannel('A')
    if alfa.getextrema()[0] < 250:
        return alfa.point(lambda a: 255 if a > 24 else 0).getbbox(), None
    rgb = imagen.convert('RGB')
    ancho, alto = rgb.size
    esquinas = [rgb.getpixel(p) for p in ((0, 0), (ancho - 1, 0), (0, alto - 1), (ancho - 1, alto - 1))]
    fondo = esquinas[0]
    if any(max(abs(a - b) for a, b in zip(esquina, fondo)) > DIFERENCIA_DE_FONDO for esquina in esquinas):
        return (0, 0, ancho, alto), None   # no tiene un fondo de un color (una foto): se deja entera
    rojo, verde, azul = ImageChops.difference(rgb, Image.new('RGB', rgb.size, fondo)).split()
    distinto = ImageChops.lighter(ImageChops.lighter(rojo, verde), azul)
    caja = distinto.point(lambda v: 255 if v > DIFERENCIA_DE_FONDO else 0).getbbox()
    if caja is None:   # todo de un color (el logo llega a las cuatro esquinas): se deja entera
        return (0, 0, ancho, alto), None
    return caja, fondo


def emparejar(imagen, formato=''):
    """
    La copia pareja del logo (una imagen RGBA), o None si no hace falta
    (ya está justa, no es enorme y es un formato que todos leen).
    """
    imagen = ImageOps.exif_transpose(imagen.convert('RGBA'))
    imagen = sacar_cuadritos(imagen).convert('RGBA')
    ancho, alto = imagen.size
    caja, fondo = _caja_del_logo(imagen)
    if not caja:
        raise LogoNoSirve('La imagen está vacía.')
    izquierda, arriba, derecha, abajo = caja
    sobra = max(izquierda / ancho, arriba / alto, (ancho - derecha) / ancho, (alto - abajo) / alto)
    if sobra < .015 and max(ancho, alto) <= LADO_PAREJO * 1.25 and formato in ('PNG', 'JPEG', 'WEBP'):
        return None
    logo = imagen.crop(caja)
    if fondo is None:
        margen = round(max(logo.size) * MARGEN_TRANSPARENTE)
        color = (0, 0, 0, 0)
    else:
        margen = round(min(logo.size) * MARGEN_DE_COLOR)
        color = (*fondo, 255)
    con_margen = Image.new('RGBA', (logo.width + 2 * margen, logo.height + 2 * margen), color)
    con_margen.paste(logo, (margen, margen))
    con_margen.thumbnail((LADO_PAREJO, LADO_PAREJO), Image.LANCZOS)
    return con_margen


def _bajar(url):
    """Los bytes del logo (si es uno subido acá, del disco)."""
    subido = _archivo_subido(url)
    if subido:
        with default_storage.open(subido) as archivo:
            return archivo.read(PESO_MAXIMO_LOGO + 1)
    if not url.lower().startswith(('http://', 'https://')):
        raise LogoNoSirve('No es una dirección web.')
    pedido = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Kairos TV)', 'Accept': 'image/*'})
    try:
        with urllib.request.urlopen(pedido, timeout=8) as respuesta:
            if respuesta.geturl().split('?')[0].endswith('imgur.com/removed.png'):
                raise LogoRoto('imgur lo borró (manda su cartel "The image you are requesting does not exist").')
            return respuesta.read(PESO_MAXIMO_LOGO + 1)
    except urllib.error.HTTPError as error:
        if error.code in (404, 410):
            raise LogoRoto(f'Ya no existe (error {error.code}).') from None
        raise LogoNoSirve(f'No se pudo bajar: error {error.code}.') from None
    except (OSError, ValueError) as error:   # urllib.error.URLError y los timeouts son OSError
        raise LogoNoSirve(f'No se pudo bajar: {error}'[:200]) from None


def _preparar(url):
    """
    (url, bytes WEBP o None si queda el original, error, roto). Sin tocar la
    base: corre en paralelo.
    """
    try:
        datos = _bajar(url)
        if len(datos) > PESO_MAXIMO_LOGO:
            raise LogoNoSirve('Pesa más de 5 MB.')
        if b'<svg' in datos[:1000].lower():
            raise LogoNoSirve('Es un SVG: queda el original.')
        try:
            imagen = Image.open(BytesIO(datos))
            formato = imagen.format
            imagen.load()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError):
            raise LogoNoSirve('No es una imagen.') from None
        parejo = emparejar(imagen, formato)
        if parejo is None:
            return url, None, '', False
        salida = BytesIO()
        parejo.save(salida, 'WEBP', quality=90, method=4)
        return url, salida.getvalue(), '', False
    except LogoRoto as error:
        return url, None, str(error), True
    except LogoNoSirve as error:
        return url, None, str(error), False
    except Exception as error:   # una imagen rara no puede cortar la tanda entera
        return url, None, f'Error al prepararlo: {error}'[:200], False


def _guardar(url, webp, error, roto):
    from .models import LogoParejo
    clave = _clave_de(url)
    archivo = ''
    if webp:
        archivo = f'{CARPETA_PAREJOS}{clave}.webp'
        default_storage.delete(archivo)   # si se rehace, el mismo nombre (si no, Django le agrega letras)
        archivo = default_storage.save(archivo, ContentFile(webp))
    LogoParejo.objects.update_or_create(clave=clave, defaults={'url': url, 'archivo': archivo, 'error': error,
                                                               'roto': roto})


def _por_hacer():
    """Las direcciones de logos que todavía no tienen copia (o fallaron hace más de REINTENTAR_FALLADOS)."""
    from .models import LogoParejo
    from . import secciones
    contenidos = ['vivo', *(s.clave for s in secciones.nuevas() if s.forma == 'vivo')]
    urls = set(Canal.todos.filter(contenido__in=contenidos).exclude(logo='').values_list('logo', flat=True))
    hechas = {fila.url for fila in LogoParejo.objects.only('url', 'archivo', 'error', 'probado')
              if not fila.error or fila.probado > timezone.now() - REINTENTAR_FALLADOS}
    return urls, sorted(urls - hechas)


def emparejar_logos(segundos=SEGUNDOS_PARA_LOGOS, preparar=None):
    """
    Lo que hace el cron: prepara las copias que faltan (de a A_LA_VEZ, hasta
    `segundos`) y borra las que ya no usa ningún canal. Devuelve cuántas.
    """
    from .models import LogoParejo
    preparar = preparar or _preparar
    en_uso, pendientes = _por_hacer()
    hasta = time.monotonic() + segundos
    resultado = {'parejos': 0, 'iguales': 0, 'rotos': 0, 'fallados': 0, 'faltan': 0, 'borrados': 0}
    with ThreadPoolExecutor(A_LA_VEZ) as ejecutor:
        for desde in range(0, len(pendientes), A_LA_VEZ * 2):
            if time.monotonic() > hasta:
                resultado['faltan'] = len(pendientes) - desde
                break
            for url, webp, error, roto in ejecutor.map(preparar, pendientes[desde:desde + A_LA_VEZ * 2]):
                _guardar(url, webp, error, roto)
                resultado['parejos' if webp else 'rotos' if roto else 'fallados' if error else 'iguales'] += 1
    for fila in LogoParejo.objects.exclude(url__in=en_uso):
        if fila.archivo:
            default_storage.delete(fila.archivo)
        fila.delete()
        resultado['borrados'] += 1
    return resultado


def emparejar_logo_al_guardar(canal):
    """
    Lo que llaman las pantallas del panel al guardar un canal: su copia
    pareja apenas se confirma lo guardado (en los tests no corre: no sale a
    internet).
    """
    transaction.on_commit(lambda: emparejar_logo(canal))


def emparejar_logo(canal):
    """Al cambiar el logo en el panel: su copia pareja en el momento (si todavía no la tiene)."""
    from .models import LogoParejo
    if not canal.logo or not tiene_logo_parejo(canal.contenido):
        return
    if LogoParejo.objects.filter(clave=_clave_de(canal.logo)).exists():
        return
    _guardar(*_preparar(canal.logo))


def logos_parejos(urls):
    """
    {dirección original: la que hay que mostrar}: la de la copia pareja
    (relativa: /media/...), o '' si el logo está roto (van las iniciales).
    Las que no están, se muestran como vinieron.
    """
    from .models import LogoParejo
    por_clave = {_clave_de(url): url for url in set(urls) if url}
    return {por_clave[clave]: '' if roto else default_storage.url(archivo)
            for clave, archivo, roto in LogoParejo.objects.filter(clave__in=por_clave)
            .filter(Q(roto=True) | ~Q(archivo='')).values_list('clave', 'archivo', 'roto')}


def logos_rotos(urls):
    """{dirección: por qué está roto} de las que ya no tienen el logo (para avisarlo en el panel)."""
    from .models import LogoParejo
    por_clave = {_clave_de(url): url for url in set(urls) if url}
    return {por_clave[clave]: error for clave, error in LogoParejo.objects.filter(clave__in=por_clave, roto=True)
            .values_list('clave', 'error')}


def logo_para_mostrar(url, parejos):
    """La dirección del logo que se muestra (`parejos`: de logos_parejos)."""
    return parejos.get(url, url)


# ── Portadas de series ───────────────────────────────────────────────

def _clave(nombre):
    """Como organizar._clave: sin acentos, sin mayúsculas, sin espacios de más."""
    return ' '.join(clasificar.sin_acentos(nombre or '').split())[:90]


def portada_de(nombre):
    return PortadaDeSerie.objects.filter(clave=_clave(nombre)).values_list('imagen', flat=True).first() or ''


def portadas_de(nombres):
    """{nombre: imagen} de las series de `nombres` que tienen portada (con el nombre tal como vino)."""
    por_clave = {}
    for nombre in nombres:
        por_clave.setdefault(_clave(nombre), []).append(nombre)
    resultado = {}
    for clave, imagen in PortadaDeSerie.objects.filter(clave__in=por_clave).values_list('clave', 'imagen'):
        for nombre in por_clave[clave]:
            resultado[nombre] = imagen
    return resultado


def poner_portada(nombre, imagen):
    """Le pone (o cambia) la portada a la serie; con `imagen` vacía se la saca. Devuelve True si cambió."""
    clave = _clave(nombre)
    actual = PortadaDeSerie.objects.filter(clave=clave).first()
    vieja = actual.imagen if actual else ''
    if vieja == imagen:
        return False
    if not imagen:
        actual.delete()
    elif actual:
        actual.imagen, actual.nombre = imagen, nombre[:90]
        actual.save()
    else:
        PortadaDeSerie.objects.create(clave=clave, nombre=nombre[:90], imagen=imagen)
    soltar(vieja)
    return True


def mover_portada(viejo, nuevo):
    """
    Al renombrar una serie (o unirla con otra), la portada va con ella. Si la
    de destino ya tenía una, queda la del destino.
    """
    origen = PortadaDeSerie.objects.filter(clave=_clave(viejo)).first()
    if origen is None or _clave(viejo) == _clave(nuevo):
        if origen is not None:
            origen.nombre = nuevo[:90]
            origen.save()
        return
    if PortadaDeSerie.objects.filter(clave=_clave(nuevo)).exists():
        imagen = origen.imagen
        origen.delete()
        soltar(imagen)
        return
    origen.clave, origen.nombre = _clave(nuevo), nuevo[:90]
    origen.save()
