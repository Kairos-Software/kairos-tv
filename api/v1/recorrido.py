"""
El "modo revisión" de la app (canales/recorrido.py): un aparato que recorre
los canales solo, de a uno, y cuenta cuáles andan. Solo para usuarios del
panel con el permiso importar_canales (no clientes).

    GET  /api/v1/canales/recorrido/?cantidad=20&formatos=hls,dash,directo,rtsp
      -> {"fuentes": [{"id", "url", "tipo", "codec", "user_agent", "referer",
                       "canal", "logo", "en_vivo"}, ...],
          "quedan": 812}
      Las próximas fuentes que conviene probar (lo en vivo, lo quitado por la
      limpieza y lo que falla primero). Vacío = no queda nada por probar hoy.

    POST /api/v1/canales/recorrido/
      {"resultados": [{"id": 5, "anduvo": true}, {"id": 6, "anduvo": false, "motivo": "rechazo", "detalle": "..."}]}
      -> {"anotados": 2}
      motivo: formato | rechazo | tiempo | conexion | error | sin_internet (este no se anota).
"""

from rest_framework.decorators import api_view
from rest_framework.response import Response

from canales import recorrido
from canales.consultas import tipos_pedidos

from ..permisos import exigir_permiso
from .serializers import FuenteSerializer


@api_view(['GET', 'POST'])
def recorrer(request):
    exigir_permiso(request.user, 'importar_canales')
    if request.method == 'POST':
        resultados = request.data.get('resultados') if isinstance(request.data, dict) else None
        if not isinstance(resultados, list):
            return Response({'detalle': 'Faltan los resultados.'}, status=400)
        return Response({'anotados': recorrido.anotar(resultados[:recorrido.MAXIMO_POR_PEDIDO])})

    formatos = request.query_params.get('formatos')
    tipos = tipos_pedidos(formatos) if formatos else None
    try:
        cantidad = int(request.query_params.get('cantidad', 20))
    except ValueError:
        cantidad = 20
    fuentes = recorrido.pendientes(cantidad, tipos)
    en_vivo = set(recorrido.secciones_en_vivo())
    return Response({
        'fuentes': [{**FuenteSerializer(f).data, 'canal': f.canal.nombre, 'logo': f.canal.logo,
                     'en_vivo': f.canal.contenido in en_vivo} for f in fuentes],
        'quedan': recorrido.cuantas_quedan(tipos),
    })
