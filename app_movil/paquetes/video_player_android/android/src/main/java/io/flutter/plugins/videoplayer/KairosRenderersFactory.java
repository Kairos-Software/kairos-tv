// Kairos TV: lo que sabe reproducir el reproductor, más el audio MP2, Dolby y DTS. Ver ../../../../../../../README.md.

package io.flutter.plugins.videoplayer;

import android.content.Context;
import android.os.Handler;
import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.annotation.VisibleForTesting;
import androidx.media3.common.util.UnstableApi;
import androidx.media3.decoder.ffmpeg.FfmpegAudioRenderer;
import androidx.media3.decoder.ffmpeg.FfmpegLibrary;
import androidx.media3.exoplayer.DefaultRenderersFactory;
import androidx.media3.exoplayer.Renderer;
import androidx.media3.exoplayer.audio.AudioRendererEventListener;
import androidx.media3.exoplayer.audio.AudioSink;
import androidx.media3.exoplayer.mediacodec.MediaCodecSelector;
import java.util.ArrayList;

/**
 * Lo de siempre (los decodificadores de Android, sin los que se trabaron en este aparato y
 * probando el siguiente si uno no arranca) y, al final, los que la app
 * trae para el audio que muchos aparatos no saben leer: {@link
 * KairosAudioRenderer} (MP1 / MP2, el de los canales de cable y satélite) y
 * {@link FfmpegAudioRenderer} (Dolby AC3 / E-AC3 / TrueHD y DTS, el de muchas
 * películas "HD": sin él se veían sin sonido; ver android/ffmpeg/README.md). Van
 * al final a propósito: el reproductor usa el primero que sabe leer cada audio,
 * así que si el aparato trae el suyo (o lo manda tal cual al televisor por HDMI),
 * se usa ese.
 */
@UnstableApi
public final class KairosRenderersFactory extends DefaultRenderersFactory {

  @Nullable private static Boolean ffmpegParaPruebas;

  /** ¿Se pudo cargar libffmpegJNI.so? (en las pruebas de la compu no: es para Android). */
  static boolean ffmpegDisponible() {
    return ffmpegParaPruebas != null ? ffmpegParaPruebas : FfmpegLibrary.isAvailable();
  }

  @VisibleForTesting
  static void ffmpegParaPruebas(@Nullable Boolean valor) {
    ffmpegParaPruebas = valor;
  }

  public KairosRenderersFactory(@NonNull Context context) {
    super(context);
    // Si el decodificador del aparato no arranca, prueba el siguiente (de fábrica se rendía con el
    // primero); y no ofrece los que se trabaron en este aparato (ver KairosDecodificadores)
    setEnableDecoderFallback(true);
    setMediaCodecSelector(new KairosDecodificadores.Selector());
  }

  @Override
  protected void buildAudioRenderers(
      @NonNull Context context,
      int extensionRendererMode,
      @NonNull MediaCodecSelector mediaCodecSelector,
      boolean enableDecoderFallback,
      @NonNull AudioSink audioSink,
      @NonNull Handler eventHandler,
      @NonNull AudioRendererEventListener eventListener,
      @NonNull ArrayList<Renderer> out) {
    super.buildAudioRenderers(
        context,
        extensionRendererMode,
        mediaCodecSelector,
        enableDecoderFallback,
        audioSink,
        eventHandler,
        eventListener,
        out);
    if (KairosAudioMpeg.disponible()) {
      out.add(new KairosAudioRenderer(eventHandler, eventListener, audioSink));
    }
    // Si la biblioteca no se pudo cargar (no debería pasar), sigue sin él: como antes, sin sonido en esos
    if (ffmpegDisponible()) {
      out.add(new FfmpegAudioRenderer(eventHandler, eventListener, audioSink));
    }
  }
}
