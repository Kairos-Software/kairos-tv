"""
Lo que el sistema HACE con los canales (capa Base).

Importar una lista es en tres pasos, para que una lista de miles de canales
no trabe el servidor y para que SOLO ENTRE LO QUE ESTÁ BIEN:

    importacion = crear_importacion(texto, 'lista.m3u')   # analiza todo (rápido, no sale a internet)
    procesar_lote(importacion, verificar_varias)          # prueba las próximas 50: quedan "aptas" o no, con el motivo
    ...                                                   # ...y así hasta que no quede ninguna por probar
    cargar_lote(importacion)                              # carga las aptas (de a 200) y recién ahí entran a la app

Qué pasa la prueba lo decide `juzgar` (formato, sonido, idioma del audio,
resolución, si llega fluido y si avanza: ver verificacion.py). Al terminar
de probar, `_revisar_series` saca las series que la app no podría mostrar
enteras (sin el capítulo 1 de la temporada 1; en una lista, también las
de menos de 3 capítulos).

La pantalla del panel llama a procesar_lote y cargar_lote una y otra vez y
muestra el avance. `importar_m3u()` hace todo de una vez (consola y pruebas).

La verificación se recibe como parámetro (`verificar`) en vez de llamarla
directo: así los tests pasan una de mentira y no salen a internet.
La real es `canales.verificacion.verificar_varias(fuentes, cabeceras=..., hasta=...)`.
"""

import itertools
import json
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError, transaction
from django.db.models import Count, F, Max, Q
from django.utils import timezone

from actividad.models import Accion
from actividad.registro import registrar

from . import clasificar, organizar, salud, secciones, youtube
from .analisis import NOMBRES_DE_IDIOMAS
from .consultas import fuentes_usables
from .m3u import EntradaM3U, leer_m3u, normalizar
from .models import (OCULTA_POR, Canal, Categoria, Contenido, EntradaImportada, Fuente, Importacion,
                     medidas_de_calidad)
from .verificacion import NOMBRES_DE_CODECS, Resultado

# De a cuántas se verifican, y cuánto puede tardar como máximo una tanda en
# EMPEZAR verificaciones (las que no llegan quedan para la tanda siguiente).
TAMANIO_LOTE = 50
SEGUNDOS_POR_LOTE = 40
# De a cuántas aptas se cargan (no sale a internet: es rápido)
TAMANIO_CARGA = 200

Estado = EntradaImportada.Estado
Causa = EntradaImportada.Causa

# ── Qué pasa la prueba ──
# Formatos de video que muchos aparatos no leen (imagen verde, cortada o negra con sonido)
CODECS_RECHAZADOS = {'mpeg2', 'vc1', 'h264_10'}
# Sonido que casi ningún aparato reproduce (se ve, pero no se escucha)
AUDIOS_QUE_NO_SE_ESCUCHAN = {'dts', 'truehd'}
# Menos líneas que esto se ve mal en una TV (480 y 576 = SD común, pasan)
ALTO_MINIMO = 360
# Segundos de video que tienen que llegar por segundo (menos: se corta a cada rato)
VELOCIDAD_MINIMA = 0.9


@dataclass
class ResultadoImportacion:
    canales_nuevos: int = 0
    fuentes_nuevas: int = 0
    repetidas: int = 0
    funcionan: int = 0
    caidas: int = 0
    sin_verificar: int = 0
    descartadas: int = 0

    def __str__(self):
        texto = (f'{self.canales_nuevos} canal(es) nuevo(s), {self.fuentes_nuevas} fuente(s) nueva(s), '
                 f'{self.repetidas} ya existían, {self.descartadas} descartada(s).')
        if self.funcionan or self.caidas:
            texto += f' Funcionan {self.funcionan}, no funcionan {self.caidas}, sin verificar {self.sin_verificar}.'
        return texto


@dataclass
class ResultadoVerificacion:
    funcionan: int = 0
    caidas: int = 0
    sin_verificar: int = 0
    revividas: int = 0   # estaban caídas y volvieron
    nuevas_caidas: int = 0

    def __str__(self):
        return (f'Funcionan {self.funcionan}, caídas {self.caidas}, sin verificar {self.sin_verificar} '
                f'({self.revividas} volvieron, {self.nuevas_caidas} se cayeron).')

    def sumar(self, otro):
        for campo in ('funcionan', 'caidas', 'sin_verificar', 'revividas', 'nuevas_caidas'):
            setattr(self, campo, getattr(self, campo) + getattr(otro, campo))


# ── Paso 1: analizar la lista ────────────────────────────────────────

def _sin_nombre(nombre):
    """Sin nombre de verdad: vacío, solo números/símbolos, o "Canal" a secas."""
    simple = clasificar.sin_acentos(nombre).strip()
    return not any(c.isalpha() for c in simple) or simple in ('canal', 'channel', 'sin nombre')


def _motivo_de_descarte(entrada, importacion, contenido, tipo, idioma, pais, nombre):
    """Por qué se descarta sin verificarla ('' = no se descarta)."""
    if importacion.descartar_vod and contenido != EntradaImportada.Contenido.VIVO:
        que = 'una película' if contenido == EntradaImportada.Contenido.PELICULA else 'un capítulo de serie'
        return f'Es {que}, no un canal en vivo.'
    if importacion.descartar_adultos and clasificar.para_adultos(entrada.nombre, entrada.categoria):
        return 'Es contenido para adultos.'
    if tipo == 'rtmp':
        return 'Es RTMP: la app todavía no reproduce ese formato.'
    if _sin_nombre(nombre):
        return 'No tiene un nombre definido.'
    aviso = clasificar.aviso_de_la_lista(entrada.nombre)
    if aviso:
        return aviso
    if importacion.solo_espanol and idioma == 'otro':
        return f'No está en español (país: {pais}).' if pais else 'No está en español.'
    if importacion.descartar_sin_logo and not entrada.logo.strip():
        return 'No tiene logo.'
    return ''


def crear_importacion(texto, archivo='', usuario=None, solo_espanol=False, descartar_sin_logo=False,
                      descartar_vod=False, descartar_adultos=True, a_fondo=False, categoria='', seccion=''):
    """
    Lee la lista y guarda cada canal como una EntradaImportada, con lo que se
    sabe de él (idioma, país, si es en vivo o película, formato). Las que no
    sirven quedan descartadas desde ya, con el motivo; las demás, pendientes
    de verificar. No sale a internet: tarda segundos aunque sean miles.
    `categoria`: todo va a esa (por nombre; se crea al cargar si no existe) en
    vez de a la que dice la lista. Igual se usa la de la lista para deducir
    idioma, país y si son capítulos de series.
    `seccion`: todo va a esa sección nueva (Radio, Música...) en vez de a En
    vivo, Películas o Series según lo que sea cada uno.
    Una lista exportada de acá (trae kairos-seccion) queda `de_kairos`.
    """
    leidas = leer_m3u(texto)
    importacion = _nueva_importacion(leidas, archivo, usuario, solo_espanol=solo_espanol,
                                     descartar_sin_logo=descartar_sin_logo, descartar_vod=descartar_vod,
                                     descartar_adultos=descartar_adultos, a_fondo=a_fondo, seccion=seccion)
    pendientes = _guardar_entradas(importacion, leidas, 1, categoria, set(Fuente.objects.values_list('url', flat=True)))
    importacion.total, importacion.para_verificar = len(leidas), pendientes
    _terminar_de_leer(importacion)
    return importacion


def _nueva_importacion(leidas, archivo='', usuario=None, **opciones):
    return Importacion.objects.create(
        archivo=archivo[:150], usuario=usuario if getattr(usuario, 'pk', None) else None,
        de_kairos=any(entrada.seccion for entrada in leidas), **opciones,
    )


def _terminar_de_leer(importacion):
    """Ya están todas las entradas: si no hay nada para probar, terminó; y queda anotado."""
    if not importacion.para_verificar:
        importacion.terminada = timezone.now()
    importacion.save(update_fields=['total', 'para_verificar', 'terminada', 'por_leer'])
    registrar(importacion.usuario, Accion.CREAR,
              f'Subió la lista de canales "{importacion.archivo}": {importacion.total} canal(es), '
              f'{importacion.para_verificar} para verificar.', modulo='canales')


def _guardar_entradas(importacion, leidas, desde, categoria, ya_guardadas, vistas=None):
    """
    Guarda `leidas` como EntradaImportada desde la posición `desde`, con lo que
    se sabe de cada una (ver crear_importacion). `ya_guardadas`: las direcciones
    ya cargadas; `vistas`: las que ya aparecieron antes en esta lista. Devuelve
    cuántas quedaron pendientes de probar.
    """
    seccion = importacion.seccion
    validas = {clave for clave, _ in secciones.todas()}
    vistas = set() if vistas is None else vistas
    entradas = []
    for posicion, entrada in enumerate(leidas, start=desde):
        nombre = clasificar.limpiar_nombre(entrada.nombre)
        idioma, pais = clasificar.idioma_y_pais(entrada.nombre, entrada.categoria, entrada.pais,
                                                entrada.tvg_id, entrada.idioma)
        # Con una sección nueva elegida, todo va ahí (una radio puede parecer "un archivo", o sea una película).
        # Si no, la que dice una lista exportada de acá (si esa sección existe) o la que parece por la dirección.
        contenido = (seccion or (entrada.seccion if entrada.seccion in validas else '')
                     or clasificar.contenido(entrada.url, entrada.categoria))
        tipo = clasificar.formato(entrada.url)

        estado, motivo = Estado.PENDIENTE, ''
        if entrada.url in vistas:
            estado, motivo = Estado.REPETIDA, 'La misma dirección aparece antes en esta lista.'
        elif entrada.url in ya_guardadas:
            estado, motivo = Estado.REPETIDA, 'Esta dirección ya estaba cargada.'
        else:
            # (descartar películas y series no aplica: se eligió a qué sección va todo)
            motivo = _motivo_de_descarte(entrada, importacion, Contenido.VIVO if seccion else contenido, tipo,
                                         idioma, pais, nombre)
            if motivo:
                estado = Estado.DESCARTADA
        vistas.add(entrada.url)

        entradas.append(EntradaImportada(
            importacion=importacion, posicion=posicion,
            nombre_original=entrada.nombre[:200], nombre=(nombre or 'Sin nombre')[:120],
            logo=entrada.logo[:500], categoria=(categoria or entrada.categoria)[:80], numero=entrada.numero[:10],
            tvg_id=entrada.tvg_id[:120], pais=pais, idioma=idioma, contenido=contenido,
            url=entrada.url[:1000], tipo=tipo, user_agent=entrada.user_agent[:300], referer=entrada.referer[:500],
            estado=estado, motivo=motivo,
        ))
    EntradaImportada.objects.bulk_create(entradas, batch_size=1000)
    return sum(1 for e in entradas if e.estado == Estado.PENDIENTE)


# ── Una lista grande: se lee de a tandas ─────────────────────────────

# Hasta tantas entradas se leen al subirla (unos segundos). Una más grande
# (una lista completa de un proveedor: 268 000 entradas) tardaba más de un
# minuto en una PC; en un servidor chico, más de los 5 minutos que espera
# gunicorn. Esas se guardan aparte y la pantalla las va leyendo de a tandas.
LEER_DE_UNA = 20_000
LEER_POR_TANDA = 15_000

# Las listas a medio leer (tienen usuarios y contraseñas: NO van en media/, que se publica)
CARPETA_DE_LISTAS = settings.BASE_DIR / 'privado' / 'listas'


def preparar_importacion(texto, archivo='', usuario=None, categoria='', **opciones):
    """
    Como crear_importacion (mismas opciones), pero si la lista es grande no la
    lee entera ahora: la deja guardada para leerla de a tandas (leer_lote).
    """
    leidas = leer_m3u(texto)
    if len(leidas) <= LEER_DE_UNA:
        return crear_importacion(texto, archivo, usuario, categoria=categoria, **opciones)
    importacion = _nueva_importacion(leidas, archivo, usuario, total=len(leidas), por_leer=len(leidas), **opciones)
    CARPETA_DE_LISTAS.mkdir(parents=True, exist_ok=True)
    with _lista_guardada(importacion).open('w', encoding='utf-8') as guardada:
        guardada.write(json.dumps({'categoria': categoria}) + '\n')
        for entrada in leidas:
            guardada.write(json.dumps(asdict(entrada), ensure_ascii=False) + '\n')
    return importacion


def _lista_guardada(importacion):
    return CARPETA_DE_LISTAS / f'importacion-{importacion.pk}.jsonl'


def leer_lote(importacion, tamanio=LEER_POR_TANDA):
    """Lee la próxima tanda de una lista grande (preparar_importacion). Devuelve cómo va (ver `lectura`)."""
    with transaction.atomic():
        if not _bloquear(importacion):
            return {**lectura(importacion), 'ocupada': True}
        importacion.refresh_from_db()
        if not importacion.por_leer:
            return lectura(importacion)
        hechas = importacion.total - importacion.por_leer
        try:
            with _lista_guardada(importacion).open(encoding='utf-8') as guardada:
                categoria = json.loads(guardada.readline()).get('categoria', '')
                leidas = [EntradaM3U(**json.loads(linea))
                          for linea in itertools.islice(guardada, hechas, hechas + tamanio)]
        except FileNotFoundError:
            leidas, categoria = [], ''
        if leidas:
            importacion.para_verificar += _guardar_entradas(
                importacion, leidas, hechas + 1, categoria, set(Fuente.objects.values_list('url', flat=True)),
                set(importacion.entradas.values_list('url', flat=True)))
        # Sin el archivo (se borró a mano), lo leído hasta acá es la lista
        importacion.por_leer = importacion.por_leer - len(leidas) if leidas else 0
        if importacion.por_leer:
            importacion.save(update_fields=['para_verificar', 'por_leer'])
        else:
            importacion.total = hechas + len(leidas)
            _lista_guardada(importacion).unlink(missing_ok=True)
            _terminar_de_leer(importacion)
    return lectura(importacion)


def lectura(importacion):
    """Cuánto se leyó de una lista grande."""
    leidas = importacion.total - importacion.por_leer
    return {
        'total': importacion.total,
        'leidas': leidas,
        'porcentaje': 100 if not importacion.total else round(100 * leidas / importacion.total),
        'terminada': not importacion.por_leer,
    }


def _donde_esta(video, nombre, contenido, activo):
    """
    'Ya está cargado (en Series; para verlo, buscá iUeAn7m2Il8 en Organizar) como «Casi Ángeles S01 E120 ...»'.
    El ID va antes que el nombre: si el texto no entra en el motivo, se corta el nombre y no el ID.
    """
    quitado = ', quitado de la app' if not activo else ''
    return (f'Ya está cargado (en {secciones.nombre(contenido)}{quitado}; para verlo, buscá {video.id} en Organizar) '
            f'como «{nombre}».')[:200]


def crear_importacion_de_youtube(listado, usuario=None, categoria='', minimo_minutos=40, solo_espanol=True,
                                 serie='', temporada=1, maximo_minutos=None, seccion='', segun_titulo=False):
    """
    Como crear_importacion, pero con los videos de un canal oficial de YouTube
    (youtube.videos_del_canal): cada video es una película, o un capítulo si
    el título dice temporada y capítulo ("T1 E2"). Después se prueba y se
    carga igual que una lista (procesar_lote, cargar_lote).
      categoria: dónde van todos ("Infantiles"); vacía = según el género del título.
      minimo_minutos: los más cortos se descartan (avances, clips, Shorts).
      maximo_minutos: los más largos también (None = sin límite). Para
             música, por ejemplo, de 2 a 6: así no entran los conciertos enteros.
      seccion: todos van a esa sección nueva (Música...) en vez de a Películas;
             sin categoría elegida, a una con el nombre del canal (el artista).
      solo_espanol: se descarta lo que el título dice que está en inglés.
      serie: TODOS los videos son capítulos de esta serie ("Masha y el Oso"),
             numerados del más viejo al más nuevo, siguiendo después del último
             que ya esté cargado. Los números definitivos se ponen al terminar
             de probar (_numerar_capitulos): así no quedan huecos por los que
             no pasan y siempre hay capítulo 1.
      segun_titulo: (serie) cada video va a la temporada y al capítulo que
             dice su título ("Temporada 3 Capítulo 33"); `temporada` es para
             los que no dicen la suya. Para canales con todo mezclado.
    """
    if serie:
        serie = organizar.nombre_de_serie_valido(serie)
    temporada = max(1, min(int(temporada or 1), 99))
    archivo = f'YouTube: {listado.nombre}'[:150]
    importacion = Importacion.objects.create(
        archivo=archivo, usuario=usuario if getattr(usuario, 'pk', None) else None, solo_espanol=solo_espanol,
        serie=serie, temporada=temporada, seccion='' if serie else seccion, segun_titulo=bool(serie and segun_titulo),
    )
    if serie:
        seccion = ''
    # Lo que ya está cargado, y DÓNDE: "ya estaba" sin decir dónde parecía que el video no aparecía
    ya_guardadas = {url: (nombre, contenido, activo) for url, nombre, contenido, activo in
                    Fuente.objects.values_list('url', 'canal__nombre', 'canal__contenido', 'canal__activo')}
    vistas = set()
    # Una serie va en el orden de sus capítulos (posición 1 = el primero); películas, como vienen
    videos = youtube.en_orden_de_capitulos(listado) if serie else listado.videos
    nombres = youtube.nombres_distintos([video.titulo for video in videos])
    generos = _genero_de_cada_serie(videos) if not (serie or categoria) else {}
    numero = organizar.ultimo_capitulo(serie, temporada) if serie else 0
    entradas = []
    for posicion, (video, nombre) in enumerate(zip(videos, nombres), start=1):
        # En una sección nueva (Música...) cada video va suelto, aunque el título diga "T1 E2"
        capitulo = None if (serie or seccion) else youtube.capitulo(video.titulo)
        nombre = capitulo or nombre
        idioma = 'otro' if youtube.en_ingles(video.titulo) else 'es'
        estado, motivo = Estado.PENDIENTE, ''
        if video.url in vistas:
            estado, motivo = Estado.REPETIDA, 'El mismo video aparece antes en este canal.'
        elif video.url in ya_guardadas:
            estado, motivo = Estado.REPETIDA, _donde_esta(video, *ya_guardadas[video.url])
        elif not video.segundos:
            estado, motivo = Estado.DESCARTADA, 'No se sabe cuánto dura (puede ser un vivo o un estreno programado).'
        elif video.segundos < minimo_minutos * 60:
            estado = Estado.DESCARTADA
            motivo = f'Dura {video.segundos // 60} min: es un video corto (se pidieron de {minimo_minutos} min o más).'
        elif maximo_minutos and video.segundos > maximo_minutos * 60:
            estado = Estado.DESCARTADA
            motivo = (f'Dura {video.segundos // 60} min: es más largo de lo pedido (hasta {maximo_minutos} min).')
        elif solo_espanol and idioma == 'otro':
            estado, motivo = Estado.DESCARTADA, 'El título dice que está en inglés.'
        elif clasificar.para_adultos(video.titulo, ''):
            estado, motivo = Estado.DESCARTADA, 'Es contenido para adultos.'
        elif _sin_nombre(nombre) and not serie:
            estado, motivo = Estado.DESCARTADA, 'No tiene un nombre definido.'
        vistas.add(video.url)
        if serie and estado == Estado.PENDIENTE:
            # provisorio: el definitivo, al terminar de probar
            dice = organizar.temporada_y_numero_del_titulo(video.titulo) if importacion.segun_titulo else None
            if dice:
                de_temporada, de_numero = dice[0] or temporada, dice[1]
            else:
                numero += 1
                de_temporada, de_numero = temporada, numero
            nombre = organizar.nombre_de_capitulo(serie, de_temporada, de_numero,
                                                  organizar.titulo_del_capitulo(nombre, serie))
        if categoria:
            de_la_categoria = categoria
        elif seccion:   # Música: el canal es la categoría (el artista)
            de_la_categoria = listado.nombre
        elif capitulo:   # todos los capítulos de una serie, en la misma categoría
            de_la_categoria = generos.get(clasificar.episodio(capitulo)[0].lower(), '')
        else:
            de_la_categoria = youtube.genero(video.titulo)
        entradas.append(EntradaImportada(
            importacion=importacion, posicion=posicion,
            nombre_original=video.titulo[:200], nombre=(nombre or 'Sin nombre')[:120], logo=video.imagen,
            categoria=de_la_categoria[:80], tvg_id=video.id, idioma=idioma,
            contenido=seccion or (Contenido.SERIE if (serie or capitulo) else Contenido.PELICULA),
            url=video.url, tipo=youtube.TIPO, estado=estado, motivo=motivo,
        ))
    EntradaImportada.objects.bulk_create(entradas, batch_size=1000)

    importacion.total = len(entradas)
    importacion.para_verificar = sum(1 for e in entradas if e.estado == Estado.PENDIENTE)
    if not importacion.para_verificar:
        importacion.terminada = timezone.now()
    importacion.save(update_fields=['total', 'para_verificar', 'terminada'])
    como = f' como la serie "{serie}"' if serie else ''
    registrar(usuario, Accion.CREAR,
              f'Trajo los videos del canal de YouTube "{listado.nombre}"{como}: {importacion.total} video(s), '
              f'{importacion.para_verificar} para verificar.', modulo='canales')
    return importacion


def _genero_de_cada_serie(videos):
    """
    {serie: género} de las series que el título numera ("T1 E2"): el género que
    más dicen sus capítulos. Así una serie no queda repartida en varias
    categorías (la app la mostraría en la del capítulo que llegue primero).
    """
    votos = {}
    for video in videos:
        capitulo = youtube.capitulo(video.titulo)
        genero = youtube.genero(video.titulo)
        if capitulo and genero:
            por_genero = votos.setdefault(clasificar.episodio(capitulo)[0].lower(), {})
            por_genero[genero] = por_genero.get(genero, 0) + 1
    return {serie: max(por_genero, key=por_genero.get) for serie, por_genero in votos.items()}


def _numerar_capitulos(importacion):
    """
    Traída como UNA serie: al terminar de probar, los capítulos que pasaron se
    numeran de corrido desde el último que ya esté cargado (o desde el 1). Así
    no quedan huecos por los que no pasaron y la serie siempre tiene su
    capítulo 1 (la app no muestra series sin él).
    """
    if not importacion.serie:
        return
    aptas = list(importacion.entradas.filter(estado=Estado.APTA).order_by('posicion'))
    if importacion.segun_titulo:
        return _numerar_segun_el_titulo(importacion, aptas)
    numero = organizar.ultimo_capitulo(importacion.serie, importacion.temporada)
    for entrada in aptas:
        numero += 1
        entrada.nombre = organizar.nombre_de_capitulo(
            importacion.serie, importacion.temporada, numero,
            organizar.titulo_del_capitulo(entrada.nombre, importacion.serie))
    EntradaImportada.objects.bulk_update(aptas, ['nombre'])


def _numerar_segun_el_titulo(importacion, aptas):
    """
    Cada capítulo a la temporada y al número que dice su título. Los que no
    dicen número (o repiten uno que ya está, en la serie o en esta tanda) van
    al final de su temporada: así nunca quedan dos con el mismo número. Para
    revisar después: la serie → "Ordenar todo según los títulos".
    """
    serie = importacion.serie
    ocupados = set()
    for canal in organizar.capitulos_de([serie]):
        _, temporada, numero, _ = clasificar.episodio(canal.nombre)
        ocupados.add((temporada, numero))
    al_final = []
    for entrada in aptas:
        titulo = organizar.titulo_del_capitulo(entrada.nombre, serie)   # como en _numerar_capitulos
        dice = organizar.temporada_y_numero_del_titulo(entrada.nombre_original)
        lugar = (dice[0] or importacion.temporada, dice[1]) if dice and dice[1] > 0 else None
        if lugar is None or lugar in ocupados:
            al_final.append((entrada, lugar[0] if lugar else importacion.temporada, titulo))
            continue
        ocupados.add(lugar)
        entrada.nombre = organizar.nombre_de_capitulo(serie, lugar[0], lugar[1], titulo)
    for entrada, temporada, titulo in al_final:
        numero = max((n or 0 for t, n in ocupados if t == temporada), default=0) + 1
        ocupados.add((temporada, numero))
        entrada.nombre = organizar.nombre_de_capitulo(serie, temporada, numero, titulo)
    EntradaImportada.objects.bulk_update(aptas, ['nombre'])


# ── Paso 2: probar de a tandas ───────────────────────────────────────

def juzgar(resultado, importacion):
    """
    ¿La fuente que respondió está bien? (causa, motivo) si no pasa; ('', '')
    si pasa. Lo que la prueba no pudo averiguar no se cuenta en contra.
    """
    if resultado.codec in CODECS_RECHAZADOS:
        return Causa.FORMATO, (f'El video es {NOMBRES_DE_CODECS[resultado.codec]}: muchos aparatos lo muestran '
                               f'verde, cortado o no lo muestran.')
    if not resultado.a_fondo:
        return '', ''
    if resultado.con_audio is False:
        return Causa.SIN_SONIDO, 'No tiene sonido: el video no trae ninguna pista de audio.'
    if resultado.audios and set(resultado.audios) <= AUDIOS_QUE_NO_SE_ESCUCHAN:
        return Causa.SIN_SONIDO, (f'El sonido es {"/".join(a.upper() for a in resultado.audios)}: casi ningún '
                                  f'aparato lo reproduce.')
    if importacion.solo_espanol and resultado.idiomas and 'es' not in resultado.idiomas:
        idiomas = ', '.join(NOMBRES_DE_IDIOMAS.get(i, i) for i in resultado.idiomas)
        return Causa.IDIOMA, f'El audio está en {idiomas} (no trae español).'
    if 0 < resultado.alto < ALTO_MINIMO:
        return Causa.BAJA_CALIDAD, f'La imagen es de {resultado.alto}p: en una TV se ve muy mal.'
    if resultado.congelada:
        return Causa.SE_CORTA, 'La señal está congelada: la lista no avanza (no llegan pedazos nuevos).'
    if resultado.se_corto:
        return Causa.SE_CORTA, 'El video dejó de llegar mientras se probaba.'
    if resultado.velocidad and resultado.velocidad < VELOCIDAD_MINIMA:
        return Causa.LENTA, (f'Llega más lento de lo que se reproduce (x{resultado.velocidad:.1f}): '
                             f'se cortaría a cada rato.')
    return '', ''


def _anotar_prueba(entrada, resultado):
    """Guarda en la entrada lo que dio la prueba (para cargarla después sin volver a probar)."""
    entrada.tipo = resultado.tipo or entrada.tipo
    entrada.codec = resultado.codec
    entrada.calidad = resultado.calidad() if resultado.a_fondo else ''
    entrada.estado_fuente = resultado.estado
    if resultado.user_agent and not entrada.user_agent:
        entrada.user_agent = resultado.user_agent
    # El idioma del audio manda sobre lo que se dedujo del nombre
    if resultado.idiomas:
        entrada.idioma = 'es' if 'es' in resultado.idiomas else 'otro'


def _motivo_apta(resultado):
    if resultado is None:
        return 'Sin probar.'
    motivos = ['Pasó todas las pruebas.' if resultado.a_fondo else 'Responde.']
    if resultado.user_agent:
        motivos.append('Anda presentándose como VLC.')
    if resultado.estado == Fuente.Estado.SIN_VERIFICAR:
        motivos = [resultado.error or 'No se pudo verificar.']
    return ' '.join(motivos)


# Al importar una lista M3U, una serie con menos capítulos que esto no entra
MINIMO_DE_CAPITULOS_EN_LISTAS = 3


def _revisar_series(importacion):
    """
    Al terminar de probar: las series que la app no mostraría (como
    consultas.Serie.completa: hace falta el capítulo 1 de la temporada 1)
    no pasan. Cuentan los capítulos aptos de esta lista más los que ya están
    cargados y se ven.

    Una LISTA (M3U) además pide MINIMO_DE_CAPITULOS_EN_LISTAS: ahí suelen venir
    series sueltas o a medias. Lo que se trae a propósito como serie (YouTube
    "Es una serie") entra desde su primer capítulo: puede ser una serie nueva.
    Una lista exportada de acá, también: esas series ya estaban aceptadas.
    """
    minimo = 1 if importacion.serie or importacion.de_kairos else MINIMO_DE_CAPITULOS_EN_LISTAS
    aptas = list(importacion.entradas.filter(estado=Estado.APTA, contenido=Contenido.SERIE))
    if not aptas:
        return 0
    ya_cargados = {}
    for nombre in (Canal.objects.filter(contenido=Contenido.SERIE, activo=True,
                                        pk__in=fuentes_usables().values('canal'))
                   .values_list('nombre', flat=True)):
        serie, temporada, numero, _ = clasificar.episodio(nombre)
        ya_cargados.setdefault(serie.lower(), set()).add((temporada, numero))
    por_serie = {}
    for entrada in aptas:
        serie, temporada, numero, _ = clasificar.episodio(entrada.nombre)
        por_serie.setdefault(serie.lower(), (serie, []))[1].append((entrada, temporada, numero))

    rechazadas = []
    for clave, (serie, capitulos) in por_serie.items():
        todos = ya_cargados.get(clave, set()) | {(temporada, numero) for _, temporada, numero in capitulos}
        if (1, 1) in todos and len(todos) >= minimo:
            continue
        falta = ('el capítulo 1 de la temporada 1. La app no la mostraría' if (1, 1) not in todos
                 else f'tener al menos {minimo} capítulos (en una lista, una serie tan corta suele estar a medias)')
        for entrada, _, _ in capitulos:
            entrada.estado, entrada.causa = Estado.RECHAZADA, Causa.SERIE_INCOMPLETA
            entrada.motivo = (f'Serie incompleta: de "{serie}" pasaron {len(capitulos)} capítulo(s) y le falta '
                              f'{falta}.')[:200]
            rechazadas.append(entrada)
    EntradaImportada.objects.bulk_update(rechazadas, ['estado', 'causa', 'motivo'])
    return len(rechazadas)


# ── Paso 3: cargar las aptas ─────────────────────────────────────────

class _IndiceDeCanales:
    """
    Los canales existentes por nombre normalizado, para reconocer el mismo
    canal escrito distinto ("ES: (HD) DAZN F1" = "DAZN F1 FHD"). Si los dos
    tienen país y no coincide, se toman como canales distintos (la ESPN de
    España no es la de Argentina). Una película nunca se junta con un canal
    en vivo del mismo nombre.

    Un capítulo también se reconoce por su serie, temporada y número, como lo
    agrupa la app: "Boruto S01 E05" = "Boruto S01 E05 El regreso". Así, al
    mandar capítulos a una serie que ya existe, el que ya estaba suma una
    fuente en vez de quedar repetido. Y de cada serie se sabe en qué categoría
    está (la de la mayoría de sus capítulos): los capítulos nuevos van ahí.
    """

    def __init__(self):
        self.por_nombre = {}
        self.por_capitulo = {}
        self.categorias_de_serie = {}
        self._categorias = {}
        for canal in Canal.objects.all():
            self.agregar(canal)

    @staticmethod
    def _serie(nombre):
        """(clave de la serie, temporada, número) como la app (sin mayúsculas, con acentos)."""
        serie, temporada, numero, _ = clasificar.episodio(nombre)
        return serie.lower(), temporada, numero

    def agregar(self, canal):
        self.por_nombre.setdefault((normalizar(canal.nombre), canal.contenido), []).append(canal)
        if canal.contenido == Contenido.SERIE:
            serie, temporada, numero = self._serie(canal.nombre)
            if numero is not None:
                self.por_capitulo.setdefault((serie, temporada, numero), canal)
            votos = self.categorias_de_serie.setdefault(serie, {})
            votos[canal.categoria_id] = votos.get(canal.categoria_id, 0) + 1

    def buscar(self, nombre, pais='', contenido=Canal.contenido.field.default):
        for canal in self.por_nombre.get((normalizar(nombre), contenido), []):
            if not (canal.pais and pais and canal.pais != pais):
                return canal
        if contenido == Contenido.SERIE:
            serie, temporada, numero = self._serie(nombre)
            if numero is not None:
                return self.por_capitulo.get((serie, temporada, numero))
        return None

    def categoria_de_la_serie(self, nombre):
        """La categoría (Categoria) de la serie de ese capítulo, si ya está en el panel y tiene una; si no, None."""
        votos = self.categorias_de_serie.get(self._serie(nombre)[0])
        if not votos:
            return None
        pk = max(votos, key=votos.get)
        if pk and pk not in self._categorias:
            self._categorias[pk] = Categoria.objects.filter(pk=pk).first()
        return self._categorias.get(pk)


def _resultado_guardado(entrada):
    """Lo que dio la prueba, guardado en la entrada (None = no se probó)."""
    if not entrada.estado_fuente:
        return None
    return Resultado(entrada.estado_fuente, tipo=entrada.tipo, codec=entrada.codec)


def _agregar(entrada, resultado, indice, categorias, origen, usuario, ahora):
    """Crea el canal (si no existe) y la fuente. Devuelve True si el canal es nuevo."""
    canal = indice.buscar(entrada.nombre, entrada.pais, entrada.contenido)
    nuevo = canal is None
    if nuevo:
        # Un capítulo de una serie que ya está en el panel va a la categoría de esa serie (una serie va en UNA)
        categoria = indice.categoria_de_la_serie(entrada.nombre) if entrada.contenido == Contenido.SERIE else None
        # Si no, respeta lo que se ordenó en el panel: si "Argentina" se juntó en "Noticias", va a "Noticias"
        categoria = categoria or organizar.categoria_por_nombre(entrada.categoria, entrada.contenido, categorias,
                                                                usuario)
        canal = Canal(nombre=entrada.nombre, numero=entrada.numero, logo=entrada.logo, categoria=categoria,
                      tvg_id=entrada.tvg_id, pais=entrada.pais, idioma=entrada.idioma, contenido=entrada.contenido)
        canal.marcar_autor(usuario)
        canal.save()
        indice.agregar(canal)
    elif not canal.logo and entrada.logo:
        canal.logo = entrada.logo   # el canal no tenía logo y esta lista sí lo trae
        canal.save(update_fields=['logo', 'modificado'])

    tipo = (resultado.tipo if resultado and resultado.tipo else entrada.tipo) or 'hls'
    estado = resultado.estado if resultado else Fuente.Estado.SIN_VERIFICAR
    prioridad = (canal.fuentes.aggregate(maximo=Max('prioridad'))['maximo'] or 0) + 1
    user_agent = entrada.user_agent or (resultado.user_agent if resultado else '')
    Fuente.objects.create(
        canal=canal, url=entrada.url, tipo=tipo, prioridad=prioridad, origen=origen[:150],
        user_agent=user_agent, referer=entrada.referer, estado=estado, codec=resultado.codec if resultado else '',
        error=resultado.error[:200] if resultado else '', verificada=ahora if resultado else None,
        calidad=entrada.calidad, **medidas_de_calidad(entrada.calidad), medida=ahora if entrada.calidad else None,
        **salud.al_cargar(estado, ahora),
    )

    motivos = ['Canal nuevo.' if nuevo else f'Se sumó como fuente alternativa de "{canal.nombre}".']
    if entrada.calidad:
        motivos.append(entrada.calidad + '.')
    if resultado and resultado.estado == Fuente.Estado.SIN_VERIFICAR:
        motivos.append(resultado.error or 'No se pudo verificar.')
    elif not resultado:
        motivos.append('Sin verificar.')
    entrada.estado, entrada.motivo, entrada.canal, entrada.tipo = Estado.AGREGADA, ' '.join(motivos), canal, tipo
    return nuevo


def _bloquear(importacion):
    """Si otra pestaña ya está trabajando con esta importación, False (hay que esperar)."""
    try:
        Importacion.objects.select_for_update(nowait=True).get(pk=importacion.pk)
    except DatabaseError:
        return False
    return True


CAMPOS_DE_LA_PRUEBA = ['estado', 'motivo', 'causa', 'canal', 'tipo', 'codec', 'calidad', 'estado_fuente',
                       'user_agent', 'idioma']


SIN_CATEGORIA = '~'


@dataclass(frozen=True)
class Seleccion:
    """
    La parte de una lista con la que se está trabajando: En vivo, Películas o
    Series (`contenido`), una categoría (SIN_CATEGORIA = las que no tienen) y lo
    que se buscó. Vacía = toda la lista. Probar, cargar y descartar se hacen
    sobre ella: en una lista de 268 000 entradas no se prueba todo de una.
    """
    contenido: str = ''
    categoria: str = ''
    texto: str = ''

    @classmethod
    def de(cls, datos):
        """La de los parámetros de la pantalla (?contenido=&categoria=&q=)."""
        return cls(datos.get('contenido', '').strip(), datos.get('categoria', '').strip(), datos.get('q', '').strip())

    @property
    def vacia(self):
        return not (self.contenido or self.categoria or self.texto)

    def aplicar(self, entradas):
        if self.contenido:
            entradas = entradas.filter(contenido=self.contenido)
        if self.categoria:
            entradas = entradas.filter(categoria='' if self.categoria == SIN_CATEGORIA else self.categoria)
        if self.texto:
            entradas = entradas.filter(Q(nombre__icontains=self.texto) | Q(nombre_original__icontains=self.texto)
                                       | Q(categoria__icontains=self.texto))
        return entradas

    def como_datos(self):
        return {'contenido': self.contenido, 'categoria': self.categoria, 'q': self.texto}


TODA = Seleccion()


def procesar_lote(importacion, verificar=None, tamanio=TAMANIO_LOTE, segundos=SEGUNDOS_POR_LOTE, seleccion=TODA):
    """
    Prueba las próximas `tamanio` entradas pendientes (de `seleccion`): las que
    pasan quedan "aptas" (todavía no se cargan: ver cargar_lote); las que no,
    "no responde" o "no pasó la prueba", con el motivo. Sin `verificar`, quedan
    aptas sin probar. Devuelve el avance (ver `progreso`).

    Si otra pestaña ya está procesando esta misma importación, no hace nada
    y devuelve el avance con "ocupada": la pantalla espera y vuelve a pedir.
    """
    with transaction.atomic():
        if not _bloquear(importacion):
            return {**progreso(importacion, seleccion), 'ocupada': True}
        if importacion.por_leer:
            return progreso(importacion, seleccion)

        pendientes = list(seleccion.aplicar(importacion.entradas.filter(estado=Estado.PENDIENTE))
                          .order_by('posicion')[:tamanio])
        indice = _IndiceDeCanales()
        a_verificar = []
        for entrada in pendientes:
            canal = indice.buscar(entrada.nombre, entrada.pais, entrada.contenido)
            if canal is not None and not canal.activo:
                # Lo quitaron a mano: no se vuelve a meter por la ventana
                entrada.estado, entrada.canal = Estado.DESCARTADA, canal
                entrada.motivo = f'El canal "{canal.nombre}" está quitado ({canal.motivo_quitado or "a mano"}).'[:200]
            elif Fuente.objects.filter(url=entrada.url).exists():   # la cargó otra importación mientras tanto
                entrada.estado, entrada.motivo = Estado.REPETIDA, 'Esta dirección ya estaba cargada.'
            else:
                a_verificar.append(entrada)

        resultados = {}
        if verificar and a_verificar:
            hasta = time.monotonic() + segundos if segundos else None
            resultados = verificar(
                {e.url: e.tipo or 'hls' for e in a_verificar},
                cabeceras={e.url: (e.user_agent, e.referer) for e in a_verificar if e.user_agent or e.referer},
                hasta=hasta,
            )

        for entrada in a_verificar:
            resultado = resultados.get(entrada.url)
            if verificar and resultado is None:
                continue   # no llegó a probarse: sigue pendiente para la próxima tanda
            if resultado and resultado.estado == Fuente.Estado.CAIDA:
                entrada.estado, entrada.motivo = Estado.CAIDA, resultado.error[:200]
                entrada.tipo = resultado.tipo or entrada.tipo
                continue
            if resultado:
                _anotar_prueba(entrada, resultado)
                causa, motivo = juzgar(resultado, importacion)
                if causa:
                    entrada.estado, entrada.causa, entrada.motivo = Estado.RECHAZADA, causa, motivo[:200]
                    continue
            entrada.estado, entrada.causa, entrada.motivo = Estado.APTA, '', _motivo_apta(resultado)[:200]

        EntradaImportada.objects.bulk_update(pendientes, CAMPOS_DE_LA_PRUEBA)

        if not importacion.entradas.filter(estado=Estado.PENDIENTE).exists():
            _numerar_capitulos(importacion)
            _revisar_series(importacion)
            importacion.terminada = timezone.now()
            importacion.save(update_fields=['terminada'])
            avance = progreso(importacion)
            registrar(importacion.usuario, Accion.CREAR,
                      f'Terminó de probar "{importacion.archivo}": {avance["aptas"]} apta(s), '
                      f'{avance["rechazadas"]} no pasaron la prueba, {avance["caidas"]} no responden, '
                      f'{avance["descartadas"]} descartada(s), {avance["repetidas"]} ya estaban.', modulo='canales')
        elif pendientes and not seleccion.aplicar(importacion.entradas.filter(estado=Estado.PENDIENTE)).exists():
            # Terminó de probar esta parte (una categoría...): sus series ya se pueden revisar y cargar
            _revisar_series(importacion)
    return progreso(importacion, seleccion)


def falta_probar(importacion, seleccion):
    """
    Si todavía hay que probar algo antes de cargar `seleccion`. Las series se
    revisan (¿está el capítulo 1?) al terminar de probar su parte. Lo que se
    trajo como UNA serie de YouTube se numera recién al terminar toda la lista.
    """
    if importacion.serie:
        seleccion = TODA
    return seleccion.aplicar(importacion.entradas.filter(estado=Estado.PENDIENTE)).exists()


def cargar_lote(importacion, tamanio=TAMANIO_CARGA, seleccion=TODA):
    """
    Carga las próximas `tamanio` aptas (de `seleccion`): crea el canal (si no
    existe) o suma la dirección como fuente alternativa. Devuelve el avance,
    más cuántos canales nuevos se crearon en esta tanda.
    """
    canales_nuevos = 0
    if importacion.por_leer or falta_probar(importacion, seleccion):
        return {**progreso(importacion, seleccion), 'canales_nuevos': 0}
    with transaction.atomic():
        if not _bloquear(importacion):
            return {**progreso(importacion, seleccion), 'ocupada': True, 'canales_nuevos': 0}
        aptas = list(seleccion.aplicar(importacion.entradas.filter(estado=Estado.APTA)).order_by('posicion')[:tamanio])
        indice = _IndiceDeCanales()
        categorias = organizar.indice_de_categorias()
        ahora = timezone.now()
        for entrada in aptas:
            canal = indice.buscar(entrada.nombre, entrada.pais, entrada.contenido)
            if canal is not None and not canal.activo:
                entrada.estado, entrada.canal = Estado.DESCARTADA, canal
                entrada.motivo = f'El canal "{canal.nombre}" está quitado ({canal.motivo_quitado or "a mano"}).'[:200]
            elif Fuente.objects.filter(url=entrada.url).exists():
                entrada.estado, entrada.motivo = Estado.REPETIDA, 'Esta dirección ya estaba cargada.'
            else:
                canales_nuevos += _agregar(entrada, _resultado_guardado(entrada), indice, categorias,
                                           importacion.archivo, importacion.usuario, ahora)
        EntradaImportada.objects.bulk_update(aptas, ['estado', 'motivo', 'canal', 'tipo'])

        quedan = importacion.entradas.filter(estado__in=[Estado.APTA, Estado.PENDIENTE]).exists()
        if aptas and not quedan:
            importacion.cargada = ahora
            importacion.save(update_fields=['cargada'])
            avance = progreso(importacion)
            registrar(importacion.usuario, Accion.CREAR,
                      f'Cargó las aptas de "{importacion.archivo}": {avance["agregadas"]} en total.', modulo='canales')
        elif aptas and not seleccion.aplicar(importacion.entradas.filter(estado=Estado.APTA)).exists():
            registrar(importacion.usuario, Accion.CREAR,
                      f'Cargó una parte de "{importacion.archivo}" ({que_es(seleccion)}).', modulo='canales')
    return {**progreso(importacion, seleccion), 'canales_nuevos': canales_nuevos}


def que_es(seleccion):
    """'Series › Novelas Mexicanas', para el registro de actividad."""
    partes = [secciones.nombre(seleccion.contenido) if seleccion.contenido else '',
              'sin categoría' if seleccion.categoria == SIN_CATEGORIA else seleccion.categoria,
              f'«{seleccion.texto}»' if seleccion.texto else '']
    return ' › '.join(p for p in partes if p) or 'toda la lista'


def descartar(importacion, seleccion, usuario=None):
    """
    "No me interesa esta parte": lo de `seleccion` que todavía no se cargó (por
    probar o que pasó) queda descartado y no se prueba ni se carga. Se puede
    volver atrás con "Cargar igual". Devuelve cuántas.
    """
    elegidas = seleccion.aplicar(importacion.entradas.filter(estado__in=[Estado.PENDIENTE, Estado.APTA]))
    sin_probar = elegidas.filter(estado=Estado.PENDIENTE).count()
    cantidad = elegidas.update(estado=Estado.DESCARTADA, causa='', motivo='Descartada a mano: no se quiso esta parte.')
    if cantidad:
        importacion.para_verificar = max(0, importacion.para_verificar - sin_probar)
        importacion.save(update_fields=['para_verificar'])
        registrar(usuario, Accion.EDITAR, f'Descartó {cantidad} de "{importacion.archivo}" ({que_es(seleccion)}).',
                  modulo='canales')
    return cantidad


# ── "¿Dónde va?": la categoría y la serie, antes de cargar ───────────

# Lo que todavía no se cargó (lo cargado se mueve desde Organizar contenido)
SE_PUEDE_UBICAR = [Estado.PENDIENTE, Estado.APTA, Estado.RECHAZADA, Estado.CAIDA, Estado.DESCARTADA]

# Hasta cuántas entradas se cuentan las series de la parte elegida (para no recorrer 200 000 en cada página)
MAXIMO_PARA_CONTAR_SERIES = 30000


def sin_ubicar(importacion, seleccion):
    return seleccion.aplicar(importacion.entradas.filter(estado__in=SE_PUEDE_UBICAR))


def como_va(importacion, seleccion, series_del_panel=None):
    """
    Adónde iría hoy lo de `seleccion` que falta cargar, para mostrarlo antes de
    cargar ("¿Dónde va?"):
      {'total': 120,
       'categorias': [{'nombre': 'SERIES CARTOON', 'cantidad': 80, 'va_a': 'Infantiles' | '' (= nueva)}, ...],
       'nuevas': 1,                      cuántas de esas categorías se crearían
       'series': {'total': 12, 'existen': 3} | None  (solo en Series)}
    series_del_panel: las claves (en minúscula) de las series que ya hay; sin
    ellas se buscan.
    """
    entradas = sin_ubicar(importacion, seleccion)
    indice = organizar.indice_de_categorias()
    categorias = []
    for nombre, cantidad in (entradas.order_by().values_list('categoria').annotate(cantidad=Count('pk'))
                             .order_by('-cantidad', 'categoria')):
        existente = organizar.categoria_existente(nombre, seleccion.contenido, indice) if nombre else None
        categorias.append({'nombre': nombre or 'Sin categoría', 'cantidad': cantidad,
                           'va_a': existente.nombre if existente else ''})
    total = sum(c['cantidad'] for c in categorias)
    series = None
    if seleccion.contenido == Contenido.SERIE and 0 < total <= MAXIMO_PARA_CONTAR_SERIES:
        if series_del_panel is None:
            series_del_panel = {clasificar.episodio(n)[0].lower() for n in
                                Canal.objects.filter(contenido=Contenido.SERIE).values_list('nombre', flat=True)}
        de_la_lista = {clasificar.episodio(n)[0].lower() for n in entradas.values_list('nombre', flat=True)}
        series = {'total': len(de_la_lista), 'existen': len(de_la_lista & series_del_panel)}
    return {'total': total, 'categorias': categorias,
            'nuevas': sum(1 for c in categorias if not c['va_a'] and c['nombre'] != 'Sin categoría'),
            'series': series}


def ubicar(importacion, seleccion, categoria='', serie='', temporada=None, recordar=False, usuario=None):
    """
    "¿Dónde va?": lo de `seleccion` que falta cargar va a la categoría
    `categoria` (una que ya existe o una nueva) y, en Series, a la serie `serie`
    (existente o nueva): cada capítulo con el número y la temporada que trae
    (o todos en `temporada`). Los que no traen número siguen después del
    último. Queda anotado en cada entrada y entra así con "Cargar".

    Una serie que ya existe va en SU categoría (organizar.categoria_para_la_serie).
    recordar: (una categoría entera de la lista, sin serie) la próxima lista que
    la traiga también va ahí.

    Devuelve (cuántas cambiaron, la Seleccion donde quedaron, si se recordó) o
    NoSePuede.
    """
    NoSePuede = organizar.NoSePuede
    contenido = seleccion.contenido
    if not contenido:
        raise NoSePuede('Primero elegí una parte de la lista (En vivo, Películas o Series).')
    categoria = organizar._limpio(categoria)
    if serie and contenido != Contenido.SERIE:
        raise NoSePuede('Solo los capítulos de Series van a una serie.')
    if not (categoria or serie):
        raise NoSePuede('Elegí la categoría o la serie donde va.')
    entradas = list(sin_ubicar(importacion, seleccion).order_by('posicion'))
    if not entradas:
        raise NoSePuede('Acá no queda nada sin cargar. Lo que ya se cargó se mueve desde Organizar contenido.')
    existente = organizar.categoria_existente(categoria, contenido) if categoria else None
    if existente:
        categoria = existente.nombre   # escrita como en el panel

    if serie:
        serie = organizar.nombre_de_serie_valido(serie)
        temporada = max(1, min(int(temporada), 99)) if temporada else None
        categoria = (organizar.categoria_para_la_serie(serie, categoria) or categoria
                     or Counter(e.categoria for e in entradas).most_common(1)[0][0])
        _a_la_serie(entradas, serie, temporada)

    revisar_series = False
    for entrada in entradas:
        if categoria:
            entrada.categoria = categoria[:80]
        if serie and entrada.estado == Estado.RECHAZADA and entrada.causa == Causa.SERIE_INCOMPLETA:
            # Con el nombre nuevo puede estar completa (la serie del panel tiene el capítulo 1): se revisa de nuevo
            entrada.estado, entrada.causa = Estado.APTA, ''
            entrada.motivo = _motivo_apta(_resultado_guardado(entrada))[:200]
            revisar_series = True
    EntradaImportada.objects.bulk_update(entradas, ['nombre', 'categoria', 'estado', 'causa', 'motivo'],
                                         batch_size=1000)

    quedo = Seleccion(contenido, categoria or seleccion.categoria, serie or seleccion.texto)
    if revisar_series and not falta_probar(importacion, quedo):
        _revisar_series(importacion)
    recordado = False
    if (recordar and categoria and not serie and not seleccion.texto
            and seleccion.categoria and seleccion.categoria != SIN_CATEGORIA):
        destino = organizar.categoria_por_nombre(categoria, contenido, usuario=usuario)
        recordado = organizar.recordar_nombre(destino, seleccion.categoria)
    destino = ' › '.join(p for p in (categoria, serie, f'temporada {temporada}' if temporada else '') if p)
    registrar(usuario, Accion.EDITAR, f'En "{importacion.archivo}", {que_es(seleccion)} va a {destino} '
                                      f'({len(entradas)}){" y lo recuerda" if recordado else ""}.', modulo='canales')
    return len(entradas), quedo, recordado


def _a_la_serie(entradas, serie, temporada=None):
    """Les cambia el nombre a capítulos de `serie` ("Boruto S01 E05 Título"), con su temporada y número."""
    al_final = []   # los que no traen número, o lo repiten (todos a una temporada: la 1 y la 2 traen un "E05")
    usados = {}
    for entrada in entradas:
        _, de_temporada, numero, _ = clasificar.episodio(entrada.nombre)
        lugar = temporada or de_temporada
        titulo = organizar.titulo_del_capitulo(entrada.nombre, serie)
        if numero is None or numero in usados.get(lugar, ()):
            al_final.append((entrada, lugar, titulo))
            continue
        usados.setdefault(lugar, set()).add(numero)
        entrada.nombre = organizar.nombre_de_capitulo(serie, lugar, numero, titulo)
    con_lo_del_panel = set()
    for entrada, lugar, titulo in al_final:
        if lugar not in con_lo_del_panel:   # siguen después del último, sea de la lista o del panel
            usados.setdefault(lugar, set()).add(organizar.ultimo_capitulo(serie, lugar))
            con_lo_del_panel.add(lugar)
        numero = max(usados[lugar]) + 1
        usados[lugar].add(numero)
        entrada.nombre = organizar.nombre_de_capitulo(serie, lugar, numero, titulo)


def _por_estado(entradas):
    """{'pendientes': 3, 'aptas': 1, ...} (los mismos nombres que `progreso`), 'total' y 'no_pasaron'."""
    return _por_estado_de(entradas.order_by().values_list('estado').annotate(cantidad=Count('pk')))


def por_contenido(importacion):
    """
    Qué trae la lista, por En vivo / Películas / Series (siempre en ese orden) y
    las secciones nuevas: [(clave, nombre, {cuántas en cada estado})].
    """
    filas = {}
    for contenido, estado, cantidad in (importacion.entradas.order_by().values_list('contenido', 'estado')
                                        .annotate(cantidad=Count('pk'))):
        filas.setdefault(contenido, []).append((estado, cantidad))
    return sorted(((contenido, secciones.nombre(contenido), _por_estado_de(cuentas))
                   for contenido, cuentas in filas.items()), key=lambda fila: (_ORDEN_DE_LAS_PARTES.get(fila[0], 9),
                                                                              -fila[2]['total']))


_ORDEN_DE_LAS_PARTES = {Contenido.VIVO: 0, Contenido.PELICULA: 1, Contenido.SERIE: 2}


def categorias_de(importacion, contenido):
    """Las categorías de una parte de la lista con cuántas hay en cada estado, de la más grande a la más chica."""
    filas = {}
    for categoria, estado, cantidad in (importacion.entradas.filter(contenido=contenido).order_by()
                                        .values_list('categoria', 'estado').annotate(cantidad=Count('pk'))):
        filas.setdefault(categoria, []).append((estado, cantidad))
    return sorted(({'nombre': categoria or 'Sin categoría', 'clave': categoria or SIN_CATEGORIA,
                    **_por_estado_de(cuentas)} for categoria, cuentas in filas.items()),
                  key=lambda fila: (-fila['total'], fila['nombre'].casefold()))


def _por_estado_de(cuentas):
    nombres = {Estado.PENDIENTE: 'pendientes', Estado.APTA: 'aptas', Estado.AGREGADA: 'agregadas',
               Estado.RECHAZADA: 'rechazadas', Estado.CAIDA: 'caidas', Estado.DESCARTADA: 'descartadas',
               Estado.REPETIDA: 'repetidas'}
    resultado = dict.fromkeys(nombres.values(), 0)
    for estado, cantidad in cuentas:
        resultado[nombres.get(estado, 'descartadas')] += cantidad
    # Lo que se prueba (o se probó): todo menos lo descartado y lo que ya estaba
    probables = sum(resultado[clave] for clave in ('pendientes', 'aptas', 'agregadas', 'rechazadas', 'caidas'))
    return {**resultado, 'total': sum(resultado.values()),
            'no_pasaron': resultado['rechazadas'] + resultado['caidas'],
            'porcentaje': 100 if not probables else round(100 * (probables - resultado['pendientes']) / probables)}


# Lo que se puede cambiar a mano antes de cargar (ver cargar_igual / no_cargar)
SE_PUEDEN_CARGAR_IGUAL = [Estado.RECHAZADA, Estado.CAIDA, Estado.DESCARTADA]


def cargar_igual(importacion, entradas, usuario=None):
    """
    Las elegidas que no pasaron (no pasaron la prueba, no respondieron o se
    descartaron) quedan aptas: entran con el próximo "Cargar". Las que no
    respondieron entran "sin verificar": la app las intenta y la verificación
    automática las vuelve a probar. Devuelve cuántas cambiaron.
    """
    elegidas = list(importacion.entradas.filter(pk__in=entradas, estado__in=SE_PUEDEN_CARGAR_IGUAL))
    for entrada in elegidas:
        if entrada.estado == Estado.CAIDA:
            entrada.estado_fuente = ''
        antes = entrada.motivo
        entrada.estado, entrada.causa = Estado.APTA, ''
        entrada.motivo = f'Elegida a mano para cargar{f" (antes: {antes})" if antes else ""}.'[:200]
    EntradaImportada.objects.bulk_update(elegidas, ['estado', 'causa', 'motivo', 'estado_fuente'])
    if elegidas:
        registrar(usuario, Accion.EDITAR, f'Eligió a mano cargar {len(elegidas)} de "{importacion.archivo}" '
                                          'que no habían pasado.', modulo='canales')
    return len(elegidas)


def no_cargar(importacion, entradas, usuario=None):
    """Las elegidas que pasaron (aptas, sin cargar todavía) quedan descartadas. Devuelve cuántas cambiaron."""
    elegidas = list(importacion.entradas.filter(pk__in=entradas, estado=Estado.APTA))
    for entrada in elegidas:
        antes = entrada.motivo
        entrada.estado = Estado.DESCARTADA
        entrada.motivo = f'Descartada a mano{f" (había pasado: {antes})" if antes else ""}.'[:200]
    EntradaImportada.objects.bulk_update(elegidas, ['estado', 'motivo'])
    if elegidas:
        registrar(usuario, Accion.EDITAR, f'Descartó a mano {len(elegidas)} de "{importacion.archivo}" '
                                          'que habían pasado.', modulo='canales')
    return len(elegidas)


def progreso(importacion, seleccion=TODA):
    """
    Cuántas hay en cada estado y el porcentaje de avance (sobre las que había
    que verificar). Con una `seleccion`, además 'en_la_seleccion' (cuántas de
    esa parte en cada estado) y 'terminada' es si ya se probó esa parte.
    """
    avance = _progreso(importacion)
    if seleccion.vacia:
        estados = ('pendientes', 'aptas', 'agregadas', 'rechazadas', 'caidas', 'descartadas', 'repetidas')
        parte = {clave: avance[clave] for clave in estados}
        parte.update(total=importacion.total - importacion.por_leer, no_pasaron=avance['rechazadas'] + avance['caidas'],
                     porcentaje=avance['porcentaje'])
    else:
        parte = _por_estado(seleccion.aplicar(importacion.entradas.all()))
    return {**avance, 'en_la_seleccion': parte, 'terminada': parte['pendientes'] == 0}


def _progreso(importacion):
    por_estado = dict(importacion.entradas.order_by().values_list('estado').annotate(cantidad=Count('pk')))
    pendientes = por_estado.get(Estado.PENDIENTE, 0)
    base = max(importacion.para_verificar, pendientes)
    porcentaje = 100 if not base else round(100 * (base - pendientes) / base)
    return {
        'total': importacion.total,
        'para_verificar': base,
        'verificadas': base - pendientes,
        'pendientes': pendientes,
        'aptas': por_estado.get(Estado.APTA, 0),
        'agregadas': por_estado.get(Estado.AGREGADA, 0),
        'rechazadas': por_estado.get(Estado.RECHAZADA, 0),
        'caidas': por_estado.get(Estado.CAIDA, 0),
        'descartadas': por_estado.get(Estado.DESCARTADA, 0),
        'repetidas': por_estado.get(Estado.REPETIDA, 0),
        'porcentaje': porcentaje,
        'terminada': pendientes == 0,
    }


def por_causa(importacion):
    """Las que no pasaron la prueba, por causa: [(causa, 'Sin sonido', 12), ...] de la que más hay a la que menos."""
    cantidades = (importacion.entradas.filter(estado=Estado.RECHAZADA).order_by().values_list('causa')
                  .annotate(cantidad=Count('pk')).order_by('-cantidad'))
    nombres = dict(Causa.choices)
    return [(causa, nombres.get(causa, 'Otra'), cantidad) for causa, cantidad in cantidades]


# Lo que puede ser algo del momento (y vale la pena volver a probar)
CAUSAS_PASAJERAS = [Causa.LENTA, Causa.SE_CORTA]


def reintentar_caidas(importacion, usuario=None):
    """
    Las que no respondieron, llegaron lentas o se cortaron vuelven a quedar
    pendientes (a veces es algo del momento). Los capítulos que no pasaron por
    "serie incompleta" vuelven a aptos: al terminar se revisan de nuevo.
    """
    cantidad = (importacion.entradas.filter(Q(estado=Estado.CAIDA)
                                            | Q(estado=Estado.RECHAZADA, causa__in=CAUSAS_PASAJERAS))
                .update(estado=Estado.PENDIENTE, motivo='', causa=''))
    if cantidad:
        importacion.entradas.filter(estado=Estado.RECHAZADA, causa=Causa.SERIE_INCOMPLETA).update(
            estado=Estado.APTA, motivo='Pasó la prueba (falta revisar la serie).', causa='')
        importacion.para_verificar, importacion.terminada, importacion.cargada = cantidad, None, None
        importacion.save(update_fields=['para_verificar', 'terminada', 'cargada'])
        registrar(usuario, Accion.EDITAR, f'Reintenta {cantidad} canal(es) de "{importacion.archivo}".',
                  modulo='canales')
    return cantidad


def importar_m3u(texto, origen='', usuario=None, verificar=None, **opciones):
    """
    Todo de una vez (consola y pruebas): crea la importación, la prueba
    entera y carga las aptas. Nunca pisa lo que ya existe:
      - canal nuevo            -> se crea (con su categoría, logo y número)
      - canal que ya existía   -> la dirección se agrega como fuente alternativa
      - dirección repetida     -> se ignora
      - no funciona            -> no se agrega (queda en el informe de la importación, con el motivo)
    """
    importacion = crear_importacion(texto, origen, usuario, **opciones)
    pendientes_antes = None
    while True:
        avance = procesar_lote(importacion, verificar, segundos=None)
        if avance['terminada'] or avance['pendientes'] == pendientes_antes:   # no avanzó: no insistir
            break
        pendientes_antes = avance['pendientes']
    nuevos = 0
    while avance['aptas'] and not avance['pendientes']:
        avance = cargar_lote(importacion)
        nuevos += avance['canales_nuevos']
    agregadas = importacion.entradas.filter(estado=Estado.AGREGADA).values('url')
    por_estado = dict(Fuente.objects.filter(url__in=agregadas).order_by().values_list('estado')
                      .annotate(cantidad=Count('pk')))
    return ResultadoImportacion(
        canales_nuevos=nuevos, fuentes_nuevas=avance['agregadas'], repetidas=avance['repetidas'],
        funcionan=por_estado.get(Fuente.Estado.FUNCIONA, 0), caidas=avance['caidas'],
        sin_verificar=por_estado.get(Fuente.Estado.SIN_VERIFICAR, 0),
        descartadas=avance['descartadas'] + avance['rechazadas'],
    )


# ── Volver a verificar las fuentes guardadas ─────────────────────────

def aplicar_resultado(fuente, resultado, ahora):
    """
    Le pone a la fuente lo que dio la verificación (estado, motivo, formato
    real y User-Agent que anduvo) y lo suma a su memoria (salud.py).
    """
    fuente.estado, fuente.error, fuente.verificada = resultado.estado, resultado.error[:200], ahora
    salud.anotar_del_servidor(fuente, resultado, ahora)
    if resultado.tipo:
        fuente.tipo = resultado.tipo
    if resultado.codec:
        fuente.codec = resultado.codec
    if resultado.user_agent and not fuente.user_agent:
        fuente.user_agent = resultado.user_agent
    if resultado.a_fondo:
        fuente.medida = ahora
        if resultado.estado == Fuente.Estado.FUNCIONA:
            # Se volvió a medir: la calidad y la velocidad de ahora
            fuente.calidad = resultado.calidad()
            fuente.alto, fuente.velocidad = resultado.alto, resultado.velocidad


CAMPOS_DE_VERIFICACION = ['estado', 'error', 'verificada', 'tipo', 'codec', 'user_agent', 'calidad', 'alto',
                          'velocidad', 'medida', *salud.CAMPOS]


def _fuentes_vigentes(seccion='', origen=''):
    """
    Las fuentes de lo que no se eliminó. Para revisar solo una parte (panel →
    Mantenimiento): `seccion` (vivo, pelicula, serie o una nueva) y `origen`
    (la lista o el link de donde vinieron, como lo guarda Fuente.origen).
    """
    fuentes = Fuente.objects.filter(canal__eliminado_en__isnull=True)
    if seccion:
        fuentes = fuentes.filter(canal__contenido=seccion)
    if origen:
        fuentes = fuentes.filter(origen=origen)
    return fuentes


# Cuántos nombres de "se cayeron" / "volvieron" manda cada tanda (la pantalla los junta)
NOMBRES_POR_TANDA = 100


def verificar_lote_de_fuentes(verificar, desde=0, tamanio=TAMANIO_LOTE, segundos=SEGUNDOS_POR_LOTE, usuario=None,
                              seccion='', origen=''):
    """
    Vuelve a probar las próximas `tamanio` fuentes (en orden de id, a partir
    de `desde`) y actualiza su estado. Las caídas que volvieron pasan a
    "funciona" (y la app las vuelve a usar); las que se cayeron dejan de
    usarse. No toca `activa`. Con `seccion` u `origen`, solo esas (ver
    _fuentes_vigentes). Devuelve el avance, `siguiente` (el `desde` para la
    próxima tanda) y los nombres de lo que se cayó y lo que volvió en esta tanda
    (`se_cayeron`, `volvieron`: [{'canal', 'pk', 'error'}]).
    """
    vigentes = _fuentes_vigentes(seccion, origen)
    fuentes = list(vigentes.filter(pk__gt=desde).select_related('canal').order_by('pk')[:tamanio])
    hasta = time.monotonic() + segundos if segundos else None
    estados = verificar({f.url: f.tipo for f in fuentes},
                        cabeceras={f.url: (f.user_agent, f.referer) for f in fuentes if f.user_agent or f.referer},
                        hasta=hasta)
    ahora = timezone.now()

    resultado = ResultadoVerificacion()
    verificadas = []
    se_cayeron, volvieron = [], []
    siguiente = desde
    corte = False
    for fuente in fuentes:
        nuevo = estados.get(fuente.url)
        if nuevo is None:
            corte = True   # no llegó: desde acá se sigue en la próxima tanda
            continue
        if not corte:
            siguiente = fuente.pk
        if fuente.estado == Fuente.Estado.CAIDA and nuevo.estado == Fuente.Estado.FUNCIONA:
            resultado.revividas += 1
            volvieron.append({'canal': fuente.canal.nombre, 'pk': fuente.canal_id, 'error': ''})
        elif fuente.estado != Fuente.Estado.CAIDA and nuevo.estado == Fuente.Estado.CAIDA:
            resultado.nuevas_caidas += 1
            se_cayeron.append({'canal': fuente.canal.nombre, 'pk': fuente.canal_id, 'error': nuevo.error[:120]})
        aplicar_resultado(fuente, nuevo, ahora)
        _contar(resultado, nuevo.estado)
        verificadas.append(fuente)
    Fuente.objects.bulk_update(verificadas, CAMPOS_DE_VERIFICACION)

    total = vigentes.count()
    terminado = not vigentes.filter(pk__gt=siguiente).exists()
    if terminado:
        registrar(usuario, Accion.EDITAR, f'Volvió a verificar {que_se_revisa(seccion, origen)}.', modulo='canales')
    hechas = vigentes.filter(pk__lte=siguiente).count()
    return {
        'siguiente': siguiente, 'total': total, 'verificadas': hechas, 'terminado': terminado,
        'porcentaje': 100 if not total else round(100 * hechas / total),
        'funcionan': resultado.funcionan, 'caidas': resultado.caidas, 'sin_verificar': resultado.sin_verificar,
        'revividas': resultado.revividas, 'nuevas_caidas': resultado.nuevas_caidas,
        'se_cayeron': se_cayeron[:NOMBRES_POR_TANDA], 'volvieron': volvieron[:NOMBRES_POR_TANDA],
    }


def que_se_revisa(seccion='', origen='', cosas='fuentes'):
    """
    'las fuentes de Series que vinieron de «lista.m3u»', 'todos los canales'
    (para la actividad y la pantalla). `cosas`: 'fuentes' o 'canales'.
    """
    articulo = 'los' if cosas == 'canales' else 'las'
    texto = f'{articulo} {cosas}' if seccion or origen else f'{"todos" if articulo == "los" else "todas"} {articulo} {cosas}'
    if seccion:
        texto += f' de {secciones.nombre(seccion)}'
    if origen:
        texto += f' que vinieron de «{origen}»'
    return texto


def avance_de_la_verificacion(desde, seccion='', origen=''):
    """Cómo va "verificar todas" sin verificar nada (mientras espera su turno, ver core/trabajos.py)."""
    vigentes = _fuentes_vigentes(seccion, origen)
    total = vigentes.count()
    hechas = vigentes.filter(pk__lte=desde).count()
    return {
        'siguiente': desde, 'total': total, 'verificadas': hechas, 'terminado': False,
        'porcentaje': 100 if not total else round(100 * hechas / total),
        'funcionan': 0, 'caidas': 0, 'sin_verificar': 0, 'revividas': 0, 'nuevas_caidas': 0,
        'se_cayeron': [], 'volvieron': [],
    }


def verificar_fuentes_guardadas(verificar, usuario=None, al_avanzar=None):
    """
    Todas de una vez (consola / cron): tanda tras tanda hasta terminar.
    `al_avanzar(avance)`: se llama después de cada tanda (para mostrar cómo va).
    """
    total = ResultadoVerificacion()
    desde = 0
    while True:
        avance = verificar_lote_de_fuentes(verificar, desde, segundos=None, usuario=usuario)
        if al_avanzar:
            al_avanzar(avance)
        total.sumar(ResultadoVerificacion(**{c: avance[c] for c in (
            'funcionan', 'caidas', 'sin_verificar', 'revividas', 'nuevas_caidas')}))
        if avance['terminado']:
            return total
        desde = avance['siguiente']


# ── Medir las fuentes (cuál es la mejor de cada canal) ───────────────

# Cuántas fuentes se miden a fondo cada vez (y en cuánto tiempo, como mucho).
# Se mide de a poco, empezando por las nunca medidas y siguiendo por las
# medidas hace más tiempo: en unos días quedan todas medidas y se van
# renovando solas.
MEDIR_POR_VEZ = 300
SEGUNDOS_PARA_MEDIR = 30 * 60
# Solo se mide de madrugada (hora de Argentina, antes de las 7): medir ocupa
# conexiones de las listas IPTV, y de día las usa la gente que está mirando.
HORA_HASTA_LA_QUE_SE_MIDE = 7
# Lo que no se puede medir bajando un pedazo de video (lo de YouTube y páginas)
TIPOS_QUE_SE_MIDEN = [Fuente.Tipo.HLS, Fuente.Tipo.DASH, Fuente.Tipo.DIRECTO]


def es_hora_de_medir(ahora=None):
    return timezone.localtime(ahora).hour < HORA_HASTA_LA_QUE_SE_MIDE


def medir_fuentes(verificar_a_fondo, cantidad=MEDIR_POR_VEZ, segundos=SEGUNDOS_PARA_MEDIR):
    """
    Mide a fondo (como la prueba a fondo de la importación: resolución y
    velocidad con que llega) las fuentes de los canales que tienen más de
    una: ahí es donde importa cuál va primera (ver
    consultas.ordenadas_por_estabilidad). Las caídas no: no se usan. Lo
    corre solo la verificación programada (verificar_fuentes), de madrugada.
    Devuelve cuántas midió.
    """
    vigentes = (_fuentes_vigentes().filter(activa=True, tipo__in=TIPOS_QUE_SE_MIDEN)
                .exclude(estado=Fuente.Estado.CAIDA))
    con_varias = vigentes.values('canal').annotate(cantidad=Count('pk')).filter(cantidad__gte=2).values('canal')
    fuentes = list(vigentes.filter(canal__in=con_varias)
                   .order_by(F('medida').asc(nulls_first=True), 'pk')[:cantidad])
    if not fuentes:
        return 0
    estados = verificar_a_fondo({f.url: f.tipo for f in fuentes},
                                cabeceras={f.url: (f.user_agent, f.referer) for f in fuentes
                                           if f.user_agent or f.referer},
                                hasta=time.monotonic() + segundos)
    ahora = timezone.now()
    medidas = []
    for fuente in fuentes:
        nuevo = estados.get(fuente.url)
        if nuevo is not None:
            aplicar_resultado(fuente, nuevo, ahora)
            medidas.append(fuente)
    Fuente.objects.bulk_update(medidas, CAMPOS_DE_VERIFICACION)
    return len(medidas)


def _contar(resultado, estado):
    if estado == Fuente.Estado.FUNCIONA:
        resultado.funcionan += 1
    elif estado == Fuente.Estado.CAIDA:
        resultado.caidas += 1
    else:
        resultado.sin_verificar += 1


# ── Quitar canales / volver a mostrarlos ─────────────────────────────

def quitar_canales(canales, motivo='', usuario=None):
    """Los saca de la app (no los borra). Si vuelven en otra lista, siguen quitados."""
    motivo = (motivo or 'Quitado a mano.').strip()[:200]
    cantidad = canales.filter(activo=True).update(activo=False, motivo_quitado=motivo, modificado=timezone.now(),
                                                   modificado_por=usuario if getattr(usuario, 'pk', None) else None)
    if cantidad:
        registrar(usuario, Accion.EDITAR, f'Quitó {cantidad} canal(es) de la app: {motivo}', modulo='canales')
    return cantidad


def mostrar_canales(canales, usuario=None):
    """
    "Volver a mostrar": lo elegido vuelve a la app, no se viera por lo que no se viera:
      - quitado (a mano o por la limpieza) → vuelve;
      - fuentes escondidas por fallar en los aparatos → se dejan de esconder y se
        olvidan esas fallas (otra oportunidad entera);
      - fuentes caídas → quedan "sin verificar": la app las intenta, y la
        verificación automática las vuelve a probar;
      - fuentes que retiró la limpieza (salud.retirar_senales) → se prenden.
    Además se olvida desde cuándo fallan sus fuentes (salud.py): si siguen
    fallando, la limpieza cuenta una semana entera desde ahora.
    Las fuentes apagadas a mano no se tocan (se prenden desde Editar).
    Devuelve cuántos canales cambiaron.
    """
    pks = set(canales.values_list('pk', flat=True))
    ahora = timezone.now()
    quien = usuario if getattr(usuario, 'pk', None) else None
    quitados = set(Canal.objects.filter(pk__in=pks, activo=False).values_list('pk', flat=True))
    Canal.objects.filter(pk__in=quitados).update(activo=True, motivo_quitado='', modificado=ahora,
                                                 modificado_por=quien)
    retiradas = Fuente.objects.filter(canal__in=pks, activa=False, retirada__isnull=False)
    con_fuentes = set(retiradas.values_list('canal', flat=True))
    retiradas.update(activa=True, retirada=None)
    escondidas = Fuente.objects.filter(canal__in=pks, activa=True).filter(
        Q(oculta_hasta__gt=ahora) | Q(estado=Fuente.Estado.CAIDA))
    con_fuentes |= set(escondidas.values_list('canal', flat=True))
    escondidas.filter(oculta_hasta__isnull=False).update(
        oculta_desde=None, oculta_hasta=None, veces_oculta=0, avisos_de_aparatos=0, primer_aviso=None,
        falla_en_aparatos='')
    escondidas.filter(estado=Fuente.Estado.CAIDA).update(estado=Fuente.Estado.SIN_VERIFICAR)
    salud.olvidar_fallas(Fuente.objects.filter(canal__in=pks))   # que la limpieza no lo vuelva a quitar enseguida
    cantidad = len(quitados | con_fuentes)
    if cantidad:
        registrar(usuario, Accion.EDITAR, f'Volvió a mostrar {cantidad} canal(es) en la app.', modulo='canales')
    return cantidad


# ── Una señal sola (Organizar → Detalles) ────────────────────────────

def quitar_fuente(fuente, usuario=None):
    """
    "Quitar esta señal": la app deja de recibirla, aunque el canal siga
    andando con las otras. Es como apagarla a mano: no vuelve sola (para eso,
    mostrar_fuente). No se borra.
    """
    fuente.activa, fuente.retirada = False, None
    fuente.save(update_fields=['activa', 'retirada'])
    registrar(usuario, Accion.EDITAR, f'Quitó una señal de "{fuente.canal}" ({fuente.origen or "sin origen"}).',
              objeto=fuente.canal, modulo='canales')


def mostrar_fuente(fuente, usuario=None):
    """
    "Volver a mostrar esta señal": otra oportunidad entera, aunque el canal ya
    se vea con otras. Se prende (si estaba apagada a mano o la retiró la
    limpieza), deja de estar escondida por los aparatos, si estaba caída
    queda "sin verificar" (la app la intenta y la verificación la vuelve a
    probar) y se olvida desde cuándo fallaba (la limpieza cuenta una semana
    desde ahora).
    """
    fuente.activa, fuente.retirada = True, None
    fuente.oculta_desde = fuente.oculta_hasta = fuente.primer_aviso = None
    fuente.veces_oculta = fuente.avisos_de_aparatos = 0
    fuente.falla_en_aparatos = ''
    fuente.falla_desde, fuente.fallas_seguidas = None, 0
    if fuente.estado == Fuente.Estado.CAIDA:
        fuente.estado = Fuente.Estado.SIN_VERIFICAR
    fuente.save()
    registrar(usuario, Accion.EDITAR, f'Volvió a mostrar una señal de "{fuente.canal}" '
                                      f'({fuente.origen or "sin origen"}).', objeto=fuente.canal, modulo='canales')


def probar_fuente(fuente, verificar_url):
    """
    "Probar ahora": el servidor la prueba en el momento. Si la había retirado
    la limpieza y ahora anda, vuelve a la app. Devuelve el resultado.
    """
    resultado = verificar_url(fuente.url, fuente.tipo, fuente.user_agent, fuente.referer)
    aplicar_resultado(fuente, resultado, timezone.now())
    fuente.save(update_fields=CAMPOS_DE_VERIFICACION)
    if fuente.retirada and resultado.estado == Fuente.Estado.FUNCIONA:
        salud.devolver_senales(fuentes=[fuente.pk])
    return resultado


# ── Editar un canal desde el panel ───────────────────────────────────

def guardar_canal(form, fuentes, usuario=None, verificar_url=None):
    """
    Guarda el formulario del canal (CanalForm) y el de sus fuentes
    (FuentesFormSet: prioridad, apagar o borrar). Si se escribió una fuente
    nueva, se crea y se prueba en el momento. Devuelve (canal, fuente_nueva o None).
    """
    with transaction.atomic():
        canal = form.save(commit=False)
        canal.marcar_autor(usuario)
        canal.save()
        fuentes.save()
    nueva = None
    if form.cleaned_data.get('nueva_fuente'):
        nueva = agregar_fuente(canal, form.cleaned_data['nueva_fuente'], verificar_url, usuario)
    registrar(usuario, Accion.EDITAR, f'Editó el canal "{canal.nombre}".', modulo='canales')
    return canal, nueva


def agregar_fuente(canal, url, verificar_url=None, usuario=None):
    """Suma una dirección al canal (al final de la lista) y, si se puede, la prueba."""
    tipo = clasificar.formato(url) or Fuente.Tipo.HLS
    prioridad = (canal.fuentes.aggregate(maximo=Max('prioridad'))['maximo'] or 0) + 1
    fuente = Fuente(canal=canal, url=url[:1000], tipo=tipo, prioridad=prioridad, origen='Agregada a mano')
    if verificar_url:
        aplicar_resultado(fuente, verificar_url(url, tipo), timezone.now())
    fuente.save()
    return fuente


def borrar_fuente(fuente, usuario=None):
    """
    Borra UNA fuente de un canal (la que no anda), sin tocar las otras. El
    canal queda; si era su única fuente, deja de verse en la app ("No tiene
    fuentes") hasta que se le agregue otra. La dirección queda anotada en la
    actividad, por si hay que volver a ponerla. Devuelve cuántas le quedan.
    """
    canal = fuente.canal
    url, origen = fuente.url, fuente.origen or 'no se sabe de dónde'
    fuente.delete()
    quedan = canal.fuentes.count()
    canal.marcar_autor(usuario)
    canal.save(update_fields=['modificado', 'modificado_por'])
    registrar(usuario, Accion.ELIMINAR, f'Borró una fuente de "{canal.nombre}" (le quedan {quedan}; de {origen}): '
                                        f'{url[:150]}', objeto=canal, cambios={'url': url, 'origen': origen},
              modulo='canales')
    return quedan


def crear_canal_a_mano(form, url, resultado, user_agent='', referer='', usuario=None):
    """
    Crea un canal con una dirección ya probada en "Probar un link": los
    datos vienen del formulario (CanalNuevoForm) y el estado y formato, de la prueba.
    """
    with transaction.atomic():
        canal = form.save(commit=False)
        canal.marcar_autor(usuario)
        canal.save()
        fuente = Fuente(canal=canal, url=url[:1000], prioridad=1, origen='Agregada a mano',
                        user_agent=user_agent[:300], referer=referer[:500],
                        tipo=clasificar.formato(url) or Fuente.Tipo.HLS)
        aplicar_resultado(fuente, resultado, timezone.now())
        fuente.save()
    registrar(usuario, Accion.CREAR, f'Agregó a mano el canal "{canal.nombre}".', modulo='canales')
    return canal


# ── Limpiar los nombres de los canales que ya estaban ────────────────

def limpiar_nombres(usuario=None, seccion='', origen='', cambios=None):
    """
    Pasa los nombres viejos al formato limpio ("ES: (FHD) DAZN 1" -> "DAZN 1"),
    como se hace al importar. Si al limpiarlo queda igual a otro canal (mismo
    contenido y país compatible), se juntan: las fuentes pasan al que ya
    estaba (quedan como alternativas) y el repetido se da de baja.
    Con `seccion` u `origen` (la lista o el link de donde vinieron), solo esos.
    En `cambios` (una lista) anota qué pasó con cada uno, para mostrarlo:
    ('renombrado' | 'juntado', nombre de antes, nombre de ahora).
    Devuelve (renombrados, juntados).
    """
    canales = Canal.objects.order_by('pk')
    if seccion:
        canales = canales.filter(contenido=seccion)
    if origen:
        canales = canales.filter(pk__in=Fuente.objects.filter(origen=origen).values('canal'))
    renombrados = juntados = 0
    cambios = cambios if cambios is not None else []
    with transaction.atomic():
        indice = _IndiceDeCanales()
        indice.por_nombre = {}
        for canal in canales:
            limpio = clasificar.limpiar_nombre(canal.nombre)[:120]
            igual = indice.buscar(limpio, canal.pais, canal.contenido)
            if igual is not None and igual.pk != canal.pk:
                cambios.append(('juntado', canal.nombre, igual.nombre))
                _juntar(canal, igual, usuario)
                juntados += 1
                continue
            if limpio != canal.nombre:
                cambios.append(('renombrado', canal.nombre, limpio))
                canal.nombre = limpio
                canal.marcar_autor(usuario)
                canal.save()
                renombrados += 1
            indice.agregar(canal)
    if renombrados or juntados:
        registrar(usuario, Accion.EDITAR,
                  f'Limpió los nombres ({que_se_revisa(seccion, origen, "canales")}): '
                  f'{renombrados} renombrado(s), {juntados} juntado(s).', modulo='canales')
    return renombrados, juntados


def _juntar(repetido, destino, usuario):
    """Las fuentes de `repetido` pasan a `destino` (al final) y `repetido` se da de baja."""
    ya_tiene = set(destino.fuentes.values_list('url', flat=True))
    prioridad = destino.fuentes.aggregate(maximo=Max('prioridad'))['maximo'] or 0
    for fuente in repetido.fuentes.order_by('prioridad', 'pk'):
        if fuente.url in ya_tiene:
            fuente.delete()
            continue
        prioridad += 1
        fuente.canal, fuente.prioridad = destino, prioridad
        fuente.save(update_fields=['canal', 'prioridad'])
    if not destino.logo and repetido.logo:
        destino.logo = repetido.logo
        destino.save(update_fields=['logo', 'modificado'])
    repetido.eliminar(usuario)


# ── Avisos de la app ─────────────────────────────────────────────────

# Una misma fuente se re-prueba como máximo una vez en este tiempo, aunque
# muchos aparatos avisen que falla a la vez (no se satura al servidor).
ESPERA_ENTRE_REVERIFICACIONES = 5 * 60   # segundos


def reverificar_por_aviso(fuente, verificar_url):
    """
    La app avisó que no pudo reproducir esta fuente. El servidor la vuelve a
    probar POR SU CUENTA (el aviso solo no alcanza: el problema puede ser la
    conexión de ese aparato): si al servidor también le falla, queda caída y
    la app deja de recibirla. Si ya la probó hace poco, no la vuelve a probar.
    Devuelve el estado con el que quedó.
    """
    clave = f'reverificar_fuente:{fuente.pk}'
    if not cache.add(clave, True, timeout=ESPERA_ENTRE_REVERIFICACIONES):
        return fuente.estado
    resultado = verificar_url(fuente.url, fuente.tipo, fuente.user_agent, fuente.referer)
    estado_anterior = fuente.estado
    aplicar_resultado(fuente, resultado, timezone.now())
    fuente.save(update_fields=CAMPOS_DE_VERIFICACION)
    if estado_anterior != Fuente.Estado.CAIDA and fuente.estado == Fuente.Estado.CAIDA:
        registrar(None, Accion.SISTEMA, f'La fuente de {fuente.canal} se cayó (avisó la app): {fuente.error}',
                  modulo='canales')
    return fuente.estado


# Lo que la app manda al avisar una falla ("motivo"), en palabras del panel.
MOTIVOS_DE_LOS_APARATOS = {
    'formato': 'el aparato no puede leer el formato del video',
    'rechazo': 'el servidor de la señal rechaza al aparato',
    'tiempo': 'tarda demasiado en arrancar',
    'conexion': 'no se puede conectar con la señal',
    'error': 'da error al reproducir',
}
# Cuántos avisos (de aparatos distintos, o del mismo pero separados por
# ESPERA_ENTRE_AVISOS) en un día hacen falta para ocultarla.
AVISOS_PARA_OCULTAR = 2
ESPERA_ENTRE_AVISOS = 30 * 60   # segundos


def _cuanto_se_oculta(veces, motivo):
    """
    Cuánto se oculta la `veces`-ésima vez seguida (OCULTA_POR: 3 horas, 1 día,
    una semana). Si los aparatos no pueden leer el formato no es algo pasajero:
    va directo a lo más largo.
    """
    if motivo == 'formato':
        return OCULTA_POR[-1]
    return OCULTA_POR[min(veces, len(OCULTA_POR)) - 1]


def _texto_de_tiempo(tiempo):
    horas = round(tiempo.total_seconds() / 3600)
    if horas < 24:
        return f'{horas} hora{"s" if horas != 1 else ""}'
    dias = round(horas / 24)
    return f'{dias} día{"s" if dias != 1 else ""}'


def registrar_falla_en_aparato(fuente, quien, motivo, detalle=''):
    """
    Cuenta un aviso de falla de un aparato (`quien`: algo que lo identifique,
    ej. el id de su sesión). Con AVISOS_PARA_OCULTAR en un día, la fuente se
    oculta un rato aunque al servidor le ande: se ve que en los aparatos no se
    reproduce. La primera vez, poco (suele ser un corte pasajero del canal);
    si al volver sigue fallando, cada vez más (OCULTA_POR). Cuando un aparato
    la ve bien, se olvida (registrar_estabilidad). El mismo aparato cuenta una
    vez cada ESPERA_ENTRE_AVISOS (reintentar diez veces seguidas no la oculta).
    Devuelve True si quedó oculta.
    """
    if fuente.oculta_por_aparatos:
        return True
    if not cache.add(f'falla_aparato:{fuente.pk}:{quien}', True, timeout=ESPERA_ENTRE_AVISOS):
        return False
    ahora = timezone.now()
    if fuente.primer_aviso is None or ahora - fuente.primer_aviso > timedelta(days=1):
        fuente.avisos_de_aparatos, fuente.primer_aviso = 0, ahora
    fuente.avisos_de_aparatos += 1
    salud.anotar_del_aparato(fuente, False, motivo, ahora)
    texto = MOTIVOS_DE_LOS_APARATOS.get(motivo, MOTIVOS_DE_LOS_APARATOS['error'])
    fuente.falla_en_aparatos = (f'{texto}: {detalle}' if detalle else texto)[:200]
    if fuente.avisos_de_aparatos >= AVISOS_PARA_OCULTAR:
        fuente.veces_oculta += 1
        tiempo = _cuanto_se_oculta(fuente.veces_oculta, motivo)
        fuente.oculta_desde, fuente.oculta_hasta = ahora, ahora + tiempo
        # Los próximos avisos cuentan desde cero (cuando vuelva, si sigue fallando)
        fuente.avisos_de_aparatos, fuente.primer_aviso = 0, None
        registrar(None, Accion.SISTEMA,
                  f'Se ocultó por {_texto_de_tiempo(tiempo)} una fuente de {fuente.canal}: no se reproduce en los '
                  f'aparatos ({texto}). Después vuelve sola a la app.', modulo='canales')
    fuente.save(update_fields=['avisos_de_aparatos', 'primer_aviso', 'falla_en_aparatos', 'oculta_desde',
                               'oculta_hasta', 'veces_oculta', *salud.CAMPOS])
    return fuente.oculta_por_aparatos


# Lo que un aparato puede contar de una sola vez (más es un error o un abuso).
MAXIMO_VISTO_POR_AVISO = 6 * 3600     # segundos
# Cuando lo visto pasa esto, lo viejo pesa la mitad: cuenta más lo reciente
# (una fuente que antes se cortaba y ahora anda bien sube sola, y al revés).
MEMORIA_DE_ESTABILIDAD = 10 * 3600    # segundos
# Con esto visto en un aparato, la fuente anda: se olvidan sus fallas (si
# estaba oculta, vuelve ya; la próxima vez que falle se oculta poco).
VISTO_PARA_PERDONAR = 60   # segundos


def registrar_estabilidad(fuente, segundos, cortes, proporcion=None):
    """
    Un aparato dejó de ver esta fuente: la vio `segundos` y se cortó `cortes`
    veces (se frenó a cargar, o se cayó y se reconectó), y la imagen tenía
    esta `proporcion` (ancho / alto; opcional). Se suma a lo que contaron los
    demás; con eso la API pone primero las que no se cortan y llenan la
    pantalla (consultas.ordenadas_por_estabilidad). No se guarda quién lo mandó.

    Si se vio VISTO_PARA_PERDONAR o más, anda: se olvida que había fallado
    (registrar_falla_en_aparato) y, si estaba oculta, vuelve a la app.
    """
    segundos = max(0, min(int(segundos), MAXIMO_VISTO_POR_AVISO))
    cortes = max(0, min(int(cortes), segundos // 5 + 1))   # más de uno cada 5 s no es real
    # Una imagen más angosta que 1:2 o más ancha que 3:1 no es real
    proporcion = round(float(proporcion), 2) if proporcion and .5 <= float(proporcion) <= 3 else None
    if not segundos and not proporcion:
        return
    with transaction.atomic():
        fuente = Fuente.objects.select_for_update().get(pk=fuente.pk)
        fuente.segundos_en_aparatos += segundos
        fuente.cortes_en_aparatos += cortes
        while fuente.segundos_en_aparatos > MEMORIA_DE_ESTABILIDAD:
            fuente.segundos_en_aparatos //= 2
            fuente.cortes_en_aparatos //= 2
        if proporcion:
            fuente.proporcion = proporcion
        campos = ['segundos_en_aparatos', 'cortes_en_aparatos', 'proporcion']
        if segundos >= VISTO_PARA_PERDONAR and salud.anotar_del_aparato(fuente, True):
            campos += salud.CAMPOS
        if segundos >= VISTO_PARA_PERDONAR and (fuente.veces_oculta or fuente.avisos_de_aparatos
                                                 or fuente.oculta_hasta):
            volvio = fuente.oculta_por_aparatos
            fuente.veces_oculta = fuente.avisos_de_aparatos = 0
            fuente.primer_aviso = fuente.oculta_desde = fuente.oculta_hasta = None
            fuente.falla_en_aparatos = ''
            campos += ['veces_oculta', 'avisos_de_aparatos', 'primer_aviso', 'oculta_desde', 'oculta_hasta',
                       'falla_en_aparatos']
            if volvio:
                registrar(None, Accion.SISTEMA, f'Volvió a la app una fuente de {fuente.canal}: un aparato la vio '
                                                f'bien.', modulo='canales')
        fuente.save(update_fields=campos)
