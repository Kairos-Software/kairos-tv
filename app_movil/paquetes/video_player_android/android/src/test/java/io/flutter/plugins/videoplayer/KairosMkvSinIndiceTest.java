package io.flutter.plugins.videoplayer;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

import android.net.Uri;
import androidx.media3.common.C;
import androidx.media3.datasource.ByteArrayDataSource;
import androidx.media3.datasource.DataSpec;
import androidx.media3.extractor.DefaultExtractorInput;
import androidx.media3.extractor.Extractor;
import androidx.media3.extractor.PositionHolder;
import androidx.media3.extractor.SeekMap;
import androidx.media3.extractor.mkv.MatroskaExtractor;
import androidx.media3.extractor.text.SubtitleParser;
import androidx.media3.test.utils.FakeExtractorOutput;
import androidx.media3.test.utils.FakeTrackOutput;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;

/**
 * Kairos TV: adelantar en un MKV sin índice (KairosMkvSinIndice). Con una
 * película de verdad hecha con ffmpeg (src/test/resources/kairos/: 60 s de
 * imagen de prueba y un tono, un bloque cada 2 s) a la que se le borró el
 * índice, como las que vienen así en las listas. Se lee como lo hace ExoPlayer:
 * abre, lee y, cuando el lector pide ir a otro lado, vuelve a abrir desde ahí.
 */
@RunWith(RobolectricTestRunner.class)
public final class KairosMkvSinIndiceTest {
  private static final long SEGUNDO = 1_000_000;

  private static byte[] archivo(String nombre) throws IOException {
    try (InputStream entrada = KairosMkvSinIndiceTest.class.getClassLoader().getResourceAsStream("kairos/" + nombre)) {
      assertNotNull("falta src/test/resources/kairos/" + nombre, entrada);
      ByteArrayOutputStream salida = new ByteArrayOutputStream();
      byte[] pedazo = new byte[16 * 1024];
      for (int n = entrada.read(pedazo); n >= 0; n = entrada.read(pedazo)) {
        salida.write(pedazo, 0, n);
      }
      return salida.toByteArray();
    }
  }

  private static KairosMkvSinIndice nuevo() {
    return new KairosMkvSinIndice(SubtitleParser.Factory.UNSUPPORTED, 0);
  }

  /** Como el reproductor de verdad: si el lector vuelve a mandar el mismo formato (al volver a 0), no pasa nada. */
  private static FakeExtractorOutput salida() {
    return new FakeExtractorOutput((id, tipo) -> new FakeTrackOutput(tipo, /* deduplicateConsecutiveFormats= */ true));
  }

  private static FakeTrackOutput video(FakeExtractorOutput salida) {
    return salida.getTrackOutputsForType(C.TRACK_TYPE_VIDEO).get(0);
  }

  /**
   * Lee desde `desde` hasta que haya imágenes nuevas (más de `habia`) con el mapa ya mandado; si el
   * lector pide ir a otro lado, vuelve a abrir desde ahí. Devuelve cuántas veces abrió el archivo.
   */
  private static int leerHastaImagenNueva(Extractor lector, byte[] datos, long desde, FakeExtractorOutput salida,
      int habia) throws IOException {
    PositionHolder adonde = new PositionHolder();
    for (int pedidos = 1; pedidos <= 10; pedidos++) {
      ByteArrayDataSource fuente = new ByteArrayDataSource(datos);
      fuente.open(new DataSpec.Builder().setUri(Uri.parse("http://prueba/pelicula.mkv")).setPosition(desde).build());
      DefaultExtractorInput entrada = new DefaultExtractorInput(fuente, desde, datos.length);
      int resultado = Extractor.RESULT_CONTINUE;
      while (resultado == Extractor.RESULT_CONTINUE
          && (salida.seekMap == null
              || salida.getTrackOutputsForType(C.TRACK_TYPE_VIDEO).isEmpty()
              || video(salida).getSampleCount() <= habia)) {
        resultado = lector.read(entrada, adonde);
      }
      fuente.close();
      if (resultado == Extractor.RESULT_CONTINUE) {
        return pedidos;
      }
      if (resultado != Extractor.RESULT_SEEK) {
        fail("se terminó el archivo sin llegar a una imagen nueva");
      }
      desde = adonde.position;
    }
    fail("abrió el archivo más de 10 veces");
    return -1;
  }

  /** Abre la película, salta a `segundo` y devuelve la hora de la primera imagen después del salto. */
  private static long saltar(byte[] datos, long segundo, int[] pedidos) throws IOException {
    KairosMkvSinIndice lector = nuevo();
    FakeExtractorOutput salida = salida();
    lector.init(salida);
    leerHastaImagenNueva(lector, datos, 0, salida, 0);
    SeekMap.SeekPoints puntos = salida.seekMap.getSeekPoints(segundo * SEGUNDO);
    lector.seek(puntos.first.position, segundo * SEGUNDO);
    int habia = video(salida).getSampleCount();
    pedidos[0] = leerHastaImagenNueva(lector, datos, puntos.first.position, salida, habia);
    return video(salida).getSampleTimeUs(habia);
  }

  @Test
  public void elLectorDeSiempreNoDejaAdelantar() throws IOException {
    // El problema: un MKV sin índice "no se puede adelantar" y cada salto vuelve a 0
    FakeExtractorOutput salida = salida();
    MatroskaExtractor lector = new MatroskaExtractor(SubtitleParser.Factory.UNSUPPORTED, 0);
    lector.init(salida);
    leerHastaImagenNueva(lector, archivo("mkv_sin_indice.mkv"), 0, salida, 0);
    assertFalse(salida.seekMap.isSeekable());
  }

  @Test
  public void sinIndiceSePuedeAdelantar() throws IOException {
    FakeExtractorOutput salida = salida();
    KairosMkvSinIndice lector = nuevo();
    lector.init(salida);
    leerHastaImagenNueva(lector, archivo("mkv_sin_indice.mkv"), 0, salida, 0);
    assertTrue(salida.seekMap.isSeekable());
    assertEquals(60.0, salida.seekMap.getDurationUs() / (double) SEGUNDO, 0.1);
  }

  @Test
  public void unSaltoCaeCercaDeLoPedido() throws IOException {
    byte[] datos = archivo("mkv_sin_indice.mkv");
    for (long segundo : new long[] {20, 40, 55}) {
      int[] pedidos = new int[1];
      long horaUs = saltar(datos, segundo, pedidos);
      String que = "al " + segundo + " s cayó en " + horaUs / (double) SEGUNDO + " s";
      assertTrue(que, horaUs >= segundo * SEGUNDO - KairosMkvSinIndice.ANTES_US);
      assertTrue(que, horaUs <= segundo * SEGUNDO + KairosMkvSinIndice.DESPUES_US);
      assertTrue(que + " con " + pedidos[0] + " pedidos", pedidos[0] <= KairosMkvSinIndice.INTENTOS);
    }
  }

  @Test
  public void cercaDelPrincipioVuelveAEmpezar() throws IOException {
    int[] pedidos = new int[1];
    assertEquals(0, saltar(archivo("mkv_sin_indice.mkv"), 5, pedidos));
  }

  @Test
  public void conIndiceUsaElSuyo() throws IOException {
    // Con índice, nada cambia: el mapa es el del archivo (con cada bloque exacto)
    FakeExtractorOutput salida = salida();
    KairosMkvSinIndice lector = nuevo();
    lector.init(salida);
    leerHastaImagenNueva(lector, archivo("mkv_con_indice.mkv"), 0, salida, 0);
    assertTrue(salida.seekMap.isSeekable());
    assertFalse(salida.seekMap instanceof KairosMkvSinIndice.MapaAproximado);
  }

  @Test
  public void reconoceElPrincipioDeUnBloque() {
    // Marca del bloque, su tamaño (8 bytes), la marca de la hora, su tamaño (2 bytes) y la hora: 1000
    byte[] bloque = {0x1F, 0x43, (byte) 0xB6, 0x75, 0x01, 0, 0, 0, 0, 0, 0x10, 0, (byte) 0xE7, (byte) 0x82, 0x03,
        (byte) 0xE8};
    assertEquals(1000, KairosMkvSinIndice.horaDelBloque(bloque, 0, bloque.length));
    // Sin la hora enseguida no es un bloque (puede ser parte de la imagen)
    byte[] casi = bloque.clone();
    casi[12] = 0x42;
    assertEquals(-1, KairosMkvSinIndice.horaDelBloque(casi, 0, casi.length));
    // Cortado: no se sabe
    assertEquals(-1, KairosMkvSinIndice.horaDelBloque(bloque, 0, 14));
    // Como los escribe FFmpeg: con un control de errores (CRC-32) antes de la hora
    byte[] conControl = {0x1F, 0x43, (byte) 0xB6, 0x75, 0x20, 0x5B, 0x58, (byte) 0xBF, (byte) 0x84, 0x08, (byte) 0xA9,
        0x2C, 0x24, (byte) 0xE7, (byte) 0x82, 0x07, 0x59};
    assertEquals(0x0759, KairosMkvSinIndice.horaDelBloque(conControl, 0, conControl.length));
  }

  @Test
  public void estimaComoSiPesaraLoMismoCadaSegundo() {
    // Entre el byte 1.000 (0 s) y el 101.000 (100 s): el segundo 50 (menos 3 de margen) está por el 48.000
    assertEquals(48_000, KairosMkvSinIndice.estimar(50 * SEGUNDO, 1_000, 0, 101_000, 100 * SEGUNDO));
  }

  @Test
  public void laFabricaPoneElDeMkv() {
    boolean esta = false;
    for (Extractor lector : new KairosExtractores().createExtractors()) {
      assertFalse(lector instanceof MatroskaExtractor);
      esta |= lector instanceof KairosMkvSinIndice;
    }
    assertTrue(esta);
  }
}
