// Kairos TV: no es parte del plugin original (ver paquetes/README.md).

package io.flutter.plugins.videoplayer;

import android.content.Context;
import android.content.SharedPreferences;
import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.annotation.OptIn;
import androidx.annotation.VisibleForTesting;
import androidx.media3.common.util.UnstableApi;
import androidx.media3.exoplayer.mediacodec.MediaCodecInfo;
import androidx.media3.exoplayer.mediacodec.MediaCodecSelector;
import androidx.media3.exoplayer.mediacodec.MediaCodecUtil;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Kairos TV: los decodificadores de video que se trabaron en ESTE aparato.
 *
 * <p>Cada aparato trae uno o más decodificadores por tipo de video: casi siempre uno del
 * fabricante (por hardware: rápido) y uno de Android (por software: más lento, pero anda en
 * todos). En muchas tablets y TV box baratos el del fabricante recibe el video y no devuelve
 * ninguna imagen (pasa sobre todo con canales de cable y satélite): la señal "no conecta nunca"
 * aunque en un celular ande. Cuando {@link KairosVigia} ve eso, lo anota acá y el reproductor
 * vuelve a arrancar: {@link Selector} ya no lo ofrece y se usa el siguiente (el de Android).
 *
 * <p>Queda anotado {@link #OLVIDAR_DESPUES_MS} (en el aparato, aunque se cierre la app): así el
 * próximo canal arranca directo con el que anda. Después se vuelve a probar el del fabricante:
 * hay televisores cuyo decodificador se traba tras días en espera y vuelve a andar al
 * desenchufarlos (y en una tele el de software pesa más). Si sigue trabado, volver a darse
 * cuenta cuesta unos segundos.
 */
@OptIn(markerClass = UnstableApi.class)
public final class KairosDecodificadores {
  private KairosDecodificadores() {}

  /** Cuánto queda anotado un decodificador trabado: dos días. */
  static final long OLVIDAR_DESPUES_MS = 2L * 24 * 60 * 60 * 1000;

  private static final String ARCHIVO = "kairos_decodificadores";

  /** "tipo|nombre" (ej. "video/avc|OMX.MTK.VIDEO.DECODER.AVC") → hasta cuándo (System.currentTimeMillis). */
  private static final Map<String, Long> trabados = new HashMap<>();

  /** El primero que se le ofreció al reproductor para cada tipo (el que va a intentar abrir). */
  private static final Map<String, String> ultimoOfrecido = new HashMap<>();

  @Nullable private static SharedPreferences guardados;

  /** Lee lo anotado en el aparato. Lo llama el plugin al arrancar (sin esto, solo en memoria). */
  public static synchronized void iniciar(@NonNull Context context) {
    guardados = context.getSharedPreferences(ARCHIVO, Context.MODE_PRIVATE);
    trabados.clear();
    for (Map.Entry<String, ?> anotado : guardados.getAll().entrySet()) {
      if (anotado.getValue() instanceof Long) {
        trabados.put(anotado.getKey(), (Long) anotado.getValue());
      }
    }
  }

  private static String clave(@NonNull String tipo, @NonNull String nombre) {
    return tipo + "|" + nombre;
  }

  /** Anota que [nombre] se trabó con este [tipo] de video (ej. "video/avc"). */
  static synchronized void anotarTrabado(@NonNull String tipo, @NonNull String nombre, long ahora) {
    long hasta = ahora + OLVIDAR_DESPUES_MS;
    trabados.put(clave(tipo, nombre), hasta);
    if (guardados != null) {
      guardados.edit().putLong(clave(tipo, nombre), hasta).apply();
    }
  }

  /**
   * Lo saca de la lista: si el de Android también se trabó con el mismo video, la culpa era del
   * video, no del decodificador del fabricante.
   */
  static synchronized void olvidar(@NonNull String tipo, @NonNull String nombre) {
    trabados.remove(clave(tipo, nombre));
    if (guardados != null) {
      guardados.edit().remove(clave(tipo, nombre)).apply();
    }
  }

  static synchronized boolean estaTrabado(@NonNull String tipo, @NonNull String nombre, long ahora) {
    Long hasta = trabados.get(clave(tipo, nombre));
    if (hasta == null) {
      return false;
    }
    if (hasta <= ahora) {
      olvidar(tipo, nombre);
      return false;
    }
    return true;
  }

  /**
   * [todos] sin los que se trabaron en este aparato. Si se trabaron todos, devuelve [todos] tal
   * cual: con alguno hay que intentar.
   */
  @NonNull
  static List<MediaCodecInfo> sinLosTrabados(@NonNull List<MediaCodecInfo> todos, @NonNull String tipo, long ahora) {
    List<MediaCodecInfo> quedan = new ArrayList<>();
    for (MediaCodecInfo info : todos) {
      if (!estaTrabado(tipo, info.name, ahora)) {
        quedan.add(info);
      }
    }
    return quedan.isEmpty() ? todos : quedan;
  }

  /** En las pruebas, los decodificadores "del aparato" (en la compu no hay). */
  @Nullable private static List<MediaCodecInfo> todosParaPruebas;

  @VisibleForTesting
  static void todosParaPruebas(@Nullable List<MediaCodecInfo> lista) {
    todosParaPruebas = lista;
  }

  /** Todos los decodificadores de este aparato para [tipo], en el orden de Android. */
  @NonNull
  static List<MediaCodecInfo> todos(@NonNull String tipo) {
    if (todosParaPruebas != null) {
      return todosParaPruebas;
    }
    try {
      return MediaCodecUtil.getDecoderInfos(tipo, false, false);
    } catch (MediaCodecUtil.DecoderQueryException e) {
      return new ArrayList<>();
    }
  }

  /**
   * ¿Hay otro decodificador para [tipo], además de [nombre] y de los ya trabados? Si no, cambiar
   * no sirve de nada.
   */
  static boolean hayOtro(@NonNull String tipo, @NonNull String nombre) {
    return hayOtro(todos(tipo), tipo, nombre, System.currentTimeMillis());
  }

  @VisibleForTesting
  static boolean hayOtro(@NonNull List<MediaCodecInfo> todos, @NonNull String tipo, @NonNull String nombre, long ahora) {
    for (MediaCodecInfo info : todos) {
      if (!info.name.equals(nombre) && !estaTrabado(tipo, info.name, ahora)) {
        return true;
      }
    }
    return false;
  }

  /** El que se le ofreció primero al reproductor para [tipo] (null si todavía ninguno). */
  @Nullable
  static synchronized String ultimoOfrecido(@NonNull String tipo) {
    return ultimoOfrecido.get(tipo);
  }

  private static synchronized void ofrecido(@NonNull String tipo, @NonNull List<MediaCodecInfo> lista) {
    if (!lista.isEmpty()) {
      ultimoOfrecido.put(tipo, lista.get(0).name);
    }
  }

  /** Para las pruebas: se olvida de todo (también de lo guardado en el aparato). */
  @VisibleForTesting
  static synchronized void olvidarTodo() {
    trabados.clear();
    ultimoOfrecido.clear();
    todosParaPruebas = null;
    if (guardados != null) {
      guardados.edit().clear().apply();
    }
    guardados = null;
  }

  /** Los de siempre (los de Android, en el orden de Android), menos los trabados en este aparato. */
  static final class Selector implements MediaCodecSelector {
    @NonNull
    @Override
    public List<MediaCodecInfo> getDecoderInfos(
        @NonNull String mimeType, boolean requiresSecureDecoder, boolean requiresTunnelingDecoder)
        throws MediaCodecUtil.DecoderQueryException {
      List<MediaCodecInfo> lista =
          sinLosTrabados(
              MediaCodecSelector.DEFAULT.getDecoderInfos(mimeType, requiresSecureDecoder, requiresTunnelingDecoder),
              mimeType,
              System.currentTimeMillis());
      ofrecido(mimeType, lista);
      return lista;
    }
  }
}
