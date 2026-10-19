// Copyright 2013 The Flutter Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package io.flutter.plugins.videoplayer;

import android.content.Context;
import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.annotation.OptIn;
import androidx.annotation.VisibleForTesting;
import androidx.media3.common.MediaItem;
import androidx.media3.common.MimeTypes;
import androidx.media3.common.util.UnstableApi;
import androidx.media3.datasource.DataSource;
import androidx.media3.datasource.DefaultDataSource;
import androidx.media3.datasource.DefaultHttpDataSource;
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory;
import androidx.media3.exoplayer.source.MediaSource;
import java.util.Locale;
import java.util.Map;

final class HttpVideoAsset extends VideoAsset {
  /** Kairos TV: cuánto detrás del vivo se mira un canal (ver getMediaItem). */
  static final long KAIROS_ATRAS_DEL_VIVO_MS = 30_000;

  /**
   * Kairos TV: cuánto espera a que el servidor de la señal conteste (conectar) y
   * a que mande el próximo pedazo (leer). De fábrica son 8 s: los servidores IPTV
   * (Xtream) redirigen a otro y a veces tardan más de 12 s en mandar lo primero, y
   * ExoPlayer se rendía con "Source error" aunque VLC (que espera más) lo viera.
   */
  static final int KAIROS_ESPERA_CONEXION_MS = 25_000;

  static final int KAIROS_ESPERA_LECTURA_MS = 30_000;

  @NonNull private final StreamingFormat streamingFormat;
  @NonNull private final Map<String, String> httpHeaders;
  @Nullable private final String userAgent;

  HttpVideoAsset(
      @Nullable String assetUrl,
      @NonNull StreamingFormat streamingFormat,
      @NonNull Map<String, String> httpHeaders,
      @Nullable String userAgent) {
    super(assetUrl);
    this.streamingFormat = streamingFormat;
    this.httpHeaders = httpHeaders;
    this.userAgent = userAgent;
  }

  @NonNull
  @Override
  public MediaItem getMediaItem() {
    MediaItem.Builder builder = new MediaItem.Builder().setUri(assetUrl);
    String mimeType = null;
    switch (streamingFormat) {
      case SMOOTH:
        mimeType = MimeTypes.APPLICATION_SS;
        break;
      case DYNAMIC_ADAPTIVE:
        mimeType = MimeTypes.APPLICATION_MPD;
        break;
      case HTTP_LIVE:
        mimeType = MimeTypes.APPLICATION_M3U8;
        break;
    }
    if (mimeType == null) {
      mimeType = kairosMimeDirecto(assetUrl);
    }
    if (mimeType != null) {
      builder.setMimeType(mimeType);
    }
    // Kairos TV: en vivo (HLS) se mira unos 30 segundos detrás del vivo, en vez
    // de los ~3 pedacitos de fábrica. Esos 30 s ya están en el servidor, así que
    // se bajan enseguida y quedan guardados: un corte de la señal de hasta ese
    // tiempo no se nota. Si la lista del canal guarda menos, ExoPlayer usa lo
    // que haya. No cambia nada en películas ni en videos directos. Ver paquetes/README.md.
    builder.setLiveConfiguration(
        new MediaItem.LiveConfiguration.Builder().setTargetOffsetMs(KAIROS_ATRAS_DEL_VIVO_MS).build());
    return builder.build();
  }

  /**
   * Kairos TV: un video directo que termina en ".ts" (un canal de una lista Xtream:
   * ".../live/usuario/clave/123.ts") es MPEG-TS que llega de corrido, no una lista
   * HLS: se lo dice a ExoPlayer. Lo demás, sin pista (lo averigua ExoPlayer).
   */
  @VisibleForTesting
  @Nullable
  static String kairosMimeDirecto(@Nullable String url) {
    if (url == null) {
      return null;
    }
    String ruta = url.split("[?#]", 2)[0].toLowerCase(Locale.ROOT);
    return ruta.endsWith(".ts") ? MimeTypes.VIDEO_MP2T : null;
  }

  @NonNull
  @Override
  public MediaSource.Factory getMediaSourceFactory(@NonNull Context context) {
    return getMediaSourceFactory(context, new DefaultHttpDataSource.Factory());
  }

  /**
   * Returns a configured media source factory, starting at the provided factory.
   *
   * <p>This method is provided for ease of testing without making real HTTP calls.
   *
   * @param context application context.
   * @param initialFactory initial factory, to be configured.
   * @return configured factory, or {@code null} if not needed for this asset type.
   */
  @VisibleForTesting
  MediaSource.Factory getMediaSourceFactory(
      Context context, DefaultHttpDataSource.Factory initialFactory) {
    unstableUpdateDataSourceFactory(initialFactory, httpHeaders, userAgent);
    DataSource.Factory dataSourceFactory = new DefaultDataSource.Factory(context, initialFactory);
    return new DefaultMediaSourceFactory(context).setDataSourceFactory(dataSourceFactory);
  }

  // TODO: Migrate to stable API, see https://github.com/flutter/flutter/issues/147039.
  @OptIn(markerClass = UnstableApi.class)
  private static void unstableUpdateDataSourceFactory(
      @NonNull DefaultHttpDataSource.Factory factory,
      @NonNull Map<String, String> httpHeaders,
      @Nullable String userAgent) {
    // Las redirecciones (también de https a http) las sigue el mismo DefaultHttpDataSource,
    // y en cada una vuelve a mandar el User-Agent y las cabeceras.
    factory
        .setUserAgent(userAgent)
        .setAllowCrossProtocolRedirects(true)
        .setConnectTimeoutMs(KAIROS_ESPERA_CONEXION_MS)
        .setReadTimeoutMs(KAIROS_ESPERA_LECTURA_MS);
    if (!httpHeaders.isEmpty()) {
      factory.setDefaultRequestProperties(httpHeaders);
    }
  }
}
