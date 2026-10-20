"""
La app de los CLIENTES (los que miran la TV): entrar con el código, saber
su estado y cerrar sesión. Ver reventa/sesiones.py para las reglas.

    POST /api/v1/cliente/login/   {"codigo": "4821 9037", "dispositivo": "Smart TV Philips"}
      -> 200 {"token": "c_...", "tipo": "Bearer", "cliente": {...}}
      -> 400 codigo_invalido · 403 servicio_vencido / suspendido · 409 cuenta_en_uso
      -> 429 login_bloqueado (demasiados códigos equivocados desde la misma conexión)

    GET  /api/v1/cliente/          (con el token) -> {"nombre", "codigo", "vence", "demo", "pantallas", "vendedor", ...}
      "demo": true si está en una prueba gratis (entonces "vence" es cuándo termina la prueba).
      "vendedor": {"nombre", "telefono"} de quien le vendió (también viene en el 403 servicio_vencido / suspendido).
      La app lo llama cada pocos minutos: es la "señal" que mantiene ocupada
      la pantalla. Si el servicio venció responde 403; si liberaron el
      dispositivo, 401 (la app vuelve a la pantalla del código).

    POST /api/v1/cliente/logout/   (con el token) -> 204, la pantalla queda libre
"""

from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from core.mantenimiento import estado_actual
from reventa import sesiones
from reventa.models import HORAS_SIN_SENAL
from usuarios.forms import ip_cliente
from usuarios.servicios import limpiar_login_fallidos, login_bloqueado, registrar_login_fallido

from ..autenticacion import TokenBearer, TokenCliente
from ..errores import ErrorApi
from ..formularios import datos_planos
from ..permisos import error_mantenimiento

# Los intentos con código equivocado se cuentan por conexión (IP), con el
# mismo límite que el login del panel: así no se pueden probar códigos al azar.
IDENTIFICADOR_INTENTOS = 'codigo-cliente'


def datos_cliente(cliente):
    return {
        'nombre': cliente.nombre,
        'codigo': cliente.codigo_legible,   # su propio código: "Mi cuenta" lo muestra por si lo olvida
        # En una prueba gratis, hasta cuándo dura la prueba (y "demo": true)
        'vence': cliente.demo_hasta if cliente.en_demo else cliente.vence,
        'demo': cliente.en_demo,
        'pantallas': cliente.pantallas_vigentes(),
        'conectados': cliente.dispositivos.count(),
        'horas_sin_senal': HORAS_SIN_SENAL,
        'vendedor': sesiones.contacto_del_vendedor(cliente),   # {"nombre", "telefono"}: para renovar
    }


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def login(request):
    estado = estado_actual()
    if estado['activo']:
        raise error_mantenimiento(estado)
    ip = ip_cliente(request._request)
    if login_bloqueado(IDENTIFICADOR_INTENTOS, ip):
        raise ErrorApi('Demasiados intentos con un código equivocado. Esperá unos minutos.', 'login_bloqueado',
                       status.HTTP_429_TOO_MANY_REQUESTS)

    datos = datos_planos(request.data)
    try:
        clave, dispositivo = sesiones.entrar(datos.get('codigo', ''), datos.get('dispositivo', ''))
    except sesiones.AccesoDenegado as error:
        if error.codigo == 'codigo_invalido':
            registrar_login_fallido(IDENTIFICADOR_INTENTOS, ip)
        estados = {'codigo_invalido': status.HTTP_400_BAD_REQUEST, 'cuenta_en_uso': status.HTTP_409_CONFLICT}
        raise ErrorApi(str(error), error.codigo, estados.get(error.codigo, status.HTTP_403_FORBIDDEN),
                       extra=error.extra)
    limpiar_login_fallidos(IDENTIFICADOR_INTENTOS, ip)
    return Response({'token': clave, 'tipo': TokenBearer.palabra_clave, 'cliente': datos_cliente(dispositivo.cliente)})


def _solo_clientes(request):
    if not getattr(request.user, 'es_cliente_app', False):
        raise PermissionDenied('Esto es solo para la app de los clientes.')


@api_view(['GET'])
@authentication_classes([TokenCliente])
def estado(request):
    _solo_clientes(request)
    return Response(datos_cliente(request.user.cliente))


@api_view(['POST'])
@authentication_classes([TokenCliente])
def logout(request):
    _solo_clientes(request)
    sesiones.salir(request.auth)
    return Response(status=status.HTTP_204_NO_CONTENT)
