#!/usr/bin/env bash
# Kairos TV: arma libffmpegJNI.so, los decodificadores de audio de FFmpeg que Android no trae (Dolby AC3 / E-AC3 /
# TrueHD y DTS), para el reproductor de la app. Basado en build_ffmpeg.sh y CMakeLists.txt de androidx/media
# (libraries/decoder_ffmpeg), adaptado a Windows: la terminal de Git (Git Bash) y el make que trae el NDK.
#
# Uso: compilar_ffmpeg.sh <código de FFmpeg> <ffmpeg_jni.cc> <carpeta de salida> <NDK> [ABIs...]
# Deja <salida>/jniLibs/<abi>/libffmpegJNI.so (y las bibliotecas de FFmpeg en <salida>/<abi>/lib).
set -eu

# Rutas como C:/Users/...: el make del NDK es de Windows y no entiende /c/Users/...
FUENTE="$(cygpath -m "$1")"
JNI="$(cygpath -m "$2")"
SALIDA="$(cygpath -m "$3")"
NDK="$(cygpath -m "$4")"
shift 4
if [ $# -gt 0 ]; then ABIS=("$@"); else ABIS=(arm64-v8a armeabi-v7a); fi
API=24   # = minSdk de la app
DECODIFICADORES="ac3,eac3,dca,truehd,mlp"
HERRAMIENTAS="$NDK/toolchains/llvm/prebuilt/windows-x86_64/bin"
MAKE="$NDK/prebuilt/windows-x86_64/bin/make.exe"
TRABAJOS="${NUMBER_OF_PROCESSORS:-4}"
# configure usa TMPDIR: en Windows viene con barras invertidas y la terminal se las come
export TMPDIR="$SALIDA/tmp"
mkdir -p "$TMPDIR"

# Solo esos decodificadores (sin --enable-gpl ni --enable-nonfree: queda LGPL)
COMUNES=(
    --target-os=android
    --enable-cross-compile
    --enable-static
    --disable-shared
    --disable-doc
    --disable-programs
    --disable-everything
    --disable-avdevice
    --disable-avformat
    --disable-swscale
    --disable-postproc
    --disable-avfilter
    --disable-symver
    --disable-network
    --disable-autodetect
    --enable-swresample
    --enable-pic
    --disable-v4l2-m2m
    --disable-vulkan
    --enable-decoder="$DECODIFICADORES"
    --nm="$HERRAMIENTAS/llvm-nm.exe"
    --ar="$HERRAMIENTAS/llvm-ar.exe"
    --ranlib="$HERRAMIENTAS/llvm-ranlib.exe"
    --strip="$HERRAMIENTAS/llvm-strip.exe"
)

for ABI in "${ABIS[@]}"; do
    case "$ABI" in
        arm64-v8a)
            CXX="$HERRAMIENTAS/aarch64-linux-android$API-clang++"
            OPCIONES=(--arch=aarch64 --cpu=armv8-a --cc="$HERRAMIENTAS/aarch64-linux-android$API-clang" --cxx="$CXX")
            ;;
        armeabi-v7a)
            CXX="$HERRAMIENTAS/armv7a-linux-androideabi$API-clang++"
            OPCIONES=(--arch=arm --cpu=armv7-a --cc="$HERRAMIENTAS/armv7a-linux-androideabi$API-clang" --cxx="$CXX"
                      --extra-cflags="-march=armv7-a -mfloat-abi=softfp")
            ;;
        *) echo "ABI desconocida: $ABI"; exit 1 ;;
    esac
    ARMADO="$SALIDA/armado-$ABI"
    rm -rf "$ARMADO" "$SALIDA/$ABI"
    mkdir -p "$ARMADO"
    cd "$ARMADO"
    echo "== $ABI: configure (tarda unos minutos)"
    "$FUENTE/configure" --prefix="$SALIDA/$ABI" "${OPCIONES[@]}" "${COMUNES[@]}" > configure.log 2>&1 \
        || { tail -30 configure.log; tail -40 ffbuild/config.log; exit 1; }
    # configure deja la ruta del código como la ve la terminal (/c/... o /tmp/...): se pasa a C:/...
    for archivo in Makefile ffbuild/config.mak; do
        sed -i -e "s#$(cd "$FUENTE" && pwd)#$FUENTE#g" -e "s#/tmp/#$(cygpath -m /tmp)/#g" "$archivo"
    done
    echo "== $ABI: make"
    "$MAKE" -j"$TRABAJOS" > make.log 2>&1 || { tail -40 make.log; exit 1; }
    "$MAKE" install-libs > install.log 2>&1 || { tail -20 install.log; exit 1; }
    # Los encabezados aparte: con la carpeta del código entera, en Windows (no distingue mayúsculas) el
    # <version> de C++ encontraba el archivo VERSION de FFmpeg
    INCLUDE="$SALIDA/$ABI/include"
    for biblioteca in libavcodec libavutil libswresample; do
        mkdir -p "$INCLUDE/$biblioteca"
        cp "$FUENTE/$biblioteca"/*.h "$INCLUDE/$biblioteca/"
    done
    cp "$ARMADO/libavutil/avconfig.h" "$ARMADO/libavutil/ffversion.h" "$INCLUDE/libavutil/"
    # La biblioteca que carga la app: ffmpeg_jni.cc (de androidx/media) con FFmpeg adentro
    echo "== $ABI: libffmpegJNI.so"
    mkdir -p "$SALIDA/jniLibs/$ABI"
    "$CXX" -shared -fPIC -O2 -std=c++17 -Wall -I"$INCLUDE" "$JNI" \
        "$SALIDA/$ABI/lib/libavcodec.a" "$SALIDA/$ABI/lib/libswresample.a" "$SALIDA/$ABI/lib/libavutil.a" \
        -landroid -llog -lm -static-libstdc++ -Wl,-Bsymbolic -Wl,--no-undefined -Wl,-z,max-page-size=16384 \
        -o "$SALIDA/jniLibs/$ABI/libffmpegJNI.so"
    "$HERRAMIENTAS/llvm-strip.exe" --strip-unneeded "$SALIDA/jniLibs/$ABI/libffmpegJNI.so"
    ls -la "$SALIDA/jniLibs/$ABI"
done
echo "== listo"
