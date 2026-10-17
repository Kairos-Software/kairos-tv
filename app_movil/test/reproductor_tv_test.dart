// Los reproductores de la TV manejados con el control remoto. El video es "de
// mentira" (_VideoDeMentira): dice que arrancó y no muestra nada, así se
// prueba el manejo sin un reproductor de verdad.
import 'dart:async';

import 'package:app_movil/api/modelos.dart';
import 'package:app_movil/movil/datos.dart';
import 'package:app_movil/sesion.dart';
import 'package:app_movil/movil/recordatorios.dart';
import 'package:app_movil/tv/mi_agenda.dart';
import 'package:app_movil/tv/reproductor.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:video_player_platform_interface/video_player_platform_interface.dart';

class _VideoDeMentira extends VideoPlayerPlatform {
  var _proximo = 0;
  final _eventos = <int, StreamController<VideoEvent>>{};

  @override
  Future<void> init() async {}

  @override
  Future<int?> createWithOptions(VideoCreationOptions options) async {
    final id = _proximo++;
    _eventos[id] = StreamController<VideoEvent>();
    return id;
  }

  @override
  Stream<VideoEvent> videoEventsFor(int playerId) {
    final eventos = _eventos[playerId]!;
    scheduleMicrotask(
      () => eventos.add(
        VideoEvent(
          eventType: VideoEventType.initialized,
          duration: const Duration(minutes: 90),
          size: const Size(1920, 1080),
        ),
      ),
    );
    return eventos.stream;
  }

  @override
  Future<void> dispose(int playerId) async => _eventos.remove(playerId)?.close();

  @override
  Future<void> play(int playerId) async {}

  @override
  Future<void> pause(int playerId) async {}

  @override
  Future<void> setLooping(int playerId, bool looping) async {}

  @override
  Future<void> setVolume(int playerId, double volume) async {}

  @override
  Future<void> setPlaybackSpeed(int playerId, double speed) async {}

  @override
  Future<void> seekTo(int playerId, Duration position) async {}

  @override
  Future<Duration> getPosition(int playerId) async => Duration.zero;

  @override
  Future<void> setMixWithOthers(bool mixWithOthers) async {}

  @override
  Widget buildViewWithOptions(VideoViewOptions options) => const SizedBox.expand();

  // Una señal con dos calidades y dos audios
  String? calidadElegida;

  @override
  bool isVideoTrackSupportAvailable() => true;

  @override
  Future<List<VideoTrack>> getVideoTracks(int playerId) async => const [
    VideoTrack(id: '0_0', isSelected: false, height: 720, bitrate: 2500000),
    VideoTrack(id: '0_1', isSelected: true, height: 1080, bitrate: 5000000),
  ];

  @override
  Future<void> selectVideoTrack(int playerId, VideoTrack? track) async => calidadElegida = track?.id ?? 'auto';

  @override
  bool isAudioTrackSupportAvailable() => true;

  @override
  Future<List<VideoAudioTrack>> getAudioTracks(int playerId) async => const [
    VideoAudioTrack(id: 'a0', label: '', isSelected: true, language: 'es-419'),
    VideoAudioTrack(id: 'a1', label: '', isSelected: false, language: 'en'),
  ];
}

Canal _canal(int id, String nombre) => Canal({
  'id': id,
  'nombre': nombre,
  'fuentes': [
    {'id': id, 'url': 'https://x/$id.m3u8', 'tipo': 'hls', 'codec': 'h264'},
  ],
}, categoria: 'Noticias');

final _canales = [_canal(1, 'Canal 26'), _canal(2, 'Telemax'), _canal(3, 'A24')];

late _VideoDeMentira _video;

Future<void> _abrir(WidgetTester tester, Widget reproductor) async {
  tester.view.physicalSize = const Size(1920, 1080);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  VideoPlayerPlatform.instance = _video = _VideoDeMentira();
  final catalogo = Catalogo(Sesion().api)
    ..categoriasEnVivo = [
      CategoriaCanales({
        'nombre': 'Noticias',
        'canales': [
          for (final c in _canales) {'id': c.id, 'nombre': c.nombre, 'fuentes': <dynamic>[]},
        ],
      }),
    ]
    ..cargado = true;
  await tester.pumpWidget(
    SesionScope(
      sesion: Sesion(),
      child: DatosScope(
        catalogo: catalogo,
        biblioteca: Biblioteca(),
        child: MaterialApp(
          home: Builder(
            builder: (context) => Center(
              child: TextButton(
                onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => reproductor)),
                child: const Text('abrir'),
              ),
            ),
          ),
        ),
      ),
    ),
  );
  await tester.tap(find.text('abrir'));
  await _pasar(tester);
}

String? _enfocado() => FocusManager.instance.primaryFocus?.debugLabel;

Future<void> _tecla(WidgetTester tester, LogicalKeyboardKey tecla) async {
  await tester.sendKeyEvent(tecla);
  await _pasar(tester);
}

/// "Atrás" del control.
Future<void> _atras(WidgetTester tester) async {
  await tester.binding.handlePopRoute();
  await _pasar(tester);
}

void main() {
  testWidgets('en vivo: el cartel solo informa y Atrás sale directo', (tester) async {
    await _abrir(tester, ReproductorVivoTv(canal: _canales[0], lista: _canales));
    expect(find.text('guía'), findsOneWidget); // el cartel con la ayuda ([OK] guía)
    expect(_enfocado(), 'reproductor'); // no le robó el foco a nadie
    await _atras(tester);
    expect(find.text('abrir'), findsOneWidget); // salió con un solo "Atrás"
  });

  testWidgets('en vivo: OK abre la guía en el canal actual, Abajo + OK cambia de canal', (tester) async {
    await _abrir(tester, ReproductorVivoTv(canal: _canales[0], lista: _canales));
    await _tecla(tester, LogicalKeyboardKey.select);
    expect(find.text('GUÍA DE CANALES'), findsOneWidget);
    expect(_enfocado(), 'guía: canal actual');
    await _tecla(tester, LogicalKeyboardKey.arrowDown);
    await _tecla(tester, LogicalKeyboardKey.select); // elige Telemax
    expect(find.text('GUÍA DE CANALES'), findsNothing);
    expect(find.text('Telemax'), findsOneWidget); // el cartel del canal nuevo
    expect(_enfocado(), 'reproductor');
  });

  testWidgets('en vivo: Atrás cierra la guía; las opciones toman el foco y se cierran solas', (tester) async {
    await _abrir(tester, ReproductorVivoTv(canal: _canales[0], lista: _canales));
    await _tecla(tester, LogicalKeyboardKey.select);
    await _atras(tester);
    expect(find.text('GUÍA DE CANALES'), findsNothing);
    expect(find.text('abrir'), findsNothing); // no salió: solo cerró la guía

    await _tecla(tester, LogicalKeyboardKey.arrowRight);
    expect(_enfocado(), 'opciones: guía'); // el foco ya está en el primer botón
    await tester.pump(const Duration(seconds: 6));
    await _pasar(tester);
    expect(_enfocado(), 'reproductor'); // se cerraron solas

    await _tecla(tester, LogicalKeyboardKey.arrowDown); // zapping: Abajo, el de abajo en la guía
    expect(find.text('Telemax'), findsOneWidget);
    await _tecla(tester, LogicalKeyboardKey.arrowUp); // Arriba, vuelve al de arriba
    expect(find.text('Canal 26'), findsOneWidget);
  });

  testWidgets('en vivo: las opciones abren los ajustes (calidad, idioma, imagen) y cambian de canal', (tester) async {
    await _abrir(tester, ReproductorVivoTv(canal: _canales[0], lista: _canales));
    await _tecla(tester, LogicalKeyboardKey.arrowRight); // opciones, en "Guía"
    for (final esperado in ['Canal anterior', 'Canal siguiente', 'Agregar a favoritos', 'Recordarme', 'Ajustes']) {
      await _tecla(tester, LogicalKeyboardKey.arrowRight);
      expect(_enfocado(), esperado); // Derecha recorre la barra (no salta al video)
    }
    await _tecla(tester, LogicalKeyboardKey.select);
    expect(find.text('1080p · 5,0 Mbps'), findsOneWidget); // de mayor a menor
    expect(find.text('720p · 2,5 Mbps'), findsOneWidget);
    expect(find.text('Español latino'), findsOneWidget);
    expect(find.text('Inglés'), findsOneWidget);
    expect(find.text('Llenar'), findsOneWidget);

    // El foco arranca en la calidad puesta (Automática): Derecha + OK elige 1080p
    expect(_enfocado(), 'Automática');
    await _tecla(tester, LogicalKeyboardKey.arrowRight);
    await _tecla(tester, LogicalKeyboardKey.select);
    expect(_video.calidadElegida, '0_1');
    await _atras(tester);
    expect(find.text('1080p · 5,0 Mbps'), findsNothing); // se cerró
    expect(find.text('abrir'), findsNothing); // y sigue en el reproductor

    // Canal siguiente desde la barra
    await _tecla(tester, LogicalKeyboardKey.arrowRight);
    await _tecla(tester, LogicalKeyboardKey.arrowRight);
    await _tecla(tester, LogicalKeyboardKey.arrowRight);
    await _tecla(tester, LogicalKeyboardKey.select);
    expect(find.text('Telemax'), findsWidgets);
  });

  testWidgets('en vivo: "Recordarme" desde las opciones anota ese canal en Mi agenda', (tester) async {
    SharedPreferences.setMockInitialValues({});
    Recordatorios.poner([]);
    await _abrir(tester, ReproductorVivoTv(canal: _canales[0], lista: _canales));
    await _tecla(tester, LogicalKeyboardKey.arrowRight); // opciones, en "Guía"
    for (var i = 0; i < 4; i++) {
      await _tecla(tester, LogicalKeyboardKey.arrowRight);
    }
    expect(_enfocado(), 'Recordarme');
    await _tecla(tester, LogicalKeyboardKey.select);
    expect(find.byType(DialogoRecordarmeTv), findsOneWidget);
    await tester.tap(find.text('Guardar'));
    await _pasar(tester);
    await tester.pump(const Duration(seconds: 3)); // el aviso "Anotado: ..." se va solo
    expect(find.byType(DialogoRecordarmeTv), findsNothing);
    expect(Recordatorios.tiene(_canales[0]), isTrue);
    Recordatorios.poner([]);
  });

  testWidgets('película: OK pausa y deja el foco en Pausa; Atrás esconde la barra y después sale', (tester) async {
    await _abrir(tester, ReproductorVodTv(canal: _canal(9, 'Matrix (1999)')));
    expect(_enfocado(), 'reproductor');
    await _tecla(tester, LogicalKeyboardKey.select);
    expect(_enfocado(), 'pausa');
    await _atras(tester);
    expect(_enfocado(), 'reproductor'); // escondió la barra
    expect(find.text('abrir'), findsNothing);

    await _tecla(tester, LogicalKeyboardKey.arrowRight); // adelanta: la barra queda en la línea de tiempo
    expect(_enfocado(), 'línea de tiempo');
    await _atras(tester);
    await _atras(tester);
    expect(find.text('abrir'), findsOneWidget);
  });

  testWidgets('película: Derecha e Izquierda recorren los botones de la barra, uno por uno', (tester) async {
    await _abrir(tester, ReproductorVodTv(canal: _canal(9, 'Matrix (1999)')));
    await _tecla(tester, LogicalKeyboardKey.select);
    expect(_enfocado(), 'pausa');
    await _tecla(tester, LogicalKeyboardKey.arrowRight);
    expect(_enfocado(), 'Agregar a favoritos');
    await _tecla(tester, LogicalKeyboardKey.arrowRight);
    expect(_enfocado(), 'Ajustes');
    await _tecla(tester, LogicalKeyboardKey.arrowRight); // en el borde: se queda
    expect(_enfocado(), 'Ajustes');
    await _tecla(tester, LogicalKeyboardKey.arrowLeft);
    await _tecla(tester, LogicalKeyboardKey.arrowLeft);
    expect(_enfocado(), 'pausa');
    // Abajo, a la línea de tiempo; Arriba vuelve a la fila
    await _tecla(tester, LogicalKeyboardKey.arrowDown);
    expect(_enfocado(), 'línea de tiempo');
    await _tecla(tester, LogicalKeyboardKey.arrowUp);
    expect(_enfocado(), 'pausa');
  });

  testWidgets('película: después de adelantar, Arriba lleva a los botones y Derecha los recorre', (tester) async {
    await _abrir(tester, ReproductorVodTv(canal: _canal(9, 'Matrix (1999)')));
    await _tecla(tester, LogicalKeyboardKey.arrowRight); // adelanta: el foco queda en la línea de tiempo
    expect(_enfocado(), 'línea de tiempo');
    await _tecla(tester, LogicalKeyboardKey.arrowUp);
    expect(_enfocado(), 'pausa');
    await _tecla(tester, LogicalKeyboardKey.arrowRight);
    expect(_enfocado(), 'Agregar a favoritos');
  });
}

/// Unos cuadros (300 ms). Sin pumpAndSettle: dejaría correr el reloj mientras
/// el video se actualiza, y los carteles se esconderían antes de mirarlos.
Future<void> _pasar(WidgetTester tester) async {
  for (var i = 0; i < 3; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}
