import 'dart:async';

import 'package:app_movil/movil/control_senal.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('entiende por qué falló el reproductor', () {
    PlatformException exo(String mensaje) => PlatformException(code: 'VideoError', message: mensaje);

    expect(Falla.de(TimeoutException('x')).motivo, 'tiempo');
    expect(Falla.de(exo('Source error: InvalidResponseCodeException: Response code: 403')).motivo, 'rechazo');
    expect(Falla.de(exo('Source error: InvalidResponseCodeException: Response code: 403')).mensaje, contains('403'));
    // El decodificador de este aparato no puede: es el aparato (no cuenta contra la señal en el servidor)
    expect(Falla.de(exo('MediaCodecVideoRenderer error, format_supported=NO_UNSUPPORTED_TYPE')).motivo, 'aparato');
    // Lo que llegó no es video (una página de error de la señal): es la señal, no el aparato
    expect(Falla.de(exo('UnrecognizedInputFormatException: None of the available extractors')).motivo, 'error');
    expect(Falla.de(exo('java.net.UnknownHostException: Unable to resolve host "x"')).motivo, 'sin_internet');
    expect(Falla.de(exo('Source error')).motivo, 'conexion');
  });

  test('el error del reproductor llega con su causa y cuántas veces se reconectó (KairosReconexion)', () {
    PlatformException exo(String mensaje) => PlatformException(code: 'VideoError', message: mensaje);
    final rechazo = Falla.de(exo('Video player had error ERROR_CODE_IO_BAD_HTTP_STATUS: Source error: '
        'Response code: 404 · se reconectó sola 6 veces'));
    expect(rechazo.motivo, 'rechazo');
    expect(rechazo.detalle, 'ERROR_CODE_IO_BAD_HTTP_STATUS: Source error: Response code: 404 · se reconectó sola 6 veces');
    final sinInternet = Falla.de(exo('Video player had error ERROR_CODE_IO_NETWORK_CONNECTION_FAILED: Source error: '
        'Unable to resolve host "x": No address associated with hostname'));
    expect(sinInternet.motivo, 'sin_internet');
  });

  test('el detalle que llega al panel dice qué pasó y cuándo (para diagnosticar)', () {
    final desde = DateTime(2026, 10, 19, 21, 42, 0);
    final ahora = desde.add(const Duration(milliseconds: 1240));
    // La transmisión empezó (llegó un cuadro) y el servidor la cortó; al final, la app y el aparato
    expect(
      ControlSenal.detalleDeLaFalla(
        Falla.cortada,
        desde: desde,
        ahora: ahora,
        imagen: const Size(1920, 1080),
        aparato: 'app 1.2.40 · Philips 55PUD7406 · Android 10',
      ),
      'la transmisión se cortó (la cortó el servidor de la señal o se cortó internet) · a los 1,2 s de empezar a conectar · '
      'llegó imagen 1920x1080 · [app 1.2.40 · Philips 55PUD7406 · Android 10]',
    );
    // El error del reproductor, tal cual, y que venía andando
    final rechazo = Falla.de(PlatformException(code: 'VideoError', message: 'Source error: Response code: 403'));
    expect(
      ControlSenal.detalleDeLaFalla(rechazo, desde: desde, ahora: ahora, andaba: true, aparato: 'x'),
      allOf(contains('Response code: 403'), contains('a los 1,2 s'), endsWith('venía andando bien · [x]')),
    );
    expect(ControlSenal.detalleDeLaFalla(Falla.tiempo), contains('no arrancó a tiempo'));
    // Nunca más largo de lo que guarda el servidor
    final larga = Falla('error', 'x', 'y' * 900);
    expect(ControlSenal.detalleDeLaFalla(larga, desde: desde, ahora: ahora).length, ControlSenal.largoDelDetalle);
  });
}
