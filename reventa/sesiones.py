"""
Sesiones de la app de los CLIENTES (capa Base): entrar con el código y
controlar que no haya más aparatos conectados que pantallas pagadas.

Cómo funciona:
  1. El cliente pone un código de 8 números en la app: el SUYO (entra a
     cualquier pantalla libre que no tenga código propio) o el PROPIO de una
     pantalla (entra solo a esa).
  2. Si está vigente y hay pantalla libre (y no cortada), se crea un
     Dispositivo en ella y se le entrega un token (empieza con "c_" para
     distinguirlo de los tokens de los usuarios del panel).
  3. La app manda el token en cada pedido y, mientras está abierta, da una
     "señal" cada pocos minutos (GET /api/v1/cliente/).
  4. Si un dispositivo no da señales en HORAS_SIN_SENAL, su pantalla se
     libera sola. El revendedor también puede liberarla a mano.

Si ya están todas las pantallas ocupadas, el dispositivo NUEVO se bloquea
("cuenta en uso"): el que está mirando no se corta.
"""

import hashlib
import secrets
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from actividad.models import Accion
from actividad.registro import registrar

from . import servicios
from .models import HORAS_SIN_SENAL, Cliente, Dispositivo, Pantalla

PREFIJO = 'c_'
# Cada cuánto se guarda la señal (no en cada pedido: ahorra escrituras).
# Tiene que ser bastante menor que lo que tarda la app entre señales.
INTERVALO_GUARDAR_SENAL = timedelta(minutes=1)


class AccesoDenegado(Exception):
    """No puede entrar. `codigo` es para la app; el mensaje, para mostrarle a la persona."""

    def __init__(self, mensaje, codigo, extra=None):
        super().__init__(mensaje)
        self.codigo = codigo
        self.extra = extra or {}


class ClienteApp:
    """
    Hace de `request.user` cuando quien pide es un cliente (no un usuario del
    panel). Tiene lo mínimo que miran DRF y los permisos de la API.
    """

    is_authenticated = True
    is_anonymous = False
    is_active = True
    is_superuser = False
    is_staff = False
    debe_cambiar_password = False
    es_cliente_app = True
    pk = id = None

    def __init__(self, dispositivo):
        self.dispositivo = dispositivo
        self.cliente = dispositivo.cliente

    def __str__(self):
        return f'Cliente {self.cliente}'


def _huella(clave):
    return hashlib.sha256(clave.encode()).hexdigest()


def normalizar_codigo(codigo):
    """'4821 9037' / '4821-9037' -> '48219037'."""
    return ''.join(c for c in str(codigo or '') if c.isdigit())


def liberar_inactivos(cliente):
    """Borra los dispositivos que no dieron señales en HORAS_SIN_SENAL. Devuelve cuántos."""
    limite = timezone.now() - timedelta(hours=HORAS_SIN_SENAL)
    cantidad, _ = cliente.dispositivos.filter(ultima_senal__lt=limite).delete()
    return cantidad


def contacto_del_vendedor(cliente):
    """A quién recurrir para renovar: la app lo muestra en "Tu servicio venció" y en "Mi cuenta"."""
    if cliente.revendedor is None:   # cliente directo: no hay revendedor que mostrar
        return {'nombre': '', 'telefono': ''}
    usuario = cliente.revendedor.usuario
    return {'nombre': usuario.get_full_name() or usuario.username, 'telefono': usuario.telefono}


def chequear_vigente(cliente):
    # Si le terminó el mes y tiene saldo, empieza el siguiente (por si la tarea diaria no llegó)
    if servicios.renovar_si_toca(cliente):
        cliente.refresh_from_db(fields=['vence'])
    if cliente.suspendido:
        raise AccesoDenegado('Tu servicio está suspendido. Comunicate con quien te lo vendió.', 'suspendido',
                             {'vendedor': contacto_del_vendedor(cliente)})
    if not cliente.vigente:
        raise AccesoDenegado('Tu servicio venció. Comunicate con quien te lo vendió para renovarlo.',
                             'servicio_vencido', {'vence': cliente.vence, 'vendedor': contacto_del_vendedor(cliente)})


def _del_codigo(codigo):
    """(cliente, pantalla) de un código: el del cliente (pantalla None) o el propio de una pantalla."""
    # select_for_update: dos aparatos entrando a la vez no pueden ocupar la misma pantalla
    cliente = Cliente.objects.select_for_update().filter(codigo=codigo).first()
    if cliente is not None:
        return cliente, None
    pantalla = Pantalla.objects.filter(codigo=codigo).first()
    if pantalla is None:
        return None, None
    cliente = Cliente.objects.select_for_update().filter(pk=pantalla.cliente_id).first()
    return (cliente, pantalla) if cliente else (None, None)


def _pantalla_para_entrar(cliente, pantalla=None):
    """La pantalla que ocupa el aparato que entra, o AccesoDenegado si no hay lugar."""
    if pantalla is not None:   # entró con el código propio de esa pantalla
        if pantalla.cortada:
            raise AccesoDenegado('Esta pantalla está desactivada. Hablá con el titular de la cuenta.',
                                 'pantalla_cortada')
        if Dispositivo.objects.filter(pantalla=pantalla).exists():
            raise AccesoDenegado(
                f'«{pantalla.nombre_visible}» ya se está usando en otro aparato. Cerrá la sesión ahí o pedile '
                'a quien te vendió el servicio que la libere.', 'cuenta_en_uso', {'pantallas': 1})
        return pantalla
    habilitadas = cliente.pantallas.filter(cortada=False, codigo__isnull=True)
    libre = habilitadas.filter(dispositivo__isnull=True).first()
    if libre is not None:
        return libre
    if not habilitadas.exists():
        raise AccesoDenegado('Cada pantalla de esta cuenta tiene su propio código (o está desactivada): '
                             'usá el código de este aparato.', 'cuenta_en_uso', {'pantallas': 0})
    cantidad = habilitadas.count()
    raise AccesoDenegado(
        f'Tu cuenta ya se está usando en {cantidad} dispositivo(s), que es lo que tenés contratado. '
        'Cerrá la sesión en otro aparato o pedile a quien te vendió el servicio que lo libere.',
        'cuenta_en_uso', {'pantallas': cantidad})


@transaction.atomic
def entrar(codigo, nombre_dispositivo=''):
    """Devuelve (clave, dispositivo) o lanza AccesoDenegado. La clave solo existe en este momento."""
    codigo = normalizar_codigo(codigo)
    cliente, pantalla = _del_codigo(codigo) if len(codigo) == 8 else (None, None)
    if cliente is None:
        raise AccesoDenegado('El código no es correcto.', 'codigo_invalido')
    chequear_vigente(cliente)

    liberar_inactivos(cliente)
    pantalla = _pantalla_para_entrar(cliente, pantalla)

    clave = PREFIJO + secrets.token_urlsafe(32)
    dispositivo = Dispositivo.objects.create(cliente=cliente, pantalla=pantalla, clave_hash=_huella(clave),
                                             nombre=(nombre_dispositivo or '')[:100], ultima_senal=timezone.now())
    registrar(None, Accion.INGRESO, f'El cliente {cliente} entró a la app desde {dispositivo.nombre or "un dispositivo"}',
              objeto=cliente, modulo='reventa')
    return clave, dispositivo


def validar(clave):
    """El Dispositivo de esa clave (con su cliente), o None si ya no vale. Actualiza la señal."""
    if not clave or not clave.startswith(PREFIJO):
        return None
    dispositivo = Dispositivo.objects.select_related('cliente').filter(clave_hash=_huella(clave)).first()
    if dispositivo is None or dispositivo.cliente.esta_eliminado:
        return None
    ahora = timezone.now()
    if ahora - dispositivo.ultima_senal > timedelta(hours=HORAS_SIN_SENAL):
        # Estuvo demasiado tiempo sin señal: su pantalla ya pudo quedar libre
        dispositivo.delete()
        return None
    if ahora - dispositivo.ultima_senal > INTERVALO_GUARDAR_SENAL:
        dispositivo.ultima_senal = ahora
        dispositivo.save(update_fields=['ultima_senal'])
    return dispositivo


def salir(dispositivo):
    """Cerrar sesión en la app: libera la pantalla en el momento."""
    dispositivo.delete()


def es_token_de_cliente(clave):
    return bool(clave) and clave.startswith(PREFIJO)
