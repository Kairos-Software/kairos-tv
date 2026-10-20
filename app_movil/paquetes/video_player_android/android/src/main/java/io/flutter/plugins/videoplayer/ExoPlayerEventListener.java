// Copyright 2013 The Flutter Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package io.flutter.plugins.videoplayer;

import android.os.Handler;
import android.os.Looper;
import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.media3.common.C;
import androidx.media3.common.PlaybackException;
import androidx.media3.common.Player;
import androidx.media3.common.Timeline;
import androidx.media3.common.Tracks;
import androidx.media3.exoplayer.ExoPlayer;

public abstract class ExoPlayerEventListener implements Player.Listener {
  static final long DURATION_UNSET_INITIALIZATION_TIMEOUT_MS = 2000;
  private boolean isInitialized = false;
  private boolean isWaitingForValidDuration = false;
  private final Handler mainHandler = new Handler(Looper.getMainLooper());
  private final Runnable initializationFallback =
      () -> {
        if (!isInitialized && isWaitingForValidDuration) {
          isWaitingForValidDuration = false;
          isInitialized = true;
          sendInitialized();
        }
      };
  protected final ExoPlayer exoPlayer;
  protected final VideoPlayerCallbacks events;

  // Kairos TV: reconectar solo un canal en vivo que se corta (ver KairosReconexion).
  private final KairosReconexion kairosReconexion = new KairosReconexion();
  /** No tiene fin (en vivo): se sabe al estar listo para reproducir. */
  private boolean kairosSinFin = false;
  /** Ya se vio imagen: si nunca arrancó, no se reconecta (la app pasa a otra señal). */
  private boolean kairosSeVio = false;
  /** Esperando para reconectar: la app lo ve como "cargando". */
  private boolean kairosReconectando = false;
  private final Runnable kairosReconectar = this::kairosVolverAConectar;

  private void kairosVolverAConectar() {
    exoPlayer.seekToDefaultPosition();
    exoPlayer.prepare();
  }

  protected enum RotationDegrees {
    ROTATE_0(0),
    ROTATE_90(90),
    ROTATE_180(180),
    ROTATE_270(270);

    private final int degrees;

    RotationDegrees(int degrees) {
      this.degrees = degrees;
    }

    public static RotationDegrees fromDegrees(int degrees) {
      for (RotationDegrees rotationDegrees : RotationDegrees.values()) {
        if (rotationDegrees.degrees == degrees) {
          return rotationDegrees;
        }
      }
      throw new IllegalArgumentException("Invalid rotation degrees specified: " + degrees);
    }

    public int getDegrees() {
      return this.degrees;
    }
  }

  public ExoPlayerEventListener(
      @NonNull ExoPlayer exoPlayer, @NonNull VideoPlayerCallbacks events) {
    this.exoPlayer = exoPlayer;
    this.events = events;
  }

  protected abstract void sendInitialized();

  /** Cancels pending initialization callbacks when the player is disposed. */
  public void dispose() {
    isWaitingForValidDuration = false;
    mainHandler.removeCallbacks(initializationFallback);
    mainHandler.removeCallbacks(kairosReconectar);
  }

  /**
   * Kairos TV: si un canal en vivo que ya se veía se cortó, lo reconecta (después
   * de la espera que diga {@link KairosReconexion}) y devuelve true. Si nunca se
   * vio, no es en vivo o ya se reconectó demasiadas veces seguidas, false.
   */
  private boolean kairosReconectarSiSePuede() {
    if (!kairosSinFin || !kairosSeVio) {
      return false;
    }
    long espera = kairosReconexion.reconectar(android.os.SystemClock.elapsedRealtime());
    if (espera < 0) {
      return false;
    }
    kairosReconectando = true;
    events.onPlaybackStateChanged(PlatformPlaybackState.BUFFERING);
    mainHandler.removeCallbacks(kairosReconectar);
    mainHandler.postDelayed(kairosReconectar, espera);
    return true;
  }

  /** Lo que se le cuenta a la app (y al panel) cuando no se pudo seguir. */
  private String kairosError(@NonNull String detalle) {
    int veces = kairosReconexion.total();
    return "Video player had error "
        + detalle
        + (veces > 0 ? " · se reconectó sola " + veces + (veces == 1 ? " vez" : " veces") : "");
  }

  @Override
  public void onRenderedFirstFrame() {
    kairosSeVio = true;
  }

  private boolean hasValidDuration() {
    return exoPlayer.getDuration() != C.TIME_UNSET;
  }

  private boolean shouldWaitForValidDuration() {
    return !exoPlayer.isCurrentMediaItemLive() && !exoPlayer.isCurrentMediaItemDynamic();
  }

  private void maybeSendInitialized() {
    if (isInitialized) {
      return;
    }

    if (!hasValidDuration() && shouldWaitForValidDuration()) {
      if (!isWaitingForValidDuration) {
        isWaitingForValidDuration = true;
        mainHandler.postDelayed(initializationFallback, DURATION_UNSET_INITIALIZATION_TIMEOUT_MS);
      }
      return;
    }

    isWaitingForValidDuration = false;
    isInitialized = true;
    mainHandler.removeCallbacks(initializationFallback);
    sendInitialized();
  }

  @Override
  public void onPlaybackStateChanged(final int playbackState) {
    PlatformPlaybackState platformState = PlatformPlaybackState.UNKNOWN;
    switch (playbackState) {
      case Player.STATE_BUFFERING:
        platformState = PlatformPlaybackState.BUFFERING;
        break;
      case Player.STATE_READY:
        platformState = PlatformPlaybackState.READY;
        kairosReconectando = false;
        if (exoPlayer.isCurrentMediaItemLive() || !hasValidDuration()) {
          kairosSinFin = true;
        }
        maybeSendInitialized();
        break;
      case Player.STATE_ENDED:
        // Kairos TV: un canal en vivo no termina: si "terminó", el servidor lo
        // cortó o se cortó internet. Se reconecta (si no, la app lo da por cortado).
        if (kairosReconectarSiSePuede()) {
          return;
        }
        if (kairosSinFin && kairosSeVio) {
          events.onError(
              "VideoError", kairosError("la transmisión se cortó demasiadas veces seguidas"), null);
          return;
        }
        platformState = PlatformPlaybackState.ENDED;
        break;
      case Player.STATE_IDLE:
        platformState =
            kairosReconectando ? PlatformPlaybackState.BUFFERING : PlatformPlaybackState.IDLE;
        break;
    }
    events.onPlaybackStateChanged(platformState);
  }

  @Override
  public void onTimelineChanged(@NonNull Timeline timeline, int reason) {
    if (isWaitingForValidDuration && exoPlayer.getPlaybackState() == Player.STATE_READY) {
      maybeSendInitialized();
    }
  }

  @Override
  public void onPlayerError(@NonNull final PlaybackException error) {
    if (error.errorCode == PlaybackException.ERROR_CODE_BEHIND_LIVE_WINDOW) {
      // See
      // https://exoplayer.dev/live-streaming.html#behindlivewindowexception-and-error_code_behind_live_window
      exoPlayer.seekToDefaultPosition();
      exoPlayer.prepare();
    } else if (KairosReconexion.esPasajero(error.errorCode) && kairosReconectarSiSePuede()) {
      // Kairos TV: un corte de conexión en un canal en vivo que se veía: reconecta solo
    } else {
      events.onError("VideoError", kairosError(KairosReconexion.describir(error)), null);
    }
  }

  @Override
  public void onIsPlayingChanged(boolean isPlaying) {
    events.onIsPlayingStateUpdate(isPlaying);
  }

  @Override
  public void onTracksChanged(@NonNull Tracks tracks) {
    // Find the currently selected audio track and notify
    String selectedAudioTrackId = findSelectedAudioTrackId(tracks);
    events.onAudioTrackChanged(selectedAudioTrackId);

    // Find the currently selected video track and notify
    String selectedVideoTrackId = findSelectedVideoTrackId(tracks);
    events.onVideoTrackChanged(selectedVideoTrackId);
  }

  /**
   * Finds the ID of the currently selected audio track.
   *
   * @param tracks The current tracks
   * @return The track ID in format "groupIndex_trackIndex", or null if no audio track is selected
   */
  @Nullable
  private String findSelectedAudioTrackId(@NonNull Tracks tracks) {
    // Keep this ID format in sync with android_video_player.dart::_parseAndroidTrackId.
    int groupIndex = 0;
    for (Tracks.Group group : tracks.getGroups()) {
      if (group.getType() == C.TRACK_TYPE_AUDIO && group.isSelected()) {
        // Find the selected track within this group
        for (int i = 0; i < group.length; i++) {
          if (group.isTrackSelected(i)) {
            return groupIndex + "_" + i;
          }
        }
      }
      groupIndex++;
    }
    return null;
  }

  /**
   * Finds the ID of the currently selected video track.
   *
   * @param tracks The current tracks
   * @return The track ID in format "groupIndex_trackIndex", or null if no video track is selected
   */
  @Nullable
  private String findSelectedVideoTrackId(@NonNull Tracks tracks) {
    // Keep this ID format in sync with android_video_player.dart::_parseAndroidTrackId.
    int groupIndex = 0;
    for (Tracks.Group group : tracks.getGroups()) {
      if (group.getType() == C.TRACK_TYPE_VIDEO && group.isSelected()) {
        // Find the selected track within this group
        for (int i = 0; i < group.length; i++) {
          if (group.isTrackSelected(i)) {
            return groupIndex + "_" + i;
          }
        }
      }
      groupIndex++;
    }
    return null;
  }
}
