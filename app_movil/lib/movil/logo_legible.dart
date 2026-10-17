/// Los logos OSCUROS sobre fondo transparente (C5N, Cine.Ar...) casi no se
/// leen sobre las tarjetas oscuras de la app. Estos se muestran sobre una
/// placa clara y redondeada, del tamaño del logo, como en las guías de TV.
///
/// Cómo se sabe: la app baja una copia chiquita del logo (32 px), mira sus
/// píxeles ([esLogoOscuro]) y guarda el resultado en el aparato. Así se mide
/// una sola vez, y la próxima vez que se abre la app ya está. Lo hace la app
/// sola, con cualquier logo: no hace falta marcar nada en el panel.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// El color de la placa: claro, sin llegar al blanco puro (encandila en la TV).
const colorPlacaDeLogo = Color(0xFFE6EBEE);

/// ¿El logo es oscuro y sobre fondo transparente? [rgba]: los píxeles (4 bytes cada uno).
///
/// - Tiene que tener bastante transparente (más del 15 %): un logo que trae su
///   propio fondo (un cuadrado de color) ya se lee solo.
/// - Lo que se ve (los píxeles opacos) tiene que ser oscuro en promedio.
bool esLogoOscuro(Uint8List rgba) {
  final total = rgba.length ~/ 4;
  if (total == 0) return false;
  var transparentes = 0;
  var opacos = 0;
  var luz = 0.0;
  for (var i = 0; i + 3 < rgba.length; i += 4) {
    final alfa = rgba[i + 3];
    if (alfa < 40) {
      transparentes++;
    } else if (alfa > 160) {
      opacos++;
      luz += .2126 * rgba[i] + .7152 * rgba[i + 1] + .0722 * rgba[i + 2];
    }
  }
  if (opacos == 0 || transparentes / total < .15) return false;
  return luz / opacos < 85;
}

/// Lo medido de cada logo: 0 = se lee bien (o no se pudo medir); más que 0 =
/// es oscuro, y el número es su forma (ancho / alto), para que la placa lo abrace.
class LogosOscuros {
  LogosOscuros._();

  static const _clave = 'kairos.logos_oscuros';
  static const _maximo = 800;
  static final Map<String, double> _medidos = {};
  static final Map<String, Future<double>> _midiendo = {};
  static Future<void>? _cargando;

  /// Para los tests: lo medido, sin bajar nada.
  @visibleForTesting
  static void poner(String url, double forma) => _medidos[url] = forma;

  /// Lo ya medido de [url] (null = todavía no se sabe).
  static double? yaMedido(String url) => _medidos[url];

  /// La forma del logo si es oscuro (0 si se lee bien). Se mide una sola vez.
  static Future<double> medir(String url) {
    final ya = _medidos[url];
    if (ya != null) return SynchronousFuture(ya);
    return _midiendo[url] ??= _medirUnaVez(url);
  }

  static Future<double> _medirUnaVez(String url) async {
    await (_cargando ??= _cargar());
    final guardado = _medidos[url];
    if (guardado != null) return guardado;
    final forma = await _medirAhora(url);
    if (forma != null) {
      _medidos[url] = forma;
      _guardar();
    }
    _midiendo.remove(url);
    return forma ?? 0.0;
  }

  static Future<void> _cargar() async {
    try {
      final texto = (await SharedPreferences.getInstance()).getString(_clave);
      if (texto == null) return;
      (jsonDecode(texto) as Map<String, dynamic>).forEach((url, forma) {
        _medidos.putIfAbsent(url, () => (forma as num).toDouble());
      });
    } catch (_) {
      // Sin lo guardado (o en los tests): se vuelve a medir
    }
  }

  static Timer? _escribir;

  /// Junta varios y escribe una vez (al abrir la app se miden muchos juntos).
  static void _guardar() {
    _escribir?.cancel();
    _escribir = Timer(const Duration(seconds: 2), () async {
      try {
        // Los últimos medidos, hasta _maximo (los más viejos se vuelven a medir si aparecen)
        final todos = _medidos.entries.toList();
        final datos = Map.fromEntries(todos.skip(todos.length > _maximo ? todos.length - _maximo : 0));
        (await SharedPreferences.getInstance()).setString(_clave, jsonEncode(datos));
      } catch (_) {
        // No se pudo guardar: se mide de nuevo la próxima vez
      }
    });
  }

  /// Baja la copia chiquita y la mide. null = no se pudo (sin internet): se reintenta la próxima vez.
  static Future<double?> _medirAhora(String url) async {
    final listo = Completer<ui.Image?>();
    final flujo = ResizeImage(
      NetworkImage(url),
      width: 32,
      height: 32,
      policy: ResizeImagePolicy.fit,
    ).resolve(ImageConfiguration.empty);
    late final ImageStreamListener oyente;
    oyente = ImageStreamListener(
      (info, _) {
        if (!listo.isCompleted) listo.complete(info.image.clone());
        info.dispose();
        flujo.removeListener(oyente);
      },
      onError: (_, _) {
        if (!listo.isCompleted) listo.complete(null);
        flujo.removeListener(oyente);
      },
    );
    flujo.addListener(oyente);
    final imagen = await listo.future.timeout(const Duration(seconds: 20), onTimeout: () => null);
    if (imagen == null) return null;
    try {
      final datos = await imagen.toByteData(format: ui.ImageByteFormat.rawRgba);
      if (datos == null || imagen.height == 0) return null;
      return esLogoOscuro(datos.buffer.asUint8List()) ? imagen.width / imagen.height : 0;
    } finally {
      imagen.dispose();
    }
  }
}

/// [imagen] (el logo, dibujado entero: BoxFit.contain), y si es oscuro, sobre
/// la placa clara. Mientras se mide, el logo se ve como siempre.
class LogoLegible extends StatefulWidget {
  const LogoLegible({super.key, required this.url, required this.imagen});

  final String url;
  final Widget imagen;

  @override
  State<LogoLegible> createState() => _LogoLegibleState();
}

class _LogoLegibleState extends State<LogoLegible> {
  late double _forma = LogosOscuros.yaMedido(widget.url) ?? 0;

  @override
  void initState() {
    super.initState();
    _medir();
  }

  @override
  void didUpdateWidget(LogoLegible anterior) {
    super.didUpdateWidget(anterior);
    if (anterior.url != widget.url) {
      _forma = LogosOscuros.yaMedido(widget.url) ?? 0;
      _medir();
    }
  }

  void _medir() {
    final url = widget.url;
    if (url.isEmpty || LogosOscuros.yaMedido(url) != null) return;
    LogosOscuros.medir(url).then((forma) {
      if (mounted && widget.url == url && forma != _forma) setState(() => _forma = forma);
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_forma <= 0) return widget.imagen;
    return LayoutBuilder(
      builder: (context, limites) {
        // Un poco de aire alrededor del logo, según el lado más corto de la placa
        final lado = limites.biggest.shortestSide.isFinite ? limites.biggest.shortestSide : 60.0;
        final aire = (lado * .12).clamp(3.0, 18.0);
        return Center(
          child: AspectRatio(
            aspectRatio: (_forma * lado + 2 * aire) / (lado + 2 * aire),
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: colorPlacaDeLogo,
                borderRadius: BorderRadius.circular((lado * .14).clamp(4.0, 14.0)),
              ),
              child: Padding(padding: EdgeInsets.all(aire), child: widget.imagen),
            ),
          ),
        );
      },
    );
  }
}
