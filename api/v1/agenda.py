"""
La Agenda para la app: partidos y programas especiales de los próximos 14
días, cada uno con su canal (ver agenda/).

  GET /api/v1/agenda/
      -> 200 {"eventos": [{"id": 3, "titulo": "Boca vs River", "detalle": "Liga Profesional",
                           "tipo": "futbol", "canal": 812,
                           "empieza": "2026-10-18T21:00:00-03:00", "termina": "2026-10-18T23:00:00-03:00"}]}

Solo lo que tiene canal y todavía no terminó. "canal" es el id del canal en
vivo (el mismo de /canales/): la app muestra el evento si ese canal se ve en
el aparato. Lo usa la app desde la 1.2.25 (las anteriores no lo piden).
"""

from rest_framework.decorators import api_view
from rest_framework.response import Response

from agenda import servicios


@api_view(['GET'])
def lista(request):
    return Response({'eventos': [servicios.en_json(e) for e in servicios.para_la_app()]})
