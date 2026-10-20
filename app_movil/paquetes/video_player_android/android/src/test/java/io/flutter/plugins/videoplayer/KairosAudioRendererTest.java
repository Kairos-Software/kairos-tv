package io.flutter.plugins.videoplayer;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import android.os.Handler;
import android.os.Looper;
import androidx.media3.common.C;
import androidx.media3.common.Format;
import androidx.media3.common.MimeTypes;
import androidx.media3.exoplayer.Renderer;
import androidx.media3.exoplayer.RendererCapabilities;
import androidx.media3.exoplayer.audio.AudioRendererEventListener;
import androidx.media3.exoplayer.audio.DefaultAudioSink;
import androidx.media3.exoplayer.audio.MediaCodecAudioRenderer;
import androidx.test.core.app.ApplicationProvider;
import java.util.ArrayList;
import java.util.List;
import org.junit.After;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;

/**
 * Kairos TV: el audio MP2 (el de los canales de cable y satélite), que Android
 * no trae. El decodificador en sí se prueba en la compu (src/test/cpp/): acá,
 * que el reproductor lo use solo para MP1 / MP2 y después del de Android.
 */
@RunWith(RobolectricTestRunner.class)
public final class KairosAudioRendererTest {

  private static Format audio(String mime) {
    return new Format.Builder().setSampleMimeType(mime).setChannelCount(2).setSampleRate(48000).build();
  }

  private static KairosAudioRenderer renderer() {
    return new KairosAudioRenderer(
        new Handler(Looper.getMainLooper()),
        new AudioRendererEventListener() {},
        new DefaultAudioSink.Builder(ApplicationProvider.getApplicationContext()).build());
  }

  private static int soporte(Format format) throws Exception {
    return RendererCapabilities.getFormatSupport(renderer().supportsFormat(format));
  }

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
    KairosAudioMpeg.disponibleParaPruebas(null);
  }

  @Test
  public void decodificaMp1yMp2PeroNoLoQueYaTraeAndroid() throws Exception {
    KairosAudioMpeg.disponibleParaPruebas(true);
    assertEquals(C.FORMAT_HANDLED, soporte(audio(MimeTypes.AUDIO_MPEG_L2)));
    assertEquals(C.FORMAT_HANDLED, soporte(audio(MimeTypes.AUDIO_MPEG_L1)));
    assertEquals(C.FORMAT_UNSUPPORTED_TYPE, soporte(audio(MimeTypes.AUDIO_MPEG)));
    assertEquals(C.FORMAT_UNSUPPORTED_TYPE, soporte(audio(MimeTypes.AUDIO_AAC)));
    assertEquals(C.FORMAT_UNSUPPORTED_TYPE, soporte(audio(MimeTypes.AUDIO_AC3)));
  }

  @Test
  public void sinLaBibliotecaNoLoUsaYTodoSigueComoAntes() throws Exception {
    KairosAudioMpeg.disponibleParaPruebas(false);
    assertEquals(C.FORMAT_UNSUPPORTED_TYPE, soporte(audio(MimeTypes.AUDIO_MPEG_L2)));
    for (Renderer renderer : audioDeLaFabrica()) {
      assertFalse(renderer instanceof KairosAudioRenderer);
    }
  }

  @Test
  public void vaDespuesDelDeAndroid() {
    KairosAudioMpeg.disponibleParaPruebas(true);
    List<Renderer> audio = audioDeLaFabrica();
    assertTrue(audio.get(0) instanceof MediaCodecAudioRenderer);
    assertTrue(audio.get(audio.size() - 1) instanceof KairosAudioRenderer);
  }
}
