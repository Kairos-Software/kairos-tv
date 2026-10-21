// Las imágenes guardadas en el aparato y armadas del tamaño de su lugar
// (widgets/imagen_guardada.dart). Armar y leer imágenes usa el motor de
// verdad: por eso cada prueba corre con tester.runAsync.
import 'dart:async';
import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:app_movil/widgets/imagen_guardada.dart';
import 'package:flutter/painting.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';

/// Un PNG de [ancho]x[alto] armado en memoria.
Future<Uint8List> _png(int ancho, int alto) async {
  final grabadora = ui.PictureRecorder();
  Canvas(grabadora)
      .drawRect(Rect.fromLTWH(0, 0, ancho.toDouble(), alto.toDouble()), Paint()..color = const Color(0xFF3366CC));
  final imagen = await grabadora.endRecording().toImage(ancho, alto);
  final datos = await imagen.toByteData(format: ui.ImageByteFormat.png);
  imagen.dispose();
  return datos!.buffer.asUint8List();
}

/// La medida con que queda armada la imagen de [proveedor].
Future<(int, int)> _medida(ImageProvider proveedor) {
  final listo = Completer<(int, int)>();
  proveedor
      .resolve(ImageConfiguration.empty)
      .addListener(
        ImageStreamListener(
          (info, _) {
            if (!listo.isCompleted) listo.complete((info.image.width, info.image.height));
          },
          onError: (error, _) {
            if (!listo.isCompleted) listo.completeError(error);
          },
        ),
      );
  return listo.future;
}

void main() {
  late Directory carpeta;
  late int bajadas;
  Uint8List? poster; // 600x900, como un póster (se arma la primera vez que se baja)

  setUp(() {
    carpeta = Directory.systemTemp.createTempSync('imagenes_');
    GuardadoDeImagenes.olvidar();
    GuardadoDeImagenes.carpetaDePrueba = carpeta;
    bajadas = 0;
    GuardadoDeImagenes.bajarDePrueba = (url) async {
      bajadas++;
      if (url.contains('rota')) throw const HttpException('404');
      return url.contains('apaisada') ? await _png(1280, 720) : poster ??= await _png(600, 900);
    };
  });
  tearDown(() {
    GuardadoDeImagenes.bajarDePrueba = null;
    GuardadoDeImagenes.carpetaDePrueba = null;
    GuardadoDeImagenes.olvidar();
    try {
      carpeta.deleteSync(recursive: true);
    } on FileSystemException {
      // En Windows, si todavía se está guardando una por detrás: queda en la carpeta temporal
    }
  });

  /// Una prueba que usa el motor de imágenes de verdad.
  void prueba(String nombre, Future<void> Function() cuerpo) {
    testWidgets(nombre, (tester) async {
      PaintingBinding.instance.imageCache.clear();
      await tester.runAsync(() async {
        await cuerpo();
        await Future<void>.delayed(const Duration(milliseconds: 300)); // lo que se guarda por detrás
      });
    });
  }

  prueba('se baja una sola vez: la segunda sale del aparato (aunque se abra de nuevo la app)', () async {
    await GuardadoDeImagenes.bytesDe('https://posters/1.jpg');
    await Future<void>.delayed(const Duration(milliseconds: 300)); // se guarda por detrás
    GuardadoDeImagenes.olvidar(); // como si se cerrara y abriera la app
    final otra = await GuardadoDeImagenes.bytesDe('https://posters/1.jpg');
    expect(bajadas, 1);
    expect(otra, poster);
  });

  prueba('si dos tarjetas piden la misma a la vez, se baja una vez', () async {
    await Future.wait([for (var i = 0; i < 5; i++) GuardadoDeImagenes.bytesDe('https://posters/2.jpg')]);
    expect(bajadas, 1);
  });

  prueba('si falla no queda guardada la falla: se reintenta', () async {
    await expectLater(GuardadoDeImagenes.bytesDe('https://rota/1.jpg'), throwsA(isA<HttpException>()));
    await expectLater(GuardadoDeImagenes.bytesDe('https://rota/1.jpg'), throwsA(isA<HttpException>()));
    expect(bajadas, 2);
  });

  prueba('se arma del tamaño de su lugar: un póster de 600x900 en una tarjeta de 150x225', () async {
    // Las medidas van de a 50 (225 -> 250): tarjetas casi iguales comparten la misma imagen armada
    expect(await _medida(imagenAlTamanio('https://posters/3.jpg', lugar: const Size(150, 225))), (167, 250));
    expect(await _medida(imagenAlTamanio('https://posters/3.jpg', lugar: const Size(150, 250))), (167, 250));
    // En una pantalla con el doble de píxeles, el doble
    expect(await _medida(imagenAlTamanio('https://posters/3.jpg', lugar: const Size(150, 225), pixeles: 2)), (
      300,
      450,
    ));
    // Nunca más grande que la original
    expect(await _medida(imagenAlTamanio('https://posters/3.jpg', lugar: const Size(1500, 2250))), (600, 900));
    // Sin medida: entera
    expect(await _medida(imagenAlTamanio('https://posters/3.jpg')), (600, 900));
    expect(bajadas, 1); // todas del mismo archivo
  });

  prueba('una apaisada en un póster llena el lugar sin quedar borrosa; un logo entra entero', () async {
    final (ancho, alto) = await _medida(imagenAlTamanio('https://yt/apaisada.jpg', lugar: const Size(150, 225)));
    expect(alto, greaterThanOrEqualTo(225)); // manda el alto
    expect(ancho, greaterThan(150));
    final (anchoLogo, _) = await _medida(
      imagenAlTamanio('https://yt/apaisada.jpg', lugar: const Size(150, 225), cubrir: false),
    );
    expect(anchoLogo, 150); // manda el ancho
  });

  test('si se pasa del lugar permitido, borra las más viejas', () async {
    for (var i = 0; i < 6; i++) {
      File('${carpeta.path}/$i.img')
        ..writeAsBytesSync(List.filled(1000, 0))
        ..setLastModifiedSync(DateTime(2026, 1, 1 + i));
    }
    await GuardadoDeImagenes.ordenar(carpeta, maximo: 4500);
    final quedan = carpeta.listSync().map((f) => f.uri.pathSegments.last).toList()..sort();
    expect(quedan, ['3.img', '4.img', '5.img']); // quedan las más nuevas, en 2/3 del máximo
  });

  test('cada dirección tiene su archivo, siempre el mismo', () {
    final uno = GuardadoDeImagenes.nombreDeArchivo('https://posters/1.jpg');
    expect(GuardadoDeImagenes.nombreDeArchivo('https://posters/1.jpg'), uno);
    expect(GuardadoDeImagenes.nombreDeArchivo('https://posters/2.jpg'), isNot(uno));
    expect(uno, matches(RegExp(r'^[0-9a-f]{16}\.img$')));
  });
}
