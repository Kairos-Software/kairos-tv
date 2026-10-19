/// El MODO REVISIÓN: este aparato recorre los canales solo, de a uno, y le
/// cuenta al servidor cuáles andan (canales/recorrido.py).
///
/// Sirve para lo que el servidor no puede probar: los paneles Xtream
/// bloquean a los servidores, pero desde una casa entregan la señal como a
/// un cliente. Es lo mismo que probar cada canal a mano con VLC, para todos,
/// sin que nadie los mire. Lo usa un usuario del panel con permiso para
/// cargar canales; se deja una TV o un celular prendido (de noche, por ejemplo).
///
/// Va de a UN canal por vez y suelta la conexión antes de pasar al siguiente
/// ([pausaEntreCanales]): hay cuentas que aceptan una sola conexión.
///
///     final recorrido = Recorrido(ServidorEnLaApi(api), probarConElReproductor)..empezar();
library;

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:video_player/video_player.dart';

import '../api/cliente.dart';
import '../api/modelos.dart';
import '../movil/control_senal.dart';
import '../senales.dart';

/// Una fuente para probar, con el canal al que pertenece.
class FuenteARevisar {
  FuenteARevisar(Map<String, dynamic> json)
    : fuente = FuenteCanal(json),
      canal = '${json['canal'] ?? ''}',
      logo = '${json['logo'] ?? ''}',
      enVivo = json['en_vivo'] != false;

  final FuenteCanal fuente;
  final String canal;
  final String logo;
  final bool enVivo;
}

/// Lo que dio la prueba de una fuente.
class Prueba {
  const Prueba.anduvo() : anduvo = true, motivo = '', mensaje = 'Anda', detalle = '';

  Prueba.fallo(Falla falla) : anduvo = false, motivo = falla.motivo, mensaje = falla.mensaje, detalle = falla.detalle;

  final bool anduvo;

  /// formato, rechazo, tiempo, conexion, error o sin_internet (como [Falla]).
  final String motivo;
  final String mensaje;
  final String detalle;

  bool get sinInternet => motivo == Falla.sinInternet.motivo;
}

/// Prueba una fuente. `mostrar` recibe el video mientras se prueba (para
/// verlo en la pantalla) y null al terminar.
typedef Probador = Future<Prueba> Function(FuenteARevisar fuente, void Function(VideoPlayerController?) mostrar);

/// Lo que el recorrido le pide y le cuenta al servidor.
abstract class ServidorDelRecorrido {
  /// Las próximas fuentes para probar y cuántas quedan en total.
  Future<(List<FuenteARevisar>, int)> pedir(int cantidad);

  /// Lo que se encontró: [{"id", "anduvo", "motivo"?, "detalle"?}].
  Future<void> contar(List<Map<String, dynamic>> resultados);
}

/// El de verdad: GET y POST /api/v1/canales/recorrido/.
class ServidorEnLaApi implements ServidorDelRecorrido {
  ServidorEnLaApi(this.api);

  final ApiCliente api;

  @override
  Future<(List<FuenteARevisar>, int)> pedir(int cantidad) async {
    final datos = await api.get(
      'canales/recorrido/',
      parametros: {'cantidad': '$cantidad', 'formatos': 'hls,dash,directo,rtsp'},
    ) as Map<String, dynamic>;
    final fuentes = [
      for (final f in datos['fuentes'] as List? ?? []) FuenteARevisar(f as Map<String, dynamic>),
    ];
    return (fuentes, (datos['quedan'] as num?)?.toInt() ?? fuentes.length);
  }

  @override
  Future<void> contar(List<Map<String, dynamic>> resultados) async {
    await api.post('canales/recorrido/', {'resultados': resultados});
  }
}

/// Una línea de "lo último que se probó".
class Probado {
  const Probado(this.canal, this.prueba);

  final String canal;
  final Prueba prueba;
}

class Recorrido extends ChangeNotifier {
  Recorrido(
    this.servidor,
    this.probar, {
    this.pausaEntreCanales = const Duration(seconds: 2),
    this.esperaSinConexion = const Duration(seconds: 60),
  });

  final ServidorDelRecorrido servidor;
  final Probador probar;

  /// Entre un canal y el siguiente: que el panel de la señal suelte la conexión.
  final Duration pausaEntreCanales;

  /// Sin internet o sin servidor, cuánto se espera para seguir.
  final Duration esperaSinConexion;

  /// De a cuántas se piden, y cada cuántas se le cuenta al servidor.
  static const _porPedido = 20;
  static const _porEnvio = 5;
  static const _ultimosQueSeMuestran = 8;

  bool corriendo = false;
  bool terminado = false;

  /// Qué está haciendo, para mostrar.
  String estado = 'Detenido.';
  FuenteARevisar? actual;
  VideoPlayerController? video;
  int probadas = 0;
  int andan = 0;
  int fallan = 0;
  int? quedan;
  final List<Probado> ultimos = [];

  final List<Map<String, dynamic>> _porContar = [];
  bool _cerrado = false;

  /// Cada vez que se empieza: si se para y se vuelve a empezar, la vuelta vieja se termina sola.
  int _vuelta = 0;

  void empezar() {
    if (corriendo || _cerrado) return;
    corriendo = true;
    terminado = false;
    estado = 'Buscando qué probar...';
    _avisar();
    unawaited(_recorrer(++_vuelta));
  }

  void parar() {
    if (!corriendo) return;
    corriendo = false;
    _vuelta++;
    estado = 'Detenido.';
    unawaited(_contar());
    _avisar();
  }

  bool _sigue(int vuelta) => corriendo && vuelta == _vuelta && !_cerrado;

  Future<void> _recorrer(int vuelta) async {
    while (_sigue(vuelta)) {
      final List<FuenteARevisar> tanda;
      try {
        final (fuentes, total) = await servidor.pedir(_porPedido);
        tanda = fuentes;
        quedan = total;
      } on ApiError catch (error) {
        if (!_sigue(vuelta)) return;
        estado = '${error.detalle} Se vuelve a intentar en un minuto.';
        _avisar();
        await Future<void>.delayed(esperaSinConexion);
        continue;
      }
      if (!_sigue(vuelta)) return;
      if (tanda.isEmpty) {
        corriendo = false;
        terminado = true;
        actual = null;
        estado = 'Listo: no queda nada por probar hoy. Mañana se puede volver a recorrer.';
        _avisar();
        return;
      }
      for (final fuente in tanda) {
        if (!_sigue(vuelta)) return;
        actual = fuente;
        estado = 'Probando ${fuente.canal}...';
        _avisar();
        final prueba = await probar(fuente, _mostrar);
        if (!_sigue(vuelta)) return;
        if (prueba.sinInternet) {
          // No es la señal: este aparato se quedó sin internet. No se cuenta; se espera y se sigue.
          estado = 'Este aparato se quedó sin internet. Se sigue en un minuto.';
          _avisar();
          await Future<void>.delayed(esperaSinConexion);
          break; // se vuelve a pedir: la que no se pudo probar sigue pendiente
        }
        _anotar(fuente, prueba);
        if (_porContar.length >= _porEnvio) await _contar();
        await Future<void>.delayed(pausaEntreCanales);
      }
      await _contar();
    }
  }

  void _anotar(FuenteARevisar fuente, Prueba prueba) {
    probadas++;
    prueba.anduvo ? andan++ : fallan++;
    if (quedan != null && quedan! > 0) quedan = quedan! - 1;
    ultimos.insert(0, Probado(fuente.canal, prueba));
    if (ultimos.length > _ultimosQueSeMuestran) ultimos.removeLast();
    _porContar.add({
      'id': fuente.fuente.id,
      'anduvo': prueba.anduvo,
      if (!prueba.anduvo) 'motivo': prueba.motivo,
      if (prueba.detalle.isNotEmpty) 'detalle': prueba.detalle,
    });
    _avisar();
  }

  /// Le cuenta al servidor lo que falta contar. Si no se puede, queda para la próxima.
  Future<void> _contar() async {
    if (_porContar.isEmpty) return;
    final envio = List<Map<String, dynamic>>.of(_porContar);
    _porContar.clear();
    try {
      await servidor.contar(envio);
    } on ApiError {
      _porContar.insertAll(0, envio);
    }
  }

  void _mostrar(VideoPlayerController? nuevo) {
    video = nuevo;
    _avisar();
  }

  void _avisar() {
    if (!_cerrado) notifyListeners();
  }

  @override
  void dispose() {
    corriendo = false;
    _vuelta++;
    unawaited(_contar());
    _cerrado = true;
    super.dispose();
  }
}

/// Cuánto tiene que verse el video (reproduciendo, sin quedarse cargando) para
/// contar como que anda, y cuánto se espera eso como mucho después de arrancar.
/// Es lo mismo que el reproductor de la app toma como "se ve" ([ControlSenal]):
/// la posición no sirve, porque en vivo no avanza como en una película.
const vistoQueAlcanza = Duration(seconds: 6);
const esperaParaVerse = Duration(seconds: 20);

/// La prueba de verdad: la abre con el reproductor de la app, igual que un
/// cliente (mismas cabeceras y esperas que [ControlSenal]), sin sonido, y se
/// fija que se vea [alcanza] seguido. Después la cierra del todo.
Future<Prueba> probarConElReproductor(
  FuenteARevisar fuente,
  void Function(VideoPlayerController?) mostrar, {
  Duration alcanza = vistoQueAlcanza,
  Duration esperaMaxima = esperaParaVerse,
}) async {
  // Solo llegan HLS, DASH, video directo y RTSP: la dirección es la del video (no hay que resolverla)
  final senal = Senal(url: fuente.fuente.url, tipo: fuente.fuente.tipo, cabeceras: fuente.fuente.cabeceras);
  final espera = ControlSenal.esperaDeArranque(enVivo: fuente.enVivo, tipo: fuente.fuente.tipo);
  // En vivo, un video directo (Xtream) se prueba dos veces antes de darlo por fallado: es intermitente
  final intentos = fuente.enVivo && fuente.fuente.tipo == 'directo' ? 2 : 1;
  Prueba? prueba;
  for (var intento = 0; intento < intentos; intento++) {
    prueba = await _probarUnaVez(senal, espera, mostrar, alcanza, esperaMaxima);
    if (prueba.anduvo || prueba.sinInternet || prueba.motivo == Falla.formato.motivo) return prueba;
    if (intento < intentos - 1) await Future<void>.delayed(const Duration(seconds: 1));
  }
  return prueba!;
}

Future<Prueba> _probarUnaVez(
  Senal senal,
  Duration espera,
  void Function(VideoPlayerController?) mostrar,
  Duration alcanza,
  Duration esperaMaxima,
) async {
  final video = VideoPlayerController.networkUrl(
    Uri.parse(senal.url),
    formatHint: senal.formato,
    httpHeaders: senal.cabeceras,
    viewType: ControlSenal.enSuperficie ? VideoViewType.platformView : VideoViewType.textureView,
  );
  try {
    await video.initialize().timeout(espera);
    await video.setVolume(0);
    await video.play();
    mostrar(video);
    const paso = Duration(milliseconds: 250);
    var visto = Duration.zero;
    final hasta = DateTime.now().add(esperaMaxima);
    while (DateTime.now().isBefore(hasta)) {
      await Future<void>.delayed(paso);
      final valor = video.value;
      if (valor.hasError) {
        return Prueba.fallo(Falla.de(PlatformException(code: 'video', message: valor.errorDescription)));
      }
      // Se ve: reproduciendo y sin quedarse cargando (si se frena, se vuelve a contar desde cero)
      visto = valor.isPlaying && !valor.isBuffering ? visto + paso : Duration.zero;
      if (visto >= alcanza) return const Prueba.anduvo();
    }
    return Prueba.fallo(Falla.trabada);
  } catch (error) {
    return Prueba.fallo(Falla.de(error));
  } finally {
    mostrar(null);
    await video.dispose();
  }
}
