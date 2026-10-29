package io.flutter.plugins.videoplayer;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import androidx.media3.common.MimeTypes;
import androidx.media3.exoplayer.mediacodec.MediaCodecInfo;
import androidx.test.core.app.ApplicationProvider;
import java.util.Arrays;
import java.util.List;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;

/**
 * Kairos TV: el decodificador de video que se trabó en este aparato deja de ofrecerse (dos días,
 * aunque se cierre la app); se usa el siguiente (el de Android, por software).
 */
@RunWith(RobolectricTestRunner.class)
public final class KairosDecodificadoresTest {
  private static final String H264 = MimeTypes.VIDEO_H264;
  private static final String DEL_FABRICANTE = "OMX.MTK.VIDEO.DECODER.AVC";
  private static final String DE_ANDROID = "c2.android.avc.decoder";

  static MediaCodecInfo decodificador(String nombre, boolean software) {
    return MediaCodecInfo.newInstance(nombre, H264, H264, null, !software, software, !software, false, false);
  }

  static List<MediaCodecInfo> losDelAparato() {
    return Arrays.asList(decodificador(DEL_FABRICANTE, false), decodificador(DE_ANDROID, true));
  }

  private static List<String> nombres(List<MediaCodecInfo> lista) {
    String[] nombres = new String[lista.size()];
    for (int i = 0; i < lista.size(); i++) {
      nombres[i] = lista.get(i).name;
    }
    return Arrays.asList(nombres);
  }

  @Before
  @After
  public void olvidar() {
    KairosDecodificadores.olvidarTodo();
  }

  @Test
  public void sinNadaAnotadoOfreceTodosEnElOrdenDeAndroid() {
    assertEquals(
        Arrays.asList(DEL_FABRICANTE, DE_ANDROID), nombres(KairosDecodificadores.sinLosTrabados(losDelAparato(), H264, 0)));
  }

  @Test
  public void elTrabadoDejaDeOfrecerseYQuedaElDeAndroid() {
    KairosDecodificadores.anotarTrabado(H264, DEL_FABRICANTE, 1_000);

    assertEquals(Arrays.asList(DE_ANDROID), nombres(KairosDecodificadores.sinLosTrabados(losDelAparato(), H264, 2_000)));
    // Solo para ese tipo de video: con otro, el del fabricante puede andar
    assertFalse(KairosDecodificadores.estaTrabado(MimeTypes.VIDEO_H265, DEL_FABRICANTE, 2_000));
  }

  @Test
  public void siSeTrabaronTodosLosOfreceIgual() {
    KairosDecodificadores.anotarTrabado(H264, DEL_FABRICANTE, 0);
    KairosDecodificadores.anotarTrabado(H264, DE_ANDROID, 0);

    assertEquals(2, KairosDecodificadores.sinLosTrabados(losDelAparato(), H264, 1).size());
  }

  @Test
  public void aLosDosDiasSeVuelveAProbarElDelFabricante() {
    KairosDecodificadores.anotarTrabado(H264, DEL_FABRICANTE, 0);

    assertTrue(KairosDecodificadores.estaTrabado(H264, DEL_FABRICANTE, KairosDecodificadores.OLVIDAR_DESPUES_MS - 1));
    assertFalse(KairosDecodificadores.estaTrabado(H264, DEL_FABRICANTE, KairosDecodificadores.OLVIDAR_DESPUES_MS));
  }

  @Test
  public void quedaAnotadoAunqueSeCierreLaApp() {
    KairosDecodificadores.iniciar(ApplicationProvider.getApplicationContext());
    long ahora = System.currentTimeMillis();
    KairosDecodificadores.anotarTrabado(H264, DEL_FABRICANTE, ahora);

    // La app se vuelve a abrir: lee lo guardado en el aparato
    KairosDecodificadores.iniciar(ApplicationProvider.getApplicationContext());

    assertTrue(KairosDecodificadores.estaTrabado(H264, DEL_FABRICANTE, ahora + 1));
  }

  @Test
  public void olvidarLoDevuelve() {
    KairosDecodificadores.iniciar(ApplicationProvider.getApplicationContext());
    KairosDecodificadores.anotarTrabado(H264, DEL_FABRICANTE, 0);
    KairosDecodificadores.olvidar(H264, DEL_FABRICANTE);
    KairosDecodificadores.iniciar(ApplicationProvider.getApplicationContext());

    assertFalse(KairosDecodificadores.estaTrabado(H264, DEL_FABRICANTE, 1));
  }

  @Test
  public void hayOtroSoloSiQuedaAlgunoSinTrabar() {
    assertTrue(KairosDecodificadores.hayOtro(losDelAparato(), H264, DEL_FABRICANTE, 0));

    KairosDecodificadores.anotarTrabado(H264, DE_ANDROID, 0);
    assertFalse(KairosDecodificadores.hayOtro(losDelAparato(), H264, DEL_FABRICANTE, 1));
  }

  @Test
  public void elSelectorNoFallaSiElAparatoNoTieneNinguno() throws Exception {
    // En la compu no hay decodificadores de verdad: lista vacía, y no anota nada como ofrecido
    assertTrue(new KairosDecodificadores.Selector().getDecoderInfos(MimeTypes.VIDEO_VP9, false, false).isEmpty());
    assertEquals(null, KairosDecodificadores.ultimoOfrecido(MimeTypes.VIDEO_VP9));
  }
}
