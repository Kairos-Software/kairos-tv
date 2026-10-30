// La sesión del cliente no se pierde porque el servidor liberó su pantalla.
//
// Si un aparato pasa más de 2 horas sin dar señales (la TV apagada, la app en
// segundo plano), el servidor libera su pantalla y su token deja de valer. Al
// volver (al abrir la app, o después de actualizarla), la app mandaba al login
// y borraba el catálogo guardado. Ahora vuelve a entrar sola con el último
// código; solo si el servidor no la deja, va al login y dice por qué.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:app_movil/acceso.dart';
import 'package:app_movil/aparato.dart';
import 'package:app_movil/movil/copia_catalogo.dart';
import 'package:app_movil/sesion.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _codigo = '48219037';
final _cliente = {'nombre': 'Ana', 'codigo': '4821 9037', 'pantallas': 1, 'conectados': 1};

/// El servidor de mentira: el token viejo ya no vale, y entrar con el código
/// responde [alEntrar] (por defecto, entra y da un token nuevo).
class _Servidor {
  _Servidor({this.alEntrar});

  final http.Response Function()? alEntrar;

  /// Si está, "canales/" no contesta hasta que se complete (una respuesta que llega tarde).
  Completer<void>? retener;

  /// Lo que pidió la app, en orden: "GET cliente/ (c_viejo)", "POST cliente/login/ (sin token)".
  final pedidos = <String>[];

  http.Response _json(Object datos, int status) =>
      http.Response(jsonEncode(datos), status, headers: {'content-type': 'application/json; charset=utf-8'});

  /// Como un cliente HTTP de verdad, la respuesta lleva el pedido (con qué token se hizo).
  Future<http.Response> responder(http.Request pedido) async {
    final respuesta = await _responder(pedido);
    return http.Response.bytes(respuesta.bodyBytes, respuesta.statusCode, headers: respuesta.headers, request: pedido);
  }

  Future<http.Response> _responder(http.Request pedido) async {
    final token = pedido.headers['Authorization']?.replaceFirst('Bearer ', '');
    final ruta = pedido.url.path.split('/api/v1/').last;
    pedidos.add('${pedido.method} $ruta (${token ?? 'sin token'})');
    if (ruta == 'cliente/login/') {
      // Con un token que ya no vale, el servidor rechaza también el login
      if (token != null) return _json({'codigo': 'no_autenticado', 'detalle': 'Token inválido.'}, 401);
      return alEntrar?.call() ?? _json({'token': 'c_nuevo', 'cliente': _cliente}, 200);
    }
    if (ruta == 'canales/') await retener?.future;
    if (token == 'c_nuevo') return _json(_cliente, 200);
    return _json({'codigo': 'no_autenticado', 'detalle': 'Token inválido.'}, 401);
  }
}

/// Una sesión que habla con [servidor], con un token viejo y el último código guardados.
Sesion _sesion(_Servidor servidor, {String token = 'c_viejo'}) {
  FlutterSecureStorage.setMockInitialValues({'token': token, 'ultimo_codigo': _codigo});
  return http.runWithClient(() => Sesion()..api, () => MockClient(servidor.responder));
}

Future<String?> _tokenGuardado() => const FlutterSecureStorage().read(key: 'token');

/// Espera (hasta 2 s) a que pase algo que la app hace por detrás.
Future<void> _esperar(bool Function() condicion) async {
  for (var i = 0; i < 100 && !condicion(); i++) {
    await Future<void>.delayed(const Duration(milliseconds: 20));
  }
}

void main() {
  late Directory carpeta;
  late File catalogoGuardado;

  setUp(() {
    carpeta = Directory.systemTemp.createTempSync('sesion_test');
    CopiaCatalogo.carpetaDePrueba = carpeta;
    catalogoGuardado = File('${carpeta.path}/servidor/vivo.json')
      ..createSync(recursive: true)
      ..writeAsStringSync('{}');
  });

  tearDown(() {
    CopiaCatalogo.carpetaDePrueba = null;
    if (carpeta.existsSync()) carpeta.deleteSync(recursive: true);
  });

  test('al abrir la app con la pantalla liberada, vuelve a entrar sola y no borra el catálogo', () async {
    final servidor = _Servidor();
    final sesion = _sesion(servidor);
    addTearDown(sesion.dispose);

    await sesion.iniciar();

    expect(sesion.estado, EstadoSesion.conSesion);
    expect(servidor.pedidos, ['GET cliente/ (c_viejo)', 'POST cliente/login/ (sin token)']);
    expect(await _tokenGuardado(), 'c_nuevo');
    expect(sesion.cuenta, 'c$_codigo', reason: 'los favoritos y "Continuar viendo" siguen siendo los suyos');
    await Future<void>.delayed(Duration.zero);
    expect(catalogoGuardado.existsSync(), isTrue, reason: 'el catálogo guardado no se vuelve a bajar entero');
  });

  test('si el servidor no la deja entrar (cuenta en uso), va al login y dice por qué', () async {
    final servidor = _Servidor(
      alEntrar: () => http.Response(
        jsonEncode({'codigo': 'cuenta_en_uso', 'detalle': 'Tu cuenta ya se está usando en 1 dispositivo(s).'}),
        403,
        headers: {'content-type': 'application/json; charset=utf-8'},
      ),
    );
    final sesion = _sesion(servidor);
    addTearDown(sesion.dispose);

    await sesion.iniciar();

    expect(sesion.estado, EstadoSesion.sinSesion);
    expect(sesion.avisoParaElLogin?.codigo, 'cuenta_en_uso');
    expect(sesion.ultimoCodigo, _codigo, reason: 'el login lo muestra ya escrito');
    expect(await _tokenGuardado(), isNull);
    await _esperar(() => !catalogoGuardado.existsSync());
    expect(catalogoGuardado.existsSync(), isFalse);
  });

  test('sin conexión al volver a entrar: no cierra la sesión, y "Reintentar" prueba el código', () async {
    var hayConexion = false;
    final servidor = _Servidor(
      alEntrar: () => hayConexion
          ? http.Response(
              jsonEncode({'token': 'c_nuevo', 'cliente': _cliente}),
              200,
              headers: {'content-type': 'application/json; charset=utf-8'},
            )
          : throw const SocketException('sin red'),
    );
    final sesion = _sesion(servidor);
    addTearDown(sesion.dispose);

    await sesion.iniciar();
    expect(sesion.estado, EstadoSesion.sinConexion);

    hayConexion = true;
    await sesion.reintentar();
    expect(sesion.estado, EstadoSesion.conSesion);
    expect(await _tokenGuardado(), 'c_nuevo');
  });

  test('mirando: si fallan varios pedidos juntos (volvió de horas en segundo plano), entra una sola vez', () async {
    final servidor = _Servidor();
    final sesion = _sesion(servidor, token: 'c_nuevo');
    addTearDown(sesion.dispose);
    await sesion.iniciar();
    expect(sesion.estado, EstadoSesion.conSesion);

    // El servidor liberó la pantalla mientras la app estaba en segundo plano.
    // Al volver salen varios pedidos con el token viejo; uno contesta tarde,
    // cuando la app ya volvió a entrar.
    sesion.api.token = 'c_viejo';
    servidor.pedidos.clear();
    servidor.retener = Completer<void>();
    final estados = <EstadoSesion>[];
    sesion.addListener(() => estados.add(sesion.estado));
    final pedidos = [
      for (final ruta in ['cliente/', 'cliente/', 'canales/'])
        sesion.api.get(ruta).then<Object?>((r) => r, onError: (_) => null),
    ];
    await _esperar(() => sesion.api.token == 'c_nuevo');
    expect(sesion.api.token, 'c_nuevo');
    servidor.retener!.complete();
    await Future.wait(pedidos);
    await pumpEventQueue();

    expect(servidor.pedidos.where((p) => p.startsWith('POST cliente/login/')), hasLength(1));
    expect(estados, isNot(contains(EstadoSesion.sinSesion)), reason: 'nunca pasa por el login');
    expect(sesion.estado, EstadoSesion.conSesion);
    expect(sesion.api.token, 'c_nuevo');
  });

  test('"Cerrar sesión" sí la cierra: no vuelve a entrar sola', () async {
    final servidor = _Servidor();
    final sesion = _sesion(servidor, token: 'c_nuevo');
    addTearDown(sesion.dispose);
    await sesion.iniciar();
    servidor.pedidos.clear();

    await sesion.salir();

    expect(sesion.estado, EstadoSesion.sinSesion);
    expect(servidor.pedidos.where((p) => p.startsWith('POST cliente/login/')), isEmpty);
    expect(await _tokenGuardado(), isNull);
  });

  group('el login en la TV', () {
    setUp(() => Aparato.esTv = true);
    tearDown(() => Aparato.esTv = false);

    testWidgets('si el ingreso falla, el control sigue escribiendo los números', (tester) async {
      tester.view.physicalSize = const Size(1920, 1080);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final servidor = _Servidor(
        alEntrar: () => http.Response(
          jsonEncode({'codigo': 'codigo_invalido', 'detalle': 'El código no es correcto.'}),
          400,
          headers: {'content-type': 'application/json; charset=utf-8'},
        ),
      );
      final sesion = _sesion(servidor);
      addTearDown(sesion.dispose);
      sesion.ultimoCodigo = _codigo;
      await tester.pumpWidget(
        SesionScope(
          sesion: sesion,
          child: const MaterialApp(home: Scaffold(body: PantallaAcceso())),
        ),
      );
      await tester.pumpAndSettle();
      sesion.api.token = null;

      // Del "1" (donde arranca el foco) al OK, y OK
      for (final tecla in [
        LogicalKeyboardKey.arrowDown,
        LogicalKeyboardKey.arrowDown,
        LogicalKeyboardKey.arrowDown,
        LogicalKeyboardKey.arrowRight,
        LogicalKeyboardKey.arrowRight,
        LogicalKeyboardKey.select,
      ]) {
        await tester.sendKeyEvent(tecla);
        await tester.pump();
      }
      await tester.pumpAndSettle();
      expect(find.text('Código incorrecto'), findsOneWidget);

      // Borrar con el control y escribir otro número
      await tester.sendKeyEvent(LogicalKeyboardKey.backspace);
      await tester.sendKeyEvent(LogicalKeyboardKey.digit5);
      await tester.pumpAndSettle();
      expect(find.text('4821  9035'), findsOneWidget);
    });
  });
}
