// Series a pedido (desde la 1.2.38): el catálogo trae la lista de series SIN
// capítulos (GET /canales/series/) y los capítulos de una recién al abrirla
// (GET /canales/series/capitulos/). Con decenas de miles de capítulos, bajarlos
// todos al abrir la app ya no entraba en un TV box.
import 'dart:convert';
import 'dart:io';

import 'package:app_movil/api/cliente.dart';
import 'package:app_movil/api/modelos.dart';
import 'package:app_movil/aparato.dart';
import 'package:app_movil/movil/copia_catalogo.dart';
import 'package:app_movil/movil/datos.dart';
import 'package:app_movil/movil/detalle.dart';
import 'package:app_movil/tv/detalle.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Un servidor de mentira con las series a pedido.
class _Servidor extends ApiCliente {
  _Servidor() : super(urlBase: 'http://prueba/api/v1/');

  /// Los capítulos que tiene (como los manda /canales/), por serie.
  final Map<String, List<Map<String, dynamic>>> capitulos = {
    'Pocoyó': [_capitulo(1, 'Pocoyó S01 E01'), _capitulo(2, 'Pocoyó S01 E02'), _capitulo(3, 'Pocoyó S02 E01')],
    'Lost': [_capitulo(10, 'Lost S01 E01', codec: 'h265_10')],
    'Sin dato': [_capitulo(20, 'Sin dato S01 E01')],
  };

  /// Cada pedido de capítulos (lo que vino en la dirección).
  final List<String> pedidosDeCapitulos = [];
  bool sinInternet = false;

  Map<String, dynamic> get _lista => {
    'cantidad': 3,
    'series': [
      {
        'nombre': 'Pocoyó', 'categoria': 'Infantiles', 'imagen': 'https://img/pocoyo.jpg', 'capitulos': 3,
        'temporadas': [
          [1, 2],
          [2, 1],
        ],
        'destacada': true,
        'codecs': ['h264'], //
      },
      {
        'nombre': 'Lost', 'categoria': 'Drama', 'imagen': '', 'capitulos': 1,
        'temporadas': [
          [1, 1],
        ],
        'destacada': false,
        'codecs': ['h265_10'], //
      },
      {
        'nombre': 'Sin dato', 'categoria': 'Drama', 'imagen': '', 'capitulos': 1,
        'temporadas': [
          [1, 1],
        ],
        'destacada': false,
        'codecs': [''], //
      },
    ],
  };

  @override
  Future<({List<int>? bytes, String huella})> getCrudo(
    String ruta, {
    Map<String, String>? parametros,
    String huella = '',
  }) async {
    if (sinInternet) throw ApiError(status: 0, codigo: 'sin_conexion', detalle: 'Sin internet.');
    final Object datos = switch (ruta) {
      'canales/series/' => _lista,
      'canales/secciones/' => {'secciones': <Object>[]},
      _ => {'cantidad': 0, 'categorias': <Object>[]},
    };
    final texto = jsonEncode(datos);
    final suya = '"${texto.hashCode}"';
    if (huella == suya) return (bytes: null, huella: suya);
    return (bytes: utf8.encode(texto), huella: suya);
  }

  @override
  Future<dynamic> get(String ruta, {Map<String, String>? parametros}) async {
    if (sinInternet) throw ApiError(status: 0, codigo: 'sin_conexion', detalle: 'Sin internet.');
    if (!ruta.startsWith('canales/series/capitulos/')) throw ApiError(status: 404, codigo: 'no', detalle: '');
    pedidosDeCapitulos.add(ruta);
    final consulta = Uri.parse('http://x/$ruta').queryParametersAll;
    final nombres = {for (final n in consulta['nombre'] ?? const <String>[]) n.toLowerCase()};
    final ids = {for (final i in (consulta['ids']?.first ?? '').split(',')) ?int.tryParse(i)};
    final elegidos = [
      for (final MapEntry(key: serie, value: lista) in capitulos.entries)
        if (nombres.contains(serie.toLowerCase()) || lista.any((c) => ids.contains(c['id']))) ...lista,
    ];
    return {
      'cantidad': elegidos.length,
      'categorias': [
        {'nombre': 'Series', 'canales': elegidos},
      ],
    };
  }
}

Map<String, dynamic> _capitulo(int id, String nombre, {String codec = 'h264'}) => {
  'id': id,
  'nombre': nombre,
  'logo': 'https://img/$id.jpg',
  'fuentes': [
    {'id': id, 'url': 'http://p:8080/series/u/c/$id.mp4', 'tipo': 'directo', 'codec': codec},
  ],
};

void main() {
  late Directory carpeta;
  setUp(() {
    NoAnda.olvidarTodo();
    FuentePreferida.olvidarTodo();
    Aparato.codecs = {};
    FuenteCanal.probarTodo = false;
    carpeta = Directory.systemTemp.createTempSync('series_');
    CopiaCatalogo.carpetaDePrueba = carpeta;
  });
  tearDown(() {
    Aparato.codecs = {};
    FuenteCanal.probarTodo = false;
    CopiaCatalogo.carpetaDePrueba = null;
    try {
      carpeta.deleteSync(recursive: true);
    } on FileSystemException {
      // Windows: si todavía se está guardando algo
    }
  });

  Future<(Catalogo, _Servidor)> cargado() async {
    final servidor = _Servidor();
    final catalogo = Catalogo(servidor);
    addTearDown(catalogo.dispose);
    await catalogo.cargar();
    return (catalogo, servidor);
  }

  test('al abrir la app llega la lista de series, sin ningún capítulo', () async {
    final (catalogo, servidor) = await cargado();
    expect(catalogo.series.map((s) => s.nombre), ['Pocoyó', 'Lost', 'Sin dato']);
    final pocoyo = catalogo.series.first;
    expect(pocoyo.cargada, isFalse);
    expect((pocoyo.cantidadDeCapitulos, pocoyo.cantidadDeTemporadas), (3, 2));
    expect(pocoyo.numerosDeTemporada, [1, 2]);
    expect(pocoyo.imagen, 'https://img/pocoyo.jpg');
    expect(pocoyo.destacada, isTrue);
    expect(pocoyo.categoria, 'Infantiles');
    expect(catalogo.canalPorId(1), isNull); // los capítulos todavía no están
    expect(servidor.pedidosDeCapitulos, isEmpty);
  });

  test('al abrir una serie llegan sus capítulos (una sola vez)', () async {
    final (catalogo, servidor) = await cargado();
    final abierta = await catalogo.abrirSerie(catalogo.series.first);
    expect(abierta.cargada, isTrue);
    expect(abierta.episodios.map((e) => e.codigo), ['T1:E1', 'T1:E2', 'T2:E1']);
    expect(abierta.imagen, 'https://img/1.jpg');
    expect(catalogo.canalPorId(2)!.nombre, 'Pocoyó S01 E02');
    expect(catalogo.serieDe(catalogo.canalPorId(3)!)!.nombre, 'Pocoyó');
    expect(catalogo.series.first.cargada, isTrue); // queda abierta en la lista
    await catalogo.abrirSerie(catalogo.series.first);
    expect(servidor.pedidosDeCapitulos, hasLength(1));
    expect(Uri.decodeQueryComponent(servidor.pedidosDeCapitulos.single), contains('nombre=Pocoyó'));
  });

  test('lo que falla en el aparato se saca también de una serie abierta', () async {
    final (catalogo, _) = await cargado();
    final abierta = await catalogo.abrirSerie(catalogo.series.first);
    NoAnda.anotar(abierta.episodios[1].canal, deFormato: true);
    expect(catalogo.series.first.episodios.map((e) => e.codigo), ['T1:E1', 'T2:E1']);
    await catalogo.cargar(); // 15 minutos después: sigue sin estar (y sin volver a pedir los capítulos)
    expect(catalogo.series.first.episodios.map((e) => e.codigo), ['T1:E1', 'T2:E1']);
  });

  test('"Continuar viendo": trae la serie de un capítulo empezado', () async {
    final (catalogo, servidor) = await cargado();
    await catalogo.asegurarCapitulos([3, 999]);
    expect(catalogo.serieDe(catalogo.canalPorId(3)!)!.nombre, 'Pocoyó');
    await catalogo.asegurarCapitulos([3, 999]); // ya se pidió: no se vuelve a pedir
    expect(servidor.pedidosDeCapitulos, hasLength(1));
    expect(servidor.pedidosDeCapitulos.single, contains('ids=3,999'));
  });

  test('una serie que el aparato no sabe mostrar (por el códec) no aparece; sin dato, sí', () async {
    Aparato.codecs = {'h264', 'h265'};
    final (catalogo, _) = await cargado();
    expect(catalogo.series.map((s) => s.nombre), ['Pocoyó', 'Sin dato']);
    FuenteCanal.probarTodo = true; // "Probar igual lo que quizá no lea"
    await catalogo.cargar();
    expect(catalogo.series.map((s) => s.nombre), ['Pocoyó', 'Lost', 'Sin dato']);
  });

  test('la lista queda guardada: abre sin internet', () async {
    final (_, servidor) = await cargado();
    servidor.sinInternet = true;
    final otra = Catalogo(servidor);
    addTearDown(otra.dispose);
    await otra.cargar();
    expect(otra.series.map((s) => s.nombre), ['Pocoyó', 'Lost', 'Sin dato']);
  });

  testWidgets('celular: la pantalla de la serie espera sus capítulos y después los muestra', (tester) async {
    final servidor = _Servidor();
    final catalogo = Catalogo(servidor);
    addTearDown(catalogo.dispose);
    await tester.runAsync(catalogo.cargar);
    await tester.pumpWidget(
      DatosScope(
        catalogo: catalogo,
        biblioteca: Biblioteca(),
        child: MaterialApp(home: PantallaDetalle.serie(catalogo.series.first)),
      ),
    );
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(find.text('Serie • 3 capítulos'), findsOneWidget); // los números de la lista
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
    await tester.pump();
    expect(find.byType(CircularProgressIndicator), findsNothing);
    expect(find.textContaining('T1:E1'), findsWidgets);
  });

  testWidgets('TV: si no se pueden traer los capítulos, dice por qué y deja reintentar', (tester) async {
    tester.view.physicalSize = const Size(1920, 1080);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final servidor = _Servidor();
    final catalogo = Catalogo(servidor);
    addTearDown(catalogo.dispose);
    await tester.runAsync(catalogo.cargar);
    servidor.sinInternet = true;
    await tester.pumpWidget(
      DatosScope(
        catalogo: catalogo,
        biblioteca: Biblioteca(),
        child: MaterialApp(home: DetalleTv.serie(catalogo.series.first)),
      ),
    );
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
    await tester.pump();
    expect(find.textContaining('No se pudieron traer los capítulos'), findsOneWidget);
    servidor.sinInternet = false;
    await tester.tap(find.text('Reintentar'));
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
    await tester.pump();
    expect(find.textContaining('No se pudieron'), findsNothing);
    expect(find.textContaining('T1:E1'), findsWidgets);
  });
}
