# lib/api/

La conexión con la API de Django.

| Archivo | Para qué |
|---|---|
| `cliente.dart` | `ApiCliente`: hace los pedidos (GET, POST, PATCH, DELETE) con el token, decodifica el JSON en UTF-8 (las respuestas grandes, como el catálogo, en otro hilo: así no se congela la pantalla) y convierte los errores en `ApiError` (mismo formato que `api/errores.py` del servidor). También avisa cuando la sesión venció (401) o no hay conexión. `getCrudo`: un GET que devuelve la respuesta tal cual (sin leer) y su huella (`ETag`); con la huella del que ya se tiene, el servidor contesta 304 si no cambió. Lo usa el catálogo (`movil/copia_catalogo.dart`). Las respuestas llegan comprimidas (gzip) y se descomprimen solas. |
| `modelos.dart` | Las clases de los datos que llegan (`Perfil`, `UsuarioResumen`, `UsuarioDetalle`, `Notificacion`, `Pagina`...). Son el espejo de `api/v1/serializers.py`. |

Si en el servidor se agrega un endpoint, acá se suma (si hace falta) su
clase en `modelos.dart`; el pedido en sí se hace desde la pantalla con
`api.get(...)` / `api.post(...)`.
