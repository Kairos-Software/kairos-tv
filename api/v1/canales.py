"""
Los canales de TV para la app.

    GET /api/v1/canales/?formatos=hls,dash,directo,rtsp
      -> {"cantidad": 3,
          "categorias": [{"id": 1, "nombre": "Noticias",
                          "canales": [{"id", "nombre", "numero", "logo", "destacado",
                                       "fuentes": [{"id", "url", "tipo", "user_agent", "referer"}, ...]}]}]}
      "destacado": marcado en el panel; el modo reposo de la TV lo muestra más
      seguido (las apps anteriores a la 1.2.19 no lo leen).

Los ven los usuarios del panel y los clientes con el servicio vigente. Solo
van los canales que la app puede reproducir: `formatos` dice cuáles sabe
reproducir esa versión de la app (sin `formatos` = solo HLS, como la 1.0.0).

    GET /api/v1/canales/?contenido=pelicula   (o serie; sin nada = en vivo)
      Con serie llegan los capítulos sueltos ("Pocoyó S01 E02") y además
      "portadas": {"Pocoyó": "https://..."}: la imagen propia de cada serie
      que la tiene (puesta en el panel). Sin portada, la app usa la del
      primer capítulo. Las apps anteriores a la 1.2.11 no la leen.
    GET /api/v1/canales/?contenido=musica     (la clave de una sección nueva, ver abajo)

    GET /api/v1/canales/secciones/
      -> {"secciones": [{"clave": "musica", "nombre": "Música", "forma": "pelicula", "icono": "musica"}, ...]}
      Las secciones nuevas creadas desde el panel (canales/secciones.py), en
      el orden del menú. "forma": "vivo" (como En vivo: radios) o "pelicula"
      (a demanda, como Películas). Lo de cada una se pide con ?contenido=<clave>.
      Las apps anteriores a la 1.2.11 no las piden (y no ven lo que tienen).

    GET /api/v1/canales/fuentes/<id>/resolver/
      -> {"url": "https://...m3u8", "tipo": "hls" | "dash" | "directo", "cabeceras": {...}}
      Para las fuentes "pagina" (Twitch, Dailymotion...): la dirección real
      del video en este momento (cambia seguido, por eso se pide al reproducir).
      YouTube no pasa por acá: lo resuelve la app en el aparato (ver canales/paginas.py).
      Si no se puede: 422 {"detalle": "El canal no está transmitiendo en vivo ahora."}

    POST /api/v1/canales/fuentes/<id>/falla/   {"motivo": "formato", "detalle": "..."}  (los dos opcionales)
      -> {"estado": "funciona" | "caida" | "sin_verificar"}
      La app avisa que no pudo reproducir esa fuente. El servidor la vuelve a
      probar por su cuenta y, si también le falla, deja de mandarla. Si al
      servidor le anda pero varios aparatos avisan que no se reproduce, se
      oculta un rato igual ("caida"): 3 horas la primera vez, más si sigue
      fallando, y vuelve sola. motivo: formato | rechazo | tiempo |
      conexion | error (ver servicios.MOTIVOS_DE_LOS_APARATOS).

    POST /api/v1/canales/fuentes/<id>/estabilidad/   {"segundos": 900, "cortes": 2, "proporcion": 1.78}
      -> {"cortes_por_hora": 8.0 | null}
      La app dejó de ver esa fuente: cuánto la vio, cuántas veces se cortó
      (se frenó a cargar, o se cayó y se reconectó) y la forma de la imagen
      (ancho / alto, opcional: 1.33 = 4:3, "cuadrada"). Con lo de todos los
      aparatos, la lista de canales manda primero las fuentes que no se
      cortan y llenan la pantalla (consultas.ordenadas_por_estabilidad). Si
      se vio un minuto o más, anda: se olvida que había fallado y, si estaba
      oculta, vuelve ya. Las apps anteriores a la 1.2.16 no lo mandan.

    POST /api/v1/canales/visto/
      {"vistos": [{"id": 12, "segundos": 300, "vista": true}], "favoritos": ["c:12", "s:Flash Gordon"]}
      -> {"sumados": 3}
      Lo que se miró en este aparato desde el último aviso ("vista": es la
      primera vez que se avisa de ese rato: cuenta una vista) y lo que se
      agregó a favoritos. Se suma a los totales del día: NO se guarda quién
      lo mandó. Lo usa el panel en "Lo más visto" (ver canales/estadisticas.py).
"""

from django.core.cache import cache
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view
from rest_framework.response import Response

from canales import clasificar, estadisticas, imagenes, paginas, secciones
from canales.consultas import agrupar_por_categoria, canales_disponibles, fuentes_usables, tipos_pedidos
from canales.models import Contenido, Fuente
from canales.servicios import registrar_estabilidad, registrar_falla_en_aparato, reverificar_por_aviso
from canales.verificacion import verificar_url

from .serializers import CanalSerializer


@api_view(['GET'])
def lista(request):
    contenido = request.query_params.get('contenido')
    canales = list(canales_disponibles(tipos_pedidos(request.query_params.get('formatos')),
                                       contenido if secciones.es_valida(contenido or '') else Contenido.VIVO))
    contexto = {'request': request}
    respuesta = {
        'cantidad': len(canales),
        'categorias': [
            {
                'id': categoria.pk if categoria else None,
                'nombre': categoria.nombre if categoria else 'Otros',
                'canales': CanalSerializer(del_grupo, many=True, context=contexto).data,
            }
            for categoria, del_grupo in agrupar_por_categoria(canales)
        ],
    }
    if contenido == Contenido.SERIE:
        respuesta['portadas'] = imagenes.portadas_de({clasificar.episodio(c.nombre)[0] for c in canales})
    return Response(respuesta)


@api_view(['GET'])
def secciones_de_la_app(request):
    return Response({'secciones': [
        {'clave': s.clave, 'nombre': s.nombre, 'forma': s.forma, 'icono': s.icono} for s in secciones.nuevas()
    ]})


@api_view(['POST'])
def avisar_falla(request, pk):
    fuente = get_object_or_404(fuentes_usables().select_related('canal'), pk=pk)
    estado = reverificar_por_aviso(fuente, verificar_url)
    if estado != Fuente.Estado.CAIDA:
        # Al servidor le anda: se cuenta el aviso del aparato (cada sesión es un aparato)
        quien = f'{type(request.auth).__name__}:{getattr(request.auth, "pk", request.user.pk)}'
        motivo = str(request.data.get('motivo', ''))[:20]
        detalle = str(request.data.get('detalle', ''))[:120]
        if registrar_falla_en_aparato(fuente, quien, motivo, detalle):
            estado = Fuente.Estado.CAIDA
    return Response({'estado': estado})


@api_view(['POST'])
def estabilidad(request, pk):
    fuente = get_object_or_404(Fuente, pk=pk)
    datos = request.data if isinstance(request.data, dict) else {}
    try:
        segundos, cortes = int(datos.get('segundos', 0)), int(datos.get('cortes', 0))
        proporcion = float(datos['proporcion']) if datos.get('proporcion') is not None else None
    except (TypeError, ValueError):
        return Response({'detalle': 'segundos, cortes y proporcion tienen que ser números.'}, status=400)
    registrar_estabilidad(fuente, segundos, cortes, proporcion)
    fuente.refresh_from_db(fields=['segundos_en_aparatos', 'cortes_en_aparatos'])
    return Response({'cortes_por_hora': fuente.cortes_por_hora})


@api_view(['POST'])
def visto(request):
    vistos = request.data.get('vistos') if isinstance(request.data, dict) else None
    favoritos = request.data.get('favoritos') if isinstance(request.data, dict) else None
    sumados = estadisticas.registrar(vistos if isinstance(vistos, list) else [],
                                     favoritos if isinstance(favoritos, list) else [])
    return Response({'sumados': sumados})


# La dirección que entrega un sitio dura un rato: si varios aparatos piden la
# misma fuente casi a la vez, se reusa en vez de volver a consultar al sitio.
GUARDAR_RESUELTA = 90   # segundos


@api_view(['GET'])
def resolver(request, pk):
    fuente = get_object_or_404(fuentes_usables().filter(tipo=Fuente.Tipo.PAGINA), pk=pk)
    clave = f'fuente_resuelta:{fuente.pk}'
    datos = cache.get(clave)
    if datos is None:
        try:
            resuelto = paginas.resolver(fuente.url)
        except paginas.NoSePudo as error:
            return Response({'detalle': str(error)}, status=422)
        datos = {'url': resuelto.url, 'tipo': resuelto.tipo, 'cabeceras': resuelto.cabeceras}
        cache.set(clave, datos, GUARDAR_RESUELTA)
    return Response(datos)
