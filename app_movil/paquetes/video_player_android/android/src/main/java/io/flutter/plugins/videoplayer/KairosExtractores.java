// Kairos TV: los lectores de archivos de siempre, con el de MKV que adelanta sin índice. Ver
// ../../../../../../../README.md.

package io.flutter.plugins.videoplayer;

import android.net.Uri;
import androidx.annotation.NonNull;
import androidx.media3.common.C;
import androidx.media3.common.util.UnstableApi;
import androidx.media3.extractor.DefaultExtractorsFactory;
import androidx.media3.extractor.Extractor;
import androidx.media3.extractor.ExtractorsFactory;
import androidx.media3.extractor.mkv.MatroskaExtractor;
import androidx.media3.extractor.text.DefaultSubtitleParserFactory;
import androidx.media3.extractor.text.SubtitleParser;
import java.util.List;
import java.util.Map;

/**
 * Los de {@link DefaultExtractorsFactory} (lo que usa el reproductor de
 * fábrica), con {@link KairosMkvSinIndice} en lugar del de MKV. Lo arma igual
 * que la de fábrica (los subtítulos, como diga el reproductor).
 */
@UnstableApi
final class KairosExtractores implements ExtractorsFactory {
  private final DefaultExtractorsFactory deFabrica = new DefaultExtractorsFactory();
  // Lo mismo que DefaultExtractorsFactory de entrada
  private SubtitleParser.Factory subtitulos = new DefaultSubtitleParserFactory();
  private boolean transcodificarSubtitulos = true;

  @NonNull
  @Override
  @SuppressWarnings("deprecation") // Lo sigue llamando DefaultMediaSourceFactory
  public ExtractorsFactory experimentalSetTextTrackTranscodingEnabled(boolean enabled) {
    transcodificarSubtitulos = enabled;
    deFabrica.experimentalSetTextTrackTranscodingEnabled(enabled);
    return this;
  }

  @NonNull
  @Override
  public ExtractorsFactory setSubtitleParserFactory(@NonNull SubtitleParser.Factory subtitleParserFactory) {
    subtitulos = subtitleParserFactory;
    deFabrica.setSubtitleParserFactory(subtitleParserFactory);
    return this;
  }

  @NonNull
  @Override
  public ExtractorsFactory experimentalSetCodecsToParseWithinGopSampleDependencies(
      @C.VideoCodecFlags int codecsToParseWithinGopSampleDependencies) {
    deFabrica.experimentalSetCodecsToParseWithinGopSampleDependencies(codecsToParseWithinGopSampleDependencies);
    return this;
  }

  @NonNull
  @Override
  public Extractor[] createExtractors() {
    return conElDeMkv(deFabrica.createExtractors());
  }

  @NonNull
  @Override
  public Extractor[] createExtractors(@NonNull Uri uri, @NonNull Map<String, List<String>> responseHeaders) {
    return conElDeMkv(deFabrica.createExtractors(uri, responseHeaders));
  }

  private Extractor[] conElDeMkv(Extractor[] lectores) {
    for (int i = 0; i < lectores.length; i++) {
      if (lectores[i] instanceof MatroskaExtractor) {
        // Las mismas opciones que le pone DefaultExtractorsFactory
        lectores[i] =
            new KairosMkvSinIndice(
                subtitulos, transcodificarSubtitulos ? 0 : MatroskaExtractor.FLAG_EMIT_RAW_SUBTITLE_DATA);
      }
    }
    return lectores;
  }
}
