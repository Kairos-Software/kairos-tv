import 'dart:math';
import 'dart:ui' as ui;

import 'package:app_movil/api/cliente.dart';
import 'package:app_movil/api/modelos.dart';
import 'package:app_movil/marca.dart';
import 'package:app_movil/movil/datos.dart';
import 'package:app_movil/tv/reposo.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Canal _canal(int id, String nombre, {String contenido = 'vivo'}) =>
    Canal({'id': id, 'nombre': nombre, 'logo': 'http://prueba/$id.jpg'}, contenido: contenido);

Catalogo _catalogo({int peliculas = 0, int capitulos = 0, int canales = 0, int anio = 2026}) {
  return Catalogo(ApiCliente(urlBase: 'http://prueba/api/v1/'))
    ..peliculas = [for (var i = 0; i < peliculas; i++) _canal(i, 'Película $i (${anio - i})', contenido: 'pelicula')]
    ..series = agruparSeries([for (var i = 0; i < capitulos; i++) _canal(1000 + i, 'Serie $i S01 E01')])
    ..categoriasEnVivo = [
      CategoriaCanales({
        'nombre': 'Noticias',
        'canales': [
          for (var i = 0; i < canales; i++) {'id': 2000 + i, 'nombre': 'Canal $i', 'logo': 'http://prueba/c$i.png'},
        ],
      }),
    ];
}

void main() {
  test('con todo el catálogo: logo y las 4 escenas de grupo, con un título entre cada una', () {
    final vidriera = Vidriera.delCatalogo(
      _catalogo(peliculas: 30, capitulos: 10, canales: 20),
      azar: Random(1),
      anioActual: 2026,
    );
    expect(vidriera.recorrido, [
      Escena.logo,
      Escena.titulo,
      Escena.estrenos,
      Escena.titulo,
      Escena.cifras,
      Escena.titulo,
      Escena.enVivo,
      Escena.titulo,
      Escena.series,
    ]);
    // Estrenos: de las 20 más nuevas
    for (final estreno in vidriera.estrenos) {
      expect(int.parse(estreno.detalle), greaterThanOrEqualTo(2026 - 19));
    }
    expect(vidriera.sonEstrenos, isTrue);
    expect(vidriera.peliculas, 30);
    expect(vidriera.cantidadCanales, 20);
  });

  test('películas viejas no se llaman "estrenos"', () {
    final vidriera = Vidriera.delCatalogo(_catalogo(peliculas: 10, anio: 2015), anioActual: 2026);
    expect(vidriera.recorrido, contains(Escena.estrenos));
    expect(vidriera.sonEstrenos, isFalse);
  });

  test('lo que no tiene con qué armarse no va', () {
    final soloCanales = Vidriera.delCatalogo(_catalogo(canales: 2));
    expect(soloCanales.recorrido, [Escena.logo, Escena.titulo, Escena.cifras]); // 2 logos no alcanzan para la grilla
    expect(Vidriera.delCatalogo(_catalogo()).recorrido, [Escena.logo]);
  });

  test('lo destacado en el panel sale más seguido, pero no todo el tiempo', () {
    final catalogo = _catalogo(peliculas: 30, capitulos: 10, canales: 20);
    catalogo.peliculas[7] = Canal({
      'id': 7,
      'nombre': 'Toy Story (2019)',
      'logo': 'http://prueba/7.jpg',
      'destacado': true,
    }, contenido: 'pelicula');
    for (var vez = 0; vez < 20; vez++) {
      final titulos = Vidriera.delCatalogo(catalogo, azar: Random(vez)).titulos.map((t) => t.titulo).toList();
      // Sale dos veces (lo demás, una o ninguna), y nunca seguidas
      expect(titulos.where((t) => t == 'Toy Story').length, 2);
      expect(titulos.toSet().length, titulos.length - 1);
      expect(titulos.indexOf('Toy Story') + 1, lessThan(titulos.lastIndexOf('Toy Story')));
    }
  });

  test('los destacados se intercalan: uno de cada tres lugares', () {
    final comunes = [for (var i = 0; i < 20; i++) 'c$i'];
    expect(intercalarDestacados(comunes, ['D']).take(6), ['c0', 'D', 'c1', 'c2', 'D', 'c3']);
    final muchos = intercalarDestacados(comunes, [for (var i = 0; i < 7; i++) 'D$i']);
    expect(muchos, hasLength(20));
    expect(muchos.where((t) => t.startsWith('D')), hasLength(7)); // cada uno una vez: 7 de 20
    // Sin destacados, todo como antes
    expect(intercalarDestacados(comunes, <String>[]), comunes);
  });

  test('en los grupos de series y canales, los destacados van primero', () {
    final catalogo = _catalogo(capitulos: 30, canales: 40);
    catalogo.categoriasEnVivo = [
      CategoriaCanales({
        'nombre': 'Noticias',
        'canales': [
          for (var i = 0; i < 40; i++)
            {'id': 2000 + i, 'nombre': 'Canal $i', 'logo': 'http://prueba/c$i.png', 'destacado': i == 33},
        ],
      }),
    ];
    final vidriera = Vidriera.delCatalogo(catalogo, azar: Random(4));
    expect(vidriera.canales.first.titulo, 'Canal 33');
  });

  test('las cifras se redondean para abajo', () {
    expect(cifraRedonda(7), '7');
    expect(cifraRedonda(70), '70');
    expect(cifraRedonda(77), '+70');
    expect(cifraRedonda(419), '+400');
    expect(cifraRedonda(700), '700');
    expect(cifraRedonda(1065), '+1.000');
  });

  testWidgets('cada escena se dibuja en la TV sin desbordarse, y todas llevan el logo', (tester) async {
    tester.view.physicalSize = const Size(1920, 1080);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final vidriera = Vidriera.delCatalogo(_catalogo(peliculas: 30, capitulos: 10, canales: 20), azar: Random(2));
    await tester.pumpWidget(
      MaterialApp(
        home: PantallaReposoTv(vidriera: vidriera, imagenDe: (url) => _ImagenDePrueba(url, ancho: 500)),
      ),
    );
    final vistas = <String>{};
    for (var i = 0; i < vidriera.recorrido.length; i++) {
      await tester.pump(const Duration(seconds: 3)); // el fundido y las entradas
      expect(tester.takeException(), isNull);
      expect(find.byType(SimboloKairos), findsWidgets);
      for (final texto in [
        'Disponible en Kairos TV',
        'Estrenos',
        'Todo en un solo lugar',
        '20 canales',
        'Temporadas completas',
      ]) {
        if (find.text(texto).evaluate().isNotEmpty) vistas.add(texto);
      }
      await tester.pump(const Duration(seconds: 9)); // la siguiente
    }
    // Con imágenes buenas aparecen todas las escenas
    expect(vistas, {
      'Disponible en Kairos TV',
      'Estrenos',
      'Todo en un solo lugar',
      '20 canales',
      'Temporadas completas',
    });
    // Y nunca se baja nada al aparecer una escena: todo sale de lo preparado al entrar
    expect(find.byType(Image), findsNothing);
  });

  testWidgets('las imágenes chicas no se muestran (se verían pixeladas)', (tester) async {
    tester.view.physicalSize = const Size(1920, 1080);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    // Las películas pares tienen buena imagen; las impares, de 100 px
    final vidriera = Vidriera.delCatalogo(_catalogo(peliculas: 30), azar: Random(3));
    await tester.pumpWidget(
      MaterialApp(
        home: PantallaReposoTv(
          vidriera: vidriera,
          imagenDe: (url) => _ImagenDePrueba(
            url,
            ancho: int.parse(RegExp(r'(\d+)\.jpg').firstMatch(url)!.group(1)!).isEven ? 500 : 100,
          ),
        ),
      ),
    );
    var titulos = 0;
    for (var i = 0; i < 12; i++) {
      await tester.pump(const Duration(seconds: 12));
      await tester.pump(const Duration(seconds: 1));
      for (final texto in tester.widgetList<Text>(find.byType(Text))) {
        final numero = RegExp(r'^Película (\d+)$').firstMatch(texto.data ?? '')?.group(1);
        if (numero == null) continue;
        titulos++;
        expect(int.parse(numero).isEven, isTrue, reason: 'Película $numero tiene una imagen de 100 px');
      }
    }
    expect(titulos, greaterThan(0));
  });
}

/// Una imagen armada en memoria, del ancho pedido (como un póster: 2:3).
class _ImagenDePrueba extends ImageProvider<_ImagenDePrueba> {
  const _ImagenDePrueba(this.url, {required this.ancho});

  final String url;
  final int ancho;

  @override
  Future<_ImagenDePrueba> obtainKey(ImageConfiguration configuration) => SynchronousFuture(this);

  @override
  ImageStreamCompleter loadImage(_ImagenDePrueba key, ImageDecoderCallback decode) {
    final grabadora = ui.PictureRecorder();
    Canvas(grabadora).drawColor(const Color(0xFF336699), BlendMode.src);
    final imagen = grabadora.endRecording().toImageSync(ancho, ancho * 3 ~/ 2);
    return OneFrameImageStreamCompleter(SynchronousFuture(ImageInfo(image: imagen)));
  }

  @override
  bool operator ==(Object other) => other is _ImagenDePrueba && other.url == url && other.ancho == ancho;

  @override
  int get hashCode => Object.hash(url, ancho);
}
