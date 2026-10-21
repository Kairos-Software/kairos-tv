// Canales que se cortan: pasar solo a otra fuente, recordar la que anda bien
// en este aparato y soltar el video cuando la app se va al fondo. El video es
// "de mentira": arranca (o falla, si su dirección dice "mala") y se le
// simulan los cortes (se frena a cargar y sigue).
import 'dart:async';

import 'package:app_movil/api/cliente.dart';
import 'package:app_movil/api/modelos.dart';
import 'package:app_movil/movil/control_senal.dart';
import 'package:app_movil/movil/datos.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:video_player_platform_interface/video_player_platform_interface.dart';

import 'servidor_de_prueba.dart';

class _VideoDeMentira extends VideoPlayerPlatform {
  var _proximo = 0;
  final _eventos = <int, StreamController<VideoEvent>>{};
  final _direcciones = <int, String>{};

  /// Los videos abiertos ahora (los cerrados se sacan).
  Iterable<int> get abiertos => _eventos.keys;

  @override
  Future<void> init() async {}

  @override
  Future<int?> createWithOptions(VideoCreationOptions options) async {
    final id = _proximo++;
    _eventos[id] = StreamController<VideoEvent>();
    _direcciones[id] = options.dataSource.uri ?? '';
    return id;
  }

  @override
  Stream<VideoEvent> videoEventsFor(int playerId) {
    final eventos = _eventos[playerId]!;
    final mala = _direcciones[playerId]!.contains('mala');
    scheduleMicrotask(() {
      if (mala) {
        eventos.addError(PlatformException(code: 'VideoError', message: 'Source error'));
      } else {
        eventos.add(
          // Con duración 0 el reproductor lo daría por terminado enseguida
          VideoEvent(
            eventType: VideoEventType.initialized,
            duration: const Duration(hours: 10),
            size: const Size(1920, 1080),
          ),
        );
      }
    });
    return eventos.stream;
  }

  /// Se frena a cargar y sigue (un corte).
  void cortar(int playerId) {
    _eventos[playerId]!
      ..add(VideoEvent(eventType: VideoEventType.bufferingStart))
      ..add(VideoEvent(eventType: VideoEventType.bufferingEnd));
  }

  @override
  Future<void> dispose(int playerId) async => unawaited(_eventos.remove(playerId)?.close());

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

/// No habla con ningún servidor: anota lo que se le avisaría.
class _ApiDePrueba extends ApiCliente with CrudoDesdeGet {
  _ApiDePrueba() : super(urlBase: 'http://prueba/api/v1/');

  final avisos = <String>[];

  @override
  Future<dynamic> post(String ruta, [Map<String, dynamic>? cuerpo]) async {
    avisos.add(ruta);
    return null;
  }
}

/// HBO con tres fuentes; [malas]: las que no arrancan.
Canal _hbo({Set<int> malas = const {}}) => Canal({
  'id': 50,
  'nombre': 'HBO',
  'fuentes': [
    for (final id in [11, 12, 13]) {'id': id, 'url': 'https://x/${malas.contains(id) ? 'mala' : 'buena'}$id.m3u8'},
  ],
}, categoria: 'Cine');

late _VideoDeMentira _video;
final _abiertos = <ControlSenal>[];

/// Una prueba que al final cierra los reproductores (dentro de la prueba:
/// si no, quedan relojes andando y la prueba falla).
void _prueba(String nombre, Future<void> Function(WidgetTester tester) cuerpo) {
  testWidgets(nombre, (tester) async {
    await cuerpo(tester);
    for (final control in _abiertos) {
      control.dispose();
    }
    _abiertos.clear();
    await _pasar(tester);
  });
}

Future<ControlSenal> _abrir(WidgetTester tester, Canal canal) async {
  VideoPlayerPlatform.instance = _video = _VideoDeMentira();
  final control = ControlSenal(_ApiDePrueba());
  _abiertos.add(control);
  unawaited(control.abrir(canal)); // sin esperarlo: si una fuente falla, cerrarla necesita _pasar
  await _pasar(tester);
  return control;
}

/// El video que se está viendo se corta [veces] veces.
Future<void> _cortar(WidgetTester tester, int veces) async {
  for (var i = 0; i < veces; i++) {
    _video.cortar(_video.abiertos.last);
    await _pasar(tester);
  }
}

/// Deja correr un ratito. Cerrar un video espera cosas que fuera de las
/// pruebas pasan solas (runAsync las deja avanzar).
Future<void> _pasar(WidgetTester tester) async {
  for (var i = 0; i < 6; i++) {
    await tester.pump(const Duration(milliseconds: 50));
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
  }
}

void main() {
  setUp(FuentePreferida.olvidarTodo);
  setUp(NoAnda.olvidarTodo);

  _prueba('en vivo: la fuente que se corta seguido se cambia sola por la siguiente', (tester) async {
    final control = await _abrir(tester, _hbo());
    expect(control.fuente, 0);
    await _cortar(tester, 2);
    expect(control.fuente, 0); // dos cortes: todavía no
    expect(control.cortes, 2);
    await _cortar(tester, 1);
    expect(control.fuente, 1); // al tercero, a la fuente 2
    expect(control.error, isNull);
    expect(control.video, isNotNull);
  });

  _prueba('si las otras no arrancan, vuelve a la que se cortaba y se queda', (tester) async {
    final control = await _abrir(tester, _hbo(malas: {12, 13}));
    await _cortar(tester, 3);
    expect(control.fuente, 0); // probó la 2 y la 3, no anduvieron: volvió a la 1
    expect(control.error, isNull);
    await _cortar(tester, 3);
    expect(control.fuente, 0); // y ya no cambia más
  });

  _prueba('la fuente elegida a mano no se cambia por cortes', (tester) async {
    final control = await _abrir(tester, _hbo());
    unawaited(control.usarFuente(2));
    await _pasar(tester);
    await _cortar(tester, 4);
    expect(control.fuente, 2);
  });

  _prueba('arranca con la fuente que mejor anduvo en este aparato', (tester) async {
    FuentePreferida.anotar(50, 13);
    final control = await _abrir(tester, _hbo());
    expect(control.fuente, 2);
  });

  _prueba('si la preferida no arranca, prueba también las de antes', (tester) async {
    FuentePreferida.anotar(50, 13);
    final control = await _abrir(tester, _hbo(malas: {13}));
    expect(control.fuente, 0); // dio la vuelta
    expect(control.error, isNull);
  });

  _prueba('al irse la app al fondo suelta el video y al volver se reconecta', (tester) async {
    final control = await _abrir(tester, _hbo());
    expect(_video.abiertos, hasLength(1));
    for (final estado in [AppLifecycleState.inactive, AppLifecycleState.hidden, AppLifecycleState.paused]) {
      tester.binding.handleAppLifecycleStateChanged(estado);
    }
    await _pasar(tester);
    expect(control.video, isNull);
    expect(_video.abiertos, isEmpty); // el decodificador quedó libre

    for (final estado in [AppLifecycleState.hidden, AppLifecycleState.inactive, AppLifecycleState.resumed]) {
      tester.binding.handleAppLifecycleStateChanged(estado);
    }
    await _pasar(tester);
    expect(control.video, isNotNull);
    expect(control.fuente, 0);
  });

  _prueba('si se había detenido a propósito, al volver a la app no se reconecta', (tester) async {
    final control = await _abrir(tester, _hbo());
    unawaited(control.detener());
    await _pasar(tester);
    for (final estado in [AppLifecycleState.inactive, AppLifecycleState.hidden, AppLifecycleState.paused]) {
      tester.binding.handleAppLifecycleStateChanged(estado);
    }
    for (final estado in [AppLifecycleState.hidden, AppLifecycleState.inactive, AppLifecycleState.resumed]) {
      tester.binding.handleAppLifecycleStateChanged(estado);
    }
    await _pasar(tester);
    expect(control.video, isNull);
  });
}
