"""
Lo que el sistema HACE con la reventa (capa Base). Todo lo que mueve
créditos pasa por acá: las vistas solo llaman a estas funciones.

Cada operación que gasta o suma créditos bloquea la fila del revendedor
(select_for_update) mientras trabaja: así dos renovaciones al mismo tiempo
no pueden gastar el mismo crédito dos veces.

Los permisos (quién puede hacer qué) los chequean las vistas, no estas
funciones.
"""

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Max, Q
from django.urls import reverse
from django.utils import timezone

from actividad.models import Accion
from actividad.registro import registrar
from notificaciones.models import Nivel
from notificaciones.servicios import notificar, notificar_a_quienes_puedan
from usuarios.models import Rol, Usuario

from .models import (ANTICIPO_RENOVACION, DIAS_POR_CREDITO, Cliente, Compra, CreditoCliente, Dispositivo, Movimiento,
                     Pantalla, Renovacion, Revendedor, _codigo_nuevo)


NOMBRE_ROL = 'Revendedor'   # el mismo de usuarios/catalogo_permisos.py (ROLES_INICIALES)


class ReventaError(Exception):
    """Algo que no se puede hacer (sin saldo, compra ya resuelta...). El mensaje es para el usuario."""


def _bloquear(revendedor):
    return Revendedor.todos.select_for_update().get(pk=revendedor.pk)


# ── Revendedores ─────────────────────────────────────────────────────

def hacer_revendedor(usuario, precio_pantalla=0, por=None):
    """Convierte a un usuario del panel en revendedor (o devuelve el que ya era)."""
    revendedor, creado = Revendedor.todos.get_or_create(usuario=usuario, defaults={'precio_pantalla': precio_pantalla})
    if creado:
        registrar(por, Accion.CREAR, f'Hizo revendedor a {revendedor}', objeto=revendedor, modulo='reventa')
    elif revendedor.esta_eliminado:
        revendedor.restaurar(por)
    return revendedor


@transaction.atomic
def crear_revendedor(username, password, first_name='', last_name='', telefono='', precio_pantalla=0, por=None):
    """Alta completa: usuario del panel (con el rol Revendedor) + su perfil de revendedor."""
    rol, _ = Rol.objects.get_or_create(nombre=NOMBRE_ROL, defaults={
        'descripcion': 'Vende el servicio: gestiona sus clientes, sus créditos y sus compras.', 'permisos': []})
    usuario = Usuario.objects.create_user(
        username, None, password, first_name=first_name, last_name=last_name, telefono=telefono, rol=rol,
        debe_cambiar_password=True, creado_por=por if getattr(por, 'is_authenticated', False) else None,
    )
    return hacer_revendedor(usuario, precio_pantalla, por)


# ── Créditos ─────────────────────────────────────────────────────────

@transaction.atomic
def regalar_creditos(revendedor, cantidad, por=None, detalle=''):
    """Créditos gratis (los da el administrador)."""
    if cantidad <= 0:
        raise ReventaError('La cantidad tiene que ser mayor a 0.')
    _bloquear(revendedor)
    movimiento = Movimiento.objects.create(revendedor=revendedor, cantidad=cantidad, tipo=Movimiento.Tipo.REGALO,
                                           detalle=detalle[:200], hecho_por=por)
    registrar(por, Accion.CREAR, f'Regaló {cantidad} crédito(s) a {revendedor}', objeto=revendedor, modulo='reventa')
    return movimiento


@transaction.atomic
def ajustar_creditos(revendedor, cantidad, por=None, detalle=''):
    """Corrección del administrador (+ o −). El saldo nunca puede quedar negativo."""
    if cantidad == 0:
        raise ReventaError('La cantidad no puede ser 0.')
    if not detalle.strip():
        raise ReventaError('Explicá el motivo del ajuste.')
    revendedor = _bloquear(revendedor)
    if revendedor.saldo + cantidad < 0:
        raise ReventaError(f'El saldo quedaría negativo (tiene {revendedor.saldo}).')
    movimiento = Movimiento.objects.create(revendedor=revendedor, cantidad=cantidad, tipo=Movimiento.Tipo.AJUSTE,
                                           detalle=detalle[:200], hecho_por=por)
    registrar(por, Accion.EDITAR, f'Ajustó {cantidad:+d} crédito(s) a {revendedor}: {detalle}', objeto=revendedor,
              modulo='reventa')
    return movimiento


# ── Compras de paquetes ──────────────────────────────────────────────

def pedir_compra(revendedor, paquete, por=None):
    """El revendedor pide un paquete: queda pendiente hasta que se confirme el pago."""
    if not paquete.activo or paquete.esta_eliminado:
        raise ReventaError('Ese paquete ya no está disponible.')
    compra = Compra.objects.create(revendedor=revendedor, paquete=paquete, creditos=paquete.creditos,
                                   precio=paquete.precio, pedida_por=por)
    registrar(por, Accion.CREAR, f'Pidió el paquete "{paquete.nombre}" para {revendedor}', objeto=compra,
              modulo='reventa')
    # La campanita de quienes confirman pagos (no se avisa a sí mismo si la cargó el administrador)
    notificar_a_quienes_puedan('confirmar_compras', f'{revendedor} pidió {compra.creditos} créditos',
                               f'Paquete "{paquete.nombre}" por $ {compra.precio}. Confirmá el pago cuando lo recibas.',
                               url=reverse('reventa:compras'), nivel=Nivel.AVISO, excepto=por)
    return compra


@transaction.atomic
def confirmar_compra(compra, por=None):
    """Se cobró: la compra pasa a pagada y se suman los créditos."""
    compra = Compra.objects.select_for_update().get(pk=compra.pk)
    if compra.estado != Compra.Estado.PENDIENTE:
        raise ReventaError(f'La compra ya está {compra.get_estado_display().lower()}.')
    _bloquear(compra.revendedor)
    compra.estado, compra.resuelta, compra.resuelta_por = Compra.Estado.PAGADA, timezone.now(), por
    compra.save(update_fields=['estado', 'resuelta', 'resuelta_por'])
    Movimiento.objects.create(revendedor=compra.revendedor, cantidad=compra.creditos, tipo=Movimiento.Tipo.COMPRA,
                              detalle=f'Paquete "{compra.paquete.nombre if compra.paquete else "—"}"', compra=compra,
                              hecho_por=por)
    registrar(por, Accion.EDITAR, f'Confirmó el pago de {compra}', objeto=compra, modulo='reventa')
    notificar(compra.revendedor.usuario, f'Ya tenés tus {compra.creditos} créditos',
              'Se confirmó el pago de tu compra. Ya podés usarlos para activar y renovar clientes.',
              url=reverse('reventa:creditos'), nivel=Nivel.EXITO, excepto=por)
    return compra


@transaction.atomic
def cancelar_compra(compra, por=None):
    compra = Compra.objects.select_for_update().get(pk=compra.pk)
    if compra.estado != Compra.Estado.PENDIENTE:
        raise ReventaError(f'La compra ya está {compra.get_estado_display().lower()}.')
    compra.estado, compra.resuelta, compra.resuelta_por = Compra.Estado.CANCELADA, timezone.now(), por
    compra.save(update_fields=['estado', 'resuelta', 'resuelta_por'])
    registrar(por, Accion.EDITAR, f'Canceló la compra {compra}', objeto=compra, modulo='reventa')
    return compra


@transaction.atomic
def registrar_compra_pagada(revendedor, paquete, por=None):
    """El administrador carga una compra que ya cobró (sin pasar por 'pendiente')."""
    return confirmar_compra(pedir_compra(revendedor, paquete, por), por)


# ── Clientes ─────────────────────────────────────────────────────────

MAXIMO_PANTALLAS = 20
MAXIMO_MESES = 24


def _usuario(por):
    return por if getattr(por, 'is_authenticated', False) else None


def _bloquear_cliente(cliente):
    return Cliente.objects.select_for_update().get(pk=cliente.pk)


def _local(momento):
    return f'{timezone.localtime(momento):%d/%m/%Y}'


def crear_cliente(revendedor, nombre, telefono='', notas='', por=None):
    """
    Lo crea SIN activar: no gasta créditos. Cuántas pantallas tiene y por
    cuántos meses se elige al activarlo.
    revendedor=None -> cliente directo de la empresa (solo para el administrador).
    """
    cliente = Cliente(revendedor=revendedor, nombre=nombre, telefono=telefono, notas=notas)
    cliente.marcar_autor(por)
    cliente.save()
    de_quien = f'de {revendedor}' if revendedor else '(directo)'
    registrar(por, Accion.CREAR, f'Creó el cliente {cliente} {de_quien}', objeto=cliente, modulo='reventa')
    return cliente


def precio_sugerido(cliente, creditos=1):
    """Lo que se propone cobrar: el precio por pantalla por mes del revendedor × créditos."""
    precio = cliente.revendedor.precio_pantalla if cliente.revendedor_id else 0
    return precio * creditos


@transaction.atomic
def pantalla_propia(revendedor, por=None):
    """
    El cliente con el que el revendedor mira la app ("Mi pantalla"). Los
    revendedores no ven gratis con su usuario del panel: se activan a sí
    mismos con sus créditos, como a cualquier cliente, y entran con ese
    código. Se crea la primera vez (sin activar: no gasta créditos).
    """
    with transaction.atomic():
        Revendedor.objects.select_for_update().get(pk=revendedor.pk)   # que no se creen dos a la vez
        cliente = revendedor.clientes.filter(propio=True).first()
        if cliente is None:
            cliente = crear_cliente(revendedor, f'{revendedor} (mi pantalla)'[:150],
                                    notas='Tu propia pantalla: activala con tus créditos para ver la app.', por=por)
            cliente.propio = True
            cliente.save(update_fields=['propio'])
    return cliente


@transaction.atomic
def cargar_creditos(cliente, creditos, monto_cobrado=None, cortesia=False, de_la_empresa=False, detalle='',
                    por=None):
    """
    Le carga créditos al saldo del cliente (meses pagados por adelantado).
    Salen de la libreta de su revendedor; si es un cliente directo, o el
    administrador elige `de_la_empresa`, los pone la empresa (no los paga
    ningún revendedor). `cortesia`: es un regalo, no se le cobró nada.
    Lo cargado no vuelve al revendedor aunque el cliente no lo use.
    """
    if creditos < 1:
        raise ReventaError('Tiene que ser al menos 1 crédito.')
    cliente = _bloquear_cliente(cliente)
    revendedor = None if de_la_empresa or not cliente.revendedor_id else _bloquear(cliente.revendedor)
    if revendedor and revendedor.saldo < creditos:
        raise ReventaError(f'No alcanzan los créditos: hacen falta {creditos} y quedan {revendedor.saldo}.')
    if cortesia:
        monto = Decimal(0)
    else:
        monto = Decimal(precio_sugerido(cliente, creditos) if monto_cobrado is None else monto_cobrado)
    if monto < 0:
        raise ReventaError('El monto cobrado no puede ser negativo.')
    movimiento = None
    if revendedor:
        movimiento = Movimiento.objects.create(
            revendedor=revendedor, cantidad=-creditos, tipo=Movimiento.Tipo.RENOVACION,
            detalle=f'{cliente.nombre}: {detalle or f"{creditos} crédito(s)"}'[:200], hecho_por=_usuario(por))
    carga = CreditoCliente.objects.create(
        cliente=cliente, cantidad=creditos, tipo=CreditoCliente.Tipo.CARGA, detalle=detalle[:200],
        revendedor=revendedor, movimiento=movimiento, cortesia=cortesia, monto_cobrado=monto, hecho_por=_usuario(por))
    origen = f'de {revendedor}' if revendedor else 'de la empresa'
    registrar(por, Accion.EDITAR, f'Cargó {creditos} crédito(s) {origen} a {cliente}'
                                  f'{" (cortesía)" if cortesia else ""}', objeto=cliente, modulo='reventa')
    return carga


def _numero_libre(cliente):
    return (cliente.pantallas.aggregate(ultimo=Max('numero'))['ultimo'] or 0) + 1


def _dejar_pantallas(cliente, cantidad):
    """Deja al cliente con `cantidad` pantallas: agrega al final o quita las últimas (con sus aparatos)."""
    actuales = list(cliente.pantallas.order_by('numero'))
    for sobrante in actuales[cantidad:]:
        sobrante.delete()
    for _ in range(cantidad - len(actuales)):
        Pantalla.objects.create(cliente=cliente, numero=_numero_libre(cliente))


def _empezar_mes(cliente, desde, por=None):
    """Un mes de servicio para todas sus pantallas: gasta 1 crédito de su saldo por cada una."""
    cantidad = cliente.pantallas.count()
    hasta = desde + timedelta(days=DIAS_POR_CREDITO)
    renovacion = Renovacion.objects.create(cliente=cliente, pantallas=cantidad, creditos=cantidad, desde=desde,
                                           hasta=hasta, hecha_por=_usuario(por))
    CreditoCliente.objects.create(cliente=cliente, cantidad=-cantidad, tipo=CreditoCliente.Tipo.MES,
                                  detalle=f'{cantidad} pantalla(s) hasta el {_local(hasta)}', renovacion=renovacion)
    cliente.vence = hasta
    cliente.save(update_fields=['vence'])
    return renovacion


@transaction.atomic
def activar(cliente, dispositivos=1, meses=1, monto_cobrado=None, cortesia=False, de_la_empresa=False, por=None):
    """
    Activa al cliente (nuevo, o vencido) con `dispositivos` pantallas,
    pagando `meses` meses: le carga dispositivos × meses créditos y empieza
    el primer mes ahora. Los demás se descuentan solos, uno por mes
    (renovar_si_toca). Si ya está activo, se usa cargar_meses o agregar_pantalla.
    """
    if not 1 <= dispositivos <= MAXIMO_PANTALLAS:
        raise ReventaError(f'Tienen que ser entre 1 y {MAXIMO_PANTALLAS} pantallas.')
    if not 1 <= meses <= MAXIMO_MESES:
        raise ReventaError(f'Tienen que ser entre 1 y {MAXIMO_MESES} meses.')
    cliente = _bloquear_cliente(cliente)
    if cliente.suspendido:
        raise ReventaError(f'{cliente} está suspendido: primero sacale la suspensión (Editar).')
    if cliente.vigente:
        raise ReventaError(f'{cliente} ya está activo hasta el {_local(cliente.vence)}. Para pagar más meses usá '
                           '"Cargar meses"; para otro aparato, "Agregar pantalla".')
    cargar_creditos(cliente, dispositivos * meses, monto_cobrado, cortesia, de_la_empresa,
                    detalle=f'{dispositivos} pantalla(s) × {meses} mes(es)', por=por)
    _dejar_pantallas(cliente, dispositivos)
    renovacion = _empezar_mes(cliente, timezone.now(), por)
    registrar(por, Accion.EDITAR, f'Activó a {cliente} con {dispositivos} pantalla(s) hasta el '
                                  f'{_local(renovacion.hasta)}', objeto=cliente, modulo='reventa')
    return renovacion


@transaction.atomic
def cargar_meses(cliente, meses=1, monto_cobrado=None, cortesia=False, de_la_empresa=False, por=None):
    """
    Paga más meses de las pantallas que ya tiene: carga pantallas × meses
    créditos a su saldo. Si ya se le había terminado el mes, empieza otro ahora.
    """
    if not 1 <= meses <= MAXIMO_MESES:
        raise ReventaError(f'Tienen que ser entre 1 y {MAXIMO_MESES} meses.')
    cantidad = cliente.pantallas.count()
    if not cantidad:
        raise ReventaError(f'{cliente} todavía no tiene pantallas: activalo primero.')
    carga = cargar_creditos(cliente, cantidad * meses, monto_cobrado, cortesia, de_la_empresa,
                            detalle=f'{cantidad} pantalla(s) × {meses} mes(es)', por=por)
    renovar_si_toca(Cliente.objects.get(pk=cliente.pk))
    return carga


def renovar(cliente, dispositivos=1, monto_cobrado=None, por=None):
    """Un mes más: activa con `dispositivos` pantallas si no está activo; si lo está, carga un mes de las que tiene."""
    cliente = Cliente.objects.get(pk=cliente.pk)
    if cliente.vigente:
        return cargar_meses(cliente, 1, monto_cobrado, por=por)
    return activar(cliente, dispositivos, 1, monto_cobrado, por=por)


def renovar_si_toca(cliente, ahora=None):
    """
    Si al cliente le termina el mes (faltan menos de ANTICIPO_RENOVACION) o
    ya le terminó, y su saldo alcanza para todas sus pantallas, empieza el
    mes siguiente: pegado al anterior o, si ya había vencido, desde ahora.
    Devuelve la Renovacion (None si no tocaba o no alcanzaba).
    """
    ahora = ahora or timezone.now()
    if cliente.suspendido or cliente.vence is None or cliente.vence - ahora > ANTICIPO_RENOVACION:
        return None
    with transaction.atomic():
        cliente = _bloquear_cliente(cliente)
        if cliente.vence - ahora > ANTICIPO_RENOVACION:
            return None   # otro pedido lo renovó recién
        cantidad = cliente.pantallas.count()
        if not cantidad or cliente.saldo < cantidad:
            return None
        return _empezar_mes(cliente, max(cliente.vence, ahora))


def renovar_los_que_tocan():
    """
    La tarea diaria (limpiar_registros): empieza el mes de los clientes a
    los que se les termina y les alcanza el saldo. A los que no les alcanza
    y vencen dentro de un día, les avisa a su revendedor (o a quienes
    administran la reventa, si es directo). Devuelve (renovados, sin_saldo).
    """
    ahora = timezone.now()
    renovados, sin_saldo = 0, 0
    for cliente in Cliente.objects.filter(suspendido=False, vence__isnull=False,
                                          vence__lte=ahora + ANTICIPO_RENOVACION).select_related('revendedor__usuario'):
        if renovar_si_toca(cliente, ahora):
            renovados += 1
        elif cliente.vence > ahora and cliente.vence - ahora <= timedelta(days=1) and cliente.pantallas.exists():
            sin_saldo += 1
            titulo = f'A {cliente} no le alcanza el saldo'
            texto = f'Vence el {_local(cliente.vence)}: cargale meses para que siga viendo.'
            url = reverse('reventa:cliente', args=[cliente.pk])
            if cliente.revendedor_id:
                notificar(cliente.revendedor.usuario, titulo, texto, url=url, nivel=Nivel.AVISO)
            else:
                notificar_a_quienes_puedan('administrar_reventa', titulo, texto, url=url, nivel=Nivel.AVISO)
    return renovados, sin_saldo


# ── Pantallas del cliente ────────────────────────────────────────────

@transaction.atomic
def agregar_pantalla(cliente, monto_cobrado=None, cortesia=False, de_la_empresa=False, por=None):
    """
    Un aparato más a mitad de mes: cuesta 1 crédito y dura hasta que vence
    el resto; desde el mes siguiente se renueva con las demás.
    """
    cliente = _bloquear_cliente(cliente)
    if not cliente.vigente:
        raise ReventaError(f'{cliente} no está activo: activalo con las pantallas que quiera.')
    if cliente.pantallas.count() >= MAXIMO_PANTALLAS:
        raise ReventaError(f'Ya tiene {MAXIMO_PANTALLAS} pantallas, el máximo.')
    cargar_creditos(cliente, 1, monto_cobrado, cortesia, de_la_empresa,
                    detalle=f'Pantalla agregada hasta el {_local(cliente.vence)}', por=por)
    pantalla = Pantalla.objects.create(cliente=cliente, numero=_numero_libre(cliente))
    renovacion = Renovacion.objects.create(cliente=cliente, pantallas=1, creditos=1, desde=timezone.now(),
                                           hasta=cliente.vence, hecha_por=_usuario(por))
    CreditoCliente.objects.create(cliente=cliente, cantidad=-1, tipo=CreditoCliente.Tipo.MES,
                                  detalle=f'Pantalla {pantalla.numero} hasta el {_local(cliente.vence)}',
                                  renovacion=renovacion)
    registrar(por, Accion.EDITAR, f'Agregó la pantalla {pantalla.numero} a {cliente}', objeto=cliente,
              modulo='reventa')
    return pantalla


@transaction.atomic
def quitar_pantalla(pantalla, por=None):
    """
    La saca (sin devolución): su aparato se desconecta y desde el mes
    siguiente se paga una menos. Las demás se vuelven a numerar.
    """
    cliente = _bloquear_cliente(pantalla.cliente)
    if cliente.pantallas.count() <= 1:
        raise ReventaError('Tiene que quedar al menos una pantalla. Para cortarle todo, suspendé al cliente.')
    numero = pantalla.numero
    pantalla.delete()
    for siguiente in cliente.pantallas.filter(numero__gt=numero).order_by('numero'):
        siguiente.numero -= 1
        siguiente.save(update_fields=['numero'])
    registrar(por, Accion.EDITAR, f'Quitó la pantalla {numero} de {cliente}', objeto=cliente, modulo='reventa')


@transaction.atomic
def cortar_pantalla(pantalla, cortada=True, por=None):
    """
    Corta (o vuelve a habilitar) una sola pantalla: su aparato se desconecta
    y su código deja de servir. Se sigue pagando (es un castigo, no una baja).
    """
    pantalla.cortada = cortada
    pantalla.save(update_fields=['cortada'])
    if cortada:
        Dispositivo.objects.filter(pantalla=pantalla).delete()
    registrar(por, Accion.SEGURIDAD, f'{"Cortó" if cortada else "Volvió a habilitar"} {pantalla}',
              objeto=pantalla.cliente, modulo='reventa')
    return pantalla


def editar_pantalla(pantalla, nombre='', titular='', por=None):
    pantalla.nombre, pantalla.titular = nombre.strip()[:60], titular.strip()[:100]
    pantalla.save(update_fields=['nombre', 'titular'])
    registrar(por, Accion.EDITAR, f'Editó {pantalla}', objeto=pantalla.cliente, modulo='reventa')
    return pantalla


@transaction.atomic
def codigo_de_pantalla(pantalla, propio=True, por=None):
    """
    Le da a la pantalla su propio código (o uno nuevo, si ya tenía: el
    aparato que la usa se desconecta), o se lo saca (`propio=False`: vuelve a
    entrarse con el código del cliente).
    """
    if propio:
        pantalla.codigo = _codigo_nuevo()
        Dispositivo.objects.filter(pantalla=pantalla).delete()
    else:
        pantalla.codigo = None
    pantalla.save(update_fields=['codigo'])
    registrar(por, Accion.SEGURIDAD, f'{"Dio un código propio a" if propio else "Sacó el código propio de"} '
                                     f'{pantalla}', objeto=pantalla.cliente, modulo='reventa')
    return pantalla


def pasar_a_revendedor(cliente, revendedor, por=None):
    """
    El cliente pasa a ser de `revendedor` (None = directo de la empresa). Su
    saldo se queda con él (ya está pagado); desde ahí, sus cargas salen de ese revendedor.
    """
    anterior = cliente.revendedor
    cliente.revendedor = revendedor
    cliente.marcar_autor(por)
    cliente.save(update_fields=['revendedor', 'modificado', 'modificado_por'])
    registrar(por, Accion.EDITAR, f'Pasó a {cliente} de {anterior or "la empresa"} a {revendedor or "la empresa"}',
              objeto=cliente, modulo='reventa')
    return cliente


@transaction.atomic
def regenerar_codigo(cliente, por=None):
    """
    Código de acceso nuevo (si el anterior se filtró). Desconecta los aparatos
    que entraron con él (los de pantallas con código propio siguen).
    """
    cliente.codigo = _codigo_nuevo()
    cliente.marcar_autor(por)
    cliente.save(update_fields=['codigo', 'modificado', 'modificado_por'])
    cliente.dispositivos.filter(Q(pantalla__isnull=True) | Q(pantalla__codigo__isnull=True)).delete()
    registrar(por, Accion.SEGURIDAD, f'Generó un código de acceso nuevo para {cliente}', objeto=cliente,
              modulo='reventa')
    return cliente


def liberar_dispositivos(cliente, dispositivo_id=None, por=None):
    """
    Desconecta un dispositivo (o todos): esa pantalla queda libre para otro
    aparato. El desconectado vuelve a la pantalla del código en la app.
    """
    dispositivos = cliente.dispositivos.all()
    if dispositivo_id is not None:
        dispositivos = dispositivos.filter(pk=dispositivo_id)
    cantidad, _ = dispositivos.delete()
    if cantidad:
        registrar(por, Accion.SEGURIDAD, f'Liberó {cantidad} dispositivo(s) de {cliente}', objeto=cliente,
                  modulo='reventa')
    return cantidad
