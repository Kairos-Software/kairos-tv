# windows/

**Kairos TV para PC (Windows 10 y 11 de 64 bits)**: la misma app de Flutter que
la APK, armada como programa de escritorio (`KairosTV.exe`). Esta carpeta es la
parte propia de Windows: el programa que abre la ventana (`runner/`, en C++),
cómo se compila (`CMakeLists.txt`) y el instalador (`instalador/`). Lo generó
`flutter create --platforms=windows`; lo nuestro es el nombre ("Kairos TV",
`KairosTV.exe`), el ícono (`runner/resources/app_icon.ico`, sacado de
`assets/logo/icono.png`) y lo de abajo.

## La ventana (`runner/`)

- **Abre maximizada**; al achicarla queda de 1280×720 y no se puede hacer más
  chica que 960×540 (el diseño de la tele quedaría ilegible).
- **Una sola abierta** (`main.cpp`): si se abre otra vez, se trae adelante la que
  ya estaba. Su marca ("KairosTVAbierta") le avisa al instalador que la app
  sigue abierta.
- **Pantalla completa** de verdad, sin bordes ni la barra de título (cerrar,
  minimizar...) y tapando la barra de tareas (`flutter_window.cpp`, canal
  `kairos/ventana`). La piden los reproductores mientras están abiertos; F11, el
  botón de arriba del reproductor o doble clic en el video la cambian.
- La **versión** instalada es la que se le da al armarla
  (`--build-name`/`--build-number`, ver `instalador/`), y también la lee la app
  por ese canal.

## Qué cambia en la PC (lo que pregunta por `Aparato.esPc`)

- **El diseño**: el de la tele (`lib/tv/`), escalado a la ventana (nunca más bajo
  que el diseño: en una ventana apaisada, más ancho; `tv/escala.dart`).
- **El mouse** (`tv/foco.dart`, `lib/pc.dart`): lo que se señala queda elegido
  (el mismo resaltado que con el control), clic = OK, clic derecho = OK largo
  (favoritos). Las filas de tarjetas muestran flechas a los costados al pasar el
  mouse (`TiraTv`) y las listas se arrastran. Mover el mouse cuenta como usar la
  app (si no, aparecía el modo reposo); en el reposo, moverlo vuelve.
- **El teclado**: flechas y Enter como el control; **Esc** es "Atrás" (también
  el botón "atrás" del costado del mouse); **F11**, pantalla completa. En el
  login se escribe con el teclado: Enter entra (o pasa a la contraseña) y Tab
  cambia de campo. Las ayudas de la pantalla nombran estas teclas.
- **El reproductor** (`tv/reproductor.dart`, `_ConMouse`): al mover el mouse
  aparecen la barra y, arriba a la derecha, Pantalla completa y Salir; con el
  mouse quieto 3 s se esconden y el puntero desaparece. Clic en el video:
  pausa (en vivo, las opciones); doble clic: pantalla completa o ventana. La
  línea de tiempo se toca o se arrastra. La barra espaciadora pausa.
- **El video**: media_kit (mpv) en vez del reproductor de Android, con tres
  arreglos nuestros: ver `paquetes/README.md` ("video_player_media_kit").
- **Salir** (en Inicio) cierra la app.
- **Se actualiza sola** desde el panel, como la APK (`lib/actualizacion.dart`,
  `/api/v1/app-pc/`): ver `instalador/README.md`.
- **El servidor**: el de producción (en Windows no hay versión "local").
- Lo que es solo de Android no se usa: "Ver en la tele", Cronet, los avisos de
  "Mi agenda". Las películas y series de **YouTube oficial** y las señales
  **web** no se piden (`FuenteCanal.formatosQueReproduce`): en Android las abre
  el navegador de Android (WebView), que en Windows no hay.

## Armarla

Hace falta, una vez por PC:

- **Visual Studio 2022** con "Desarrollo para el escritorio con C++"
  (`flutter doctor` dice si falta).
- **Modo para programadores** de Windows prendido (Configuración → Sistema →
  Para programadores): Flutter lo necesita para los complementos (el reproductor).

Y armarla **desde una letra de unidad corta**: la carpeta del proyecto tiene una
ruta larga y el reproductor arma carpetas muy hondas; pasan las 260 letras que
acepta Visual Studio y falla ("supera el límite máximo para la ruta de acceso").

```powershell
subst K: "D:\Desktop\migracion\KAIROS SOFTWARE SISTEMAS\KAIROS TV\kairos-tv"
cd K:\app_movil
flutter build windows --release
```

Sale en `build\windows\x64\produccion\runner\Release\` (`KairosTV.exe` con sus
DLL y la carpeta `data\`: va todo junto). `subst` se borra al reiniciar la PC.
Para repartirla, el instalador: `instalador\armar.ps1` (hace todo esto solo).

## Falta

- Las películas y series de YouTube oficial y las señales web (haría falta el
  navegador de Windows, WebView2).
- La firma digital (sin ella Windows y algunos antivirus avisan al instalar):
  para más adelante.
