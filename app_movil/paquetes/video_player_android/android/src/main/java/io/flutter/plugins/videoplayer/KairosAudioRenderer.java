// Kairos TV: el que reproduce el audio MP1 / MP2 con KairosAudioMpeg. Ver ../../../../../../../README.md.

package io.flutter.plugins.videoplayer;

import android.os.Handler;
import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.media3.common.C;
import androidx.media3.common.Format;
import androidx.media3.common.MimeTypes;
import androidx.media3.common.util.UnstableApi;
import androidx.media3.common.util.Util;
import androidx.media3.decoder.CryptoConfig;
import androidx.media3.decoder.DecoderException;
import androidx.media3.exoplayer.audio.AudioRendererEventListener;
import androidx.media3.exoplayer.audio.AudioSink;
import androidx.media3.exoplayer.audio.DecoderAudioRenderer;

/**
 * Reproduce el audio MPEG capa 1 y 2 (MP1 / MP2) con {@link KairosAudioMpeg}.
 * Va DESPUÉS del de Android ({@link KairosRenderersFactory}): si el aparato
 * trae decodificador propio para MP2, se usa ese; si no (casi todos los
 * celulares), este. Para cualquier otro audio dice que no (lo hace Android).
 */
@UnstableApi
public final class KairosAudioRenderer extends DecoderAudioRenderer<KairosAudioMpeg> {

  private static final int BUFFERS = 16;
  /** Un cuadro de MP2 a 384 kb/s y 32 kHz (el más grande) entra de sobra. */
  private static final int TAMANIO_INICIAL = 4096;

  public KairosAudioRenderer(
      @Nullable Handler eventHandler,
      @Nullable AudioRendererEventListener eventListener,
      @NonNull AudioSink audioSink) {
    super(eventHandler, eventListener, audioSink);
  }

  @NonNull
  @Override
  public String getName() {
    return "KairosAudioRenderer";
  }

  /** Los audios que decodifica: MPEG capa 1 y 2. */
  static boolean esSuyo(@Nullable String mime) {
    return MimeTypes.AUDIO_MPEG_L1.equals(mime) || MimeTypes.AUDIO_MPEG_L2.equals(mime);
  }

  @Override
  protected int supportsFormatInternal(@NonNull Format format) {
    if (!KairosAudioMpeg.disponible() || !esSuyo(format.sampleMimeType)) {
      return C.FORMAT_UNSUPPORTED_TYPE;
    }
    if (format.cryptoType != C.CRYPTO_TYPE_NONE) {
      return C.FORMAT_UNSUPPORTED_DRM;
    }
    if (!sinkSupportsFormat(salida(format))) {
      return C.FORMAT_UNSUPPORTED_SUBTYPE;
    }
    return C.FORMAT_HANDLED;
  }

  @NonNull
  @Override
  protected KairosAudioMpeg createDecoder(@NonNull Format format, @Nullable CryptoConfig cryptoConfig)
      throws DecoderException {
    int tamanio = format.maxInputSize != Format.NO_VALUE ? format.maxInputSize : TAMANIO_INICIAL;
    Format pcm = salida(format);
    return new KairosAudioMpeg(BUFFERS, tamanio, pcm.channelCount, pcm.sampleRate);
  }

  @NonNull
  @Override
  protected Format getOutputFormat(@NonNull KairosAudioMpeg decoder) {
    return Util.getPcmFormat(C.ENCODING_PCM_16BIT, decoder.getCanales(), decoder.getFrecuencia());
  }

  /** PCM de 16 bits con los canales y la frecuencia del audio original. */
  @NonNull
  private static Format salida(@NonNull Format entrada) {
    int canales = entrada.channelCount != Format.NO_VALUE ? entrada.channelCount : 2;
    int frecuencia = entrada.sampleRate != Format.NO_VALUE ? entrada.sampleRate : 48000;
    return Util.getPcmFormat(C.ENCODING_PCM_16BIT, canales, frecuencia);
  }
}
