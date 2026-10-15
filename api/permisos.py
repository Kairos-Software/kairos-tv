"""
Quién puede usar la API.

- `SistemaDisponible` se aplica a TODAS las vistas (ver REST_FRAMEWORK en
  settings): si el sistema está en mantenimiento solo deja pasar a los
  superusuarios, y si el usuario tiene que cambiar la contraseña solo lo
  deja ver su perfil, cambiarla y cerrar sesión. Es lo mismo que hacen los
  middlewares en la web.
- `exigir_permiso()` chequea los permisos del catálogo, con la misma lógica
  que la web (usuarios/permisos.py).
"""

from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission

from core.mantenimiento import estado_actual
from reventa import sesiones
from usuarios.permisos import tiene_algun_permiso

from .errores import ErrorApi

# Lo único que puede usar un CLIENTE (login con código): ver canales (pedir
# la dirección real de los de Twitch, Dailymotion..., avisar si uno falla o
# cuánto se miró), su biblioteca (favoritos, "Continuar viendo"), su estado y
# cerrar sesión. Todo lo demás es de los usuarios del panel.
VISTAS_DE_CLIENTES = {'api_v1:canales', 'api_v1:canales_secciones', 'api_v1:fuente_resolver', 'api_v1:fuente_falla',
                      'api_v1:canales_visto', 'api_v1:biblioteca', 'api_v1:cliente', 'api_v1:cliente_logout'}

# Las vistas para MIRAR (los canales). Un revendedor no las usa con su usuario
# del panel: mira con su propia pantalla, un cliente que activa con sus
# créditos (reventa.servicios.pantalla_propia). El administrador sí, para probar.
VISTAS_PARA_MIRAR = {'api_v1:canales', 'api_v1:canales_secciones', 'api_v1:fuente_falla', 'api_v1:fuente_resolver',
                     'api_v1:canales_visto', 'api_v1:biblioteca'}
MENSAJE_REVENDEDOR = ('Para ver la app usá tu propia pantalla: en el panel, entrá a Reventa → "Mi pantalla", '
                      'activala con tus créditos y entrá a la app con ese código.')

# Lo único que puede hacer quien tiene que cambiar la contraseña
VISTAS_CON_PASSWORD_PENDIENTE = {'api_v1:perfil', 'api_v1:cambiar_password', 'api_v1:logout'}


def error_mantenimiento(estado):
    return ErrorApi(
        estado['mensaje'] or 'Estamos actualizando el sistema. Volvé a intentar en unos minutos.',
        'mantenimiento', status.HTTP_503_SERVICE_UNAVAILABLE,
        extra={'vuelve': estado['vuelve_aprox']},
    )


class SistemaDisponible(BasePermission):

    def has_permission(self, request, view):
        usuario = request.user
        if not usuario.is_superuser:
            estado = estado_actual()
            if estado['activo']:
                raise error_mantenimiento(estado)

        if getattr(usuario, 'es_cliente_app', False):
            self._chequear_cliente(request, usuario.cliente)
        elif usuario.is_authenticated and self._es_revendedor_mirando(request, usuario):
            raise ErrorApi(MENSAJE_REVENDEDOR, 'revendedor_sin_pantalla', status.HTTP_403_FORBIDDEN)

        if usuario.is_authenticated and usuario.debe_cambiar_password:
            vista = request.resolver_match.view_name if request.resolver_match else ''
            if vista not in VISTAS_CON_PASSWORD_PENDIENTE:
                raise ErrorApi('Tenés que cambiar tu contraseña antes de seguir.', 'debe_cambiar_password',
                               status.HTTP_403_FORBIDDEN)
        return True


    @staticmethod
    def _es_revendedor_mirando(request, usuario):
        """Un revendedor (que no es administrador) pidiendo los canales con su usuario del panel."""
        vista = request.resolver_match.view_name if request.resolver_match else ''
        if vista not in VISTAS_PARA_MIRAR or tiene_algun_permiso(usuario, 'administrar_reventa'):
            return False
        from reventa.models import Revendedor
        return Revendedor.objects.filter(usuario=usuario).exists()

    @staticmethod
    def _chequear_cliente(request, cliente):
        vista = request.resolver_match.view_name if request.resolver_match else ''
        if vista not in VISTAS_DE_CLIENTES:
            raise PermissionDenied()
        if vista == 'api_v1:cliente_logout':
            return   # cerrar sesión se puede siempre
        try:
            sesiones.chequear_vigente(cliente)
        except sesiones.AccesoDenegado as error:
            raise ErrorApi(str(error), error.codigo, status.HTTP_403_FORBIDDEN, extra=error.extra)


def exigir_permiso(usuario, *codigos):
    """Corta con 403 si `usuario` no tiene ninguno de los permisos `codigos`."""
    if not tiene_algun_permiso(usuario, *codigos):
        raise PermissionDenied()
