package io.flutter.plugins.videoplayer;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNull;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import androidx.media3.common.MediaItem;
import androidx.media3.common.MimeTypes;
import androidx.media3.datasource.DefaultHttpDataSource;
import androidx.test.core.app.ApplicationProvider;
import java.util.HashMap;
import java.util.Map;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;

/**
 * Kairos TV: canales en vivo de listas Xtream (".../live/usuario/clave/123.ts", MPEG-TS
 * directo con una redirección en el medio) y los tiempos de espera de la conexión.
 */
@RunWith(RobolectricTestRunner.class)
public final class KairosHttpVideoAssetTest {
  private static final String XTREAM = "http://servidor:8080/live/usuario/clave/444969.ts";
  private static final String VLC = "VLC/3.0.21 LibVLC/3.0.21";

  private static DefaultHttpDataSource.Factory fabricaDePrueba() {
    DefaultHttpDataSource.Factory fabrica = mock(DefaultHttpDataSource.Factory.class);
    when(fabrica.setUserAgent(any())).thenReturn(fabrica);
    when(fabrica.setAllowCrossProtocolRedirects(anyBoolean())).thenReturn(fabrica);
    when(fabrica.setDefaultRequestProperties(anyMap())).thenReturn(fabrica);
    when(fabrica.setConnectTimeoutMs(anyInt())).thenReturn(fabrica);
    when(fabrica.setReadTimeoutMs(anyInt())).thenReturn(fabrica);
    return fabrica;
  }

  private static String mimeDe(String url, VideoAsset.StreamingFormat formato) {
    MediaItem item = VideoAsset.fromRemoteUrl(url, formato, new HashMap<>(), null).getMediaItem();
    assert item.localConfiguration != null;
    return item.localConfiguration.mimeType;
  }

  @Test
  public void unTsDirectoEsMpegTs() {
    assertEquals(MimeTypes.VIDEO_MP2T, mimeDe(XTREAM, VideoAsset.StreamingFormat.UNKNOWN));
    assertEquals(MimeTypes.VIDEO_MP2T, mimeDe(XTREAM + "?token=abc", VideoAsset.StreamingFormat.UNKNOWN));
    assertEquals(MimeTypes.VIDEO_MP2T, mimeDe("http://x/CANAL.TS", VideoAsset.StreamingFormat.UNKNOWN));
  }

  @Test
  public void loQueNoEsTsNoCambia() {
    // Una lista HLS sigue siendo HLS (aunque sus pedacitos sean .ts)
    assertEquals(
        MimeTypes.APPLICATION_M3U8, mimeDe("http://x/canal.m3u8", VideoAsset.StreamingFormat.HTTP_LIVE));
    assertEquals(MimeTypes.APPLICATION_M3U8, mimeDe(XTREAM, VideoAsset.StreamingFormat.HTTP_LIVE));
    // Sin extensión o un .mp4: ExoPlayer lo averigua solo
    assertNull(mimeDe("http://servidor:8080/usuario/clave/444969", VideoAsset.StreamingFormat.UNKNOWN));
    assertNull(mimeDe("http://x/pelicula.mp4", VideoAsset.StreamingFormat.UNKNOWN));
    assertNull(mimeDe("http://x/stats?archivo=algo.ts#no", VideoAsset.StreamingFormat.UNKNOWN));
  }

  @Test
  public void esperaComoVlcYSigueLasRedireccionesConSuUserAgent() {
    Map<String, String> cabeceras = new HashMap<>();
    cabeceras.put("Referer", "http://servidor/");
    VideoAsset asset =
        VideoAsset.fromRemoteUrl(XTREAM, VideoAsset.StreamingFormat.UNKNOWN, cabeceras, VLC);
    DefaultHttpDataSource.Factory fabrica = fabricaDePrueba();

    ((HttpVideoAsset) asset)
        .getMediaSourceFactory(ApplicationProvider.getApplicationContext(), fabrica);

    verify(fabrica).setUserAgent(VLC);
    verify(fabrica).setAllowCrossProtocolRedirects(true);
    verify(fabrica).setDefaultRequestProperties(cabeceras);
    verify(fabrica).setConnectTimeoutMs(HttpVideoAsset.KAIROS_ESPERA_CONEXION_MS);
    verify(fabrica).setReadTimeoutMs(HttpVideoAsset.KAIROS_ESPERA_LECTURA_MS);
    assertEquals(25_000, HttpVideoAsset.KAIROS_ESPERA_CONEXION_MS);
    assertEquals(30_000, HttpVideoAsset.KAIROS_ESPERA_LECTURA_MS);
  }

  @Test
  public void unaPeliculaEsperaMasQueUnCanalEnVivo() {
    VideoAsset.StreamingFormat nada = VideoAsset.StreamingFormat.UNKNOWN;
    // Archivos (películas y capítulos): hasta 90 s a que el servidor mande lo primero
    assertEquals(90_000, HttpVideoAsset.kairosEsperaLectura("http://s:1/movie/u/c/26473.mp4", nada));
    assertEquals(90_000, HttpVideoAsset.kairosEsperaLectura("http://s:1/series/u/c/9.MKV?x=1", nada));
    assertEquals(90_000, HttpVideoAsset.kairosEsperaLectura("http://s:1/movie/u/c/26461.avi", nada));
    // En vivo, igual que antes
    assertEquals(30_000, HttpVideoAsset.kairosEsperaLectura(XTREAM, nada));
    assertEquals(30_000, HttpVideoAsset.kairosEsperaLectura("http://x/canal.m3u8?t=1", nada));
    assertEquals(30_000, HttpVideoAsset.kairosEsperaLectura("http://x/pelicula.mp4", VideoAsset.StreamingFormat.HTTP_LIVE));

    DefaultHttpDataSource.Factory fabrica = fabricaDePrueba();
    ((HttpVideoAsset) VideoAsset.fromRemoteUrl("http://s:1/movie/u/c/1.mp4", nada, new HashMap<>(), null))
        .getMediaSourceFactory(ApplicationProvider.getApplicationContext(), fabrica);
    verify(fabrica).setReadTimeoutMs(90_000);
  }
}
