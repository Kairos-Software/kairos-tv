"""
"PARA REVISAR": la bandeja con SOLO lo que necesita una decisión humana.

Lo normal se arregla solo (salud.py: lo que falla una semana se quita solo,
lo que vuelve a andar vuelve solo). Acá queda lo que el sistema no puede
decidir, agrupado por motivo (GRUPOS) y con LO MÁS VISTO PRIMERO (lo que
miraron los clientes en los últimos DIAS_DE_VISTO días: estadisticas.Visto),
cada caso con su acción ahí mismo:

  - El proveedor los rechaza (cuenta vencida, ocupada o bloqueada);
  - Fallan ahora (todavía no pasó la semana);
  - A veces andan y a veces no (inestables);
  - Algunos aparatos no los pueden leer (formato);
  - Los quitó la limpieza (por si sabés que andan);
  - Señales retiradas: el canal anda, pero la limpieza le retiró las que no
    andaban (por si querés devolverlas o borrarlas para siempre).

"Dejar así" (Canal.revisado) lo saca de la bandeja mientras siga en ese
estado; si cambia, vuelve a aparecer. En Series cada caso es una SERIE (sus
capítulos en ese estado), no capítulo por capítulo.

Además, el resumen POR LISTA DE ORIGEN (listas): cuánto de cada lista anda y
cuánto está caído, para decidir de una sobre la lista entera (apagar todas
sus fuentes: los canales que tienen otra fuente buena siguen andando).
"""

import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import timedelta

from django.db.models import Prefetch, Sum
from django.utils import timezone

from actividad.models import Accion
from actividad.registro import registrar

from . import clasificar, salud
from .models import Canal, Contenido, Fuente, Visto
from .salud import Salud
from .servicios import CAMPOS_DE_VERIFICACION, aplicar_resultado

# Lo visto de estos últimos días ordena la bandeja (lo más visto primero)
DIAS_DE_VISTO = 30
# Cuántos casos se muestran por grupo (el resto, con "Ver todos")
CASOS_POR_GRUPO = 10
# Una lista "casi toda caída": de sus fuentes prendidas, al menos esta parte falla o está muerta
PARTE_CAIDA_PARA_AVISAR = .5
MINIMO_DE_FUENTES_PARA_AVISAR = 10


@dataclass
class Grupo:
    clave: str
    estado: Salud | None   # None: los quitados por la limpieza
    titulo: str
    explicacion: str
    acciones: tuple
    casos: list = field(default_factory=list)

    @property
    def cantidad(self):
        return len(self.casos)


def _grupos():
    return [
        Grupo('rechaza', Salud.RECHAZA, 'El proveedor los rechaza',
              'La cuenta de la lista está vencida, ocupada o bloqueada. Si la lista es tuya, revisá la cuenta; si '
              'no, conviene quitarlos.', ('quitar', 'dejar')),
        Grupo('falla', Salud.FALLA, 'Fallan ahora',
              'Ninguna de sus fuentes anda en este momento. Si siguen así una semana se quitan solos: podés '
              'esperar, probarlos de nuevo ya o quitarlos.', ('probar', 'quitar', 'dejar')),
        Grupo('inestable', Salud.INESTABLE, 'A veces andan y a veces no',
              'Se cortan seguido o fallan en algunas horas (hora pico, proveedor saturado). Si tienen buena '
              'audiencia, conviene buscarles otra fuente.', ('quitar', 'dejar')),
        Grupo('formato', Salud.FORMATO, 'Algunos aparatos no los pueden leer',
              'La señal anda, pero en algunos celulares o TV no se ve (el formato del video). Si el canal tiene '
              'otra fuente buena, no pasa nada.', ('dejar', 'quitar')),
        Grupo('quitados', None, 'Los quitó la limpieza',
              f'Ninguna fuente anduvo en {salud.DIAS_PARA_QUITAR} días. Vuelven solos si alguna vuelve a andar; '
              f'si sabés que andan, mostralos.', ('mostrar',)),
        Grupo('senales', None, 'Señales retiradas (el canal sigue andando)',
              f'Estas señales no anduvieron en {salud.DIAS_PARA_QUITAR} días y se retiraron solas: la app ya no las '
              f'usa y el canal se ve con las otras. Si vuelven a andar, vuelven solas. Si no las querés más, '
              f'borralas (el canal y sus otras señales quedan).', ('mostrar', 'borrar_retiradas')),
    ]


@dataclass
class Caso:
    nombre: str
    logo: str
    categoria: str
    pks: list
    visto: int = 0           # segundos mirados en los últimos DIAS_DE_VISTO días
    detalle: str = ''        # cómo está su mejor fuente (salud.texto_de_fuente) o por qué se quitó
    origenes: list = field(default_factory=list)
    buscar: str = ''         # para abrirlo en Organizar contenido

    @property
    def minutos(self):
        return self.visto // 60


def _visto_por_canal(contenido, ahora):
    desde = timezone.localdate(ahora) - timedelta(days=DIAS_DE_VISTO)
    return dict(Visto.objects.filter(fecha__gte=desde, canal__contenido=contenido).values('canal')
                .annotate(segundos=Sum('segundos')).values_list('canal', 'segundos'))


def _mejor(fuentes, ahora):
    prendidas = [f for f in fuentes if f.activa] or list(fuentes)
    return min(prendidas, key=lambda f: list(Salud).index(salud.de_fuente(f, ahora))) if prendidas else None


def armar(contenido=Contenido.VIVO, ahora=None):
    """
    La bandeja de una sección: (grupos con sus casos, lo más visto primero;
    cuántos canales hay en cada estado). Lo que se dejó así y cambió de
    estado se vuelve a mostrar (se le borra el "dejado así").
    """
    ahora = ahora or timezone.now()
    grupos = _grupos()
    por_estado = {g.estado: g for g in grupos if g.estado}
    por_clave = {g.clave: g for g in grupos}
    quitados, con_retiradas = por_clave['quitados'], por_clave['senales']
    cuentas = Counter()
    vistos = _visto_por_canal(contenido, ahora)
    canales = (Canal.objects.filter(contenido=contenido).select_related('categoria')
               .prefetch_related(Prefetch('fuentes', to_attr='todas')))
    series = {}   # en Series, un caso por serie y estado
    cambiaron = []
    for canal in canales:
        if not canal.activo:
            if canal.motivo_quitado.startswith(salud.QUITADO_POR_LA_LIMPIEZA):
                grupo, estado = quitados, None
            else:
                continue
        else:
            retiradas = [f for f in canal.todas if f.retirada and not f.activa]
            if retiradas:
                _agregar_retiradas(con_retiradas, canal, retiradas, vistos, contenido, series)
            estado = salud.de_canal(canal.todas, ahora)
            if estado is None:
                continue
            cuentas[estado] += 1
            if canal.revisado and canal.revisado != estado:
                cambiaron.append(canal.pk)
            elif canal.revisado == estado:
                continue
            grupo = por_estado.get(estado)
            if grupo is None:
                continue
        mejor = _mejor(canal.todas, ahora)
        detalle = canal.motivo_quitado if estado is None else (salud.texto_de_fuente(mejor, ahora) if mejor else '')
        origenes = sorted({f.origen or 'No se sabe' for f in canal.todas})
        if contenido == Contenido.SERIE:
            nombre = clasificar.episodio(canal.nombre)[0]
            caso = series.get((nombre.lower(), grupo.clave))
            if caso is None:
                caso = series[(nombre.lower(), grupo.clave)] = Caso(
                    nombre, canal.logo, canal.categoria.nombre if canal.categoria else '', [], detalle=detalle,
                    buscar=nombre)
                grupo.casos.append(caso)
            caso.pks.append(canal.pk)
            caso.visto += vistos.get(canal.pk, 0)
            caso.origenes = sorted(set(caso.origenes) | set(origenes))
            caso.logo = caso.logo or canal.logo
            continue
        grupo.casos.append(Caso(canal.nombre, canal.logo, canal.categoria.nombre if canal.categoria else '',
                                [canal.pk], vistos.get(canal.pk, 0), detalle, origenes, canal.nombre))
    if cambiaron:
        Canal.objects.filter(pk__in=cambiaron).update(revisado='')
    for grupo in grupos:
        if contenido == Contenido.SERIE:
            for caso in grupo.casos:
                caso.nombre = f'{caso.nombre} · {len(caso.pks)} capítulo{"s" if len(caso.pks) != 1 else ""}'
        grupo.casos.sort(key=lambda c: (-c.visto, c.nombre.lower()))
    cuentas[None] = quitados.cantidad
    return grupos, cuentas


def _agregar_retiradas(grupo, canal, retiradas, vistos, contenido, series):
    """Un caso de "Señales retiradas" (en Series, uno por serie)."""
    total = len(canal.todas)
    origenes = sorted({f.origen or 'No se sabe' for f in retiradas})
    if contenido == Contenido.SERIE:
        nombre = clasificar.episodio(canal.nombre)[0]
        caso = series.get((nombre.lower(), grupo.clave))
        if caso is None:
            caso = series[(nombre.lower(), grupo.clave)] = Caso(
                nombre, canal.logo, canal.categoria.nombre if canal.categoria else '', [], buscar=nombre,
                detalle='Algunos capítulos tienen señales retiradas: se ven con las otras.')
            grupo.casos.append(caso)
        caso.pks.append(canal.pk)
        caso.visto += vistos.get(canal.pk, 0)
        caso.origenes = sorted(set(caso.origenes) | set(origenes))
        return
    grupo.casos.append(Caso(
        canal.nombre, canal.logo, canal.categoria.nombre if canal.categoria else '', [canal.pk],
        vistos.get(canal.pk, 0),
        f'Se retiraron {len(retiradas)} de sus {total} señales; se ve con las otras {total - len(retiradas)}.',
        origenes, canal.nombre))


@dataclass
class Lista:
    origen: str
    fuentes: int = 0
    andan: int = 0        # andan, inestables o con problemas de formato en algunos aparatos
    fallan: int = 0       # fallan o las rechaza el proveedor (todavía no pasó la semana)
    muertas: int = 0
    sin_datos: int = 0
    apagadas: int = 0

    @property
    def prendidas(self):
        return self.fuentes - self.apagadas

    @property
    def parte_que_anda(self):
        return round(100 * self.andan / self.prendidas) if self.prendidas else 0

    @property
    def parte_caida(self):
        return round(100 * (self.fallan + self.muertas) / self.prendidas) if self.prendidas else 0

    @property
    def casi_toda_caida(self):
        return (self.prendidas >= MINIMO_DE_FUENTES_PARA_AVISAR
                and (self.fallan + self.muertas) >= PARTE_CAIDA_PARA_AVISAR * self.prendidas)


_ANDAN = (Salud.ANDA, Salud.INESTABLE, Salud.FORMATO)
_FALLAN = (Salud.FALLA, Salud.RECHAZA)


def listas(contenido=Contenido.VIVO, ahora=None):
    """Cada lista de origen de la sección y cómo están sus fuentes: lo más caído primero."""
    ahora = ahora or timezone.now()
    por_origen = {}
    fuentes = Fuente.objects.filter(canal__eliminado_en__isnull=True, canal__contenido=contenido).only(
        'origen', 'activa', 'retirada', 'historial', 'anduvo', 'falla_desde', 'fallas_seguidas', 'por_que_falla')
    for fuente in fuentes:
        lista = por_origen.setdefault(fuente.origen, Lista(fuente.origen))
        lista.fuentes += 1
        if not fuente.activa:
            if fuente.retirada:
                lista.muertas += 1   # la retiró la limpieza: no anduvo en una semana
            else:
                lista.apagadas += 1
            continue
        estado = salud.de_fuente(fuente, ahora)
        if estado in _ANDAN:
            lista.andan += 1
        elif estado in _FALLAN:
            lista.fallan += 1
        elif estado == Salud.MUERTA:
            lista.muertas += 1
        else:
            lista.sin_datos += 1
    return sorted(por_origen.values(), key=lambda l: (-l.casi_toda_caida, -l.parte_caida, l.origen.lower()))


# ── Las acciones de la bandeja (quitar y volver a mostrar son las de siempre: servicios) ──

def dejar_asi(canales, usuario=None, ahora=None):
    """'Dejar así': no vuelven a la bandeja mientras sigan en el estado de ahora. Devuelve cuántos."""
    ahora = ahora or timezone.now()
    cambiados = []
    for canal in canales.prefetch_related('fuentes'):
        estado = salud.de_canal(canal.fuentes.all(), ahora)
        if estado:
            canal.revisado = estado
            cambiados.append(canal)
    Canal.objects.bulk_update(cambiados, ['revisado'])
    if cambiados:
        registrar(usuario, Accion.EDITAR, f'Dejó así {len(cambiados)} canal(es) en Para revisar.', modulo='canales')
    return len(cambiados)


# Para "Probar de nuevo": como mucho estas fuentes y este tiempo (se espera en la página)
FUENTES_PARA_PROBAR = 40
SEGUNDOS_PARA_PROBAR = 25


def probar_de_nuevo(canales, verificar, ahora=None):
    """
    Vuelve a probar YA, desde el servidor, las fuentes prendidas de estos
    canales (`verificar`: verificacion.verificar_varias). Devuelve cuántas
    andan y cuántas probó.
    """
    ahora = ahora or timezone.now()
    fuentes = list(Fuente.objects.filter(canal__in=canales, activa=True).order_by('prioridad', 'pk')
                   [:FUENTES_PARA_PROBAR])
    estados = verificar({f.url: f.tipo for f in fuentes},
                        cabeceras={f.url: (f.user_agent, f.referer) for f in fuentes if f.user_agent or f.referer},
                        hasta=time.monotonic() + SEGUNDOS_PARA_PROBAR)
    probadas = []
    for fuente in fuentes:
        if fuente.url in estados:
            aplicar_resultado(fuente, estados[fuente.url], ahora)
            probadas.append(fuente)
    Fuente.objects.bulk_update(probadas, CAMPOS_DE_VERIFICACION)
    andan = sum(1 for f in probadas if f.estado == Fuente.Estado.FUNCIONA)
    return andan, len(probadas)


def prender_o_apagar_lista(origen, prender, contenido=Contenido.VIVO, usuario=None):
    """
    Apaga (o vuelve a prender) TODAS las fuentes de una lista de origen en una
    sección. Los canales que tienen otra fuente buena siguen andando; los que
    solo tenían esa, dejan de verse. Devuelve cuántas cambiaron.
    """
    fuentes = Fuente.objects.filter(origen=origen, canal__eliminado_en__isnull=True, canal__contenido=contenido,
                                    activa=not prender)
    cantidad = fuentes.update(activa=prender, retirada=None)
    if cantidad:
        registrar(usuario, Accion.EDITAR, f'{"Prendió" if prender else "Apagó"} las {cantidad} fuentes de la lista '
                                          f'«{origen}» (Para revisar).', modulo='canales')
    return cantidad


def borrar_retiradas(canales, usuario=None):
    """
    Borra PARA SIEMPRE las señales que retiró la limpieza de estos canales
    (el canal y sus otras señales quedan). Las direcciones quedan anotadas en
    la actividad, por si hay que volver a ponerlas. Devuelve cuántas borró.
    """
    retiradas = Fuente.objects.filter(canal__in=canales, activa=False, retirada__isnull=False)
    borradas = list(retiradas.values_list('canal__nombre', 'url'))
    if not borradas:
        return 0
    retiradas.delete()
    detalle = '; '.join(f'{nombre}: {url[:150]}' for nombre, url in borradas[:50])
    registrar(usuario, Accion.ELIMINAR, f'Borró {len(borradas)} señal(es) retiradas por la limpieza (Para revisar).',
              cambios={'borradas': detalle}, modulo='canales')
    return len(borradas)
