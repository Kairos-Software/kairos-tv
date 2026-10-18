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

## Archivos

| Archivo | Qué contiene |
|---|---|
| `css/kairos.css` | **El único CSS del panel.** El mismo sistema de diseño que la app (`diseno_kairos_tv/DESIGN.md`): colores, letras, radios y todas las piezas de las pantallas. |
| `js/sistema.js` | Comportamiento general: menú en celulares, mostrar/ocultar contraseña, el "momento" (hora en vivo, saludo y línea del día) y las iniciales cuando el logo de un canal no carga. |
| `js/tandas.js` | Corre una tarea larga de a tandas (llama al servidor una y otra vez y pinta el avance). Lo usan las pantallas de canales para verificar listas grandes sin saturar el servidor. |
| `js/trabajos.js` + `css/trabajos.css` | El aviso de trabajos pesados en curso, arriba de todas las pantallas (`templates/parciales/_trabajos.html`, `core/trabajos.py`). Aparte de `kairos.css` para no pisar su diseño. |
| `js/mantenimiento.js` + `css/mantenimiento.css` | Contenido → Mantenimiento del catálogo: "Qué revisar" (una sección o una lista importada), verificar de a tandas y el resultado (qué se cayó y qué volvió). Solo los carga `canales/inicio.html` (con `tandas.js`). |
| `js/organizar_detalle.js` + `css/organizar_detalle.css` | Organizar contenido: el **panel de detalles** que se abre al costado con el botón "Detalles" de una tarjeta (elegirla no lo abre) (todos sus datos y cada señal con su link, de qué lista salió, cómo anda, y "Borrar esta señal"). `KairosSenales.pintar` dibuja las señales también en el cuadro Editar. El CSS además acomoda los cuadros Editar y Exportar en el celular. Solo los carga `canales/organizar.html`. |
| `js/ordenar_capitulos.js` + `css/ordenar_capitulos.css` | La lista de capítulos de la página de una serie y cómo se ordena: arrastrar (mouse o dedo) o flechas, barra "Guardar orden / Deshacer", y el aviso de desordenados con su botón. Solo los carga `canales/serie_detalle.html`. |
| `css/importacion_partes.css` | La pantalla de una lista importada por partes (`canales/importacion.html`): las tarjetas de "Qué trae esta lista", la tabla de categorías y los cuatro pasos (probar, revisar, ¿dónde va?, cargar). |
| `js/importacion_destino.js` | El paso "¿Dónde va?" de esa pantalla: muestra el campo de la categoría o serie nueva, pone sola la categoría de una serie que ya existe, muestra "Recordarlo" y dice cómo va a quedar. |
| `js/separar_serie.js` + `css/separar_serie.css` | **Separar en otra serie** (la tarjeta de la página de la serie y `canales/serie_separar.html`): cuenta los tildados, "Tildar / Destildar todos", pregunta antes de separar, y Enter en "o a otra serie" usa "Pasar a esa serie". |
| `js/destino_serie.js` + `css/destino_serie.css` | **"Dónde va" una serie**: 1 Categoría → 2 Serie → 3 Temporada, mostrando lo que ya hay (las series de la categoría con sus temporadas y capítulos, "＋ Una serie nueva", "＋ Nueva: temporada N") y "Va a quedar: Series › … › …". Llena los campos de siempre (`nombre_serie`, `temporada` y la categoría), así el servidor no cambia. Lo usan Traer de YouTube y, en Organizar, "Unir en una sola serie" y "Pasar a Series" (ahí pide las series a `/canales/series/arbol/` recién cuando se abre la acción). El CSS también arma el recuadro "Categoría / Serie / Temporadas" de la página de cada serie. |
| `js/tablas_anchas.js` | Las tablas anchas que se deslizan de costado (`.tabla-ancha-con-fija`, Estadísticas): si no entran, arriba aparece "Deslizá de costado para ver todas las columnas →" (en el celular se veían cortadas sin que se notara que había más). |

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
