# lib/

El código de la app. Flutter arranca por `main.dart`.

| Archivo / carpeta | Para qué | Equivalente en Django |
|---|---|---|
| `main.dart` | Arranque, tema, idioma, y `Raiz`: decide qué mostrar según la sesión (carga, login, servicio vencido, sin conexión) y, con sesión, el celular (`movil/`) o la TV (`tv/`). | `urls.py` + `@login_required` |
| `config.dart` | Nombre de la app y **dirección del servidor**: la app de producción habla siempre con producción (no se puede cambiar ni se ve); la versión "Kairos TV Local" (`--flavor local`) con la PC. | `.env` |
| `sesion.dart` | Quién está logueado (un **cliente** con código o un **usuario** del panel), el token guardado, entrar y salir, y la "señal" del cliente cada 5 min. Si el aparato pasa más de 2 horas sin señal (TV apagada, app en segundo plano), el servidor libera su pantalla y el token deja de valer: el cliente **vuelve a entrar solo** con el último código (al abrir la app, después de actualizarla o al volver de segundo plano) y el catálogo guardado no se borra. Solo si el servidor no lo deja (ej: cuenta en uso) va al login, que dice por qué. "Cerrar sesión" la cierra de verdad. | `request.user` + sesiones |
| `aparato.dart` | Nombre del aparato, si es una TV y la versión instalada (lo da `MainActivity.kt`); instalar una APK y abrir enlaces (WhatsApp). | — |
| `acceso.dart` | Lo de antes de entrar, igual en celular y TV: el login (código del cliente con teclado numérico; usuario y contraseña del panel aparte; en la TV se escriben con un teclado en la pantalla, porque los campos de Android se traban con el control; si el ingreso falla, el foco del control se queda donde estaba), "Tu servicio venció" (con el contacto del vendedor), la pantalla de carga y la de sin conexión. | `login.html` |
| `marca.dart` | El logo de Kairos TV **dibujado** (el portal de cuatro paneles con el punto rubí): `SimboloKairos`, `LogoKairos`, `NombreKairos`. Las imágenes de `assets/logo/` salen de las mismas medidas (`tools/generar_marca.py`). | — |
| `bienvenida.dart` | La presentación al abrir la app: reproduce un video horizontal en TV o pantalla acostada y uno vertical en celular, ambos con audio incorporado. Mientras se ve, por debajo cargan la sesión y el catálogo, pero la app no se dibuja (el video la tapa: dibujar las dos cosas trababa el video) y los botones del control no le llegan. Android arranca con una pantalla lisa del mismo color hasta que el primer cuadro está listo. Archivos en `assets/bienvenida/`. | — |
| `actualizacion.dart` | El aviso "Hay una versión nueva": pregunta a `/api/v1/app/` al abrir (si no hay internet, reintenta cada minuto; si la app queda abierta, cada 6 horas), baja la APK y abre el instalador de Android. Antes del cartel cierra el teclado de Android para que el control llegue a "Actualizar", y mientras está abierto no deja que nada de atrás se lleve el foco (en la TV, el inicio que terminaba de cargar se quedaba con él). El login tiene su propio botón "Buscar actualización". | — |
| `tema.dart` | El diseño viejo (lo usan todavía las pantallas de `pantallas/`): el del panel en versión oscura (azul noche del menú, celeste/azul en lo activo, naranja en el foco del control remoto), letras Sora y Manrope, radios y `FondoMarca`. Si cambian los colores del panel, se cambian acá. | `static/css/kairos.css` |
| `campos.dart` | Los campos del usuario agrupados por sección, como en `usuarios/forms.py`. | `SECCIONES_USUARIO` |
| `senales.dart` | De una fuente a la dirección que abre el reproductor: YouTube se resuelve en el aparato (con Cronet), las páginas de video (Twitch...) se le piden al servidor, y le dice al reproductor el formato (HLS, DASH, video directo). | `canales/paginas.py` |
| `utiles.dart` | Funciones chicas: fechas legibles, mensajes, "¿seguro?". | `herramientas/` |
| `movil/` | La app en el **celular** con el diseño de Stitch (inicio, en vivo, guía, películas, series, favoritos, detalle, reproductores, mi espacio). También los datos que usa la TV (`datos.dart`, `control_senal.dart`) y los colores y letras (`estilo.dart`). Ver su README. | templates |
| `tv/` | La app en la **TV**, manejada con el control remoto (diseño de `diseno_kairos_tv/`). Ver su README. | templates |
| `tele/` | **"Ver en la tele"**: la app corre en el celular y una tele cualquiera (aunque no sea Android) hace de segundo monitor, con el diseño de TV. En el celular queda el control remoto. Ver su README. | — |
| `api/` | Cómo se habla con la API y las clases de los datos. Ver su README. | — |
| `revision/` | El **modo revisión** (usuarios del panel que cargan canales): el aparato recorre los canales solo, de a uno, y le cuenta al servidor cuáles andan. Ver su README. | `canales/recorrido.py` |
| `pantallas/` | Las herramientas del panel en el celular (perfil, usuarios, avisos). Ver su README. | `views.py` + templates |
| `widgets/` | Piezas de pantalla reutilizables. Ver su README. | `templates/parciales/` |

## Cómo fluye una pantalla

1. La pantalla pide datos con `SesionScope.leer(context).api.get('usuarios/')`.
2. `ApiCliente` agrega el token, hace el pedido y convierte el JSON.
3. Si sale bien, la pantalla los guarda en su estado y se redibuja (`setState`).
4. Si sale mal, llega un `ApiError` con `detalle` (para mostrar) y `campos`
   (errores de cada campo, para los formularios).
5. Si la sesión venció (401), `Sesion` vuelve sola al login (un cliente
   primero intenta volver a entrar con su último código). Un 401 de un pedido
   hecho con un token anterior no cuenta: llegó tarde.
6. Si un cliente se quedó sin servicio (403 `servicio_vencido` / `suspendido`),
   `Sesion` muestra "Tu servicio venció" (`acceso.dart`).
