import 'dart:async';

import 'package:app_movil/aparato.dart';
import 'package:app_movil/bienvenida.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:video_player/video_player.dart';
import 'package:video_player_platform_interface/video_player_platform_interface.dart';

class _VideoDeMentira extends VideoPlayerPlatform {
  var _proximo = 0;
  final _eventos = <int, StreamController<VideoEvent>>{};
  String? ultimoAsset;

  @override
  Future<void> init() async {}

  @override
  Future<int?> createWithOptions(VideoCreationOptions options) async {
    ultimoAsset = options.dataSource.asset;
    final id = _proximo++;
    _eventos[id] = StreamController<VideoEvent>();
    return id;
  }

  @override
  Stream<VideoEvent> videoEventsFor(int playerId) {
    final eventos = _eventos[playerId]!;
    scheduleMicrotask(
      () => eventos.add(
        VideoEvent(eventType: VideoEventType.initialized, duration: Bienvenida.duracion, size: const Size(1080, 1920)),
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
}

void main() {
  late VideoPlayerPlatform plataformaAnterior;
  late _VideoDeMentira video;

  setUp(() {
    plataformaAnterior = VideoPlayerPlatform.instance;
    VideoPlayerPlatform.instance = video = _VideoDeMentira();
    Aparato.esTv = false;
  });

  tearDown(() {
    VideoPlayerPlatform.instance = plataformaAnterior;
    Aparato.esTv = false;
  });

  testWidgets('reproduce el video vertical encima de la app y se desvanece', (tester) async {
    tester.view.physicalSize = const Size(1080, 1920);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(const Bienvenida(esperarElVideo: false, child: MaterialApp(home: Text('la app'))));
    await tester.pump();

    expect(video.ultimoAsset, Bienvenida.videoCelular);
    expect(find.byType(VideoPlayer), findsOneWidget);
    // Por debajo la app ya está cargando, pero no se dibuja (el video la tapa)
    expect(find.text('la app', skipOffstage: false), findsOneWidget);
    expect(find.text('la app'), findsNothing);

    // Los botones del control no le llegan a la app mientras se ve el video
    expect(await tester.sendKeyEvent(LogicalKeyboardKey.select), isTrue);

    await tester.pump(const Duration(seconds: 2));
    expect(find.byType(VideoPlayer), findsOneWidget); // todavía se reproduce

    await tester.pump(); // termina la preparación asíncrona y registra el reloj
    await tester.pump(Bienvenida.duracion);
    await tester.pumpAndSettle();
    expect(find.byType(VideoPlayer), findsNothing);
    expect(find.text('la app'), findsOneWidget);
  });

  testWidgets('usa el video horizontal en TV', (tester) async {
    tester.view.physicalSize = const Size(1920, 1080);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    Aparato.esTv = true;

    await tester.pumpWidget(const Bienvenida(esperarElVideo: false, child: MaterialApp(home: Text('la app'))));
    await tester.pump();

    expect(video.ultimoAsset, Bienvenida.videoTv);
    expect(find.byType(VideoPlayer), findsOneWidget);
  });
}
