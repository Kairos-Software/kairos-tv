// "Lo más visto": lo que la app junta y le manda al servidor (sin decir quién es).
import 'package:app_movil/api/cliente.dart';
import 'package:app_movil/movil/datos.dart';
import 'package:app_movil/movil/medidor.dart';
import 'package:flutter_test/flutter_test.dart';

import 'servidor_de_prueba.dart';

/// Un servidor de mentira: guarda lo que le mandan (o falla, si se pide).
class _Servidor extends ApiCliente with CrudoDesdeGet {
  _Servidor() : super(urlBase: 'http://prueba/api/v1/');

  final avisos = <Map<String, dynamic>>[];
  bool sinInternet = false;

  @override
  Future<dynamic> post(String ruta, [Map<String, dynamic>? cuerpo]) async {
    if (sinInternet) throw ApiError(status: 0, codigo: 'conexion', detalle: 'No se pudo conectar con el servidor.');
    expect(ruta, 'canales/visto/');
    avisos.add(cuerpo!);
    return {'sumados': 1};
  }
}

void main() {
  late _Servidor servidor;

  setUp(() {
    Medidor.olvidar();
    servidor = _Servidor();
  });

  test('junta el tiempo y las vistas, y al mandarlo queda vacío', () async {
    Medidor.sumar(servidor, 12, const Duration(seconds: 70, milliseconds: 400));
    Medidor.contarVista(12);
    Medidor.sumar(servidor, 7, const Duration(seconds: 3));
    expect(servidor.avisos, isEmpty); // todavía no llegó a 5 minutos

    await Medidor.enviar(servidor);
    expect(servidor.avisos.single, {
      'vistos': [
        {'id': 12, 'segundos': 70, 'vista': true},
        {'id': 7, 'segundos': 3, 'vista': false},
      ],
      'favoritos': <String>[],
    });
    expect(Medidor.pendiente['segundos'], {12: 0}); // quedan los 400 ms para la próxima
    expect(Medidor.pendiente['vistas'], isEmpty);

    await Medidor.enviar(servidor);
    expect(servidor.avisos, hasLength(1)); // menos de un segundo: espera a juntar más
    Medidor.sumar(servidor, 12, const Duration(milliseconds: 700));
    await Medidor.enviar(servidor);
    expect(servidor.avisos.last['vistos'], [
      {'id': 12, 'segundos': 1, 'vista': false},
    ]);
  });

  test('al juntar 5 minutos avisa solo', () async {
    for (var i = 0; i < 10; i++) {
      Medidor.sumar(servidor, 12, const Duration(seconds: 30));
    }
    await pumpEventQueue();
    expect(servidor.avisos.single['vistos'], [
      {'id': 12, 'segundos': 300, 'vista': false},
    ]);
  });

  test('sin internet guarda todo y no reintenta a cada rato', () async {
    servidor.sinInternet = true;
    Medidor.sumar(servidor, 12, const Duration(minutes: 5));
    Medidor.contarVista(12);
    await pumpEventQueue();
    expect(Medidor.pendiente['segundos'], {12: 300}); // lo devolvió
    expect(Medidor.pendiente['vistas'], {12});

    servidor.sinInternet = false;
    Medidor.sumar(servidor, 12, const Duration(seconds: 1));
    await pumpEventQueue();
    expect(servidor.avisos, isEmpty); // espera un rato antes de volver a probar solo

    await Medidor.enviar(servidor); // al salir del reproductor sí prueba
    expect(servidor.avisos.single['vistos'], [
      {'id': 12, 'segundos': 301, 'vista': true},
    ]);
  });

  test('manda de a 50 (lo que acepta el servidor) y el resto va después', () async {
    for (var id = 1; id <= 60; id++) {
      Medidor.sumar(servidor, id, const Duration(seconds: 2));
    }
    await Medidor.enviar(servidor);
    expect(servidor.avisos.single['vistos'], hasLength(50));
    expect((Medidor.pendiente['segundos'] as Map).length, 10);
  });

  test('los favoritos: cuenta solo cuando se agrega, no cuando se saca', () async {
    final biblioteca = Biblioteca();
    biblioteca.alternarMiLista('c:12'); // agrega
    biblioteca.alternarMiLista('c:12'); // saca
    biblioteca.alternarMiLista('s:Flash Gordon'); // agrega
    await Medidor.enviar(servidor);
    expect(servidor.avisos.single['favoritos'], ['c:12', 's:Flash Gordon']);
    expect(servidor.avisos.single['vistos'], isEmpty);
  });
}
