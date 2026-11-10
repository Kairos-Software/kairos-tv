import 'package:app_movil/api/cliente.dart';
import 'package:app_movil/api/modelos.dart';
import 'package:app_movil/aparato.dart';
import 'package:app_movil/movil/busqueda.dart';
import 'package:app_movil/movil/buscar.dart';
import 'package:app_movil/movil/datos.dart';
import 'package:app_movil/movil/estructura.dart';
import 'package:app_movil/tv/estructura.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

Canal _canal(int id, String nombre, String contenido) =>
    Canal({'id': id, 'nombre': nombre, 'fuentes': <dynamic>[]}, categoria: 'Varios', contenido: contenido);

/// Un catálogo donde "casa" aparece en un canal, en películas y en una serie.
Catalogo _catalogo() => Catalogo(ApiCliente(urlBase: 'http://prueba/api/v1/'))
  ..categoriasEnVivo = [
    CategoriaCanales({
      'nombre': 'Varios',
      'canales': [
        {'id': 1, 'nombre': 'Casa Club TV', 'numero': '15'},
        {'id': 2, 'nombre': 'Noticias 24', 'numero': '16'},
      ],
    }),
  ]
  ..peliculas = [
    _canal(10, 'Una casa en la playa (2020)', 'pelicula'),
    _canal(11, 'Casablanca (1942)', 'pelicula'),
    _canal(12, 'Mi pobre angelito (1990)', 'pelicula'),
  ]
  ..series = agruparSeries([for (var e = 1; e <= 3; e++) _canal(100 + e, 'La casa de papel S01 E0$e', 'serie')])
  ..cargado = true;

String? _enfocado() =>
    FocusManager.instance.primaryFocus?.context?.findAncestorWidgetOfExactType<Semantics>()?.properties.label;

void main() {
  test('primero lo que empieza con lo escrito, sin tildes ni mayúsculas', () {
    final encontrado = buscarEnCatalogo(_catalogo(), 'CASÁ');
    // "Casablanca" empieza con "casa"; "Una casa..." tiene una palabra que empieza así: las dos van
    expect(encontrado.peliculas.map((p) => p.nombre), ['Una casa en la playa (2020)', 'Casablanca (1942)']);
    expect(encontrado.series.single.nombre, 'La casa de papel');
    expect(encontrado.canales.single.nombre, 'Casa Club TV');
    expect(encontrado.cuantos(QueBuscar.todo), 4);
    expect(encontrado.cuantos(QueBuscar.series), 1);

    // Lo que solo CONTIENE las letras va después de lo que empieza con ellas
    final angel = buscarEnCatalogo(_catalogo(), 'gel');
    expect(angel.peliculas.single.nombre, 'Mi pobre angelito (1990)');

    // En la TV, el número del canal también lo encuentra
    expect(buscarEnCatalogo(_catalogo(), '16', conNumeros: true).canales.single.nombre, 'Noticias 24');
    expect(buscarEnCatalogo(_catalogo(), '16').canales, isEmpty);
    expect(sinTildes('Notícias Ñandú'), 'noticias nandu');
  });

  testWidgets('celular: buscar desde Series muestra solo series, y "Todo" muestra el resto', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: DatosScope(
          catalogo: _catalogo(),
          biblioteca: Biblioteca(),
          child: PantallaBuscar(irA: (_, {categoria, canal}) {}, que: PantallaBuscar.queDesde(Seccion.series)),
        ),
      ),
    );
    await tester.enterText(find.byType(TextField), 'casa');
    await tester.pump();
    expect(find.text('Series (1)'), findsOneWidget);
    expect(find.text('La casa de papel'), findsOneWidget);
    expect(find.text('Casa Club TV'), findsNothing);
    expect(find.text('Canales en vivo'), findsNothing);

    await tester.tap(find.text('Todo (4)'));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Casa Club TV'), findsOneWidget);
  });

  testWidgets('TV: desde Series busca series, y DERECHA lleva del teclado a los resultados', (tester) async {
    tester.view.physicalSize = const Size(1920, 1080);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      MaterialApp(
        home: PantallaTv(catalogo: _catalogo(), biblioteca: Biblioteca(), seccionInicial: SeccionTv.series),
      ),
    );
    await tester.pumpAndSettle();
    // El botón "Buscar" de Series
    Focus.of(tester.element(find.text('Buscar').first)).requestFocus();
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.select);
    await tester.pumpAndSettle();
    expect(_enfocado(), 'A'); // el foco arranca en la "A"

    // "CASA" con el teclado de la pantalla: C (2 a la derecha), OK, A, S, A...
    Future<void> tecla(LogicalKeyboardKey tecla) async {
      await tester.sendKeyEvent(tecla);
      await tester.pumpAndSettle();
    }

    Future<void> escribir(String letra) async {
      Focus.of(tester.element(find.text(letra).first)).requestFocus();
      await tester.pumpAndSettle();
      await tecla(LogicalKeyboardKey.select);
    }

    for (final letra in ['C', 'A', 'S', 'A']) {
      await escribir(letra);
    }
    expect(find.text('casa'), findsOneWidget);
    // Solo la serie (se venía de Series); los otros tipos dicen cuántos hay
    expect(find.text('La casa de papel'), findsOneWidget);
    expect(find.text('Casablanca'), findsNothing);
    expect(find.text('Películas (2)'), findsOneWidget);
    expect(find.text('Con la flecha DERECHA ▶ vas a los resultados.'), findsOneWidget);

    // Desde la "A" (lejos del borde), DERECHA las veces que haga falta llega a los resultados
    for (var i = 0; i < 12 && _enfocado() != 'La casa de papel, Serie · 3 capítulos'; i++) {
      await tecla(LogicalKeyboardKey.arrowRight);
    }
    expect(_enfocado(), 'La casa de papel, Serie · 3 capítulos');

    // IZQUIERDA vuelve al teclado (no abre el menú)
    await tecla(LogicalKeyboardKey.arrowLeft);
    expect(FocusManager.instance.primaryFocus?.debugLabel, isNot(startsWith('menú')));
    expect(_enfocado()?.length, 1); // una tecla
  });

  testWidgets('PC: se escribe con el teclado de verdad y Enter va a los resultados', (tester) async {
    // Antes, Enter apretaba la tecla de la pantalla con el foco (la "A") y escribía una "a"
    Aparato.esPc = true;
    Aparato.esTv = true;
    addTearDown(() {
      Aparato.esPc = false;
      Aparato.esTv = false;
    });
    tester.view.physicalSize = const Size(1920, 1080);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      MaterialApp(
        home: PantallaTv(catalogo: _catalogo(), biblioteca: Biblioteca(), seccionInicial: SeccionTv.buscar),
      ),
    );
    await tester.pumpAndSettle();
    expect(_enfocado(), 'A');

    for (final tecla in [LogicalKeyboardKey.keyC, LogicalKeyboardKey.keyA, LogicalKeyboardKey.keyS]) {
      await tester.sendKeyEvent(tecla);
      await tester.pump();
    }
    await tester.sendKeyEvent(LogicalKeyboardKey.space); // en la PC la barra espaciadora escribe (no es "OK")
    await tester.pumpAndSettle();
    expect(find.text('cas '), findsOneWidget);

    await tester.sendKeyEvent(LogicalKeyboardKey.backspace);
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(find.text('cas'), findsOneWidget); // no escribió nada más
    expect(_enfocado(), isNot('A')); // está en el primer resultado
    expect(_enfocado()?.length, greaterThan(1));
  });
}
