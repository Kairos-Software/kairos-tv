package io.flutter.plugins.videoplayer;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

import android.net.Uri;
import androidx.media3.common.C;
import androidx.media3.datasource.DataSource;
import androidx.media3.datasource.DataSpec;
import androidx.media3.datasource.DefaultHttpDataSource;
import androidx.media3.extractor.DefaultExtractorInput;
import androidx.media3.extractor.Extractor;
import androidx.media3.extractor.PositionHolder;
import androidx.media3.extractor.avi.AviExtractor;
import androidx.media3.extractor.mp4.Mp4Extractor;
import androidx.media3.extractor.text.SubtitleParser;
import androidx.media3.test.utils.FakeExtractorOutput;
import androidx.media3.test.utils.FakeTrackOutput;
import androidx.test.core.app.ApplicationProvider;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.HashMap;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;

/**
 * Kairos TV: películas de verdad (chiquitas, hechas con ffmpeg: src/test/resources/kairos/) con
 * el índice al final, como las .avi y muchas .mp4 de las listas. Se leen como lo hace ExoPlayer
 * (ProgressiveMediaPeriod: abre, lee y, cuando el lector pide ir a otro lado, cierra y vuelve a
 * abrir desde ahí) hasta tener la primera imagen, con las conexiones que arma la app
 * (HttpVideoAsset.kairosFabricaDeDatos), contra un servidor que se porta como Xtream. Cuenta
 * cuántas veces se pasó por el link de la lista, que en el servidor de verdad es lo que tarda
 * cerca de un minuto.
 */
@RunWith(RobolectricTestRunner.class)
public final class KairosPeliculaQueArrancaTest {
  private ServidorXtreamDePrueba servidor;

  @Before
  public void olvidar() {
    KairosRedireccionFija.olvidarTodo();
  }

  @After
  public void parar() throws IOException {
    if (servidor != null) {
      servidor.close();
    }
    KairosRedireccionFija.olvidarTodo();
  }

  private static byte[] archivo(String nombre) throws IOException {
    try (InputStream entrada = KairosPeliculaQueArrancaTest.class.getClassLoader().getResourceAsStream("kairos/" + nombre)) {
      assertNotNull("falta src/test/resources/kairos/" + nombre, entrada);
      ByteArrayOutputStream salida = new ByteArrayOutputStream();
      byte[] pedazo = new byte[16 * 1024];
      for (int n = entrada.read(pedazo); n >= 0; n = entrada.read(pedazo)) {
        salida.write(pedazo, 0, n);
      }
      return salida.toByteArray();
    }
  }

  /** Las conexiones que arma la app para ese link (las mismas que usa el reproductor). */
  private static DataSource.Factory deLaApp(String link) {
    HttpVideoAsset video =
        (HttpVideoAsset) VideoAsset.fromRemoteUrl(link, VideoAsset.StreamingFormat.UNKNOWN, new HashMap<>(), null);
    return video.kairosFabricaDeDatos(ApplicationProvider.getApplicationContext(), new DefaultHttpDataSource.Factory());
  }

  private static boolean hayImagen(FakeExtractorOutput salida) {
    if (salida.seekMap == null) {
      return false;
    }
    for (FakeTrackOutput pista : salida.getTrackOutputsForType(C.TRACK_TYPE_VIDEO)) {
      if (pista.getSampleCount() > 0) {
        return true;
      }
    }
    return false;
  }

  /** Lee como ExoPlayer hasta la primera imagen; devuelve cuántas veces pidió el archivo. */
  private static int pedidosHastaLaPrimeraImagen(Extractor lector, DataSource.Factory fabrica, String link)
      throws IOException {
    FakeExtractorOutput salida = new FakeExtractorOutput();
    lector.init(salida);
    PositionHolder adonde = new PositionHolder();
    long desde = 0;
    for (int pedidos = 1; pedidos <= 20; pedidos++) {
      DataSource fuente = fabrica.createDataSource();
      int resultado = Extractor.RESULT_CONTINUE;
      try {
        long largo = fuente.open(new DataSpec.Builder().setUri(Uri.parse(link)).setPosition(desde).build());
        DefaultExtractorInput entrada =
            new DefaultExtractorInput(fuente, desde, largo == C.LENGTH_UNSET ? C.LENGTH_UNSET : desde + largo);
        while (resultado == Extractor.RESULT_CONTINUE && !hayImagen(salida)) {
          resultado = lector.read(entrada, adonde);
        }
      } finally {
        fuente.close();
      }
      if (hayImagen(salida)) {
        return pedidos;
      }
      if (resultado != Extractor.RESULT_SEEK) {
        fail("se terminó el archivo sin llegar a la primera imagen");
      }
      desde = adonde.position;
    }
    fail("pidió el archivo más de 20 veces");
    return -1;
  }

  @Test
  public void unAviPasaUnaSolaVezPorElLink() throws IOException {
    servidor = new ServidorXtreamDePrueba(archivo("pelicula.avi"), "26480.avi");
    int pedidos = pedidosHastaLaPrimeraImagen(new AviExtractor(0, SubtitleParser.Factory.UNSUPPORTED),
        deLaApp(servidor.link), servidor.link);
    // El .avi tiene el índice al final: hay que ir a buscarlo y volver
    assertTrue("pidió el archivo " + pedidos + " veces", pedidos >= 3);
    assertEquals("por el link (lo lento) una sola vez", 1, servidor.alLink.get());
    assertEquals(pedidos, servidor.alServidorDeVideo.get());
  }

  @Test
  public void unMp4ConElIndiceAlFinalTambien() throws IOException {
    servidor = new ServidorXtreamDePrueba(archivo("pelicula_indice_al_final.mp4"), "26455.mp4");
    int pedidos = pedidosHastaLaPrimeraImagen(new Mp4Extractor(SubtitleParser.Factory.UNSUPPORTED),
        deLaApp(servidor.link), servidor.link);
    assertTrue("pidió el archivo " + pedidos + " veces", pedidos >= 2);
    assertEquals(1, servidor.alLink.get());
  }

  @Test
  public void sinElArregloPasabaPorElLinkCadaVez() throws IOException {
    // Lo que hacía antes (y hace ExoPlayer solo): cada pedido, otra vez por el link lento
    servidor = new ServidorXtreamDePrueba(archivo("pelicula.avi"), "26480.avi");
    DataSource.Factory comoAntes = new DefaultHttpDataSource.Factory().setAllowCrossProtocolRedirects(true);
    int pedidos =
        pedidosHastaLaPrimeraImagen(new AviExtractor(0, SubtitleParser.Factory.UNSUPPORTED), comoAntes, servidor.link);
    assertTrue(pedidos >= 3);
    assertEquals(pedidos, servidor.alLink.get());
  }
}
