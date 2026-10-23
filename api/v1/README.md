# api/v1/

**Versión 1** de la API. Si algún día hay que cambiarla de una forma que
rompería las apps ya instaladas, se crea `v2/` al lado y las dos conviven.

## Qué contiene

| Archivo | Para qué |
|---|---|
| `urls.py` | Las rutas de la v1 (y `GET /api/v1/`, que las lista). |
| `serializers.py` | Cómo se convierte cada objeto a JSON (lo que la app **recibe**). |
| `auth.py` | Iniciar y cerrar sesión. |
| `perfil.py` | Mi perfil y cambiar mi contraseña. |
| `usuarios.py` | Gestión de usuarios. |
| `notificaciones.py` | Mis notificaciones. |
| `canales.py` | Los canales de TV para la app. |
| `catalogo.py` | El catálogo de `GET /api/v1/canales/` **armado rápido**: pide a la base solo las columnas que van a la app (sin el serializador: con 5.000 películas tardaba 2 s por pedido), lo guarda armado y comprimido 1 minuto (`CATALOGO_APP_SEGUNDOS`; en los tests, 0) para que los aparatos que lo piden juntos no lo armen de nuevo, lo manda comprimido (gzip: entre 5 y 20 veces menos datos) y con su huella (`ETag`): si la app ya lo tiene (`If-None-Match`), contesta 304 sin mandar nada. Manda EXACTAMENTE lo mismo que el serializador de antes (lo prueba `api/tests/test_catalogo_rapido.py`): las apps viejas lo leen igual. |
| `app.py` | La última versión publicada de la app Android (para el aviso "Hay una versión nueva"). |
| `cliente.py` | La app de los **clientes** (los que miran la TV): entrar con su código, su estado ("señal") y cerrar sesión. |

Lo que la app **envía** se valida con los formularios de la web
(`usuarios/forms.py`): los campos se llaman igual.

## Endpoints

Todos piden `Authorization: Bearer <token>`, salvo `login`, `cliente/login`, `app` y el índice.

Hay **dos tipos de sesión**:

- **Usuario del panel** (`login/`, usuario y contraseña): administradores y
  revendedores. El superusuario ve los canales sin créditos ni límite de dispositivos.
- **Cliente** (`cliente/login/`, código de 8 números): solo puede usar
  `canales/` (con `secciones/`, `fuentes/<id>/resolver/` y los avisos de falla y de lo visto), `biblioteca/`, `cliente/` y `cliente/logout/` (lo demás responde 403). Su token
  empieza con `c_`. Si su servicio vence o lo suspenden, todo responde 403
  `servicio_vencido` / `suspendido`; si le liberan el dispositivo, 401.
  Reglas en `reventa/sesiones.py`.

| Método | Ruta | Permiso | Qué hace |
|---|---|---|---|
| GET | `/api/v1/` | — | Lista de endpoints |
| POST | `/api/v1/login/` | — | `{username, password, dispositivo}` → `{token, vence, usuario}` |
| POST | `/api/v1/logout/` | sesión | Cierra la sesión de este dispositivo |
| GET | `/api/v1/perfil/` | sesión | Mis datos y mis permisos (`permisos`: códigos; `permisos_por_modulo`: legibles) |
| PATCH | `/api/v1/perfil/` | sesión | Modificar mis datos (solo lo que cambia) |
| GET | `/api/v1/perfil/opciones/` | sesión | Opciones para el formulario del perfil (géneros) |
| POST | `/api/v1/perfil/cambiar-password/` | sesión | `{old_password, new_password1, new_password2}` |
| GET | `/api/v1/usuarios/` | `ver_usuarios` | Lista. Filtros: `q`, `rol` (id o `sin_rol`), `estado` (`activos`/`inactivos`), `pagina` |
| POST | `/api/v1/usuarios/` | `crear_usuarios` | Crear (`password1`, `password2` y los datos) |
| GET | `/api/v1/usuarios/opciones/` | crear o editar | Roles (y si se pueden asignar), tipos de documento, géneros |
| GET | `/api/v1/usuarios/<id>/` | `ver_usuarios` | Detalle, con `acciones` que puede hacer quien pregunta |
| PATCH | `/api/v1/usuarios/<id>/` | `editar_usuarios` | Modificar (solo lo que cambia) |
| DELETE | `/api/v1/usuarios/<id>/` | `eliminar_usuarios` | Eliminar |
| POST | `/api/v1/usuarios/<id>/estado/` | `editar_usuarios` | `{activo: true/false}` |
| POST | `/api/v1/usuarios/<id>/restablecer-password/` | `restablecer_password_usuarios` | `{password1, password2, obligar_cambio}` |
| GET | `/api/v1/canales/` | sesión (usuario o cliente vigente) | Canales de TV activos, agrupados por categoría, con sus fuentes en el orden en que conviene probarlas (primero las que no se cortan en los aparatos, después por prioridad). `?contenido=pelicula`, `serie` o la clave de una sección nueva (`musica`). Con `serie` llega además `portadas`: `{"Pocoyó": "https://..."}`, la portada propia de cada serie que la tiene (sin portada, la app usa la imagen del primer capítulo) |
| GET | `/api/v1/canales/secciones/` | sesión (usuario o cliente vigente) | Las secciones nuevas creadas en el panel → `{secciones: [{clave, nombre, forma, icono}]}` (forma: `vivo` o `pelicula`). Lo de cada una se pide a `canales/?contenido=<clave>` |
| GET | `/api/v1/canales/series/` | sesión (usuario o cliente vigente) | **Las series SIN sus capítulos** (app 1.2.38+): `?formatos=` como en `/canales/` → `{cantidad, series: [{nombre, categoria, imagen, capitulos, temporadas: [[1, 26], [2, 26]], destacada, codecs}]}`. Con la misma regla que la app (`clasificar.episodio`, anotada en cada capítulo: `Canal.serie`), por categoría (en el orden de la app) y por nombre, solo las que tienen el T1:E1. Comprimida, con huella (304) y guardada 1 minuto, como el catálogo. Con 75.000 capítulos: 0,5 MB contra 28 MB de `?contenido=serie`, que sigue igual para las apps viejas. |
| GET | `/api/v1/canales/series/capitulos/` | sesión (usuario o cliente vigente) | Los capítulos de las series `?nombre=Pocoyó&nombre=Lost` y de las series de los capítulos `?ids=12,40` (para "Continuar viendo"), hasta 50, con el mismo formato que `/canales/`. La app los pide al abrir una serie. |
| POST | `/api/v1/canales/fuentes/<id>/falla/` | sesión (usuario o cliente) | `{motivo, detalle}` (opcionales). La app avisa que no pudo reproducir esa fuente: el servidor la vuelve a probar y, si también falla, deja de mandarla; si a él le anda pero fallan 3 aparatos en un día, la oculta 7 días. → `{estado}` |
| POST | `/api/v1/canales/fuentes/<id>/estabilidad/` | sesión (usuario o cliente) | `{segundos, cortes}`. La app dejó de ver esa fuente: cuánto la vio y cuántas veces se cortó. Con lo de todos los aparatos, `/canales/` manda primero las fuentes que no se cortan. → `{cortes_por_hora}` (null si todavía se vio poco) |
| GET / POST | `/api/v1/canales/recorrido/` | usuario del panel con `importar_canales` (no clientes) | El **modo revisión** de la app (`canales/recorrido.py`). GET `?cantidad=20&formatos=hls,dash,directo,rtsp` → `{fuentes: [{id, url, tipo, codec, user_agent, referer, canal, logo, en_vivo}], quedan}`: las próximas que conviene probar (en vivo primero; lo quitado por la limpieza, lo que falla y lo nunca visto antes). POST `{resultados: [{id, anduvo, motivo?, detalle?}]}` → `{anotados}`: se suma a la salud de cada fuente; si anda una de un canal quitado por la limpieza, vuelve ya. `motivo: sin_internet` no se anota. |
| POST | `/api/v1/canales/visto/` | sesión (usuario o cliente) | `{vistos: [{id, segundos, vista}], favoritos: ["c:12", "s:Serie"]}`. Lo que se miró desde el último aviso y lo agregado a favoritos. Se suma a los totales del día **sin guardar quién lo mandó** ("Lo más visto" del panel). → `{sumados}` |
| GET / POST | `/api/v1/biblioteca/` | sesión (usuario o cliente) | Favoritos, "Continuar viendo" y últimos canales vistos **de la cuenta** (el cliente, la pantalla con código propio o el usuario; ver `biblioteca/README.md`). GET → `{favoritos: ["c:12", "s:Serie"], progresos: [{id, p, d, t, aparato}], recientes: [{id, t, aparato}]}` (segundos; `t` en milisegundos). POST manda CAMBIOS (todo opcional): `{aparato, agregar, quitar, progresos, olvidar, vistos}` → la biblioteca como quedó. Desde la app 1.2.20 |
| GET | `/api/v1/app/` | — | Última versión publicada de la app: `{version, notas, descarga}` (`version: null` si no hay). La app lo consulta al abrirse |
| POST | `/api/v1/cliente/login/` | — | `{codigo, dispositivo}` → `{token, cliente}`. Errores: 400 `codigo_invalido`, 403 `servicio_vencido`/`suspendido`, 409 `cuenta_en_uso`, 429 `login_bloqueado` |
| GET | `/api/v1/cliente/` | cliente | Su estado (`nombre`, `vence`, `pantallas`, `conectados`, `vendedor`: `{nombre, telefono}`). La app lo llama cada 5 min: es la "señal" que mantiene ocupada su pantalla |
| POST | `/api/v1/cliente/logout/` | cliente | Cierra la sesión y libera la pantalla |
| GET | `/api/v1/notificaciones/` | sesión | Mis notificaciones (`?no_leidas=1`); trae `no_leidas` |
| POST | `/api/v1/notificaciones/<id>/leida/` | sesión | Marcar una como leída |
| POST | `/api/v1/notificaciones/marcar-todas/` | sesión | Marcar todas como leídas |

Para subir una foto (perfil o usuario), mandar el pedido como
`multipart/form-data` con el campo `foto`. Para quitarla: `quitar_foto: true`.
