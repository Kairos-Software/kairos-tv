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
    expect(Falla.de(exo('MediaCodecVideoRenderer error, format_supported=NO_UNSUPPORTED_TYPE')).motivo, 'formato');
    // Lo que llegó no es video (una página de error de la señal): es la señal, no el aparato
    expect(Falla.de(exo('UnrecognizedInputFormatException: None of the available extractors')).motivo, 'error');
    expect(Falla.de(exo('java.net.UnknownHostException: Unable to resolve host "x"')).motivo, 'sin_internet');
    expect(Falla.de(exo('Source error')).motivo, 'conexion');
  });
}
