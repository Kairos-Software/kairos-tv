import 'package:app_movil/api/cliente.dart';
import 'package:app_movil/api/modelos.dart';
import 'package:app_movil/movil/datos.dart';
import 'package:app_movil/movil/estructura.dart';
import 'package:app_movil/movil/portal.dart';
import 'package:app_movil/sesion.dart';
import 'package:app_movil/tv/estructura.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

Map<String, dynamic> _canal(int id, String nombre) => {'id': id, 'nombre': nombre, 'fuentes': <dynamic>[]};

Catalogo _catalogo() => Catalogo(ApiCliente(urlBase: 'http://prueba/api/v1/'))
  ..categoriasEnVivo = [
    CategoriaCanales({
      'nombre': 'Noticias',
      'canales': [_canal(1, 'Noticias 24'), _canal(2, 'Señal Federal'), _canal(3, 'Actualidad')],
    }),
  ]
  ..cargado = true;

String _letrasDelPortal(WidgetTester tester) => tester.widget<PortalCanal>(find.byType(PortalCanal)).letras;

/// Hasta que no quede nada por dibujar (el punto en vivo late siempre: no hay "settle").
Future<void> _esperar(WidgetTester tester) async {
  for (var i = 0; i < 20; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}

void main() {
  test('las letras del portal salen del nombre del canal', () {
    expect(letrasDelPortal('Noticias 24'), 'N24');
    expect(letrasDelPortal('Crónica TV'), 'CT');
    expect(letrasDelPortal('A24'), 'A24');
    expect(letrasDelPortal('Actualidad'), 'ACT');
    expect(letrasDelPortal('  '), '');
  });

  testWidgets('celular: la portada arranca en el primer canal y va pasando por los demás', (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      SesionScope(
        sesion: Sesion(),
        child: MaterialApp(
          home: PantallaMovil(catalogo: _catalogo(), biblioteca: Biblioteca()),
        ),
      ),
    );
    await _esperar(tester);
    expect(_letrasDelPortal(tester), 'N24');

    await tester.pump(const Duration(seconds: 7));
    await tester.pump();
    expect(_letrasDelPortal(tester), 'SF');

    await tester.pumpWidget(const SizedBox());
    await tester.pump(const Duration(seconds: 1));
  });

  testWidgets('TV: el portal sigue al canal enfocado y "Ver en vivo" queda en el primero al abrir', (tester) async {
    tester.view.physicalSize = const Size(1920, 1080);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      SesionScope(
        sesion: Sesion(),
        child: MaterialApp(
          home: PantallaTv(catalogo: _catalogo(), biblioteca: Biblioteca(), seccionInicial: SeccionTv.inicio),
        ),
      ),
    );
    await _esperar(tester);
    expect(_letrasDelPortal(tester), 'N24');
    expect(find.text('Ver en vivo'), findsOneWidget);

    // Abajo: la primera tarjeta (el mismo canal). Derecha: la siguiente, y el portal la acompaña
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
    await _esperar(tester);
    expect(FocusManager.instance.primaryFocus?.debugLabel, contains('Noticias 24'));
    expect(_letrasDelPortal(tester), 'N24');
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await _esperar(tester);
    expect(FocusManager.instance.primaryFocus?.debugLabel, contains('Señal Federal'));
    expect(_letrasDelPortal(tester), 'SF');

    await tester.pumpWidget(const SizedBox());
    await tester.pump(const Duration(seconds: 1));
  });
}
