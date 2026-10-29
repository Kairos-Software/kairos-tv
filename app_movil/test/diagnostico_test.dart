// Una señal que en un aparato "no conecta nunca" y en otro anda: el
// reproductor de Android mira por dentro (KairosVigia) si llegó el video y si
// el decodificador del aparato devolvió imagen. La app se lo pregunta cuando
// la señal no arranca a tiempo, para no culpar al servidor de la señal de lo
// que es del aparato (el servidor esconde para todos lo que falla en los
// aparatos) y para que el panel diga qué pasó, en qué aparato y con qué app.
import 'dart:async';

import 'package:app_movil/api/cliente.dart';
import 'package:app_movil/api/modelos.dart';
import 'package:app_movil/aparato.dart';
import 'package:app_movil/movil/control_senal.dart';
import 'package:app_movil/movil/datos.dart';
import 'package:app_movil/movil/diagnostico.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:video_player_platform_interface/video_player_platform_interface.dart';

import 'servidor_de_prueba.dart';

/// Cada dirección: 'cuelga' (no arranca nunca) o 'tarda' (arranca a los 25 s).
/// Lo que no está en el guion, anda enseguida.
class _VideoDeMentira extends VideoPlayerPlatform {
  _VideoDeMentira(this.guion);

  final Map<String, String> guion;
  var _proximo = 0;
  final _eventos = <int, StreamController<VideoEvent>>{};
  final _direcciones = <int, String>{};
  final abiertas = <String>[];

  @override
  Future<void> init() async {}

  @override
  Future<int?> createWithOptions(VideoCreationOptions options) async {
    final id = _proximo++;
    _eventos[id] = StreamController<VideoEvent>();
    _direcciones[id] = options.dataSource.uri ?? '';
    abiertas.add(_direcciones[id]!);
    return id;
  }

  @override
  Stream<VideoEvent> videoEventsFor(int playerId) {
    final eventos = _eventos[playerId]!;
    void arrancar() {
      if (eventos.isClosed) return;
      eventos.add(
        VideoEvent(
          eventType: VideoEventType.initialized,
          duration: const Duration(hours: 10),
          size: const Size(1920, 1080),
        ),
      );
    }

    switch (guion[_direcciones[playerId]]) {
      case 'cuelga':
        break;
      case 'tarda':
        Timer(const Duration(seconds: 25), arrancar);
      default:
        scheduleMicrotask(arrancar);
    }
    return eventos.stream;
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

/// Anota los avisos de falla que se le mandarían al servidor.
class _ApiDePrueba extends ApiCliente with CrudoDesdeGet {
  _ApiDePrueba() : super(urlBase: 'http://prueba/api/v1/');

  final fallas = <Map<String, dynamic>>[];

  @override
  Future<dynamic> post(String ruta, [Map<String, dynamic>? cuerpo]) async {
    if (ruta.endsWith('/falla/')) fallas.add({'ruta': ruta, ...?cuerpo});
    return null;
  }
}

const _hls = 'https://servidor/canal.m3u8';
const _otra = 'https://otro/canal.m3u8';
const _canalReproductor = MethodChannel('kairos/reproductor');

Canal _canal(List<String> direcciones) => Canal({
  'id': 7,
  'nombre': 'Canal',
  'fuentes': [
    for (final (i, url) in direcciones.indexed) {'id': 11 + i, 'url': url, 'tipo': 'hls'},
  ],
}, contenido: 'vivo');

/// Lo que contesta "el reproductor" cuando la app pregunta qué pasó.
void _elReproductorDice(Map<String, Object?>? Function(String url) respuesta) {
  TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
    _canalReproductor,
    (llamada) async => respuesta((llamada.arguments as Map)['url'] as String),
  );
}

Future<void> _pasar(WidgetTester tester, Duration cuanto) async {
  final pasos = (cuanto.inMilliseconds / 50).ceil().clamp(6, 4000);
  for (var i = 0; i < pasos; i++) {
    await tester.pump(const Duration(milliseconds: 50));
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
  }
}

void main() {
  setUp(FuentePreferida.olvidarTodo);
  setUp(NoAnda.olvidarTodo);
  setUp(() {
    Aparato.version = '1.2.40';
    Aparato.nombre = 'Lenovo TB-X505F';
    Aparato.android = '10';
  });
  tearDown(() {
    Aparato.version = '';
    Aparato.nombre = 'App Android';
    Aparato.android = '';
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(_canalReproductor, null);
  });

  group('qué se le cuenta al servidor', () {
    const llegoYNoSeVio = Diagnostico(
      texto: 'video h264 1920x1080 25 fps · deco OMX.MTK.VIDEO.DECODER.AVC: entraron 12, salieron 0',
      causa: 'aparato',
    );

    test('si llegó el video y el aparato no lo mostró, es el aparato (no cuenta contra la señal)', () {
      final falla = Falla.sinArrancar(llegoYNoSeVio);
      expect(falla.motivo, 'aparato');
      expect(falla.detalle, contains('entraron 12, salieron 0'));
      // No se esconde acá: el reproductor ya anotó el decodificador trabado y al volver usa otro
      expect(falla.delAparato, isFalse);
    });

    test('si no llegó nada, es el servidor de la señal', () {
      final falla = Falla.sinArrancar(const Diagnostico(texto: 'no llegó nada del servidor', causa: 'sin_datos'));
      expect(falla.motivo, 'tiempo');
      expect(falla.detalle, startsWith('el servidor de la señal no mandó nada'));
      // Sin diagnóstico (un reproductor viejo), como siempre
      expect(Falla.sinArrancar(null), same(Falla.tiempo));
    });

    test('si el reproductor probó todos sus decodificadores y no pudo, se esconde en este aparato', () {
      final falla = Falla.de(
        PlatformException(
          code: 'VideoError',
          message:
              'Video player had error KAIROS_DECODIFICADOR_TRABADO: el decodificador no devolvió imagen · '
              'video h264 1920x1080 · deco c2.android.avc.decoder: entraron 9, salieron 0',
        ),
      );
      expect((falla.motivo, falla.delAparato), ('aparato', true));
      expect(ControlSenal.esconderDespuesDe(falla, hayFuentes: true, seVio: false), isTrue);
    });

    test('sin imagen: si la señal no trae video es la señal; si lo trae, el aparato (y no se esconde)', () {
      final sinVideo = Falla.sinImagenSegun(const Diagnostico(texto: 'sin video · audio aac', causa: 'sin_video'));
      expect((sinVideo.motivo, sinVideo.delAparato), ('formato', false));
      final conVideo = Falla.sinImagenSegun(llegoYNoSeVio);
      expect((conVideo.motivo, conVideo.delAparato), ('aparato', false));
      expect(ControlSenal.esconderDespuesDe(conVideo, hayFuentes: true, seVio: false), isFalse);
    });

    test('el detalle termina con la app, el aparato y su Android, y eso nunca se corta', () {
      final larga = Falla('error', 'x', 'y' * 900);
      final detalle = ControlSenal.detalleDeLaFalla(larga);
      expect(detalle.length, ControlSenal.largoDelDetalle);
      expect(detalle, endsWith(' · [app 1.2.40 · Lenovo TB-X505F · Android 10]'));
    });
  });

  testWidgets('no arranca y el reproductor dice que es el aparato: se avisa así y se prueba la otra señal', (
    tester,
  ) async {
    VideoPlayerPlatform.instance = _VideoDeMentira({_hls: 'cuelga'});
    _elReproductorDice(
      (url) => {
        'texto': 'video h264 1920x1080 · deco OMX.MTK.VIDEO.DECODER.AVC: entraron 8, salieron 0',
        'causa': 'aparato',
      },
    );
    final api = _ApiDePrueba();
    final control = ControlSenal(api);
    unawaited(control.abrir(_canal([_hls, _otra])));

    await _pasar(tester, const Duration(seconds: 16));

    expect(api.fallas, hasLength(1));
    expect(api.fallas.single['motivo'], 'aparato');
    expect(api.fallas.single['detalle'], contains('entraron 8, salieron 0'));
    expect(api.fallas.single['detalle'], endsWith('[app 1.2.40 · Lenovo TB-X505F · Android 10]'));
    // Pasó a la otra señal, que anda
    expect(control.video, isNotNull);
    expect(control.fuente, 1);
    control.dispose();
    await _pasar(tester, const Duration(milliseconds: 300));
  });

  testWidgets('si el reproductor está cambiando de decodificador, la app lo espera un rato más', (tester) async {
    final video = VideoPlayerPlatform.instance = _VideoDeMentira({_hls: 'tarda'});
    _elReproductorDice((url) => {'texto': 'cambió de decodificador 1 vez', 'causa': 'cambiando', 'cambiando': true});
    final api = _ApiDePrueba();
    final control = ControlSenal(api);
    unawaited(control.abrir(_canal([_hls, _otra])));

    await _pasar(tester, const Duration(seconds: 27));

    // Arrancó con el otro decodificador: sin falla y con la misma señal (no abrió la otra)
    expect(api.fallas, isEmpty);
    expect(control.error, isNull);
    expect(control.video, isNotNull);
    expect(control.fuente, 0);
    expect(video.abiertas, [_hls]);
    control.dispose();
    await _pasar(tester, const Duration(milliseconds: 300));
  });

  testWidgets('mientras conecta un canal con varias señales, dice cuál está probando', (tester) async {
    VideoPlayerPlatform.instance = _VideoDeMentira({_hls: 'cuelga', _otra: 'cuelga'});
    final control = ControlSenal(_ApiDePrueba());
    unawaited(control.abrir(_canal([_hls, _otra])));

    await _pasar(tester, const Duration(seconds: 1));
    expect(control.avisoDeConexion, 'Conectando…');
    await _pasar(tester, const Duration(seconds: 15));
    expect(control.avisoDeConexion, 'La señal anterior no respondió. Probando la 2 de 2…');
    // Un canal con una sola señal: nada (la ruedita alcanza)
    unawaited(control.abrir(_canal([_hls])));
    await _pasar(tester, const Duration(seconds: 1));
    expect(control.avisoDeConexion, isNull);
    control.dispose();
    // Las esperas de las señales que se dejaron (vencen solas, sin efecto)
    await _pasar(tester, const Duration(seconds: 16));
  });
}
