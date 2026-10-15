// Un canal que está en el celular y no en la TV (pasó con Next): qué esconde
// cada aparato y por qué, y que un error pasajero no lo esconda.
import 'package:app_movil/api/cliente.dart';
import 'package:app_movil/api/modelos.dart';
import 'package:app_movil/aparato.dart';
import 'package:app_movil/movil/control_senal.dart';
import 'package:app_movil/movil/datos.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

/// Un servidor de mentira: Next viene en H.265 de 10 bits, Canal 26 en H.264.
class _Servidor extends ApiCliente {
  _Servidor() : super(urlBase: 'http://prueba/api/v1/');

  @override
  Future<dynamic> get(String ruta, {Map<String, String>? parametros}) async {
    if (ruta == 'canales/secciones/') return {'secciones': []};
    if (parametros?['contenido'] != 'vivo') return {'cantidad': 0, 'categorias': []};
    return {
      'cantidad': 2,
      'categorias': [
        {
          'nombre': 'Noticias',
          'canales': [
            {
              'id': 1,
              'nombre': 'Canal 26',
              'fuentes': [
                {'id': 1, 'url': 'https://x/1.m3u8', 'tipo': 'hls', 'codec': 'h264'},
              ],
            },
            {
              'id': 2,
              'nombre': 'Next',
              'fuentes': [
                {'id': 2, 'url': 'https://x/2.m3u8', 'tipo': 'hls', 'codec': 'h265_10'},
              ],
            },
          ],
        },
      ],
    };
  }
}

void main() {
  setUp(() {
    NoAnda.olvidarTodo();
    Aparato.codecs = {'h264', 'h265'}; // una TV que no lee 10 bits
    FuenteCanal.probarTodo = false;
  });
  tearDown(() {
    Aparato.codecs = {};
    FuenteCanal.probarTodo = false;
  });

  test('la TV sabe qué esconde y por qué', () async {
    final catalogo = Catalogo(_Servidor());
    addTearDown(catalogo.dispose);
    await catalogo.cargar();
    expect(catalogo.canales.map((c) => c.nombre), ['Canal 26']);
    final escondido = catalogo.escondidos.single;
    expect(escondido.$1.nombre, 'Next');
    expect(escondido.$2, 'Este aparato no lee H.265 de 10 bits.');
  });

  test('"Probar igual lo que quizá no lea" lo muestra', () async {
    FuenteCanal.probarTodo = true;
    final catalogo = Catalogo(_Servidor());
    addTearDown(catalogo.dispose);
    await catalogo.cargar();
    expect(catalogo.canales.map((c) => c.nombre), ['Canal 26', 'Next']);
    expect(catalogo.escondidos, isEmpty);
  });

  test('lo que falló acá se ve en la lista y se puede volver a mostrar', () async {
    Aparato.codecs = {};
    final catalogo = Catalogo(_Servidor());
    addTearDown(catalogo.dispose);
    await catalogo.cargar();
    NoAnda.anotar(catalogo.canales.last, deFormato: true);
    expect(catalogo.canales.map((c) => c.nombre), ['Canal 26']);
    expect(catalogo.escondidos.single.$2, startsWith('Falló acá: este aparato no lo pudo mostrar.'));
    expect(NoAnda.cuantos, 1);
    await NoAnda.volverAMostrarTodo();
    await catalogo.cargar();
    expect(catalogo.canales.map((c) => c.nombre), ['Canal 26', 'Next']);
  });

  test('solo un error del decodificador del aparato esconde; si la señal manda basura, no', () {
    final basura = Falla.de(
      PlatformException(
        code: 'VideoError',
        message: 'UnrecognizedInputFormatException: None of the available extractors',
      ),
    );
    expect((basura.motivo, basura.delAparato), ('error', false));
    expect(ControlSenal.esconderDespuesDe(basura, hayFuentes: true, seVio: false), isFalse);
    final decodificador = Falla.de(
      PlatformException(code: 'VideoError', message: 'MediaCodecVideoRenderer error, Decoder init failed'),
    );
    expect((decodificador.motivo, decodificador.delAparato), ('formato', true));
    expect(ControlSenal.esconderDespuesDe(decodificador, hayFuentes: true, seVio: false), isTrue);
    // Sin imagen a los 8 segundos: puede ser la TV trabada (pantalla verde) o un momento de la señal
    expect(ControlSenal.esconderDespuesDe(Falla.sinImagen, hayFuentes: true, seVio: false), isFalse);
  });
}
