// Kairos TV: un canal en vivo que ya se estaba viendo y se corta, se reconecta
// solo (como VLC) en vez de darse por fallado. Ver ../../../../../../../README.md.

package io.flutter.plugins.videoplayer;

import androidx.annotation.NonNull;
import androidx.media3.common.PlaybackException;
import java.util.ArrayDeque;
import java.util.LinkedHashSet;
import java.util.Set;

/**
 * Con internet satelital (Starlink) o un WiFi flojo hay microcortes, y muchos
 * servidores de canales (Astra, Xtream) cortan al aparato que se atrasa un
 * momento: la transmisión "termina" o da error a los pocos segundos. VLC
 * reconecta y sigue; el reproductor se rendía y la app pasaba a otra señal.
 *
 * <p>Esto decide cuándo reconectar por dentro: solo en vivo, solo si ya se
 * llegó a ver (una señal que nunca arrancó pasa a la siguiente como siempre),
 * solo por errores pasajeros (de conexión, no del aparato) y hasta {@link
 * #MAXIMO_POR_VENTANA} veces por minuto, cada vez esperando un poco más. Si se
 * corta más seguido, avisa (y la app pasa a otra señal).
 */
final class KairosReconexion {
  static final int MAXIMO_POR_VENTANA = 6;
  static final long VENTANA_MS = 60_000;
  static final long ESPERA_MAXIMA_MS = 3_000;

  private final ArrayDeque<Long> recientes = new ArrayDeque<>();
  private int total;

  /**
   * ¿Se puede reconectar ahora? Si sí, la anota y devuelve cuánto esperar
   * antes (0, 1, 2, 3, 3... segundos: si internet se cayó, darle un momento).
   * Si ya van demasiadas en el último minuto, devuelve -1.
   */
  long reconectar(long ahoraMs) {
    while (!recientes.isEmpty() && ahoraMs - recientes.peekFirst() > VENTANA_MS) {
      recientes.pollFirst();
    }
    if (recientes.size() >= MAXIMO_POR_VENTANA) {
      return -1;
    }
    long espera = Math.min(1000L * recientes.size(), ESPERA_MAXIMA_MS);
    recientes.addLast(ahoraMs);
    total++;
    return espera;
  }

  /** Cuántas veces se reconectó en total (para el diagnóstico). */
  int total() {
    return total;
  }

  /**
   * ¿Es un error de conexión, de esos que se arreglan reconectando? Los del
   * aparato (decodificador, formato) o de permisos no: reconectar no sirve.
   */
  static boolean esPasajero(int codigo) {
    switch (codigo) {
      case PlaybackException.ERROR_CODE_UNSPECIFIED:
      case PlaybackException.ERROR_CODE_TIMEOUT:
      case PlaybackException.ERROR_CODE_IO_UNSPECIFIED:
      case PlaybackException.ERROR_CODE_IO_NETWORK_CONNECTION_FAILED:
      case PlaybackException.ERROR_CODE_IO_NETWORK_CONNECTION_TIMEOUT:
      case PlaybackException.ERROR_CODE_IO_INVALID_HTTP_CONTENT_TYPE:
      case PlaybackException.ERROR_CODE_IO_BAD_HTTP_STATUS:
      case PlaybackException.ERROR_CODE_IO_READ_POSITION_OUT_OF_RANGE:
      case PlaybackException.ERROR_CODE_PARSING_CONTAINER_MALFORMED:
      case PlaybackException.ERROR_CODE_PARSING_MANIFEST_MALFORMED:
        return true;
      default:
        return false;
    }
  }

  /**
   * El error con su causa, para el diagnóstico del panel ("Último problema en
   * un aparato"). De fábrica decía solo "Source error"; acá va el tipo y lo
   * que dijo cada causa, por ejemplo
   * "ERROR_CODE_IO_BAD_HTTP_STATUS: Source error: Response code: 404". Los
   * nombres de las clases no (al armar la app se acortan y no dicen nada).
   */
  @NonNull
  static String describir(@NonNull PlaybackException error) {
    StringBuilder texto = new StringBuilder(error.getErrorCodeName());
    Set<String> dichos = new LinkedHashSet<>();
    Throwable causa = error;
    for (int i = 0; causa != null && i < 6; i++, causa = causa.getCause()) {
      String mensaje = causa.getMessage();
      if (mensaje != null && !mensaje.trim().isEmpty() && dichos.add(mensaje.trim())) {
        texto.append(": ").append(mensaje.trim());
      }
    }
    return texto.toString();
  }
}
