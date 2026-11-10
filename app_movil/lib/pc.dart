/// Lo propio de la app de PC (Windows): la ventana y lo que en la tele hace el control remoto.
///
///   - [Ventana]: la pantalla completa (sin bordes ni la barra de título; la pone cada reproductor mientras está
///     abierto y F11 la cambia en cualquier lado) y la versión instalada. Las atiende el programa de Windows
///     (windows/runner/flutter_window.cpp, canal "kairos/ventana").
///   - Teclas: Esc es el "Atrás" del control (cierra lo abierto, sale del reproductor, en Inicio pregunta si salir)
///     y F11, la pantalla completa ([atajosDePc] y [accionesDePc], en MaterialApp). El botón "atrás" del costado
///     del mouse también vuelve ([MouseDePc]).
///   - El mouse: las listas y filas se pueden arrastrar ([ScrollDePc]); lo demás (resaltar lo que se señala, clic
///     derecho = OK largo) lo hace cada `Enfocable` (tv/foco.dart).
///
/// En Android no se usa nada de esto (todo pregunta antes por [Aparato.esPc]).
library;

import 'dart:ui' show AppExitType;

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'aparato.dart';

class Ventana {
  Ventana._();

  static const _canal = MethodChannel('kairos/ventana');

  /// ¿Está en pantalla completa? (los botones del reproductor muestran una cosa u otra)
  static final pantallaCompleta = ValueNotifier<bool>(false);

  /// Cuántos reproductores hay abiertos (al pasar de uno a otro no se sale de la pantalla completa).
  static int _reproductores = 0;

  /// Si ya estaba en pantalla completa antes del reproductor (F11): al salir, queda así.
  static bool _estabaCompleta = false;

  static Future<void> poner(bool completa) async {
    if (!Aparato.esPc) return;
    final antes = pantallaCompleta.value;
    // Se anota enseguida (el botón cambia sin esperar) y después vale lo que diga la ventana
    pantallaCompleta.value = completa;
    try {
      pantallaCompleta.value = await _canal.invokeMethod<bool>('pantallaCompleta', completa) ?? completa;
    } on MissingPluginException {
      // En las pruebas no hay ventana: queda lo anotado
    } on PlatformException {
      pantallaCompleta.value = antes; // la ventana no se pudo cambiar
    }
  }

  static Future<void> alternar() => poner(!pantallaCompleta.value);

  /// Un reproductor se abre: el video ocupa toda la pantalla, como en la tele.
  static void entrarAlReproductor() {
    if (_reproductores++ == 0) {
      _estabaCompleta = pantallaCompleta.value;
      poner(true);
    }
  }

  /// Se cerró: vuelve la ventana como estaba (si no se cambió a mano mientras tanto).
  static void salirDelReproductor() {
    if (_reproductores == 0) return;
    if (--_reproductores == 0 && !_estabaCompleta) poner(false);
  }

  /// La versión instalada: la que se le dio al armarla (`--build-name 2026.11.10 --build-number 1530` ->
  /// "2026.11.10.1530"). Vacía si no se sabe.
  static Future<String> version() async {
    try {
      return (await _canal.invokeMethod<String>('version') ?? '').replaceAll('+', '.');
    } on MissingPluginException {
      return '';
    } on PlatformException {
      return '';
    }
  }

  /// Cierra la app ("Salir" en Inicio). En Android se usa SystemNavigator.pop, que en Windows no hace nada.
  static Future<void> cerrarLaApp() async {
    await poner(false);
    await ServicesBinding.instance.exitApplication(AppExitType.required);
  }
}

/// Esc: "Atrás". Lo atiende [accionesDePc].
class VolverIntent extends Intent {
  const VolverIntent();
}

/// F11: pantalla completa.
class PantallaCompletaIntent extends Intent {
  const PantallaCompletaIntent();
}

/// Las teclas de la PC, sumadas a las de siempre de Flutter. Esc reemplaza a la de Flutter (que cierra los
/// carteles sin preguntarle a la pantalla): así hace lo mismo que el "Atrás" del control, nada más.
Map<ShortcutActivator, Intent> get atajosDePc => {
  ...WidgetsApp.defaultShortcuts,
  const SingleActivator(LogicalKeyboardKey.escape): const VolverIntent(),
  const SingleActivator(LogicalKeyboardKey.browserBack): const VolverIntent(),
  const SingleActivator(LogicalKeyboardKey.f11): const PantallaCompletaIntent(),
};

Map<Type, Action<Intent>> accionesDePc(GlobalKey<NavigatorState> navegador) => {
  ...WidgetsApp.defaultActions,
  VolverIntent: CallbackAction<VolverIntent>(onInvoke: (_) => volver(navegador)),
  PantallaCompletaIntent: CallbackAction<PantallaCompletaIntent>(onInvoke: (_) => Ventana.alternar()),
};

/// Lo mismo que el "Atrás" del control: la pantalla de arriba decide (PopScope) si se cierra o hace otra cosa.
void volver(GlobalKey<NavigatorState> navegador) => navegador.currentState?.maybePop();

/// El botón "atrás" del costado del mouse vuelve, como Esc.
class MouseDePc extends StatelessWidget {
  const MouseDePc({super.key, required this.navegador, required this.child});

  final GlobalKey<NavigatorState> navegador;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Listener(
      behavior: HitTestBehavior.translucent,
      onPointerDown: (evento) {
        if (evento.kind == PointerDeviceKind.mouse && evento.buttons & kBackMouseButton != 0) volver(navegador);
      },
      child: child,
    );
  }
}

/// En la PC las listas y las filas de tarjetas también se arrastran con el mouse (la rueda mueve lo vertical).
class ScrollDePc extends MaterialScrollBehavior {
  const ScrollDePc();

  @override
  Set<PointerDeviceKind> get dragDevices => PointerDeviceKind.values.toSet();
}
