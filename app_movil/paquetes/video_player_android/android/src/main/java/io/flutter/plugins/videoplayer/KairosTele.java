// Kairos TV: lo que cambia en el reproductor mientras el celular usa una tele
// como pantalla ("Ver en la tele", app_movil/lib/tele/). Lo pone PantallaTele.kt
// al conectarse la tele y lo saca al desconectarse. Ver paquetes/README.md.

package io.flutter.plugins.videoplayer;

import androidx.annotation.NonNull;
import androidx.media3.common.util.UnstableApi;
import androidx.media3.exoplayer.DefaultLoadControl;
import androidx.media3.exoplayer.trackselection.DefaultTrackSelector;

/**
 * Con una tele conectada, el celular baja el canal y a la vez le manda la
 * imagen a la tele por el mismo WiFi. Para que no se trabe:
 *
 * <ul>
 *   <li>{@link #altoMaximo}: el video no pasa de ese alto (720p). Baja la mitad que un 1080p y en
 *       la tele casi no se nota, porque Android igual vuelve a comprimir la imagen para mandarla.
 *       Sigue eligiendo solo la calidad según internet, por debajo de ese tope.
 *   <li>{@link #esperaTrasCorte}: después de un corte junta más video antes de seguir.
 * </ul>
 *
 * Los dos motores de Flutter (el del celular y el de la tele) corren en el mismo proceso, así que
 * esto vale para los reproductores que se creen mientras está puesto.
 */
public final class KairosTele {
  private KairosTele() {}

  /** El alto máximo del video, en píxeles. 0 = sin tope (sin tele). */
  public static volatile int altoMaximo = 0;

  /** Cuánto video junta antes de seguir después de un corte, en milisegundos. */
  public static volatile int esperaTrasCorte = 5000;

  /** El buffer de Kairos TV: 5 s para arrancar y {@link #esperaTrasCorte} después de un corte. */
  @UnstableApi
  @NonNull
  public static DefaultLoadControl.Builder buffer() {
    return new DefaultLoadControl.Builder()
        .setBufferDurationsMs(
            DefaultLoadControl.DEFAULT_MIN_BUFFER_MS,
            DefaultLoadControl.DEFAULT_MAX_BUFFER_MS,
            /* bufferForPlaybackMs= */ 5000,
            /* bufferForPlaybackAfterRebufferMs= */ esperaTrasCorte);
  }

  /** Aplica el tope de alto (si hay) a las preferencias del selector de calidades. */
  @UnstableApi
  public static void aplicarTope(@NonNull DefaultTrackSelector.Parameters.Builder parametros) {
    int tope = altoMaximo;
    if (tope > 0) parametros.setMaxVideoSize(Integer.MAX_VALUE, tope);
  }
}
