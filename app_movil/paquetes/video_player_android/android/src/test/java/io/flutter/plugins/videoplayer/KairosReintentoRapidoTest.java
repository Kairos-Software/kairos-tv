package io.flutter.plugins.videoplayer;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import android.net.Uri;
import androidx.media3.common.C;
import androidx.media3.common.PlaybackException;
import androidx.media3.datasource.DataSpec;
import androidx.media3.datasource.HttpDataSource;
import androidx.media3.exoplayer.DefaultLoadControl;
import androidx.media3.exoplayer.analytics.PlayerId;
import androidx.media3.exoplayer.source.LoadEventInfo;
import androidx.media3.exoplayer.source.MediaLoadData;
import androidx.media3.exoplayer.upstream.LoadErrorHandlingPolicy;
import java.io.IOException;
import java.net.ConnectException;
import java.net.SocketTimeoutException;
import java.util.HashMap;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;

/**
 * Kairos TV: un servidor saturado a veces no atiende la conexión (medido: 3 de cada 7 intentos
 * con un proveedor Xtream). En vez de esperar 25 s cada vez, se espera 5 y se reintenta enseguida;
 * una película reintenta más antes de dar error. Y una película guarda lo ya visto.
 */
@RunWith(RobolectricTestRunner.class)
public final class KairosReintentoRapidoTest {
  private static final DataSpec PEDIDO = new DataSpec(Uri.parse("http://s:1/movie/u/c/26461.avi"));

  private static LoadErrorHandlingPolicy.LoadErrorInfo error(IOException causa, int vez) {
    LoadEventInfo evento = new LoadEventInfo(LoadEventInfo.getNewId(), PEDIDO, 0);
    return new LoadErrorHandlingPolicy.LoadErrorInfo(evento, new MediaLoadData(C.DATA_TYPE_MEDIA), causa, vez);
  }

  private static IOException noAtendio() {
    return new HttpDataSource.HttpDataSourceException(
        new SocketTimeoutException("connect timed out"),
        PEDIDO,
        PlaybackException.ERROR_CODE_IO_NETWORK_CONNECTION_TIMEOUT,
        HttpDataSource.HttpDataSourceException.TYPE_OPEN);
  }

  @Test
  public void siNoAtendioReintentaEnseguida() {
    KairosReintentoRapido regla = new KairosReintentoRapido(true);
    // Aunque ya vayan varios intentos, la pausa es corta (de fábrica crecía hasta 5 s)
    assertEquals(KairosReintentoRapido.PAUSA_MS, regla.getRetryDelayMsFor(error(noAtendio(), 1)));
    assertEquals(KairosReintentoRapido.PAUSA_MS, regla.getRetryDelayMsFor(error(noAtendio(), 5)));
    assertEquals(
        KairosReintentoRapido.PAUSA_MS,
        regla.getRetryDelayMsFor(error(new IOException(new ConnectException("refused")), 2)));
  }

  @Test
  public void otrosErroresComoDeFabrica() {
    KairosReintentoRapido regla = new KairosReintentoRapido(true);
    assertEquals(2000, regla.getRetryDelayMsFor(error(new IOException("otra cosa"), 3)));
    assertFalse(KairosReintentoRapido.noAtendio(new IOException("otra cosa")));
    assertTrue(KairosReintentoRapido.noAtendio(noAtendio()));
  }

  @Test
  public void unaPeliculaReintentaMasQueUnCanal() {
    assertEquals(
        KairosReintentoRapido.REINTENTOS_ARCHIVO,
        new KairosReintentoRapido(true).getMinimumLoadableRetryCount(C.DATA_TYPE_MEDIA));
    // En vivo, los de fábrica: si no, tardaría en pasar a otra señal del canal
    assertEquals(3, new KairosReintentoRapido(false).getMinimumLoadableRetryCount(C.DATA_TYPE_MEDIA));
  }

  @Test
  public void conectarEsperaPocoYUnaPeliculaYaNoEspera90Segundos() {
    assertEquals(5_000, HttpVideoAsset.KAIROS_ESPERA_CONEXION_MS);
    assertEquals(20_000, HttpVideoAsset.KAIROS_ESPERA_LECTURA_ARCHIVO_MS);
  }

  private static long loVistoQueGuarda(String url) {
    DefaultLoadControl.Builder buffer = KairosTele.buffer();
    VideoAsset.kairosAjustarBuffer(
        VideoAsset.fromRemoteUrl(url, VideoAsset.StreamingFormat.UNKNOWN, new HashMap<>(), null), buffer);
    return buffer.build().getBackBufferDurationUs(PlayerId.UNSET);
  }

  @Test
  public void unaPeliculaGuardaLoYaVisto() {
    // Volver 10 o 20 segundos es al instante: no se le pide de nuevo al servidor
    assertEquals(90_000_000L, loVistoQueGuarda("http://s:1/movie/u/c/26461.avi"));
    assertEquals(90_000_000L, loVistoQueGuarda("http://s:1/series/u/c/9.mkv"));
    // Un canal en vivo no (no se puede volver atrás)
    assertEquals(0L, loVistoQueGuarda("http://s:1/live/u/c/444969.ts"));
  }
}
