/// La presentación al abrir la app (como la de Netflix o Disney): un video de
/// Kairos TV de ocho segundos, con su sonido incorporado.
///
/// Va ENCIMA de la app (ver main.dart): mientras se reproduce, por debajo ya se
/// cargan la sesión y el catálogo, así no se pierde tiempo. Después se desvanece.
///
///   assets/bienvenida/intro_tv.mp4        TV y celular acostado (1920×1080)
///   assets/bienvenida/intro_celular.mp4   celular parado (1080×1920)
///
/// Para que al abrir se vea DIRECTAMENTE el video (y no antes otro logo),
/// Android arranca con una pantalla lisa del mismo color de fondo (ver
/// android/app/src/main/res: launch_background y values-v31/styles.xml). Flutter
/// espera a que el reproductor tenga listo el primer cuadro antes de dibujar.
///
/// Solo se muestra al abrir la app de cero, no al volver a ella. Si el video no
/// se puede iniciar, se deja pasar a la app inmediatamente.
///
/// Fluidez: mientras el video tapa todo, la app de abajo se arma (carga la
/// sesión y el catálogo) pero NO se dibuja ([Offstage]): si no, la placa de
/// video de un TV box tendría que pintar las dos cosas en cada cuadro y el
/// video se trababa. Los botones del control tampoco le llegan (si no,
/// tocarían a ciegas el login de abajo).
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:video_player/video_player.dart';

import 'aparato.dart';

class Bienvenida extends StatefulWidget {
  const Bienvenida({super.key, required this.child, this.esperarElVideo = true});

  final Widget child;

  /// Demora el primer cuadro de Flutter hasta que el video esté preparado.
  /// En las pruebas se desactiva para que el motor no quede esperando.
  final bool esperarElVideo;

  static const duracion = Duration(seconds: 8);
  static const desvanecer = Duration(milliseconds: 450);

  /// El mismo color de la pantalla de arranque nativa de Android.
  static const fondo = Color(0xFF07090C);

  static const videoTv = 'assets/bienvenida/intro_tv.mp4';
  static const videoCelular = 'assets/bienvenida/intro_celular.mp4';

  @override
  State<Bienvenida> createState() => _BienvenidaState();
}

class _BienvenidaState extends State<Bienvenida> {
  VideoPlayerController? _video;
  Timer? _reloj;
  bool _visible = true;
  bool _terminada = false;
  bool _preparando = false;
  bool _primerCuadroDemorado = false;

  /// Las teclas que se apretaron durante el video: también se descarta su
  /// "soltar", aunque llegue cuando el video ya terminó.
  final _tragadas = <PhysicalKeyboardKey>{};

  @override
  void initState() {
    super.initState();
    if (widget.esperarElVideo) {
      WidgetsBinding.instance.deferFirstFrame();
      _primerCuadroDemorado = true;
    }
    HardwareKeyboard.instance.addHandler(_tecla);
  }

  /// Mientras se ve el video, el control no hace nada.
  bool _tecla(KeyEvent evento) {
    if (evento is KeyDownEvent && _visible && !_terminada) {
      _tragadas.add(evento.physicalKey);
      return true;
    }
    if (_tragadas.contains(evento.physicalKey)) {
      if (evento is KeyUpEvent) _tragadas.remove(evento.physicalKey);
      return true;
    }
    return false;
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_preparando) _prepararVideo();
  }

  /// En TV siempre se usa el video horizontal. En celular se elige según la
  /// orientación física para que nunca se estire ni queden barras negras.
  static String _asset(BuildContext context) {
    final tamanio = View.of(context).physicalSize;
    final vertical = tamanio.height > tamanio.width;
    return Aparato.esTv || !vertical ? Bienvenida.videoTv : Bienvenida.videoCelular;
  }

  Future<void> _prepararVideo() async {
    _preparando = true;
    final controlador = VideoPlayerController.asset(
      _asset(context),
      videoPlayerOptions: VideoPlayerOptions(mixWithOthers: false),
    );

    try {
      await controlador.initialize().timeout(const Duration(seconds: 3));
      await controlador.setLooping(false);
      await controlador.setVolume(1);

      if (!mounted) {
        await controlador.dispose();
        return;
      }

      setState(() => _video = controlador);
      _dejarDibujar();
      await controlador.play();

      // El desvanecido ocupa los últimos 450 ms: video y audio terminan juntos.
      _reloj = Timer(Bienvenida.duracion - Bienvenida.desvanecer, () {
        if (mounted) setState(() => _visible = false);
      });
    } catch (_) {
      await controlador.dispose();
      _dejarDibujar();
      if (mounted) {
        setState(() {
          _video = null;
          _visible = false;
          _terminada = true;
        });
      }
    }
  }

  void _dejarDibujar() {
    if (!_primerCuadroDemorado) return;
    _primerCuadroDemorado = false;
    WidgetsBinding.instance.allowFirstFrame();
  }

  @override
  void dispose() {
    HardwareKeyboard.instance.removeHandler(_tecla);
    _dejarDibujar();
    _reloj?.cancel();
    _video?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // La app no se dibuja mientras el video la tapa entero (sí cuando se desvanece)
    final tapada = _visible && _video != null;
    return Stack(
      textDirection: TextDirection.ltr,
      children: [
        Offstage(offstage: tapada, child: widget.child),
        if (!_terminada)
          Positioned.fill(
            child: AbsorbPointer(
              absorbing: _visible,
              child: AnimatedOpacity(
                opacity: _visible ? 1 : 0,
                duration: Bienvenida.desvanecer,
                curve: Curves.easeOut,
                onEnd: () {
                  if (!_visible && mounted) {
                    // Primero se saca el video de la pantalla, después se suelta el reproductor
                    final video = _video;
                    setState(() {
                      _terminada = true;
                      _video = null;
                    });
                    WidgetsBinding.instance.addPostFrameCallback((_) => video?.dispose());
                  }
                },
                child: ColoredBox(
                  color: Bienvenida.fondo,
                  child: _video == null ? const SizedBox.expand() : _VideoPantalla(controlador: _video!),
                ),
              ),
            ),
          ),
      ],
    );
  }
}

class _VideoPantalla extends StatelessWidget {
  const _VideoPantalla({required this.controlador});

  final VideoPlayerController controlador;

  @override
  Widget build(BuildContext context) {
    final tamanio = controlador.value.size;
    // La presentación va por encima de MaterialApp, donde todavía no se sabe hacia dónde se lee. El
    // reproductor de la PC (media_kit) lo necesita: sin esto fallaba al armarse y solo se oía el sonido.
    return Directionality(
      textDirection: TextDirection.ltr,
      child: ClipRect(
        child: SizedBox.expand(
          child: FittedBox(
            fit: BoxFit.cover,
            child: SizedBox(width: tamanio.width, height: tamanio.height, child: VideoPlayer(controlador)),
          ),
        ),
      ),
    );
  }
}
