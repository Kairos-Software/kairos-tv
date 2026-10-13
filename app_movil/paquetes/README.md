# paquetes/

Copias de paquetes de Flutter con algún cambio nuestro. `pubspec.yaml` las usa
en lugar de las originales (sección `dependency_overrides`).

## video_player_android/ (2.12.2)

El reproductor de video de Android (ExoPlayer) que usa `video_player`. Es el
paquete oficial **con tres cambios**: el buffer, el margen en vivo y el idioma
del audio.

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

**Si algún día se actualiza `video_player`** y pide una versión más nueva de
este paquete: copiar la nueva de `%LOCALAPPDATA%\Pub\Cache\hosted\pub.dev\video_player_android-X.Y.Z`
(carpetas `lib/` y `android/`, `pubspec.yaml`, `LICENSE`), volver a aplicar los
tres cambios y sacar `dev_dependencies` de su `pubspec.yaml`.
