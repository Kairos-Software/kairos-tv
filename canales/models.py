"""
Los canales de TV en vivo.

    Categoria  1 ──< Canal  1 ──< Fuente

    Importacion  1 ──< EntradaImportada  (una lista M3U subida y qué pasó con cada línea)

    Canal  1 ──< Visto            (cuánto se miró cada día, todos los aparatos juntos)
    FavoritoAgregado              (cuántas veces se agregó algo a favoritos cada día)

Un canal (ej: "Canal 26") puede tener VARIAS fuentes: distintas direcciones
de la misma señal. La app usa la primera que funcione y, si se corta, pasa
sola a la siguiente (failover). Así, si una fuente se cae, el canal sigue.
"""

import re
from datetime import timedelta

from django.conf import settings
from django.core.validators import URLValidator
from django.db import models
from django.utils import timezone

from herramientas.modelos import ModeloBase


class Idioma(models.TextChoices):
    ESPANOL = 'es', 'Español'
    OTRO = 'otro', 'Otro idioma'
    DESCONOCIDO = '', 'No se sabe'


class Contenido(models.TextChoices):
    """
    Las tres secciones fijas de la app. Además están las que se crean desde el
    panel (Seccion: Música, Radio...): `contenido` guarda la clave de una u otra.
    """
    VIVO = 'vivo', 'En vivo'
    PELICULA = 'pelicula', 'Película'
    SERIE = 'serie', 'Serie'


def _nombre_del_contenido(contenido):
    if contenido in Contenido.values:
        return Contenido(contenido).label
    from .secciones import nombre
    return nombre(contenido) or contenido


class Seccion(ModeloBase):
    """
    Una sección nueva de la app, creada desde el panel (Música, Radio,
    Deportes...). Aparece en el menú de la app (1.2.11 o más nueva) con sus
    propias categorías, igual que En vivo o Películas. Lo que tiene guarda su
    `clave` en `contenido`. Es de una de dos formas:
      - en vivo: radios o canales que transmiten ahora (como En vivo);
      - a demanda: videos que se eligen (música, documentales...; como Películas).
    """

    class Forma(models.TextChoices):
        VIVO = 'vivo', 'En vivo (radios o canales que transmiten ahora)'
        A_DEMANDA = 'pelicula', 'A demanda (videos que se eligen: música, documentales...)'

    class Icono(models.TextChoices):
        MUSICA = 'musica', 'Música'
        RADIO = 'radio', 'Radio'
        DEPORTES = 'deportes', 'Deportes'
        DOCUMENTALES = 'documentales', 'Documentales'
        INFANTIL = 'infantil', 'Infantil'
        NOTICIAS = 'noticias', 'Noticias'
        OTRO = 'otro', 'Otro (una estrella)'

    clave = models.CharField(max_length=10, editable=False, help_text='Se arma del nombre: "Música" -> "musica".')
    nombre = models.CharField(max_length=30)
    forma = models.CharField(max_length=10, choices=Forma.choices, default=Forma.A_DEMANDA)
    icono = models.CharField('ícono', max_length=15, choices=Icono.choices, default=Icono.OTRO)
    orden = models.PositiveIntegerField(default=0, help_text='Menor = más arriba en el menú de la app.')

    class Meta:
        verbose_name = 'sección'
        verbose_name_plural = 'secciones'
        ordering = ['orden', 'nombre']
        constraints = [
            models.UniqueConstraint(fields=['clave'], condition=models.Q(eliminado_en__isnull=True),
                                    name='seccion_clave_unica'),
        ]

    def __str__(self):
        return self.nombre


class Categoria(ModeloBase):
    """
    Una categoría de UNA sección de la app (En vivo, Películas o Series): la
    "Infantil" de los canales no es la "Infantil" de las películas. Así, al
    ordenar las películas solo aparecen categorías de películas.
    """
    nombre = models.CharField(max_length=80)
    # Una de las fijas (Contenido) o la clave de una Seccion nueva
    contenido = models.CharField('sección', max_length=10, default=Contenido.VIVO, db_index=True)
    orden = models.PositiveIntegerField(default=0, help_text='Menor = aparece primero.')
    # Los nombres que tenía antes o de las categorías que se le juntaron (uno
    # por línea). Al importar, una lista que diga "Argentina" va a la categoría
    # que tiene "Argentina" acá (ver organizar.categoria_por_nombre).
    otros_nombres = models.TextField(blank=True)

    class Meta:
        verbose_name = 'categoría'
        verbose_name_plural = 'categorías'
        ordering = ['orden', 'nombre']
        constraints = [
            models.UniqueConstraint(fields=['contenido', 'nombre'], condition=models.Q(eliminado_en__isnull=True),
                                    name='categoria_nombre_unico_por_seccion'),
        ]

    def __str__(self):
        return self.nombre


class Canal(ModeloBase):
    """
    Un canal en vivo, o una película o capítulo de serie (`contenido`). Por
    ahora la app muestra los en vivo; películas y series se cargan igual,
    para cuando la app tenga esas secciones.
    """
    nombre = models.CharField(max_length=120)
    numero = models.CharField('número', max_length=10, blank=True, help_text='Número de canal (ej: 26).')
    logo = models.URLField(max_length=500, blank=True, help_text='Dirección de la imagen del logo.')
    categoria = models.ForeignKey(
        Categoria, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='canales', verbose_name='categoría',
    )
    # El identificador de las listas M3U (tvg-id): sirve para reconocer el
    # mismo canal en distintas listas y, más adelante, para la guía (EPG).
    tvg_id = models.CharField('ID de guía (tvg-id)', max_length=120, blank=True, db_index=True)
    pais = models.CharField('país', max_length=2, blank=True, help_text='Código de 2 letras (AR, UY...).')
    # Una de las fijas (Contenido) o la clave de una Seccion nueva
    contenido = models.CharField(max_length=10, default=Contenido.VIVO, db_index=True)
    idioma = models.CharField(max_length=5, choices=Idioma.choices, blank=True, db_index=True,
                              help_text='Estimado al importar (país, categoría, prefijo del nombre...).')
    activo = models.BooleanField(default=True, help_text='Un canal inactivo ("quitado") no aparece en la app.')
    motivo_quitado = models.CharField('por qué se quitó', max_length=200, blank=True)
    orden = models.PositiveIntegerField(default=0, help_text='Menor = aparece primero dentro de su categoría.')
    # Lo que se elige en el panel para que el modo reposo de la TV lo muestre
    # MÁS SEGUIDO (no siempre: se mezcla con lo que sale al azar). En una
    # serie se marcan todos sus capítulos (ver organizar.editar_serie).
    destacado = models.BooleanField('destacado en la TV', default=False,
                                    help_text='Sale más seguido en el modo reposo de la TV.')
    # "Dejar así" en Para revisar (bandeja.py): el estado de salud en que se
    # dejó (salud.Salud). No vuelve a aparecer en la bandeja mientras siga así.
    revisado = models.CharField('dejado así en', max_length=10, blank=True)

    class Meta:
        verbose_name = 'canal'
        verbose_name_plural = 'canales'
        ordering = ['orden', 'nombre']

    def __str__(self):
        return f'{self.numero} · {self.nombre}' if self.numero else self.nombre

    def get_contenido_display(self):
        return _nombre_del_contenido(self.contenido)


class LogoParejo(models.Model):
    """
    La copia "pareja" del logo de un canal en vivo (o una radio): sin el borde
    vacío que traen muchos archivos, con un margen chico e igual para todos y
    achicada (ver imagenes.emparejar). Así todos quedan centrados y del mismo
    tamaño en su tarjeta. Una por DIRECCIÓN (muchos canales comparten logo).
    `archivo` vacío = se usa el original (no hacía falta, o no se pudo: `error`).
    `roto`: la dirección ya no tiene el logo (imgur lo borró y manda su cartel
    "The image you are requesting does not exist", o da 404): no se manda
    ninguno y la app muestra las iniciales.
    """
    clave = models.CharField(max_length=40, unique=True)   # sha1 de la dirección
    url = models.TextField()
    archivo = models.CharField(max_length=120, blank=True)
    error = models.CharField(max_length=200, blank=True)
    roto = models.BooleanField(default=False)
    probado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'logo parejo'
        verbose_name_plural = 'logos parejos'

    def __str__(self):
        return self.url


class PortadaDeSerie(models.Model):
    """
    La portada de una serie, aparte de las imágenes de sus capítulos (cada
    capítulo conserva la suya, la que trajo YouTube). Las series no son una
    tabla: salen del nombre de los capítulos ("Pocoyó S01 E02"), así que la
    portada va por el nombre de la serie (`clave`: sin acentos ni mayúsculas).
    Sin portada, la serie usa la imagen de su primer capítulo. Ver imagenes.py.
    """
    clave = models.CharField(max_length=90, unique=True)
    nombre = models.CharField(max_length=90)
    imagen = models.URLField(max_length=500)
    modificada = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'portada de serie'
        verbose_name_plural = 'portadas de series'

    def __str__(self):
        return self.nombre


# Cuánto queda oculta una fuente que falla en los aparatos (ver
# servicios.registrar_falla_en_aparato): la primera vez poco, porque suele ser
# un corte pasajero del canal; si al volver sigue fallando, más; desde la
# tercera, una semana. Cuando un aparato la ve bien, se olvida todo y vuelve a
# empezar por la primera (servicios.registrar_estabilidad).
OCULTA_POR = [timedelta(hours=3), timedelta(days=1), timedelta(days=7)]


# Estabilidad en los aparatos (Fuente.cortes_por_hora). Con menos de
# MINIMO_VISTO_PARA_JUZGAR segundos vistos no se sabe todavía; desde
# CORTES_POR_HORA_TOLERABLES cortes por hora (uno cada 10 minutos) se
# considera que "se corta" y la app la prueba después de las demás.
MINIMO_VISTO_PARA_JUZGAR = 10 * 60
CORTES_POR_HORA_TOLERABLES = 6
# La prueba a fondo: desde esta velocidad (segundos de video por segundo) la
# señal llega SOBRADA; por debajo llega justa y es más fácil que se corte.
VELOCIDAD_SOBRADA = 1.5
# Por debajo de esta forma (ancho / alto) la imagen es "cuadrada" (4:3 = 1.33):
# en una TV o un celular acostado queda con franjas negras a los costados.
PROPORCION_PANTALLA_COMPLETA = 1.5


def medidas_de_calidad(calidad):
    """
    Lo que midió la prueba a fondo, en números, sacado del texto de la
    calidad: '1080p · H.264 · audio AAC (es) · llega x3.2' -> {'alto': 1080, 'velocidad': 3.2}.
    """
    alto = re.search(r'\b(\d{3,4})p\b', calidad or '')
    velocidad = re.search(r'llega x(\d+(?:\.\d+)?)', calidad or '')
    return {'alto': int(alto.group(1)) if alto else 0, 'velocidad': float(velocidad.group(1)) if velocidad else 0}


class Fuente(models.Model):

    # El formato de la señal. Lo averigua la verificación mirando lo que
    # responde el servidor (como VLC), no la extensión de la dirección.
    class Tipo(models.TextChoices):
        HLS = 'hls', 'HLS (.m3u8)'
        DASH = 'dash', 'DASH (.mpd)'
        DIRECTO = 'directo', 'Video directo (TS, MP4...)'
        RTSP = 'rtsp', 'RTSP'
        YOUTUBE = 'youtube', 'YouTube'
        PAGINA = 'pagina', 'Página de video (Twitch, Dailymotion...)'
        # Películas y capítulos de canales oficiales de YouTube: la app los muestra en el
        # reproductor de YouTube, sin sacarlos de ahí (ver canales/youtube.py)
        YT_VIDEO = 'yt_video', 'Video de YouTube (reproductor oficial)'

    # `activa` la decide una persona; `estado` lo pone la verificación
    # automática. La app usa una fuente solo si está activa Y no está caída.
    class Estado(models.TextChoices):
        SIN_VERIFICAR = 'sin_verificar', 'Sin verificar'
        FUNCIONA = 'funciona', 'Funciona'
        CAIDA = 'caida', 'Caída'

    canal = models.ForeignKey(Canal, on_delete=models.CASCADE, related_name='fuentes')
    url = models.CharField('dirección', max_length=1000,
                           validators=[URLValidator(schemes=['http', 'https', 'rtsp', 'rtsps'])])
    tipo = models.CharField(max_length=10, choices=Tipo.choices, default=Tipo.HLS)
    # El códec del video (h264, h265, mpeg2...): lo averigua la verificación.
    # La app lo compara con los que sabe mostrar su aparato (no todos leen todos).
    codec = models.CharField('códec', max_length=10, blank=True, help_text='Lo averigua la verificación.')
    # Lo que encontró la prueba a fondo al importarla: '1080p · H.264 · audio AAC (es) · llega x3.2'
    calidad = models.CharField(max_length=80, blank=True, help_text='Lo que encontró la prueba a fondo.')
    # Lo mismo, en números, para elegir la mejor (ver consultas.ordenadas_por_estabilidad):
    # las líneas de la imagen (1080, 720...) y cuántos segundos de video llegan por
    # segundo (3.2 = sobrado; cerca de 1 = justo, se puede cortar). 0 = no se sabe.
    alto = models.PositiveSmallIntegerField(default=0)
    velocidad = models.FloatField(default=0)
    # Cuándo se midió por última vez (la verificación programada mide de a
    # tandas, empezando por las nunca medidas: servicios.medir_fuentes).
    medida = models.DateTimeField('última medición', null=True, blank=True)
    prioridad = models.PositiveIntegerField(default=0, help_text='Menor = se prueba primero.')
    activa = models.BooleanField(default=True, help_text='Apagarla a mano: la app no la usa aunque funcione.')
    estado = models.CharField(max_length=15, choices=Estado.choices, default=Estado.SIN_VERIFICAR,
                              help_text='Lo pone la verificación automática. La app no usa las caídas.')
    verificada = models.DateTimeField('última verificación', null=True, blank=True)
    error = models.CharField('motivo de la falla', max_length=200, blank=True)
    # Cómo tiene que presentarse el reproductor para que el servidor del canal
    # entregue la señal. Vacío = el de siempre (verificacion.USER_AGENT_REPRODUCTOR).
    user_agent = models.CharField('User-Agent', max_length=300, blank=True,
                                  help_text='Solo si el canal lo exige (lo traen algunas listas M3U).')
    referer = models.CharField('Referer', max_length=500, blank=True,
                               help_text='Página desde la que "viene" el pedido, si el canal lo exige.')
    origen = models.CharField(max_length=150, blank=True, help_text='De qué lista se importó.')
    creado = models.DateTimeField(auto_now_add=True)

    # Lo que avisan los APARATOS (la app), aparte de la verificación del
    # servidor: hay señales que al servidor le responden pero en los aparatos
    # no se reproducen (formato de video que no leen, servidores que aceptan
    # una sola conexión...). Si varios aparatos avisan que falla, se oculta
    # un rato aunque el servidor la vea bien (ver servicios.registrar_falla_en_aparato).
    avisos_de_aparatos = models.PositiveSmallIntegerField(default=0)
    primer_aviso = models.DateTimeField(null=True, blank=True)
    falla_en_aparatos = models.CharField('motivo según los aparatos', max_length=200, blank=True)
    oculta_desde = models.DateTimeField('oculta por fallar en los aparatos desde', null=True, blank=True)
    # Hasta cuándo, y cuántas veces seguidas se ocultó (cada vez, más tiempo: OCULTA_POR)
    oculta_hasta = models.DateTimeField('oculta hasta', null=True, blank=True)
    veces_oculta = models.PositiveSmallIntegerField(default=0)

    # Qué tan estable es en los aparatos: cuánto se vio y cuántas veces se
    # cortó mientras se veía (se frenó a cargar o se cayó y se reconectó). Con
    # eso la API pone primero las que no se cortan (ver consultas.fuentes_usables
    # y servicios.registrar_estabilidad). Pesa más lo reciente.
    segundos_en_aparatos = models.PositiveIntegerField('visto en los aparatos (segundos)', default=0)
    cortes_en_aparatos = models.PositiveIntegerField('cortes en los aparatos', default=0)
    # La forma de la imagen según los aparatos (ancho / alto: 1.78 = 16:9; 1.33 = 4:3,
    # "cuadrada", con franjas negras a los costados). 0 = no se sabe.
    proporcion = models.FloatField('forma de la imagen', default=0)

    # La SALUD con memoria (ver salud.py): no se juzga por la última prueba
    # sola. `historial`: las últimas pruebas del servidor y de los aparatos,
    # una letra cada una (la más nueva al final); `anduvo`: la última vez que
    # anduvo; `falla_desde` y `fallas_seguidas`: desde cuándo falla SIN PARAR y
    # cuántas veces (cualquier vez que anda vuelve a cero); `por_que_falla`: el
    # motivo de la última falla (salud.MOTIVOS).
    historial = models.CharField('últimas pruebas', max_length=20, blank=True)
    anduvo = models.DateTimeField('anduvo por última vez', null=True, blank=True)
    falla_desde = models.DateTimeField('falla sin parar desde', null=True, blank=True)
    fallas_seguidas = models.PositiveSmallIntegerField(default=0)
    por_que_falla = models.CharField('por qué falla', max_length=10, blank=True)
    # La última vez que la probó el "modo revisión" de la app (recorrido.py):
    # un aparato que recorre los canales solo, desde una casa.
    recorrida = models.DateTimeField('probada por el modo revisión', null=True, blank=True)
    # La RETIRÓ la limpieza (salud.limpiar): no anduvo en una semana y el canal
    # tiene otras que sí. Queda apagada (`activa` = False), pero no como lo
    # apagado a mano: el servidor la sigue probando y, si vuelve a andar,
    # vuelve sola. Null = no la retiró la limpieza.
    retirada = models.DateTimeField('retirada por la limpieza', null=True, blank=True)

    class Meta:
        verbose_name = 'fuente'
        verbose_name_plural = 'fuentes'
        ordering = ['prioridad', 'pk']
        constraints = [
            models.UniqueConstraint(fields=['canal', 'url'], name='fuente_unica_por_canal'),
        ]

    def __str__(self):
        return f'{self.canal} · {self.get_tipo_display()} · {self.url[:60]}'

    def usable(self):
        """¿La app la puede usar?"""
        return self.activa and self.estado != self.Estado.CAIDA and not self.oculta_por_aparatos

    @property
    def oculta_por_aparatos(self):
        return self.oculta_hasta is not None and self.oculta_hasta > timezone.now()

    @property
    def vuelve_a_probarse(self):
        """Cuándo deja de estar oculta (y la app la vuelve a intentar)."""
        return self.oculta_hasta

    @property
    def cortes_por_hora(self):
        """Cada cuánto se corta en los aparatos (None = todavía se vio poco para saberlo)."""
        if self.segundos_en_aparatos < MINIMO_VISTO_PARA_JUZGAR:
            return None
        return round(self.cortes_en_aparatos * 3600 / self.segundos_en_aparatos, 1)


class Importacion(models.Model):
    """
    Una lista M3U subida desde el panel, en tres pasos:

      1. Se analiza toda al subirla (rápido): se descarta lo que ya se sabe
         que no sirve (adultos, otro idioma, repetidos...).
      2. Se PRUEBA de a tandas (TAMANIO_LOTE): la pantalla va pidiendo tanda
         por tanda y muestra el avance. Lo que pasa todas las pruebas queda
         "apta"; todavía no se carga nada.
      3. Se CARGAN las aptas (otro botón), y recién ahí entran a la app.

    Así una lista de miles de canales no traba el servidor, si se cierra la
    página se puede seguir después, y solo entra lo que está bien.
    """
    archivo = models.CharField(max_length=150)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='+')
    creada = models.DateTimeField(auto_now_add=True)
    terminada = models.DateTimeField(null=True, blank=True)
    total = models.PositiveIntegerField(default=0)
    # Cuántas quedaron para verificar en esta ronda (sin las descartadas ni
    # repetidas al subirla): sobre esto se calcula el porcentaje de avance.
    para_verificar = models.PositiveIntegerField(default=0)
    # Lo que se eligió al subirla
    solo_espanol = models.BooleanField(default=False)
    descartar_sin_logo = models.BooleanField(default=False)
    descartar_vod = models.BooleanField('descartar películas y series', default=False)
    descartar_adultos = models.BooleanField('descartar contenido para adultos', default=True)
    # La prueba a fondo: sonido, idioma del audio, resolución, formato, si llega fluido y si avanza
    a_fondo = models.BooleanField('prueba a fondo', default=False)
    # Cuándo se cargaron las aptas (null = todavía no)
    cargada = models.DateTimeField(null=True, blank=True)
    # Traer de YouTube como UNA serie: todos los videos son capítulos de esta
    # serie, numerados del más viejo al más nuevo ('' = películas sueltas).
    # Los números definitivos se ponen al terminar de probar (servicios._numerar_capitulos).
    serie = models.CharField('serie', max_length=90, blank=True)
    temporada = models.PositiveSmallIntegerField(default=1)
    # Cada video va a la temporada y al capítulo que dice su título ("Temporada 3
    # Capítulo 33"); `temporada` queda para los que no dicen la suya. Para canales
    # con todas las temporadas mezcladas (ver servicios._numerar_capitulos).
    segun_titulo = models.BooleanField('según el título', default=False)
    # Todo lo importado va a esta sección nueva (Música, Radio...; '' = cada
    # cosa a la fija que le toca: En vivo, Películas o Series)
    seccion = models.CharField('sección', max_length=10, blank=True)
    # La lista la exportó este sistema (canales/exportar.py): lo que trae ya
    # estaba aceptado acá, así que sus series entran aunque tengan pocos capítulos
    de_kairos = models.BooleanField('exportada de Kairos', default=False)
    # Una lista grande (más de servicios.LEER_DE_UNA entradas) se lee de a tandas,
    # desde la pantalla de la importación: cuántas faltan leer (0 = ya se leyó toda)
    por_leer = models.PositiveIntegerField('faltan leer', default=0)

    class Meta:
        verbose_name = 'importación'
        verbose_name_plural = 'importaciones'
        ordering = ['-creada']

    def __str__(self):
        return f'{self.archivo} ({self.creada:%d/%m/%Y %H:%M})'

    @property
    def contenido_principal(self):
        """La sección de la mayoría de lo que trajo (para ir a verlo en Organizar contenido)."""
        fila = (self.entradas.values('contenido').annotate(cuantas=models.Count('pk')).order_by('-cuantas')
                .first())
        return self.seccion or (fila['contenido'] if fila else Contenido.VIVO)


class EntradaImportada(models.Model):
    """Un canal de la lista importada y qué pasó con él (y por qué)."""

    class Estado(models.TextChoices):
        PENDIENTE = 'pendiente', 'Por probar'
        APTA = 'apta', 'Apta (falta cargar)'
        AGREGADA = 'agregada', 'Cargada'
        CAIDA = 'caida', 'No responde'
        RECHAZADA = 'rechazada', 'No pasó la prueba'
        DESCARTADA = 'descartada', 'Descartada'
        REPETIDA = 'repetida', 'Ya estaba'

    # Por qué no pasó la prueba (para agrupar en el informe)
    class Causa(models.TextChoices):
        FORMATO = 'formato', 'Formato que muchos aparatos no leen'
        SIN_SONIDO = 'sin_sonido', 'Sin sonido'
        IDIOMA = 'idioma', 'Audio en otro idioma'
        BAJA_CALIDAD = 'baja_calidad', 'Imagen de baja calidad'
        LENTA = 'lenta', 'Llega lenta (se cortaría)'
        SE_CORTA = 'se_corta', 'Se corta o está congelada'
        SERIE_INCOMPLETA = 'serie_incompleta', 'Serie incompleta'

    Contenido = Contenido

    importacion = models.ForeignKey(Importacion, on_delete=models.CASCADE, related_name='entradas')
    posicion = models.PositiveIntegerField()
    nombre_original = models.CharField(max_length=200, help_text='Como venía en la lista.')
    nombre = models.CharField(max_length=120, help_text='Limpio: sin prefijo de país ni calidad.')
    logo = models.CharField(max_length=500, blank=True)
    categoria = models.CharField(max_length=80, blank=True)
    numero = models.CharField(max_length=10, blank=True)
    tvg_id = models.CharField(max_length=120, blank=True)
    pais = models.CharField(max_length=2, blank=True)
    idioma = models.CharField(max_length=5, choices=Idioma.choices, blank=True)
    contenido = models.CharField(max_length=10, default=Contenido.VIVO)
    url = models.CharField(max_length=1000)
    tipo = models.CharField('formato', max_length=10, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    referer = models.CharField(max_length=500, blank=True)
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.PENDIENTE)
    motivo = models.CharField(max_length=200, blank=True)
    causa = models.CharField(max_length=16, choices=Causa.choices, blank=True)
    # Lo que dio la prueba (para cargarla después sin volver a probar)
    estado_fuente = models.CharField(max_length=15, blank=True)
    codec = models.CharField(max_length=10, blank=True)
    calidad = models.CharField(max_length=80, blank=True)
    canal = models.ForeignKey(Canal, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    class Meta:
        verbose_name = 'entrada importada'
        verbose_name_plural = 'entradas importadas'
        ordering = ['posicion']
        indexes = [
            models.Index(fields=['importacion', 'estado', 'posicion']),
            # Para trabajar por partes una lista grande: En vivo / Películas / Series y sus categorías
            models.Index(fields=['importacion', 'contenido', 'categoria']),
        ]

    def __str__(self):
        return f'{self.nombre} · {self.get_estado_display()}'

    def get_contenido_display(self):
        return _nombre_del_contenido(self.contenido)

    def get_tipo_display(self):
        return dict(Fuente.Tipo.choices).get(self.tipo) or ('RTMP' if self.tipo == 'rtmp' else 'Se averigua al verificar')


# ── Lo más visto (estadísticas para el administrador) ────────────────

class Visto(models.Model):
    """
    Cuánto se miró un canal, película o capítulo en un día, sumando todos
    los aparatos. NO se guarda quién lo miró: solo los totales. Lo cuenta la
    app y lo manda de a ratos (POST /api/v1/canales/visto/).
    """
    canal = models.ForeignKey(Canal, on_delete=models.CASCADE, related_name='vistos')
    fecha = models.DateField(db_index=True)
    segundos = models.PositiveIntegerField(default=0)
    vistas = models.PositiveIntegerField(default=0, help_text='Veces que alguien lo miró más de un minuto.')

    class Meta:
        verbose_name = 'visto'
        verbose_name_plural = 'vistos'
        constraints = [models.UniqueConstraint(fields=['canal', 'fecha'], name='un_visto_por_canal_y_dia')]

    def __str__(self):
        return f'{self.canal} · {self.fecha} · {self.segundos // 60} min'


class FavoritoAgregado(models.Model):
    """
    Cuántas veces se agregó algo a favoritos en un día (todos los aparatos
    juntos, sin saber quién). `clave` es la que usa la app: "c:<id>" para un
    canal o película, "s:<nombre>" para una serie entera.
    """
    clave = models.CharField(max_length=130)
    fecha = models.DateField(db_index=True)
    veces = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'favorito agregado'
        verbose_name_plural = 'favoritos agregados'
        constraints = [models.UniqueConstraint(fields=['clave', 'fecha'], name='un_favorito_por_clave_y_dia')]

    def __str__(self):
        return f'{self.clave} · {self.fecha} · {self.veces}'
