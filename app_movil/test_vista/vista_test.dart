// Herramienta (no es una prueba): dibuja pantallas a PNG para mirarlas.
//   flutter test test_vista/vista_test.dart
import 'dart:io';
import 'dart:ui' as ui;

import 'package:app_movil/api/cliente.dart';
import 'package:app_movil/api/modelos.dart';
import 'package:app_movil/aparato.dart';
import 'package:app_movil/marca.dart';
import 'package:app_movil/movil/datos.dart';
import 'package:app_movil/movil/estructura.dart';
import 'package:app_movil/sesion.dart';
import 'package:app_movil/tv/cuenta.dart';
import 'package:app_movil/tv/escenario.dart';
import 'package:app_movil/tv/estructura.dart';
import 'package:app_movil/tv/reposo.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

const salida = String.fromEnvironment('SALIDA', defaultValue: 'build/vista');

Future<void> cargarLetras() async {
  for (final (familia, archivos) in [
    ('PlusJakartaSans', ['PlusJakartaSans-Bold', 'PlusJakartaSans-ExtraBold', 'PlusJakartaSans-SemiBold']),
    ('Inter', ['Inter-Regular', 'Inter-Medium', 'Inter-SemiBold', 'Inter-Bold']),
  ]) {
    final cargador = FontLoader(familia);
    for (final a in archivos) {
      cargador.addFont(Future.value(ByteData.sublistView(File('assets/fuentes/$a.ttf').readAsBytesSync())));
    }
    await cargador.load();
  }
}

Future<void> foto(
  WidgetTester tester,
  String nombre,
  Widget pantalla, {
  Duration espera = const Duration(seconds: 3),
}) async {
  final clave = GlobalKey();
  await tester.pumpWidget(
    MaterialApp(
      debugShowCheckedModeBanner: false,
      home: Material(
        color: Colors.black,
        child: RepaintBoundary(key: clave, child: pantalla),
      ),
    ),
  );
  await tester.pump(espera);
  await tester.runAsync(() async {
    final borde = clave.currentContext!.findRenderObject()! as RenderRepaintBoundary;
    final imagen = await borde.toImage();
    final datos = await imagen.toByteData(format: ui.ImageByteFormat.png);
    Directory(salida).createSync(recursive: true);
    File('$salida/$nombre.png').writeAsBytesSync(datos!.buffer.asUint8List());
  });
}

/// Un servidor con lo que la cuenta estaba mirando en OTRO aparato (para "Seguir acá").
class _CuentaConAlgo extends ApiCliente {
  _CuentaConAlgo(this.aparato) : super(urlBase: 'http://prueba/api/v1/');

  final String aparato;

  @override
  Future<dynamic> get(String ruta, {Map<String, String>? parametros}) async => {
    'favoritos': <String>[],
    'progresos': [
      {
        'id': 5,
        'p': 2590,
        'd': 5880,
        't': DateTime.now().subtract(const Duration(minutes: 12)).millisecondsSinceEpoch,
        'aparato': aparato,
      },
    ],
    'recientes': <dynamic>[],
  };
}

Future<(Catalogo, Biblioteca)> _datosConAlgoEnOtroAparato(WidgetTester tester, String otroAparato) async {
  SharedPreferences.setMockInitialValues({});
  final api = _CuentaConAlgo(otroAparato);
  final catalogo = Catalogo(api)
    ..peliculas = [
      Canal(
        {'id': 5, 'nombre': 'Toy Story (1995)', 'fuentes': <dynamic>[]},
        categoria: 'Infantil',
        contenido: 'pelicula',
      ),
    ]
    ..categoriasEnVivo = [
      CategoriaCanales({
        'nombre': 'Noticias',
        'canales': [
          for (var i = 1; i <= 6; i++) {'id': 100 + i, 'nombre': 'Canal $i', 'fuentes': <dynamic>[]},
        ],
      }),
    ]
    ..cargado = true;
  final biblioteca = Biblioteca(api: api, cuenta: 'vista');
  await tester.runAsync(biblioteca.cargar);
  return (catalogo, biblioteca);
}

void main() {
  testWidgets('seguir acá en la TV', (tester) async {
    tester.view.physicalSize = const Size(1920, 1080);
    tester.view.devicePixelRatio = 1;
    await cargarLetras();
    Aparato.nombre = 'Smart TV Philips';
    final (catalogo, biblioteca) = await _datosConAlgoEnOtroAparato(tester, 'Celular de Ana');
    await foto(
      tester,
      'tv-seguir-aca',
      SesionScope(
        sesion: Sesion(),
        child: PantallaTv(catalogo: catalogo, biblioteca: biblioteca),
      ),
      espera: const Duration(milliseconds: 600),
    );
  });

  testWidgets('seguir acá en el celular', (tester) async {
    tester.view.physicalSize = const Size(390 * 3, 844 * 3);
    tester.view.devicePixelRatio = 3;
    await cargarLetras();
    Aparato.nombre = 'Celular de Ana';
    final (catalogo, biblioteca) = await _datosConAlgoEnOtroAparato(tester, 'Smart TV Philips');
    await foto(
      tester,
      'movil-seguir-aca',
      SesionScope(
        sesion: Sesion(),
        child: PantallaMovil(catalogo: catalogo, biblioteca: biblioteca),
      ),
      espera: const Duration(milliseconds: 600),
    );
  });

  testWidgets('escenario', (tester) async {
    tester.view.physicalSize = const Size(1920, 1080);
    tester.view.devicePixelRatio = 1;
    await cargarLetras();
    await foto(
      tester,
      'escenario',
      const Stack(
        fit: StackFit.expand,
        children: [
          EscenarioNeon(),
          Center(child: LogoKairos(tamanio: 140)),
        ],
      ),
    );
  });

  testWidgets('lo que no se ve en esta TV', (tester) async {
    tester.view.physicalSize = const Size(1920, 1080);
    tester.view.devicePixelRatio = 1;
    await cargarLetras();
    Canal canal(int id, String nombre) => Canal({'id': id, 'nombre': nombre});
    await foto(
      tester,
      'tv-lo-que-no-se-ve',
      Stack(
        children: [
          CuadroLoQueNoSeVe(
            escondidos: [
              (canal(1, 'Next'), 'Este aparato no lee H.265 de 10 bits.'),
              (canal(2, 'Disney Junior'), 'Falló acá: este aparato no lo pudo mostrar. Se vuelve a probar el 21/10.'),
              for (var i = 3; i < 12; i++) (canal(i, 'Canal $i'), 'Este aparato no lee MPEG-2.'),
            ],
            codecs: const {'h264', 'h265', 'mpeg2', 'vp9'},
            hayFallados: true,
            probarTodo: false,
          ),
        ],
      ),
    );
  });

  testWidgets('reposo', (tester) async {
    tester.view.physicalSize = const Size(1920, 1080);
    tester.view.devicePixelRatio = 1;
    await cargarLetras();
    final clave = GlobalKey();
    await tester.pumpWidget(
      MaterialApp(
        debugShowCheckedModeBanner: false,
        home: RepaintBoundary(
          key: clave,
          child: PantallaReposoTv(vidriera: Vidriera(peliculas: 1065, cantidadSeries: 419, cantidadCanales: 77)),
        ),
      ),
    );
    Future<void> guardar(String nombre) => tester.runAsync(() async {
      final borde = clave.currentContext!.findRenderObject()! as RenderRepaintBoundary;
      final datos = await (await borde.toImage()).toByteData(format: ui.ImageByteFormat.png);
      File('$salida/$nombre.png').writeAsBytesSync(datos!.buffer.asUint8List());
    });
    await tester.pump(const Duration(seconds: 3));
    await guardar('reposo-logo');
    await tester.pump(const Duration(seconds: 9)); // la escena siguiente (cada 12 s)
    for (var i = 0; i < 40; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }
    await guardar('reposo-cifras');
  });
}
