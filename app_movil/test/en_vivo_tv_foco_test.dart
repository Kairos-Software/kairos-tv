// En vivo en la TV: al volver del canal (Atrás), el foco queda en el canal que
// se eligió, no vuelve al primero de arriba (si no andaba, había que bajar de
// nuevo para probar otro).
import 'dart:async';

import 'package:app_movil/api/modelos.dart';
import 'package:app_movil/movil/datos.dart';
import 'package:app_movil/sesion.dart';
import 'package:app_movil/tv/estructura.dart';
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
        VideoEvent(eventType: VideoEventType.initialized, duration: Duration.zero, size: const Size(1920, 1080)),
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

CategoriaCanales _categoria(String nombre, int desde, {int cuantos = 12}) => CategoriaCanales({
  'nombre': nombre,
  'canales': [
    for (var id = desde; id < desde + cuantos; id++)
      {
        'id': id,
        'nombre': 'Canal $id',
        'fuentes': [
          {'id': id, 'url': 'https://x/$id.m3u8', 'tipo': 'hls', 'codec': 'h264'},
        ],
      },
  ],
});

String? _enfocado() => FocusManager.instance.primaryFocus?.debugLabel;

Future<void> _pasar(WidgetTester tester) async {
  for (var i = 0; i < 5; i++) {
    await tester.pump(const Duration(milliseconds: 200));
  }
}

Future<void> _tecla(WidgetTester tester, LogicalKeyboardKey tecla) async {
  await tester.sendKeyEvent(tecla);
  await _pasar(tester);
}

Future<Catalogo> _abrirEnVivo(
  WidgetTester tester, {
  SeccionTv seccion = SeccionTv.enVivo,
  List<CategoriaCanales>? categorias,
}) async {
  tester.view.physicalSize = const Size(1920, 1080);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  SharedPreferences.setMockInitialValues({});
  VideoPlayerPlatform.instance = _VideoDeMentira();
  final catalogo = Catalogo(Sesion().api)
    ..categoriasEnVivo =
        categorias ?? [_categoria('Noticias', 1), _categoria('Deportes', 101), _categoria('Música', 201)]
    ..cargado = true;
  await tester.pumpWidget(
    SesionScope(
      sesion: Sesion(),
      child: MaterialApp(
        home: PantallaTv(catalogo: catalogo, biblioteca: Biblioteca(), seccionInicial: seccion),
      ),
    ),
  );
  await _pasar(tester);
  return catalogo;
}

Future<void> _verYVolver(WidgetTester tester, {Future<void> Function()? mientras}) async {
  await _tecla(tester, LogicalKeyboardKey.select);
  expect(find.byType(ReproductorVivoTv), findsOneWidget);
  await mientras?.call();
  await _pasar(tester);
  await tester.binding.handlePopRoute(); // Atrás: sale del canal
  await _pasar(tester);
  await tester.pump(const Duration(seconds: 5)); // el cartel del canal y lo que tarde en cerrarse
  await _pasar(tester);
  expect(find.byType(ReproductorVivoTv), findsNothing);
}

void main() {
  testWidgets('"Todo": al volver del canal, el foco sigue en ese canal (no en el primero)', (tester) async {
    await _abrirEnVivo(tester);
    expect(_enfocado(), startsWith('Canal 1,'));
    await _tecla(tester, LogicalKeyboardKey.arrowDown);
    await _tecla(tester, LogicalKeyboardKey.arrowDown); // fila de Música
    for (var i = 0; i < 4; i++) {
      await _tecla(tester, LogicalKeyboardKey.arrowRight);
    }
    final elegido = _enfocado();
    expect(elegido, isNot(startsWith('Canal 1,')));
    await _verYVolver(tester);
    expect(_enfocado(), elegido);
  });

  testWidgets('una categoría (grilla): al volver del canal, el foco sigue en ese canal', (tester) async {
    await _abrirEnVivo(tester);
    await _tecla(tester, LogicalKeyboardKey.arrowUp); // a los chips de categorías
    await _tecla(tester, LogicalKeyboardKey.arrowRight); // "Noticias"
    await _tecla(tester, LogicalKeyboardKey.select);
    await _tecla(tester, LogicalKeyboardKey.arrowDown);
    await _tecla(tester, LogicalKeyboardKey.arrowDown);
    await _tecla(tester, LogicalKeyboardKey.arrowRight);
    final elegido = _enfocado();
    expect(elegido, startsWith('Canal '));
    await _verYVolver(tester);
    expect(_enfocado(), elegido);
  });

  testWidgets('"Todo" con muchas categorías: al volver de una fila de abajo, sigue ahí', (tester) async {
    await _abrirEnVivo(tester, categorias: [for (var c = 0; c < 10; c++) _categoria('Categoría $c', c * 100 + 1)]);
    for (var i = 0; i < 7; i++) {
      await _tecla(tester, LogicalKeyboardKey.arrowDown);
    }
    await _tecla(tester, LogicalKeyboardKey.arrowRight);
    final elegido = _enfocado();
    expect(elegido, endsWith('Canal 702'));
    await _verYVolver(tester);
    expect(_enfocado(), elegido);
  });

  testWidgets('guía: al volver de un canal de abajo, sigue ahí', (tester) async {
    await _abrirEnVivo(tester, seccion: SeccionTv.guia, categorias: [_categoria('Noticias', 1, cuantos: 60)]);
    expect(_enfocado(), startsWith('Canal 1,'));
    for (var i = 0; i < 30; i++) {
      await _tecla(tester, LogicalKeyboardKey.arrowDown);
    }
    final elegido = _enfocado();
    expect(elegido, endsWith('Canal 31'));
    await _verYVolver(tester);
    expect(_enfocado(), elegido);
  });

  testWidgets('si mientras se mira el catálogo se vuelve a cargar, al volver sigue ahí', (tester) async {
    final catalogo = await _abrirEnVivo(tester);
    await _tecla(tester, LogicalKeyboardKey.arrowDown);
    await _tecla(tester, LogicalKeyboardKey.arrowRight);
    await _tecla(tester, LogicalKeyboardKey.arrowRight);
    final elegido = _enfocado();
    await _verYVolver(
      tester,
      mientras: () async {
        // Como la recarga de cada 15 minutos: listas y canales nuevos (los mismos datos)
        catalogo.categoriasEnVivo = [_categoria('Noticias', 1), _categoria('Deportes', 101), _categoria('Música', 201)];
        catalogo.notifyListeners();
      },
    );
    expect(_enfocado(), elegido);
  });

  testWidgets('si el canal elegido no anda y se esconde, al volver queda en el de al lado (no arriba)', (tester) async {
    final catalogo = await _abrirEnVivo(tester);
    await _tecla(tester, LogicalKeyboardKey.arrowDown);
    for (var i = 0; i < 4; i++) {
      await _tecla(tester, LogicalKeyboardKey.arrowRight);
    }
    expect(_enfocado(), endsWith('Canal 105'));
    await _verYVolver(tester, mientras: () async => NoAnda.anotar(catalogo.canalPorId(105)!, deFormato: true));
    expect(_enfocado(), endsWith('Canal 106'));
  });

  testWidgets('guía: si el canal elegido no anda y se esconde, al volver queda en el de al lado', (tester) async {
    final catalogo = await _abrirEnVivo(
      tester,
      seccion: SeccionTv.guia,
      categorias: [_categoria('Noticias', 1, cuantos: 60)],
    );
    for (var i = 0; i < 30; i++) {
      await _tecla(tester, LogicalKeyboardKey.arrowDown);
    }
    expect(_enfocado(), endsWith('Canal 31'));
    await _verYVolver(tester, mientras: () async => NoAnda.anotar(catalogo.canalPorId(31)!, deFormato: true));
    expect(_enfocado(), endsWith('Canal 32'));
  });
}
