# ffmpeg/ — el audio Dolby y DTS (desde la app 1.2.39)

Muchas películas y series "HD" traen el audio en **Dolby** (AC3, E-AC3, TrueHD) o
**DTS**. Muchos celulares y TV box no traen decodificador para eso, y el
reproductor de Android, en vez de avisar, mostraba la imagen **sin sonido**. VLC
suena porque trae los suyos. Ahora la app también: los de **FFmpeg**.

## Qué hay acá

| Archivo | Qué es |
|---|---|
| `compilar_ffmpeg.sh` | Arma `libffmpegJNI.so` para `arm64-v8a` y `armeabi-v7a` (los procesadores de la app). Adaptado a Windows de `build_ffmpeg.sh` de androidx/media. |
| `ffmpeg_jni.cc` | El puente entre Java y FFmpeg, de androidx/media 1.9.2 (`libraries/decoder_ffmpeg/src/main/jni/`), sin cambios. Licencia Apache 2.0. |
| `COPYING.LGPLv2.1` | La licencia de FFmpeg. |

Lo que usa la app:

- `../src/main/jniLibs/<abi>/libffmpegJNI.so`: las bibliotecas ya armadas (FFmpeg + `ffmpeg_jni.cc`), ~1,1 MB cada una. Van ya armadas para que armar la APK no necesite compilar FFmpeg.
- `../src/main/java/androidx/media3/decoder/ffmpeg/`: el lado Java, de androidx/media 1.9.2 sin cambios (`FfmpegAudioRenderer`, `FfmpegAudioDecoder`, `FfmpegLibrary`...). Va con su paquete original porque las funciones nativas se llaman por ese nombre. (La versión de media3 tiene que ser la misma que en `../build.gradle.kts`.)
- `KairosRenderersFactory` lo pone **al final**: se usa solo si el aparato no trae el suyo (o no lo manda tal cual al televisor por HDMI). Si la biblioteca no se pudiera cargar, todo sigue como antes.

## Qué tiene adentro

FFmpeg **6.0.1** (la que recomienda media3 para este `ffmpeg_jni.cc`), con
`--disable-everything` y solo estos decodificadores: `ac3`, `eac3`, `dca`
(DTS), `truehd` y `mlp`; más `libswresample` (para pasarlos al formato que
reproduce Android). Nada de video ni de red. **Sin** `--enable-gpl` ni
`--enable-nonfree`: queda bajo la licencia **LGPL 2.1 o posterior**.

- Código: https://ffmpeg.org/releases/ffmpeg-6.0.1.tar.xz
  (sha256 `9b16b8731d78e596b4be0d720428ca42df642bb2d78342881ff7f5bc29fc9623`).
- Lo prueba `../src/test/java/.../KairosAudioDolbyTest.java`: que el reproductor
  lo ponga después del de Android y que las dos bibliotecas traigan esos
  decodificadores (y ninguno de video).

## La licencia (LGPL): qué hay que cumplir

FFmpeg va en una biblioteca aparte (`libffmpegJNI.so`), que la app carga al
abrir el reproductor: se puede reemplazar por otra armada con este mismo
guion. Para cumplir la LGPL alcanza con avisar que la app usa FFmpeg bajo la
LGPL, cuál versión, y tener disponible su código y cómo se armó (este
README, el guion y `ffmpeg_jni.cc`). Si alguien lo pide, se le pasa esto.

## Cómo rehacer las bibliotecas

En Windows, con la terminal de Git (Git Bash) y el NDK de Android (el que usa
Flutter, `ndkVersion` de la app; probado con el 28.2.13676358):

```
# El código de FFmpeg, en una carpeta SIN espacios
curl -LO https://ffmpeg.org/releases/ffmpeg-6.0.1.tar.xz && tar -xJf ffmpeg-6.0.1.tar.xz
# Arma las dos (configure tarda unos 4 minutos cada una)
bash compilar_ffmpeg.sh ffmpeg-6.0.1 ffmpeg_jni.cc salida "$LOCALAPPDATA/Android/Sdk/ndk/28.2.13676358"
# Copiar salida/jniLibs/<abi>/libffmpegJNI.so a ../src/main/jniLibs/<abi>/
```

Las vueltas que tiene el guion para Windows (por si algo cambia):

- El `make` es el que trae el NDK (`prebuilt/windows-x86_64/bin/make.exe`), que
  es de Windows: todas las rutas van como `C:/...` y, después de `configure`,
  se cambian las `/c/...` y `/tmp/...` que deja en `Makefile` y
  `ffbuild/config.mak`.
- `TMPDIR` propio: el de Windows viene con barras invertidas.
- Los encabezados se copian aparte: con la carpeta del código entera, el
  `<version>` de C++ encontraba el archivo `VERSION` de FFmpeg (Windows no
  distingue mayúsculas).
