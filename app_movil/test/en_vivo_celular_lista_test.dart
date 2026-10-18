// En vivo en el celular: al tocar un canal de abajo (Zappin, con la Z), la
// lista se queda donde está. Antes subía hasta arriba (A24) y había que volver
// a bajar para probar el de al lado si ese no andaba.
import 'dart:async';

import 'package:app_movil/api/modelos.dart';
import 'package:app_movil/movil/datos.dart';
import 'package:app_movil/movil/en_vivo.dart';
import 'package:app_movil/sesion.dart';
import 'package:flutter/material.dart';
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

// La lista de canales (la de las categorías va de costado)
final _lista = find.byWidgetPredicate((w) => w is Scrollable && w.axisDirection == AxisDirection.down);

double _dondeEsta(WidgetTester tester) => tester.state<ScrollableState>(_lista).position.pixels;

void main() {
  testWidgets('tocar un canal de abajo no sube la lista', (tester) async {
    tester.view.physicalSize = const Size(400, 860);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    SharedPreferences.setMockInitialValues({});
    VideoPlayerPlatform.instance = _VideoDeMentira();
    final catalogo = Catalogo(Sesion().api)
      ..categoriasEnVivo = [
        CategoriaCanales({
          'nombre': 'Todos',
          'canales': [
            for (var id = 1; id <= 40; id++)
              {
                'id': id,
                'nombre': id == 40 ? 'Zappin' : 'Canal $id',
                'fuentes': [
                  {'id': id, 'url': 'https://x/$id.m3u8', 'tipo': 'hls', 'codec': 'h264'},
                ],
              },
          ],
        }),
      ]
      ..cargado = true;
    await tester.pumpWidget(
      SesionScope(
        sesion: Sesion(),
        child: MaterialApp(
          home: Scaffold(
            body: DatosScope(catalogo: catalogo, biblioteca: Biblioteca(), child: const SeccionEnVivo(visible: true)),
          ),
        ),
      ),
    );
    await tester.pump();

    final zappin = find.text('Zappin');
    await tester.scrollUntilVisible(zappin, 300, scrollable: _lista);
    await tester.pump();
    final abajo = _dondeEsta(tester);
    expect(abajo, greaterThan(1000));

    await tester.tap(zappin);
    for (var i = 0; i < 5; i++) {
      await tester.pump(const Duration(milliseconds: 200));
    }
    expect(_dondeEsta(tester), abajo); // sigue donde estaba...
    expect(find.text('Canal 39').hitTestable(), findsOneWidget); // ...con el de al lado a mano

    await tester.pump(const Duration(seconds: 5)); // que se escondan los controles
  });
}
