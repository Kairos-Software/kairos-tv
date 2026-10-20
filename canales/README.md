# canales/

Los **canales de TV en vivo** que ven los clientes en la app, y también las
**películas y series** (`Canal.contenido`), que se cargan igual. Además de esas
tres secciones fijas, desde el panel se crean **secciones nuevas** (Música,
Radio, Deportes...: `Seccion`, ver `secciones.py`), que la app 1.2.11 o más
nueva muestra en su menú.

```
Categoria  1 ──< Canal  1 ──< Fuente

Importacion  1 ──< EntradaImportada   (cada lista subida y qué pasó con cada canal)
```

Un canal puede tener **varias fuentes** (distintas direcciones de la misma
señal). La app prueba la primera y, si falla o se corta, pasa sola a la
siguiente. Si una fuente se cae, el canal sigue andando.

> Django **solo guarda las direcciones**: el video viaja directo desde el
> servidor de cada canal al celular/TV, sin pasar por nuestro servidor. Por
> eso no consume ancho de banda propio ni choca con otros servicios de
> streaming que corran en el mismo servidor.

## Qué contiene

| Archivo / carpeta | Capa | Para qué |
|---|---|---|
| `models.py` | Base | `Categoria`, `Canal` (con idioma, baja lógica y "quitado" con motivo), `Fuente` (dirección, formato, prioridad, estado) e `Importacion` / `EntradaImportada` (cada lista subida y qué pasó con cada canal). `Visto` y `FavoritoAgregado`: cuánto se miró cada cosa y cuántas veces se agregó a favoritos, por día y sumando todos los aparatos (sin saber quién). `PortadaDeSerie`: la portada propia de una serie, por su nombre (ver `imagenes.py`). `LogoParejo`: la copia pareja del logo de cada dirección (ver `imagenes.py`, "Logos parejos"). |
| `imagenes.py` | Base | **Imágenes puestas a mano** en Organizar contenido → Editar. `guardar_subida()`: una imagen subida desde la compu (JPG, PNG o WEBP, hasta 8 MB) se achica a 1600 de lado, se guarda en `media/canales/imagenes/` con un nombre al azar y queda en `logo` como dirección completa, igual que un link pegado (con transparencia queda PNG). `sacar_cuadritos()`: muchos "PNG sin fondo" bajados de internet traen los cuadritos grises PINTADOS; si el borde los tiene (dos grises que se alternan), ese fondo pasa a transparente (solo lo pegado al borde: un gris adentro del logo se queda). Se sube desde Organizar contenido → Editar o desde la página Editar de cada canal. `soltar()` borra una subida vieja cuando ya nadie la usa. **Portada de serie** (`portada_de`, `portadas_de`, `poner_portada`, `mover_portada`): la imagen de la serie aparte de la de sus capítulos (cada capítulo conserva la que trajo YouTube); sin portada, la serie usa la del primer capítulo. Va con la serie al renombrarla o unirla y se borra al eliminarla. La API la manda en `portadas` con `?contenido=serie` (app 1.2.11 o más nueva). **Logos parejos** (canales en vivo y radios): los logos vienen de cualquier lado, unos con mucho borde vacío (Comarca TV, 25 % a cada costado), otros justo al borde, de 100 o de 3840 px; centrados "tal cual" unos se veían chiquitos y otros enormes. `emparejar()` recorta lo que sobra alrededor (lo transparente; o el fondo de un solo color, dejándole un margen de ese color: sacárselo dejaría invisible un logo oscuro sobre blanco), deja un margen chico e igual para todos y lo achica a 512 px (WEBP en `media/canales/logos/`, una por dirección: `LogoParejo`). **Rotos**: si imgur lo borró (manda su cartel "The image you are requesting does not exist") o da 404, no se manda ninguno y la app muestra las iniciales; el panel de detalles de Organizar lo avisa. `emparejar_logos()` lo corre el cron (`verificar_fuentes`, hasta 4 minutos por pasada; reintenta los fallados a los 7 días y borra las copias que ya no usa nadie) y `emparejar_logo_al_guardar()` lo hace en el momento al cambiar un logo en el panel. La API (`CanalSerializer.logo`) y el panel (`logos_parejos()`) muestran la copia: la app no necesita versión nueva. SVG: queda el original. |
| `secciones.py` | Base | **Secciones nuevas de la app** (Música, Radio...). `Seccion` tiene nombre, ícono, orden y su **forma**: "a demanda" (`pelicula`: funciona como Películas, se elige un video, ej. música de YouTube) o "en vivo" (`vivo`: como En vivo, ej. radios). Lo que está en una sección guarda su `clave` ("musica") en `contenido` (igual que "vivo", "pelicula" o "serie"), así importar, organizar, probar y la API sirven igual. `todas()`, `nombre()`, `forma()`, `es_valida()`, `crear()` (arma la clave del nombre; no deja repetir ni pisar las fijas), `editar()` (nombre, ícono, orden; la clave y la forma no cambian) y `borrar()` (si tiene algo, solo "con todo lo que tiene"). Las series no van en secciones nuevas. En el panel: Organizar contenido → pestaña "Nueva sección". |
| `m3u.py` | Base | Lector de listas M3U/M3U8: saca nombre, logo, categoría, número, tvg-id, país, idioma (`tvg-language`), cabeceras y dirección. También `kairos-seccion`, la sección que anotan las listas exportadas de acá (así cada cosa vuelve a su sección). No toca la base. |
| `exportar.py` | Base | **Exportar** desde Organizar contenido. `Eleccion`: secciones enteras, categorías (de una o varias secciones), lo sin categoría, canales y series sueltos, con o sin los filtros de la página y "solo las señales que andan". `elegir()` lo junta en el orden de la app; `lista_m3u()` (una entrada por señal con el mismo nombre, logo, categoría, número, país, idioma, User-Agent/Referer y `kairos-seccion`: al volver a importarla queda igual) y `planilla_excel()` (hojas "Contenido" y "Fuentes", con si la ve la app y por qué no). Lo de YouTube no se exporta. Una lista exportada se importa como `Importacion.de_kairos`: sus series entran aunque tengan menos de 3 capítulos. |
| `clasificar.py` | Base | Conclusiones sobre cada entrada: idioma y país, si es en vivo / película / serie, si es para adultos, el formato que parece y el nombre limpio (`ES: (HD REPUESTO) DAZN F1` → `DAZN F1`). `episodio()`: "Arrow S02 E05" → serie, temporada y capítulo (la misma regla que la app). |
| `paginas.py` | Base | YouTube y páginas de video (Twitch, Dailymotion, Vimeo, Kick...) con **yt-dlp**: `verificar()` (¿hay video?) y `resolver()` (la dirección real en este momento). |
| `verificacion.py` | Base | Prueba si una fuente responde y **qué formato es** mirando los bytes (como VLC): HLS, DASH, video directo (MPEG-TS/MP4/MKV) o RTSP. Si el servidor rechaza al "navegador", reintenta como VLC. Además averigua el **códec** del video (h264, h265, mpeg2...) por la lista HLS o los primeros bytes (`Fuente.codec`), y si es de **10 bits** (`h264_10` / `h265_10`, mirando el perfil: la mayoría de los TV box no leen H.264 de 10 bits y lo muestran con franjas verdes). La app lo compara con lo que sabe mostrar su aparato y no muestra lo que no puede ver. Máximo 2 pedidos a la vez al mismo servidor y un tiempo límite por tanda. |
| `salud.py` | Base | **La salud con memoria** y la **limpieza automática** (ver "Salud de las fuentes" más abajo): cada fuente recuerda sus últimas pruebas (servidor y aparatos), cada fuente y canal queda en un estado (Anda, Inestable, Sin datos, Formato, Rechaza, Falla, Muerta) y `limpiar()` quita los canales que no anduvieron en una semana y devuelve los que revivieron. |
| `bandeja.py` + `views_revisar.py` + `templates/canales/revisar.html` | Base / Panel | **Para revisar** (`/canales/revisar/`, botón en Contenido → Tu catálogo): ver "Salud de las fuentes" más abajo. |
| `recorrido.py` | Base | El **modo revisión** de la app (`GET/POST /api/v1/canales/recorrido/`): qué fuentes le toca probar a un aparato que recorre los canales solo, y lo que encuentra va a la salud. Ver "Salud de las fuentes". |
| `analisis.py` | Base | Qué trae un video mirando sus primeros bytes (MPEG-TS, MKV, MP4 y la lista HLS maestra): si tiene **sonido** y de qué tipo, el **idioma del audio**, la **resolución** (leyendo el SPS de H.264 / H.265), cuántos segundos de video hay en esos bytes y cuánto dura la película. Lo usa la prueba a fondo. |
| `servicios.py` | Base | `crear_importacion()` (analiza la lista, rápido), `procesar_lote()` (prueba las próximas 50: quedan aptas o no, con el motivo), `juzgar()` (qué pasa la prueba), `cargar_lote()` (carga las aptas), `cargar_igual()` / `no_cargar()` (lo que se elige a mano antes de cargar; lo que no respondía entra sin verificar), `verificar_lote_de_fuentes()` (vuelve a probar las guardadas de a 50), `quitar_canales()` / `mostrar_canales()` e `importar_m3u()` (todo de una vez, para la consola). |
| `consultas.py` | Base | `canales_disponibles(tipos)` (lo que ve la app, según los formatos que sabe reproducir), `resumen()` (los números sueltos son solo de en vivo; `por_contenido` trae en vivo, películas y series por separado), `series()` (los capítulos agrupados por serie y temporada, con cuántos ve la app; `Serie.completa` / `por_que_no_se_ve`: como la app, una serie se muestra desde que tiene visible el T1:E1, aunque sea su único capítulo), `catalogo(filtros)` y `por_que_no_se_ve(canal)`. |
| `youtube.py` | Base | **Películas de canales oficiales de YouTube** (Movie Central, Peppa Pig, Bluey...; los revisados están en `SUGERIDOS`). `videos_del_canal()` lee la lista de videos de un canal con yt-dlp (solo los datos), `verificar_video()` prueba con oEmbed que exista y que el dueño deje insertarlo, y del título saca el nombre (`titulo_limpio`, `nombres_distintos`: si todos empiezan "Masha y el Oso" usa lo que sigue), el género (`genero`: la categoría), si es un capítulo (`capitulo`: "T1 E2" -> "Serie S01 E02") y si está en inglés. Son fuentes tipo `yt_video`: la app las muestra en el reproductor de YouTube (sin sacarlas de ahí) y las apps viejas no las reciben. La página `/canales/youtube/` arma con eso una importación (`servicios.crear_importacion_de_youtube`) que se prueba y carga como una lista. Los títulos se piden en español (`lang=es`): si no, YouTube los devuelve traducidos al inglés. **"Es una serie"** (`Importacion.serie`): TODOS los videos son capítulos de esa serie, en el orden de los capítulos (`en_orden_de_capitulos`: si casi todos dicen "Capítulo N", "S02 E05" o "1x05", por ese número, porque hay listas al revés; si no, un canal del más viejo al más nuevo y una lista de reproducción como está), en la categoría de Series elegida; los números definitivos se ponen al terminar de probar (`servicios._numerar_capitulos`: de corrido, siguiendo el último ya cargado, así siempre hay capítulo 1 y no quedan huecos). Las películas no pueden ir a una categoría de Series ni al revés (el formulario lo explica). **Temporadas:** cada temporada se trae con su link, el mismo nombre de serie y su número (`temporada`): los capítulos de cada una se numeran desde el 1. **Mínimo y máximo de minutos** (`maximo_minutos`): para música, por ejemplo, de 2 a 6. **Sección** (`Importacion.seccion`): los videos sueltos pueden ir a una sección nueva "a demanda" (Música) en vez de a Películas; sin categoría elegida, a una con el nombre del canal (el artista). Si YouTube cambia algo y no entrega la lista, hay que actualizar yt-dlp (ver `despliegue/README.md`). |
| `organizar.py` | Base | **Ordenar el contenido.** Cada categoría es de UNA sección (`Categoria.contenido`: En vivo, Películas o Series; la "Infantil" de canales no es la de películas). `categoria_por_nombre(nombre, contenido)` la usa la importación: si "Kids" se juntó en "Infantil", las listas nuevas con "Kids" van a "Infantil". `crear_categoria`, `renombrar_categoria` (el nombre viejo queda en `otros_nombres`), `juntar_categorias` (misma sección; las demás dejan de existir), `borrar_categoria` (con o sin su contenido), `ordenar_categorias`, `categorias_parecidas` ("Kids" / "Infantil" / "Animation;Kids"). `mover_a_categoria`, `cambiar_contenido` (pasa a otra sección con una categoría del mismo nombre; a serie exige el nombre de la serie si no dicen "S01 E01", para crear un T1:E1 identificable), `unir_en_una_serie` (ej: 239 videos de Pocoyó → una serie; si la serie ya tiene capítulos, los nuevos siguen después del último: `ultimo_capitulo`, así se puede unir de a una página), `eliminar_contenido` (si se reimporta, entra de nuevo; para que no vuelva, "quitar"), `eliminados_recientes` / `restaurar_eliminados` (deshacer una eliminación: las señales se rearman con lo anotado en el informe de cada lista y quedan sin verificar; la categoría vuelve si se había borrado), `ordenar_capitulos` (renumera una temporada en el orden elegido, desde la página de la serie), `mover_a_temporada` (pasa capítulos a otra temporada o a una nueva, al final, y renumera sin huecos la de donde salieron), `eliminar_capitulos` (elimina capítulos sueltos de una serie y renumera sin huecos; al restaurarlos vuelven a su lugar), `plan_por_titulos` / `ordenar_por_titulos` (reparte la serie entera en temporadas y números según lo que dice cada título, con vista previa), `categoria_para_la_serie` / `destino_de_serie` (una serie va en UNA categoría: lo que se le suma va a la suya; una nueva necesita que se elija), `editar_canal` / `editar_serie` / `renombrar_serie` (no deja usar el nombre de OTRA serie: se pisarían los capítulos; para eso, "unir"). `nombre_de_serie_valido` rechaza nombres que la app tomaría como número de capítulo ("4x4", "S2 E3"). |
| `estadisticas.py` | Base | **Lo más visto.** `registrar()` suma lo que manda la app (`POST /api/v1/canales/visto/`: segundos mirados, vistas de más de 1 minuto y favoritos agregados) a los totales del día, **sin guardar quién lo mandó**. `lo_mas_visto(dias)`: el ranking de los últimos 7, 30 o 90 días, separado en canales en vivo, películas y series (los capítulos se juntan por serie). |
| `views.py`, `urls.py`, `forms.py`, `templates/` | Panel | `/canales/` (resumen separado de en vivo, películas y series; en «Tu catálogo» el nombre de cada sección, «Los ve la app» y **«No se ven»** —caídos o quitados, `resumen_de()['no_se_ven']`— abren Organizar ya filtrado), `/canales/importaciones/<id>/` (avance e informe: pestañas por lo que pasó —Pasaron, Cargados, No pasaron...— con cuántos hay; al terminar la prueba abre en «Pasaron» para revisar antes de cargar; cada entrada es una ficha con todos sus datos y la dirección completa, sin correr de costado; antes de cargar se puede elegir a mano, de a una o varias: «No cargar» lo que pasó y «Cargar igual» lo que no pasó, no respondió o se descartó, en `/canales/importaciones/<id>/elegir/`), `/canales/catalogo/` y `/canales/series/` (pantallas viejas: llevan a Organizar contenido con los mismos filtros), `/canales/series/detalle/?nombre=...` (temporadas, capítulos y fuentes) `/canales/canal/<id>/editar/` y `/canales/lo-mas-visto/` (pestañas En vivo / Películas / Series, período 7/30/90 días). `/canales/categorias/` (recibe las acciones de categorías; al entrar, lleva a Organizar), `/canales/organizar/` (**Organizar contenido**: TODO en un lugar, sección por sección. A la izquierda las categorías de la sección con cuántos tienen, las que parecen la misma y elegir varias para juntarlas en una, crear; a la derecha su contenido como en la app, con edición rápida —nombre, imagen (link o subida), categoría, si se muestra y cada señal en el orden en que la prueba la app: **de dónde salió** (con link a su importación), formato, estado, códec, error y cuándo se probó— y una barra por pasos con lo que hace cada acción: mover, pasar a otra sección, unir en una serie, quitar, volver a mostrar, eliminar; usa `consultas.organizar_contenido`; filtros: nombre, qué mostrar —todo, lo que ve la app, lo que no se ve, caído, quitado a mano—, idioma, lista de origen y sin imagen; `/canales/como-en-la-app/` redirige acá; **con un filtro puesto, las acciones tocan SOLO lo que se ve**: en una serie, sus capítulos que coinciden; en una categoría, «Solo los N que ves» aparte de borrarla entera, que muestra su total real; **Eliminados** (`/canales/eliminados/`): lo eliminado en 30 días, de a una vez, con «Restaurar»; **Exportar**, arriba o en la barra con lo elegido: `/canales/organizar/exportar/` baja una lista M3U8 o un Excel, ver `exportar.py`). Permisos `ver_canales`, `importar_canales` y `ver_estadisticas` (lo más visto; solo lo da un superusuario). |
| `templatetags/canales_extras.py` | Panel | Filtro `iniciales` (lo que muestra la app cuando un canal no tiene logo). |
| `admin.py` | Técnica | Editar canales, fuentes y categorías puntuales desde `/admin/`. |
| `management/commands/importar_m3u.py` | Técnica | `python manage.py importar_m3u <archivo> [--sin-verificar] [--a-fondo] [--solo-espanol] [--descartar-sin-logo] [--con-peliculas] [--con-adultos]` |
| `management/commands/verificar_fuentes.py` | Técnica | `python manage.py verificar_fuentes` (para programarlo con cron en producción). De madrugada además mide (calidad y velocidad) una tanda de fuentes de los canales que tienen más de una, para que la app arranque por la mejor; `--medir` lo fuerza. Después de verificar, hace la **limpieza automática** (`salud.limpiar`) y prepara los logos parejos que falten (`imagenes.emparejar_logos`). |
| `datos/canales_prueba.m3u8` | Datos | 3 canales públicos para probar (Canal 26, Telemax, TV Universidad). |
| `tests/` | Técnica | Pruebas de las herramientas (probar un link, limpiar nombres), del lector, el clasificador, la verificación, las tandas, las pantallas y la API. |

La API para la app está en `api/v1/canales.py` (`GET /api/v1/canales/?formatos=...`).

## Importar una lista (desde el panel)

Menú **Kairos TV → Contenido → Importar una lista**. Acepta `.m3u`, `.m3u8`
o un `.zip` que la contenga (hasta 150 MB; una de 268 000 entradas tarda ~1,5 min en entrar). Es en tres pasos, para que una
lista de miles de canales no sature el servidor y para que **solo entre lo
que está bien** (no la lista entera: se descarta la basura de cada lista):

1. **Subir y analizar** (segundos, no sale a internet). Cada entrada de la
   lista queda guardada con su idioma, país, categoría, formato y si es en
   vivo, película o serie. Según lo que se elija, se descartan desde ya (con
   el motivo): películas y series (por defecto se importan), otro idioma,
   adultos, sin logo. Siempre se descartan los que no tienen nombre y los
   RTMP. Las direcciones repetidas o ya cargadas quedan como "Ya estaba".
2. **Probar de a tandas.** La pantalla de la importación le pide al
   servidor que pruebe las próximas 50 (cada pedido dura menos de 2
   minutos), muestra la barra "35 % completado", cuánto falta y los
   contadores, y repite hasta terminar. Se puede pausar; si se cierra la
   página, después se sigue con "Continuar". **Todavía no se carga nada**:
   lo que pasa queda "Apta"; lo que no, "No responde" o "No pasó la
   prueba", con el motivo y agrupado por causa ("Audio en otro idioma: 600").
   "Volver a probar las que fallaron" reintenta las que no respondieron,
   llegaron lentas o se cortaron (a veces es algo del momento).
3. **Cargar las aptas.** Un botón "Cargar los N que pasaron" (de a 200, con
   avance). Recién ahí entran a la app.

### Varias listas de una (desde el 18/10/2026)

En Contenido, el botón **Importar lista** abre la tarjeta y directo el
explorador. Se eligen (o se arrastran a la tarjeta) varias listas y se suben
solas, de a una, sin confirmar (`static/js/importar_varias.js`). Cada una es
su propio pedido a `inicio` con `X-Requested-With: XMLHttpRequest`, y la
respuesta es JSON: `{"ok": true, "url": ..., "total": ...}` o `{"ok": false,
"error": ...}`. Las opciones de la tarjeta valen para todas. Cada lista queda
con "Abrir" (en otra pestaña) para probarla y cargarla.

### Una lista grande: por partes (desde el 18/10/2026)

Una lista completa de un proveedor (en vivo + películas + series: 268 000
entradas, 75 MB) no se puede probar entera de una (llevaría días) y en un
servidor chico ni siquiera se puede leer de una (gunicorn corta a los 5 min).

- **Se lee de a tandas.** Con más de `servicios.LEER_DE_UNA` (20 000) entradas,
  al subirla solo se guarda (en `privado/listas/`, fuera de `media/`: tiene
  usuarios y contraseñas) y la pantalla `importacion_leyendo.html` la lee de a
  15 000 con una barra (`importacion_leer` → `servicios.leer_lote`). No arranca
  a probar sola: después se elige qué.
- **Se trabaja por partes** (`servicios.Seleccion`: En vivo / Películas /
  Series, una categoría, lo buscado). La pantalla muestra, de arriba abajo:
  "Qué trae esta lista" (una tarjeta por parte con cuántos pasaron, se
  cargaron y faltan probar), las **categorías** de la parte elegida (tabla con
  buscador) y "Estás trabajando con…" en cuatro pasos: **1 Probar**, **2
  Revisar**, **3 ¿Dónde va?** (ver abajo), **4 Cargar a la app**, más **"No quiero esto: descartar"**
  (`importacion_descartar` → `servicios.descartar`: lo que no interesa, o no
  se tienen derechos para pasar). Probar, cargar y descartar son solo de esa
  parte: se puede cargar una categoría apenas se terminó de probar, aunque
  falte el resto. Las series de esa parte se revisan (¿está el capítulo 1?)
  al terminar de probarla.

### ¿Dónde va? (desde el 18/10/2026)

En el paso 3 de una parte elegida se ve **adónde iría hoy** (`servicios.como_va`:
cada categoría de la lista, si ya existe en el panel —o se juntó ahí— o si se
crearía nueva, y en Series cuántas series ya están) y se elige, antes de cargar
(`importacion_destino` → `servicios.ubicar`; `static/js/importacion_destino.js`):

- **Categoría:** una del panel o una nueva. Con una categoría entera de la
  lista, "Recordarlo" la deja como otro nombre de la elegida
  (`organizar.recordar_nombre`): la próxima lista que la traiga va directo ahí.
- **Serie** (solo Series): una que ya existe o una nueva. Los capítulos se
  renombran a esa serie con el número y la temporada que traen (o todos a una
  temporada); los que no traen número, o lo repiten, siguen después del
  último. Una serie que ya existe va en **su** categoría. Si con el nombre
  nuevo la serie queda completa (el capítulo 1 está en el panel), lo que no
  había pasado por "serie incompleta" vuelve a pasar.

Se anota en cada entrada que falta cargar; lo ya cargado se mueve desde
Organizar contenido. Además, al cargar (con o sin "¿Dónde va?"):

- un capítulo se reconoce también por **serie + temporada + número**, como lo
  agrupa la app: si la serie ya lo tiene, la dirección se suma como fuente
  alternativa en vez de quedar repetido (`_IndiceDeCanales.buscar`);
- los capítulos nuevos de una serie que ya está en el panel van a la
  **categoría de esa serie** (una serie va en una sola categoría).

### Canales Xtream en vivo: el servidor no los da por caídos (desde el 19/10/2026)

Un canal en vivo Xtream (`http://panel:puerto/usuario/clave/123` o
`.../live/usuario/clave/123.ts`) se prueba **sin Range** (llega de corrido,
como lo abre VLC). Si al VPS no le anda, queda **sin verificar** y la app lo
recibe igual (`verificacion._caida_segura`). Solo queda **caído** si el panel
dice que ese canal no existe (404, 410) o el servidor del panel ya no existe.

El motivo: desde el VPS no se sabe. Muchos paneles bloquean las IP de
servidores, y las cuentas suelen permitir **una sola conexión**: cuando la app
pasa de una fuente a otra de la misma cuenta y avisa la falla, el servidor
vuelve a probar la primera (`reverificar_por_aviso`) y choca con la conexión
de la app. Antes eso la dejaba caída y la app dejaba de recibirla, aunque en
VLC anduviera. Si en los aparatos tampoco anda, la esconden sus avisos
(`registrar_falla_en_aparato`). Las películas y los capítulos Xtream siguen
como antes.

### La prueba a fondo (recomendada, viene marcada)

Además de ver que responda, baja hasta 1 MB de cada entrada y revisa:

| Prueba | No pasa si... |
|---|---|
| Formato | El video es MPEG-2, VC-1 o H.264 de 10 bits: muchos aparatos lo muestran verde, cortado o no lo muestran. (Esto se revisa siempre, también sin la prueba a fondo.) |
| Sonido | No trae ninguna pista de audio, o solo DTS / TrueHD (casi ningún aparato lo reproduce). |
| Idioma | Con "Solo en español": el audio dice que está en otro idioma. Si trae español entre varios, pasa. Si el video no dice el idioma, se guía por el nombre y la categoría (paso 1). |
| Imagen | Tiene menos de 360 líneas (240p, 288p): en una TV se ve muy mal. 480 y 576 (SD común) pasan. |
| Fluidez | Llega más lento de lo que se reproduce (menos de x0.9): se cortaría a cada rato. Se mide con las marcas de tiempo del video, o con lo que pesa y lo que dura. |
| En vivo | La señal está congelada: se vuelve a pedir la lista después de un pedazo (6 a 10 s) y no tiene nada nuevo. O el video deja de llegar mientras se prueba. |
| Series | Al terminar: si de una serie no pasó el capítulo 1 de la temporada 1, no pasa ninguno: la app no mostraría una serie que empieza a mitad. En una **lista** además tienen que ser al menos 3 capítulos (contando los ya cargados): ahí suelen venir series sueltas o a medias. Traída de YouTube con "Es una serie", entra desde su primer capítulo (una serie nueva). Pasada a serie a mano en Organizar, no hay mínimo. |

Lo que la prueba no puede averiguar (un MP4 con el índice al final, un
video que no dice su idioma) no se cuenta en contra. La calidad que
encontró ("1080p · H.264 · audio AAC (es) · llega x3.2") queda en el
informe y en la fuente (`Fuente.calidad`). Gasta hasta 1 MB por entrada
(una lista de 1.000 entradas: hasta 1 GB, una sola vez) y en vivo tarda
unos segundos más por canal (espera a que avance).

Ninguna prueba garantiza que un canal no se corte en dos horas: lo que pasa
después lo cuidan la verificación automática (cron cada 6 horas) y los
avisos de los aparatos (ver "Estado de una fuente").

Si un canal ya existe (mismo nombre limpio y país compatible), la dirección se
suma como fuente alternativa. Si el canal está **quitado**, no se vuelve a
agregar. Borrar el informe no borra lo que ya se cargó.

Por consola (todo de una vez, sin barra):

```
python manage.py importar_m3u canales/datos/canales_prueba.m3u8
```

## Elegir qué se ve (antes "Catálogo")

El catálogo (datos técnicos) y la lista de Series eran pantallas aparte: desde
2026-10-10 todo está en **Organizar contenido** (`/canales/organizar/`), y sus
direcciones viejas llevan ahí con los mismos filtros. Cada cosa dice si la app
la muestra y, si no, por qué.

**Detalles** (desde 2026-10-14): con el botón "Detalles" de una tarjeta se abre al
costado un panel con TODO lo suyo. Tocar la tarjeta solo la ELIGE (desde
2026-10-15; antes también abría el panel y molestaba al elegir varias para
recategorizar o borrar). Los filtros quedan fijos arriba solo si entran en un
renglón (partidos, tapaban las tarjetas). El panel (`static/js/organizar_detalle.js`; los datos
los arma `views._preparar_para_editar`): sección, categoría, idioma, país,
tvg-id, quién la cargó y cuándo, el último cambio, y cada señal en el orden en
que la prueba la app: de qué lista o link salió (link a esa importación), el
link completo (con "Copiar link"), formato, estado, calidad, error, cuándo la
probó el servidor, cómo anda en los aparatos (horas vistas, cortes por hora,
imagen cuadrada) y si está oculta y hasta cuándo. Se cierra con la X o
tocando otra vez "Detalles". Lo mismo en el cuadro **Editar**.

**Borrar UNA señal** (`/canales/fuentes/<id>/borrar/`, `servicios.borrar_fuente`):
botón "Borrar esta señal" en el panel de detalles y el cuadro Editar, "Borrar"
en la página del canal y en cada capítulo de la página de una serie. Pregunta
antes; las otras quedan. Si era la única, el canal sigue cargado pero no se ve
en la app hasta que tenga otra. El link borrado queda en la Actividad (en
"cambios", completo). En una serie, el panel junta las señales por lista de
origen: se borran desde cada capítulo ("Ver y ordenar capítulos").

Filtros: nombre, qué mostrar
(todo / lo que ve la app / lo que no se ve / caído / quitado a mano / destacado), idioma,
lista de origen y "sin imagen". En Series, "lo que no se ve" incluye las que
están **a medias** (se ven capítulos, pero falta el T1:E1).
El detalle de una serie (`/canales/series/detalle/`: "N capítulos" en la
tarjeta, o "Ver y ordenar capítulos" en el cuadro Editar) despliega sus
temporadas con disponibilidad, motivo, fuentes y acceso a la edición de cada
capítulo. **Ordenar**: en la misma lista, arrastrando un capítulo de los
puntitos (mouse o dedo) o con las flechas ↑ ↓; al cambiar algo aparece
abajo "Guardar orden / Deshacer". Si la mayoría de los títulos dicen su
número ("Capítulo 12", "EP 12", "12 - ...") y no van en orden, avisa que
están desordenados y un botón los ordena así. Al guardar (`/canales/series/ordenar/`,
`organizar.ordenar_capitulos`) quedan numerados 1, 2, 3... en ese orden: el
número va en el nombre ("Serie S01 E05 Título"), que es lo que lee la app;
cada capítulo conserva su título, sus fuentes y lo visto en los aparatos.

**Las 3 cosas de una serie** (desde 2026-10-15): **categoría** (Disney,
Infantiles...) → **serie** (Buena suerte Charlie) → **temporada** (1, 2...,
cada una con sus capítulos). No son tablas: la categoría va en cada capítulo
y la serie y la temporada en su nombre ("Buena suerte Charlie S02 E05
Título"), que es lo que lee la app. Una serie va en UNA categoría: los
capítulos que se le suman van a la suya (`organizar.categoria_para_la_serie`;
elegir otra se explica en vez de partirla en dos). Donde se deciden:

- **Traer de YouTube con "Cada video va a la temporada y al capítulo que
  dice su título"** (`Importacion.segun_titulo`, migración 0024): para
  canales con todas las temporadas mezcladas; la temporada elegida queda para
  los que no dicen la suya, y los que no dicen número o repiten uno que ya
  está van al final (`servicios._numerar_segun_el_titulo`).
- **"Ya estaban"** en una importación de YouTube dice DÓNDE está cada uno
  ("Ya está cargado (en Series; para verlo, buscá iUeAn7m2Il8 en Organizar)
  como «...»"): el buscador de Organizar encuentra un video pegando su link
  o su ID (`consultas._buscar`), y cualquier señal pegando su dirección.
- **Al traer o juntar** (Traer de YouTube con "Es una serie"; en Organizar,
  "Unir en una sola serie" y "Pasar a otra sección → a Series"): el selector
  "Dónde va" (`static/js/destino_serie.js`, con `consultas.arbol_de_series()`;
  en Organizar lo pide a `/canales/series/arbol/` recién al abrir la acción)
  muestra las series de la categoría elegida (o "＋ Una serie nueva") y las
  temporadas de la serie con cuántos capítulos tiene cada una y desde cuál
  siguen los nuevos (o "＋ Nueva: temporada N"), y abajo "Va a quedar: Series ›
  Disney › Buena suerte Charlie › Temporada 2". Elegir una serie pone su
  categoría; escribir como nueva una que ya existe la elige. Una serie nueva
  sin categoría no se crea (`organizar.destino_de_serie` lo pide).
- **Al editar** (la página de la serie): arriba "Series › Disney › Buena
  suerte Charlie" (cada parte lleva a Organizar) y el recuadro con la
  categoría y el nombre (`/canales/series/editar/`, `organizar.editar_serie`:
  cambia todos los capítulos). En cada temporada se tildan capítulos (Shift
  elige los del medio) y "pasarlos a" otra temporada o a una nueva
  (`/canales/series/temporada/`, `organizar.mover_a_temporada`): van al final
  de esa temporada y la de donde salieron se renumera sin huecos. Si la
  temporada 1 queda vacía avisa (la app muestra la serie desde su T1). Con los
  mismos tildados, **"Eliminarlos"** (`/canales/series/eliminar-capitulos/`,
  `organizar.eliminar_capitulos`): borra solo esos capítulos (en Organizar,
  la tarjeta es la serie entera) y renumera la temporada sin huecos; si eran
  todos, la serie desaparece. Se recuperan en «Eliminados» y vuelven a su
  lugar (`_hacer_lugar`: el que tiene su número y los siguientes se corren uno).
  **"Ordenar todo según los títulos"** (`/canales/series/por-titulos/`,
  `organizar.plan_por_titulos` / `ordenar_por_titulos`): para lo que vino
  mezclado de un canal de YouTube (numerado por fecha, todo en una
  temporada). Cada capítulo va a la temporada y al número que dice su título
  ("Temporada 3 Capitulo 33" → T3 E33; también "S02 E26", "1x05", "Capítulo
  12"; si el nombre ya no lo dice, el título que traía de YouTube). Primero
  muestra cómo quedaría (temporadas, qué cambia, los que no dicen número y
  los que repiten uno, que van al final para revisarlos) y recién con
  "Aplicar" cambia. "Numerar de corrido": 1, 2, 3... sin huecos (si no, el
  número exacto del título; avisa si la temporada 1 no arrancaría en el 1). "Agregar
  capítulos a la temporada N desde YouTube" abre Traer de YouTube con la
  serie, su categoría y esa temporada ya elegidas.
- **Separar en otra serie** lo que vino mezclado en una: un canal de YouTube
  "Yu-Gi-Oh" con los capítulos de GX y 5D's, "Dragon Ball" con Z y GT. En la
  página de la serie, "¿Tiene otras series mezcladas?": se escribe lo que dicen
  sus títulos ("GX") y `/canales/series/separar/` (`serie_separar.html`) muestra
  los que lo dicen, todos tildados (se destilda lo que no va), con el nombre
  sugerido según cómo empiezan los títulos ("Yu-Gi-Oh! GX Episodio 5" → "Yu-Gi-Oh!
  GX", `organizar.nombre_sugerido`) y la temporada. "Separar" los pasa
  (`organizar.mover_a_otra_serie`): a una serie nueva (queda en la misma
  categoría) o a una que existe (se suman al final, en su categoría); los que
  quedan se renumeran sin huecos y vuelve a la serie para seguir separando. A
  mano: en la barra de los tildados de una temporada, "o a otra serie".

**Quitar** = el canal deja de verse en la app (no se borra). Se puede quitar
uno, los elegidos o todos los que coinciden con el filtro, con un motivo.
"Volver a mostrar" lo deshace.

**Editar** ("Más opciones" en el cuadro Editar de Organizar, o el nombre en el
informe de una importación): nombre, logo (link o subido, con vista previa de cómo queda en la app),
número, categoría (elegir una o escribir una nueva), contenido, idioma, país,
orden, si se muestra y si está destacado en la TV. Abajo, sus fuentes: cambiar el orden en que la app las
prueba, apagarlas, borrar una (botón "Borrar", en el momento) o agregar una dirección nueva (se prueba al guardar).

## Probar un link y agregarlo a mano

`/canales/probar/` (botón **Probar un link** en Canales): se pega una
dirección y se prueba igual que al importar (formato real, como la app y como
VLC; YouTube y páginas con yt-dlp). Dice si funciona, de qué tipo es y por
qué no anda. Si es YouTube o una página, sugiere el nombre y la imagen. Con
el resultado se completa nombre, logo, categoría... y se crea el canal (si
no anda, se puede agregar igual: aparece en la app cuando una verificación lo
encuentre funcionando). Si la dirección ya estaba cargada, avisa en qué canal.

## Mantenimiento: verificar y limpiar nombres

En **Contenido → Mantenimiento del catálogo** (`static/js/mantenimiento.js`):

- **Qué revisar**: todo, una sección (En vivo, Películas, Series, Música...) o
  solo lo que vino de una lista o link importado (`Fuente.origen`). Vale para
  los dos botones (`servicios._fuentes_vigentes(seccion, origen)`).
- **Verificar**: prueba esas señales de a tandas (`/canales/verificar/lote/`
  con `seccion` y `origen`). Al terminar queda el **resultado** en la página:
  cuántas andan y cuántas están caídas, y los nombres de lo que **se cayó
  ahora** (con el error) y lo que **volvió**, cada uno con link a su página, más
  "Ver en Organizar lo que no se ve" con la misma sección y lista.
- **Limpiar nombres**: pasa los nombres cargados antes al formato limpio
  ("ES: (FHD) DAZN 1" -> "DAZN 1"). Si dos canales quedan iguales (mismo
  contenido y país compatible), se juntan en uno: sus fuentes quedan como
  alternativas y el repetido se da de baja. Al volver, la página muestra qué
  cambió ("«ES: DAZN 1» → «DAZN 1»", qué se juntó con qué; queda en la sesión).

La verificación programada (cron, cada 6 h) sigue revisando todo.

## Formatos que reproduce la app

| Formato | Ejemplo | App 1.0.0 | App 1.1.0 |
|---|---|---|---|
| HLS | `.../playlist.m3u8` | Sí | Sí |
| Video directo (MPEG-TS, MP4...) | `http://servidor:8080/usuario/clave/123` (listas IPTV) | No | Sí |
| DASH | `.../manifest.mpd` | No | Sí |
| RTSP | `rtsp://...` | No | Sí |
| YouTube (vivos y videos) | `youtube.com/@canal/live`, `youtu.be/...` | No | Sí |
| Página de video | Twitch, Dailymotion, Vimeo, Kick, OK.ru, Facebook... | No | Sí |
| RTMP | `rtmp://...` | No | No (se descarta) |

**YouTube** lo verifica el servidor con yt-dlp (si el canal no está en vivo
ahora, queda caído con ese motivo y "Volver a verificar" lo reactiva cuando
vuelve). Pero lo **resuelve la app en el aparato**: las direcciones de video
de YouTube quedan atadas a la IP de quien las pidió, y si las pidiera el
servidor al celular le darían error. **Las páginas** (Twitch...) las resuelve
el servidor en el momento de reproducir: `GET /api/v1/canales/fuentes/<id>/resolver/`.

yt-dlp hay que **actualizarlo seguido** (los sitios cambian y lo rompen):
`pip install -U yt-dlp` en el servidor (ver `despliegue/README.md`).

La app le dice al servidor qué formatos sabe (`?formatos=hls,dash,directo,rtsp,youtube,pagina`);
la 1.0.0 no dice nada y recibe solo HLS, así no le llegan canales que no
puede abrir.

**Por qué VLC los reproducía y la app no:** las listas IPTV mandan video
directo sin extensión. Antes el verificador exigía HLS (las marcaba caídas)
y la app le decía al reproductor "es HLS". Ahora el verificador mira lo que
llega, guarda el formato real en la fuente, y la app se lo pasa al reproductor.

## Estado de una fuente

| Campo | Quién lo cambia | Para qué |
|---|---|---|
| `activa` | Una persona (admin), o la limpieza | Apagar una fuente a mano aunque funcione ("Quitar esta señal"). La limpieza también la apaga cuando la retira (`retirada`). |
| `retirada` | La limpieza automática | Cuándo la retiró: no anduvo en 7 días y el canal tiene otras que sí. A diferencia de lo apagado a mano, vuelve sola si vuelve a andar. |
| `estado` | La verificación automática | `funciona`, `caida` o `sin_verificar` (si YouTube no dejó verificar desde el servidor, o importada con `--sin-verificar`). |
| `tipo` | La verificación automática | El formato real (ver la tabla de arriba). |
| `codec` | La verificación automática | Códec de video (`h264`, `h265`, `mpeg2`...; `h264_10` / `h265_10` si es de 10 bits), o vacío si todavía no se sabe. En una lista HLS con varias calidades, el **más compatible** (`verificacion.CODECS_DEL_MAS_COMPATIBLE`): el reproductor elige una calidad que el aparato lee. La app esconde una fuente cuyo códec el aparato no lee: en ese aparato el canal no aparece aunque el panel diga "se ve" (el panel de detalles lo avisa, y en la TV lo muestra Mi cuenta → "Lo que no se ve en esta TV"). |

La app recibe una fuente solo si está **activa, no caída y es de un formato
que esa versión reproduce**. Un canal sin ninguna fuente así **no aparece en
la app**. "Volver a verificar todas" (de a tandas, con barra de avance)
reactiva las caídas que volvieron y corrige el formato de las viejas.

**Cómo se presenta el reproductor:** hay canales que rechazan al reproductor
de Android ("ExoPlayer") con error 403 y solo entregan el video a algo que
parece un navegador, y paneles IPTV que solo se lo entregan a VLC. Por eso la
app pide el video con el User-Agent que le manda la API
(`verificacion.USER_AGENT_REPRODUCTOR`, o el propio de la fuente), y el
verificador prueba **igual**; si así lo rechazan, prueba como VLC
(`USER_AGENT_VLC`) y, si anda, lo guarda en la fuente para que la app también
lo use. Si una lista M3U trae `#EXTVLCOPT:http-user-agent=` / `http-referrer=`
o `|User-Agent=...&Referer=...`, se guardan en la fuente (`user_agent`,
`referer`) y se usan siempre.

**Se arregla sola:** cuando la app no puede reproducir una fuente, avisa
(`POST /api/v1/canales/fuentes/<id>/falla/`). El servidor la vuelve a probar
por su cuenta (como máximo una vez cada 5 minutos por fuente) y, si también
le falla, la marca caída: desde la próxima actualización de la lista, la app
ya no la recibe.

**Lo que el servidor ve bien pero los aparatos no:** hay señales que al
servidor le responden pero en los celulares y TV no se reproducen (un formato
de video que el aparato no lee, servidores que aceptan una sola conexión,
otros que rechazan a los reproductores). Por eso la app manda también el
motivo (`{"motivo": "formato" | "rechazo" | "tiempo" | "conexion" | "error",
"detalle"}`). Si en un día avisan **2 aparatos distintos** (o el mismo, con
media hora de diferencia), la fuente se **oculta un rato** aunque al servidor
le ande, y **vuelve sola** (`Fuente.oculta_hasta`, `veces_oculta`,
`falla_en_aparatos`; ver `servicios.registrar_falla_en_aparato`):

- la primera vez, **3 horas** (casi siempre es un corte pasajero del canal: pasó con Disney);
- si al volver sigue fallando, **1 día**; desde la tercera, **una semana** (`models.OCULTA_POR`);
- si los aparatos no pueden leer el formato, directo una semana (no es pasajero);
- en cuanto un aparato la **ve bien un minuto**, se olvida todo: si estaba
  oculta vuelve ya, y la próxima falla empieza otra vez por 3 horas
  (`servicios.registrar_estabilidad`, `VISTO_PARA_PERDONAR`).

En Organizar contenido el canal aparece como "Oculto un rato porque no se
reproduce en los aparatos (motivo). Vuelve solo a la app el 14/10 a las 18:00".
Nadie tiene que hacer nada. Si falla porque el aparato no tiene internet, la
app no avisa. Y la app ya no esconde por su cuenta un canal que no conecta
(desde la 1.2.19): solo lo que ese aparato no sabe mostrar (formato).

Las **caídas** (las que tampoco le andan al servidor) también vuelven solas:
la verificación programada (`verificar_fuentes`, cada 6 horas) las prueba de
nuevo y las que andan pasan a "funciona".

**Destacado en la TV** (`Canal.destacado`): se marca en Organizar contenido →
Editar ("★ Destacado en la TV"; en una serie se marcan todos sus capítulos) o
en la página del canal. La API lo manda (`destacado`) y el modo reposo de la
TV lo muestra más seguido que lo que sale al azar, sin que salga siempre
(ver `app_movil/lib/tv/reposo.dart`). En Organizar, "Mostrar → Destacado en la
TV (★)" lista lo marcado, y la tarjeta lleva una ★.

**La mejor fuente, primera:** la app arranca por la primera fuente de cada
canal, así que el servidor las manda ordenadas (`consultas.ordenadas_por_estabilidad`):

1. **Al final, las que se cortan** en los aparatos. Al dejar de ver una
   fuente, la app cuenta cuánto la vio y cuántas veces se cortó (se frenó a
   cargar, o se cayó y se reconectó): `POST /api/v1/canales/fuentes/<id>/estabilidad/`
   (`{"segundos", "cortes", "proporcion"}`, desde la app 1.2.16). Se suma en
   `Fuente.segundos_en_aparatos` / `cortes_en_aparatos`, sin saber quién;
   pasadas las 10 h vistas lo viejo pesa la mitad (`servicios.registrar_estabilidad`).
   Con 10 minutos vistos y 6 cortes por hora o más, "se corta".
2. **Primero, las que llenan la pantalla:** las "cuadradas" (4:3, con franjas
   negras a los costados) van después. Lo cuenta la app (`proporcion`, ancho
   / alto de lo que dibuja: `Fuente.proporcion`).
3. **Lo que midió la prueba a fondo** (`Fuente.alto` y `velocidad`): las que
   andan antes que las sin verificar; las que llegan sobradas (x1,5 o más)
   antes que las no medidas, y esas antes que las que llegan justas; a igual
   fluidez, la de mejor imagen (1080p antes que 720p).
4. Las que ya se vieron bien un rato antes que las que todavía no se vieron.
5. La prioridad del panel (el orden en que se cargaron).

"Se vio bien" no pasa por delante de la prueba a propósito: si no, la primera
que anduvo quedaría siempre primera y las demás nunca se verían.

**Se miden solas:** la verificación programada (`verificar_fuentes`, cada 6 h
por cron), **de madrugada** (antes de las 7, cuando casi nadie mira y no se
le ocupan conexiones a las listas), además mide a fondo una tanda de 300
fuentes de los canales que tienen más de una (`servicios.medir_fuentes`):
primero las nunca medidas y después las medidas hace más tiempo
(`Fuente.medida`). En unos días quedan todas medidas y se renuevan solas. No
hay que hacer nada a mano (`--medir` lo fuerza a cualquier hora).

En la app, además, cada aparato recuerda la que mejor le anduvo
(`FuentePreferida`) y, si la que está viendo se corta 3 veces en 3 minutos,
pasa sola a otra.

## Salud de las fuentes y limpieza automática (desde el 19/10/2026)

Antes cada fuente se juzgaba por su **última** prueba: un corte de 5 minutos
a las 3 de la mañana pesaba lo mismo que una fuente muerta hace un mes. Con
más de 1000 canales de listas que no se sabe de dónde vienen, revisarlos a
mano es imposible. Ahora cada fuente tiene **memoria** (`salud.py`):

| Campo de `Fuente` | Qué guarda |
|---|---|
| `historial` | Sus últimas 20 pruebas, una letra cada una (la más nueva al final): `+` anduvo en el servidor, `*` se vio bien en un aparato, `-` falló en el servidor, `x` falló en un aparato, `f` un aparato no pudo leer el video, `?` el servidor no pudo saber. |
| `anduvo` | La última vez que anduvo (el servidor la vio bien, o un aparato la miró al menos un minuto). |
| `falla_desde` / `fallas_seguidas` | Desde cuándo falla **sin parar** y cuántas veces falló en ese tiempo. **Cualquier vez que anda, vuelven a cero.** |
| `por_que_falla` | El motivo de la última falla: `no_existe`, `rechaza` (cuenta vencida, ocupada o bloqueada), `tiempo`, `conexion`, `formato` o `error`. |

**De dónde salen las pruebas (todo automático):** la verificación del cron
(cada 6 h), la que dispara un aviso de la app, y lo que cuentan los aparatos
al ver una fuente (`/estabilidad/`, un minuto o más = anduvo) o al no poder
(`/falla/`). Lo de los aparatos entra al historial como mucho una vez cada
media hora por fuente: si cien personas miran el mismo canal, no tapa al
servidor. Cuando el servidor **no puede saber** (los paneles Xtream bloquean
al VPS) anota `?`, que no cuenta ni a favor ni en contra: ahí deciden los aparatos.

**Los estados** (un canal está como su MEJOR fuente prendida):

| Estado | Cuándo |
|---|---|
| Anda | Anduvo, y no falla seguido. |
| Inestable | De sus últimas 12 pruebas, anduvo alguna y falló al menos 2 (1 de cada 4 o más): a veces sí, a veces no (hora pico, proveedor saturado). |
| Sin datos | Nadie la vio todavía y el servidor no puede probarla. |
| Formato | La señal anda, pero algunos aparatos no pueden leer el video (no es que el link falle: no cuenta para quitar). |
| Rechaza | Está fallando y el servidor de la señal la rechaza (403, 401, página de error): cuenta vencida, ocupada o bloqueada. |
| Falla | Está fallando, pero hace menos de una semana: puede ser un corte. |
| Muerta | Falla **sin parar hace 7 días** (`DIAS_PARA_QUITAR`) y al menos **8 veces** (`FALLAS_PARA_QUITAR`: a distintas horas, no un solo corte). |

**Limpieza automática** (`salud.limpiar`, la corre `verificar_fuentes` después
de verificar, cada 6 h): un canal cuyas fuentes prendidas están **todas
muertas** se quita de la app con el motivo ("Limpieza automática: ninguna
fuente anduvo en 7 días (la dirección ya no existe)..."). **Nunca se borra
nada**: el servidor lo sigue probando y, si alguna fuente vuelve a andar, el
canal **vuelve solo**. Lo que se quitó a mano no lo toca. "Volver a mostrar"
le da otra semana entera (`salud.olvidar_fallas`). Queda anotado en la
Actividad qué se quitó y qué volvió.

**Señales sueltas (desde el 19/10/2026):** si un canal sigue andando con
otras señales, la que está muerta no lo tira: se **retira** sola
(`salud.retirar_senales`, `Fuente.retirada`): queda apagada, la app ya no la
recibe ni pierde tiempo probándola. El servidor (y el modo revisión) la sigue
probando y, si vuelve a andar, **vuelve sola** (`salud.devolver_senales`).
Si después mueren también las otras, se quita el canal entero, y vuelve con
cualquiera que reviva. Lo apagado a mano no vuelve solo. Borrar es siempre a
mano.

**Cada señal, a mano** (Organizar contenido → Detalles; `views_revisar.fuente_accion`,
`/canales/fuentes/<id>/accion/`), aunque el canal se vea:

- **Probar ahora**: el servidor la prueba en el momento (si estaba retirada y anda, vuelve).
- **Quitar esta señal**: la app deja de usarla (como apagarla a mano; no vuelve sola). No se borra.
- **Volver a mostrar esta señal**: aparece si está apagada, retirada, caída,
  oculta por los aparatos o fallando. Se prende, deja de estar escondida, si
  estaba caída queda "sin verificar" y se le da otra semana entera.
- **Borrar esta señal** (ya estaba): para siempre.

**Por qué no conecta** (`Fuente.problema_en_aparato` y `problema_en`): cada
vez que la app no puede reproducir una señal, manda el detalle técnico (qué
pasó, el error del reproductor, a los cuántos segundos de empezar a conectar,
si llegó imagen, si venía andando: `ControlSenal.detalleDeLaFalla`, app
1.2.31). El servidor lo guarda SIEMPRE (`servicios.anotar_problema`, también
lo que encuentra el modo revisión) y no se borra cuando vuelve a andar: en
Detalles cada señal muestra **"Último problema en un aparato (fecha): ..."**.
Por ejemplo: "la transmisión terminó: el servidor de la señal la cortó · a
los 1,2 s de empezar a conectar · llegó imagen 1920x1080" (el servidor corta;
suele ser la regla de una conexión por cuenta) o "Response code: 403" (rechaza
al aparato).

En Organizar, **Mostrar → "Se ve, pero tiene señales que no andan"** lista
esos canales, y su tarjeta dice "Se ve en la app · 2 de 4 señales". "Volver a
mostrar" de un canal entero también devuelve sus señales retiradas.

Las fuentes que hoy funcionan arrancaron con `anduvo` en su última
verificación (migración 0026). Las caídas arrancan de cero: nada se quita por
datos de antes; la primera limpieza posible es una semana después de desplegar.

**Dónde se ve:** en Organizar contenido → panel de detalles, el canal tiene
la fila **Salud** y cada señal su línea "Salud: Falla hace 2 días (no
responde a tiempo). Si sigue así hasta el 26/10, se da por muerta. Últimas
pruebas: ✓✓✗✗." La salida del cron (`/var/log/kairostv-cron.log`) dice cuántos
quitó, cuántos volvieron y cuántos canales hay en cada estado.

### Para revisar (la bandeja del panel)

`/canales/revisar/` (Contenido → Tu catálogo → **Para revisar**; `bandeja.py`):
SOLO lo que necesita una decisión, por sección (En vivo, Películas, Series...),
con **lo más visto por los clientes en 30 días primero** y la acción ahí mismo:

| Grupo | Acciones |
|---|---|
| El proveedor los rechaza | Quitar · Dejar así |
| Fallan ahora (todavía no pasó la semana) | Probar de nuevo (el servidor, en el momento) · Quitar · Dejar así |
| A veces andan y a veces no | Quitar · Dejar así |
| Algunos aparatos no los pueden leer | Dejar así · Quitar |
| Los quitó la limpieza | Volver a mostrar |
| Señales retiradas (el canal sigue andando con otras) | Volver a mostrar · **Borrar las retiradas** (para siempre; las direcciones quedan en la Actividad) |

Cada grupo muestra 10 (con "Ver los N") y tiene la acción para todos juntos.
En Series cada caso es una serie (sus capítulos en ese estado). **Dejar así**
(`Canal.revisado`) lo saca de la bandeja mientras siga en ese estado; si
cambia, vuelve a aparecer. "Sin datos" no se lista (son muchos y no hay nada
que decidir): los prueba el modo revisión.

**Cómo está cada lista:** las fuentes de la sección según la lista de donde
vinieron (andan, fallan, muertas, sin datos, apagadas), las más caídas
primero; "Casi toda caída" desde el 50 % (con 10 fuentes o más). **Apagar
todas** apaga todas las fuentes de esa lista (los canales con otra fuente
buena siguen andando); **Volver a prender** lo deshace (prende también las que
se habían apagado de a una). El nombre de la lista abre Organizar filtrado por ella.

### El modo revisión (en la app)

Un usuario del panel con permiso para cargar canales deja una TV o un celular
**en una casa** recorriendo los canales solo (app 1.2.30: celular → Mi Espacio
→ Revisar canales; TV → Mi cuenta). Es lo que el servidor no puede hacer con
los Xtream: desde una casa entregan la señal. `recorrido.py` le da las
próximas fuentes (en vivo primero; dentro de eso, lo quitado o retirado por
la limpieza, lo que falla, lo nunca visto y lo demás; ni YouTube ni páginas, ni lo que un
cliente vio andar en 12 h, ni lo que ya probó en 20 h) y anota lo que
encontró en la salud (`Fuente.recorrida`). Si anda una fuente de un canal
quitado por la limpieza, el canal vuelve en el momento; si el servidor la
tenía caída (no la podía ver), pasa a "sin verificar" para que la app la
intente. La app va de a una y suelta la conexión antes de la siguiente (ver
`app_movil/lib/revision/README.md`).

## Formato M3U (resumen)

```
#EXTINF:-1 tvg-id="Canal26.ar" tvg-logo="https://..." tvg-chno="26" group-title="Noticias",Canal 26
https://servidor/canal26/main.m3u8
```

| Atributo | Se guarda en |
|---|---|
| texto después de la coma / `tvg-name` | `Canal.nombre` (limpio: sin prefijo de país ni calidad) |
| `tvg-logo` | `Canal.logo` |
| `group-title` | `Categoria` |
| `tvg-chno` | `Canal.numero` |
| `tvg-id` | `Canal.tvg_id` (para la guía, más adelante) |
| `tvg-country` | `Canal.pais` (si no viene, se estima) |
| `tvg-language` | `Canal.idioma` (si no viene, se estima por país, categoría o prefijo) |
| segunda línea | `Fuente.url` |
| `#EXTVLCOPT:http-user-agent` / `http-referrer`, o `\|User-Agent=` / `Referer=` | `Fuente.user_agent` / `Fuente.referer` |

## Pendiente (próximas etapas)

- Qué canales ve cada cliente según su plan / créditos.
- Secciones de películas y series en la app (agrupar capítulos por serie y temporada).
- Guía de programación (EPG) con el `tvg-id`.
