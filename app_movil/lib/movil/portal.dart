/// El portal: los cuatro paneles de la marca también son una pantalla. Las
/// iniciales del canal se cortan en cuatro tiras y, al cambiar de canal, cada
/// tira corre por su lado (diseno_kairos_tv/propuesta-interactiva.html).
///
/// Las medidas son las de la marca (GeometriaMarca): los paneles no se rotan ni
/// se deforman (brand/README.md), lo único que se mueve es lo que muestran. Lo
/// usan la portada del celular y la de la TV.
library;

import 'dart:ui' as ui;

import 'package:flutter/material.dart';

import '../marca.dart';
import 'estilo.dart';

/// Las hasta tres letras del portal: "Noticias 24" → "N24", "Crónica TV" → "CT",
/// "A24" → "A24", "Actualidad" → "ACT".
String letrasDelPortal(String nombre) {
  final palabras = RegExp(r'[\p{L}\p{N}]+', unicode: true).allMatches(nombre).map((m) => m[0]!).toList();
  if (palabras.isEmpty) return '';
  final primera = palabras.first;
  if (palabras.length == 1) return (primera.length > 3 ? primera.substring(0, 3) : primera).toUpperCase();
  final segunda = palabras[1];
  final letras = primera[0] + (int.tryParse(segunda) != null ? segunda : segunda[0]);
  return (letras.length > 3 ? letras.substring(0, 3) : letras).toUpperCase();
}

class PortalCanal extends StatefulWidget {
  const PortalCanal({super.key, required this.letras});

  /// Hasta tres iniciales ("N24"); vacío, solo los paneles.
  final String letras;

  @override
  State<PortalCanal> createState() => _PortalCanalState();
}

class _PortalCanalState extends State<PortalCanal> with TickerProviderStateMixin {
  late final AnimationController _cambio = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 820),
  );
  late final AnimationController _latido = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 2200),
  );
  String _antes = ''; // al abrir, las tiras llegan desde afuera
  late String _ahora = widget.letras;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (MediaQuery.disableAnimationsOf(context)) {
      _latido.stop();
      _cambio.value = 1;
    } else {
      if (!_latido.isAnimating) _latido.repeat(reverse: true);
      if (_cambio.isDismissed) _cambio.forward();
    }
  }

  @override
  void didUpdateWidget(PortalCanal anterior) {
    super.didUpdateWidget(anterior);
    if (widget.letras == _ahora) return;
    _antes = _ahora;
    _ahora = widget.letras;
    if (MediaQuery.disableAnimationsOf(context)) {
      _cambio.value = 1;
    } else {
      _cambio.forward(from: 0);
    }
  }

  @override
  void dispose() {
    _cambio.dispose();
    _latido.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // En capas: el resplandor no se redibuja cuando corren las tiras, ni las tiras cuando late el punto
    return ExcludeSemantics(
      child: Stack(
        fit: StackFit.expand,
        children: [
          RepaintBoundary(child: CustomPaint(painter: _PintorFondo())),
          RepaintBoundary(
            child: CustomPaint(
              painter: _PintorPaneles(cambio: _cambio, antes: _antes, ahora: _ahora),
            ),
          ),
          RepaintBoundary(
            child: CustomPaint(painter: _PintorPunto(latido: _latido)),
          ),
        ],
      ),
    );
  }
}

/// Cuántos píxeles mide una unidad de la marca en [lugar] (con aire para el resplandor).
double _escalaEn(Size lugar) {
  final porAncho = lugar.width / 2;
  final porAlto = lugar.height / (2 * GeometriaMarca.mediaAltura);
  return (porAncho < porAlto ? porAncho : porAlto) * .9;
}

/// Cada panel en píxeles, con el tamaño de [lugar].
List<Path> _caminosEn(Size lugar) {
  final escala = _escalaEn(lugar);
  final centro = lugar.center(Offset.zero);
  Offset punto(double x, double y) => centro + Offset(x * escala, y * escala);
  return [
    for (final (desde, hasta) in GeometriaMarca.paneles)
      Path()
        ..moveTo(punto(desde, GeometriaMarca.techo(desde)).dx, punto(desde, GeometriaMarca.techo(desde)).dy)
        ..lineTo(punto(hasta, GeometriaMarca.techo(hasta)).dx, punto(hasta, GeometriaMarca.techo(hasta)).dy)
        ..lineTo(punto(hasta, -GeometriaMarca.techo(hasta)).dx, punto(hasta, -GeometriaMarca.techo(hasta)).dy)
        ..lineTo(punto(desde, -GeometriaMarca.techo(desde)).dx, punto(desde, -GeometriaMarca.techo(desde)).dy)
        ..close(),
  ];
}

double _grosorEn(double escala) => (GeometriaMarca.grosor * escala).clamp(GeometriaMarca.grosorMinimo, 16.0);

/// Lo que no cambia: la luz que sale por las ranuras, el resplandor y las caras de los paneles.
class _PintorFondo extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final escala = _escalaEn(size);
    final centro = size.center(Offset.zero);
    final altoMedio = GeometriaMarca.mediaAltura * escala;
    final luz = Rect.fromCircle(center: centro, radius: 1.28 * escala);
    canvas.drawRect(
      luz,
      Paint()
        ..shader = RadialGradient(colors: [Tono.celeste.withValues(alpha: .34), Tono.celeste.withValues(alpha: 0)])
            .createShader(luz),
    );
    final ranura = Rect.fromCenter(center: centro, width: .34 * escala, height: 2.2 * altoMedio);
    canvas.drawRect(
      ranura,
      Paint()
        ..shader = LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            Tono.celesteClaro.withValues(alpha: 0),
            Tono.celesteClaro.withValues(alpha: .62),
            Tono.celesteClaro.withValues(alpha: 0),
          ],
        ).createShader(ranura),
    );
    final grosor = _grosorEn(escala);
    final caras = Paint()
      ..shader = const LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: [Color(0xFF1B1B20), Tono.capaMinima],
      ).createShader(Rect.fromCenter(center: centro, width: 2 * escala, height: 2 * altoMedio));
    final halo = Paint()
      ..color = Tono.celeste.withValues(alpha: .6)
      ..style = PaintingStyle.stroke
      ..strokeWidth = grosor * 1.8
      ..maskFilter = ui.MaskFilter.blur(ui.BlurStyle.normal, grosor * 2.4);
    for (final camino in _caminosEn(size)) {
      canvas.drawPath(camino, halo);
      canvas.drawPath(camino, caras);
    }
  }

  @override
  bool shouldRepaint(_PintorFondo viejo) => false;
}

/// Las letras cortadas por los paneles y, encima, el borde celeste.
class _PintorPaneles extends CustomPainter {
  _PintorPaneles({required this.cambio, required this.antes, required this.ahora}) : super(repaint: cambio);

  final Animation<double> cambio;
  final String antes;
  final String ahora;

  /// Los del centro arrancan primero; cada tira, un poco después de la anterior.
  static const _orden = [2, 0, 1, 3];

  final Map<String, TextPainter> _letras = {};

  TextPainter _armar(String letras, double escala) {
    return _letras.putIfAbsent('$letras@$escala', () {
      TextPainter medir(double tamanio, {Paint? pintura}) => TextPainter(
        text: TextSpan(
          text: letras,
          style: TextStyle(
            fontFamily: Letra.titulos,
            fontSize: tamanio,
            fontWeight: FontWeight.w800,
            letterSpacing: -tamanio * .03,
            height: 1,
            color: pintura == null ? Tono.celesteClaro : null,
            foreground: pintura,
          ),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      final prueba = medir(100);
      // Que ocupen casi todo el ancho del portal, sin pasarse de su alto
      final porAncho = 100 * (1.82 * escala) / (prueba.width == 0 ? 1 : prueba.width);
      final tamanio = porAncho < 1.45 * escala ? porAncho : 1.45 * escala;
      final pintura = Paint()
        ..shader = const LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Tono.celesteClaro, Tono.celeste],
          stops: [.25, 1],
        ).createShader(Rect.fromLTWH(0, 0, 1, tamanio));
      return medir(tamanio, pintura: pintura);
    });
  }

  @override
  void paint(Canvas canvas, Size size) {
    final escala = _escalaEn(size);
    final centro = size.center(Offset.zero);
    final recorrido = 2 * GeometriaMarca.mediaAltura * escala;
    final borde = Paint()
      ..color = Tono.celeste
      ..style = PaintingStyle.stroke
      ..strokeWidth = _grosorEn(escala)
      ..strokeJoin = StrokeJoin.miter;
    final textoAntes = antes.isEmpty ? null : _armar(antes, escala);
    final textoAhora = ahora.isEmpty ? null : _armar(ahora, escala);
    void letras(TextPainter? texto, double corrimiento) {
      if (texto == null) return;
      canvas.save();
      canvas.translate(centro.dx - texto.width / 2, centro.dy - texto.height / 2 + corrimiento);
      texto.paint(canvas, Offset.zero);
      canvas.restore();
    }

    final caminos = _caminosEn(size);
    for (var i = 0; i < caminos.length; i++) {
      // Una tira sube y la otra baja, para que se lea como un corte
      final inicio = _orden.indexOf(i) * .08;
      final avance = Curves.easeInOutCubic.transform(((cambio.value - inicio) / (1 - .24)).clamp(0.0, 1.0));
      final sentido = i.isEven ? -1.0 : 1.0;
      canvas.save();
      canvas.clipPath(caminos[i]);
      if (avance < 1) letras(textoAntes, sentido * recorrido * avance);
      if (avance > 0) letras(textoAhora, sentido * recorrido * (avance - 1));
      canvas.restore();
      canvas.drawPath(caminos[i], borde);
    }
  }

  @override
  bool shouldRepaint(_PintorPaneles viejo) => viejo.antes != antes || viejo.ahora != ahora;
}

/// El punto rubí del centro: el momento activo, en vivo. Se mantiene quieto y solo late su luz.
class _PintorPunto extends CustomPainter {
  _PintorPunto({required this.latido}) : super(repaint: latido);

  final Animation<double> latido;

  @override
  void paint(Canvas canvas, Size size) {
    final escala = _escalaEn(size);
    final centro = size.center(Offset.zero);
    final radio = GeometriaMarca.radioPunto * escala;
    final alcance = radio * (3.1 + latido.value * 1.1);
    final luz = Rect.fromCircle(center: centro, radius: alcance);
    canvas.drawCircle(
      centro,
      alcance,
      Paint()
        ..shader = RadialGradient(colors: [Tono.rubi.withValues(alpha: .62), Tono.rubi.withValues(alpha: 0)])
            .createShader(luz),
    );
    canvas.drawCircle(centro, radio, Paint()..color = Tono.rubi);
  }

  @override
  bool shouldRepaint(_PintorPunto viejo) => false;
}
