package io.flutter.plugins.videoplayer;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import androidx.media3.common.C;
import androidx.media3.common.PlaybackException;
import androidx.media3.common.Player;
import androidx.media3.datasource.DataSpec;
import androidx.media3.datasource.HttpDataSource;
import androidx.media3.exoplayer.ExoPlaybackException;
import androidx.media3.exoplayer.ExoPlayer;
import java.util.Collections;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.shadows.ShadowLooper;

/**
 * Kairos TV: un canal en vivo que ya se veía y se corta (microcortes de
 * internet, servidores que cortan al que se atrasa) se reconecta solo, como
 * VLC, en vez de darse por fallado.
 */
@RunWith(RobolectricTestRunner.class)
public final class KairosReconexionTest {

  private static final class Escucha extends ExoPlayerEventListener {
    Escucha(ExoPlayer exoPlayer, VideoPlayerCallbacks events) {
      super(exoPlayer, events);
    }

    @Override
    protected void sendInitialized() {}
  }

  private static PlaybackException errorDeConexion(int codigoHttp) {
    HttpDataSource.InvalidResponseCodeException causa =
        new HttpDataSource.InvalidResponseCodeException(
            codigoHttp, null, null, Collections.emptyMap(), new DataSpec(android.net.Uri.EMPTY), new byte[0]);
    return ExoPlaybackException.createForSource(causa, PlaybackException.ERROR_CODE_IO_BAD_HTTP_STATUS);
  }

  /** Un canal en vivo (sin duración) que llegó a verse. */
  private static Escucha enVivoQueSeVio(ExoPlayer exoPlayer, VideoPlayerCallbacks events) {
    when(exoPlayer.isCurrentMediaItemLive()).thenReturn(true);
    when(exoPlayer.getDuration()).thenReturn(C.TIME_UNSET);
    Escucha escucha = new Escucha(exoPlayer, events);
    escucha.onPlaybackStateChanged(Player.STATE_READY);
    escucha.onRenderedFirstFrame();
    return escucha;
  }

  @Test
  public void reconectaHastaSeisVecesPorMinutoEsperandoCadaVezUnPocoMas() {
    KairosReconexion reconexion = new KairosReconexion();
    long ahora = 1_000_000;
    assertEquals(0, reconexion.reconectar(ahora));
    assertEquals(1000, reconexion.reconectar(ahora + 1));
    assertEquals(2000, reconexion.reconectar(ahora + 2));
    assertEquals(3000, reconexion.reconectar(ahora + 3));
    assertEquals(3000, reconexion.reconectar(ahora + 4));
    assertEquals(3000, reconexion.reconectar(ahora + 5));
    assertEquals(-1, reconexion.reconectar(ahora + 6)); // demasiado seguido
    // Pasado el minuto, vuelve a poder
    assertEquals(0, reconexion.reconectar(ahora + 61_000));
    assertEquals(7, reconexion.total());
  }

  @Test
  public void soloLosErroresDeConexionSonPasajeros() {
    assertTrue(KairosReconexion.esPasajero(PlaybackException.ERROR_CODE_IO_NETWORK_CONNECTION_FAILED));
    assertTrue(KairosReconexion.esPasajero(PlaybackException.ERROR_CODE_IO_BAD_HTTP_STATUS));
    assertTrue(KairosReconexion.esPasajero(PlaybackException.ERROR_CODE_PARSING_CONTAINER_MALFORMED));
    assertFalse(KairosReconexion.esPasajero(PlaybackException.ERROR_CODE_DECODER_INIT_FAILED));
    assertFalse(KairosReconexion.esPasajero(PlaybackException.ERROR_CODE_DECODING_FORMAT_UNSUPPORTED));
    assertFalse(KairosReconexion.esPasajero(PlaybackException.ERROR_CODE_IO_CLEARTEXT_NOT_PERMITTED));
  }

  @Test
  public void elErrorDiceSuCausa() {
    String texto = KairosReconexion.describir(errorDeConexion(404));
    assertTrue(texto, texto.startsWith("ERROR_CODE_IO_BAD_HTTP_STATUS: Source error"));
    assertTrue(texto, texto.contains("Response code: 404"));
  }

  @Test
  public void unCanalEnVivoQueSeVioYTerminaSeReconectaSinAvisar() {
    ExoPlayer exoPlayer = mock(ExoPlayer.class);
    VideoPlayerCallbacks events = mock(VideoPlayerCallbacks.class);
    Escucha escucha = enVivoQueSeVio(exoPlayer, events);

    escucha.onPlaybackStateChanged(Player.STATE_ENDED);
    ShadowLooper.idleMainLooper();

    verify(exoPlayer).seekToDefaultPosition();
    verify(events, never()).onPlaybackStateChanged(PlatformPlaybackState.ENDED);
    verify(events).onPlaybackStateChanged(PlatformPlaybackState.BUFFERING);
  }

  @Test
  public void unCorteDeConexionTambienSeReconectaSinAvisar() {
    ExoPlayer exoPlayer = mock(ExoPlayer.class);
    VideoPlayerCallbacks events = mock(VideoPlayerCallbacks.class);
    Escucha escucha = enVivoQueSeVio(exoPlayer, events);

    escucha.onPlayerError(errorDeConexion(503));
    escucha.onPlaybackStateChanged(Player.STATE_IDLE); // mientras espera: "cargando", no "parado"
    ShadowLooper.idleMainLooper();

    verify(exoPlayer).seekToDefaultPosition();
    verify(exoPlayer, org.mockito.Mockito.atLeastOnce()).prepare();
    verify(events, never()).onError(org.mockito.ArgumentMatchers.anyString(), org.mockito.ArgumentMatchers.any(), org.mockito.ArgumentMatchers.any());
    verify(events, never()).onPlaybackStateChanged(PlatformPlaybackState.IDLE);
  }

  @Test
  public void siSeCortaDemasiadoSeguidoAvisaConCuantasVecesSeReconecto() {
    ExoPlayer exoPlayer = mock(ExoPlayer.class);
    VideoPlayerCallbacks events = mock(VideoPlayerCallbacks.class);
    Escucha escucha = enVivoQueSeVio(exoPlayer, events);

    for (int i = 0; i < KairosReconexion.MAXIMO_POR_VENTANA; i++) {
      escucha.onPlaybackStateChanged(Player.STATE_ENDED);
    }
    escucha.onPlaybackStateChanged(Player.STATE_ENDED);

    verify(events)
        .onError(
            "VideoError",
            "Video player had error la transmisión se cortó demasiadas veces seguidas · se reconectó sola 6 veces",
            null);
  }

  @Test
  public void siNuncaSeVioNoSeReconecta() {
    ExoPlayer exoPlayer = mock(ExoPlayer.class);
    VideoPlayerCallbacks events = mock(VideoPlayerCallbacks.class);
    when(exoPlayer.isCurrentMediaItemLive()).thenReturn(true);
    Escucha escucha = new Escucha(exoPlayer, events);
    escucha.onPlaybackStateChanged(Player.STATE_READY);

    escucha.onPlayerError(errorDeConexion(403));

    verify(exoPlayer, never()).seekToDefaultPosition();
    verify(events)
        .onError(
            org.mockito.ArgumentMatchers.eq("VideoError"),
            org.mockito.ArgumentMatchers.contains("Response code: 403"),
            org.mockito.ArgumentMatchers.isNull());
  }

  @Test
  public void unaPeliculaQueTerminaTermina() {
    ExoPlayer exoPlayer = mock(ExoPlayer.class);
    VideoPlayerCallbacks events = mock(VideoPlayerCallbacks.class);
    when(exoPlayer.getDuration()).thenReturn(5_400_000L);
    Escucha escucha = new Escucha(exoPlayer, events);
    escucha.onPlaybackStateChanged(Player.STATE_READY);
    escucha.onRenderedFirstFrame();

    escucha.onPlaybackStateChanged(Player.STATE_ENDED);

    verify(exoPlayer, never()).seekToDefaultPosition();
    verify(events).onPlaybackStateChanged(PlatformPlaybackState.ENDED);
  }
}
