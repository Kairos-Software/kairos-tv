# Kairos TV: el decodificador de audio MP1 / MP2 (ver kairos_audio.c y KairosAudioMpeg.java).
cmake_minimum_required(VERSION 3.22.1)
project(kairos_audio C)

add_library(kairos_audio SHARED kairos_audio.c kairos_audio_jni.c)
target_compile_options(kairos_audio PRIVATE -O2 -Wall)
# Páginas de 16 KB (Android 15+ lo pide para las bibliotecas nativas)
target_link_options(kairos_audio PRIVATE "-Wl,-z,max-page-size=16384")
