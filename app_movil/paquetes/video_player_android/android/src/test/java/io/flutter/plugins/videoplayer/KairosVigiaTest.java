package io.flutter.plugins.videoplayer;

import static io.flutter.plugins.videoplayer.KairosVigia.Accion.FALLAR;
import static io.flutter.plugins.videoplayer.KairosVigia.Accion.NADA;
import static io.flutter.plugins.videoplayer.KairosVigia.Accion.OTRO_DECODIFICADOR;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.robolectric.Shadows.shadowOf;

import android.os.Looper;
import androidx.media3.common.Format;
import androidx.media3.common.MimeTypes;
import androidx.media3.common.PlaybackException;
import androidx.media3.common.Tracks;
import androidx.media3.common.util.Size;
import androidx.media3.exoplayer.DecoderCounters;
import androidx.media3.exoplayer.ExoPlaybackException;
import androidx.media3.exoplayer.ExoPlayer;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;

/**
 * Kairos TV: un aparato cuyo decodificador recibe el video y no devuelve ninguna imagen (la señal
 * "no conecta nunca" aunque en un celular ande). El vigía lo cambia por el de Android y, si ese
 * tampoco puede, le avisa a la app que es el aparato (no el servidor de la señal).
 */
@RunWith(RobolectricTestRunner.class)
public final class KairosVigiaTest {
  private static final String H264 = MimeTypes.VIDEO_H264;
  private static final String DEL_FABRICANTE = "OMX.MTK.VIDEO.DECODER.AVC";
  private static final String DE_ANDROID = "c2.android.avc.decoder";
  private static final String DIRECCION = "http://servidor/live/u/c/123.ts";

  /** Lo que el vigía le pidió al reproductor. */
  private static final class Pedidos implements KairosVigia.Acciones {
    int cambios;
    final List<String> fallas = new ArrayList<>();

    @Override
    public void otroDecodificador() {
      cambios++;
    }

    @Override
    public void fallar(String detalle) {
      fallas.add(detalle);
    }
  }

  private ExoPlayer exoPlayer;
  private DecoderCounters contadores;
  private Pedidos pedidos;

  @Before
  public void preparar() {
    KairosDecodificadores.olvidarTodo();
    KairosVigia.olvidarTodos();
    KairosDecodificadores.todosParaPruebas(KairosDecodificadoresTest.losDelAparato());
    contadores = new DecoderCounters();
    exoPlayer = mock(ExoPlayer.class);
    when(exoPlayer.getVideoDecoderCounters()).thenReturn(contadores);
    when(exoPlayer.getSurfaceSize()).thenReturn(Size.UNKNOWN); // hay superficie (de tamaño desconocido)
    when(exoPlayer.getCurrentTracks()).thenReturn(Tracks.EMPTY);
    pedidos = new Pedidos();
  }

  @After
  public void olvidar() {
    KairosDecodificadores.olvidarTodo();
    KairosVigia.olvidarTodos();
  }

  private static Format videoH264() {
    return new Format.Builder().setSampleMimeType(H264).setWidth(1920).setHeight(1080).setFrameRate(25).build();
  }

  /** Llegaron 4 s de video y el decodificador [nombre] recibió 8 cuadros sin devolver ninguno. */
  private KairosVigia conVideoTrabadoEn(String nombre) {
    when(exoPlayer.getTotalBufferedDuration()).thenReturn(4_000L);
    KairosVigia vigia = new KairosVigia(exoPlayer, pedidos, DIRECCION);
    vigia.onVideoInputFormatChanged(null, videoH264(), null);
    vigia.onVideoDecoderInitialized(null, nombre, 0, 0);
    contadores.queuedInputBufferCount = 8;
    return vigia;
  }

  private static void pasan(long milisegundos) {
    shadowOf(Looper.getMainLooper()).idleFor(Duration.ofMillis(milisegundos));
  }

  // ── Las reglas ──

  @Test
  public void sinVideoGuardadoNoSeJuzgaAlDecodificador() {
    assertEquals(NADA, KairosVigia.decidir(false, true, true, DEL_FABRICANTE, false, true, 8, 0, 60_000, 60_000, 500, 0));
  }

  @Test
  public void siYaSeVioOSinSuperficieNoHaceNada() {
    assertEquals(NADA, KairosVigia.decidir(true, true, true, DEL_FABRICANTE, false, true, 8, 0, 60_000, 60_000, 4_000, 0));
    assertEquals(NADA, KairosVigia.decidir(false, false, true, null, false, true, 0, 0, 0, 60_000, 4_000, 0));
  }

  @Test
  public void unDecodificadorQueDevuelveImagenNoEstaTrabado() {
    assertEquals(NADA, KairosVigia.decidir(false, true, true, DEL_FABRICANTE, false, true, 8, 1, 60_000, 60_000, 4_000, 0));
  }

  @Test
  public void leDaTiempoAntesDeDarloPorTrabado() {
    long casi = KairosVigia.TRABADO_MS - 1;
    assertEquals(NADA, KairosVigia.decidir(false, true, true, DEL_FABRICANTE, false, true, 8, 0, casi, casi, 4_000, 0));
  }

  @Test
  public void trabadoDelFabricanteConOtroDisponibleCambia() {
    long ya = KairosVigia.TRABADO_MS;
    assertEquals(
        OTRO_DECODIFICADOR, KairosVigia.decidir(false, true, true, DEL_FABRICANTE, false, true, 8, 0, ya, ya, 4_000, 0));
  }

  @Test
  public void trabadoSinOtroOConElDeAndroidOYaCambiadoSeRinde() {
    long ya = KairosVigia.TRABADO_MS;
    assertEquals(FALLAR, KairosVigia.decidir(false, true, true, DEL_FABRICANTE, false, false, 8, 0, ya, ya, 4_000, 0));
    assertEquals(FALLAR, KairosVigia.decidir(false, true, true, DE_ANDROID, true, true, 8, 0, ya, ya, 4_000, 0));
    assertEquals(
        FALLAR,
        KairosVigia.decidir(false, true, true, DEL_FABRICANTE, false, true, 8, 0, ya, ya, 4_000, KairosVigia.MAXIMO_CAMBIOS));
  }

  @Test
  public void elDecodificadorQueNoTerminaDeArrancarSeRinde() {
    assertEquals(NADA, KairosVigia.decidir(false, true, true, null, false, true, 0, 0, 0, 9_000, 4_000, 0));
    assertEquals(
        FALLAR, KairosVigia.decidir(false, true, true, null, false, true, 0, 0, 0, KairosVigia.SIN_ARRANCAR_MS, 4_000, 0));
  }

  // ── Con el reproductor ──

  @Test
  public void elDelFabricanteTrabadoSeCambiaPorElDeAndroidYQuedaAnotado() {
    KairosVigia vigia = conVideoTrabadoEn(DEL_FABRICANTE);

    pasan(KairosVigia.TRABADO_MS + 2_000);

    assertEquals(1, pedidos.cambios);
    assertTrue(pedidos.fallas.isEmpty());
    assertTrue(KairosDecodificadores.estaTrabado(H264, DEL_FABRICANTE, System.currentTimeMillis()));
    assertEquals("cambiando", vigia.diagnostico().get("causa"));
    assertEquals(true, vigia.diagnostico().get("cambiando"));
  }

  @Test
  public void siElDeAndroidTambienSeTrabaEsElVideoYSeRinde() {
    KairosVigia vigia = conVideoTrabadoEn(DEL_FABRICANTE);
    pasan(KairosVigia.TRABADO_MS + 2_000);

    // Arrancó de nuevo, ahora con el de Android, y tampoco devuelve imagen
    contadores.queuedInputBufferCount = 0;
    vigia.onVideoInputFormatChanged(null, videoH264(), null);
    vigia.onVideoDecoderInitialized(null, DE_ANDROID, 0, 0);
    pasan(1_000);
    contadores.queuedInputBufferCount = 8;
    pasan(KairosVigia.TRABADO_MS + 2_000);

    assertEquals(1, pedidos.cambios);
    assertEquals(1, pedidos.fallas.size());
    assertTrue(pedidos.fallas.get(0).startsWith(KairosVigia.TRABADO));
    // No era culpa del del fabricante: se lo deja de anotar
    assertFalse(KairosDecodificadores.estaTrabado(H264, DEL_FABRICANTE, System.currentTimeMillis()));
    assertEquals("aparato", vigia.diagnostico().get("causa"));
  }

  @Test
  public void conImagenNoHaceNada() {
    KairosVigia vigia = conVideoTrabadoEn(DEL_FABRICANTE);
    contadores.renderedOutputBufferCount = 1;
    vigia.onRenderedFirstFrame(null, new Object(), 0);

    pasan(KairosVigia.TRABADO_MS * 3);

    assertEquals(0, pedidos.cambios);
    assertTrue(pedidos.fallas.isEmpty());
  }

  @Test
  public void unErrorDelDecodificadorDelFabricanteASeguirConOtro() {
    KairosVigia vigia = conVideoTrabadoEn(DEL_FABRICANTE);
    ExoPlaybackException error =
        ExoPlaybackException.createForRenderer(
            new IllegalStateException(), "MediaCodecVideoRenderer", 0, videoH264(), 4, /* mediaPeriodId= */ null,
            false, PlaybackException.ERROR_CODE_DECODING_FAILED);

    assertTrue(vigia.otroDecodificadorPorError(error));
    assertEquals(1, pedidos.cambios);
    // Con el de Android ya no hay otro: el error sigue su camino
    vigia.onVideoDecoderInitialized(null, DE_ANDROID, 0, 0);
    assertFalse(vigia.otroDecodificadorPorError(error));
  }

  // ── El diagnóstico ──

  @Test
  public void elDiagnosticoDiceQueLlegoYQueSalio() {
    conVideoTrabadoEn(DEL_FABRICANTE);

    Map<String, Object> diagnostico = KairosVigia.diagnostico(DIRECCION);

    assertNotNull(diagnostico);
    String texto = (String) diagnostico.get("texto");
    assertTrue(texto, texto.contains("video h264 1920x1080 25 fps"));
    assertTrue(texto, texto.contains("deco " + DEL_FABRICANTE + ": entraron 8, salieron 0"));
    assertTrue(texto, texto.contains("guardado 4 s"));
    assertEquals("aparato", diagnostico.get("causa"));
  }

  @Test
  public void siNoLlegoNadaEsElServidor() {
    when(exoPlayer.getTotalBufferedDuration()).thenReturn(0L);
    KairosVigia vigia = new KairosVigia(exoPlayer, pedidos, DIRECCION);
    vigia.onLoadError(null, cargaFallida(), null, new java.net.SocketTimeoutException("connect timed out"), false);

    Map<String, Object> diagnostico = vigia.diagnostico();

    assertEquals("sin_datos", diagnostico.get("causa"));
    String texto = (String) diagnostico.get("texto");
    assertTrue(texto, texto.contains("no llegó nada del servidor"));
    assertTrue(texto, texto.contains("1 reintento (connect timed out)"));
  }

  @Test
  public void alCerrarGuardaLoQueVioYSeSiguePidiendo() {
    KairosVigia vigia = conVideoTrabadoEn(DEL_FABRICANTE);
    vigia.cerrar();
    when(exoPlayer.getVideoDecoderCounters()).thenReturn(null); // el reproductor ya no está

    assertTrue(((String) KairosVigia.diagnostico(DIRECCION).get("texto")).contains("entraron 8"));
    assertNull(KairosVigia.diagnostico("http://otra/direccion"));
  }

  private static androidx.media3.exoplayer.source.LoadEventInfo cargaFallida() {
    return new androidx.media3.exoplayer.source.LoadEventInfo(
        0, new androidx.media3.datasource.DataSpec(android.net.Uri.parse(DIRECCION)), 0);
  }
}
