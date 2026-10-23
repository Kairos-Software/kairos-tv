# Kairos TV: el decodificador de audio MP1 / MP2 (KairosAudioMpeg) llama a C por
# el NOMBRE de sus funciones: que el achicador de código (R8) no las renombre.
-keep class io.flutter.plugins.videoplayer.KairosAudioMpeg {
    native <methods>;
}

# Kairos TV: el decodificador FFmpeg (Dolby y DTS, ver ffmpeg/README.md). Las reglas de androidx/media
# (libraries/decoder_ffmpeg/proguard-rules.txt): sus funciones nativas van por nombre y C llama a
# growOutputBuffer.
-keepclasseswithmembernames class androidx.media3.decoder.ffmpeg.** {
    native <methods>;
}
-keep, includedescriptorclasses class androidx.media3.decoder.ffmpeg.FfmpegAudioDecoder {
  private java.nio.ByteBuffer growOutputBuffer(androidx.media3.decoder.SimpleDecoderOutputBuffer, int);
}
