"""
La biblioteca de la cuenta: favoritos, "Continuar viendo" y los últimos
canales vistos (ver biblioteca/servicios.py: de quién es cada cosa).

  GET  /api/v1/biblioteca/
      -> 200 {"favoritos": ["c:12", "s:Pocoyó"],
              "progresos": [{"id", "p", "d", "t", "aparato"}],   (segundos; t en milisegundos)
              "recientes": [{"id", "t", "aparato"}]}

  POST /api/v1/biblioteca/   {"aparato": "Smart TV Philips",
                              "agregar": [...], "quitar": [...], "progresos": [...],
                              "olvidar": [...], "vistos": [...]}   (todo opcional)
      -> 200 la biblioteca como quedó

La app manda CAMBIOS, no la lista entera: si dos aparatos cambian cosas a la
vez no se pisan. Lo usa la app desde la 1.2.20.
"""

from rest_framework.decorators import api_view
from rest_framework.response import Response

from biblioteca import servicios


@api_view(['GET', 'POST'])
def biblioteca(request):
    try:
        cuenta = servicios.cuenta_de(request)
    except servicios.SinCuenta:
        return Response({'detalle': 'Esta sesión no tiene biblioteca.'}, status=403)
    if request.method == 'GET':
        return Response(servicios.leer(cuenta))
    cambios = request.data if isinstance(request.data, dict) else {}
    return Response(servicios.aplicar(cuenta, cambios, aparato=cambios.get('aparato', '')))
