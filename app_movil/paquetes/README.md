# paquetes/

Copias de paquetes de Flutter con algún cambio nuestro. `pubspec.yaml` las usa
en lugar de las originales (sección `dependency_overrides`).

## video_player_android/ (2.12.2)

El reproductor de video de Android (ExoPlayer) que usa `video_player`. Es el
paquete oficial **con seis cambios**: el buffer, el margen en vivo, el idioma
del audio, lo de la tele conectada, la espera de los canales Xtream y el audio
MP2 (que Android no trae).

### 1. El buffer

- De fábrica ExoPlayer arranca apenas tiene **2,5 segundos** de video cargados.
  Si la señal se frena un momento, el video se corta enseguida.
- Acá arranca recién con **5 segundos** cargados, y después de un corte
  espera de nuevo a tener 5 s antes de seguir. Así un microcorte de la señal
  no se nota (el video sigue con lo que tiene guardado mientras llega más).
- El costo: un canal puede tardar un poquito más en empezar (lo que tarde en
  juntar esos 5 s; con una buena señal, casi nada).

El cambio está en `android/src/main/java/io/flutter/plugins/videoplayer/texture/TextureVideoPlayer.java`
y en `.../platformview/PlatformViewVideoPlayer.java` (buscar "Kairos TV").
Para cambiar los segundos, tocar `bufferForPlaybackMs` y
`bufferForPlaybackAfterRebufferMs` en los dos archivos.

### 2. El margen en vivo (30 segundos)

- Un canal en vivo HLS (`.m3u8`) es una lista de pedacitos de video que el
  servidor va publicando. De fábrica ExoPlayer mira ~3 pedacitos detrás del
  último, así que tiene guardados muy pocos segundos: si internet o el
  servidor se frenan un rato más que eso, el video se corta.
- Acá se mira **30 segundos detrás del vivo**. Esos 30 s ya están publicados,
  se bajan enseguida y quedan guardados: un frenazo de hasta ese tiempo no se
  nota. Arrancar no tarda más (arranca igual con 5 s cargados).
- El costo: el canal va unos 30 s atrasado respecto de la transmisión real
  (en un partido, el vecino grita el gol antes).
- Si la lista del canal guarda menos de 30 s, ExoPlayer usa lo que haya. No
  cambia nada en películas, series ni en videos directos (`.ts`, `.mp4`).

Está en `.../videoplayer/HttpVideoAsset.java`, `KAIROS_ATRAS_DEL_VIVO_MS`
(buscar "Kairos TV").

### 3. El audio en español

- Muchas películas traen dos audios (por ejemplo inglés y latino). De fábrica
  ExoPlayer arranca con el que el archivo marca como "principal", que suele
  ser el idioma original: la película se escuchaba en inglés aunque trajera
  el latino.
- Acá se le pide el español (`setPreferredAudioLanguages("es")`): si el video
  lo trae, arranca con ese. Si no lo trae, no cambia nada. Entiende las
  distintas formas de anotarlo ("es", "spa", "es-419"...).
- Elegir otro idioma a mano desde ⚙ sigue andando igual (esa elección manda).

Está en los mismos dos archivos, justo después de crear el `DefaultTrackSelector`
(buscar "Kairos TV").

### 4. Con una tele conectada ("Ver en la tele")

- Cuando el celular usa una tele como pantalla (`app_movil/lib/tele/`), baja
  el canal y a la vez le manda la imagen a la tele, por el mismo WiFi. Con
  1080p no alcanzaba y se trababa y pixelaba.
- Mientras hay tele, el video no pasa de **720p** (sigue eligiendo solo la
  calidad según internet, por debajo de eso) y después de un corte junta
  **8 segundos** antes de seguir (sin tele, 5). En la tele casi no se nota la
  diferencia: Android igual vuelve a comprimir la imagen para mandarla.
- Lo pone y lo saca `PantallaTele.kt` con `KairosTele` (archivo nuevo,
  `android/src/main/java/io/flutter/plugins/videoplayer/KairosTele.java`).
  Los dos reproductores lo usan para el buffer (`KairosTele.buffer()`) y el
  tope (`KairosTele.aplicarTope`). Vale para los videos que se abren con la tele ya
  conectada. Elegir una calidad a mano en Ajustes sigue mandando.

### 5. Canales Xtream en vivo (video directo `.ts`)

- Los canales de una lista Xtream son MPEG-TS que llega de corrido
  (`.../live/usuario/clave/123.ts`). El servidor primero **redirige** a otro
  (otra IP, puerto 8080, con un token) y a veces tarda **más de 12 segundos**
  en mandar lo primero.
- De fábrica ExoPlayer espera **8 s** a conectar y 8 s a que lleguen datos: se
  rendía con "Source error" aunque VLC (que espera más) lo viera. Acá espera
  **25 s** a conectar y **30 s** a leer (`KAIROS_ESPERA_CONEXION_MS`,
  `KAIROS_ESPERA_LECTURA_MS`).
- Una dirección que termina en `.ts` (sin pista de formato) se abre como
  **MPEG-TS** (`video/mp2t`, `kairosMimeDirecto`), nunca como HLS.
- Las redirecciones (también de https a http) las sigue el mismo
  `DefaultHttpDataSource`, que en cada una vuelve a mandar el User-Agent (el de
  VLC que manda la API) y las demás cabeceras.
- Del lado de Dart (`lib/movil/control_senal.dart`): un canal en vivo
  `directo` espera **40 s** a arrancar (HLS sigue en 15) y, si no arranca, se
  cierra, se espera 1 s y se prueba **la misma una vez más** antes de pasar a
  otra fuente; recién ahí se le avisa al servidor. Nunca hay dos conexiones a
  la vez.

Está en `.../videoplayer/HttpVideoAsset.java` (buscar "Kairos TV"). Tests:
`android/src/test/.../KairosHttpVideoAssetTest.java` (se corren con
`gradlew :video_player_android:testDebugUnitTest` desde `app_movil/android`) y
`app_movil/test/arranque_directo_test.dart`.

### 6. El audio MP2 (desde la app 1.2.31)

- **MP2** (MPEG audio capa 2, "MPEG Audio layer 1/2" en VLC) es el audio
  clásico de los canales de cable y satélite. **Android no trae decodificador
  para él** (la lista oficial de Android: AAC, MP3, Opus, Vorbis... pero no
  MP2 ni AC3): el canal se veía **sin sonido**. VLC sí suena porque trae los suyos.
- Acá la app trae el suyo: **minimp3**, de **dominio público** (CC0: se puede
  usar en una app comercial sin ninguna obligación; ver
  `android/src/main/cpp/minimp3-LICENSE.txt`). Decodifica MP1, MP2 y MP3 a PCM.
  Pesa unos 150 KB por arquitectura.
- Se usa **solo** para MP1 / MP2 y **solo si el aparato no trae uno propio**:
  `KairosRenderersFactory` lo agrega DESPUÉS de los de Android, y el
  reproductor usa el primero que sabe leer cada audio. Si la biblioteca nativa
  no carga, no se agrega y todo sigue como antes (se ve, sin sonido). Un cuadro
  roto sale en silencio, no corta el video.
- Archivos: `android/src/main/cpp/` (`minimp3.h`, `kairos_audio.c` y su
  puente `kairos_audio_jni.c`, `CMakeLists.txt`: lo compila Gradle con el
  NDK), `KairosAudioMpeg.java` (el decodificador), `KairosAudioRenderer.java`,
  `KairosRenderersFactory.java` (lo usan los dos reproductores, buscar "Kairos
  TV") y `kairos-proguard.pro` (que R8 no renombre las funciones nativas).
- **AC3 / E-AC3 (Dolby)** no: necesita FFmpeg, y la versión ya compilada que
  hay (Jellyfin) es GPL (obligaría a publicar el código de la app). Si hace
  falta, compilar FFmpeg LGPL solo con esos decodificadores.

Tests: `android/src/test/cpp/kairos_audio_prueba.c` (el decodificador, en la
compu: `gcc -O2 -I ../../main/cpp kairos_audio_prueba.c ../../main/cpp/kairos_audio.c -o prueba && ./prueba tono_440hz.mp2`;
sale igual que ffmpeg) y `android/src/test/.../KairosAudioRendererTest.java`
(que se use solo para MP1/MP2 y después del de Android).

**Si algún día se actualiza `video_player`** y pide una versión más nueva de
este paquete: copiar la nueva de `%LOCALAPPDATA%\Pub\Cache\hosted\pub.dev\video_player_android-X.Y.Z`
(carpetas `lib/` y `android/`, `pubspec.yaml`, `LICENSE`), volver a aplicar los
seis cambios (con los archivos nuevos `Kairos*.java`, `src/main/cpp/` y lo de
`build.gradle.kts`: `externalNativeBuild`, `ndkVersion` y `consumerProguardFiles`)
y sacar `dev_dependencies` de su `pubspec.yaml`.
