# lib/tv/

La app en la **TV** (Android TV / Google TV), manejada con el control remoto.
El diseño está en `diseno_kairos_tv/` (pantallas `tv-*`, y el recorrido del
control en `DESIGN.md`). Usa los mismos datos, reproductor y colores que el
celular (`lib/movil/datos.dart`, `control_senal.dart`, `estilo.dart`).

**Todo se dibuja en un lienzo de 1920×1080** (las medidas del diseño) y se
escala a la pantalla (`escala.dart`): así se ve igual en cualquier televisor.

| Archivo | Qué es | Diseño |
|---|---|---|
| `escala.dart` | El lienzo de 1920×1080 que se agranda o achica a la pantalla. `TamanioReal`: lo que dibuja Android directamente (el video en superficie, YouTube) no se entera de ese achique y lo armaba al doble; en un canal 4:3 el video quedaba corrido y tapaba la parte derecha de la barra. Lo arma del tamaño real. | — |
| `foco.dart` | `Enfocable`: lo elegido con el control se agranda, con borde celeste y brillo. OK y **OK largo** (mantener apretado); el OK cuenta solo si se apretó ahí (si no, el OK que abre una sección también abría lo primero). `BotonTv`. | "Foco TV" |
| `piezas.dart` | Encabezado, chips, tarjetas de canal y de póster, filas, avisos cortos, favoritos con OK largo. | todas |
| `estructura.dart` | El menú de la izquierda (se abre al entrar en él) y las 8 secciones, más las que se crean en el panel (Música, Radio...: `SeccionTv.nueva`, después de Series; "en vivo" se ve como En vivo y "a demanda" como Películas). Si hay muchas, el medio del menú se desplaza. "Atrás" vuelve a Inicio; en Inicio pregunta si salir. "Volver al último canal" con cuenta regresiva. Cuida que el foco nunca quede "en el aire" (si cae en la pantalla en general, lo pasa al contenido; si igual se pierde, la primera tecla lo recupera). Cuenta el tiempo sin tocar el control para el modo reposo. | `tv-20` |
| `reposo.dart` | El modo reposo (una "vidriera" de publicidad de Kairos TV): al minuto sin tocar el control (y sin nada reproduciéndose) pasan escenas: el logo con la hora sobre el escenario de neón, **estrenos**, **cifras** ("+1.000 películas · +400 series..."), **canales en vivo**, **series**, y entre cada una un título del catálogo en grande. Todo sale del catálogo del momento (nunca queda viejo). **Destacados:** lo que en el panel se marca "★ Destacado en la TV" sale más seguido que lo que sale al azar, pero no siempre: uno de cada tres títulos es un destacado (cada uno hasta dos veces por vuelta, nunca seguidas; `intercalarDestacados`) y en los grupos de series y canales van primero. Cada escena dura 12 segundos. **Al entrar baja y prepara todas las imágenes** (mientras se ve el logo): las chicas no se usan, y si no hay suficientes buenas, la escena se saltea (mejor no mostrarla que pixelada). Para que no se trabe en un TV box: las escenas solo muestran imágenes ya listas (nunca cargan nada al aparecer), hay un solo escenario de fondo para todas y, al cambiar, la escena que se va se apaga antes de que aparezca la otra (nunca se dibujan dos a la vez). Cualquier botón vuelve a donde se estaba. | — |
| `escenario.dart` | `EscenarioNeon`: el fondo de la marca (pasillo con paneles de neón, arcos, piso que refleja y punto rubí, como la pantalla de carga v2) **dibujado**, no una imagen, y animado despacio. Se dibuja UNA vez, como dos fotos (a pleno y tenue), y en cada cuadro solo se mezclan: dibujarlo entero 60 veces por segundo (unos 30 difuminados) trababa los TV box. Lo usa el modo reposo. | — |
| `inicio.dart` | Portada con un canal en vivo, favoritos, últimos vistos, continuar viendo, una fila por categoría, películas y series. | `tv-04` |
| `en_vivo.dart` | Los canales como tarjetas: una fila por categoría, o la grilla de una categoría. | `tv-05` |
| `guia.dart` | Categorías a la izquierda, todos los canales en lista a la derecha. Derecha desde las categorías va al último canal elegido de esa categoría (o al primero); Izquierda desde los canales, a la categoría elegida. Los números del control saltan a un canal. | `tv-06` |
| `grilla.dart` | Películas y Series: chips y grilla de pósters. | `tv-08`, `tv-09` |
| `detalle.dart` | Detalle de película (Reproducir/Continuar, Favoritos, similares) y de serie (temporadas y episodios con lo visto). | `tv-10`, `tv-11` |
| `reproductor.dart` | En vivo: un cartel con el canal que solo informa (Atrás sale directo); **OK abre la guía** encima del video (parada en el canal actual); ↑ ↓ zapping como en la guía (↑ el canal de arriba, ↓ el de abajo) y CH+/CH- como en cualquier TV (CH+ sube el número); ← → las opciones (guía, canal anterior / siguiente, favoritos, **Ajustes**: calidad, idioma, imagen y fuente); números. Películas y capítulos: OK pausa; ← → ±10 s; ↑ ↓ la barra (siguiente episodio, favoritos, Ajustes): ← → de botón en botón, ↓ la línea de tiempo y ↑ vuelve a Pausa. Lo que se abre lleva el foco a su primer botón, se cierra con Atrás o solo. **La barra** (`_PanelControles`): un degradé que sube desde abajo, botones redondos que con el foco se llenan de celeste y muestran qué hacen, insignias de la señal (CANAL N, FULL HD / HD / SD, 4:3, SEÑAL 2/3) y la ayuda con las teclas dibujadas. Error de señal con "Probar de nuevo". Las de YouTube oficial (`ReproductorYoutubeTv`) se manejan igual (sin Ajustes: la calidad la elige YouTube, con el tope que aguanta cada TV: `movil/calidad_youtube.dart`; con botón **Subtítulos**, que pasa de castellano a los otros idiomas y a ninguno; el audio sale en castellano si el video lo tiene (aunque el "original" sea el inglés) y, si tiene más de un audio, aparece el botón **Idioma**: lo hace un script que Android mete en el reproductor de YouTube, `scriptDentroDeYoutube`; y el WebView nunca se queda con el foco del control: ver `MainActivity.kt`) y, mientras se ven, no queda nada dibujado encima del video. | `tv-12`, `tv-13`, `tv-19` |
| `buscar.dart` | Teclado en pantalla a la izquierda y resultados a la derecha, con los filtros Todo / En vivo / Películas / Series (arranca en el de la sección desde donde se vino). DERECHA desde el borde del teclado va al primer resultado; IZQUIERDA vuelve al teclado. Abajo del teclado lo dice. | `tv-14` |
| `favoritos.dart` | Canales, películas y series guardados; vacío: "Explorar contenido". | `tv-15`, `tv-21` |
| `cuenta.dart` | Datos de la cuenta y preferencias (volver al último canal, modo de video "TV" o "compatible" por si la imagen sale verde, buscar actualizaciones, cerrar sesión). **"Lo que no se ve en esta TV"** (`CuadroLoQueNoSeVe`, desde la 1.2.20): lo que el panel manda pero esta TV esconde y por qué (falló acá, o "esta TV no lee H.265 de 10 bits"), qué códecs lee la TV, "Volver a mostrar lo que falló acá" y "Probar igual lo que quizá no lea" (`Biblioteca.probarTodo`). Para cuando algo está en el celular y no en la TV (pasó con Next). | `tv-16` |

El login, "Tu servicio venció" y la carga son los mismos del celular
(`lib/acceso.dart`), que en pantalla ancha se parten en dos columnas.

## El control remoto

| Tecla | Qué hace |
|---|---|
| Flechas | Moverse. Izquierda en el borde izquierdo del contenido abre el menú (parado en la sección actual); Derecha vuelve al contenido. |
| OK | Abrir, reproducir, confirmar. |
| OK largo | Agregar o quitar de favoritos (sobre una tarjeta). |
| Atrás | Cierra lo que esté abierto (también el menú); en una sección vuelve a Inicio; en Inicio pregunta si salir. |
| Arriba/Abajo, CH+/CH- (viendo un canal) | Zapping. |
| OK o Guía (viendo un canal) | La guía de canales encima del video. |
| Izquierda/Derecha (viendo un canal) | Las opciones: guía, favoritos, fuente. |
| Números (viendo un canal o en la guía) | Ir al canal con ese número. |
| Play/Pausa, adelantar, atrasar | En películas y capítulos. |
