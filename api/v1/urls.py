from django.urls import path, reverse
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from . import agenda, app, auth, biblioteca, canales, cliente, notificaciones, perfil, usuarios

app_name = 'api_v1'


@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def indice(request):
    """GET /api/v1/ — la lista de endpoints (para orientarse desde el navegador)."""
    def url(nombre, **kwargs):
        return request.build_absolute_uri(reverse(f'api_v1:{nombre}', kwargs=kwargs))

    return Response({
        'version': 'v1',
        'endpoints': {
            'login': url('login'),
            'logout': url('logout'),
            'perfil': url('perfil'),
            'cambiar_password': url('cambiar_password'),
            'usuarios': url('usuarios'),
            'usuarios_opciones': url('usuarios_opciones'),
            'notificaciones': url('notificaciones'),
            'canales': url('canales'),
            'cliente_login': url('cliente_login'),
            'cliente': url('cliente'),
            'cliente_logout': url('cliente_logout'),
            'biblioteca': url('biblioteca'),
            'agenda': url('agenda'),
            'app': url('app'),
        },
    })


urlpatterns = [
    path('', indice, name='indice'),
    path('login/', auth.login, name='login'),
    path('logout/', auth.logout, name='logout'),

    path('perfil/', perfil.perfil, name='perfil'),
    path('perfil/opciones/', perfil.opciones, name='perfil_opciones'),
    path('perfil/cambiar-password/', perfil.cambiar_password, name='cambiar_password'),

    path('usuarios/', usuarios.lista, name='usuarios'),
    path('usuarios/opciones/', usuarios.opciones, name='usuarios_opciones'),
    path('usuarios/<int:pk>/', usuarios.detalle, name='usuario'),
    path('usuarios/<int:pk>/estado/', usuarios.cambiar_estado, name='usuario_estado'),
    path('usuarios/<int:pk>/restablecer-password/', usuarios.restablecer_password,
         name='usuario_restablecer_password'),

    path('canales/', canales.lista, name='canales'),
    path('canales/secciones/', canales.secciones_de_la_app, name='canales_secciones'),
    path('canales/fuentes/<int:pk>/falla/', canales.avisar_falla, name='fuente_falla'),
    path('canales/fuentes/<int:pk>/estabilidad/', canales.estabilidad, name='fuente_estabilidad'),
    path('canales/visto/', canales.visto, name='canales_visto'),
    path('canales/fuentes/<int:pk>/resolver/', canales.resolver, name='fuente_resolver'),

    # La última versión de la app (para avisar que hay una nueva)
    path('app/', app.ultima_version, name='app'),

    # La app de los clientes (login con código)
    path('cliente/login/', cliente.login, name='cliente_login'),
    path('cliente/', cliente.estado, name='cliente'),
    path('cliente/logout/', cliente.logout, name='cliente_logout'),

    # Favoritos, "Continuar viendo" y últimos canales vistos de la cuenta (no del aparato)
    path('biblioteca/', biblioteca.biblioteca, name='biblioteca'),

    # Partidos y programas especiales, con su canal ("Avisarme" en la app)
    path('agenda/', agenda.lista, name='agenda'),

    path('notificaciones/', notificaciones.lista, name='notificaciones'),
    path('notificaciones/<int:pk>/leida/', notificaciones.marcar_leida, name='notificacion_leida'),
    path('notificaciones/marcar-todas/', notificaciones.marcar_todas, name='notificaciones_marcar_todas'),
]
