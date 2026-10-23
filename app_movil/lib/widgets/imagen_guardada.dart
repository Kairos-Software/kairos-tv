/// Las imágenes de internet (pósters, logos, portadas), guardadas en el
/// aparato y achicadas al tamaño en que se muestran.
///
/// Antes eran `Image.network`, que tiene dos problemas con muchas películas:
///
///   1. No guarda nada en el aparato: cada vez que se abría la app (o la
///      memoria se llenaba y se soltaban), se volvían a bajar todas. Muchos
///      pósters vienen del mismo servidor del proveedor, que ya anda lento.
///   2. Las arma a tamaño completo: un póster de 600x900 ocupa ~2 MB en la
///      memoria aunque se vea de 150 de ancho. Con una grilla de películas
///      eso traba el desplazamiento en un TV box y llena la memoria (y al
///      llenarse, se sueltan y se bajan de nuevo).
///
/// [ImagenGuardada] baja cada imagen una sola vez y la deja en la carpeta de
/// caché de la app (Android la vacía solo si le falta lugar; acá se limita a
/// [GuardadoDeImagenes.maximoBytes]). Con [ImagenGuardada.tamanio] la arma al
/// tamaño en que se muestra ([imagenAlTamanio]).
library;

import 'dart:async';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/painting.dart';
import 'package:path_provider/path_provider.dart';

/// La imagen de [url] armada para un lugar de [lugar] (en píxeles lógicos, en
/// una pantalla de [pixeles] por píxel lógico). [cubrir]: llena el lugar
/// recortando (un póster, BoxFit.cover); si no, entra entera (un logo,
/// BoxFit.contain). Si el lugar no tiene medida, la imagen entera.
ImageProvider imagenAlTamanio(String url, {Size? lugar, double pixeles = 1, bool cubrir = true}) {
  if (lugar == null || !lugar.width.isFinite || !lugar.height.isFinite || lugar.isEmpty) return ImagenGuardada(url);
  // De a 50 píxeles: tarjetas casi iguales comparten la misma imagen armada
  int redondear(double medida) => ((medida * pixeles / 50).ceil() * 50).clamp(50, 4000);
  return ImagenGuardada(url, tamanio: (redondear(lugar.width), redondear(lugar.height)), cubrir: cubrir);
}

/// Una imagen de internet que se guarda en el aparato (ver arriba).
@immutable
class ImagenGuardada extends ImageProvider<ImagenGuardada> {
  const ImagenGuardada(this.url, {this.tamanio, this.cubrir = true});

  final String url;

  /// (ancho, alto) en píxeles del lugar donde se muestra: se arma de ese
  /// tamaño (nunca más grande que la original). Null = entera.
  final (int, int)? tamanio;

  /// Con [tamanio]: llena el lugar (recortando) o entra entera.
  final bool cubrir;

  @override
  Future<ImagenGuardada> obtainKey(ImageConfiguration configuration) => SynchronousFuture(this);

  @override
  ImageStreamCompleter loadImage(ImagenGuardada key, ImageDecoderCallback decode) => MultiFrameImageStreamCompleter(
    codec: _cargar(key, decode),
    scale: 1,
    debugLabel: url,
    informationCollector: () => [DiagnosticsProperty<String>('Dirección', url)],
  );

  Future<ui.Codec> _cargar(ImagenGuardada key, ImageDecoderCallback decode) async {
    try {
      final bytes = await GuardadoDeImagenes.bytesDe(url);
      final buffer = await ui.ImmutableBuffer.fromUint8List(bytes);
      final lugar = tamanio;
      if (lugar == null) return await decode(buffer);
      // Recién acá se sabe la medida de la original: se elige la escala que la deja justo
      return await decode(
        buffer,
        getTargetSize: (ancho, alto) {
          final (anchoLugar, altoLugar) = lugar;
          final porAncho = anchoLugar / ancho;
          final porAlto = altoLugar / alto;
          final escala = cubrir ? (porAncho > porAlto ? porAncho : porAlto) : (porAncho < porAlto ? porAncho : porAlto);
          if (escala >= 1) return ui.TargetImageSize(); // ya es chica: entera
          return ui.TargetImageSize(width: (ancho * escala).ceil(), height: (alto * escala).ceil());
        },
      );
    } catch (_) {
      // Como NetworkImage: si falla, no queda guardada la falla (se reintenta la próxima vez)
      scheduleMicrotask(() => PaintingBinding.instance.imageCache.evict(key));
      rethrow;
    }
  }

  @override
  bool operator ==(Object other) =>
      other is ImagenGuardada && other.url == url && other.tamanio == tamanio && other.cubrir == cubrir;

  @override
  int get hashCode => Object.hash(url, tamanio, cubrir);

  @override
  String toString() => 'ImagenGuardada("$url", $tamanio${cubrir ? '' : ', entera'})';
}

/// Las imágenes bajadas, en archivos (uno por dirección).
class GuardadoDeImagenes {
  /// Cuánto lugar ocupan como mucho. Al pasarlo se borran las más viejas.
  static const maximoBytes = 150 * 1024 * 1024;

  /// Una imagen más grande que esto no se usa (no es un póster).
  static const maximoPorImagen = 15 * 1024 * 1024;

  static final HttpClient _http = HttpClient()..connectionTimeout = const Duration(seconds: 15);

  /// Las que se están bajando: si dos tarjetas piden la misma, se baja una vez.
  static final Map<String, Future<Uint8List>> _bajando = {};

  static Future<Directory?>? _carpeta;
  static bool _ordenado = false;

  /// Solo para las pruebas: dónde se guardan (si no, la carpeta de caché de la app).
  @visibleForTesting
  static Directory? carpetaDePrueba;

  /// Solo para las pruebas: cómo se baja (si no, de internet).
  @visibleForTesting
  static Future<Uint8List> Function(String url)? bajarDePrueba;

  static Future<Directory?> _laCarpeta() => _carpeta ??= () async {
    try {
      final carpeta = carpetaDePrueba ?? Directory('${(await getTemporaryDirectory()).path}/imagenes');
      await carpeta.create(recursive: true);
      return carpeta;
    } catch (_) {
      return null; // sin carpeta (ej: en las pruebas): se baja cada vez, como antes
    }
  }();

  /// Los bytes de la imagen: del aparato si ya se bajó; si no, de internet (y se guarda).
  static Future<Uint8List> bytesDe(String url) => _bajando[url] ??= _buscar(url).whenComplete(() {
    // Con llaves a propósito: si devolviera lo que saca (esta misma espera), se esperaría a sí misma
    _bajando.remove(url);
  });

  static Future<Uint8List> _buscar(String url) async {
    final carpeta = await _laCarpeta();
    final archivo = carpeta == null ? null : File('${carpeta.path}/${nombreDeArchivo(url)}');
    if (archivo != null) {
      try {
        if (await archivo.exists()) return await archivo.readAsBytes();
      } catch (_) {
        // No se pudo leer: se baja de nuevo
      }
    }
    final bytes = await (bajarDePrueba ?? _bajar)(url);
    if (archivo != null) {
      // Se espera a que quede en el disco (son milisegundos): si no, pedirla enseguida en otro tamaño
      // (la grilla y después el detalle) no la encontraba y la bajaba de nuevo
      await _guardar(archivo, bytes);
      if (!_ordenado) {
        _ordenado = true;
        // Una vez por vez que se abre la app, y un rato después (no mientras arranca)
        unawaited(Future.delayed(const Duration(seconds: 30), () => ordenar(carpeta!)));
      }
    }
    return bytes;
  }

  static Future<Uint8List> _bajar(String url) async {
    final pedido = await _http.getUrl(Uri.parse(url)).timeout(const Duration(seconds: 20));
    final respuesta = await pedido.close().timeout(const Duration(seconds: 20));
    if (respuesta.statusCode != HttpStatus.ok) {
      await respuesta.drain<void>();
      throw HttpException('La imagen respondió ${respuesta.statusCode}', uri: Uri.parse(url));
    }
    final bytes = await consolidateHttpClientResponseBytes(respuesta).timeout(const Duration(seconds: 40));
    if (bytes.isEmpty || bytes.length > maximoPorImagen) {
      throw HttpException('La imagen pesa ${bytes.length} bytes', uri: Uri.parse(url));
    }
    return bytes;
  }

  static Future<void> _guardar(File archivo, Uint8List bytes) async {
    try {
      // Primero a uno temporal y después se renombra: nunca queda una imagen cortada
      final temporal = File('${archivo.path}.nuevo');
      await temporal.writeAsBytes(bytes, flush: true);
      await temporal.rename(archivo.path);
    } catch (_) {
      // Sin lugar: se vuelve a bajar la próxima vez
    }
  }

  /// Si pasan de [maximoBytes], borra las más viejas hasta quedar en 2/3.
  @visibleForTesting
  static Future<void> ordenar(Directory carpeta, {int maximo = maximoBytes}) async {
    try {
      final archivos = <(File, DateTime, int)>[];
      var total = 0;
      await for (final entrada in carpeta.list()) {
        if (entrada is! File) continue;
        final datos = await entrada.stat();
        archivos.add((entrada, datos.modified, datos.size));
        total += datos.size;
      }
      if (total <= maximo) return;
      archivos.sort((a, b) => a.$2.compareTo(b.$2));
      for (final (archivo, _, tamanio) in archivos) {
        if (total <= maximo * 2 ~/ 3) break;
        try {
          await archivo.delete();
          total -= tamanio;
        } catch (_) {}
      }
    } catch (_) {}
  }

  /// El nombre del archivo de una dirección: su huella FNV-1a de 64 bits (siempre la misma).
  @visibleForTesting
  static String nombreDeArchivo(String url) {
    var huella = 0xcbf29ce484222325;
    for (final unidad in url.codeUnits) {
      huella ^= unidad;
      huella *= 0x100000001b3;
    }
    return '${huella.toUnsigned(64).toRadixString(16).padLeft(16, '0')}.img';
  }

  /// Solo para las pruebas: se olvida de la carpeta (la próxima vez la vuelve a buscar).
  @visibleForTesting
  static void olvidar() {
    _carpeta = null;
    _ordenado = false;
    _bajando.clear();
  }
}
