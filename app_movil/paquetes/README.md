# paquetes/

Copias de paquetes de Flutter con algún cambio nuestro. `pubspec.yaml` las usa
en lugar de las originales (sección `dependency_overrides`).

## video_player_android/ (2.12.2)

El reproductor de video de Android (ExoPlayer) que usa `video_player`. Es el
paquete oficial **con diez cambios**: el buffer, el margen en vivo, el idioma
del audio, lo de la tele conectada, la espera de los canales Xtream, el audio
MP2 (que Android no trae), la reconexión sola de los canales que se cortan, el
audio Dolby y DTS, adelantar en las películas MKV sin índice, y el decodificador
de video trabado (con el diagnóstico de por qué una señal no arranca).

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
- De fábrica ExoPlayer espera 8 s a que lleguen datos: con canales en vivo se
  rendía con "Source error" aunque VLC (que espera más) lo viera. Acá espera
  **30 s** a leer en vivo (`KAIROS_ESPERA_LECTURA_MS`).
- **Conectar: 5 s y reintentar enseguida** (desde la app 1.2.36,
  `KAIROS_ESPERA_CONEXION_MS`, `KairosReintentoRapido.java`). Medido el
  21/10/2026 con curl contra un proveedor Xtream: **3 de cada 7 intentos de
  conexión no los atendía** (al azar, no por pedir rápido; una sola IP) y,
  cuando atendía, el primer dato llegaba en **1 a 3,5 s**. Cada intento que no
  atendía costaba 25 s (lo que se esperaba antes para conectar) más la pausa de
  fábrica: de ahí el minuto que tardaban las películas (y VLC). Ahora, si no
  atiende en 5 s, se reintenta a los 250 ms con otra conexión; una película
  reintenta hasta 8 veces seguidas (`REINTENTOS_ARCHIVO`), en vivo los de
  fábrica (para pasar rápido a otra señal). También vale si se corta a mitad
  de una película o al adelantar.
- Una **película o capítulo** (un archivo: `.mp4`, `.mkv`, `.avi`...) espera
  **20 s** a leer (`KAIROS_ESPERA_LECTURA_ARCHIVO_MS`, `kairosEsperaLectura`):
  si el servidor deja de mandar, se reconecta. En la 1.2.34 eran 90 s, por la
  idea (equivocada, ver la medición) de que el servidor tardaba un minuto en
  mandar lo primero: una película se quedaba cargando un minuto entero.
- Una película **guarda lo ya visto** (90 s, `KAIROS_LO_VISTO_MS`,
  `VideoAsset.kairosAjustarBuffer`, que llaman los dos reproductores): de
  fábrica no guarda nada y volver 10 segundos era pedirlo de nuevo al
  servidor (otra conexión, otra espera). Ahora es al instante. Son datos ya
  bajados: unos 10 a 40 MB de memoria.
- Del lado de Dart una película espera 90 s en total a arrancar, 60 s cargando
  antes de darse por trabada y los toques seguidos de adelantar/atrasar se
  juntan en un solo salto (`ControlSenal.saltar`, desde la app 1.2.34).
- **Una película pasa UNA sola vez por el link** (desde la app 1.2.35,
  `KairosRedireccionFija.java`). ExoPlayer pide el archivo varias veces: un
  `.avi` (y un `.mp4` con el índice al final) **3 veces antes de la primera
  imagen** (el principio, el índice del final y otra vez el principio), y cada
  salto, otra. Y siempre pide el **link original**: en Xtream
  (`.../movie/usuario/clave/123.avi`) ese link redirige a otro servidor, y ese
  paso es el que tarda cerca de un minuto. Así una película tardaba unos 3
  minutos en arrancar (la app se rendía a los 90 s) y adelantar costaba otro
  minuto. VLC pide el link una vez y después usa adonde lo mandaron: por eso
  tarda un minuto y después adelanta en segundos. Ahora la app hace lo mismo:
  recuerda adonde redirigió el link (en toda la app, 1 hora: también al
  reconectar o volver a la app) y, si esa dirección dejó de servir (403,
  404...: el permiso venció), vuelve a pedir el link. Solo películas y
  capítulos (`kairosEsArchivo`); en vivo se sigue pidiendo el link (renueva el
  permiso). Lo arma `HttpVideoAsset.kairosFabricaDeDatos`.
- Mientras una película tarda en arrancar, debajo de la ruedita dice que el
  servidor tarda en contestar, que la app sigue intentando y cuántos segundos van
  (`ControlSenal.avisoDeEspera`, `lib/widgets/espera_larga.dart`): con la
  ruedita sola parecía colgada.
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

Está en `.../videoplayer/HttpVideoAsset.java` (buscar "Kairos TV") y
`KairosRedireccionFija.java` y `KairosReintentoRapido.java`. Tests:
`android/src/test/.../KairosHttpVideoAssetTest.java`, `KairosRedireccionFijaTest.java`,
`KairosReintentoRapidoTest.java` y `KairosPeliculaQueArrancaTest.java` (se
corren con `gradlew :video_player_android:testDebugUnitTest` desde
`app_movil/android`) y `app_movil/test/arranque_directo_test.dart`. Los de la
redirección usan `ServidorXtreamDePrueba.java`, un servidor HTTP local que se
porta como Xtream y cuenta los pedidos; `KairosPeliculaQueArrancaTest` lee dos
películas de verdad con el índice al final (`src/test/resources/kairos/`,
hechas con ffmpeg: 12 s de imagen de prueba y un tono) como lo hace ExoPlayer,
hasta la primera imagen.

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
- **Dolby (AC3 / E-AC3 / TrueHD) y DTS**: desde la 1.2.39, con FFmpeg (LGPL, armado
  con solo esos decodificadores; la versión ya compilada de Jellyfin es GPL y
  obligaría a publicar el código de la app). Ver `android/ffmpeg/README.md`.

Tests: `android/src/test/cpp/kairos_audio_prueba.c` (el decodificador, en la
compu: `gcc -O2 -I ../../main/cpp kairos_audio_prueba.c ../../main/cpp/kairos_audio.c -o prueba && ./prueba tono_440hz.mp2`;
sale igual que ffmpeg) y `android/src/test/.../KairosAudioRendererTest.java`
(que se use solo para MP1/MP2 y después del de Android).

### 7. Canales en vivo que se cortan: se reconectan solos (desde la app 1.2.32)

- Con internet satelital (Starlink) o un WiFi flojo hay **microcortes**, y
  muchos servidores de canales (Astra, Xtream) **cortan al aparato que se
  atrasa** un momento: la transmisión "terminaba" o daba error a los pocos
  segundos. VLC reconecta y sigue; ExoPlayer se rendía y la app pasaba a otra
  señal (o decía que no anda).
- Ahora `ExoPlayerEventListener` (buscar "Kairos TV"), con las reglas de
  `KairosReconexion.java`: si un canal **en vivo** que **ya se estaba viendo**
  termina o da un error de conexión, se reconecta por dentro (la app solo ve
  "cargando"), esperando 0, 1, 2, 3 s... **hasta 6 veces por minuto**. Si se
  corta más seguido, avisa el error y la app sigue como siempre (reconecta o
  pasa a otra señal). Una señal que **nunca arrancó** no se reconecta (pasa a
  la siguiente enseguida), y los errores del aparato (decodificador, formato)
  tampoco.
- El error ahora dice **su causa** (antes era solo "Source error"): por
  ejemplo `ERROR_CODE_IO_BAD_HTTP_STATUS: Source error: Response code: 404 ·
  se reconectó sola 6 veces`. La app lo manda al panel ("Último problema en un
  aparato").
- Un video directo sin duración conocida se toma como en vivo. Una película
  (con duración) termina normal.
- **La duración en vivo (app 1.2.33)** — el error de verdad de los canales TS
  directos que "muestran medio segundo y se cortan" aunque en VLC anden: un
  canal en vivo no tiene duración y ExoPlayer da `C.TIME_UNSET` (un número
  enorme negativo). `video_player` lo pasa a microsegundos, **se desborda y
  queda en 1 ms**: apenas arrancaba, la posición "llegaba al final",
  `video_player` lo daba por terminado, lo pausaba y la app pasaba a otra
  señal. Ahora `kairosDuracion()` (en `ExoPlayerEventListener`, lo usan los dos
  `sendInitialized`) pasa unos 100 años en vivo (`KAIROS_SIN_FIN_MS`). Las
  películas siguen pasando su duración real.

Tests: `android/src/test/.../KairosReconexionTest.java`.

**Si algún día se actualiza `video_player`** y pide una versión más nueva de
este paquete: copiar la nueva de `%LOCALAPPDATA%\Pub\Cache\hosted\pub.dev\video_player_android-X.Y.Z`
(carpetas `lib/` y `android/`, `pubspec.yaml`, `LICENSE`), volver a aplicar los
diez cambios (con los archivos nuevos `Kairos*.java`, `src/main/cpp/`,
`src/main/jniLibs/`, `src/main/java/androidx/media3/decoder/ffmpeg/`,
`android/ffmpeg/` y lo de `build.gradle.kts`: `externalNativeBuild`,
`ndkVersion` y `consumerProguardFiles`; buscar "Kairos TV" en los del paquete:
`ExoPlayerEventListener`, `VideoPlayerPlugin`, `HttpVideoAsset`, los dos
reproductores) y sacar `dev_dependencies` de su `pubspec.yaml`.

### 8. El audio Dolby y DTS (desde la app 1.2.39)

- Muchas películas y series "HD" traen el audio en **Dolby** (AC3, E-AC3,
  TrueHD) o **DTS**. Muchos celulares y TV box no traen decodificador para eso
  y el reproductor, en vez de avisar, mostraba la imagen **sin sonido** (en VLC
  suena: trae los suyos).
- Ahora la app trae los de **FFmpeg** (LGPL), armados con solo esos
  decodificadores: `android/src/main/jniLibs/<abi>/libffmpegJNI.so`, con el lado
  Java de androidx/media 1.9.2 sin cambios (`android/src/main/java/androidx/media3/decoder/ffmpeg/`).
  `KairosRenderersFactory` lo agrega al final, después del de Android y del de
  MP2: se usa solo si el aparato no trae el suyo. Suman ~1,1 MB por arquitectura.
- Cómo se armó, cómo rehacerlo y qué pide la licencia: `android/ffmpeg/README.md`.
- Test: `android/src/test/.../KairosAudioDolbyTest.java` (el orden, y que las
  bibliotecas traigan esos decodificadores).

### 9. Adelantar en una película MKV sin índice (desde la app 1.2.39)

- Un MKV trae al final un **índice** (los "Cues") con el lugar de cada momento
  de la película. Algunos vienen sin él (los grabados o convertidos al vuelo) y
  el lector de ExoPlayer los marcaba "no se puede adelantar": **cualquier salto
  volvía la película a 0**. VLC sí adelanta: va buscando dentro del archivo.
- Ahora `KairosMkvSinIndice.java` (lo pone `KairosExtractores.java` en lugar
  del lector de MKV de siempre; lo usa `HttpVideoAsset`): si no hay índice pero
  sí duración y se sabe cuánto pesa el archivo, un salto calcula a qué parte del
  archivo corresponde (como si pesara lo mismo cada minuto), busca desde ahí el
  próximo bloque de la película ("Cluster": tiene una marca fija y dice su hora)
  y, si quedó lejos, corrige y vuelve a probar: **4 pedidos al servidor como
  mucho**, y cae hasta 10 s antes de lo pedido (lo que falta lo recorre el
  reproductor sin mostrarlo) o apenas después. Lo demás lo hace el lector de
  siempre. Un salto a los primeros 10 s vuelve a empezar (como antes).
- Con índice no cambia nada (usa el del archivo).
- Test: `android/src/test/.../KairosMkvSinIndiceTest.java`, con
  `src/test/resources/kairos/mkv_sin_indice.mkv` (60 s hechos con ffmpeg y al
  que se le borró el índice) y `mkv_con_indice.mkv`.

### 10. El decodificador de video trabado y el diagnóstico (desde la app 1.2.40)

- Caso: una tablet en la que **ninguna señal arranca** ("se queda intentando
  conectar") y el mismo canal, en un celular en el mismo WiFi, anda en
  segundos. Cada aparato trae uno o más decodificadores de video: el del
  fabricante (por hardware, rápido) y el de Android (por software, más lento,
  anda en todos). En muchas tablets y TV box baratos el del fabricante **recibe
  el video y no devuelve ninguna imagen**, sin dar error: ExoPlayer quedaba
  "cargando" para siempre, la app esperaba hasta 80 s por señal y le avisaba al
  servidor que la señal "no mandó video" (mentira: era el aparato).
- `KairosRenderersFactory` ahora **prueba el siguiente decodificador si uno no
  arranca** (`setEnableDecoderFallback`; de fábrica se rendía con el primero) y
  usa `KairosDecodificadores.Selector`: los de siempre menos los que se
  trabaron en este aparato.
- `KairosVigia.java` (lo crea `ExoPlayerEventListener`, buscar "Kairos TV")
  mira cada segundo, hasta que aparece la primera imagen, qué llegó y qué hizo
  el decodificador. Si **entró video y no salió ninguna imagen en 6 s** (con
  video guardado y dónde dibujarlo), anota ese decodificador como trabado
  (`KairosDecodificadores.java`: en el aparato, **2 días**) y hace arrancar el
  video de nuevo, ya con otro (la app solo ve "cargando"). Si ya era el de
  Android, no hay otro o el decodificador no termina de arrancar en 10 s,
  avisa el error `KAIROS_DECODIFICADOR_TRABADO` y la app pasa a otra señal
  enseguida (y se lo cuenta al servidor como **del aparato**, no de la señal).
  Si el de Android también se trabó con ese video, el del fabricante se
  "perdona" (era el video). Un error del decodificador del fabricante a mitad
  de camino (`ERROR_CODE_DECODING_FAILED`) también pasa a otro.
- **2 días** y no más: hay televisores cuyo decodificador se traba tras días en
  espera y vuelve a andar al desenchufarlos, y en una tele el de software pesa
  más. Si sigue trabado, volver a darse cuenta cuesta unos 6 s.
- **El diagnóstico**: el vigía junta qué video llegó (tipo, tamaño, cuadros por
  segundo), qué decodificador se usó y cuánto entró y salió, el audio, lo
  guardado y los reintentos de conexión. Va al final de cada error ("· video
  h264 1920x1080 25 fps · deco OMX.MTK.VIDEO.DECODER.AVC: entraron 12, salieron
  0 · ...") y la app lo pide cuando una señal no arranca a tiempo, por el canal
  `kairos/reproductor` (método `diagnostico` con la dirección del video; lo
  abre `VideoPlayerPlugin`). Contesta `{texto, causa, cambiando}`: causa
  `aparato` (llegó y no se mostró), `sin_datos` (no llegó nada del servidor),
  `sin_video` (la señal no trae video), `cambiando` (está probando otro
  decodificador: la app espera 20 s más) o `desconocida`.
- Tests: `android/src/test/.../KairosVigiaTest.java` (las reglas, y con un
  reproductor de mentira: el del fabricante trabado pasa al de Android; si ese
  también, se rinde) y `KairosDecodificadoresTest.java` (lo anotado, cuánto
  dura, que quede aunque se cierre la app).
