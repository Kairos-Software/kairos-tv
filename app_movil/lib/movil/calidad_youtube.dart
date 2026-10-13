/// La calidad con que la TV pide los videos de YouTube, aprendida en cada
/// aparato: la mejor que aguanta sin trabarse.
///
/// YouTube elige la calidad según el tamaño del reproductor, así que la app
/// lo arma de un ancho "tope" y lo agranda a la pantalla (ver
/// reproductor_youtube.dart -> paginaDelReproductor). El tope va por
/// escalones: 480p, 720p, 1080p, 1440p y 4K (este último solo si la pantalla
/// lo tiene).
///
///   - Arranca en lo que aprendió este aparato (la primera vez, Full HD).
///   - Mientras se ve, la página cuenta cada 5 s los cuadros que se dibujaron
///     tarde (más de 50 ms: el aparato no da abasto) y la app anota cuándo se
///     frenó a cargar. Si en dos tandas seguidas se atrasa más de 1 cuadro de
///     cada 5, o se frena 2 veces en 2 minutos, baja un escalón en el momento
///     (sin cortar el video) y lo recuerda.
///   - Después de 10 minutos viéndose bien, prueba el escalón de arriba, si
///     ese no falló en este aparato en los últimos 3 días.
///
/// No ve la imagen: si el decodificador de la TV la rompe sin atrasarse, no
/// se entera (eso es la TV; ver pantalla verde en tv/README.md).
library;

import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

class CalidadYoutube {
  CalidadYoutube({required double anchoDePantalla, this.alCambiar, DateTime Function()? reloj})
    : _reloj = reloj ?? DateTime.now,
      _maximo = escalones.firstWhere((e) => e >= anchoDePantalla - 1, orElse: () => escalones.last) {
    ancho = escalones.lastWhere((e) => e <= _maximo && e <= (_aprendido ?? inicial));
    _calmarHasta = _reloj().add(_calma);
  }

  /// Los anchos tope: 480p, 720p, 1080p, 1440p y 4K.
  static const escalones = [854, 1280, 1920, 2560, 3840];

  /// La primera vez que se ve YouTube en este aparato: Full HD.
  static const inicial = 1920;

  /// Cada cuánto manda la página lo que midió.
  static const tanda = Duration(seconds: 5);

  /// Un cuadro que tardó más que esto (a 60 cuadros por segundo son 16 ms): el aparato no dio abasto.
  static const cuadroLentoMs = 50;

  static const _lentosTolerables = 0.2;
  static const _tandasMalasParaBajar = 2;
  static const _frenadasParaBajar = 2;
  static const _ventanaDeFrenadas = Duration(minutes: 2);
  static const fluidoParaSubir = Duration(minutes: 10);
  static const esperaParaReintentar = Duration(days: 3);

  /// Al arrancar, después de adelantar o de cambiar la calidad, YouTube se
  /// frena a cargar porque sí: eso no cuenta.
  static const _calma = Duration(seconds: 20);

  static const _clave = 'kairos.calidad_youtube';
  static int? _aprendido;
  static final Map<int, DateTime> _fallo = {};
  static bool _cargado = false;

  final DateTime Function() _reloj;
  final int _maximo;

  /// Se llama con el ancho nuevo cuando cambia (para avisarle a la página).
  void Function(int ancho)? alCambiar;

  /// El ancho tope de ahora.
  late int ancho;

  late DateTime _calmarHasta;
  int _tandasMalas = 0;
  Duration _fluido = Duration.zero;
  final List<DateTime> _frenadas = [];

  static Future<void> cargar() async {
    if (_cargado) return;
    _cargado = true;
    try {
      final preferencias = await SharedPreferences.getInstance();
      final guardado = jsonDecode(preferencias.getString(_clave) ?? '{}') as Map<String, dynamic>;
      final ancho = guardado['ancho'];
      if (ancho is int && escalones.contains(ancho)) _aprendido = ancho;
      for (final MapEntry(:key, :value) in ((guardado['fallo'] as Map<String, dynamic>?) ?? {}).entries) {
        final escalon = int.tryParse(key);
        if (escalon != null && value is int) _fallo[escalon] = DateTime.fromMillisecondsSinceEpoch(value);
      }
    } catch (_) {
      // Si no se puede leer, se arranca de cero
    }
  }

  /// Lo que no hay que contar por un rato (se adelantó, se cambió de video).
  void calmar() => _calmarHasta = _reloj().add(_calma);

  bool get _calmo => _reloj().isBefore(_calmarHasta);

  /// Lo que midió la página en una [tanda] mientras se veía el video.
  void medir({required int cuadros, required int lentos}) {
    if (cuadros <= 0 || _calmo) return;
    if (lentos > cuadros * _lentosTolerables) {
      _tandasMalas++;
      if (_tandasMalas >= _tandasMalasParaBajar) _bajar();
      return;
    }
    _tandasMalas = 0;
    _fluido += tanda;
    if (_fluido >= fluidoParaSubir) _subir();
  }

  /// El video se frenó a cargar mientras se veía.
  void anotarFrenada() {
    if (_calmo) return;
    final ahora = _reloj();
    _frenadas
      ..add(ahora)
      ..removeWhere((momento) => ahora.difference(momento) > _ventanaDeFrenadas);
    if (_frenadas.length >= _frenadasParaBajar) _bajar();
  }

  void _bajar() {
    final indice = escalones.indexOf(ancho);
    _fallo[ancho] = _reloj();
    _empezarDeNuevo();
    if (indice > 0) _cambiarA(escalones[indice - 1]);
    unawaited(_guardar());
  }

  void _subir() {
    _fluido = Duration.zero;
    final indice = escalones.indexOf(ancho);
    if (indice + 1 >= escalones.length || escalones[indice + 1] > _maximo) return;
    final arriba = escalones[indice + 1];
    final fallo = _fallo[arriba];
    if (fallo != null && _reloj().difference(fallo) < esperaParaReintentar) return;
    _empezarDeNuevo();
    _cambiarA(arriba);
    unawaited(_guardar());
  }

  void _empezarDeNuevo() {
    _tandasMalas = 0;
    _fluido = Duration.zero;
    _frenadas.clear();
  }

  void _cambiarA(int nuevo) {
    ancho = nuevo;
    _aprendido = nuevo;
    calmar();
    alCambiar?.call(nuevo);
  }

  static Future<void> _guardar() async {
    try {
      final preferencias = await SharedPreferences.getInstance();
      await preferencias.setString(
        _clave,
        jsonEncode({
          'ancho': _aprendido,
          'fallo': {for (final e in _fallo.entries) '${e.key}': e.value.millisecondsSinceEpoch},
        }),
      );
    } catch (_) {}
  }

  /// Solo para las pruebas: olvida lo aprendido.
  @visibleForTesting
  static void olvidarTodo() {
    _aprendido = null;
    _fallo.clear();
    _cargado = false;
  }
}
