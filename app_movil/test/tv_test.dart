import 'package:app_movil/api/cliente.dart';
import 'package:app_movil/api/modelos.dart';
import 'package:app_movil/movil/datos.dart';
import 'package:app_movil/tv/estructura.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

Canal _pelicula(int id) =>
    Canal({'id': id, 'nombre': 'Película $id', 'fuentes': <dynamic>[]}, categoria: 'Acción', contenido: 'pelicula');

/// La TV con un catálogo ya cargado (sin servidor), parada en [seccion].
Future<void> _abrirTv(
  WidgetTester tester,
  SeccionTv seccion, {
  Duration esperaReposo = const Duration(minutes: 3),
  List<CategoriaCanales> enVivo = const [],
}) async {
  tester.view.physicalSize = const Size(1920, 1080);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final catalogo = Catalogo(ApiCliente(urlBase: 'http://prueba/api/v1/'))
    ..peliculas = [for (var i = 1; i <= 10; i++) _pelicula(i)]
    ..categoriasEnVivo = enVivo
    ..cargado = true;
  await tester.pumpWidget(
    MaterialApp(
      home: PantallaTv(
        catalogo: catalogo,
        biblioteca: Biblioteca(),
        seccionInicial: seccion,
        esperaReposo: esperaReposo,
      ),
    ),
  );
  await tester.pumpAndSettle();
}

/// El foco fuera del contenido y del menú, en la pantalla en general (lo que pasa al abrir la app).
Future<void> _focoAfuera(WidgetTester tester) async {
  FocusScope.of(tester.element(find.byType(PantallaTv))).requestScopeFocus();
  await tester.pumpAndSettle();
}

String? _enfocado() => FocusManager.instance.primaryFocus?.debugLabel;

Future<void> _tecla(WidgetTester tester, LogicalKeyboardKey tecla) async {
  await tester.sendKeyEvent(tecla);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('con el control: Izquierda abre el menú, Abajo + OK cambia de sección', (tester) async {
    await _abrirTv(tester, SeccionTv.peliculas);
    expect(find.text('Series'), findsNothing); // menú cerrado: solo íconos

    // La primera película está en el borde izquierdo: Izquierda abre el menú en "Películas"
    await _tecla(tester, LogicalKeyboardKey.arrowLeft);
    expect(_enfocado(), 'menú: peliculas');
    expect(find.text('Series'), findsOneWidget); // abierto: con los nombres

    // Abajo pasa a "Series" y OK la abre (el menú se cierra)
    await _tecla(tester, LogicalKeyboardKey.arrowDown);
    expect(_enfocado(), 'menú: series');
    await _tecla(tester, LogicalKeyboardKey.select);
    expect(find.text('Todavía no hay series.'), findsOneWidget);
    expect(_enfocado(), isNot(startsWith('menú')));

    // En Series (vacía) el foco está en "Buscar": Izquierda, las veces que haga falta, llega al menú
    for (var i = 0; i < 4 && _enfocado() != 'menú: series'; i++) {
      await _tecla(tester, LogicalKeyboardKey.arrowLeft);
    }
    expect(_enfocado(), 'menú: series');
    // Arriba + OK vuelve a Películas y el foco cae en la primera película (no queda "en el aire")
    await _tecla(tester, LogicalKeyboardKey.arrowUp);
    await _tecla(tester, LogicalKeyboardKey.select);
    final foco = FocusManager.instance.primaryFocus;
    expect(foco, isNot(isA<FocusScopeNode>()));
    expect(foco?.context?.findAncestorWidgetOfExactType<Semantics>()?.properties.label, 'Película 1');
  });

  testWidgets('OK en el menú abre la sección y nada más (no "toca" también lo primero)', (tester) async {
    await _abrirTv(tester, SeccionTv.series); // vacía: el foco está en "Buscar"
    for (var i = 0; i < 4 && _enfocado() != 'menú: series'; i++) {
      await _tecla(tester, LogicalKeyboardKey.arrowLeft);
    }
    await _tecla(tester, LogicalKeyboardKey.arrowUp);
    expect(_enfocado(), 'menú: peliculas');
    // Como un control de verdad: el OK se suelta un rato después, cuando la
    // sección nueva ya se dibujó y el foco está en la primera película
    await tester.sendKeyDownEvent(LogicalKeyboardKey.select);
    await tester.pumpAndSettle();
    await tester.sendKeyUpEvent(LogicalKeyboardKey.select);
    await tester.pumpAndSettle();
    final foco = FocusManager.instance.primaryFocus;
    expect(foco?.context?.findAncestorWidgetOfExactType<Semantics>()?.properties.label, 'Película 1');
    expect(find.byType(PantallaTv), findsOneWidget);
    expect(ModalRoute.of(tester.element(find.byType(PantallaTv)))?.isCurrent, isTrue); // no abrió la película
  });

  testWidgets('si el foco quedó afuera, el control lo recupera (nunca queda "muerto")', (tester) async {
    await _abrirTv(tester, SeccionTv.series);
    await _focoAfuera(tester);
    await _tecla(tester, LogicalKeyboardKey.arrowLeft);
    expect(_enfocado(), 'menú: series');

    await _focoAfuera(tester);
    await _tecla(tester, LogicalKeyboardKey.arrowDown);
    expect(_enfocado(), isNot(startsWith('menú'))); // no abrió el menú...
    expect(FocusManager.instance.primaryFocus, isNot(isA<FocusScopeNode>())); // ...y quedó en un elemento
  });

  testWidgets('modo reposo: aparece sin tocar el control y cualquier botón vuelve', (tester) async {
    await _abrirTv(tester, SeccionTv.peliculas, esperaReposo: const Duration(seconds: 30));
    await tester.pump(const Duration(seconds: 20));
    await _tecla(tester, LogicalKeyboardKey.arrowRight); // tocar el control reinicia la cuenta
    await tester.pump(const Duration(seconds: 20));
    expect(find.text('Apretá cualquier botón para volver'), findsNothing);

    await tester.pump(const Duration(seconds: 15));
    await tester.pump(const Duration(seconds: 2)); // el fundido de entrada
    expect(find.text('Apretá cualquier botón para volver'), findsOneWidget); // arranca en el logo

    final antes = FocusManager.instance.primaryFocus;
    await _tecla(tester, LogicalKeyboardKey.select); // OK: vuelve y NO abre nada
    expect(find.text('Apretá cualquier botón para volver'), findsNothing);
    expect(find.text('Reproducir'), findsNothing); // no se abrió el detalle de la película
    expect(FocusManager.instance.primaryFocus, isNot(antes)); // el foco volvió a la pantalla de abajo
  });

  testWidgets('guía: de las categorías se pasa a los canales con Derecha', (tester) async {
    CategoriaCanales categoria(String nombre, int desde, int cuantos) => CategoriaCanales({
      'nombre': nombre,
      'canales': [
        for (var i = desde; i < desde + cuantos; i++) {'id': i, 'nombre': '$nombre $i', 'fuentes': <dynamic>[]},
      ],
    });
    await _abrirTv(
      tester,
      SeccionTv.guia,
      enVivo: [categoria('Noticias', 1, 12), categoria('Deportes', 20, 3), categoria('Infantil', 30, 4)],
    );
    expect(_enfocado(), startsWith('Canal 1,')); // arranca en el primer canal

    // Izquierda: a las categorías. Abajo hasta "Infantil" y OK la elige
    await _tecla(tester, LogicalKeyboardKey.arrowLeft);
    expect(_enfocado(), isNot(startsWith('Canal')));
    for (var i = 0; i < 6 && _enfocado() != 'Infantil'; i++) {
      await _tecla(tester, LogicalKeyboardKey.arrowDown);
    }
    expect(_enfocado(), 'Infantil');
    await _tecla(tester, LogicalKeyboardKey.select);
    expect(find.text('4 canales'), findsOneWidget);

    // Derecha: al primer canal de esa categoría
    await _tecla(tester, LogicalKeyboardKey.arrowRight);
    expect(_enfocado(), contains('Infantil 30'));
    await _tecla(tester, LogicalKeyboardKey.arrowDown);
    expect(_enfocado(), contains('Infantil 31'));

    // Izquierda vuelve a la categoría elegida (no a la que está a la misma altura) y Derecha, al mismo canal
    await _tecla(tester, LogicalKeyboardKey.arrowLeft);
    expect(_enfocado(), 'Infantil');
    await _tecla(tester, LogicalKeyboardKey.arrowRight);
    expect(_enfocado(), contains('Infantil 31'));

    // En "Todos", Derecha lleva al canal elegido aunque esté lejos en la lista (todavía sin dibujar)
    await _tecla(tester, LogicalKeyboardKey.arrowLeft);
    for (var i = 0; i < 6 && _enfocado() != 'Todos'; i++) {
      await _tecla(tester, LogicalKeyboardKey.arrowUp);
    }
    await _tecla(tester, LogicalKeyboardKey.select);
    await _tecla(tester, LogicalKeyboardKey.arrowRight);
    expect(_enfocado(), contains('Noticias 1'));
    for (var i = 0; i < 16; i++) {
      await _tecla(tester, LogicalKeyboardKey.arrowDown);
    }
    expect(_enfocado(), contains('Infantil 31'));
    await _tecla(tester, LogicalKeyboardKey.arrowLeft);
    expect(_enfocado(), 'Todos');
    await _tecla(tester, LogicalKeyboardKey.arrowRight);
    expect(_enfocado(), contains('Infantil 31'));
  });

  testWidgets('desde el menú, Derecha o Atrás vuelven al contenido', (tester) async {
    await _abrirTv(tester, SeccionTv.peliculas);
    await _tecla(tester, LogicalKeyboardKey.arrowRight); // segunda película
    await _tecla(tester, LogicalKeyboardKey.arrowLeft); // primera: todavía no abre el menú
    expect(_enfocado(), isNot(startsWith('menú')));

    await _tecla(tester, LogicalKeyboardKey.arrowLeft);
    expect(_enfocado(), 'menú: peliculas');
    await _tecla(tester, LogicalKeyboardKey.arrowRight);
    expect(_enfocado(), isNot(startsWith('menú')));
    expect(find.text('Series'), findsNothing);

    await _tecla(tester, LogicalKeyboardKey.arrowLeft);
    expect(_enfocado(), 'menú: peliculas');
    await tester.binding.handlePopRoute(); // el botón "Atrás" del control
    await tester.pumpAndSettle();
    expect(_enfocado(), isNot(startsWith('menú')));
    expect(find.text('Series'), findsNothing);
    expect(find.text('Películas'), findsWidgets); // sigue en Películas, no volvió a Inicio
  });
}
