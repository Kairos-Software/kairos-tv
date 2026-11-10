// La app de PC (Windows): lo que cambia con el teclado y el mouse respecto de la tele (lib/pc.dart y lo que
// pregunta por Aparato.esPc). El video es "de mentira", como en reproductor_tv_test.dart.
import 'dart:async';
import 'dart:convert';

import 'package:app_movil/acceso.dart';
import 'package:app_movil/api/modelos.dart';
import 'package:app_movil/aparato.dart';
import 'package:app_movil/movil/datos.dart';
import 'package:app_movil/pc.dart';
import 'package:app_movil/sesion.dart';
import 'package:app_movil/tv/escala.dart';
import 'package:app_movil/tv/foco.dart';
import 'package:app_movil/tv/reproductor.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:video_player_platform_interface/video_player_platform_interface.dart';

class _VideoDeMentira extends VideoPlayerPlatform {
  var _proximo = 0;
  final _eventos = <int, StreamController<VideoEvent>>{};

  /// Cuántas veces se pausó (la barra espaciadora).
  var pausas = 0;

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
  Future<void> play(int playerId) async {
    // Como el de verdad: avisa que está reproduciendo (si no, la pausa no tendría qué pausar)
    _eventos[playerId]?.add(VideoEvent(eventType: VideoEventType.isPlayingStateUpdate, isPlaying: true));
  }

  @override
  Future<void> pause(int playerId) async => pausas++;

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

Canal _canal(int id, String nombre) => Canal({
  'id': id,
  'nombre': nombre,
  'fuentes': [
    {'id': id, 'url': 'https://x/$id.m3u8', 'tipo': 'hls', 'codec': 'h264'},
  ],
}, categoria: 'Noticias');

final _canales = [_canal(1, 'Canal 26'), _canal(2, 'Telemax')];

late _VideoDeMentira _video;

/// Como en la PC: la app de la tele, en una pantalla Full HD.
void _comoEnLaPc(WidgetTester tester) {
  Aparato.esPc = true;
  Aparato.esTv = true;
  addTearDown(() {
    Aparato.esPc = false;
    Aparato.esTv = false;
  });
  tester.view.physicalSize = const Size(1920, 1080);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
}

/// Unos cuadros (300 ms), sin dejar correr el reloj de más (los carteles se esconden solos).
Future<void> _pasar(WidgetTester tester) async {
  for (var i = 0; i < 3; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}

String? _enfocado() => FocusManager.instance.primaryFocus?.debugLabel;

Future<void> _abrirReproductor(WidgetTester tester, Widget reproductor) async {
  SharedPreferences.setMockInitialValues({});
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

/// El mouse, en la pantalla, sin apretar nada.
Future<TestGesture> _mouse(WidgetTester tester, Offset donde) async {
  final mouse = await tester.createGesture(kind: PointerDeviceKind.mouse);
  await mouse.addPointer(location: donde);
  addTearDown(mouse.removePointer);
  return mouse;
}

/// Un servidor que anota lo que se manda al entrar y contesta que no (así el login queda a la vista).
class _ServidorDelLogin {
  final enviados = <String, Map<String, dynamic>>{};

  Future<http.Response> responder(http.Request pedido) async {
    final ruta = pedido.url.path.split('/api/v1/').last;
    if (pedido.method == 'POST') enviados[ruta] = jsonDecode(pedido.body) as Map<String, dynamic>;
    return http.Response.bytes(
      utf8.encode(jsonEncode({'codigo': 'codigo_invalido', 'detalle': 'No.'})),
      400,
      headers: {'content-type': 'application/json; charset=utf-8'},
      request: pedido,
    );
  }
}

Future<_ServidorDelLogin> _abrirLogin(WidgetTester tester) async {
  FlutterSecureStorage.setMockInitialValues({});
  final servidor = _ServidorDelLogin();
  final sesion = http.runWithClient(() => Sesion()..api, () => MockClient(servidor.responder));
  addTearDown(sesion.dispose);
  await tester.pumpWidget(
    SesionScope(
      sesion: sesion,
      child: const MaterialApp(home: Scaffold(body: PantallaAcceso())),
    ),
  );
  await tester.pumpAndSettle();
  return servidor;
}

Future<void> _escribir(WidgetTester tester, List<LogicalKeyboardKey> teclas) async {
  for (final tecla in teclas) {
    await tester.sendKeyEvent(tecla);
    await tester.pump();
  }
}

void main() {
  group('el login con el teclado de la PC', () {
    testWidgets('el código se escribe con el teclado y Enter entra (no aprieta la tecla elegida)', (tester) async {
      _comoEnLaPc(tester);
      final servidor = await _abrirLogin(tester);
      expect(_enfocado(), 'teclado del código'); // como en la tele, el foco arranca en el "1" de la pantalla

      await _escribir(tester, [
        for (final n in [4, 8, 2, 1, 9, 0, 3, 7]) LogicalKeyboardKey(LogicalKeyboardKey.digit0.keyId + n),
      ]);
      await _escribir(tester, [LogicalKeyboardKey.enter]);
      await tester.pumpAndSettle();

      expect(servidor.enviados['cliente/login/']?['codigo'], '48219037');
      expect(find.text('1___  ____'), findsNothing); // antes, Enter apretaba el "1" y empezaba otro código
    });

    testWidgets('usuario y contraseña: Enter pasa a la contraseña y después entra; el espacio escribe', (tester) async {
      _comoEnLaPc(tester);
      final servidor = await _abrirLogin(tester);
      await tester.tap(find.text('Ingresar como revendedor o administrador'));
      await tester.pumpAndSettle();

      await _escribir(tester, [LogicalKeyboardKey.keyA, LogicalKeyboardKey.keyN, LogicalKeyboardKey.keyA]);
      await _escribir(tester, [LogicalKeyboardKey.enter]); // antes escribía una "q" (la tecla con el foco)
      await _escribir(tester, [LogicalKeyboardKey.keyX, LogicalKeyboardKey.space, LogicalKeyboardKey.keyY]);
      await _escribir(tester, [LogicalKeyboardKey.enter]);
      await tester.pumpAndSettle();

      expect(servidor.enviados['login/'], allOf(containsPair('username', 'ana'), containsPair('password', 'x y')));
    });

    testWidgets('Tab pasa de un campo al otro', (tester) async {
      _comoEnLaPc(tester);
      final servidor = await _abrirLogin(tester);
      await tester.tap(find.text('Ingresar como revendedor o administrador'));
      await tester.pumpAndSettle();

      await _escribir(tester, [LogicalKeyboardKey.tab, LogicalKeyboardKey.keyZ]); // en la contraseña
      await _escribir(tester, [LogicalKeyboardKey.tab, LogicalKeyboardKey.keyB]); // de vuelta en el usuario
      await _escribir(tester, [LogicalKeyboardKey.tab, LogicalKeyboardKey.enter]);
      await tester.pumpAndSettle();

      expect(servidor.enviados['login/'], allOf(containsPair('username', 'b'), containsPair('password', 'z')));
    });
  });

  group('el mouse', () {
    testWidgets('lo que se señala queda elegido; clic es OK y clic derecho, OK largo', (tester) async {
      _comoEnLaPc(tester);
      final hecho = <String>[];
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Row(
              children: [
                BotonTv(texto: 'Uno', alOk: () => hecho.add('uno'), autofocus: true),
                Enfocable(
                  etiqueta: 'Dos',
                  alOk: () => hecho.add('dos'),
                  alOkLargo: () => hecho.add('dos largo'),
                  child: const SizedBox(width: 200, height: 100, child: Text('Dos')),
                ),
              ],
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(_enfocado(), 'Uno');

      final mouse = await _mouse(tester, Offset.zero);
      await mouse.moveTo(tester.getCenter(find.text('Dos')));
      await tester.pumpAndSettle();
      expect(_enfocado(), 'Dos');

      await tester.tap(find.text('Dos'), kind: PointerDeviceKind.mouse);
      await tester.tap(find.text('Dos'), kind: PointerDeviceKind.mouse, buttons: kSecondaryButton);
      await tester.pumpAndSettle();
      expect(hecho, ['dos', 'dos largo']);
    });
  });

  group('el reproductor en la PC', () {
    setUp(() => Ventana.pantallaCompleta.value = false);

    testWidgets('película: pantalla completa mientras se mira; el mouse muestra la barra y Salir sale', (tester) async {
      _comoEnLaPc(tester);
      await _abrirReproductor(tester, ReproductorVodTv(canal: _canal(9, 'Matrix (1999)')));
      expect(Ventana.pantallaCompleta.value, isTrue);
      expect(find.text('Pausa'), findsNothing); // la barra todavía no

      final mouse = await _mouse(tester, const Offset(900, 500));
      await mouse.moveTo(const Offset(960, 540));
      await _pasar(tester);
      expect(find.text('Pausa'), findsOneWidget); // apareció la barra, con el foco en Pausa
      expect(find.byIcon(Icons.close_rounded), findsOneWidget); // y arriba, Salir

      await tester.tap(find.byIcon(Icons.close_rounded), kind: PointerDeviceKind.mouse);
      await tester.pumpAndSettle(); // que termine de cerrarse
      expect(find.text('abrir'), findsOneWidget); // salió de una (no solo escondió la barra)
      expect(Ventana.pantallaCompleta.value, isFalse); // y la ventana volvió a como estaba
    });

    testWidgets('película: la barra espaciadora pausa; con el mouse quieto la barra se esconde', (tester) async {
      _comoEnLaPc(tester);
      await _abrirReproductor(tester, ReproductorVodTv(canal: _canal(9, 'Matrix (1999)')));
      final antes = _video.pausas; // video_player también pausa al prepararse
      await _escribir(tester, [LogicalKeyboardKey.space]);
      await _pasar(tester);
      expect(_video.pausas, antes + 1);

      await _escribir(tester, [LogicalKeyboardKey.space]); // sigue: la barra se esconde sola al reproducir
      final mouse = await _mouse(tester, const Offset(900, 500));
      await mouse.moveTo(const Offset(960, 540));
      await _pasar(tester);
      expect(find.byIcon(Icons.close_rounded), findsOneWidget);
      await tester.pump(const Duration(seconds: 6));
      await _pasar(tester);
      expect(_enfocado(), 'reproductor'); // la barra se fue y el foco volvió al reproductor
    });

    testWidgets('en vivo: el mouse abre las opciones y el clic en el video las cierra', (tester) async {
      _comoEnLaPc(tester);
      await _abrirReproductor(tester, ReproductorVivoTv(canal: _canales[0], lista: _canales));
      final mouse = await _mouse(tester, const Offset(900, 500));
      await mouse.moveTo(const Offset(960, 300));
      await _pasar(tester);
      expect(_enfocado(), 'opciones: guía');

      await tester.tapAt(const Offset(960, 300), kind: PointerDeviceKind.mouse);
      await tester.pump(kDoubleTapTimeout + const Duration(milliseconds: 50)); // el clic simple, no doble
      await _pasar(tester);
      expect(_enfocado(), 'reproductor');
    });
  });

  testWidgets('Esc es el "Atrás" del control', (tester) async {
    _comoEnLaPc(tester);
    final navegador = GlobalKey<NavigatorState>();
    await tester.pumpWidget(
      MaterialApp(
        navigatorKey: navegador,
        shortcuts: atajosDePc,
        actions: accionesDePc(navegador),
        home: Builder(
          builder: (context) => TextButton(
            autofocus: true,
            onPressed: () =>
                Navigator.of(context)
                    .push(MaterialPageRoute<void>(builder: (_) => const Scaffold(body: Text('adentro')))),
            child: const Text('entrar'),
          ),
        ),
      ),
    );
    await tester.tap(find.text('entrar'));
    await tester.pumpAndSettle();
    expect(find.text('adentro'), findsOneWidget);

    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    await tester.pumpAndSettle();
    expect(find.text('adentro'), findsNothing);
    expect(find.text('entrar'), findsOneWidget);
  });

  group('el diseño de la tele, en una ventana de PC', () {
    Future<Size> lienzo(WidgetTester tester, Size ventana) async {
      tester.view.physicalSize = ventana;
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      late Size medida;
      await tester.pumpWidget(
        MaterialApp(
          builder: (context, hijo) => EscalaTv(child: hijo!),
          home: Builder(
            builder: (context) {
              medida = MediaQuery.sizeOf(context);
              return const SizedBox.expand();
            },
          ),
        ),
      );
      return medida;
    }

    testWidgets('nunca queda más bajo que el diseño (1080): en una ventana apaisada, más ancho', (tester) async {
      expect(await lienzo(tester, const Size(1280, 720)), const Size(1920, 1080));
      expect(await lienzo(tester, const Size(1920, 1200)), const Size(1920, 1200));
      expect(await lienzo(tester, const Size(2560, 1080)), const Size(2560, 1080));
      expect(await lienzo(tester, const Size(1600, 600)), const Size(2880, 1080));
    });
  });

  test('en la PC no se piden las fuentes que necesitan el navegador de Android', () {
    Aparato.esPc = true;
    addTearDown(() => Aparato.esPc = false);
    expect(FuenteCanal.formatosQueReproduce, isNot(contains('yt_video')));
    expect(FuenteCanal.formatosQueReproduce, isNot(contains('web')));
    expect(FuenteCanal.formatosQueReproduce, containsAll(['hls', 'directo', 'youtube']));
  });

  test('pantalla completa: con dos reproductores seguidos no se sale en el medio', () async {
    Aparato.esPc = true;
    addTearDown(() => Aparato.esPc = false);
    Ventana.pantallaCompleta.value = false;
    Ventana.entrarAlReproductor();
    Ventana.entrarAlReproductor(); // el siguiente se abre antes de que se cierre el anterior
    Ventana.salirDelReproductor();
    await Future<void>.delayed(Duration.zero);
    expect(Ventana.pantallaCompleta.value, isTrue);
    Ventana.salirDelReproductor();
    await Future<void>.delayed(Duration.zero);
    expect(Ventana.pantallaCompleta.value, isFalse);
  });
}
