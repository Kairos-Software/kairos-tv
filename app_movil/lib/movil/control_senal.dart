/// Reproduce un canal, película o capítulo probando sus fuentes en orden:
/// si una no arranca, da error o se queda trabada cargando, pasa sola a la
/// siguiente (failover) y le avisa al servidor que esa falló y por qué (ver
/// [Falla]). Si ninguna anda, queda con [error]: el motivo de la última, y
/// se anota en [NoAnda] (deja de mostrarse en este aparato por un tiempo),
/// salvo que haya llegado a verse bien: entonces fue un corte de la señal.
///
/// Además:
///   - Sin imagen: si a los pocos segundos el video suena pero no tiene imagen
///     (el aparato no sabe mostrar ese video), se toma como falla de formato.
///   - Cortes: si una fuente venía andando bien y se corta, primero se
///     reconecta a la MISMA (suele ser un microcorte o un link con vencimiento
///     que se renueva al volver a pedirlo); una película sigue donde iba. En
///     vivo, si se caen todas, se vuelve a recorrerlas antes de rendirse.
///   - Lo más visto: cuenta el tiempo que el video se ve de verdad (no en
///     pausa ni cargando) y se lo pasa al [Medidor], que se lo manda al servidor.
///   - [enSuperficie]: el video se dibuja en una superficie de Android
///     (SurfaceView) en vez de una textura. En muchos TV box la textura muestra
///     la imagen verde o negra con el sonido bien; es lo que usa la TV.
///
/// Lo usan el reproductor chico de "En vivo" y los de pantalla completa.
///
///     final control = ControlSenal(api)..addListener(() => setState(() {}));
///     await control.abrir(canal);            // o abrir(pelicula, desde: Duration(minutes: 24))
///     VideoPlayer(control.video!)
library;

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:video_player/video_player.dart';

import '../api/cliente.dart';
import '../api/modelos.dart';
import '../senales.dart';
import 'ajustes_video.dart';
import 'datos.dart';
import 'medidor.dart';

class ControlSenal extends ChangeNotifier {
  ControlSenal(this.api);

  /// Cuánto se espera a que arranque. Una película o capítulo es un archivo
  /// grande y tarda más en empezar que un canal en vivo.
  static const _esperaVivo = Duration(seconds: 15);
  static const _esperaArchivo = Duration(seconds: 30);
  static const _esperaTrabado = Duration(seconds: 20);

  /// Cuánto se espera a que aparezca la imagen después de arrancar.
  static const _esperaImagen = Duration(seconds: 8);

  /// Cuánto tiene que andar sin problemas una fuente para contar como "andaba"
  /// (y que, si se corta, se reconecte a ella antes de pasar a otra).
  static const _esperaEstable = Duration(seconds: 20);
  static const _maximoReconexiones = 2;

  /// En vivo: cuántas veces se vuelve a recorrer todas las fuentes si se caen.
  static const _maximoVueltas = 2;
  static const _esperaEntreVueltas = Duration(seconds: 3);

  /// Dibujar el video en una superficie de Android (ver arriba). Lo decide
  /// Biblioteca.videoEnSuperficie (Mi cuenta en la TV).
  static bool enSuperficie = false;

  /// Cómo se acomoda la imagen en la pantalla (Ajustar / Llenar / Estirar).
  /// Vale para todo lo que se vea mientras la app está abierta.
  static AjusteImagen ajuste = AjusteImagen.ajustar;

  /// La calidad y el idioma que se eligieron para lo que se está viendo
  /// (null = automática / el del video). Se olvidan al cambiar de fuente.
  String? calidadElegida;
  String? idiomaElegido;

  final ApiCliente api;

  /// Se llama cuando un canal en vivo empieza a verse (para "Últimos canales vistos").
  void Function(Canal canal)? alVerCanal;

  Canal? canal;
  VideoPlayerController? video;
  String? error;
  int fuente = 0;
  bool _cerrado = false;

  /// Sube cada vez que se empieza a probar una fuente: si mientras una carga
  /// se cambia de canal, su resultado (que llega tarde) se descarta.
  int _intento = 0;
  Timer? _vigiaTrabado;
  Timer? _vigiaImagen;
  Timer? _vigiaEstable;
  Duration? _desde;
  double _volumen = 1;
  Falla? _ultimaFalla;

  /// La fuente actual anduvo bien un rato ([_esperaEstable]).
  bool _andaba = false;

  /// Alguna fuente de este canal llegó a andar bien.
  bool _seVio = false;

  /// Cuántos canales seguidos no anduvieron en este aparato (vuelve a 0
  /// cuando uno anda bien un rato). Si son varios, o si el aparato no pudo
  /// arrancar la imagen, en la TV se sugiere reiniciarla: hay televisores
  /// (ej. Philips con Android TV 10) cuyo decodificador de video se traba
  /// tras días en espera y muestran casi todo en verde o sin imagen.
  static int canalesSinAndar = 0;

  /// Cuántos canales seguidos sin andar alcanzan para sugerir reiniciar la TV.
  static const _sinAndarParaSugerir = 2;

  bool get sugerirReiniciarAparato =>
      error != null && (canalesSinAndar >= _sinAndarParaSugerir || _ultimaFalla?.motivo == Falla.formato.motivo);
  int _reconexiones = 0;
  int _vueltas = 0;

  /// Lo más visto: desde cuándo se está viendo (null = no se ve: pausa,
  /// cargando...), cuánto se vio desde que se abrió y si ya contó como vista.
  DateTime? _seVeDesde;
  Duration _vistoDeEstaVez = Duration.zero;
  bool _vistaContada = false;

  bool get _enVivo => canal?.contenido == 'vivo';

  Duration get _esperaInicio => _enVivo ? _esperaVivo : _esperaArchivo;

  /// Las que abre este reproductor. Las de YouTube oficial ("yt_video") no:
  /// van en el reproductor de YouTube (reproductor_youtube.dart).
  List<FuenteCanal> get fuentes => [
    for (final fuente in canal?.fuentesReproducibles ?? const <FuenteCanal>[])
      if (fuente.tipo != 'yt_video') fuente,
  ];

  bool get cargando => error == null && (video == null || video!.value.isBuffering);

  bool get silenciado => _volumen == 0;

  /// Empieza a reproducir [nuevo] (corta lo que estaba). [desde]: para seguir donde se dejó.
  Future<void> abrir(Canal nuevo, {Duration? desde}) {
    _medir(seVe: false);
    canal = nuevo;
    _vistoDeEstaVez = Duration.zero;
    _vistaContada = false;
    _desde = desde;
    _empezarDeCero();
    return _probar(0);
  }

  /// Vuelve a intentar desde la primera fuente.
  Future<void> reintentar() {
    _empezarDeCero();
    return _probar(0);
  }

  void _empezarDeCero() {
    _ultimaFalla = null;
    _seVio = false;
    _reconexiones = 0;
    _vueltas = 0;
  }

  void _cancelarVigias() {
    _vigiaTrabado?.cancel();
    _vigiaTrabado = null;
    _vigiaImagen?.cancel();
    _vigiaEstable?.cancel();
  }

  /// Pasa a una fuente en particular (el usuario la eligió).
  Future<void> usarFuente(int indice) => _probar(indice);

  Future<void> _probar(int indice) async {
    final intento = ++_intento;
    _cancelarVigias();
    final anterior = video;
    video = null;
    fuente = indice;
    error = null;
    _andaba = false;
    calidadElegida = null;
    idiomaElegido = null;
    _avisar();
    await anterior?.dispose();
    if (intento != _intento || _cerrado) return;

    // En vivo, si ya se había visto y se cayeron todas: otra vuelta en un ratito
    if (indice >= fuentes.length && _enVivo && _seVio && _vueltas < _maximoVueltas && fuentes.isNotEmpty) {
      _vueltas++;
      _vigiaEstable = Timer(_esperaEntreVueltas, () {
        if (intento == _intento && !_cerrado) _probar(0);
      });
      return;
    }

    if (indice >= fuentes.length) {
      error = fuentes.isEmpty
          ? 'Este canal no tiene una señal que la app pueda reproducir.'
          : (_ultimaFalla?.mensaje ?? Falla.conexion.mensaje);
      final falla = _ultimaFalla;
      if (esconderDespuesDe(falla, hayFuentes: fuentes.isNotEmpty, seVio: _seVio)) {
        NoAnda.anotar(canal!, deFormato: falla!.motivo == Falla.formato.motivo);
        canalesSinAndar++;
      }
      _avisar();
      return;
    }

    final elegida = fuentes[indice];
    final Senal senal;
    try {
      // YouTube, Twitch...: primero hay que averiguar dónde está el video (ver senales.dart)
      senal = await resolverSenal(elegida, api).timeout(_esperaInicio);
    } catch (e) {
      if (intento == _intento && !_cerrado) {
        _avisarFalla(elegida, Falla.de(e));
        _probar(indice + 1);
      }
      return;
    }
    if (intento != _intento || _cerrado) return;

    final nuevo = VideoPlayerController.networkUrl(
      Uri.parse(senal.url),
      formatHint: senal.formato,
      httpHeaders: senal.cabeceras, // como un navegador (o VLC): algunos canales rechazan a ExoPlayer
      viewType: enSuperficie ? VideoViewType.platformView : VideoViewType.textureView,
    );
    try {
      await nuevo.initialize().timeout(_esperaInicio);
    } catch (e) {
      await nuevo.dispose();
      if (intento == _intento && !_cerrado) {
        _avisarFalla(elegida, Falla.de(e));
        _probar(indice + 1);
      }
      return;
    }
    if (intento != _intento || _cerrado) {
      await nuevo.dispose();
      return;
    }
    final desde = _desde;
    if (desde != null && desde > Duration.zero && nuevo.value.duration > desde) {
      await nuevo.seekTo(desde);
    }
    _desde = null;
    await nuevo.setVolume(_volumen);
    nuevo.addListener(_vigilar);
    await nuevo.play();
    video = nuevo;
    if (_enVivo) alVerCanal?.call(canal!);
    _avisar();

    // ¿Aparece la imagen? (las radios no tienen: no se controlan)
    if (_deberiaTenerImagen(elegida)) {
      _vigiaImagen = Timer(_esperaImagen, () {
        if (_cerrado || video != nuevo || nuevo.value.hasError) return;
        if (nuevo.value.size.isEmpty) _fallo(nuevo, Falla.sinImagen, reconectar: false);
      });
    }
    // Si anda bien un rato, "andaba": ante un corte se reconecta a esta misma
    _vigiaEstable = Timer(_esperaEstable, () {
      if (_cerrado || video != nuevo || nuevo.value.hasError) return;
      _andaba = true;
      _seVio = true;
      canalesSinAndar = 0;
      _reconexiones = 0;
      _vueltas = 0;
    });
  }

  /// Si no anduvo ninguna fuente, ¿deja de mostrarse en este aparato por un
  /// tiempo ([NoAnda])? No si el problema es la conexión del aparato, ni si
  /// llegó a verse bien y después se cortó: en este aparato SÍ anda, la señal
  /// tuvo un corte (suele volver enseguida, o la estaba usando otro aparato).
  static bool esconderDespuesDe(Falla? falla, {required bool hayFuentes, required bool seVio}) =>
      hayFuentes && falla != null && falla.motivo != Falla.sinInternet.motivo && !seVio;

  /// Las radios (solo audio) no tienen imagen y está bien.
  bool _deberiaTenerImagen(FuenteCanal elegida) {
    final ruta = Uri.tryParse(elegida.url)?.path.toLowerCase() ?? '';
    if (RegExp(r'\.(mp3|aac|m4a|ogg|opus)$').hasMatch(ruta)) return false;
    return !RegExp(r'\bradio', caseSensitive: false).hasMatch(canal?.categoria ?? '');
  }

  /// Si la señal da error, se queda cargando demasiado o (en vivo) termina,
  /// reconecta o pasa a la siguiente fuente.
  void _vigilar() {
    final actual = video;
    if (actual == null || _cerrado) return;
    _medir(seVe: actual.value.isPlaying && !actual.value.isBuffering && !actual.value.hasError);
    if (actual.value.hasError) {
      _fallo(actual, Falla.de(actual.value.errorDescription ?? ''));
      return;
    }
    // Una señal en vivo no "termina": si terminó, se cortó
    if (_enVivo && actual.value.isCompleted) {
      _fallo(actual, Falla.cortada);
      return;
    }
    if (actual.value.isBuffering) {
      _vigiaTrabado ??= Timer(_esperaTrabado, () {
        _vigiaTrabado = null;
        if (!_cerrado && video == actual && actual.value.isBuffering) _fallo(actual, Falla.trabada);
      });
    } else {
      _vigiaTrabado?.cancel();
      _vigiaTrabado = null;
    }
    _avisar();
  }

  /// Lo más visto: suma el rato que pasó desde el último aviso del video, si
  /// se estaba viendo. El video avisa cada medio segundo mientras se
  /// reproduce: si pasó mucho más (la app estuvo en segundo plano), no se cuenta.
  void _medir({required bool seVe}) {
    final ahora = DateTime.now();
    final desde = _seVeDesde;
    _seVeDesde = seVe ? ahora : null;
    final actual = canal;
    if (desde == null || actual == null) return;
    final rato = ahora.difference(desde);
    if (rato > const Duration(seconds: 5)) return;
    Medidor.sumar(api, actual.id, rato);
    _vistoDeEstaVez += rato;
    if (!_vistaContada && _vistoDeEstaVez >= Medidor.paraUnaVista) {
      _vistaContada = true;
      Medidor.contarVista(actual.id);
    }
  }

  /// La fuente actual falló mientras se veía. Si venía andando bien, se
  /// reconecta a la misma (una película, desde donde iba); si no, se avisa
  /// al servidor y se pasa a la siguiente.
  void _fallo(VideoPlayerController actual, Falla falla, {bool reconectar = true}) {
    actual.removeListener(_vigilar);
    if (reconectar && _andaba && _reconexiones < _maximoReconexiones && falla.motivo != Falla.formato.motivo) {
      _reconexiones++;
      if (!_enVivo) _desde = actual.value.position;
      _probar(fuente);
      return;
    }
    _avisarFalla(fuentes[fuente], falla);
    _probar(fuente + 1);
  }

  /// Le avisa al servidor que esta fuente no anduvo y por qué. El servidor la
  /// vuelve a probar por su cuenta y, si también le falla (o si falla en varios
  /// aparatos), deja de mandarla. No se espera la respuesta.
  void _avisarFalla(FuenteCanal fuente, Falla falla) {
    _ultimaFalla = falla;
    // Si el problema es la conexión de este aparato, la señal no tiene la culpa
    if (falla.motivo == Falla.sinInternet.motivo) return;
    api
        .post('canales/fuentes/${fuente.id}/falla/', {'motivo': falla.motivo, 'detalle': falla.detalle})
        .catchError((Object _) => null);
  }

  void alternarPausa() {
    final actual = video;
    if (actual == null) return;
    actual.value.isPlaying ? actual.pause() : actual.play();
    _avisar();
  }

  void alternarSonido() {
    _volumen = _volumen == 0 ? 1 : 0;
    video?.setVolume(_volumen);
    _avisar();
  }

  // ── Ajustes (ajustes_video.dart) ──

  /// Las calidades que ofrece la señal, de mayor a menor (vacía si no hay para elegir).
  Future<List<Calidad>> calidades() async {
    final actual = video;
    if (actual == null || !actual.isVideoTrackSupportAvailable()) return const [];
    try {
      return Calidad.ordenadas((await actual.getVideoTracks()).where((p) => (p.height ?? 0) > 0));
    } catch (_) {
      return const [];
    }
  }

  /// null = automática (el reproductor la elige según la velocidad de internet).
  Future<void> elegirCalidad(Calidad? calidad) async {
    final actual = video;
    if (actual == null) return;
    calidadElegida = calidad?.pista.id;
    _avisar();
    try {
      await actual.selectVideoTrack(calidad?.pista);
    } catch (_) {}
  }

  /// Los audios del video (idiomas).
  Future<List<VideoAudioTrack>> idiomas() async {
    final actual = video;
    if (actual == null || !actual.isAudioTrackSupportAvailable()) return const [];
    try {
      return await actual.getAudioTracks();
    } catch (_) {
      return const [];
    }
  }

  Future<void> elegirIdioma(String id) async {
    final actual = video;
    if (actual == null) return;
    idiomaElegido = id;
    _avisar();
    try {
      await actual.selectAudioTrack(id);
    } catch (_) {}
  }

  void cambiarAjuste(AjusteImagen nuevo) {
    ajuste = nuevo;
    _avisar();
  }

  Future<void> saltar(Duration cuanto) async {
    final actual = video;
    if (actual == null) return;
    final destino = actual.value.position + cuanto;
    await actual.seekTo(destino < Duration.zero ? Duration.zero : destino);
  }

  /// Corta la reproducción (libera la conexión: hay listas IPTV que permiten una sola).
  Future<void> detener() async {
    ++_intento;
    _cancelarVigias();
    final actual = video;
    video = null;
    _avisar();
    await actual?.dispose();
  }

  void _avisar() {
    if (!_cerrado) notifyListeners();
  }

  @override
  void dispose() {
    _medir(seVe: false);
    Medidor.enviar(api); // al salir del reproductor, se avisa lo que se miró
    _cerrado = true;
    ++_intento;
    _cancelarVigias();
    video?.dispose();
    super.dispose();
  }
}

/// Por qué no se pudo reproducir una fuente: lo que se le muestra a la persona
/// y lo que se le avisa al servidor ([motivo]: formato, rechazo, tiempo,
/// conexion, error; ver canales/servicios.py -> MOTIVOS_DE_LOS_APARATOS).
class Falla {
  const Falla(this.motivo, this.mensaje, [this.detalle = '']);

  final String motivo;
  final String mensaje;

  /// Lo técnico (lo que dijo el reproductor), recortado. Para el panel.
  final String detalle;

  static const formato = Falla('formato', 'Este aparato no puede reproducir el formato de este video.');
  static const tiempo = Falla('tiempo', 'La señal tardó demasiado en arrancar. Probá de nuevo en un rato.');
  static const trabada = Falla('tiempo', 'La señal se quedó trabada cargando.');
  static const cortada = Falla('conexion', 'La señal se cortó.');
  static const sinImagen = Falla(
    'formato',
    'Este aparato no puede mostrar la imagen de esta señal (sale solo el sonido).',
    'sin imagen: el video arrancó pero no tiene imagen',
  );
  static const conexion = Falla(
    'conexion',
    'No se pudo conectar con la señal. Puede estar caída o no disponible en tu zona.',
  );
  static const sinInternet = Falla('sin_internet', 'Revisá la conexión a internet de este aparato.');

  /// Lee el error que dio el reproductor (ExoPlayer) o la espera.
  factory Falla.de(Object error) {
    if (error is TimeoutException) return tiempo;
    final texto = error is PlatformException ? '${error.message} ${error.details ?? ''}' : '$error';
    final detalle = texto.replaceAll(RegExp(r'\s+'), ' ').trim();
    final corto = detalle.length > 120 ? detalle.substring(0, 120) : detalle;
    if (RegExp(
      r'UnknownHost|Unable to resolve host|ENETUNREACH|Network is unreachable',
      caseSensitive: false,
    ).hasMatch(texto)) {
      return sinInternet;
    }
    final codigo = RegExp(r'Response code: (\d{3})').firstMatch(texto)?.group(1);
    if (codigo != null && codigo.startsWith('4')) {
      return Falla('rechazo', 'El servidor de la señal no deja verla (error $codigo).', corto);
    }
    if (RegExp(
      r'Decoder|MediaCodec|NO_UNSUPPORTED|format_supported=NO|UnrecognizedInputFormat|None of the available extractors',
      caseSensitive: false,
    ).hasMatch(texto)) {
      return Falla(formato.motivo, formato.mensaje, corto);
    }
    if (error is SenalNoDisponible) return Falla('error', error.toString(), corto);
    return Falla(conexion.motivo, conexion.mensaje, corto);
  }
}
