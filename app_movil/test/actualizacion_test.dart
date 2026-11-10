import 'dart:convert';
import 'dart:io';

import 'package:app_movil/actualizacion.dart';
import 'package:app_movil/aparato.dart';
import 'package:crypto/crypto.dart' as crypto;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

/// Como el inicio de la TV: carga un rato y después su primer canal pide el foco solo (autofocus).
class _InicioQueCarga extends StatefulWidget {
  const _InicioQueCarga({super.key});

  @override
  State<_InicioQueCarga> createState() => _InicioQueCargaState();
}

class _InicioQueCargaState extends State<_InicioQueCarga> {
  bool cargado = false;

  void terminarDeCargar() => setState(() => cargado = true);

  @override
  Widget build(BuildContext context) => cargado
      ? Column(
          children: [
            ElevatedButton(autofocus: true, onPressed: () {}, child: const Text('Canal 1')),
            ElevatedButton(onPressed: () {}, child: const Text('Canal 2')),
          ],
        )
      : const Text('Cargando…');
}

void main() {
  test('compara versiones número por número', () {
    expect(esMasNueva('1.1.0', '1.0.0'), isTrue);
    expect(esMasNueva('1.10.0', '1.9.3'), isTrue); // no alfabético
    expect(esMasNueva('2.0', '1.9.9'), isTrue);
    expect(esMasNueva('1.1.0', '1.1.0'), isFalse);
    expect(esMasNueva('1.0.9', '1.1.0'), isFalse); // la del servidor es más vieja
    expect(esMasNueva('1.1', '1.1.0'), isFalse);
    expect(esMasNueva('1.1.0+3', '1.1.0'), isFalse); // el +N no cuenta
    expect(esMasNueva('', '1.0.0'), isFalse);
  });

  testWidgets('el control remoto no se va del cartel aunque lo de atrás termine de cargar', (tester) async {
    final inicio = GlobalKey<_InicioQueCargaState>();
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: _InicioQueCarga(key: inicio)),
      ),
    );
    showDialog<bool>(
      context: inicio.currentContext!,
      barrierDismissible: false,
      builder: (_) => cartelDeActualizacion(version: '9.9.9'),
    );
    await tester.pumpAndSettle();
    final actualizar = find.widgetWithText(FilledButton, 'Actualizar');
    expect(Focus.of(tester.element(find.text('Actualizar'))).hasPrimaryFocus, isTrue);

    // Atrás termina de cargar y su primer canal pide el foco: antes se lo quedaba
    inicio.currentState!.terminarDeCargar();
    await tester.pumpAndSettle();
    expect(find.text('Canal 1'), findsOneWidget);
    expect(Focus.of(tester.element(find.text('Actualizar'))).hasPrimaryFocus, isTrue);

    // Y las flechas se mueven entre los botones del cartel
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowLeft);
    await tester.pumpAndSettle();
    expect(Focus.of(tester.element(find.text('Más tarde'))).hasPrimaryFocus, isTrue);
    expect(actualizar, findsOneWidget);
  });

  group('PC: el instalador que se baja', () {
    final instalador = utf8.encode('MZ un instalador de mentira');
    late Directory carpeta;

    setUp(() {
      Aparato.esPc = true;
      carpeta = Directory.systemTemp.createTempSync('kairos-actualizacion-');
      Aparato.carpetaTemporal = carpeta.path;
      clienteDeDescarga = () => MockClient((_) async => http.Response.bytes(instalador, 200));
    });
    tearDown(() {
      Aparato.esPc = false;
      Aparato.carpetaTemporal = '';
      clienteDeDescarga = http.Client.new;
      carpeta.deleteSync(recursive: true);
    });

    /// Abre el cartel, toca Actualizar y espera (de verdad: se baja y se escribe un archivo) a que diga [texto].
    Future<void> actualizar(WidgetTester tester, {required String sha256, int? tamanio, required String texto}) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: cartelDeActualizacion(
              version: '2026.11.11.900',
              descarga: 'https://kairos/descargar/pc/3/',
              tamanio: tamanio ?? instalador.length,
              sha256: sha256,
            ),
          ),
        ),
      );
      await tester.tap(find.text('Actualizar'));
      await tester.runAsync(() async {
        for (var i = 0; i < 250 && find.textContaining(texto).evaluate().isEmpty; i++) {
          await Future<void>.delayed(const Duration(milliseconds: 20));
          await tester.pump();
        }
      });
      expect(find.textContaining(texto), findsOneWidget);
    }

    testWidgets('con otra huella no se corre y se borra', (tester) async {
      await actualizar(tester, sha256: 'ab' * 32, texto: 'llegó dañado');
      expect(carpeta.listSync(), isEmpty);
    });

    testWidgets('si no llegó entero no se corre', (tester) async {
      final huella = crypto.sha256.convert(instalador).toString();
      await actualizar(tester, sha256: huella, tamanio: instalador.length + 10, texto: 'se cortó');
    });

    testWidgets('con la huella justa se corre (este de mentira no es un programa: lo avisa)', (tester) async {
      final huella = crypto.sha256.convert(instalador).toString();
      await actualizar(tester, sha256: huella, texto: 'Instalando…');
      // Windows no lo puede abrir (no es un programa de verdad): lo dice, y la app no se cierra
      for (var i = 0; i < 100 && find.textContaining('No se pudo abrir el instalador').evaluate().isEmpty; i++) {
        await tester.pump(const Duration(milliseconds: 100));
        await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 20)));
      }
      expect(find.textContaining('No se pudo abrir el instalador'), findsOneWidget);
      expect(File('${carpeta.path}${Platform.pathSeparator}KairosTV-2026.11.11.900.exe').existsSync(), isTrue);
    });
  });
}
