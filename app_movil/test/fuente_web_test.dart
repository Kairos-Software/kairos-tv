import 'package:app_movil/api/cliente.dart';
import 'package:app_movil/api/modelos.dart';
import 'package:app_movil/movil/control_senal.dart';
import 'package:app_movil/movil/reproductor_web.dart';
import 'package:app_movil/movil/datos.dart';
import 'package:flutter_test/flutter_test.dart';

class _Api extends ApiCliente {
  _Api() : super(urlBase: "https://api.example/");
  final pedidos = <String>[];
  @override
  Future<dynamic> get(String ruta, {Map<String, String>? parametros}) async {
    pedidos.add(ruta);
    throw StateError('Una fuente web no se resuelve en el servidor');
  }
}

Canal canal(int id) => Canal({
  'id': id,
  'nombre': 'Canal web',
  'fuentes': [
    {'id': id * 10, 'tipo': 'web', 'url': 'https://player.example/canal/$id'},
    {'id': id * 10 + 1, 'tipo': 'web', 'url': 'https://otro.example/canal/$id'},
  ],
});

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(FuentePreferida.olvidarTodo);

  test('el reproductor no puede navegar ni a otras paginas del mismo sitio', () {
    final source = Uri.parse('https://player.example/watch?r=canal');
    expect(esDestinoDelReproductorWeb(source, source.replace(fragment: 'player')), isTrue);
    for (final other in [
      'https://player.example/',
      'https://player.example/eventos',
      'https://player.example/watch?r=otro',
      'https://ads.example/watch?r=canal',
      'http://player.example/watch?r=canal',
      'intent://player',
      'javascript:alert(1)',
    ]) {
      expect(esDestinoDelReproductorWeb(source, Uri.parse(other)), isFalse, reason: other);
    }
  });

  test('cambiar de fuente y canal reemplaza la pagina sin resolverla como video', () async {
    final api = _Api();
    final control = ControlSenal(api);
    addTearDown(control.dispose);
    await control.abrir(canal(1));
    expect(control.fuenteWeb?.url, 'https://player.example/canal/1');
    expect(control.video, isNull);
    expect(control.cargando, isFalse);
    expect(control.error, isNull);
    await control.usarFuente(1);
    expect(control.fuenteWeb?.url, 'https://otro.example/canal/1');
    await control.abrir(canal(2));
    expect(control.fuenteWeb?.id, 20);
    expect(api.pedidos, isEmpty);
    await control.detener();
    expect(control.fuenteWeb, isNull);
    expect(control.video, isNull);
  });
}
