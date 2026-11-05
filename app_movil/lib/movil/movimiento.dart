/// El movimiento de la app en el celular (diseno_kairos_tv/propuesta-interactiva.html):
/// lo que aparece de a poco, las tarjetas que responden al dedo y las filas que
/// se curvan en 3D al deslizarlas. Solo visual. Si el aparato tiene las
/// animaciones apagadas (MediaQuery.disableAnimations), todo queda quieto.
library;

import 'package:flutter/material.dart';

import 'estilo.dart';

/// Aparece subiendo un poco, una sola vez. [orden] la hace esperar a las de antes.
class Entrada extends StatefulWidget {
  const Entrada({super.key, this.orden = 0, required this.child});

  final int orden;
  final Widget child;

  @override
  State<Entrada> createState() => _EntradaState();
}

class _EntradaState extends State<Entrada> with SingleTickerProviderStateMixin, AutomaticKeepAliveClientMixin {
  static const _espera = Duration(milliseconds: 70);
  static const _duracion = Duration(milliseconds: 520);

  late final AnimationController _control = AnimationController(
    vsync: this,
    duration: _duracion + _espera * widget.orden,
  );
  late final Animation<double> _avance = CurvedAnimation(
    parent: _control,
    curve: Interval(
      (_espera * widget.orden).inMilliseconds / _control.duration!.inMilliseconds,
      1,
      curve: Curves.easeOutCubic,
    ),
  );

  // Que no vuelva a aparecer cada vez que la lista la saca y la trae al desplazarse
  @override
  bool get wantKeepAlive => true;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_control.isCompleted || _control.isAnimating) return;
    if (MediaQuery.disableAnimationsOf(context)) {
      _control.value = 1;
    } else {
      _control.forward();
    }
  }

  @override
  void dispose() {
    _control.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return AnimatedBuilder(
      animation: _avance,
      child: widget.child,
      builder: (_, hijo) => Opacity(
        opacity: _avance.value,
        child: Transform.translate(offset: Offset(0, (1 - _avance.value) * 22), child: hijo),
      ),
    );
  }
}

/// Responde al dedo: se hunde y se inclina hacia donde se apoyó. No toma el toque:
/// el botón que tiene adentro sigue funcionando igual.
class Presionable extends StatefulWidget {
  const Presionable({super.key, required this.child});

  final Widget child;

  @override
  State<Presionable> createState() => _PresionableState();
}

class _PresionableState extends State<Presionable> {
  bool _apretada = false;
  Offset _donde = Offset.zero; // de -1 a 1 en cada eje, desde el centro

  void _apretar(PointerDownEvent evento) {
    final caja = context.findRenderObject();
    if (caja is! RenderBox || !caja.hasSize) return;
    final tam = caja.size;
    setState(() {
      _apretada = true;
      _donde = Offset(
        (evento.localPosition.dx / tam.width * 2 - 1).clamp(-1.0, 1.0),
        (evento.localPosition.dy / tam.height * 2 - 1).clamp(-1.0, 1.0),
      );
    });
  }

  void _soltar([Object? _]) {
    if (_apretada) setState(() => _apretada = false);
  }

  @override
  Widget build(BuildContext context) {
    final quieta = MediaQuery.disableAnimationsOf(context);
    return Listener(
      onPointerDown: _apretar,
      onPointerUp: _soltar,
      onPointerCancel: _soltar,
      child: TweenAnimationBuilder<double>(
        tween: Tween(end: _apretada && !quieta ? 1 : 0),
        duration: const Duration(milliseconds: 160),
        curve: Curves.easeOut,
        child: widget.child,
        builder: (_, cuanto, hijo) => Transform(
          alignment: Alignment.center,
          transform: Matrix4.identity()
            ..setEntry(3, 2, .0012)
            ..rotateX(_donde.dy * .1 * cuanto)
            ..rotateY(-_donde.dx * .1 * cuanto)
            ..scaleByDouble(1 - .035 * cuanto, 1 - .035 * cuanto, 1, 1),
          child: hijo,
        ),
      ),
    );
  }
}

/// Una fila que se desliza de costado: lo que va quedando en los bordes gira y
/// se aleja, como si la fila fuera curva.
class CarruselCurvo extends StatefulWidget {
  const CarruselCurvo({
    super.key,
    required this.cantidad,
    required this.anchoItem,
    required this.alto,
    required this.item,
    this.separacion = Espacio.sm,
  });

  final int cantidad;
  final double anchoItem;
  final double alto;
  final double separacion;
  final Widget Function(BuildContext context, int indice) item;

  @override
  State<CarruselCurvo> createState() => _CarruselCurvoState();
}

class _CarruselCurvoState extends State<CarruselCurvo> {
  final ScrollController _control = ScrollController();

  @override
  void dispose() {
    _control.dispose();
    super.dispose();
  }

  /// De -1 (a la izquierda) a 1 (a la derecha), según qué tan lejos del centro está.
  double _distancia(int i, double ancho) {
    final posicion = _control.hasClients && _control.position.hasPixels ? _control.position.pixels : 0.0;
    final centro = Espacio.margen + i * (widget.anchoItem + widget.separacion) + widget.anchoItem / 2 - posicion;
    return ((centro - ancho / 2) / (ancho * .62)).clamp(-1.0, 1.0);
  }

  @override
  Widget build(BuildContext context) {
    final quieta = MediaQuery.disableAnimationsOf(context);
    return SizedBox(
      height: widget.alto,
      child: LayoutBuilder(
        builder: (context, lugar) => ListView.builder(
          controller: _control,
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.symmetric(horizontal: Espacio.margen),
          itemExtent: widget.anchoItem + widget.separacion,
          itemCount: widget.cantidad,
          // Unos píxeles de más a los costados: un item girado no se corta justo al borde
          clipBehavior: Clip.none,
          itemBuilder: (context, i) {
            final item = Padding(
              padding: EdgeInsets.only(right: widget.separacion),
              child: Align(alignment: Alignment.topCenter, child: widget.item(context, i)),
            );
            if (quieta) return item;
            return AnimatedBuilder(
              animation: _control,
              child: item,
              builder: (_, hijo) {
                final d = _distancia(i, lugar.maxWidth);
                return Transform(
                  alignment: Alignment.center,
                  transform: Matrix4.identity()
                    ..setEntry(3, 2, .0011)
                    ..translateByDouble(0, 0, -d.abs() * 36, 1)
                    ..rotateY(-d * .46),
                  child: hijo,
                );
              },
            );
          },
        ),
      ),
    );
  }
}
