package io.flutter.plugins.videoplayer;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import android.os.Handler;
import android.os.Looper;
import androidx.media3.common.C;
import androidx.media3.decoder.ffmpeg.FfmpegAudioRenderer;
import androidx.media3.exoplayer.Renderer;
import androidx.media3.exoplayer.audio.AudioRendererEventListener;
import androidx.media3.exoplayer.audio.MediaCodecAudioRenderer;
import androidx.test.core.app.ApplicationProvider;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.List;
import org.junit.After;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;

/**
 * Kairos TV: el audio Dolby (AC3 / E-AC3 / TrueHD) y DTS de muchas películas
 * "HD", que muchos aparatos no saben leer (se veían sin sonido). Lo decodifica
 * FFmpeg (libffmpegJNI.so, ver android/ffmpeg/README.md). En la compu la
 * biblioteca no se puede cargar (es para los procesadores de los aparatos):
 * acá se prueba que el reproductor lo ponga después del de Android y que las
 * bibliotecas que van en la app traigan esos decodificadores.
 */
@RunWith(RobolectricTestRunner.class)
public final class KairosAudioDolbyTest {

  /** Los nombres de los decodificadores, como quedan escritos adentro de libffmpegJNI.so. */
  private static final String[] DECODIFICADORES = {
    "ATSC A/52A (AC-3)", "ATSC A/52B (AC-3, E-AC-3)", "DCA (DTS Coherent Acoustics)", "TrueHD",
    "MLP (Meridian Lossless Packing)",
  };

  private static List<Renderer> audioDeLaFabrica() {
    Renderer[] todos =
        new KairosRenderersFactory(ApplicationProvider.getApplicationContext())
            .createRenderers(
                new Handler(Looper.getMainLooper()),
                new androidx.media3.exoplayer.video.VideoRendererEventListener() {},
                new AudioRendererEventListener() {},
                cues -> {},
                metadata -> {});
    List<Renderer> audio = new ArrayList<>();
    for (Renderer renderer : todos) {
      if (renderer.getTrackType() == C.TRACK_TYPE_AUDIO) {
        audio.add(renderer);
      }
    }
    return audio;
  }

  @After
  public void olvidar() {
    KairosRenderersFactory.ffmpegParaPruebas(null);
    KairosAudioMpeg.disponibleParaPruebas(null);
  }

  @Test
  public void vaAlFinalDespuesDelDeAndroidYDelMp2() {
    KairosRenderersFactory.ffmpegParaPruebas(true);
    KairosAudioMpeg.disponibleParaPruebas(true);
    List<Renderer> audio = audioDeLaFabrica();
    assertTrue(audio.get(0) instanceof MediaCodecAudioRenderer);
    assertTrue(audio.get(audio.size() - 2) instanceof KairosAudioRenderer);
    assertTrue(audio.get(audio.size() - 1) instanceof FfmpegAudioRenderer);
  }

  @Test
  public void sinLaBibliotecaTodoSigueComoAntes() {
    // En la compu no se puede cargar: así queda en un aparato si algún día falla (sin sonido, como antes)
    for (Renderer renderer : audioDeLaFabrica()) {
      assertFalse(renderer instanceof FfmpegAudioRenderer);
    }
  }

  @Test
  public void lasBibliotecasDeLaAppTraenLosDecodificadores() throws Exception {
    for (String abi : new String[] {"arm64-v8a", "armeabi-v7a"}) {
      File biblioteca = new File("src/main/jniLibs/" + abi + "/libffmpegJNI.so");
      assertTrue("Falta " + biblioteca + " (ver android/ffmpeg/README.md)", biblioteca.isFile());
      // ISO_8859_1: cada byte es un carácter, así se buscan los textos dentro del binario
      String contenido = new String(Files.readAllBytes(biblioteca.toPath()), StandardCharsets.ISO_8859_1);
      for (String decodificador : DECODIFICADORES) {
        assertTrue(abi + " no trae " + decodificador, contenido.contains(decodificador));
      }
      // FFmpeg 6.0 (libavcodec 60): la que se probó con el ffmpeg_jni.cc de media3 1.9.2
      assertTrue(abi + ": no es FFmpeg 6.0", contenido.contains("Lavc60."));
      // Solo esos: con todos los de FFmpeg pesaría más de 10 MB (los nombres de todos los formatos están
      // igual adentro, en la tabla de FFmpeg: por eso se mira el tamaño)
      assertTrue(abi + ": pesa demasiado", biblioteca.length() < 3_000_000);
    }
    assertEquals(2, new File("src/main/jniLibs").list().length);
  }
}
