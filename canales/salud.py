"""
La SALUD de las fuentes y los canales: si andan de verdad, con memoria.

Antes cada fuente se juzgaba por su ÚLTIMA prueba: un corte de 5 minutos a
las 3 de la mañana pesaba lo mismo que una fuente muerta hace un mes. Ahora
cada fuente recuerda (campos de Fuente):

  - `historial`: sus últimas pruebas, del servidor y de los aparatos, una
    letra cada una (ver LETRAS);
  - `anduvo`: la última vez que anduvo (el servidor la vio bien, o un aparato
    la miró al menos un minuto: servicios.VISTO_PARA_PERDONAR);
  - `falla_desde` y `fallas_seguidas`: desde cuándo falla SIN PARAR y cuántas
    veces falló en ese tiempo. Cualquier vez que anda, vuelven a cero;
  - `por_que_falla`: el motivo de la última falla (MOTIVOS).

Las pruebas llegan solas: la verificación del cron (cada 6 horas), la que
dispara un aviso de la app, y lo que cuentan los aparatos al ver (o no poder
ver) cada fuente. Cuando el servidor no puede saber (los paneles Xtream
bloquean al VPS) anota "?" y no cuenta ni a favor ni en contra: ahí deciden
los aparatos.

Con eso cada fuente, y cada canal, está en UN estado (Salud): Anda,
Inestable, Sin datos, Formato, Rechaza, Falla o Muerta.

LIMPIEZA AUTOMÁTICA (limpiar, la corre el cron después de verificar): un canal
cuyas fuentes prendidas están TODAS muertas (fallan sin parar hace
DIAS_PARA_QUITAR días, y al menos FALLAS_PARA_QUITAR veces: a distintas
horas, no un corte) se quita de la app con el motivo anotado (empieza con
QUITADO_POR_LA_LIMPIEZA). Nunca se borra nada: el servidor lo sigue probando
y, si alguna fuente vuelve a andar, el canal vuelve solo. Lo que se quitó a
mano no lo toca.

Lo mismo con cada SEÑAL: una fuente muerta de un canal que tiene otras que
andan se RETIRA (Fuente.retirada: la app deja de recibirla y no pierde tiempo
probándola). El servidor la sigue probando y, si vuelve a andar, vuelve sola.
Lo apagado a mano (activa = False sin `retirada`) no vuelve solo.
"""

from collections import Counter
from datetime import timedelta

from django.core.cache import cache
from django.db.models import Prefetch, Q, TextChoices
from django.utils import timezone

from actividad.models import Accion
from actividad.registro import registrar

from .models import Canal, Fuente

# Cuántas pruebas recuerda cada fuente (con el cron cada 6 h y los aparatos, unos días)
LARGO_DEL_HISTORIAL = 20

# Las letras del historial
ANDUVO_EN_EL_SERVIDOR = '+'
SE_VIO_EN_UN_APARATO = '*'
FALLO_EN_EL_SERVIDOR = '-'
FALLO_EN_UN_APARATO = 'x'
UN_APARATO_NO_LA_LEE = 'f'   # no es que el link falle: ese aparato no puede con el video
NO_SE_SABE = '?'             # el servidor no pudo probarla (Xtream que bloquea al VPS)
LETRAS = {
    ANDUVO_EN_EL_SERVIDOR: '✓', SE_VIO_EN_UN_APARATO: '✓', FALLO_EN_EL_SERVIDOR: '✗', FALLO_EN_UN_APARATO: '✗',
    UN_APARATO_NO_LA_LEE: '▣', NO_SE_SABE: '?',
}
ANDUVO = ANDUVO_EN_EL_SERVIDOR + SE_VIO_EN_UN_APARATO
FALLO = FALLO_EN_EL_SERVIDOR + FALLO_EN_UN_APARATO

# Por qué falla, en palabras del panel
MOTIVOS = {
    'no_existe': 'la dirección ya no existe',
    'rechaza': 'el proveedor la rechaza: cuenta vencida, ocupada o bloqueada',
    'tiempo': 'no responde a tiempo',
    'conexion': 'no se puede conectar',
    'formato': 'algunos aparatos no pueden leer el video',
    'error': 'da error',
}
# Lo que manda la app al avisar una falla (servicios.MOTIVOS_DE_LOS_APARATOS) -> MOTIVOS
_MOTIVO_DEL_APARATO = {'rechazo': 'rechaza', 'formato': 'formato', 'tiempo': 'tiempo', 'conexion': 'conexion'}

# Cuándo una fuente está muerta: falla sin parar hace estos días, y al menos estas veces
DIAS_PARA_QUITAR = 7
FALLAS_PARA_QUITAR = 8
# Inestable: entre sus últimas pruebas hay de las dos, y fallan al menos 1 de cada 4
PRUEBAS_PARA_INESTABLE = 12

# Lo que cuentan los aparatos entra al historial como mucho una vez cada esto
# (por fuente): si cien personas miran el mismo canal, no tapa al servidor.
ESPERA_ENTRE_APARATOS = 30 * 60   # segundos

# Así empieza el motivo de lo que quitó la limpieza (y solo eso vuelve solo)
QUITADO_POR_LA_LIMPIEZA = 'Limpieza automática'

CAMPOS = ['historial', 'anduvo', 'falla_desde', 'fallas_seguidas', 'por_que_falla']


class Salud(TextChoices):
    # En orden de mejor a peor: un canal está como su MEJOR fuente
    ANDA = 'anda', 'Anda'
    INESTABLE = 'inestable', 'Inestable'
    SIN_DATOS = 'sin_datos', 'Sin datos'
    FORMATO = 'formato', 'Formato'
    RECHAZA = 'rechaza', 'Rechaza'
    FALLA = 'falla', 'Falla'
    MUERTA = 'muerta', 'Muerta'


_ORDEN = list(Salud)


# ── Anotar las pruebas ───────────────────────────────────────────────

def anotar(fuente, letra, motivo='', ahora=None):
    """
    Suma una prueba (`letra`) a la memoria de la fuente. No guarda: los campos
    que cambian son CAMPOS.
    """
    ahora = ahora or timezone.now()
    fuente.historial = (fuente.historial + letra)[-LARGO_DEL_HISTORIAL:]
    if letra in ANDUVO:
        fuente.anduvo = ahora
        fuente.falla_desde, fuente.fallas_seguidas, fuente.por_que_falla = None, 0, ''
    elif letra in FALLO:
        fuente.falla_desde = fuente.falla_desde or ahora
        fuente.fallas_seguidas = min(fuente.fallas_seguidas + 1, 30000)
        fuente.por_que_falla = motivo or 'error'
    elif letra == UN_APARATO_NO_LA_LEE and not fuente.fallas_seguidas:
        fuente.por_que_falla = 'formato'


def _motivo_del_servidor(error):
    error = error or ''
    if any(texto in error for texto in ('error 404', 'error 410', 'ya no existe')):
        return 'no_existe'
    if any(texto in error for texto in ('error 401', 'error 403', 'error 451', 'página web', 'cortó la conexión')):
        return 'rechaza'
    if 'a tiempo' in error:
        return 'tiempo'
    if 'conectar' in error or 'conexión' in error or 'Certificado' in error:
        return 'conexion'
    return 'error'


def anotar_del_servidor(fuente, resultado, ahora=None):
    """Lo que dio una verificación del servidor (verificacion.Resultado)."""
    if resultado.estado == Fuente.Estado.FUNCIONA:
        anotar(fuente, ANDUVO_EN_EL_SERVIDOR, ahora=ahora)
    elif resultado.estado == Fuente.Estado.CAIDA:
        anotar(fuente, FALLO_EN_EL_SERVIDOR, _motivo_del_servidor(resultado.error), ahora)
    else:
        anotar(fuente, NO_SE_SABE, ahora=ahora)


def anotar_del_aparato(fuente, anduvo, motivo='', ahora=None):
    """
    Lo que contó un aparato: la vio bien (`anduvo`) o no pudo (`motivo`: el
    que manda la app). Al historial entra una vez cada ESPERA_ENTRE_APARATOS;
    pero que anduvo se anota siempre (cualquier vez que anda, deja de fallar).
    Devuelve True si cambió algo (hay que guardar CAMPOS).
    """
    motivo = _MOTIVO_DEL_APARATO.get(motivo, 'error')
    letra = SE_VIO_EN_UN_APARATO if anduvo else UN_APARATO_NO_LA_LEE if motivo == 'formato' else FALLO_EN_UN_APARATO
    if cache.add(f'salud_aparato:{fuente.pk}:{letra}', True, timeout=ESPERA_ENTRE_APARATOS):
        anotar(fuente, letra, motivo, ahora)
        return True
    if anduvo:
        fuente.anduvo = ahora or timezone.now()
        fuente.falla_desde, fuente.fallas_seguidas, fuente.por_que_falla = None, 0, ''
        return True
    return False


def anotar_del_recorrido(fuente, anduvo, motivo='', ahora=None):
    """
    Lo que encontró el "modo revisión" de la app (recorrido.py): un aparato
    que prueba los canales uno por uno a propósito. Entra siempre al historial
    (no es gente mirando: no hace falta limitarlo).
    """
    motivo = _MOTIVO_DEL_APARATO.get(motivo, 'error')
    letra = SE_VIO_EN_UN_APARATO if anduvo else UN_APARATO_NO_LA_LEE if motivo == 'formato' else FALLO_EN_UN_APARATO
    anotar(fuente, letra, motivo, ahora)


def al_cargar(estado, ahora):
    """Los campos de una fuente que se carga recién probada (importación): su primera prueba."""
    if estado == Fuente.Estado.FUNCIONA:
        return {'historial': ANDUVO_EN_EL_SERVIDOR, 'anduvo': ahora}
    return {}


def olvidar_fallas(fuentes):
    """'Volver a mostrar': otra oportunidad entera (si siguen fallando, se cuentan DIAS_PARA_QUITAR desde cero)."""
    return fuentes.filter(fallas_seguidas__gt=0).update(falla_desde=None, fallas_seguidas=0)


# ── Cómo está cada fuente y cada canal ───────────────────────────────

def esta_muerta(fuente, ahora=None):
    ahora = ahora or timezone.now()
    return (fuente.fallas_seguidas >= FALLAS_PARA_QUITAR and fuente.falla_desde is not None
            and fuente.falla_desde <= ahora - timedelta(days=DIAS_PARA_QUITAR))


def _cuentas(historial):
    """De las últimas pruebas que dicen algo: (cuántas anduvo, cuántas falló)."""
    claras = [letra for letra in historial if letra in ANDUVO + FALLO][-PRUEBAS_PARA_INESTABLE:]
    anduvo = sum(1 for letra in claras if letra in ANDUVO)
    return anduvo, len(claras) - anduvo


def de_fuente(fuente, ahora=None):
    if fuente.fallas_seguidas:
        if esta_muerta(fuente, ahora):
            return Salud.MUERTA
        return Salud.RECHAZA if fuente.por_que_falla == 'rechaza' else Salud.FALLA
    if fuente.por_que_falla == 'formato':
        return Salud.FORMATO
    anduvo, fallo = _cuentas(fuente.historial)
    if anduvo and fallo >= 2 and fallo * 4 >= anduvo + fallo:
        return Salud.INESTABLE
    return Salud.ANDA if fuente.anduvo else Salud.SIN_DATOS


def de_canal(fuentes, ahora=None):
    """Un canal está como su MEJOR fuente prendida (None: no tiene ninguna prendida)."""
    estados = [de_fuente(f, ahora) for f in fuentes if f.activa]
    return min(estados, key=_ORDEN.index) if estados else None


def _fecha(momento):
    return f'{timezone.localtime(momento):%d/%m %H:%M}'


def _hace(momento, ahora):
    tiempo = ahora - momento
    if tiempo < timedelta(hours=1):
        return 'menos de una hora'
    if tiempo < timedelta(days=2):
        horas = round(tiempo.total_seconds() / 3600)
        return f'{horas} hora{"s" if horas != 1 else ""}'
    return f'{tiempo.days} días'


def texto_de_fuente(fuente, ahora=None):
    """Para el panel de detalles: cómo está, por qué, y sus últimas pruebas."""
    ahora = ahora or timezone.now()
    salud = de_fuente(fuente, ahora)
    motivo = MOTIVOS.get(fuente.por_que_falla, MOTIVOS['error'])
    anduvo, fallo = _cuentas(fuente.historial)
    if salud == Salud.MUERTA:
        texto = f'Muerta: falla sin parar hace {_hace(fuente.falla_desde, ahora)} ({motivo}).'
    elif salud in (Salud.FALLA, Salud.RECHAZA):
        quita = fuente.falla_desde + timedelta(days=DIAS_PARA_QUITAR)
        texto = (f'{"Rechazada" if salud == Salud.RECHAZA else "Falla"} hace {_hace(fuente.falla_desde, ahora)} '
                 f'({motivo}). Si sigue así hasta el {_fecha(quita)}, se da por muerta.')
    elif salud == Salud.FORMATO:
        texto = 'Formato: la señal anda, pero algunos aparatos no pueden leer el video.'
    elif salud == Salud.INESTABLE:
        texto = f'Inestable: anduvo {anduvo} de las últimas {anduvo + fallo} pruebas (a veces sí, a veces no).'
    elif salud == Salud.ANDA:
        texto = 'Anda' + (f': anduvo {anduvo} de las últimas {anduvo + fallo} pruebas.' if fallo else '.')
    else:
        texto = ('Sin datos: el servidor no puede probarla (los paneles Xtream lo bloquean) y todavía nadie la '
                 'vio en un aparato.' if NO_SE_SABE in fuente.historial else 'Sin datos: todavía no se probó.')
    if fuente.anduvo and salud != Salud.ANDA:
        texto += f' Anduvo por última vez el {_fecha(fuente.anduvo)}.'
    if fuente.historial:
        texto += ' Últimas pruebas: ' + ''.join(LETRAS.get(letra, letra) for letra in fuente.historial) + '.'
    return texto


TEXTOS_DE_CANAL = {
    Salud.ANDA: 'Anda.',
    Salud.INESTABLE: 'Inestable: a veces anda y a veces no (hora pico, proveedor saturado...).',
    Salud.SIN_DATOS: 'Sin datos: todavía no se sabe si anda (nadie lo vio y el servidor no puede probarlo).',
    Salud.FORMATO: 'Formato: anda, pero algunos aparatos no pueden leer el video.',
    Salud.RECHAZA: 'Rechaza: el servidor de la señal no lo entrega (cuenta vencida, ocupada o bloqueada).',
    Salud.FALLA: 'Falla: ninguna fuente anda ahora. Si sigue así una semana, se quita solo.',
    Salud.MUERTA: f'Muerto: ninguna fuente anduvo en {DIAS_PARA_QUITAR} días. La limpieza lo quita de la app.',
}


def texto_de_canal(fuentes, ahora=None):
    salud = de_canal(fuentes, ahora)
    return TEXTOS_DE_CANAL[salud] if salud else ''


# ── La limpieza automática ───────────────────────────────────────────

def _no_muerta(ahora):
    """La regla de esta_muerta, al revés y en la base."""
    limite = ahora - timedelta(days=DIAS_PARA_QUITAR)
    return Q(fallas_seguidas__lt=FALLAS_PARA_QUITAR) | Q(falla_desde__isnull=True) | Q(falla_desde__gt=limite)


def _vivas(ahora):
    """Las fuentes prendidas que NO están muertas."""
    return Fuente.objects.filter(activa=True).filter(_no_muerta(ahora))


def devolver_senales(ahora=None, fuentes=None):
    """
    Las señales que retiró la limpieza y volvieron a andar (ya no están
    muertas) vuelven a la app. `fuentes`: solo entre esas. Devuelve cuántas.
    """
    ahora = ahora or timezone.now()
    volvieron = Fuente.objects.filter(activa=False, retirada__isnull=False).filter(_no_muerta(ahora))
    if fuentes is not None:
        volvieron = volvieron.filter(pk__in=fuentes)
    return volvieron.update(activa=True, retirada=None)


def retirar_senales(ahora=None):
    """
    Retira las señales muertas de los canales que tienen otra que no lo está
    (si todas están muertas, se quita el canal entero: limpiar). Devuelve
    los nombres de los canales a los que se les retiró alguna.
    """
    ahora = ahora or timezone.now()
    muertas = (Fuente.objects.filter(activa=True, canal__eliminado_en__isnull=True)
               .exclude(_no_muerta(ahora)).filter(canal__in=_vivas(ahora).values('canal')))
    canales = sorted(set(muertas.values_list('canal__nombre', flat=True)))
    cantidad = muertas.update(activa=False, retirada=ahora)
    if cantidad:
        registrar(None, Accion.SISTEMA, f'La limpieza automática retiró {cantidad} señal(es) que no anduvieron en '
                                        f'{DIAS_PARA_QUITAR} días, de canales que siguen andando con otras '
                                        f'({_nombres(canales)}). Si vuelven a andar, vuelven solas.',
                  modulo='canales')
    return canales


def _motivo_de_quitar(canal):
    fuente = canal.fuentes_prendidas[0]
    return (f'{QUITADO_POR_LA_LIMPIEZA}: ninguna fuente anduvo en {DIAS_PARA_QUITAR} días '
            f'({MOTIVOS.get(fuente.por_que_falla, MOTIVOS["error"])}). Si alguna vuelve a andar, vuelve sola.')[:200]


def limpiar(ahora=None):
    """
    La limpieza: devuelve las señales retiradas que volvieron a andar,
    retira las muertas de canales que tienen otras, quita de la app los
    canales muertos y devuelve los que revivieron. La corre el cron
    (verificar_fuentes) después de verificar. Devuelve {'quitados': [nombres],
    'volvieron': [nombres], 'senales_retiradas': [canales], 'senales_devueltas': cantidad}.
    """
    ahora = ahora or timezone.now()
    devueltas = devolver_senales(ahora)
    retiradas = retirar_senales(ahora)
    vivas = _vivas(ahora).values('canal')
    muertos = list(
        Canal.objects.filter(activo=True, fuentes__activa=True).exclude(pk__in=vivas).distinct()
        .prefetch_related(Prefetch('fuentes', queryset=Fuente.objects.filter(activa=True), to_attr='fuentes_prendidas'))
    )
    for canal in muertos:
        canal.activo, canal.motivo_quitado, canal.modificado = False, _motivo_de_quitar(canal), ahora
    Canal.objects.bulk_update(muertos, ['activo', 'motivo_quitado', 'modificado'])

    quitados = [canal.nombre for canal in muertos]
    if quitados:
        registrar(None, Accion.SISTEMA, f'La limpieza automática quitó {len(quitados)} canal(es) de la app: ninguna '
                                        f'fuente anduvo en {DIAS_PARA_QUITAR} días ({_nombres(quitados)}).',
                  modulo='canales')
    return {'quitados': quitados, 'volvieron': devolver_los_que_andan(ahora), 'senales_retiradas': retiradas,
            'senales_devueltas': devueltas}


def devolver_los_que_andan(ahora=None, canales=None):
    """
    Los canales que quitó la limpieza y ya no están muertos (alguna fuente
    volvió a andar) vuelven a la app. `canales`: solo entre esos (pks).
    Devuelve sus nombres.
    """
    ahora = ahora or timezone.now()
    revivieron = Canal.objects.filter(activo=False, motivo_quitado__startswith=QUITADO_POR_LA_LIMPIEZA,
                                      pk__in=_vivas(ahora).values('canal'))
    if canales is not None:
        revivieron = revivieron.filter(pk__in=canales)
    volvieron = list(revivieron.values_list('nombre', flat=True))
    revivieron.update(activo=True, motivo_quitado='', modificado=ahora)
    if volvieron:
        registrar(None, Accion.SISTEMA, f'Volvieron solos a la app {len(volvieron)} canal(es) que había quitado la '
                                        f'limpieza: alguna fuente volvió a andar ({_nombres(volvieron)}).',
                  modulo='canales')
    return volvieron


def _nombres(nombres, cuantos=10):
    texto = ', '.join(nombres[:cuantos])
    return texto + (f' y {len(nombres) - cuantos} más' if len(nombres) > cuantos else '')


def resumen(ahora=None):
    """Cuántos canales (prendidos, no quitados) hay en cada estado: {Salud: cantidad}."""
    canales = Canal.objects.filter(activo=True).prefetch_related(
        Prefetch('fuentes', queryset=Fuente.objects.filter(activa=True).only(
            'canal_id', 'activa', 'historial', 'anduvo', 'falla_desde', 'fallas_seguidas', 'por_que_falla'),
            to_attr='fuentes_prendidas')).only('pk')
    cuentas = Counter(de_canal(canal.fuentes_prendidas, ahora) for canal in canales)
    cuentas.pop(None, None)
    return {salud: cuentas.get(salud, 0) for salud in Salud}
