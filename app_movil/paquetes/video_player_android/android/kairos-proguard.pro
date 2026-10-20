# Kairos TV: el decodificador de audio MP1 / MP2 (KairosAudioMpeg) llama a C por
# el NOMBRE de sus funciones: que el achicador de código (R8) no las renombre.
-keep class io.flutter.plugins.videoplayer.KairosAudioMpeg {
    native <methods>;
}
