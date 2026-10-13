/// Los ajustes del video mientras se mira (como los de cualquier app de TV):
///
///   - Calidad: "Automática" o una fija (1080p, 720p...), en las señales que
///     traen varias (HLS / DASH). Con internet lento conviene bajarla.
///   - Idioma: el audio, si el video trae más de uno (ej: latino e inglés).
///   - Imagen: Ajustar (se ve entera, con bordes negros si no es de la misma
///     forma que la pantalla), Llenar (sin bordes, recorta un poco) o Estirar.
///   - Fuente: otra dirección de la misma señal, si tiene varias.
///
/// Lo que se elige lo aplica [ControlSenal] (calidad e idioma valen para lo
/// que se está viendo; la imagen queda para todo lo que se vea después).
/// En la TV se eligen con el control (tv/reproductor.dart -> ajustesDeVideoTv);
/// en el celular, con [ajustesDeVideoMovil].
library;

import 'package:flutter/material.dart';
import 'package:video_player/video_player.dart';

import '../tv/escala.dart' show TamanioReal;
import 'control_senal.dart';
import 'estilo.dart';

enum AjusteImagen {
  ajustar('Ajustar', Icons.fit_screen_rounded),
  llenar('Llenar', Icons.crop_rounded),
  estirar('Estirar', Icons.aspect_ratio_rounded);

  const AjusteImagen(this.nombre, this.icono);

  final String nombre;
  final IconData icono;
}

/// Una calidad del video ("1080p · 4,5 Mbps").
class Calidad {
  const Calidad(this.pista);

  final VideoTrack pista;

  int get alto => pista.height ?? 0;

  String get nombre => alto > 0 ? '${alto}p' : (pista.label ?? 'Calidad');

  /// "4,5 Mbps" / "800 kbps" ('' si no se sabe).
  String get detalle {
    final bits = pista.bitrate ?? 0;
    if (bits <= 0) return '';
    if (bits < 1000000) return '${(bits / 1000).round()} kbps';
    return '${(bits / 1000000).toStringAsFixed(1).replaceAll('.', ',')} Mbps';
  }

  /// De mayor a menor y una por alto (la de más bitrate), así no aparecen "720p" repetidas.
  static List<Calidad> ordenadas(Iterable<VideoTrack> pistas) {
    final porAlto = <int, VideoTrack>{};
    for (final pista in pistas) {
      final alto = pista.height ?? 0;
      final otra = porAlto[alto];
      if (otra == null || (pista.bitrate ?? 0) > (otra.bitrate ?? 0)) porAlto[alto] = pista;
    }
    return porAlto.values.map(Calidad.new).toList()..sort((a, b) => b.alto.compareTo(a.alto));
  }
}

/// Un idioma del audio ("Español", "Inglés", o lo que diga el video).
class Idioma {
  const Idioma(this.pista);

  final VideoAudioTrack pista;

  static const _nombres = {
    'es': 'Español',
    'spa': 'Español',
    'es-419': 'Español latino',
    'es-mx': 'Español latino',
    'es-es': 'Español de España',
    'en': 'Inglés',
    'eng': 'Inglés',
    'pt': 'Portugués',
    'por': 'Portugués',
    'fr': 'Francés',
    'fra': 'Francés',
    'fre': 'Francés',
    'it': 'Italiano',
    'ita': 'Italiano',
    'de': 'Alemán',
    'deu': 'Alemán',
    'ger': 'Alemán',
    'ja': 'Japonés',
    'jpn': 'Japonés',
    'ko': 'Coreano',
    'kor': 'Coreano',
    'zh': 'Chino',
    'chi': 'Chino',
    'ru': 'Ruso',
    'rus': 'Ruso',
  };

  String get nombre {
    final codigo = (pista.language ?? '').toLowerCase().replaceAll('_', '-');
    final conocido = _nombres[codigo] ?? _nombres[codigo.split('-').first];
    final etiqueta = (pista.label ?? '').trim();
    if (etiqueta.isNotEmpty && (conocido == null || etiqueta.length > 3)) return etiqueta;
    return conocido ?? (codigo.isEmpty ? 'Audio' : codigo.toUpperCase());
  }

  /// Si dos pistas se llaman igual, se distinguen con "Audio 1", "Audio 2"...
  static List<(Idioma, String)> conNombres(List<VideoAudioTrack> pistas) {
    final idiomas = pistas.map(Idioma.new).toList();
    return [
      for (final (i, idioma) in idiomas.indexed)
        (
          idioma,
          idiomas.where((o) => o.nombre == idioma.nombre).length > 1 ? '${idioma.nombre} (${i + 1})' : idioma.nombre,
        ),
    ];
  }
}

/// El video con el ajuste de imagen elegido (Ajustar / Llenar / Estirar).
class VideoAjustado extends StatelessWidget {
  const VideoAjustado({super.key, required this.video, required this.ajuste});

  final VideoPlayerController video;
  final AjusteImagen ajuste;

  /// El tamaño del video dentro de [caja], según el ajuste.
  static Size medida(Size caja, double proporcion, AjusteImagen ajuste) {
    if (ajuste == AjusteImagen.estirar || caja.isEmpty) return caja;
    final masAncha = caja.width / caja.height > proporcion;
    // Ajustar: entra entero (franjas negras). Llenar: cubre todo (se recortan los bordes).
    final porAlto = ajuste == AjusteImagen.ajustar ? masAncha : !masAncha;
    return porAlto ? Size(caja.height * proporcion, caja.height) : Size(caja.width, caja.width / proporcion);
  }

  @override
  Widget build(BuildContext context) {
    final valor = video.value;
    final proporcion = valor.aspectRatio == 0 ? 16 / 9 : valor.aspectRatio;
    // El tamaño se calcula acá, sin FittedBox ni AspectRatio alrededor del
    // video: en la TV el video lo dibuja Android, que no ve esas
    // transformaciones (ver TamanioReal).
    return LayoutBuilder(
      builder: (context, limites) {
        final tamanio = medida(limites.biggest, proporcion, ajuste);
        final hijo = OverflowBox(
          minWidth: tamanio.width,
          maxWidth: tamanio.width,
          minHeight: tamanio.height,
          maxHeight: tamanio.height,
          child: TamanioReal(child: VideoPlayer(video)),
        );
        return ajuste == AjusteImagen.llenar ? ClipRect(child: hijo) : hijo;
      },
    );
  }
}

/// Lo que ofrecen los ajustes para lo que se está viendo (se pide al reproductor).
class OpcionesDeVideo {
  const OpcionesDeVideo({this.calidades = const [], this.idiomas = const []});

  final List<Calidad> calidades;
  final List<VideoAudioTrack> idiomas;

  static Future<OpcionesDeVideo> de(ControlSenal control) async {
    final resultados = await Future.wait([control.calidades(), control.idiomas()]);
    return OpcionesDeVideo(calidades: resultados[0] as List<Calidad>, idiomas: resultados[1] as List<VideoAudioTrack>);
  }
}

/// Los ajustes en el celular: una hoja de abajo con las cuatro secciones.
Future<void> ajustesDeVideoMovil(BuildContext context, ControlSenal control) async {
  final opciones = await OpcionesDeVideo.de(control);
  if (!context.mounted) return;
  await showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    builder: (context) => ListenableBuilder(
      listenable: control,
      builder: (context, _) {
        Widget titulo(String texto) => Padding(
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 8),
          child: Text(texto, style: Letra.titulo.copyWith(fontSize: 15)),
        );
        Widget chips(List<Widget> hijos) => Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Wrap(spacing: 8, runSpacing: 8, children: hijos),
        );
        ChoiceChip chip(String texto, bool elegido, VoidCallback alTocar) => ChoiceChip(
          label: Text(texto),
          selected: elegido,
          onSelected: (_) => alTocar(),
          selectedColor: Tono.celeste.withValues(alpha: .25),
        );
        return SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.only(bottom: 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (opciones.calidades.length > 1) ...[
                  titulo('Calidad'),
                  chips([
                    chip('Automática', control.calidadElegida == null, () => control.elegirCalidad(null)),
                    for (final calidad in opciones.calidades)
                      chip(
                        [calidad.nombre, if (calidad.detalle.isNotEmpty) calidad.detalle].join(' · '),
                        control.calidadElegida == calidad.pista.id,
                        () => control.elegirCalidad(calidad),
                      ),
                  ]),
                ],
                if (opciones.idiomas.length > 1) ...[
                  titulo('Idioma'),
                  chips([
                    for (final (idioma, nombre) in Idioma.conNombres(opciones.idiomas))
                      chip(
                        nombre,
                        control.idiomaElegido == idioma.pista.id ||
                            (control.idiomaElegido == null && idioma.pista.isSelected),
                        () => control.elegirIdioma(idioma.pista.id),
                      ),
                  ]),
                ],
                titulo('Imagen'),
                chips([
                  for (final ajuste in AjusteImagen.values)
                    chip(ajuste.nombre, ControlSenal.ajuste == ajuste, () => control.cambiarAjuste(ajuste)),
                ]),
                if (control.fuentes.length > 1) ...[
                  titulo('Fuente de la señal'),
                  chips([
                    for (final (i, _) in control.fuentes.indexed)
                      chip('Fuente ${i + 1}', i == control.fuente, () {
                        if (i != control.fuente) control.usarFuente(i);
                        Navigator.pop(context);
                      }),
                  ]),
                ],
              ],
            ),
          ),
        );
      },
    ),
  );
}
