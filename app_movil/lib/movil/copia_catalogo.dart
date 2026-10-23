/// El catálogo guardado en el aparato, y cómo se lee sin trabar la pantalla.
///
/// Con miles de películas y capítulos, el catálogo pesa varios MB. Antes, cada
/// vez que se abría la app había que esperar a que llegara entero (y cada 15
/// minutos se volvía a bajar todo). Ahora:
///
///   - Cada parte (En vivo, Películas, Series, cada sección nueva) se guarda
///     en el aparato con su huella (el ETag del servidor): [CopiaCatalogo].
///   - Al abrir la app se muestra enseguida lo guardado, y por detrás se le
///     pregunta al servidor si cambió (con la huella). Si no cambió, contesta
///     "es el mismo" (304) y no se baja nada.
///   - Lo que llega se lee en otro hilo ([leerParteAparte]): leer JSON grande y
///     armar las series congelaba la pantalla (y en la TV, el control remoto).
///
/// Las direcciones de los videos tienen datos de la cuenta del proveedor: la
/// copia queda en la carpeta privada de la app y se borra al cerrar sesión.
library;

import 'dart:convert';
import 'dart:io';
import 'dart:isolate';

import 'package:path_provider/path_provider.dart';

import '../api/modelos.dart';
import 'datos.dart';

/// Una parte del catálogo ya leída, TAL CUAL la mandó el servidor (todavía
/// sin sacar lo que este aparato no ve: eso lo hace Catalogo).
class ParteCatalogo {
  ParteCatalogo({required this.categorias, this.portadas = const {}, this.series = const []});

  final List<CategoriaCanales> categorias;

  /// {nombre de la serie: imagen} (solo en Series).
  final Map<String, String> portadas;

  /// Solo en Series: los capítulos ya agrupados por serie y temporada.
  final List<Serie> series;

  List<Canal> get canales => [for (final c in categorias) ...c.canales];
}

/// Lee lo que mandó GET /canales/ ([contenido]: cómo se ven sus canales, "vivo",
/// "pelicula" o "serie"). Con Series también las agrupa ([agruparSeries]).
ParteCatalogo leerParte(List<int> bytes, String contenido) {
  final datos = jsonDecode(utf8.decode(bytes)) as Map<String, dynamic>;
  final categorias = [
    for (final c in datos['categorias'] as List? ?? [])
      CategoriaCanales(c as Map<String, dynamic>, contenido: contenido),
  ];
  final portadas = <String, String>{
    if (datos['portadas'] case final Map<String, dynamic> recibidas)
      for (final p in recibidas.entries) p.key: '${p.value}',
  };
  return ParteCatalogo(
    categorias: categorias,
    portadas: portadas,
    series: contenido == 'serie'
        ? agruparSeries([for (final c in categorias) ...c.canales], portadas: portadas)
        : const [],
  );
}

/// La lista de series SIN capítulos (GET /canales/series/, desde la 1.2.38): [ParteCatalogo.series] con
/// series resumidas. Si no es esa lista (un servidor viejo contestó otra cosa), [FormatException].
ParteCatalogo leerSeries(List<int> bytes) {
  final datos = jsonDecode(utf8.decode(bytes));
  if (datos is! Map<String, dynamic> || datos['series'] is! List) {
    throw const FormatException('No es la lista de series');
  }
  return ParteCatalogo(
    categorias: const [],
    series: [for (final s in datos['series'] as List) Serie.resumida(s as Map<String, dynamic>)],
  );
}

Future<ParteCatalogo> leerSeriesAparte(List<int> bytes) async {
  if (bytes.length < grandeDesde) return leerSeries(bytes);
  return Isolate.run(() => leerSeries(bytes));
}

/// Como [leerParte], pero lo grande en otro hilo (lo chico no vale lo que
/// cuesta arrancar otro hilo).
Future<ParteCatalogo> leerParteAparte(List<int> bytes, String contenido) async {
  if (bytes.length < grandeDesde) return leerParte(bytes, contenido);
  return Isolate.run(() => leerParte(bytes, contenido));
}

/// Desde cuántos bytes se lee en otro hilo.
const grandeDesde = 64 * 1024;

/// Lo guardado de una parte: lo que mandó el servidor y su huella.
typedef Guardado = ({List<int> bytes, String huella});

/// Las partes del catálogo guardadas en el aparato (una carpeta por servidor).
/// Si no se puede leer o escribir (sin lugar, en los tests), no pasa nada: se
/// baja del servidor como siempre.
class CopiaCatalogo {
  CopiaCatalogo(String servidor) : _servidor = servidor.replaceAll(RegExp(r'[^A-Za-z0-9]+'), '_');

  final String _servidor;

  /// Solo para las pruebas: dónde se guarda (si no, la carpeta de la app).
  static Directory? carpetaDePrueba;

  static Future<Directory> _base() async =>
      carpetaDePrueba ?? Directory('${(await getApplicationSupportDirectory()).path}/catalogo');

  Future<File> _archivo(String parte, String extension) async {
    final nombre = parte.replaceAll(RegExp(r'[^A-Za-z0-9_]+'), '_');
    return File('${(await _base()).path}/$_servidor/$nombre.$extension');
  }

  Future<Guardado?> leer(String parte) async {
    try {
      final datos = await _archivo(parte, 'json');
      final huella = await _archivo(parte, 'huella');
      if (!await datos.exists() || !await huella.exists()) return null;
      return (bytes: await datos.readAsBytes(), huella: await huella.readAsString());
    } catch (_) {
      return null;
    }
  }

  Future<void> guardar(String parte, List<int> bytes, String huella) async {
    try {
      final datos = await _archivo(parte, 'json');
      await datos.parent.create(recursive: true);
      // Primero a uno temporal y después se renombra: si se apaga la TV a
      // mitad de camino, no queda un archivo cortado
      final temporal = File('${datos.path}.nuevo');
      await temporal.writeAsBytes(bytes, flush: true);
      await temporal.rename(datos.path);
      await (await _archivo(parte, 'huella')).writeAsString(huella, flush: true);
    } catch (_) {
      // Sin lugar o sin permiso: la próxima vez se baja de nuevo
    }
  }

  /// Saca una parte (una sección que ya no existe).
  Future<void> borrar(String parte) async {
    for (final extension in ['json', 'huella']) {
      try {
        await (await _archivo(parte, extension)).delete();
      } catch (_) {}
    }
  }

  /// Al cerrar sesión: no queda nada del catálogo en el aparato.
  static Future<void> borrarTodo() async {
    try {
      final base = await _base();
      if (await base.exists()) await base.delete(recursive: true);
    } catch (_) {}
  }
}
