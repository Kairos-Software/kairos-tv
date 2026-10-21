// El catálogo guardado en el aparato (movil/copia_catalogo.dart): abre
// enseguida con lo guardado, no se baja de nuevo si no cambió (304) y lo que
// falla en el aparato se sigue sacando. Y los índices del catálogo.
import 'dart:convert';
import 'dart:io';

import 'package:app_movil/api/cliente.dart';
import 'package:app_movil/api/modelos.dart';
import 'package:app_movil/movil/copia_catalogo.dart';
import 'package:app_movil/movil/datos.dart';
import 'package:flutter_test/flutter_test.dart';

/// Un servidor de mentira que contesta como el de verdad: con huella, y 304
/// si el aparato ya tiene ese mismo catálogo.
class _Servidor extends ApiCliente {
  _Servidor() : super(urlBase: 'http://prueba/api/v1/');

  /// Lo que manda de cada contenido ("vivo", "pelicula", "serie", "musica").
  final Map<String, Map<String, dynamic>> partes = {
    'vivo': _parte([_canal(1, 'TN'), _canal(2, 'Telefe')]),
    'pelicula': _parte([_canal(10, 'Toy Story (1995)'), _canal(11, 'Up (2009)')]),
    'serie': _parte([_canal(20, 'Pocoyó S01 E01'), _canal(21, 'Pocoyó S01 E02')]),
    'musica': _parte([_canal(30, 'Un video')]),
  };

  bool sinInternet = false;

  /// Cuántas veces mandó un catálogo entero (no un 304).
  int enteros = 0;

  @override
  Future<({List<int>? bytes, String huella})> getCrudo(
    String ruta, {
    Map<String, String>? parametros,
    String huella = '',
  }) async {
    if (sinInternet) throw ApiError(status: 0, codigo: 'sin_conexion', detalle: 'Sin internet.');
    if (ruta == 'canales/secciones/') {
      final secciones = {
        'secciones': [
          {'clave': 'musica', 'nombre': 'Música', 'forma': 'pelicula', 'icono': 'musica'},
        ],
      };
      return (bytes: utf8.encode(jsonEncode(secciones)), huella: '');
    }
    final texto = jsonEncode(partes[parametros!['contenido']]);
    final suya = '"${texto.hashCode}"';
    if (huella == suya) return (bytes: null, huella: suya);
    enteros++;
    return (bytes: utf8.encode(texto), huella: suya);
  }
}

Map<String, dynamic> _parte(List<Map<String, dynamic>> canales) => {
  'cantidad': canales.length,
  'categorias': [
    {'nombre': 'Todo', 'canales': canales},
  ],
};

Map<String, dynamic> _canal(int id, String nombre) => {
  'id': id,
  'nombre': nombre,
  'fuentes': [
    {'id': id, 'url': 'https://x/$id.m3u8', 'tipo': 'hls'},
  ],
};

List<String> _nombres(Catalogo catalogo) => [
  ...catalogo.canales.map((c) => c.nombre),
  ...catalogo.peliculas.map((c) => c.nombre),
  ...catalogo.series.map((s) => s.nombre),
  for (final s in catalogo.seccionesNuevas) ...s.canales.map((c) => c.nombre),
];

void main() {
  late Directory carpeta;
  setUp(() {
    NoAnda.olvidarTodo();
    FuentePreferida.olvidarTodo();
    carpeta = Directory.systemTemp.createTempSync('catalogo_');
    CopiaCatalogo.carpetaDePrueba = carpeta;
  });
  tearDown(() {
    CopiaCatalogo.carpetaDePrueba = null;
    carpeta.deleteSync(recursive: true);
  });

  test('lo guarda en el aparato y la próxima vez abre aunque no haya internet', () async {
    final servidor = _Servidor();
    final primero = Catalogo(servidor);
    addTearDown(primero.dispose);
    await primero.cargar();
    expect(_nombres(primero), ['TN', 'Telefe', 'Toy Story (1995)', 'Up (2009)', 'Pocoyó', 'Un video']);

    // Otra vez la app (otro Catalogo), sin internet: muestra lo guardado
    servidor.sinInternet = true;
    final despues = Catalogo(servidor);
    addTearDown(despues.dispose);
    await despues.cargar();
    expect(despues.cargado, isTrue);
    expect(_nombres(despues), _nombres(primero));
    expect(despues.seccionNueva('musica')!.nombre, 'Música');
  });

  test('si no cambió, no se baja de nuevo; si cambió, llega lo nuevo', () async {
    final servidor = _Servidor();
    final catalogo = Catalogo(servidor);
    addTearDown(catalogo.dispose);
    await catalogo.cargar();
    expect(servidor.enteros, 4); // vivo, películas, series y Música

    await catalogo.cargar(); // a los 15 minutos: nada cambió
    expect(servidor.enteros, 4);
    expect(_nombres(catalogo), contains('Toy Story (1995)'));

    servidor.partes['pelicula'] = _parte([_canal(12, 'Coco (2017)')]);
    await catalogo.cargar();
    expect(servidor.enteros, 5); // solo películas
    expect(catalogo.peliculas.map((p) => p.nombre), ['Coco (2017)']);
    expect(catalogo.canales.map((c) => c.nombre), ['TN', 'Telefe']);

    // Y al abrir de nuevo la app, lo guardado ya es lo nuevo (con su huella: no se baja nada)
    final otra = Catalogo(servidor);
    addTearDown(otra.dispose);
    await otra.cargar();
    expect(otra.peliculas.map((p) => p.nombre), ['Coco (2017)']);
    expect(servidor.enteros, 5);
  });

  test('lo que falla en el aparato se saca, aunque el catálogo no haya cambiado', () async {
    final servidor = _Servidor();
    final catalogo = Catalogo(servidor);
    addTearDown(catalogo.dispose);
    await catalogo.cargar();
    final up = catalogo.peliculas.firstWhere((p) => p.nombre == 'Up (2009)');
    NoAnda.anotar(up, deFormato: true);
    expect(catalogo.peliculas.map((p) => p.nombre), ['Toy Story (1995)']); // enseguida
    await catalogo.cargar(); // 304: sigue sin estar
    expect(catalogo.peliculas.map((p) => p.nombre), ['Toy Story (1995)']);
    expect(catalogo.escondidos.map((e) => e.$1.nombre), ['Up (2009)']);
    // Y vuelve cuando se lo vuelve a mostrar (Mi cuenta en la TV), sin bajar nada
    await NoAnda.volverAMostrarTodo();
    await catalogo.cargar();
    expect(catalogo.peliculas.map((p) => p.nombre), ['Toy Story (1995)', 'Up (2009)']);
    expect(servidor.enteros, 4);
  });

  test('una copia rota se ignora y se baja de nuevo', () async {
    final servidor = _Servidor();
    final primero = Catalogo(servidor);
    addTearDown(primero.dispose);
    await primero.cargar();
    for (final archivo in carpeta.listSync(recursive: true).whereType<File>()) {
      if (archivo.path.endsWith('pelicula.json')) archivo.writeAsStringSync('{roto');
    }
    final despues = Catalogo(servidor);
    addTearDown(despues.dispose);
    await despues.cargar();
    expect(despues.peliculas.map((p) => p.nombre), ['Toy Story (1995)', 'Up (2009)']);
  });

  test('al cerrar sesión no queda nada guardado', () async {
    final catalogo = Catalogo(_Servidor());
    addTearDown(catalogo.dispose);
    await catalogo.cargar();
    expect(carpeta.listSync(recursive: true).whereType<File>(), isNotEmpty);
    await CopiaCatalogo.borrarTodo();
    expect(carpeta.existsSync(), isFalse);
    carpeta.createSync(); // para el tearDown
  });

  test('los índices encuentran por id, la serie de un capítulo y se rehacen si cambia una lista', () async {
    final catalogo = Catalogo(_Servidor());
    addTearDown(catalogo.dispose);
    await catalogo.cargar();
    expect(catalogo.canalPorId(2)!.nombre, 'Telefe');
    expect(catalogo.canalPorId(11)!.nombre, 'Up (2009)');
    expect(catalogo.canalPorId(30)!.nombre, 'Un video');
    final capitulo = catalogo.canalPorId(21)!;
    expect(catalogo.serieDe(capitulo)!.nombre, 'Pocoyó');
    expect(catalogo.seriePorNombre('Pocoyó')!.episodios, hasLength(2));
    expect(catalogo.canalPorId(999), isNull);

    catalogo.peliculas = [
      Canal({
        'id': 50,
        'nombre': 'Nueva',
        'fuentes': [
          {'id': 50, 'url': 'https://x/50.m3u8', 'tipo': 'hls'},
        ],
      }, contenido: 'pelicula'),
    ];
    expect(catalogo.canalPorId(50)!.nombre, 'Nueva');
    expect(catalogo.canalPorId(11), isNull);
  });
}
