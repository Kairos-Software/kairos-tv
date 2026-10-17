// Los logos oscuros sobre transparente van sobre una placa clara (movil/logo_legible.dart).
import 'dart:typed_data';

import 'package:app_movil/movil/logo_legible.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Un logo de 10×10: [lleno] de los píxeles del color dado y el resto transparente.
Uint8List _logo({required int lleno, required int gris, int alfaDelResto = 0}) {
  final datos = Uint8List(10 * 10 * 4);
  for (var i = 0; i < 100; i++) {
    final esLogo = i < lleno;
    datos[i * 4] = esLogo ? gris : 0;
    datos[i * 4 + 1] = esLogo ? gris : 0;
    datos[i * 4 + 2] = esLogo ? gris : 0;
    datos[i * 4 + 3] = esLogo ? 255 : alfaDelResto;
  }
  return datos;
}

void main() {
  test('letras negras sobre transparente: oscuro', () {
    expect(esLogoOscuro(_logo(lleno: 40, gris: 20)), isTrue);
  });

  test('letras blancas o de color claro sobre transparente: se lee solo', () {
    expect(esLogoOscuro(_logo(lleno: 40, gris: 240)), isFalse);
    expect(esLogoOscuro(_logo(lleno: 40, gris: 150)), isFalse);
  });

  test('un logo con su propio fondo (sin transparente) no lleva placa, aunque sea oscuro', () {
    expect(esLogoOscuro(_logo(lleno: 100, gris: 10)), isFalse);
    expect(esLogoOscuro(_logo(lleno: 40, gris: 10, alfaDelResto: 255)), isFalse);
  });

  test('vacío o todo transparente: sin placa', () {
    expect(esLogoOscuro(Uint8List(0)), isFalse);
    expect(esLogoOscuro(_logo(lleno: 0, gris: 0)), isFalse);
  });

  testWidgets('un logo oscuro se ve sobre la placa clara; uno claro, como siempre', (tester) async {
    LogosOscuros.poner('http://prueba/oscuro.png', 2);
    LogosOscuros.poner('http://prueba/claro.png', 0);
    Future<void> mostrar(String url) => tester.pumpWidget(
      Center(
        child: SizedBox(
          width: 200,
          height: 100,
          child: LogoLegible(url: url, imagen: const SizedBox.expand()),
        ),
      ),
    );
    bool hayPlaca() => tester
        .widgetList<DecoratedBox>(find.byType(DecoratedBox))
        .any((caja) => (caja.decoration as BoxDecoration).color == colorPlacaDeLogo);

    await mostrar('http://prueba/oscuro.png');
    expect(hayPlaca(), isTrue);
    await mostrar('http://prueba/claro.png');
    expect(hayPlaca(), isFalse);
  });
}
