// Kairos TV: no es parte del plugin original (ver paquetes/README.md).

package io.flutter.plugins.videoplayer;

import androidx.annotation.NonNull;
import androidx.annotation.OptIn;
import androidx.media3.common.util.UnstableApi;
import androidx.media3.exoplayer.upstream.DefaultLoadErrorHandlingPolicy;
import java.io.IOException;
import java.net.ConnectException;
import java.net.NoRouteToHostException;
import java.net.SocketTimeoutException;

/**
 * Kairos TV: cuándo vuelve a intentar ExoPlayer si un pedido falla.
 *
 * <p>Medido (2026-10-21, desde la compu, con curl): el servidor de un proveedor Xtream no atendía
 * 3 de cada 7 intentos de conexión (al azar, no por pedir rápido); cuando atendía, el primer dato
 * llegaba en 1 a 3,5 s. Cada intento que no atendía costaba 25 s de espera (la de conectar) más la
 * pausa de fábrica antes de reintentar: una película tardaba un minuto en arrancar o no arrancaba.
 *
 * <p>Ahora conectar espera {@link HttpVideoAsset#KAIROS_ESPERA_CONEXION_MS} y, si no atendió (o
 * dejó de mandar datos), se reintenta enseguida ({@link #PAUSA_MS}) con una conexión nueva. Una
 * película o capítulo reintenta hasta {@link #REINTENTOS_ARCHIVO} veces antes de dar error (en
 * total, igual lo corta la espera del lado de Dart: ControlSenal). En vivo, los reintentos de
 * fábrica (si no, se tardaría en pasar a otra señal del canal).
 */
@OptIn(markerClass = UnstableApi.class)
final class KairosReintentoRapido extends DefaultLoadErrorHandlingPolicy {
  /** La pausa antes de reintentar cuando el servidor no atendió. */
  static final long PAUSA_MS = 250;

  /** Cuántas veces seguidas se reintenta una película o capítulo. */
  static final int REINTENTOS_ARCHIVO = 8;

  private final boolean archivo;

  KairosReintentoRapido(boolean archivo) {
    this.archivo = archivo;
  }

  @Override
  public long getRetryDelayMsFor(@NonNull LoadErrorInfo loadErrorInfo) {
    if (noAtendio(loadErrorInfo.exception)) {
      return PAUSA_MS;
    }
    return super.getRetryDelayMsFor(loadErrorInfo);
  }

  @Override
  public int getMinimumLoadableRetryCount(int dataType) {
    int deFabrica = super.getMinimumLoadableRetryCount(dataType);
    return archivo ? Math.max(deFabrica, REINTENTOS_ARCHIVO) : deFabrica;
  }

  /** El servidor no atendió la conexión, o dejó de mandar datos: vale reintentar ya. */
  static boolean noAtendio(@NonNull IOException error) {
    for (Throwable causa = error; causa != null; causa = causa.getCause()) {
      if (causa instanceof SocketTimeoutException
          || causa instanceof ConnectException
          || causa instanceof NoRouteToHostException) {
        return true;
      }
    }
    return false;
  }
}
