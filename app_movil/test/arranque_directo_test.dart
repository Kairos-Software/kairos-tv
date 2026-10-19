// Canales en vivo de listas Xtream (video directo MPEG-TS, ".../123.ts"): la
// conexión del proveedor es intermitente y a veces tarda más de 12 s en
// arrancar. Se espera más que con HLS y, si no arranca, se prueba la MISMA una
// vez más antes de pasar a otra fuente, sin avisarle al servidor ni abrir dos
// conexiones a la vez (hay cuentas que permiten una sola).
import 'dart:async';

import 'package:app_movil/api/cliente.dart';
import 'package:app_movil/api/modelos.dart';
import 'package:app_movil/movil/control_senal.dart';
import 'package:app_movil/movil/datos.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:video_player_platform_interface/video_player_platform_interface.dart';

/// Qué hace cada vez que se abre una dirección, en orden: 'anda', 'falla'
/// (Source error) o 'cuelga' (no contesta nunca). Después de la lista, anda.
class _VideoDeMentira extends VideoPlayerPlatform {
  _VideoDeMentira(this.guion);

  final Map<String, List<String>> guion;
  var _proximo = 0;
  final _eventos = <int, StreamController<VideoEvent>>{};
  final _direcciones = <int, String>{};
  final _vecesQueSeAbrio = <String, int>{};

  /// Lo que pasó, en orden: "abre (dirección)" y "cierra (dirección)".
  final historia = <String>[];

  /// Cuántos estuvieron abiertos a la vez, como mucho.
  var maximoAbiertos = 0;

  int vecesQueSeAbrio(String url) => _vecesQueSeAbrio[url] ?? 0;

  @override
  Future<void> init() async {}

  @override
  Future<int?> createWithOptions(VideoCreationOptions options) async {
    final id = _proximo++;
    final url = options.dataSource.uri ?? '';
    _eventos[id] = StreamController<VideoEvent>();
    _direcciones[id] = url;
    _vecesQueSeAbrio[url] = vecesQueSeAbrio(url) + 1;
    historia.add('abre $url');
    if (_eventos.length > maximoAbiertos) maximoAbiertos = _eventos.length;
    return id;
  }

  @override
  Stream<VideoEvent> videoEventsFor(int playerId) {
    final eventos = _eventos[playerId]!;
    final url = _direcciones[playerId]!;
    final pasos = guion[url] ?? const [];
    final vez = vecesQueSeAbrio(url) - 1;
    final que = vez < pasos.length ? pasos[vez] : 'anda';
    scheduleMicrotask(() {
      if (que == 'falla') {
        eventos.addError(PlatformException(code: 'VideoError', message: 'Video player had error Source error'));
      } else if (que == 'anda') {
        eventos.add(
          VideoEvent(
            eventType: VideoEventType.initialized,
            duration: const Duration(hours: 10),
            size: const Size(1920, 1080),
          ),
        );
      } // 'cuelga': no manda nada
    });
    return eventos.stream;
  }

  @override
  Future<void> dispose(int playerId) async {
    historia.add('cierra ${_direcciones[playerId]}');
    unawaited(_eventos.remove(playerId)?.close());
  }

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
class _ApiDePrueba extends ApiCliente {
  _ApiDePrueba() : super(urlBase: 'http://prueba/api/v1/');

  final avisos = <String>[];

  List<String> get fallas => avisos.where((ruta) => ruta.endsWith('/falla/')).toList();

  @override
  Future<dynamic> post(String ruta, [Map<String, dynamic>? cuerpo]) async {
    avisos.add(ruta);
    return null;
  }
}

const _xtream = 'http://servidor:8080/live/usuario/clave/444969.ts';
const _otra = 'http://otro:8080/live/usuario/clave/555.ts';
const _hls = 'https://x/canal.m3u8';

Canal _canal(List<(int, String, String)> fuentes, {String contenido = 'vivo'}) => Canal({
  'id': 7,
  'nombre': 'Canal',
  'fuentes': [
    for (final (id, url, tipo) in fuentes)
      {'id': id, 'url': url, 'tipo': tipo, 'user_agent': 'VLC/3.0.21 LibVLC/3.0.21'},
  ],
}, contenido: contenido);

late _VideoDeMentira _video;
late _ApiDePrueba _api;
final _abiertos = <ControlSenal>[];

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

Future<ControlSenal> _abrir(WidgetTester tester, Canal canal, Map<String, List<String>> guion) async {
  VideoPlayerPlatform.instance = _video = _VideoDeMentira(guion);
  final control = ControlSenal(_api = _ApiDePrueba());
  _abiertos.add(control);
  unawaited(control.abrir(canal));
  await _pasar(tester);
  return control;
}

/// Deja correr un ratito (y lo que, fuera de las pruebas, pasa solo).
Future<void> _pasar(WidgetTester tester, [Duration cuanto = const Duration(milliseconds: 300)]) async {
  final pasos = (cuanto.inMilliseconds / 50).ceil().clamp(6, 2000);
  for (var i = 0; i < pasos; i++) {
    await tester.pump(const Duration(milliseconds: 50));
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
  }
}

void main() {
  setUp(FuentePreferida.olvidarTodo);
  setUp(NoAnda.olvidarTodo);

  test('cuánto se espera a que arranque cada fuente', () {
    expect(ControlSenal.esperaDeArranque(enVivo: true, tipo: 'hls'), const Duration(seconds: 15));
    expect(ControlSenal.esperaDeArranque(enVivo: true, tipo: 'directo'), const Duration(seconds: 40));
    // Películas y capítulos, como siempre
    expect(ControlSenal.esperaDeArranque(enVivo: false, tipo: 'directo'), const Duration(seconds: 30));
    expect(ControlSenal.esperaDeArranque(enVivo: false, tipo: 'hls'), const Duration(seconds: 30));
  });

  _prueba('directo en vivo: si la primera vez no arranca, la segunda sí (y el servidor no se entera)', (tester) async {
    final control = await _abrir(tester, _canal([(11, _xtream, 'directo'), (12, _otra, 'directo')]), {
      _xtream: ['falla', 'anda'],
    });
    await _pasar(tester, const Duration(seconds: 2)); // el segundo de espera antes de reintentar
    expect(_video.vecesQueSeAbrio(_xtream), 2); // exactamente dos veces
    expect(_video.vecesQueSeAbrio(_otra), 0);
    expect(control.fuente, 0);
    expect(control.video, isNotNull);
    expect(control.error, isNull);
    expect(_api.fallas, isEmpty);
    // El que falló se cerró antes de abrir el segundo: nunca dos conexiones a la vez
    expect(_video.historia, ['abre $_xtream', 'cierra $_xtream', 'abre $_xtream']);
    expect(_video.maximoAbiertos, 1);
  });

  _prueba('directo en vivo: si falla las dos veces, recién ahí avisa y pasa a la siguiente', (tester) async {
    final control = await _abrir(tester, _canal([(11, _xtream, 'directo'), (12, _otra, 'directo')]), {
      _xtream: ['falla', 'falla'],
    });
    await _pasar(tester, const Duration(seconds: 2));
    expect(_video.vecesQueSeAbrio(_xtream), 2);
    expect(_api.fallas, ['canales/fuentes/11/falla/']); // una sola vez, después del reintento
    expect(control.fuente, 1);
    expect(control.video, isNotNull);
    expect(_video.historia, [
      'abre $_xtream',
      'cierra $_xtream',
      'abre $_xtream',
      'cierra $_xtream',
      'abre $_otra',
    ]);
    expect(_video.maximoAbiertos, 1);
  });

  _prueba('directo en vivo: espera 40 s a que arranque, y si no, lo cierra y reintenta', (tester) async {
    final control = await _abrir(tester, _canal([(11, _xtream, 'directo')]), {
      _xtream: ['cuelga', 'anda'],
    });
    await tester.pump(const Duration(seconds: 20)); // con 15 s (lo de HLS) ya se habría rendido
    expect(_video.vecesQueSeAbrio(_xtream), 1);
    await tester.pump(const Duration(seconds: 21));
    await _pasar(tester, const Duration(seconds: 2));
    expect(_video.vecesQueSeAbrio(_xtream), 2);
    expect(control.video, isNotNull);
    expect(_api.fallas, isEmpty);
    expect(_video.historia, ['abre $_xtream', 'cierra $_xtream', 'abre $_xtream']);
    expect(_video.maximoAbiertos, 1);
  });

  _prueba('HLS en vivo: sin reintento, pasa enseguida a la siguiente (como siempre)', (tester) async {
    final control = await _abrir(tester, _canal([(11, _hls, 'hls'), (12, _otra, 'directo')]), {
      _hls: ['falla'],
    });
    await _pasar(tester);
    expect(_video.vecesQueSeAbrio(_hls), 1);
    expect(_api.fallas, ['canales/fuentes/11/falla/']);
    expect(control.fuente, 1);
  });

  _prueba('una película directa: sin reintento (como siempre)', (tester) async {
    final control = await _abrir(tester, _canal([(11, _xtream, 'directo'), (12, _otra, 'directo')], contenido: 'pelicula'), {
      _xtream: ['falla'],
    });
    await _pasar(tester);
    expect(_video.vecesQueSeAbrio(_xtream), 1);
    expect(control.fuente, 1);
  });

  _prueba('el reproductor recibe el User-Agent de la API', (tester) async {
    VideoPlayerPlatform.instance = _video = _VideoDeMentira({});
    String? agente;
    final espia = _Espia(_video, (opciones) => agente = opciones.dataSource.httpHeaders['User-Agent']);
    VideoPlayerPlatform.instance = espia;
    final control = ControlSenal(_api = _ApiDePrueba());
    _abiertos.add(control);
    unawaited(control.abrir(_canal([(11, _xtream, 'directo')])));
    await _pasar(tester);
    expect(agente, 'VLC/3.0.21 LibVLC/3.0.21');
  });
}

/// Pasa todo al de mentira, pero se fija con qué opciones se abrió.
class _Espia extends _VideoDeMentira {
  _Espia(_VideoDeMentira base, this.alAbrir) : super(base.guion);

  final void Function(VideoCreationOptions opciones) alAbrir;

  @override
  Future<int?> createWithOptions(VideoCreationOptions options) {
    alAbrir(options);
    return super.createWithOptions(options);
  }
}
