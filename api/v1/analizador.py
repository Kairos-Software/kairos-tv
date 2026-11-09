"""
Para los analizadores de canales instalados en PC (analizador-canales/analizador/actualizar.py): cuál es la última
versión publicada y bajarla. Así se actualizan solos.

    GET /api/v1/analizador/
      Cabeceras: X-Kairos-Instalador (la huella del instalador del que salió), X-Kairos-Instalacion (su número),
                 X-Kairos-Version y X-Kairos-Pc (el nombre de la PC).
      -> 200 {"version": "2026.11.9.1530", "notas": "...", "tamanio": 312000000, "sha256": "...",
              "descarga": "https://.../api/v1/analizador/descargar/3/"}
      -> 200 {"version": null}   si todavía no se publicó ninguna
      -> 403 {"detail": "..."}   si la huella no es de un instalador del panel o la PC está desconectada

    GET /api/v1/analizador/descargar/<id>/   (las mismas cabeceras) -> el instalador

No usa sesión ni token: quien se presenta con la huella de un instalador del panel ya lo tiene (ver
descargas/analizador.py). Cada consulta anota la PC y su versión: se ven en Descargas → Analizador para PC.
"""

from django.shortcuts import get_object_or_404
from django.urls import reverse
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from descargas import analizador
from descargas.models import VersionAnalizador
from descargas.views import entregar_instalador


@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def ultima_version(request):
    try:
        analizador.presentarse(request.headers)
    except analizador.Problema as error:
        return Response({'detail': str(error)}, status=403)
    version = VersionAnalizador.ultima()
    if version is None:
        return Response({'version': None})
    return Response({
        'version': version.version,
        'notas': version.notas,
        'tamanio': version.tamanio,
        'sha256': version.sha256,
        # La de esa versión puntual: si justo publican otra mientras se baja, se instala la que se anunció
        'descarga': request.build_absolute_uri(reverse('api_v1:analizador_descargar', args=[version.pk])),
    })


@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def descargar(request, pk):
    try:
        analizador.presentarse(request.headers)
    except analizador.Problema as error:
        return Response({'detail': str(error)}, status=403)
    return entregar_instalador(get_object_or_404(VersionAnalizador, pk=pk, publicada=True))
