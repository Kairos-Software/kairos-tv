// Kairos TV: no es parte del plugin original (ver paquetes/README.md).

package io.flutter.plugins.videoplayer;

import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.annotation.OptIn;
import androidx.annotation.VisibleForTesting;
import androidx.media3.common.C;
import androidx.media3.common.Format;
import androidx.media3.common.MimeTypes;
import androidx.media3.common.PlaybackException;
import androidx.media3.common.Tracks;
import androidx.media3.common.util.Size;
import androidx.media3.common.util.UnstableApi;
import androidx.media3.exoplayer.DecoderCounters;
import androidx.media3.exoplayer.DecoderReuseEvaluation;
import androidx.media3.exoplayer.ExoPlaybackException;
import androidx.media3.exoplayer.ExoPlayer;
import androidx.media3.exoplayer.analytics.AnalyticsListener;
import androidx.media3.exoplayer.mediacodec.MediaCodecInfo;
import androidx.media3.exoplayer.source.LoadEventInfo;
import androidx.media3.exoplayer.source.MediaLoadData;
import java.io.IOException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Kairos TV: mira por dentro un video mientras arranca, para dos cosas.
 *
 * <ol>
 *   <li><b>Decodificador trabado.</b> Si el video llega pero el decodificador del aparato no
 *       devuelve ninguna imagen en {@link #TRABADO_MS} (o da error a mitad de camino), lo anota en
 *       {@link KairosDecodificadores} y hace arrancar el reproductor de nuevo con otro (el de
 *       Android, por software). Si ya era el de Android o no hay otro, avisa el error a la app:
 *       es el aparato, no la señal (la app pasa enseguida a otra fuente, sin culpar al servidor).
 *   <li><b>Diagnóstico.</b> Qué llegó (video, audio, tamaño), qué decodificador se usó, cuánto
 *       entró y salió, los reintentos de conexión. Va con cada error, y la app lo pide cuando una
 *       señal no arranca a tiempo ({@link #diagnostico(String)}, por el canal
 *       "kairos/reproductor"): así el panel dice si fue el servidor o el aparato.
 * </ol>
 *
 * <p>Deja de mirar cuando aparece la primera imagen (lo que pase después lo ve {@link
 * KairosReconexion}), salvo un error del decodificador, que se atiende siempre.
 */
@OptIn(markerClass = UnstableApi.class)
final class KairosVigia implements AnalyticsListener {

  /** Lo que el vigía le pide al reproductor (ExoPlayerEventListener). */
  interface Acciones {
    /** Volver a arrancar el video: el reproductor elige otro decodificador. */
    void otroDecodificador();

    /** Avisar a la app que este aparato no puede mostrar el video. */
    void fallar(@NonNull String detalle);
  }

  /** Entró video al decodificador y no salió ninguna imagen en este rato: está trabado. */
  static final long TRABADO_MS = 6_000;

  /** Llegó el video y el decodificador no terminó de arrancar en este rato. */
  static final long SIN_ARRANCAR_MS = 10_000;

  /** Lo mínimo de video guardado para juzgar (si no llega video, no es el decodificador). */
  static final long CON_VIDEO_MS = 1_000;

  /** Cuántas veces se cambia de decodificador en un mismo video. */
  static final int MAXIMO_CAMBIOS = 2;

  /** Después de cambiar de decodificador, la app espera un poco más antes de rendirse. */
  static final long CAMBIANDO_MS = 20_000;

  static final long MIRAR_CADA_MS = 1_000;

  /** El comienzo del error que manda el vigía (la app lo reconoce: es el aparato). */
  static final String TRABADO = "KAIROS_DECODIFICADOR_TRABADO";

  enum Accion {
    NADA,
    OTRO_DECODIFICADOR,
    FALLAR
  }

  /** Los últimos videos abiertos, por dirección (la app pregunta por la dirección). */
  private static final int RECORDAR = 8;

  private static final LinkedHashMap<String, KairosVigia> porDireccion =
      new LinkedHashMap<String, KairosVigia>(RECORDAR, 0.75f, true) {
        @Override
        protected boolean removeEldestEntry(Map.Entry<String, KairosVigia> masViejo) {
          return size() > RECORDAR;
        }
      };

  private final ExoPlayer exoPlayer;
  private final Acciones acciones;
  private final Handler handler = new Handler(Looper.getMainLooper());
  private final Runnable mirar = this::mirar;

  @Nullable private Format video;
  @Nullable private Format audio;
  @Nullable private String decoVideo;
  @Nullable private String decoAudio;
  private long formatoDesde = -1;
  private long entroDesde = -1;
  private boolean seVio;
  private int cambios;
  private long ultimoCambio = -1;
  private boolean seRindio;
  private long bytes;
  private int reintentos;
  @Nullable private String ultimoErrorDeCarga;
  private final List<String[]> anotadosAca = new ArrayList<>();

  /** Lo que se vio al cerrarlo (después el reproductor ya no existe). */
  @Nullable private Map<String, Object> alCerrar;

  KairosVigia(@NonNull ExoPlayer exoPlayer, @NonNull Acciones acciones, @Nullable String direccion) {
    this.exoPlayer = exoPlayer;
    this.acciones = acciones;
    exoPlayer.addAnalyticsListener(this);
    if (direccion != null) {
      porDireccion.put(direccion, this);
    }
    handler.postDelayed(mirar, MIRAR_CADA_MS);
  }

  /** El diagnóstico del último video abierto con esa dirección (null si no hay). */
  @Nullable
  static Map<String, Object> diagnostico(@Nullable String direccion) {
    KairosVigia vigia = direccion == null ? null : porDireccion.get(direccion);
    return vigia == null ? null : vigia.diagnostico();
  }

  @VisibleForTesting
  static void olvidarTodos() {
    porDireccion.clear();
  }

  /** Se cierra el reproductor: guarda lo que vio y deja de mirar. */
  void cerrar() {
    if (alCerrar == null) {
      alCerrar = diagnostico();
    }
    handler.removeCallbacks(mirar);
  }

  // ── Lo que avisa ExoPlayer ──

  @Override
  public void onVideoInputFormatChanged(
      @NonNull EventTime eventTime, @NonNull Format format, @Nullable DecoderReuseEvaluation reuse) {
    video = format;
    if (formatoDesde < 0) {
      formatoDesde = SystemClock.elapsedRealtime();
    }
  }

  @Override
  public void onAudioInputFormatChanged(
      @NonNull EventTime eventTime, @NonNull Format format, @Nullable DecoderReuseEvaluation reuse) {
    audio = format;
  }

  @Override
  public void onVideoDecoderInitialized(
      @NonNull EventTime eventTime, @NonNull String decoderName, long initializedTimestampMs, long initializationDurationMs) {
    decoVideo = decoderName;
    entroDesde = -1;
  }

  @Override
  public void onAudioDecoderInitialized(
      @NonNull EventTime eventTime, @NonNull String decoderName, long initializedTimestampMs, long initializationDurationMs) {
    decoAudio = decoderName;
  }

  @Override
  public void onRenderedFirstFrame(@NonNull EventTime eventTime, @NonNull Object output, long renderTimeMs) {
    yaSeVio();
  }

  /** Apareció la imagen: ya no hay nada que vigilar al arrancar. */
  void yaSeVio() {
    seVio = true;
    handler.removeCallbacks(mirar);
  }

  @Override
  public void onLoadCompleted(
      @NonNull EventTime eventTime, @NonNull LoadEventInfo loadEventInfo, @NonNull MediaLoadData mediaLoadData) {
    bytes += Math.max(0, loadEventInfo.bytesLoaded);
  }

  @Override
  public void onLoadCanceled(
      @NonNull EventTime eventTime, @NonNull LoadEventInfo loadEventInfo, @NonNull MediaLoadData mediaLoadData) {
    bytes += Math.max(0, loadEventInfo.bytesLoaded);
  }

  @Override
  public void onLoadError(
      @NonNull EventTime eventTime,
      @NonNull LoadEventInfo loadEventInfo,
      @NonNull MediaLoadData mediaLoadData,
      @NonNull IOException error,
      boolean wasCanceled) {
    bytes += Math.max(0, loadEventInfo.bytesLoaded);
    reintentos++;
    String mensaje = error.getMessage() != null ? error.getMessage() : error.getClass().getSimpleName();
    ultimoErrorDeCarga = mensaje.length() > 60 ? mensaje.substring(0, 60) : mensaje;
  }

  // ── Decidir ──

  /**
   * Qué hacer con lo que se ve ahora. Mientras no haya video guardado no se juzga al
   * decodificador (si no llega video, es la señal). Un decodificador sano devuelve la primera
   * imagen en menos de un segundo: {@link #TRABADO_MS} es largo a propósito.
   */
  @VisibleForTesting
  static Accion decidir(
      boolean seVio,
      boolean haySuperficie,
      boolean hayFormato,
      @Nullable String deco,
      boolean software,
      boolean hayOtro,
      int entraron,
      int salieron,
      long msDesdeQueEntro,
      long msDesdeFormato,
      long guardadoMs,
      int cambios) {
    // Sin superficie el decodificador no arranca a propósito (todavía no hay dónde dibujar)
    if (seVio || !haySuperficie || !hayFormato || guardadoMs < CON_VIDEO_MS) {
      return Accion.NADA;
    }
    if (deco == null) {
      return msDesdeFormato >= SIN_ARRANCAR_MS ? Accion.FALLAR : Accion.NADA;
    }
    if (entraron == 0 || salieron > 0 || msDesdeQueEntro < TRABADO_MS) {
      return Accion.NADA;
    }
    return !software && hayOtro && cambios < MAXIMO_CAMBIOS ? Accion.OTRO_DECODIFICADOR : Accion.FALLAR;
  }

  private void mirar() {
    if (seVio || seRindio || alCerrar != null) {
      return;
    }
    long ahora = SystemClock.elapsedRealtime();
    DecoderCounters contadores = contadoresDeVideo();
    int entraron = contadores == null ? 0 : contadores.queuedInputBufferCount;
    if (entraron > 0 && entroDesde < 0) {
      entroDesde = ahora;
    }
    String tipo = video == null ? null : video.sampleMimeType;
    Accion accion =
        decidir(
            seVio,
            haySuperficie(),
            tipo != null,
            decoVideo,
            tipo != null && decoVideo != null && esDeSoftware(tipo, decoVideo),
            tipo != null && decoVideo != null && KairosDecodificadores.hayOtro(tipo, decoVideo),
            entraron,
            salieron(contadores),
            entroDesde < 0 ? 0 : ahora - entroDesde,
            formatoDesde < 0 ? 0 : ahora - formatoDesde,
            guardadoMs(),
            cambios);
    if (accion == Accion.OTRO_DECODIFICADOR && tipo != null && decoVideo != null) {
      cambiar(tipo, decoVideo);
    } else if (accion == Accion.FALLAR && tipo != null) {
      rendirse(tipo);
      return;
    }
    handler.postDelayed(mirar, MIRAR_CADA_MS);
  }

  /** Anota el decodificador como trabado y hace arrancar el video de nuevo (con otro). */
  private void cambiar(@NonNull String tipo, @NonNull String deco) {
    KairosDecodificadores.anotarTrabado(tipo, deco, System.currentTimeMillis());
    anotadosAca.add(new String[] {tipo, deco});
    cambios++;
    ultimoCambio = SystemClock.elapsedRealtime();
    decoVideo = null;
    entroDesde = -1;
    formatoDesde = -1;
    acciones.otroDecodificador();
  }

  /** No hay con qué mostrarlo en este aparato: se avisa a la app. */
  private void rendirse(@NonNull String tipo) {
    seRindio = true;
    if (decoVideo == null) {
      // No terminó de arrancar: el que lo intentaba es el primero que se le ofreció
      String probable = KairosDecodificadores.ultimoOfrecido(tipo);
      if (probable != null && !esDeSoftware(tipo, probable)) {
        KairosDecodificadores.anotarTrabado(tipo, probable, System.currentTimeMillis());
      }
    } else if (esDeSoftware(tipo, decoVideo)) {
      // El de Android también se trabó con este video: no era culpa de los del fabricante
      for (String[] anotado : anotadosAca) {
        KairosDecodificadores.olvidar(anotado[0], anotado[1]);
      }
    }
    acciones.fallar(TRABADO + ": " + (decoVideo == null ? "el decodificador no arrancó" : "el decodificador no devolvió imagen"));
  }

  /**
   * El decodificador de video dio error a mitad de camino (pasa con algunos del fabricante y
   * ciertos canales). Si hay otro, lo anota y arranca de nuevo con ese: devuelve true. Si no,
   * false (el error sigue su camino).
   */
  boolean otroDecodificadorPorError(@NonNull PlaybackException error) {
    if (!(error instanceof ExoPlaybackException) || error.errorCode != PlaybackException.ERROR_CODE_DECODING_FAILED) {
      return false;
    }
    ExoPlaybackException delReproductor = (ExoPlaybackException) error;
    Format formato = delReproductor.rendererFormat;
    if (delReproductor.type != ExoPlaybackException.TYPE_RENDERER
        || formato == null
        || formato.sampleMimeType == null
        || !MimeTypes.isVideo(formato.sampleMimeType)) {
      return false;
    }
    String tipo = formato.sampleMimeType;
    String deco = decoVideo != null ? decoVideo : KairosDecodificadores.ultimoOfrecido(tipo);
    if (deco == null || cambios >= MAXIMO_CAMBIOS || esDeSoftware(tipo, deco) || !KairosDecodificadores.hayOtro(tipo, deco)) {
      return false;
    }
    seVio = false; // vuelve a mirar hasta que el nuevo muestre imagen
    seRindio = false;
    cambiar(tipo, deco);
    handler.removeCallbacks(mirar);
    handler.postDelayed(mirar, MIRAR_CADA_MS);
    return true;
  }

  // ── Lo que se ve del reproductor (con cuidado: en las pruebas es de mentira) ──

  @Nullable
  private DecoderCounters contadoresDeVideo() {
    DecoderCounters contadores = exoPlayer.getVideoDecoderCounters();
    if (contadores != null) {
      contadores.ensureUpdated();
    }
    return contadores;
  }

  private static int salieron(@Nullable DecoderCounters contadores) {
    return contadores == null
        ? 0
        : contadores.renderedOutputBufferCount + contadores.skippedOutputBufferCount + contadores.droppedBufferCount;
  }

  /** Sin superficie, ExoPlayer da tamaño 0x0 (con una, "desconocido" o el tamaño de verdad). */
  private boolean haySuperficie() {
    Size tamanio = exoPlayer.getSurfaceSize();
    return tamanio != null && !tamanio.equals(Size.ZERO);
  }

  private long guardadoMs() {
    return Math.max(0, exoPlayer.getTotalBufferedDuration());
  }

  private boolean hayPistas() {
    Tracks pistas = exoPlayer.getCurrentTracks();
    return pistas != null && !pistas.isEmpty();
  }

  private boolean hayPistaDeVideo() {
    Tracks pistas = exoPlayer.getCurrentTracks();
    return pistas != null && pistas.containsType(C.TRACK_TYPE_VIDEO);
  }

  /** Si [nombre] es un decodificador por software (los de Android: andan en todos los aparatos). */
  static boolean esDeSoftware(@NonNull String tipo, @NonNull String nombre) {
    for (MediaCodecInfo info : KairosDecodificadores.todos(tipo)) {
      if (info.name.equals(nombre)) {
        return info.softwareOnly;
      }
    }
    String minusculas = nombre.toLowerCase(Locale.ROOT);
    return minusculas.startsWith("omx.google.")
        || minusculas.startsWith("omx.ffmpeg.")
        || minusculas.startsWith("c2.android.")
        || minusculas.startsWith("c2.google.")
        || minusculas.contains(".sw.")
        || minusculas.contains("swvdec");
  }

  // ── El diagnóstico ──

  /** {texto, causa, cambiando}: lo que pide la app (ver ControlSenal). */
  @NonNull
  Map<String, Object> diagnostico() {
    if (alCerrar != null) {
      return alCerrar;
    }
    Map<String, Object> datos = new HashMap<>();
    datos.put("texto", texto());
    datos.put("causa", causa());
    datos.put("cambiando", cambiando());
    return datos;
  }

  /** Acaba de cambiar de decodificador y todavía no hay imagen: la app espera un poco más. */
  private boolean cambiando() {
    return !seVio && !seRindio && ultimoCambio >= 0 && SystemClock.elapsedRealtime() - ultimoCambio < CAMBIANDO_MS;
  }

  /**
   * aparato: el video llega y el aparato no lo muestra. sin_datos: no llegó nada del servidor.
   * sin_video: llegó, pero la señal no trae video. cambiando: ver {@link #cambiando()}.
   */
  @NonNull
  private String causa() {
    if (cambiando()) {
      return "cambiando";
    }
    DecoderCounters contadores = contadoresDeVideo();
    boolean trabado = decoVideo != null && contadores != null && contadores.queuedInputBufferCount > 0 && salieron(contadores) == 0;
    boolean sinArrancar = video != null && decoVideo == null && haySuperficie() && guardadoMs() >= CON_VIDEO_MS;
    if (!seVio && (seRindio || trabado || sinArrancar)) {
      return "aparato";
    }
    if (hayPistas() && !hayPistaDeVideo()) {
      return "sin_video";
    }
    boolean llegoAlgo = video != null || audio != null || hayPistas() || bytes > 0 || guardadoMs() > 0;
    return llegoAlgo ? "desconocida" : "sin_datos";
  }

  /**
   * Corto, para el panel ("Último problema en un aparato"). Ej: "video h264 1920x1080 25 fps ·
   * deco OMX.MTK.VIDEO.DECODER.AVC: entraron 12, salieron 0 · audio mp2 · guardado 9 s".
   */
  @NonNull
  String texto() {
    if (alCerrar != null) {
      Object texto = alCerrar.get("texto");
      return texto == null ? "" : texto.toString();
    }
    List<String> partes = new ArrayList<>();
    if (video != null) {
      StringBuilder deVideo = new StringBuilder("video ").append(nombreCorto(video.sampleMimeType));
      if (video.width > 0 && video.height > 0) {
        deVideo.append(' ').append(video.width).append('x').append(video.height);
      }
      if (video.frameRate > 0) {
        deVideo.append(' ').append(Math.round(video.frameRate)).append(" fps");
      }
      partes.add(deVideo.toString());
    } else if (hayPistas() && !hayPistaDeVideo()) {
      partes.add("sin video");
    }
    DecoderCounters contadores = contadoresDeVideo();
    if (decoVideo != null) {
      partes.add(
          "deco "
              + decoVideo
              + (contadores == null
                  ? ""
                  : ": entraron " + contadores.queuedInputBufferCount + ", salieron " + salieron(contadores)));
    } else if (video != null) {
      partes.add(haySuperficie() ? "el decodificador no arrancó" : "sin superficie");
    }
    if (audio != null) {
      partes.add("audio " + nombreCorto(audio.sampleMimeType) + (decoAudio == null ? "" : " (" + decoAudio + ")"));
    }
    long guardado = guardadoMs();
    if (bytes > 0) {
      partes.add(String.format(Locale.ROOT, "llegaron %.1f MB", bytes / 1_000_000.0).replace('.', ','));
    }
    if (guardado > 0) {
      partes.add("guardado " + (guardado / 1000) + " s");
    }
    if (!seVio && video == null && audio == null && !hayPistas() && bytes == 0 && guardado == 0) {
      partes.add("no llegó nada del servidor");
    }
    if (reintentos > 0) {
      partes.add(reintentos + (reintentos == 1 ? " reintento" : " reintentos") + " (" + ultimoErrorDeCarga + ")");
    }
    if (cambios > 0) {
      partes.add("cambió de decodificador " + cambios + (cambios == 1 ? " vez" : " veces"));
    }
    return String.join(" · ", partes);
  }

  private static final Map<String, String> NOMBRES = new HashMap<>();

  static {
    NOMBRES.put(MimeTypes.VIDEO_H264, "h264");
    NOMBRES.put(MimeTypes.VIDEO_H265, "h265");
    NOMBRES.put(MimeTypes.VIDEO_MPEG2, "mpeg2");
    NOMBRES.put(MimeTypes.VIDEO_MP4V, "mpeg4");
    NOMBRES.put(MimeTypes.VIDEO_VP9, "vp9");
    NOMBRES.put(MimeTypes.VIDEO_AV1, "av1");
    NOMBRES.put(MimeTypes.AUDIO_AAC, "aac");
    NOMBRES.put(MimeTypes.AUDIO_MPEG, "mp3");
    NOMBRES.put(MimeTypes.AUDIO_MPEG_L2, "mp2");
    NOMBRES.put(MimeTypes.AUDIO_AC3, "ac3");
    NOMBRES.put(MimeTypes.AUDIO_E_AC3, "e-ac3");
    NOMBRES.put(MimeTypes.AUDIO_DTS, "dts");
  }

  @NonNull
  private static String nombreCorto(@Nullable String tipo) {
    if (tipo == null) {
      return "?";
    }
    String nombre = NOMBRES.get(tipo);
    return nombre != null ? nombre : tipo.substring(tipo.indexOf('/') + 1);
  }
}
