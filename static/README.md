# static/

Archivos estáticos generales: los que no cambian y se envían tal cual al
navegador.

## Subcarpetas

| Carpeta | Qué va |
|---|---|
| `css/` | Hojas de estilo generales del sistema |
| `js/` | JavaScript general del sistema |
| `img/` | Logos, íconos y otras imágenes generales |

## Qué NO va acá

- Estáticos propios de una sola app: van en `<app>/static/<app>/`.
- Archivos que suben los usuarios: van en `media/`.

## En producción

`python manage.py collectstatic` junta todos los estáticos (estos y los de
cada app) en la carpeta `staticfiles/`, que es la que sirve nginx. Esa carpeta
se genera sola y no va al repo.

Los archivos se sirven con su mismo nombre, así que un navegador puede seguir
un rato con la copia vieja de un `.js` o `.css`. Por eso Organizar, la página
de una serie, Editar canal, Importar y estado y la de una lista importada los
piden con `?v=20261021` al final (los nuevos dependen del `trabajo.js` nuevo):
**si se cambia alguno de esos archivos, subir ese número en esas cinco
plantillas** (`canales/templates/canales/organizar.html`, `serie_detalle.html`,
`editar.html`, `inicio.html` e `importacion.html`).

## Archivos

| Archivo | Qué contiene |
|---|---|
| `css/kairos.css` | **El único CSS del panel.** El mismo sistema de diseño que la app (`diseno_kairos_tv/DESIGN.md`): colores, letras, radios y todas las piezas de las pantallas. |
| `js/sistema.js` | Comportamiento general: menú en celulares, mostrar/ocultar contraseña, el "momento" (hora en vivo, saludo y línea del día) y las iniciales cuando el logo de un canal no carga. |
| `js/tandas.js` | Corre una tarea larga de a tandas (llama al servidor una y otra vez y pinta el avance). Lo usan las pantallas de canales para verificar listas grandes sin saturar el servidor. |
| `js/trabajos.js` + `css/trabajos.css` | El aviso de trabajos pesados en curso, arriba de todas las pantallas (`templates/parciales/_trabajos.html`, `core/trabajos.py`). Aparte de `kairos.css` para no pisar su diseño. |
| `js/mantenimiento.js` + `css/mantenimiento.css` | Contenido → Mantenimiento del catálogo: "Qué revisar" (una sección o una lista importada), verificar de a tandas y el resultado (qué se cayó y qué volvió). Solo los carga `canales/inicio.html` (con `tandas.js`). |
| `js/organizar_detalle.js` + `css/organizar_detalle.css` | Organizar contenido: **las señales de una tarjeta** (`KairosSenales.pintar`: cada señal con su link, de qué lista salió, cómo anda y sus botones Probar ahora / Quitar / Volver a mostrar / Borrar; al volver de la acción el panel se abre en la misma tarjeta). Las usa el panel de edición. El CSS dibuja esa lista y los datos, y acomoda el cuadro Exportar en el celular. Solo los carga `canales/organizar.html`. |
| `js/organizar_trabajo.js` + `css/organizar_trabajo.css` | **Organizar para trabajar rápido** (`canales/organizar.html`): el **panel de edición** del costado (tocar una tarjeta; guarda sin recargar, Anterior / Siguiente, Ctrl+Enter = guardar y seguir, Esc cierra), la **vista Lista como planilla** (nombre ahí mismo con Enter / Tab, categoría con buscador, ★ y «se muestra» con un toque), **arrastrar una imagen arriba de una tarjeta** (con «Deshacer»), las casillas con Shift, la barra de abajo con **Cambiar nombres** (vista previa), juntar categorías, crear una sección y Exportar. Habla con `canales/views_organizar.py`. |
| `js/imagenes_contenido.js` | **Imágenes sin salir del panel** (`KairosImagenes`): lee lo que se arrastra o pega (archivos, imágenes de otras páginas, links, resultados de Google Imágenes) y arma la tira de sugerencias: las que ya tienen otras cosas con ese nombre en el panel (`/canales/organizar/imagenes/`) y las de Wikipedia. Lo usan Organizar, la página de una serie y Editar canal. |
| `js/serie_trabajo.js` | La página de una serie: portada (buscar, subir, link, arrastrar o pegar), nombre y categoría que se cambian ahí mismo sin recargar, y la imagen de un capítulo arrastrándole una encima. |
| `js/ordenar_capitulos.js` + `css/ordenar_capitulos.css` | La lista de capítulos de la página de una serie y cómo se ordena: arrastrar (mouse o dedo) o flechas, barra "Guardar orden / Deshacer", y el aviso de desordenados con su botón. Solo los carga `canales/serie_detalle.html`. |
| `js/importar_varias.js` + `css/importar_varias.css` | Contenido → **Importar y estado**: la zona de subir (siempre a la vista: se toca o se le sueltan varias listas, y se suben solas, de a una; el servidor responde JSON), cada una con su avance y su "Abrir", las opciones como casillas cortas y el historial con cómo va cada lista. Sin JavaScript, el formulario sube una como siempre. |
| `js/importacion_trabajo.js` + `css/importacion_partes.css` | **La pantalla de una lista importada** (`canales/importacion.html`), para trabajar sin recargar: las partes con su barrita, «Estás trabajando con…» (Probar / Cargar de a tandas), **las categorías** con el próximo paso de cada una, tildar varias y encolarlas («Probar y cargar», «Solo probar», «Cargar lo que pasó», «Descartar» con «Deshacer»; de a una, con «Parar»), y uno por uno con «No cargar» / «Cargar igual» que redibujan solo esa fila. Lo que cambia se redibuja trayendo la página de nuevo (`data-refrescar`). Habla con `canales/views_importacion.py`. |
| `js/importacion_destino.js` | "¿Dónde va?" de esa pantalla: muestra el campo de la categoría o serie nueva, pone sola la categoría de una serie que ya existe, muestra "Recordarlo" y dice cómo va a quedar. Si esa parte se redibuja, se vuelve a armar (`KairosDondeVa()`). |
| `js/separar_serie.js` + `css/separar_serie.css` | **Separar en otra serie** (la tarjeta de la página de la serie y `canales/serie_separar.html`): cuenta los tildados, "Tildar / Destildar todos", pregunta antes de separar, y Enter en "o a otra serie" usa "Pasar a esa serie". |
| `js/destino_serie.js` + `css/destino_serie.css` | **"Dónde va" una serie**: 1 Categoría → 2 Serie → 3 Temporada, mostrando lo que ya hay (las series de la categoría con sus temporadas y capítulos, "＋ Una serie nueva", "＋ Nueva: temporada N") y "Va a quedar: Series › … › …". Llena los campos de siempre (`nombre_serie`, `temporada` y la categoría), así el servidor no cambia. Lo usan Traer de YouTube y, en Organizar, "Unir en una sola serie" y "Pasar a Series" (ahí pide las series a `/canales/series/arbol/` recién cuando se abre la acción). El CSS también arma el recuadro "Categoría / Serie / Temporadas" de la página de cada serie. |
| `js/tablas_anchas.js` | Las tablas anchas que se deslizan de costado (`.tabla-ancha-con-fija`, Estadísticas): si no entran, arriba aparece "Deslizá de costado para ver todas las columnas →" (en el celular se veían cortadas sin que se notara que había más). |
| `js/trabajo.js` + `css/trabajo.css` | Lo que comparten las **pantallas de trabajo de Contenido** (Organizar, Señales, Para revisar, Importar y estado, YouTube, Probar un link, Lo más visto, Eliminados y la página de una serie): la barra de arriba para ir de una a otra (`canales/_barra_contenido.html`), los botones **"?"** con la explicación en una burbuja flotante (popover nativo: se cierra con Esc o tocando afuera) en vez de textos fijos, copiar un link, confirmar antes de borrar (`data-confirmar`: lo hace este archivo, las páginas ya no tienen el suyo), filtrar apenas se elige (`data-enviar-al-cambiar`), la tecla **/** para buscar, tildar filas con Shift y la barra de abajo con lo elegido, **Tarjetas / Lista** en Organizar (queda guardado en el navegador) y cambiar el título de un capítulo ahí mismo. También `KairosTrabajo.pedir` (guardar sin recargar) y `KairosTrabajo.avisar` (los avisos de abajo, con «Deshacer»), y en el CSS las sugerencias de imágenes, la cabecera de una serie y la lista importada más junta. Aparte de `kairos.css` (que se edita en paralelo): solo usa sus colores. En el celular, las tablas de trabajo se ven como tarjetas apiladas. |
| `css/revisar.css` | Contenido → **Para revisar** (`canales/revisar.html`): los números de cada estado, los grupos de casos (borde de color según el motivo) con su acción ahí mismo y la tabla "Cómo está cada lista". |

Librerías externas (se cargan desde CDN en `templates/base_html.html`):
Bootstrap 5.3 (en modo oscuro: `data-bs-theme="dark"`), Bootstrap Icons y las
fuentes Plus Jakarta Sans (títulos) e Inter (todo lo demás), las mismas de la app.

## El CSS del panel (`css/kairos.css`)

Hasta octubre de 2026 había dos hojas (`sistema.css` y `panel-kairos.css`)
con varios rediseños apilados que se pisaban entre sí (textos ilegibles,
datos cortados letra por letra, campos gigantes). Se reemplazaron por esta
sola hoja, ordenada por secciones (el índice está al principio del archivo):

1. Colores y medidas: los tokens de la app en `:root` (fondo `#131317`,
   capas, celeste `#00F0FF`, rubí, dorado), y Bootstrap teñido con ellos.
2. Base · 3. Estructura (menú, barra superior) · 4. Encabezado de página ·
   5. Tarjetas y datos · 6. Botones · 7. Formularios · 8. Tablas y filtros ·
   9. Chips, estados y alertas · 10. Inicio · 11. Acceso · 12. Contenido ·
   13. Reventa, usuarios, actividad... · 14. Celular.

Para sumar una pantalla:

- reutilizá primero `pagina-encabezado`, `tarjeta`, `tarjeta-titulo`,
  `ficha-datos` (etiqueta arriba, dato abajo), `resumen-metricas`, `filtros`,
  `tabla`, `formulario-seccion`, `formulario-acciones`, `vacio` y los chips;
- no inventes colores ni radios: usá las variables de `:root`;
- las tablas, siempre dentro de `table-responsive`;
- revisá la pantalla en celular (390 px) y en escritorio.
