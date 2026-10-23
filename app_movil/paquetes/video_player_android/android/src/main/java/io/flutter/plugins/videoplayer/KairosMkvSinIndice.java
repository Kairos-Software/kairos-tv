// Kairos TV: adelantar en una película MKV que no trae índice. Ver ../../../../../../../README.md.

package io.flutter.plugins.videoplayer;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.annotation.VisibleForTesting;
import androidx.media3.common.C;
import androidx.media3.common.ParserException;
import androidx.media3.common.util.UnstableApi;
import androidx.media3.extractor.Extractor;
import androidx.media3.extractor.ExtractorInput;
import androidx.media3.extractor.ExtractorOutput;
import androidx.media3.extractor.PositionHolder;
import androidx.media3.extractor.SeekMap;
import androidx.media3.extractor.SeekPoint;
import androidx.media3.extractor.TrackOutput;
import androidx.media3.extractor.mkv.MatroskaExtractor;
import androidx.media3.extractor.text.SubtitleParser;
import java.io.IOException;

/**
 * Un MKV trae al final un índice (los "Cues") que dice en qué parte del
 * archivo está cada momento de la película. Algunos vienen sin él (los
 * grabados o convertidos al vuelo) y el lector de ExoPlayer los marcaba como
 * "no se puede adelantar": cualquier salto volvía la película a 0. VLC sí
 * adelanta: va buscando dentro del archivo.
 *
 * <p>Acá, igual que VLC: si el MKV no trae índice pero sí su duración y se
 * sabe cuánto pesa, un salto calcula a qué parte del archivo corresponde ese
 * momento (como si la película pesara lo mismo cada minuto), busca desde ahí el
 * próximo bloque de la película (un "Cluster": empieza con una marca fija y
 * dice a qué hora está) y, si quedó lejos de lo pedido, corrige y vuelve a
 * probar ({@link #INTENTOS} veces como mucho, cada una un pedido nuevo al
 * servidor). Cae en un bloque hasta {@link #ANTES_US} antes de lo pedido (lo
 * que falta lo recorre el reproductor sin mostrarlo) o apenas después.
 *
 * <p>Lo demás lo hace el lector de siempre ({@link MatroskaExtractor}): ubicado
 * al principio de un bloque, sigue leyendo desde ahí (así funcionan los saltos
 * cuando hay índice). Lo pone {@link KairosExtractores} en lugar del de siempre.
 */
@UnstableApi
final class KairosMkvSinIndice implements Extractor {

  // Los "elementos" de un MKV que se usan acá (cada uno: su número, su tamaño y su contenido)
  private static final int ID_CLUSTER = 0x1F43B675;
  private static final int ID_TIMECODE = 0xE7;
  private static final int ID_CRC32 = 0xBF;
  private static final int ID_TIMECODE_SCALE = 0x2AD7B1;

  /** Cuántos pedidos al servidor como mucho para encontrar el momento pedido. */
  @VisibleForTesting static final int INTENTOS = 4;

  /** Se acepta un bloque hasta 10 s antes de lo pedido (o hasta {@link #DESPUES_US} después). */
  @VisibleForTesting static final long ANTES_US = 10_000_000;

  @VisibleForTesting static final long DESPUES_US = 2_000_000;

  /** Se apunta un poco antes de lo pedido: así el bloque donde cae suele quedar antes. */
  private static final long MARGEN_US = 3_000_000;

  /** Cuánto se lee buscando un bloque como mucho (en una película son cada pocos segundos). */
  private static final int BUSCAR_COMO_MUCHO = 16 * 1024 * 1024;

  /** Lo que ocupa como mucho el principio de un bloque: su marca, su tamaño, el control de errores y la hora. */
  private static final int PRINCIPIO_DE_BLOQUE = 4 + 8 + 6 + 1 + 8 + 8;

  private final Lector lector;

  private long largo = C.LENGTH_UNSET;
  private long escalaNs = 1_000_000; // la de casi todos (milisegundos); la dice el archivo
  private long primerBloque = C.INDEX_UNSET;
  private long duracionUs = C.TIME_UNSET;

  // La búsqueda en curso (después de un salto): lo pedido y entre qué lugares del archivo está
  private long buscadoUs = C.TIME_UNSET;
  private int intentos;
  private long antesPosicion;
  private long antesUs;
  private long despuesPosicion;
  private long despuesUs;

  KairosMkvSinIndice(@NonNull SubtitleParser.Factory subtitulos, @MatroskaExtractor.Flags int opciones) {
    lector = new Lector(subtitulos, opciones);
  }

  @Override
  public boolean sniff(@NonNull ExtractorInput input) throws IOException {
    return lector.sniff(input);
  }

  @Override
  public void init(@NonNull ExtractorOutput output) {
    lector.init(new Salida(output));
  }

  @Override
  public int read(@NonNull ExtractorInput input, @NonNull PositionHolder seekPosition) throws IOException {
    if (input.getLength() != C.LENGTH_UNSET) {
      largo = input.getLength();
    }
    if (buscadoUs != C.TIME_UNSET) {
      int resultado = buscar(input, seekPosition);
      if (resultado != RESULT_CONTINUE) {
        return resultado;
      }
    }
    return lector.read(input, seekPosition);
  }

  @Override
  public void seek(long position, long timeUs) {
    lector.seek(position, timeUs);
    // Con el mapa aproximado, un salto (no al principio) cae en cualquier parte del archivo: hay que buscar
    if (duracionUs != C.TIME_UNSET && position > 0) {
      buscadoUs = timeUs;
      intentos = 0;
      antesPosicion = primerBloque;
      antesUs = 0;
      despuesPosicion = largo;
      despuesUs = duracionUs;
    } else {
      buscadoUs = C.TIME_UNSET;
    }
  }

  @Override
  public void release() {
    lector.release();
  }

  /**
   * Busca desde acá el próximo bloque. Si está cerca de lo pedido, se ubica en
   * él y sigue el lector de siempre ({@link #RESULT_CONTINUE}); si no, pide
   * seguir desde otro lugar del archivo ({@link #RESULT_SEEK}).
   */
  private int buscar(ExtractorInput input, PositionHolder seekPosition) throws IOException {
    long[] bloque = proximoBloque(input);
    if (bloque == null) {
      // Ni un bloque (no debería pasar): desde el principio, como antes de este arreglo
      buscadoUs = C.TIME_UNSET;
      lector.seek(0, 0);
      seekPosition.position = 0;
      return RESULT_SEEK;
    }
    long posicion = bloque[0];
    long horaUs = bloque[1] * escalaNs / 1000;
    intentos++;
    boolean cerca = horaUs >= buscadoUs - ANTES_US && horaUs <= buscadoUs + DESPUES_US;
    if (!cerca && intentos < INTENTOS) {
      if (horaUs < buscadoUs) {
        antesPosicion = posicion;
        antesUs = horaUs;
      } else {
        despuesPosicion = posicion;
        despuesUs = horaUs;
      }
      long otra = estimar(buscadoUs, antesPosicion, antesUs, despuesPosicion, despuesUs);
      if (otra != input.getPosition()) {
        seekPosition.position = otra;
        return RESULT_SEEK;
      }
    }
    // Acá: el lector de siempre sigue desde el principio de este bloque
    input.skipFully((int) (posicion - input.getPosition()));
    buscadoUs = C.TIME_UNSET;
    return RESULT_CONTINUE;
  }

  /**
   * En qué lugar del archivo estaría ese momento, sabiendo dónde están dos
   * momentos (antes y después): como si entre ellos la película pesara lo mismo
   * cada segundo. Apunta {@link #MARGEN_US} antes.
   */
  @VisibleForTesting
  static long estimar(long buscadoUs, long antesPosicion, long antesUs, long despuesPosicion, long despuesUs) {
    if (despuesUs <= antesUs || despuesPosicion <= antesPosicion) {
      return antesPosicion;
    }
    long apuntadoUs = Math.max(antesUs, buscadoUs - MARGEN_US);
    double proporcion = (double) (apuntadoUs - antesUs) / (despuesUs - antesUs);
    long posicion = antesPosicion + (long) (proporcion * (despuesPosicion - antesPosicion));
    return Math.max(antesPosicion, Math.min(posicion, despuesPosicion - 1));
  }

  /**
   * El próximo bloque desde donde está la lectura: {lugar en el archivo, hora
   * (en las unidades del archivo)}, o null si no hay. Deja la lectura en un lugar
   * anterior a ese bloque (lo que ya se revisó se descarta para no guardarlo).
   */
  @Nullable
  private static long[] proximoBloque(ExtractorInput input) throws IOException {
    byte[] ventana = new byte[64 * 1024];
    int llenos = 0;
    long base = input.getPosition();
    long inicio = base;
    boolean seTermino = false;
    input.resetPeekPosition();
    while (true) {
      if (!seTermino) {
        int leidos = input.peek(ventana, llenos, ventana.length - llenos);
        if (leidos == C.RESULT_END_OF_INPUT) {
          seTermino = true;
        } else {
          llenos += leidos;
        }
      }
      // Sin saber si la hora entra entera, no se mira: queda para la vuelta siguiente (salvo al final)
      int hasta = seTermino ? llenos : llenos - PRINCIPIO_DE_BLOQUE;
      for (int i = 0; i < hasta; i++) {
        long hora = horaDelBloque(ventana, i, llenos);
        if (hora >= 0) {
          input.resetPeekPosition();
          return new long[] {base + i, hora};
        }
      }
      if (seTermino || base - inicio > BUSCAR_COMO_MUCHO) {
        input.resetPeekPosition();
        return null;
      }
      if (hasta > 0) {
        // Se descarta lo revisado y se guarda la cola (un bloque puede empezar ahí)
        input.resetPeekPosition();
        input.skipFully(hasta);
        System.arraycopy(ventana, hasta, ventana, 0, llenos - hasta);
        llenos -= hasta;
        base += hasta;
        input.advancePeekPosition(llenos);
      }
    }
  }

  /**
   * Si en datos[i] empieza un bloque, su hora (lo que dice su "Timecode", el
   * primer elemento de todo bloque, a veces después de un control de errores
   * "CRC-32", como los escribe FFmpeg); si no, -1. La marca de 4 bytes, un tamaño
   * válido y enseguida la hora: que eso aparezca por casualidad dentro de la
   * imagen o el sonido es casi imposible.
   */
  @VisibleForTesting
  static long horaDelBloque(byte[] datos, int i, int llenos) {
    if (i + 6 > llenos
        || (datos[i] & 0xFF) != 0x1F
        || (datos[i + 1] & 0xFF) != 0x43
        || (datos[i + 2] & 0xFF) != 0xB6
        || (datos[i + 3] & 0xFF) != 0x75) {
      return -1;
    }
    int j = i + 4;
    int largoDelTamanio = largoDeNumero(datos[j]);
    if (largoDelTamanio == 0) {
      return -1;
    }
    j += largoDelTamanio;
    // El control de errores: su marca, su tamaño (siempre 4) y 4 bytes
    if (j + 2 <= llenos && (datos[j] & 0xFF) == ID_CRC32 && (datos[j + 1] & 0xFF) == 0x84) {
      j += 6;
    }
    if (j + 2 > llenos || (datos[j] & 0xFF) != ID_TIMECODE) {
      return -1;
    }
    j++;
    int largoDelTamanioDeLaHora = largoDeNumero(datos[j]);
    if (largoDelTamanioDeLaHora == 0 || j + largoDelTamanioDeLaHora > llenos) {
      return -1;
    }
    long bytesDeLaHora = valorDeNumero(datos, j, largoDelTamanioDeLaHora);
    j += largoDelTamanioDeLaHora;
    if (bytesDeLaHora < 1 || bytesDeLaHora > 8 || j + bytesDeLaHora > llenos) {
      return -1;
    }
    long hora = 0;
    for (int k = 0; k < bytesDeLaHora; k++) {
      hora = (hora << 8) | (datos[j + k] & 0xFF);
    }
    return hora;
  }

  /** Los números de tamaño de un MKV ocupan de 1 a 8 bytes: lo dice el primero (0 = no es uno). */
  private static int largoDeNumero(byte primero) {
    for (int bytes = 1; bytes <= 8; bytes++) {
      if ((primero & (0x100 >> bytes)) != 0) {
        return bytes;
      }
    }
    return 0;
  }

  private static long valorDeNumero(byte[] datos, int desde, int bytes) {
    long valor = datos[desde] & (0xFF >> bytes);
    for (int k = 1; k < bytes; k++) {
      valor = (valor << 8) | (datos[desde + k] & 0xFF);
    }
    return valor;
  }

  /** El lector de siempre, avisando dónde empieza la película y en qué unidades dice las horas. */
  private final class Lector extends MatroskaExtractor {
    Lector(SubtitleParser.Factory subtitulos, @Flags int opciones) {
      super(subtitulos, opciones);
    }

    @Override
    protected void startMasterElement(int id, long contentPosition, long contentSize) throws ParserException {
      if (id == ID_CLUSTER && primerBloque == C.INDEX_UNSET) {
        primerBloque = contentPosition;
      }
      super.startMasterElement(id, contentPosition, contentSize);
    }

    @Override
    protected void integerElement(int id, long value) throws ParserException {
      if (id == ID_TIMECODE_SCALE) {
        escalaNs = value;
      }
      super.integerElement(id, value);
    }
  }

  /** Lo que el lector manda al reproductor: igual, salvo el "no se puede adelantar" de un MKV sin índice. */
  private final class Salida implements ExtractorOutput {
    private final ExtractorOutput destino;

    Salida(ExtractorOutput destino) {
      this.destino = destino;
    }

    @NonNull
    @Override
    public TrackOutput track(int id, int type) {
      return destino.track(id, type);
    }

    @Override
    public void endTracks() {
      destino.endTracks();
    }

    @Override
    public void seekMap(@NonNull SeekMap seekMap) {
      if (!seekMap.isSeekable()
          && seekMap.getDurationUs() != C.TIME_UNSET
          && largo != C.LENGTH_UNSET
          && primerBloque != C.INDEX_UNSET
          && primerBloque < largo) {
        duracionUs = seekMap.getDurationUs();
        destino.seekMap(new MapaAproximado(duracionUs, primerBloque, largo));
      } else {
        destino.seekMap(seekMap);
      }
    }
  }

  /** "Sí se puede adelantar": el lugar de cada momento, aproximado (lo ajusta {@link #buscar}). */
  @VisibleForTesting
  static final class MapaAproximado implements SeekMap {
    private final long duracionUs;
    private final long primerBloque;
    private final long largo;

    MapaAproximado(long duracionUs, long primerBloque, long largo) {
      this.duracionUs = duracionUs;
      this.primerBloque = primerBloque;
      this.largo = largo;
    }

    @Override
    public boolean isSeekable() {
      return true;
    }

    @Override
    public long getDurationUs() {
      return duracionUs;
    }

    @NonNull
    @Override
    public SeekPoints getSeekPoints(long timeUs) {
      if (timeUs < ANTES_US) {
        // Cerca del principio: desde el comienzo del archivo, como antes (son pocos segundos)
        return new SeekPoints(new SeekPoint(0, 0));
      }
      return new SeekPoints(new SeekPoint(timeUs, estimar(timeUs, primerBloque, 0, largo, duracionUs)));
    }
  }
}
