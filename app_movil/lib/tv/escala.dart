/// En la TV, la app se dibuja SIEMPRE en un lienzo de 1920×1080 (las medidas
/// del diseño, diseno_kairos_tv/) y se agranda o achica para llenar la
/// pantalla. Así se ve igual en un televisor HD, Full HD o 4K: Android le
/// dice a Flutter que una TV Full HD mide 960×540, y con las medidas del
/// diseño todo quedaría el doble de grande.
library;

import 'package:flutter/material.dart';

import '../aparato.dart';

const anchoTv = 1920.0;

class EscalaTv extends StatelessWidget {
  const EscalaTv({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final medidas = MediaQuery.of(context);
    if (medidas.size.width <= 0) return child;
    final escala = medidas.size.width / anchoTv;
    final alto = medidas.size.height / escala;
    return FittedBox(
      fit: BoxFit.contain,
      alignment: Alignment.topLeft,
      child: SizedBox(
        width: anchoTv,
        height: alto,
        child: MediaQuery(
          data: medidas.copyWith(
            size: Size(anchoTv, alto),
            devicePixelRatio: medidas.devicePixelRatio * escala,
            padding: medidas.padding / escala,
            viewPadding: medidas.viewPadding / escala,
            viewInsets: medidas.viewInsets / escala,
            // En la TV las letras no se agrandan con la accesibilidad del sistema: ya son grandes
            textScaler: TextScaler.noScaling,
          ),
          child: child,
        ),
      ),
    );
  }
}

/// Para lo que dibuja ANDROID directamente (el video "en superficie", el
/// navegador de YouTube): Android no se entera del achique de [EscalaTv] y
/// lo armaba al doble. En un video 16:9 no se notaba (ocupa toda la
/// pantalla), pero en uno "cuadrado" (4:3) el video quedaba corrido y más
/// grande, y tapaba la parte derecha de la barra de controles. Esto lo arma
/// del tamaño REAL de la pantalla y lo agranda después. Fuera de la TV (sin
/// achique) no hace nada.
///
/// En la tele del celular ("Ver en la tele", lib/tele/) YouTube dibuja con la
/// densidad de [Aparato.densidadDeVistas]: la de la tele, si PantallaTele.kt le
/// pudo dar el contexto de la tele (desde la 1.2.27), y si no la del celular
/// (la cuenta lo compensa).
class TamanioReal extends StatelessWidget {
  const TamanioReal({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final vista = View.of(context);
    final anchoReal = vista.physicalSize.width / vista.devicePixelRatio; // una TV Full HD dice 960
    final densidad = Aparato.densidadDeVistas > 0 ? Aparato.densidadDeVistas : vista.devicePixelRatio;
    final escala = anchoReal <= 0
        ? 1.0
        // 1920 / 960 = 2 (y en la tele del celular, por cuánto difieren las dos densidades)
        : MediaQuery.sizeOf(context).width / anchoReal * densidad / vista.devicePixelRatio;
    if ((escala - 1).abs() <= .01) return child;
    return LayoutBuilder(
      builder: (context, limites) => FittedBox(
        fit: BoxFit.fill,
        child: SizedBox(width: limites.maxWidth / escala, height: limites.maxHeight / escala, child: child),
      ),
    );
  }
}
