package io.flutter.plugins.videoplayer;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import android.net.Uri;
import androidx.media3.datasource.DataSource;
import androidx.media3.datasource.DataSpec;
import androidx.media3.datasource.DefaultHttpDataSource;
import java.io.IOException;
import java.util.Arrays;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;

/**
 * Kairos TV: una película de una lista Xtream (".../movie/usuario/clave/123.avi") redirige a
 * otro servidor, y ese paso es el lento. ExoPlayer pide el archivo varias veces (un .avi, 3
 * antes de la primera imagen; cada salto, otra): solo la primera tiene que pasar por el link.
 * Con un servidor de verdad (local) que cuenta los pedidos (ServidorXtreamDePrueba).
 */
@RunWith(RobolectricTestRunner.class)
public final class KairosRedireccionFijaTest {
  private static final byte[] PELICULA = new byte[4096];

  private ServidorXtreamDePrueba servidor;

  @Before
  public void arrancar() throws IOException {
    KairosRedireccionFija.olvidarTodo();
    for (int i = 0; i < PELICULA.length; i++) {
      PELICULA[i] = (byte) i;
    }
    servidor = new ServidorXtreamDePrueba(PELICULA, "26480.avi");
  }

  @After
  public void parar() throws IOException {
    servidor.close();
    KairosRedireccionFija.olvidarTodo();
  }

  private static DataSource.Factory fabrica() {
    return new KairosRedireccionFija.Factory(
        new DefaultHttpDataSource.Factory().setAllowCrossProtocolRedirects(true));
  }

  /** Abre desde [desde] (como ExoPlayer al pedir otro pedazo), lee un poco y cierra. */
  private static byte[] leer(DataSource.Factory fabrica, String link, int desde) throws IOException {
    DataSource fuente = fabrica.createDataSource();
    try {
      fuente.open(new DataSpec.Builder().setUri(Uri.parse(link)).setPosition(desde).build());
      byte[] leido = new byte[16];
      int total = 0;
      while (total < leido.length) {
        int n = fuente.read(leido, total, leido.length - total);
        if (n < 0) {
          break;
        }
        total += n;
      }
      return leido;
    } finally {
      fuente.close();
    }
  }

  @Test
  public void elLinkLentoSePideUnaSolaVez() throws IOException {
    DataSource.Factory fabrica = fabrica();
    // Como un .avi: el principio, el índice del final y otra vez el principio; después, un salto
    leer(fabrica, servidor.link, 0);
    byte[] delFinal = leer(fabrica, servidor.link, 4000);
    leer(fabrica, servidor.link, 0);
    leer(fabrica, servidor.link, 2048);

    assertEquals("el link (lo lento) se pidió una sola vez", 1, servidor.alLink.get());
    assertEquals(4, servidor.alServidorDeVideo.get());
    assertArrayEquals(Arrays.copyOfRange(PELICULA, 4000, 4016), delFinal);
  }

  @Test
  public void unReproductorNuevoTambienVaDirecto() throws IOException {
    // Al reconectar o volver a la app se arma otro reproductor (otra fábrica)
    leer(fabrica(), servidor.link, 0);
    leer(fabrica(), servidor.link, 1000);
    assertEquals(1, servidor.alLink.get());
  }

  @Test
  public void siElPermisoVencioVuelveAPedirElLink() throws IOException {
    DataSource.Factory fabrica = fabrica();
    leer(fabrica, servidor.link, 0);
    servidor.permiso.incrementAndGet(); // el servidor dejó de aceptar el permiso que se recordaba

    byte[] leido = leer(fabrica, servidor.link, 100);
    assertArrayEquals(Arrays.copyOfRange(PELICULA, 100, 116), leido);
    assertEquals("se volvió a pedir el link", 2, servidor.alLink.get());
    // Y desde ahí, la nueva dirección
    leer(fabrica, servidor.link, 200);
    assertEquals(2, servidor.alLink.get());
  }

  @Test
  public void sinRedireccionAndaIgual() throws IOException {
    String directo = servidor.base + "/directo/pelicula.mp4";
    DataSource.Factory fabrica = fabrica();
    leer(fabrica, directo, 0);
    assertArrayEquals(Arrays.copyOfRange(PELICULA, 50, 66), leer(fabrica, directo, 50));
    assertEquals(0, servidor.alLink.get());
  }

  @Test
  public void soloLasPeliculasYCapitulos() {
    VideoAsset.StreamingFormat nada = VideoAsset.StreamingFormat.UNKNOWN;
    assertTrue(HttpVideoAsset.kairosEsArchivo("http://x/movie/u/c/26480.avi", nada));
    assertTrue(HttpVideoAsset.kairosEsArchivo("http://x/series/u/c/1.mkv?token=a", nada));
    assertFalse(HttpVideoAsset.kairosEsArchivo("http://x/live/u/c/444969.ts", nada));
    assertFalse(HttpVideoAsset.kairosEsArchivo("http://x/canal.m3u8", nada));
    assertFalse(HttpVideoAsset.kairosEsArchivo("http://x/movie/1.mp4", VideoAsset.StreamingFormat.HTTP_LIVE));
  }
}
