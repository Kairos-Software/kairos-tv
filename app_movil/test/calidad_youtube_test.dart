// La calidad de YouTube en la TV: la mejor que aguanta cada aparato, aprendida sola.

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:app_movil/movil/calidad_youtube.dart';

void main() {
  late DateTime ahora;
  late List<int> cambios;

  setUp(() {
    SharedPreferences.setMockInitialValues({});
    CalidadYoutube.olvidarTodo();
    ahora = DateTime(2026, 10, 13, 21);
    cambios = [];
  });

  CalidadYoutube nueva({double pantalla = 1920}) =>
      CalidadYoutube(anchoDePantalla: pantalla, reloj: () => ahora, alCambiar: cambios.add);

  void pasar(Duration cuanto) => ahora = ahora.add(cuanto);

  /// [veces] tandas de 5 s: fluidas (1 de cada 100 cuadros tarde) o trabadas (1 de cada 3).
  void ver(CalidadYoutube calidad, {int veces = 1, bool trabado = false}) {
    for (var i = 0; i < veces; i++) {
      pasar(CalidadYoutube.tanda);
      calidad.medir(cuadros: 300, lentos: trabado ? 100 : 3);
    }
  }

  test('la primera vez arranca en Full HD (y no más que la pantalla)', () {
    expect(nueva().ancho, 1920);
    expect(nueva(pantalla: 1280).ancho, 1280);
    expect(nueva(pantalla: 3840).ancho, 1920);
  });

  test('si no da abasto baja un escalón en el momento y lo recuerda', () async {
    final calidad = nueva();
    pasar(const Duration(seconds: 30)); // pasó la calma del arranque
    ver(calidad, trabado: true);
    expect(calidad.ancho, 1920, reason: 'una tanda mala sola puede ser casualidad');
    ver(calidad, trabado: true);
    expect(calidad.ancho, 1280);
    expect(cambios, [1280]);
    // El próximo video ya arranca en 720p
    expect(nueva().ancho, 1280);
    // Y quedó guardado para cuando se vuelva a abrir la app
    await Future<void>.delayed(Duration.zero);
    final guardado = (await SharedPreferences.getInstance()).getString('kairos.calidad_youtube');
    expect(guardado, contains('"ancho":1280'));
  });

  test('lo que pasa al arrancar o al adelantar no cuenta', () {
    final calidad = nueva();
    ver(calidad, veces: 2, trabado: true); // recién arranca
    calidad.anotarFrenada();
    calidad.anotarFrenada();
    expect(calidad.ancho, 1920);
    pasar(const Duration(seconds: 30));
    calidad.calmar(); // adelantó
    ver(calidad, veces: 2, trabado: true);
    expect(calidad.ancho, 1920);
  });

  test('si se frena a cargar dos veces en 2 minutos, baja', () {
    final calidad = nueva();
    pasar(const Duration(seconds: 30));
    calidad.anotarFrenada();
    pasar(const Duration(minutes: 3));
    calidad.anotarFrenada();
    expect(calidad.ancho, 1920, reason: 'separadas por más de 2 minutos');
    pasar(const Duration(minutes: 1));
    calidad.anotarFrenada();
    expect(calidad.ancho, 1280);
  });

  test('después de 10 minutos fluidos prueba el escalón de arriba', () {
    final calidad = nueva(pantalla: 3840);
    pasar(const Duration(seconds: 30));
    ver(calidad, veces: 119);
    expect(calidad.ancho, 1920);
    ver(calidad);
    expect(calidad.ancho, 2560);
    expect(cambios, [2560]);
  });

  test('nunca pide más que la pantalla', () {
    final calidad = nueva();
    pasar(const Duration(seconds: 30));
    ver(calidad, veces: 500);
    expect(calidad.ancho, 1920);
    expect(cambios, isEmpty);
  });

  test('lo que falló no lo vuelve a probar hasta dentro de 3 días', () {
    final calidad = nueva();
    pasar(const Duration(seconds: 30));
    ver(calidad, veces: 2, trabado: true); // 1080p no anduvo
    expect(calidad.ancho, 1280);
    pasar(const Duration(seconds: 30));
    ver(calidad, veces: 200); // 720p anda perfecto
    expect(calidad.ancho, 1280);
    pasar(const Duration(days: 3));
    ver(calidad, veces: 120);
    expect(calidad.ancho, 1920, reason: 'pasaron 3 días: lo vuelve a intentar');
  });

  test('en lo más bajo se queda ahí', () {
    final calidad = nueva();
    for (var i = 0; i < 5; i++) {
      pasar(const Duration(seconds: 30));
      ver(calidad, veces: 2, trabado: true);
    }
    expect(calidad.ancho, 854);
    expect(cambios, [1280, 854]);
  });

  test('sin cuadros (pausado o en el fondo) no mide nada', () {
    final calidad = nueva();
    pasar(const Duration(seconds: 30));
    for (var i = 0; i < 3; i++) {
      calidad.medir(cuadros: 0, lentos: 0);
    }
    expect(calidad.ancho, 1920);
  });
}
