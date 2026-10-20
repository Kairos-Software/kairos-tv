"""
SEÑALES CON PROBLEMAS (/canales/senales/): todas las fuentes que no andan bien,
UNA POR UNA, aunque su canal se siga viendo con otras.

En Organizar y en Para revisar se mira por CANAL: si un canal anda con 2 de
sus 4 señales, "se ve", y las otras 2 no aparecen en ningún lado salvo que se
abra su Detalle. Acá aparecen todas, cada una con su problema (PROBLEMAS, en
el orden en que conviene mirarlas), si su canal se sigue viendo o no, y su
acción ahí mismo (probar, quitar, volver a mostrar, borrar), de a una o
varias juntas.

El problema de cada señal sale de la misma salud que usa el resto del panel
(salud.de_fuente), más lo que la saca de la app: apagada a mano, retirada por
la limpieza o escondida un rato por fallar en los aparatos. Ver de_fuente.
"""

import time
from dataclasses import dataclass

from django.db.models import Q
from django.utils import timezone

from . import salud
from .bandeja import FUENTES_PARA_PROBAR, SEGUNDOS_PARA_PROBAR
from .consultas import TIPOS_QUE_REPRODUCE_LA_APP
from .models import Fuente
from .salud import Salud
from .servicios import CAMPOS_DE_VERIFICACION, aplicar_resultado

# clave -> (nombre corto, explicación para la ayuda). En el orden en que conviene revisarlas.
PROBLEMAS = {
    'fallan': ('Fallan', 'No andan en este momento. Si siguen así una semana, se retiran solas (o se quita el canal, '
                         'si no tiene otra).'),
    'rechazan': ('Rechazadas', 'El proveedor no la entrega: cuenta vencida, ocupada o bloqueada.'),
    'ocultas': ('Fallan en los aparatos', 'Los aparatos avisaron que no la pueden ver: la app no la usa por un rato y '
                                          'después la vuelve a probar sola.'),
    'inestables': ('Inestables', 'A veces andan y a veces no (hora pico, proveedor saturado). Si el canal es muy '
                                 'visto, conviene buscarle otra.'),
    'formato': ('Formato', 'Anda, pero algunos aparatos no pueden leer el video.'),
    'muertas': ('Muertas', f'No andan hace {salud.DIAS_PARA_QUITAR} días o más.'),
    'retiradas': ('Retiradas', 'La limpieza las sacó de la app porque no anduvieron en una semana. Si vuelven a '
                               'andar, vuelven solas.'),
    'apagadas': ('Quitadas a mano', 'Alguien las quitó: la app no las usa aunque anden. No vuelven solas.'),
    'sin_datos': ('Sin datos', 'Todavía no se sabe si andan: el servidor no las puede probar (los paneles Xtream lo '
                               'bloquean) y nadie las vio en un aparato.'),
}
# "Con problemas" (lo que se ve al entrar): todo menos lo que todavía no se sabe
CON_PROBLEMAS = [clave for clave in PROBLEMAS if clave != 'sin_datos']
POR_PAGINA = 50

_DE_LA_SALUD = {Salud.MUERTA: 'muertas', Salud.RECHAZA: 'rechazan', Salud.FALLA: 'fallan', Salud.FORMATO: 'formato',
                Salud.INESTABLE: 'inestables', Salud.SIN_DATOS: 'sin_datos'}


def de_fuente(fuente, ahora=None):
    """El problema de una señal (una clave de PROBLEMAS), o '' si anda bien."""
    ahora = ahora or timezone.now()
    if not fuente.activa:
        return 'retiradas' if fuente.retirada else 'apagadas'
    if fuente.oculta_hasta and fuente.oculta_hasta > ahora:
        return 'ocultas'
    estado = salud.de_fuente(fuente, ahora)
    if fuente.estado == Fuente.Estado.CAIDA and estado in (Salud.ANDA, Salud.SIN_DATOS, Salud.INESTABLE):
        return 'fallan'   # caída en la última prueba (de antes de la salud con memoria): la app no la usa
    return _DE_LA_SALUD.get(estado, '')


def usable(fuente, ahora):
    """¿La app la recibe? (la misma regla que consultas.fuentes_usables)"""
    return (fuente.activa and fuente.tipo in TIPOS_QUE_REPRODUCE_LA_APP and fuente.estado != Fuente.Estado.CAIDA
            and not (fuente.oculta_hasta and fuente.oculta_hasta > ahora))


def _hace(momento, ahora):
    return salud._hace(momento, ahora) if momento else ''


def detalle(fuente, problema, ahora):
    """Una línea: qué le pasa y desde cuándo."""
    motivo = salud.MOTIVOS.get(fuente.por_que_falla, '')
    if problema in ('fallan', 'rechazan', 'muertas'):
        partes = [motivo or fuente.error or 'no anda']
        if fuente.falla_desde:
            partes.append(f'hace {_hace(fuente.falla_desde, ahora)}')
        return ' · '.join(partes)
    if problema == 'ocultas':
        vuelve = timezone.localtime(fuente.oculta_hasta)
        return f'{fuente.falla_en_aparatos or "no se pudo ver"} · se vuelve a probar el {vuelve:%d/%m %H:%M}'
    if problema == 'inestables':
        anduvo, fallo = salud._cuentas(fuente.historial)
        return f'anduvo {anduvo} de las últimas {anduvo + fallo} pruebas'
    if problema == 'formato':
        return 'algunos aparatos no pueden leer el video'
    if problema == 'retiradas':
        return f'retirada el {timezone.localtime(fuente.retirada):%d/%m}' + (f' · {motivo}' if motivo else '')
    if problema == 'apagadas':
        return 'la quitaron a mano'
    if problema == 'sin_datos':
        return ('el servidor no la puede probar y nadie la vio' if salud.NO_SE_SABE in fuente.historial
                else 'todavía no se probó')
    return ''


@dataclass
class Senal:
    """Una fila de la lista: la fuente, su problema y lo que importa de su canal."""
    fuente: Fuente
    problema: str
    detalle: str
    numero: int          # su lugar entre las señales del canal (1 = la que se prueba primero)
    de: int              # cuántas señales tiene el canal
    canal_se_ve: bool    # ¿el canal se ve en la app con alguna señal?
    otras_que_andan: int

    @property
    def nombre_problema(self):
        return PROBLEMAS[self.problema][0]

    @property
    def pruebas(self):
        return ''.join(salud.LETRAS.get(letra, letra) for letra in self.fuente.historial[-10:])


def _alcance(contenido='', origen='', texto='', canal=None):
    """Las fuentes de los canales que se miran (no eliminados), con su canal."""
    fuentes = Fuente.objects.filter(canal__eliminado_en__isnull=True).select_related('canal', 'canal__categoria')
    if contenido:
        fuentes = fuentes.filter(canal__contenido=contenido)
    if origen:
        fuentes = fuentes.filter(origen=origen)
    if texto:
        fuentes = fuentes.filter(Q(canal__nombre__icontains=texto) | Q(url__icontains=texto))
    if canal:
        fuentes = fuentes.filter(canal_id=canal)
    return fuentes


def armar(contenido='', problema='', origen='', texto='', canal=None, ahora=None):
    """
    (filas, cuentas): las señales con `problema` (una clave de PROBLEMAS, 'todas' = con cualquier problema
    menos "sin datos", 'cualquiera' = también las que andan) y cuántas hay de cada problema con los
    mismos filtros. Primero las de canales que NO se ven (lo urgente), después por canal y número de señal.
    """
    ahora = ahora or timezone.now()
    fuentes = list(_alcance(contenido, origen, texto, canal))
    # Las otras señales de cada canal, para numerarlas y saber si el canal se ve (aunque el filtro no las traiga)
    canales = {f.canal_id for f in fuentes}
    hermanas = {}
    for f in (Fuente.objects.filter(canal_id__in=canales).order_by('prioridad', 'pk')
              .only('pk', 'canal_id', 'activa', 'tipo', 'estado', 'oculta_hasta')):
        hermanas.setdefault(f.canal_id, []).append(f)
    cuentas = dict.fromkeys(PROBLEMAS, 0)
    filas = []
    for fuente in fuentes:
        clave = de_fuente(fuente, ahora)
        if clave:
            cuentas[clave] += 1
        quiere = (clave in CON_PROBLEMAS if problema in ('', 'todas') else
                  True if problema == 'cualquiera' else clave == problema)
        if not quiere:
            continue
        del_canal = hermanas.get(fuente.canal_id, [fuente])
        usables = [f.pk for f in del_canal if usable(f, ahora)]
        numero = next((i for i, f in enumerate(del_canal, start=1) if f.pk == fuente.pk), 1)
        filas.append(Senal(fuente, clave or 'anda', detalle(fuente, clave, ahora) if clave else 'anda bien', numero,
                           len(del_canal), fuente.canal.activo and bool(usables),
                           len([pk for pk in usables if pk != fuente.pk])))
    filas.sort(key=lambda s: (s.canal_se_ve, s.fuente.canal.nombre.lower(), s.fuente.canal_id, s.numero))
    cuentas['todas'] = sum(cuentas[clave] for clave in CON_PROBLEMAS)
    return filas, cuentas


def contar(ahora=None):
    """Cuántas señales tienen algún problema (para el número de la barra de Contenido)."""
    ahora = ahora or timezone.now()
    campos = ('activa', 'retirada', 'oculta_hasta', 'estado', 'historial', 'anduvo', 'falla_desde', 'fallas_seguidas',
              'por_que_falla')
    return sum(1 for f in Fuente.objects.filter(canal__eliminado_en__isnull=True).only(*campos)
               if de_fuente(f, ahora) in CON_PROBLEMAS)


# ── Lo que se hace con varias juntas ─────────────────────────────────

def probar(fuentes, verificar, ahora=None):
    """
    "Probar ahora" de varias: el servidor las prueba ya (`verificar`: verificacion.verificar_varias), hasta
    bandeja.FUENTES_PARA_PROBAR y por bandeja.SEGUNDOS_PARA_PROBAR. Las retiradas que andan vuelven a la app.
    Devuelve (cuántas andan, cuántas probó).
    """
    ahora = ahora or timezone.now()
    fuentes = list(fuentes[:FUENTES_PARA_PROBAR])
    resultados = verificar({f.url: f.tipo for f in fuentes},
                           cabeceras={f.url: (f.user_agent, f.referer) for f in fuentes if f.user_agent or f.referer},
                           hasta=time.monotonic() + SEGUNDOS_PARA_PROBAR)
    probadas = []
    for fuente in fuentes:
        if fuente.url in resultados:
            aplicar_resultado(fuente, resultados[fuente.url], ahora)
            probadas.append(fuente)
    Fuente.objects.bulk_update(probadas, CAMPOS_DE_VERIFICACION)
    andan = [f.pk for f in probadas if f.estado == Fuente.Estado.FUNCIONA]
    if andan:
        salud.devolver_senales(ahora, fuentes=andan)
    return len(andan), len(probadas)
