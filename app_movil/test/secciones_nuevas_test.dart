// Las secciones que se crean en el panel (Música, Radio...): llegan de la API,
// aparecen en el menú de la TV y en los chips de Inicio del celular.
import 'package:app_movil/api/cliente.dart';
import 'package:app_movil/api/modelos.dart';
import 'package:app_movil/movil/busqueda.dart';
import 'package:app_movil/movil/datos.dart';
import 'package:app_movil/movil/estructura.dart';
import 'package:app_movil/sesion.dart';
import 'package:app_movil/tv/estructura.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'servidor_de_prueba.dart';

Map<String, dynamic> _canal(int id, String nombre) => {
  'id': id,
  'nombre': nombre,
  'fuentes': [
    {'id': id, 'url': 'https://x/$id.m3u8', 'tipo': 'hls'},
  ],
};

/// Un servidor de mentira con Música (a demanda), Radio (en vivo) y Deportes (vacía).
class _Servidor extends ApiCliente with CrudoDesdeGet {
  _Servidor({this.viejo = false}) : super(urlBase: 'http://prueba/api/v1/');

  /// Un servidor de antes de las secciones nuevas: no tiene /secciones/.
  final bool viejo;

  @override
  Future<dynamic> get(String ruta, {Map<String, String>? parametros}) async {
    if (ruta == 'canales/secciones/') {
      if (viejo) throw ApiError(status: 404, codigo: 'no_existe', detalle: 'No existe.');
      return {
        'secciones': [
          {'clave': 'musica', 'nombre': 'Música', 'forma': 'pelicula', 'icono': 'musica'},
          {'clave': 'radio', 'nombre': 'Radio', 'forma': 'vivo', 'icono': 'radio'},
          {'clave': 'deportes', 'nombre': 'Deportes', 'forma': 'pelicula', 'icono': 'deportes'},
        ],
      };
    }
    final grupos = switch (parametros?['contenido']) {
      'vivo' => [
        {
          'nombre': 'Noticias',
          'canales': [_canal(1, 'Canal 26')],
        },
      ],
      'musica' => [
        {
          'nombre': 'Shakira',
          'canales': [_canal(10, 'Waka Waka'), _canal(11, 'Hips Don\'t Lie')],
        },
      ],
      'radio' => [
        {
          'nombre': 'AM',
          'canales': [_canal(20, 'Radio Mitre')],
        },
      ],
      _ => <Map<String, dynamic>>[],
    };
    return {'cantidad': 0, 'categorias': grupos};
  }
}

Catalogo _catalogoConSecciones() {
  final catalogo = Catalogo(ApiCliente(urlBase: 'http://prueba/api/v1/'))..cargado = true;
  catalogo.seccionesNuevas = [
    SeccionNueva(clave: 'musica', nombre: 'Música', forma: 'pelicula', icono: 'musica')
      ..categorias = [
        CategoriaCanales({
          'nombre': 'Shakira',
          'canales': [_canal(10, 'Waka Waka')],
        }, contenido: 'pelicula'),
      ],
  ];
  return catalogo;
}

void main() {
  setUp(NoAnda.olvidarTodo);

  test('el catálogo trae las secciones nuevas con lo suyo, y saca las vacías', () async {
    final catalogo = Catalogo(_Servidor());
    await catalogo.cargar();
    expect(catalogo.error, isNull);
    expect(catalogo.seccionesNuevas.map((s) => s.nombre), ['Música', 'Radio']); // Deportes no tiene nada
    final musica = catalogo.seccionNueva('musica')!;
    expect(musica.enVivo, isFalse);
    expect(musica.canales.map((c) => (c.nombre, c.categoria, c.contenido)), [
      ('Waka Waka', 'Shakira', 'pelicula'),
      ('Hips Don\'t Lie', 'Shakira', 'pelicula'),
    ]);
    expect(catalogo.seccionNueva('radio')!.canales.single.contenido, 'vivo');
    // No se mezclan con En vivo ni con Películas, pero sí se encuentran (favoritos, seguir viendo)
    expect(catalogo.canales.map((c) => c.nombre), ['Canal 26']);
    expect(catalogo.peliculas, isEmpty);
    expect(catalogo.canalPorId(20)?.nombre, 'Radio Mitre');
    final biblioteca = Biblioteca()..alternarMiLista('c:10');
    expect(catalogo.peliculasFavoritas(biblioteca).map((c) => c.nombre), ['Waka Waka']);
  });

  test('el buscador encuentra lo de las secciones nuevas, también por la categoría (el artista)', () async {
    final catalogo = Catalogo(_Servidor());
    await catalogo.cargar();
    final porNombre = buscarEnCatalogo(catalogo, 'waka');
    expect(porNombre.nuevas.single.$1.nombre, 'Música');
    expect(porNombre.nuevas.single.$2.map((c) => c.nombre), ['Waka Waka']);
    expect(porNombre.cuantos(QueBuscar.todo), 1);
    expect(porNombre.cuantos(QueBuscar.peliculas), 0); // no se mezcla con Películas
    final porArtista = buscarEnCatalogo(catalogo, 'shakira');
    expect(porArtista.nuevas.single.$2.map((c) => c.nombre), ['Waka Waka', 'Hips Don\'t Lie']);
    expect(buscarEnCatalogo(catalogo, 'mitre').nuevas.single.$1.nombre, 'Radio');
    expect(buscarEnCatalogo(catalogo, 'nada parecido').nuevas, isEmpty);
  });

  test('con un servidor viejo (sin secciones nuevas) el catálogo carga igual', () async {
    final catalogo = Catalogo(_Servidor(viejo: true));
    await catalogo.cargar();
    expect(catalogo.error, isNull);
    expect(catalogo.seccionesNuevas, isEmpty);
    expect(catalogo.canales.single.nombre, 'Canal 26');
  });

  testWidgets('en la TV va en el menú después de Series y se abre como Películas', (tester) async {
    tester.view.physicalSize = const Size(1920, 1080);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      MaterialApp(
        home: PantallaTv(catalogo: _catalogoConSecciones(), biblioteca: Biblioteca(), seccionInicial: SeccionTv.series),
      ),
    );
    await tester.pumpAndSettle();
    for (var i = 0; i < 4 && FocusManager.instance.primaryFocus?.debugLabel != 'menú: series'; i++) {
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowLeft);
      await tester.pumpAndSettle();
    }
    expect(FocusManager.instance.primaryFocus?.debugLabel, 'menú: series');
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
    await tester.pumpAndSettle();
    expect(FocusManager.instance.primaryFocus?.debugLabel, 'menú: musica');
    await tester.sendKeyEvent(LogicalKeyboardKey.select);
    await tester.pumpAndSettle();
    expect(find.text('Música'), findsWidgets);
    expect(find.text('1 título'), findsOneWidget);
    expect(find.text('Waka Waka'), findsOneWidget);
  });

  testWidgets('en el celular está en los chips de Inicio y abre su pantalla', (tester) async {
    tester.view.physicalSize = const Size(1080, 2340);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      SesionScope(
        sesion: Sesion(),
        child: MaterialApp(
          home: PantallaMovil(catalogo: _catalogoConSecciones(), biblioteca: Biblioteca()),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Música'));
    await tester.pumpAndSettle();
    expect(find.text('MÚSICA'), findsOneWidget);
    expect(find.text('Waka Waka'), findsOneWidget);
  });
}
