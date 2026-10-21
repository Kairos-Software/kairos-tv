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
   * Kairos TV: cuánto espera a que el servidor de la señal ATIENDA la conexión. Un servidor que
   * atiende conecta en menos de 2 s; uno saturado a veces no atiende nunca, y esperarlo 25 s
   * (lo que había antes) costaba un minuto por película. Si no atendió, se reintenta enseguida
   * con otra conexión (KairosReintentoRapido): medido con un proveedor Xtream, 3 de cada 7
   * intentos no atendían y el siguiente sí.
   */
  static final int KAIROS_ESPERA_CONEXION_MS = 5_000;

  /**
   * Kairos TV: cuánto espera a que mande el próximo pedazo (leer). De fábrica son 8 s: los
   * servidores IPTV (Xtream) de canales en vivo redirigen a otro y a veces tardan más de 12 s
   * en mandar lo primero, y ExoPlayer se rendía con "Source error" aunque VLC lo viera.
   */
  static final int KAIROS_ESPERA_LECTURA_MS = 30_000;

  /**
   * Kairos TV: una película o capítulo (un archivo: .mp4, .mkv, .avi...). Ya conectado, el
   * primer dato llega en 1 a 3,5 s (medido). Si deja de mandar más que esto, se reconecta
   * (enseguida: KairosReintentoRapido) en vez de quedarse esperando: con 90 s (la app 1.2.34)
   * una película se quedaba cargando un minuto entero.
   */
  static final int KAIROS_ESPERA_LECTURA_ARCHIVO_MS = 20_000;

  /**
   * Kairos TV: cuánto de lo ya visto guarda una película o capítulo. De fábrica, nada: volver 10
   * segundos era pedirlo otra vez al servidor (otra conexión, otra espera). Así, volver dentro de
   * este rato es al instante. Son datos que ya se bajaron (unos 10 a 40 MB de memoria).
   */
  static final int KAIROS_LO_VISTO_MS = 90_000;

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

  /**
   * Kairos TV: cuánto espera a que llegue el próximo pedazo. Un canal en vivo (HLS o un
   * ".ts" directo) 30 s; un archivo (película o capítulo) 90 s (ver
   * {@link #KAIROS_ESPERA_LECTURA_ARCHIVO_MS}).
   */
  @VisibleForTesting
  static int kairosEsperaLectura(@Nullable String url, @NonNull StreamingFormat formato) {
    return kairosEsArchivo(url, formato) ? KAIROS_ESPERA_LECTURA_ARCHIVO_MS : KAIROS_ESPERA_LECTURA_MS;
  }

  /** Kairos TV: si este video es una película o capítulo (ver {@link #kairosEsArchivo(String, StreamingFormat)}). */
  boolean kairosEsArchivo() {
    return kairosEsArchivo(assetUrl, streamingFormat);
  }

  /**
   * Kairos TV: si es un archivo (película o capítulo: .mp4, .mkv, .avi...) y no un canal
   * en vivo (una lista HLS o un ".ts" que llega de corrido).
   */
  @VisibleForTesting
  static boolean kairosEsArchivo(@Nullable String url, @NonNull StreamingFormat formato) {
    if (formato != StreamingFormat.UNKNOWN || url == null) {
      return false;
    }
    String ruta = url.split("[?#]", 2)[0].toLowerCase(Locale.ROOT);
    return !(ruta.endsWith(".ts") || ruta.endsWith(".m3u8") || ruta.endsWith(".m3u"));
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
    DataSource.Factory dataSourceFactory = kairosFabricaDeDatos(context, initialFactory);
    // Kairos TV: si el servidor no atiende, se reintenta enseguida (ver KairosReintentoRapido)
    return new DefaultMediaSourceFactory(context)
        .setDataSourceFactory(dataSourceFactory)
        .setLoadErrorHandlingPolicy(new KairosReintentoRapido(kairosEsArchivo()));
  }

  /**
   * Kairos TV: lo que abre las conexiones de este video (las pruebas lo usan tal cual). Una
   * película pide el archivo varias veces; desde la segunda, directo a donde redirigió el link
   * (ver KairosRedireccionFija). En vivo, siempre el link (así se renueva el permiso).
   */
  @VisibleForTesting
  DataSource.Factory kairosFabricaDeDatos(Context context, DefaultHttpDataSource.Factory initialFactory) {
    unstableUpdateDataSourceFactory(
        initialFactory, httpHeaders, userAgent, kairosEsperaLectura(assetUrl, streamingFormat));
    DataSource.Factory http =
        kairosEsArchivo(assetUrl, streamingFormat)
            ? new KairosRedireccionFija.Factory(initialFactory)
            : initialFactory;
    return new DefaultDataSource.Factory(context, http);
  }

  // TODO: Migrate to stable API, see https://github.com/flutter/flutter/issues/147039.
  @OptIn(markerClass = UnstableApi.class)
  private static void unstableUpdateDataSourceFactory(
      @NonNull DefaultHttpDataSource.Factory factory,
      @NonNull Map<String, String> httpHeaders,
      @Nullable String userAgent,
      int esperaLecturaMs) {
    // Las redirecciones (también de https a http) las sigue el mismo DefaultHttpDataSource,
    // y en cada una vuelve a mandar el User-Agent y las cabeceras.
    factory
        .setUserAgent(userAgent)
        .setAllowCrossProtocolRedirects(true)
        .setConnectTimeoutMs(KAIROS_ESPERA_CONEXION_MS)
        .setReadTimeoutMs(esperaLecturaMs);
    if (!httpHeaders.isEmpty()) {
      factory.setDefaultRequestProperties(httpHeaders);
    }
  }
}
