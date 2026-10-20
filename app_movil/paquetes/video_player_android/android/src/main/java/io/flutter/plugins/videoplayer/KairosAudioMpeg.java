// Kairos TV: decodificador propio de audio MPEG capa 1 y 2 (MP1 / MP2). Ver ../../../../../../../README.md.

package io.flutter.plugins.videoplayer;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.annotation.VisibleForTesting;
import androidx.media3.common.util.UnstableApi;
import androidx.media3.decoder.DecoderException;
import androidx.media3.decoder.DecoderInputBuffer;
import androidx.media3.decoder.SimpleDecoder;
import androidx.media3.decoder.SimpleDecoderOutputBuffer;
import java.nio.ByteBuffer;

/**
 * MP2 es el audio clásico de los canales de cable y satélite, y Android NO
 * trae decodificador para él: el canal se veía pero sin sonido (VLC sí suena
 * porque trae los suyos). Este lo decodifica en el aparato con minimp3 (de
 * dominio público, ver src/main/cpp/), a PCM de 16 bits.
 *
 * <p>Lo usa {@link KairosAudioRenderer} solo cuando el aparato no tiene uno
 * propio. Si la biblioteca nativa no está ({@link #disponible()} false), el
 * reproductor sigue como antes: el video se ve, sin sonido.
 */
@UnstableApi
public final class KairosAudioMpeg
    extends SimpleDecoder<DecoderInputBuffer, SimpleDecoderOutputBuffer, DecoderException> {

  /** Muestras por cuadro de MPEG audio capa 2 (la capa 1 tiene menos) y el cuadro más chico posible. */
  private static final int MUESTRAS_POR_CUADRO = 1152;
  private static final int CUADRO_MAS_CHICO = 96;

  private static final boolean CARGADA = cargar();
  @Nullable private static Boolean disponibleParaPruebas;

  private static boolean cargar() {
    try {
      System.loadLibrary("kairos_audio");
      return true;
    } catch (UnsatisfiedLinkError | SecurityException error) {
      return false;
    }
  }

  /** ¿Se cargó la biblioteca nativa? (si no, el reproductor no lo usa). */
  public static boolean disponible() {
    return disponibleParaPruebas != null ? disponibleParaPruebas : CARGADA;
  }

  @VisibleForTesting
  static void disponibleParaPruebas(@Nullable Boolean valor) {
    disponibleParaPruebas = valor;
  }

  private final int canales;
  private final int frecuencia;
  private long nativo;

  KairosAudioMpeg(int buffers, int tamanioInicial, int canales, int frecuencia) throws DecoderException {
    super(new DecoderInputBuffer[buffers], new SimpleDecoderOutputBuffer[buffers]);
    if (!CARGADA) {
      throw new DecoderException("Falta la biblioteca de audio de Kairos.");
    }
    nativo = nativoAbrir();
    if (nativo == 0) {
      throw new DecoderException("No se pudo crear el decodificador de audio.");
    }
    this.canales = Math.max(1, canales);
    this.frecuencia = frecuencia > 0 ? frecuencia : 48000;
    setInitialInputBufferSize(tamanioInicial);
  }

  @NonNull
  @Override
  public String getName() {
    return "kairos-mp2";
  }

  /** Lo que sale: PCM de 16 bits con los canales y la frecuencia del audio original. */
  int getCanales() {
    return canales;
  }

  int getFrecuencia() {
    return frecuencia;
  }

  @NonNull
  @Override
  protected DecoderInputBuffer createInputBuffer() {
    return new DecoderInputBuffer(DecoderInputBuffer.BUFFER_REPLACEMENT_MODE_DIRECT);
  }

  @NonNull
  @Override
  protected SimpleDecoderOutputBuffer createOutputBuffer() {
    return new SimpleDecoderOutputBuffer(this::releaseOutputBuffer);
  }

  @NonNull
  @Override
  protected DecoderException createUnexpectedDecodeException(@NonNull Throwable error) {
    return new DecoderException("Error inesperado al decodificar el audio.", error);
  }

  @Nullable
  @Override
  protected DecoderException decode(
      @NonNull DecoderInputBuffer entrada, @NonNull SimpleDecoderOutputBuffer salida, boolean reiniciar) {
    if (reiniciar) {
      nativoReiniciar(nativo);
    }
    ByteBuffer datos = entrada.data;
    int largo = datos == null ? 0 : datos.limit();
    // Lo más que puede salir de este pedazo: todos cuadros de los más chicos
    int maximo = (largo / CUADRO_MAS_CHICO + 1) * MUESTRAS_POR_CUADRO * canales * 2;
    ByteBuffer pcm = salida.init(entrada.timeUs, maximo);
    int bytes = largo == 0 ? 0 : nativoDecodificar(nativo, datos, largo, pcm);
    // Un cuadro roto no corta el video: sale sin sonido ese pedacito
    pcm.position(0);
    pcm.limit(Math.max(bytes, 0));
    if (!isAtLeastOutputStartTimeUs(entrada.timeUs)) {
      salida.shouldBeSkipped = true;
    }
    return null;
  }

  @Override
  public void release() {
    super.release();
    if (nativo != 0) {
      nativoCerrar(nativo);
      nativo = 0;
    }
  }

  private static native long nativoAbrir();

  private static native void nativoReiniciar(long decodificador);

  private static native void nativoCerrar(long decodificador);

  private static native int nativoDecodificar(long decodificador, ByteBuffer entrada, int largo, ByteBuffer salida);
}
