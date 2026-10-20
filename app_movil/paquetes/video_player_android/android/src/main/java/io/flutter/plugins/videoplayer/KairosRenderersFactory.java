// Kairos TV: lo que sabe reproducir el reproductor, más el audio MP2. Ver ../../../../../../../README.md.

package io.flutter.plugins.videoplayer;

import android.content.Context;
import android.os.Handler;
import androidx.annotation.NonNull;
import androidx.media3.common.util.UnstableApi;
import androidx.media3.exoplayer.DefaultRenderersFactory;
import androidx.media3.exoplayer.Renderer;
import androidx.media3.exoplayer.audio.AudioRendererEventListener;
import androidx.media3.exoplayer.audio.AudioSink;
import androidx.media3.exoplayer.mediacodec.MediaCodecSelector;
import java.util.ArrayList;

/**
 * Lo de siempre (los decodificadores de Android) y, al final, {@link
 * KairosAudioRenderer} para el audio MP1 / MP2 que Android no trae. Va al final
 * a propósito: el reproductor usa el primero que sabe leer cada audio, así que
 * si el aparato trae el suyo, se usa ese.
 */
@UnstableApi
public final class KairosRenderersFactory extends DefaultRenderersFactory {

  public KairosRenderersFactory(@NonNull Context context) {
    super(context);
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
  }
}
