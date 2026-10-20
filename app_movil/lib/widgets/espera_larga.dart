/// Debajo de la ruedita de "cargando": si una película tarda en arrancar, dice que es
/// el servidor preparándola y cuántos segundos van (ver [ControlSenal.avisoDeEspera]).
/// Sin esto, un minuto con la ruedita sola parece que la app se colgó.
///
/// La usan el reproductor de películas del celular y el de la TV.
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../movil/control_senal.dart';

class EsperaLarga extends StatefulWidget {
  const EsperaLarga({super.key, required this.control, this.estilo, this.ancho = 320});

  final ControlSenal control;
  final TextStyle? estilo;
  final double ancho;

  @override
  State<EsperaLarga> createState() => _EsperaLargaState();
}

class _EsperaLargaState extends State<EsperaLarga> {
  Timer? _reloj;

  @override
  void initState() {
    super.initState();
    // Cada segundo, para que el número avance aunque el video no avise nada
    _reloj = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    _reloj?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final texto = widget.control.avisoDeEspera();
    if (texto == null) return const SizedBox.shrink();
    return ConstrainedBox(
      constraints: BoxConstraints(maxWidth: widget.ancho),
      child: Text(texto, textAlign: TextAlign.center, style: widget.estilo),
    );
  }
}
