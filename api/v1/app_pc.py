"""
La última versión publicada de la app Kairos TV para PC (Windows), la que se sube en el panel en Descargas → App
para PC. La app instalada la consulta al abrirse (lib/actualizacion.dart): si la suya es más vieja, muestra el cartel
"Hay una versión nueva", baja el instalador, revisa su huella y lo instala sola.

    GET /api/v1/app-pc/   (sin sesión)
      -> 200 {"version": "2026.11.10.1530", "notas": "...", "tamanio": 98000000, "sha256": "...",
              "descarga": "https://.../descargar/pc/3/"}
      -> 200 {"version": null}   si todavía no se publicó ninguna

Es pública como /descargar/pc/: sin un código de cliente válido la app no sirve.
"""

from django.urls import reverse
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from descargas.models import VersionPc


@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def ultima_version(request):
    version = VersionPc.ultima()
    if version is None:
        return Response({'version': None})
    return Response({
        'version': version.version,
        'notas': version.notas,
        'tamanio': version.tamanio,
        'sha256': version.sha256,
        # La de esa versión puntual: si justo publican otra mientras se baja, se instala la que se anunció
        'descarga': request.build_absolute_uri(reverse('descargas:descargar_pc_version', args=[version.pk])),
    })
