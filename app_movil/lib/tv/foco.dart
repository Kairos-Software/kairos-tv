/// El FOCO del control remoto (diseno_kairos_tv/DESIGN.md, "Foco TV"): lo
/// que está elegido se agranda un poco y tiene borde celeste con brillo, así
/// se ve desde el sillón. Todo lo que se puede elegir en la TV es un
/// [Enfocable].
///
///   - OK corto: [alOk].  OK largo (mantener apretado): [alOkLargo] (favoritos).
///   - Con el dedo (celular): tocar = OK, mantener = OK largo.
///   - Al recibir el foco, se desplaza la lista para que quede a la vista.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../movil/estilo.dart';

/// Las teclas que valen como "OK" en un control remoto o un teclado.
final teclasOk = {
  LogicalKeyboardKey.select,
  LogicalKeyboardKey.enter,
  LogicalKeyboardKey.numpadEnter,
  LogicalKeyboardKey.gameButtonA,
  LogicalKeyboardKey.space,
};

/// Lo que dura apretado OK para contar como "OK largo".
const _esperaOkLargo = Duration(milliseconds: 650);

class Enfocable extends StatefulWidget {
  const Enfocable({
    super.key,
    required this.child,
    this.alOk,
    this.alOkLargo,
    this.alEnfocar,
    this.autofocus = false,
    this.nodo,
    this.curva = Curva.grande,
    this.escala = 1.055,
    this.alTecla,
    this.etiqueta,
  });

  final Widget child;
  final VoidCallback? alOk;
  final VoidCallback? alOkLargo;

  /// Avisa cuando gana o pierde el foco.
  final ValueChanged<bool>? alEnfocar;
  final bool autofocus;
  final FocusNode? nodo;
  final double curva;

  /// Cuánto se agranda con el foco (1 = nada; los botones chicos, poco).
  final double escala;

  /// Para teclas propias (ej: flechas en la línea de tiempo del reproductor).
  final KeyEventResult Function(KeyEvent evento)? alTecla;

  /// Lo que dice el lector de pantalla.
  final String? etiqueta;

  @override
  State<Enfocable> createState() => _EnfocableState();
}

class _EnfocableState extends State<Enfocable> {
  bool _enfocado = false;
  Timer? _largo;
  bool _fueLargo = false;

  /// OK se apretó acá. Sin esto, al soltar el OK que abrió una sección desde
  /// el menú, lo "soltaba" la primera película (que ya tenía el foco) y se
  /// abría sola: parecía que el botón se tocaba dos veces.
  bool _apretado = false;

  @override
  void dispose() {
    _largo?.cancel();
    super.dispose();
  }

  void _alCambiarFoco(bool enfocado) {
    if (!enfocado) {
      _apretado = false;
      _largo?.cancel();
    }
    setState(() => _enfocado = enfocado);
    widget.alEnfocar?.call(enfocado);
    if (enfocado) {
      // Que no quede tapado ni cortado al borde de una lista
      Scrollable.ensureVisible(
        context,
        alignment: .5,
        alignmentPolicy: ScrollPositionAlignmentPolicy.explicit,
        duration: const Duration(milliseconds: 180),
        curve: Curves.easeOut,
      );
    }
  }

  KeyEventResult _alTecla(FocusNode nodo, KeyEvent evento) {
    final propia = widget.alTecla?.call(evento);
    if (propia == KeyEventResult.handled) return propia!;
    if (!teclasOk.contains(evento.logicalKey)) return KeyEventResult.ignored;
    if (widget.alOkLargo == null) {
      if (evento is KeyDownEvent) widget.alOk?.call();
      return KeyEventResult.handled;
    }
    // Con OK largo: se decide al soltar (o cuando pasa el tiempo apretado).
    // Solo cuenta si el OK se apretó acá (ver _apretado).
    if (evento is KeyDownEvent) {
      _apretado = true;
      _fueLargo = false;
      _largo?.cancel();
      _largo = Timer(_esperaOkLargo, () {
        _fueLargo = true;
        widget.alOkLargo?.call();
      });
    } else if (evento is KeyUpEvent) {
      _largo?.cancel();
      if (_apretado && !_fueLargo) widget.alOk?.call();
      _apretado = false;
    }
    return KeyEventResult.handled;
  }

  @override
  Widget build(BuildContext context) {
    final sinAnimar = MediaQuery.maybeDisableAnimationsOf(context) ?? false;
    final radio = BorderRadius.circular(widget.curva);
    return Semantics(
      button: true,
      label: widget.etiqueta,
      child: Focus(
        focusNode: widget.nodo,
        debugLabel: widget.etiqueta,
        autofocus: widget.autofocus,
        onFocusChange: _alCambiarFoco,
        onKeyEvent: _alTecla,
        child: GestureDetector(
          onTap: widget.alOk,
          onLongPress: widget.alOkLargo,
          child: AnimatedScale(
            scale: _enfocado && !sinAnimar ? widget.escala : 1,
            duration: const Duration(milliseconds: 140),
            curve: Curves.easeOut,
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 140),
              curve: Curves.easeOut,
              foregroundDecoration: _enfocado
                  ? BoxDecoration(
                      borderRadius: radio,
                      border: Border.all(color: Tono.celeste, width: 3),
                    )
                  : null,
              decoration: BoxDecoration(
                borderRadius: radio,
                boxShadow: _enfocado
                    ? [
                        BoxShadow(color: Tono.celesteClaro.withValues(alpha: .14), spreadRadius: 3),
                        BoxShadow(color: Tono.celeste.withValues(alpha: .48), blurRadius: 34),
                      ]
                    : const [],
              ),
              child: ClipRRect(borderRadius: radio, child: widget.child),
            ),
          ),
        ),
      ),
    );
  }
}

/// Un botón para la TV (y para pantallas que se usan con control, como el login).
///   principal: celeste lleno ("Reproducir").  Si no: gris con borde suave.
class BotonTv extends StatelessWidget {
  const BotonTv({
    super.key,
    required this.texto,
    required this.alOk,
    this.icono,
    this.principal = false,
    this.autofocus = false,
    this.nodo,
    this.alto = 58,
    this.ancho,
    this.color,
    this.tamanioTexto = 17,
  });

  final String texto;
  final VoidCallback? alOk;
  final IconData? icono;
  final bool principal;
  final bool autofocus;
  final FocusNode? nodo;
  final double alto;
  final double? ancho;

  /// Color del ícono (ej: el corazón rubí de favoritos).
  final Color? color;
  final double tamanioTexto;

  @override
  Widget build(BuildContext context) {
    final colorTexto = principal ? Tono.sobreCelesteOscuro : Tono.texto;
    return Enfocable(
      alOk: alOk,
      autofocus: autofocus,
      nodo: nodo,
      curva: Curva.boton,
      escala: 1.04,
      etiqueta: texto,
      child: Container(
        height: alto,
        width: ancho,
        padding: const EdgeInsets.symmetric(horizontal: 26),
        decoration: BoxDecoration(
          color: principal ? Tono.celeste : Tono.capaAlta,
          borderRadius: BorderRadius.circular(Curva.boton),
          border: principal ? null : Border.all(color: Tono.bordeSuave.withValues(alpha: .6)),
        ),
        child: Row(
          mainAxisSize: ancho == null ? MainAxisSize.min : MainAxisSize.max,
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            if (icono != null) ...[
              Icon(icono, size: tamanioTexto + 5, color: color ?? colorTexto),
              const SizedBox(width: 10),
            ],
            Flexible(
              child: Text(
                texto,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontFamily: Letra.texto,
                  fontSize: tamanioTexto,
                  fontWeight: FontWeight.w700,
                  color: colorTexto,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Dónde estaba el foco en una lista de canales: cuál y en qué lugar. El foco
/// "inicial" de la lista (el `autofocus`) es ese; y si ya no está (no andaba y
/// se escondió: NoAnda), el que quedó en su lugar. Así, al volver de un canal
/// que no andaba, el foco queda al lado y no salta al primero de arriba (la
/// pantalla de la TV lleva el foco al inicial cuando lo elegido desaparece).
class LugarDelFoco {
  /// La lista (una categoría, o '' = todas) y el canal (id) y su lugar en ella.
  String? _lista;
  int? _id;
  int _lugar = 0;

  /// Envuelve una tarjeta para anotar cuándo recibe el foco.
  Widget anotar({required String lista, required int id, required int lugar, required Widget child}) => Focus(
    canRequestFocus: false,
    skipTraversal: true,
    onFocusChange: (enfocado) {
      if (!enfocado) return;
      _lista = lista;
      _id = id;
      _lugar = lugar;
    },
    child: child,
  );

  /// Si el [lugar] de [ids] (la lista [lista]) es el inicial. [primera]: si
  /// esta lista es la primera de la pantalla (sin nada anotado que se vea, el
  /// inicial es su primer elemento). [listas]: las que se ven ahora.
  bool esInicial({
    required String lista,
    required List<int> ids,
    required int lugar,
    required bool primera,
    required Iterable<String> listas,
  }) {
    if (_lista == null || !listas.contains(_lista)) return primera && lugar == 0;
    if (lista != _lista || ids.isEmpty) return false;
    final donde = ids.indexOf(_id ?? -1);
    return lugar == (donde >= 0 ? donde : _lugar.clamp(0, ids.length - 1));
  }

  /// Si el canal anotado de [lista] ya no está en [ids] (se escondió), el que
  /// quedó en su lugar (y pasa a ser el anotado). null = sigue estando.
  int? reemplazo({required String lista, required List<int> ids}) {
    if (_lista != lista || _id == null || ids.isEmpty || ids.contains(_id)) return null;
    _id = ids[_lugar.clamp(0, ids.length - 1)];
    return _id;
  }
}
