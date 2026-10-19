// El modo revisión (lib/revision/): el aparato recorre los canales solo, de a
// uno, y le cuenta al servidor cuáles andan.

import 'dart:async';

import 'package:app_movil/api/cliente.dart';
import 'package:app_movil/aparato.dart';
import 'package:app_movil/movil/control_senal.dart';
import 'package:app_movil/revision/pantalla_recorrido.dart';
import 'package:app_movil/revision/recorrido.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:video_player/video_player.dart';
import 'package:video_player_platform_interface/video_player_platform_interface.dart';

FuenteARevisar _fuente(int id, String canal, {String tipo = 'hls', bool enVivo = true}) => FuenteARevisar({
  'id': id,
  'url': 'http://x/$id',
  'tipo': tipo,
  'canal': canal,
  'en_vivo': enVivo,
});

/// El servidor de mentira: entrega las tandas que se le dan y anota lo que le cuentan.
class _Servidor implements ServidorDelRecorrido {
  _Servidor(this.tandas);

  final List<List<FuenteARevisar>> tandas;
  final contado = <Map<String, dynamic>>[];
  var pedidos = 0;
  ApiError? fallarAlPedir;
  ApiError? fallarAlContar;

  @override
  Future<(List<FuenteARevisar>, int)> pedir(int cantidad) async {
    pedidos++;
    final error = fallarAlPedir;
    if (error != null) {
      fallarAlPedir = null;
      throw error;
    }
    final tanda = tandas.isEmpty ? <FuenteARevisar>[] : tandas.removeAt(0);
    return (tanda, tandas.fold(tanda.length, (suma, t) => suma + t.length));
  }

  @override
  Future<void> contar(List<Map<String, dynamic>> resultados) async {
    final error = fallarAlContar;
    if (error != null) {
      fallarAlContar = null;
      throw error;
    }
    contado.addAll(resultados);
  }
}

final _sinConexion = ApiError(status: 0, codigo: 'sin_conexion', detalle: 'No se pudo conectar con el servidor.');

Future<void> _hastaQueTermine(Recorrido recorrido) async {
  for (var i = 0; i < 200 && !recorrido.terminado; i++) {
    await Future<void>.delayed(Duration.zero);
  }
}

Recorrido _recorrido(_Servidor servidor, Map<int, Prueba> resultados) => Recorrido(
  servidor,
  (fuente, mostrar) async => resultados[fuente.fuente.id] ?? const Prueba.anduvo(),
  pausaEntreCanales: Duration.zero,
  esperaSinConexion: Duration.zero,
);

/// El reproductor de mentira para probar [probarConElReproductor]: arranca y
/// se ve, se queda cargando (`trabado`) o no arranca (`error`).
class _Video extends VideoPlayerPlatform {
  _Video({this.error, this.trabado = false});

  final PlatformException? error;
  final bool trabado;
  var _proximo = 0;
  final cerrados = <int>[];
  final _eventos = <int, StreamController<VideoEvent>>{};
  final pedidos = <String>[];

  @override
  Future<void> init() async {}

  @override
  Future<int?> createWithOptions(VideoCreationOptions options) async {
    pedidos.add(options.dataSource.uri ?? '');
    final id = _proximo++;
    _eventos[id] = StreamController<VideoEvent>();
    return id;
  }

  @override
  Stream<VideoEvent> videoEventsFor(int playerId) {
    final eventos = _eventos[playerId]!;
    scheduleMicrotask(() {
      final falla = error;
      if (falla != null) {
        eventos.addError(falla);
      } else {
        eventos.add(
          VideoEvent(eventType: VideoEventType.initialized, duration: Duration.zero, size: const Size(1280, 720)),
        );
        if (trabado) eventos.add(VideoEvent(eventType: VideoEventType.bufferingStart));
      }
    });
    return eventos.stream;
  }

  @override
  Future<void> dispose(int playerId) async {
    cerrados.add(playerId);
    await _eventos.remove(playerId)?.close();
  }

  @override
  Future<Duration> getPosition(int playerId) async => Duration.zero; // en vivo no avanza: no se usa

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
  Future<void> setMixWithOthers(bool mixWithOthers) async {}

  @override
  Widget buildViewWithOptions(VideoViewOptions options) => const SizedBox.expand();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('Recorrido', () {
    test('recorre todo de a una, le cuenta al servidor y termina', () async {
      final servidor = _Servidor([
        [_fuente(1, 'Telefe'), _fuente(2, 'HBO')],
        [_fuente(3, 'ESPN')],
      ]);
      final rechazo = Prueba.fallo(Falla('rechazo', 'El servidor de la señal no deja verla (error 403).', '403'));
      final recorrido = _recorrido(servidor, {2: rechazo})..empezar();
      await _hastaQueTermine(recorrido);

      expect(recorrido.terminado, isTrue);
      expect(recorrido.corriendo, isFalse);
      expect((recorrido.probadas, recorrido.andan, recorrido.fallan), (3, 2, 1));
      expect(servidor.contado, [
        {'id': 1, 'anduvo': true},
        {'id': 2, 'anduvo': false, 'motivo': 'rechazo', 'detalle': '403'},
        {'id': 3, 'anduvo': true},
      ]);
      expect(recorrido.ultimos.map((p) => p.canal), ['ESPN', 'HBO', 'Telefe']);
      expect(recorrido.estado, contains('no queda nada por probar'));
      recorrido.dispose();
    });

    test('sin internet no cuenta: espera y la vuelve a pedir', () async {
      final servidor = _Servidor([
        [_fuente(1, 'Telefe')],
        [_fuente(1, 'Telefe')],
      ]);
      var veces = 0;
      final recorrido = Recorrido(
        servidor,
        (fuente, mostrar) async => ++veces == 1 ? Prueba.fallo(Falla.sinInternet) : const Prueba.anduvo(),
        pausaEntreCanales: Duration.zero,
        esperaSinConexion: Duration.zero,
      )..empezar();
      await _hastaQueTermine(recorrido);
      expect(servidor.contado, [
        {'id': 1, 'anduvo': true},
      ]);
      expect(recorrido.probadas, 1);
      recorrido.dispose();
    });

    test('si no llega al servidor, lo vuelve a intentar y no pierde lo probado', () async {
      final servidor = _Servidor([
        [_fuente(1, 'Telefe')],
      ])
        ..fallarAlPedir = _sinConexion
        ..fallarAlContar = _sinConexion;
      final recorrido = _recorrido(servidor, {})..empezar();
      await _hastaQueTermine(recorrido);
      expect(servidor.pedidos, greaterThanOrEqualTo(2));
      // El primer envío falló: se manda en el siguiente (al terminar o al parar)
      recorrido.parar();
      recorrido.dispose();
      await Future<void>.delayed(Duration.zero);
      expect(servidor.contado, [
        {'id': 1, 'anduvo': true},
      ]);
    });

    test('parar corta enseguida', () async {
      final servidor = _Servidor([
        [for (var i = 1; i <= 10; i++) _fuente(i, 'Canal $i')],
      ]);
      late Recorrido recorrido;
      recorrido = Recorrido(servidor, (fuente, mostrar) async {
        if (fuente.fuente.id == 2) recorrido.parar();
        return const Prueba.anduvo();
      }, pausaEntreCanales: Duration.zero)..empezar();
      for (var i = 0; i < 50; i++) {
        await Future<void>.delayed(Duration.zero);
      }
      expect(recorrido.corriendo, isFalse);
      expect(recorrido.probadas, 1); // la 2 se estaba probando cuando se paró: no cuenta
      expect(recorrido.estado, 'Detenido.');
      recorrido.dispose();
    });
  });

  group('La prueba con el reproductor', () {
    const rapido = Duration(seconds: 1);

    test('anda si se ve un rato seguido; después lo cierra', () async {
      final video = _Video();
      VideoPlayerPlatform.instance = video;
      final mostrados = <VideoPlayerController?>[];
      final prueba = await probarConElReproductor(_fuente(1, 'Telefe'), mostrados.add, alcanza: rapido);
      expect(prueba.anduvo, isTrue);
      expect(video.pedidos, ['http://x/1']);
      expect(video.cerrados, [0]);
      expect(mostrados.last, isNull); // ya no se muestra
    });

    test('si se queda cargando, falla: trabada', () async {
      VideoPlayerPlatform.instance = _Video(trabado: true);
      final prueba = await probarConElReproductor(
        _fuente(1, 'Telefe'),
        (_) {},
        alcanza: rapido,
        esperaMaxima: const Duration(seconds: 2),
      );
      expect((prueba.anduvo, prueba.motivo), (false, 'tiempo'));
    });

    test('si el servidor de la señal lo rechaza, falla con ese motivo', () async {
      VideoPlayerPlatform.instance = _Video(
        error: PlatformException(code: 'VideoError', message: 'Source error: Response code: 403'),
      );
      final prueba = await probarConElReproductor(_fuente(1, 'HBO'), (_) {});
      expect((prueba.anduvo, prueba.motivo), (false, 'rechazo'));
    });

    test('un Xtream en vivo se prueba dos veces antes de darlo por fallado', () async {
      final video = _Video(error: PlatformException(code: 'VideoError', message: 'Source error'));
      VideoPlayerPlatform.instance = video;
      final prueba = await probarConElReproductor(_fuente(1, 'ESPN', tipo: 'directo'), (_) {});
      expect(prueba.anduvo, isFalse);
      expect(video.pedidos.length, 2);
    });
  });

  testWidgets('la pantalla: empezar, ver lo probado y parar', (tester) async {
    final servidor = _Servidor([
      [_fuente(1, 'Telefe'), _fuente(2, 'HBO')],
    ]);
    final completar = Completer<Prueba>();
    final recorrido = Recorrido(servidor, (fuente, mostrar) {
      if (fuente.fuente.id == 1) return Future.value(const Prueba.anduvo());
      return completar.future;
    }, pausaEntreCanales: Duration.zero);
    addTearDown(recorrido.dispose);
    await tester.pumpWidget(MaterialApp(home: PantallaRecorrido(recorrido: recorrido)));

    expect(find.text('Empezar'), findsOneWidget);
    await tester.tap(find.byKey(const Key('recorrido-boton')));
    for (var i = 0; i < 10; i++) {
      await tester.pump(const Duration(milliseconds: 1));
    }
    expect(find.text('Parar'), findsOneWidget);
    expect(find.text('Probando HBO...'), findsOneWidget);
    expect(find.text('Telefe'), findsWidgets);

    await tester.tap(find.byKey(const Key('recorrido-boton')));
    await tester.pump();
    expect(find.text('Seguir'), findsOneWidget);
    completar.complete(const Prueba.anduvo());
  });

  for (final (nombre, ancho, alto, tv) in [('celular', 360.0, 740.0, false), ('TV', 1920.0, 1080.0, true)]) {
    testWidgets('en $nombre entra todo, con lo probado y sus motivos', (tester) async {
      tester.view.physicalSize = Size(ancho, alto);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      Aparato.esTv = tv;
      addTearDown(() => Aparato.esTv = false);
      final servidor = _Servidor([
        [for (var i = 1; i <= 9; i++) _fuente(i, 'Un canal con un nombre bastante largo número $i')],
      ]);
      final rechazo = Prueba.fallo(const Falla('rechazo', 'El servidor de la señal no deja verla (error 403).'));
      final recorrido = Recorrido(
        servidor,
        (fuente, mostrar) async => fuente.fuente.id.isEven ? rechazo : const Prueba.anduvo(),
        pausaEntreCanales: Duration.zero,
      );
      addTearDown(recorrido.dispose);
      await tester.pumpWidget(MaterialApp(home: PantallaRecorrido(recorrido: recorrido)));
      await tester.tap(find.byKey(const Key('recorrido-boton')));
      for (var i = 0; i < 40; i++) {
        await tester.pump(const Duration(milliseconds: 1));
      }
      expect(tester.takeException(), isNull);
      expect(recorrido.probadas, 9);
      expect(find.textContaining('no deja verla'), findsWidgets);
    });
  }
}
