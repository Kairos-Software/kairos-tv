// Kairos TV: no es parte del plugin original (ver paquetes/README.md).

package io.flutter.plugins.videoplayer;

import android.net.Uri;
import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.annotation.OptIn;
import androidx.media3.common.util.UnstableApi;
import androidx.media3.datasource.DataSource;
import androidx.media3.datasource.DataSpec;
import androidx.media3.datasource.HttpDataSource;
import androidx.media3.datasource.TransferListener;
import java.io.IOException;
import java.io.InterruptedIOException;
import java.net.SocketTimeoutException;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Kairos TV: una película o capítulo pide el archivo VARIAS veces (ExoPlayer, para cada
 * pedazo que no viene a continuación): un .avi o un .mp4 con el índice al final se
 * piden 3 veces antes de la primera imagen (el principio, el índice del final y otra
 * vez el principio), y cada vez que se adelanta o atrasa, otra. ExoPlayer pide siempre
 * el link ORIGINAL; en una lista Xtream ese link (".../movie/usuario/clave/123.mp4")
 * redirige a otro servidor, y ese primer paso es el que tarda (cerca de un minuto). Así,
 * una película tardaba ~3 minutos en arrancar (y la app se rendía antes) y cada salto,
 * uno más. VLC pide el link una sola vez y después usa adonde lo mandaron: por eso
 * tarda un minuto en arrancar y después adelanta en segundos.
 *
 * <p>Esto hace lo mismo que VLC: recuerda adónde redirigió el link y los pedidos que
 * siguen van directo ahí. Se recuerda en toda la app un rato ({@link #DURA_MS}): al
 * reconectar después de un corte o al volver a la app (que arman un reproductor nuevo)
 * tampoco se vuelve a pasar por el paso lento. Si esa dirección dejó de servir (el
 * permiso que da el servidor venció: 403, 404...), vuelve a pedir el link original y
 * recuerda la nueva.
 */
@OptIn(markerClass = UnstableApi.class)
final class KairosRedireccionFija implements DataSource {

  /** Cuánto se recuerda adónde mandó un link (después se vuelve a preguntar). */
  static final long DURA_MS = 60 * 60 * 1000;

  /** Cuántos links como mucho (una película por vez, en la práctica). */
  private static final int MAXIMO = 50;

  /** Link original -> adónde mandó y cuándo (en toda la app). */
  private static final Map<Uri, Recordada> RECORDADAS = new ConcurrentHashMap<>();

  private static final class Recordada {
    final Uri destino;
    final long cuando;

    Recordada(Uri destino, long cuando) {
      this.destino = destino;
      this.cuando = cuando;
    }
  }

  /** Arma una por pedido de ExoPlayer. */
  static final class Factory implements DataSource.Factory {
    private final DataSource.Factory base;

    Factory(@NonNull DataSource.Factory base) {
      this.base = base;
    }

    @NonNull
    @Override
    public DataSource createDataSource() {
      return new KairosRedireccionFija(base.createDataSource());
    }
  }

  private final DataSource fuente;

  KairosRedireccionFija(@NonNull DataSource fuente) {
    this.fuente = fuente;
  }

  /** Para las pruebas: que cada una empiece sin nada recordado. */
  static void olvidarTodo() {
    RECORDADAS.clear();
  }

  @Nullable
  private static Uri recordada(Uri original) {
    Recordada r = RECORDADAS.get(original);
    if (r == null) {
      return null;
    }
    if (System.currentTimeMillis() - r.cuando > DURA_MS) {
      RECORDADAS.remove(original);
      return null;
    }
    return r.destino;
  }

  private static void recordar(Uri original, Uri destino) {
    if (RECORDADAS.size() >= MAXIMO) {
      RECORDADAS.clear();
    }
    RECORDADAS.put(original, new Recordada(destino, System.currentTimeMillis()));
  }

  @Override
  public long open(@NonNull DataSpec dataSpec) throws IOException {
    Uri original = dataSpec.uri;
    Uri destino = recordada(original);
    if (destino != null) {
      try {
        return fuente.open(dataSpec.withUri(destino));
      } catch (HttpDataSource.HttpDataSourceException e) {
        Throwable causa = e.getCause();
        if (causa instanceof InterruptedIOException && !(causa instanceof SocketTimeoutException)) {
          throw e; // lo cancelaron (se cerró el video o se volvió a saltar): no hay que reintentar
        }
        // Venció: se vuelve a pedir el link original (y se recuerda adonde mande ahora)
        RECORDADAS.remove(original);
        fuente.close();
      }
    }
    long largo = fuente.open(dataSpec);
    Uri adonde = fuente.getUri();
    if (adonde != null && !adonde.equals(original)) {
      recordar(original, adonde);
    }
    return largo;
  }

  @Override
  public int read(@NonNull byte[] buffer, int offset, int length) throws IOException {
    return fuente.read(buffer, offset, length);
  }

  @Override
  public void addTransferListener(@NonNull TransferListener transferListener) {
    fuente.addTransferListener(transferListener);
  }

  @Nullable
  @Override
  public Uri getUri() {
    return fuente.getUri();
  }

  @NonNull
  @Override
  public Map<String, List<String>> getResponseHeaders() {
    return fuente.getResponseHeaders();
  }

  @Override
  public void close() throws IOException {
    fuente.close();
  }
}
