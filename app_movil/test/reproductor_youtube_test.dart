// Películas de canales oficiales de YouTube: cuándo se usa su reproductor y qué entiende de él.

import 'package:flutter_test/flutter_test.dart';

import 'package:app_movil/api/modelos.dart';
import 'package:app_movil/movil/reproductor_youtube.dart';

Canal _pelicula(List<Map<String, dynamic>> fuentes) =>
    Canal({'id': 7, 'nombre': 'Tormenta Blanca', 'fuentes': fuentes}, contenido: 'pelicula');

void main() {
  test('la app le pide al servidor las películas de YouTube oficial', () {
    expect(FuenteCanal.formatosQueReproduce, contains('yt_video'));
  });

  test('se usa el reproductor de YouTube solo si es la primera fuente que se puede ver', () {
    final deYoutube = _pelicula([
      {'id': 1, 'url': 'https://www.youtube.com/watch?v=NvQqHzqClf0', 'tipo': 'yt_video'},
    ]);
    expect(fuenteDeYoutube(deYoutube)?.id, 1);
    final comun = _pelicula([
      {'id': 2, 'url': 'https://x/peli.mp4', 'tipo': 'directo'},
      {'id': 3, 'url': 'https://www.youtube.com/watch?v=NvQqHzqClf0', 'tipo': 'yt_video'},
    ]);
    expect(fuenteDeYoutube(comun), isNull);
  });

  test('saca el id del video', () {
    expect(idDeVideo('https://www.youtube.com/watch?v=NvQqHzqClf0'), 'NvQqHzqClf0');
    expect(idDeVideo('https://youtu.be/NvQqHzqClf0'), 'NvQqHzqClf0');
    expect(idDeVideo('https://www.youtube.com/@canal'), isNull);
  });

  test('la página se presenta como de Kairos y arranca donde quedó', () {
    final celular = paginaDelReproductor('NvQqHzqClf0', controles: true, desde: const Duration(minutes: 2));
    expect(celular, contains("videoId: 'NvQqHzqClf0'"));
    expect(celular, contains('"origin":"$sitioDeKairos"'));
    expect(celular, contains('"start":120'));
    expect(celular, contains('"controls":1'));
    expect(paginaDelReproductor('NvQqHzqClf0', controles: false), contains('"controls":0')); // TV: el control remoto
    expect(celular, contains('var LIMITE = 0;'));
  });

  test('en la TV el video se pide con un tope que se puede cambiar sin recargar', () {
    final tv = paginaDelReproductor('NvQqHzqClf0', controles: false, limite: 1280);
    expect(tv, contains('var LIMITE = 1280;'));
    // El reproductor se arma más chico y se agranda: YouTube elige la calidad por su tamaño
    expect(tv, contains("marco.style.transform = 'scale(' + escala + ')'"));
    expect(tv, contains('function cambiarLimite(ancho)'));
    // Y mide si el aparato da abasto
    expect(tv, contains("avisar({e: 'fluidez', c: cuadros, l: lentos})"));
    expect(tv, contains('ahora - anterior > 50'));
  });

  test('entiende lo que avisa el reproductor', () {
    final estado = EstadoYoutube();
    var avisos = 0;
    var avances = 0;
    estado.addListener(() => avisos++);
    estado.avance.addListener(() => avances++);
    expect(estado.cargando, isTrue);
    estado
      ..recibir('{"e":"listo"}')
      ..recibir('{"e":"estado","v":1}')
      ..recibir('{"e":"tiempo","t":65.5,"d":5400}')
      ..recibir('{"e":"tiempo","t":65.5,"d":5400}')
      ..recibir('esto no es json');
    // Por dónde va avisa aparte (y solo si cambió): la pantalla no se redibuja cada segundo
    expect((avisos, avances), (2, 1));
    expect(estado.reproduciendo, isTrue);
    expect(estado.posicion, const Duration(milliseconds: 65500));
    expect(estado.duracion, const Duration(minutes: 90));
    estado.recibir('{"e":"estado","v":0}');
    expect(estado.termino, isTrue);
    estado.recibir('{"e":"error","v":150}');
    expect(estado.error, 150);
  });

  test('pasa la fluidez sin redibujar la pantalla', () {
    final estado = EstadoYoutube();
    var avisos = 0;
    (int, int)? medido;
    estado
      ..addListener(() => avisos++)
      ..alMedirFluidez = ((cuadros, lentos) => medido = (cuadros, lentos));
    estado.recibir('{"e":"fluidez","c":300,"l":12}');
    expect(medido, (300, 12));
    expect(avisos, 0);
    estado
      ..recibir('{"e":"listo"}')
      ..recibir('{"e":"estado","v":3}');
    expect(estado.frenado, isTrue);
  });

  test('los errores de YouTube, en castellano y con el motivo para el servidor', () {
    expect(EstadoYoutube.mensajeDe(150), contains('no deja verlo fuera de YouTube'));
    expect(EstadoYoutube.mensajeDe(100), contains('ya no está'));
    expect(EstadoYoutube.motivoDe(101), 'rechazo');
    expect(EstadoYoutube.motivoDe(5), 'formato');
  });
}
