/// Los datos de las pantallas de celular:
///
///   - [Catalogo]: lo que hay para ver (canales en vivo, películas, series y
///     las secciones nuevas que se crean en el panel, como Música o Radio:
///     [SeccionNueva]), pedido a la API. Las series llegan como capítulos
///     sueltos ("Show S01 E02") y acá se agrupan por serie y temporada.
///   - [Biblioteca]: lo de cada aparato: "Mi lista" y "Continuar viendo"
///     (por dónde iba cada película o capítulo). Se guarda en el aparato.
library;

import 'dart:async';
import 'dart:convert';

import 'package:flutter/widgets.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api/cliente.dart';
import '../api/modelos.dart';
import '../aparato.dart';
import 'calidad_youtube.dart';
import 'control_senal.dart';
import 'medidor.dart';

// ── Series ─────────────────────────────────────────────────────────

/// Un capítulo de una serie.
class Episodio {
  Episodio({required this.canal, required this.temporada, required this.numero, required this.titulo});

  final Canal canal;
  final int temporada;
  final int numero;

  /// Lo que viene después de "S01 E02" en el nombre (puede estar vacío).
  final String titulo;

  /// "T1:E2"
  String get codigo => 'T$temporada:E$numero';
}

/// Una serie con sus temporadas (armada a partir de los capítulos sueltos).
class Serie {
  Serie({required this.nombre, required this.categoria, this.portada = ''});

  final String nombre;
  final String categoria;
  final Map<int, List<Episodio>> temporadas = {};

  /// La portada propia de la serie, si se la pusieron en el panel ('' = no tiene).
  final String portada;

  /// La imagen de la serie: su portada o, si no tiene, la del primer capítulo que tenga.
  String get imagen => portada.isNotEmpty
      ? portada
      : episodios.map((e) => e.canal.logo).firstWhere((logo) => logo.isNotEmpty, orElse: () => '');

  List<int> get numerosDeTemporada => temporadas.keys.toList()..sort();

  /// Si sus capítulos dicen temporada y capítulo ("S01 E02"). Un video suelto
  /// cargado como serie no lo dice: no se puede saber cuál es el primero.
  bool numerada = false;

  /// Se puede seguir desde el principio: tiene el T1:E1. Una serie nueva se
  /// muestra desde su primer capítulo; las que empiezan a mitad no se muestran.
  bool get completa => numerada && (temporadas[1]?.any((e) => e.numero == 1) ?? false);

  List<Episodio> get episodios => [for (final t in numerosDeTemporada) ...temporadas[t]!];

  /// Destacada en el panel (se marcan sus capítulos): el modo reposo la muestra más seguido.
  bool get destacada => episodios.any((e) => e.canal.destacado);

  /// Para "Mi lista": las series se guardan por nombre (sus capítulos tienen cada uno su id).
  String get clave => 's:$nombre';
}

// "Show S01 E02", "Show - S1E2 - Título", "Show 1x02"
final _patronEpisodio = RegExp(
  r'^(.*?)[\s._\-:|]*(?:\bS(\d{1,2})\s*[._\- ]?\s*E(\d{1,4})|\b(\d{1,2})x(\d{1,3}))\b[\s._\-:|]*(.*)$',
  caseSensitive: false,
);

/// Los capítulos sueltos -> series con temporadas, en el orden en que llegaron.
/// [portadas]: {nombre de la serie: imagen} (las que tienen portada propia).
List<Serie> agruparSeries(List<Canal> capitulos, {Map<String, String> portadas = const {}}) {
  final series = <String, Serie>{};
  final portadaDe = {for (final p in portadas.entries) p.key.toLowerCase(): p.value};
  var sinNumero = 0;
  for (final capitulo in capitulos) {
    final partes = _patronEpisodio.firstMatch(capitulo.nombre);
    final String nombre;
    final int temporada;
    final int numero;
    final String titulo;
    final conNumero = partes != null && partes.group(1)!.trim().isNotEmpty;
    if (conNumero) {
      nombre = partes.group(1)!.trim();
      temporada = int.parse(partes.group(2) ?? partes.group(4)!);
      numero = int.parse(partes.group(3) ?? partes.group(5)!);
      titulo = partes.group(6)!.trim();
    } else {
      // Sin "S01 E02": cada uno es una "serie" de un solo capítulo
      nombre = capitulo.nombre;
      temporada = 1;
      numero = ++sinNumero;
      titulo = '';
    }
    final serie = series.putIfAbsent(
      nombre.toLowerCase(),
      () => Serie(nombre: nombre, categoria: capitulo.categoria, portada: portadaDe[nombre.toLowerCase()] ?? ''),
    );
    if (conNumero) serie.numerada = true;
    serie.temporadas
        .putIfAbsent(temporada, () => [])
        .add(Episodio(canal: capitulo, temporada: temporada, numero: numero, titulo: titulo));
  }
  for (final serie in series.values) {
    for (final lista in serie.temporadas.values) {
      lista.sort((a, b) => a.numero.compareTo(b.numero));
    }
  }
  return series.values.toList();
}

/// "6 Guns (2010)" -> 2010 (o null).
int? anioDe(String nombre) {
  final anio = RegExp(r'\((19\d\d|20\d\d)\)').firstMatch(nombre);
  return anio == null ? null : int.parse(anio.group(1)!);
}

/// "6 Guns (2010)" -> "6 Guns"
String sinAnio(String nombre) => nombre.replaceAll(RegExp(r'\s*\((19\d\d|20\d\d)\)\s*'), ' ').trim();

/// "VOD | SPAIN" -> "Spain", "LAME | ARGENTINA" -> "Argentina", "Noticias" -> "Noticias".
String categoriaLegible(String categoria) {
  final partes = categoria.split('|').map((p) => p.trim()).where((p) => p.isNotEmpty).toList();
  final ultima = partes.isEmpty ? categoria.trim() : partes.last;
  if (ultima.isEmpty) return '';
  final esMayusculas = ultima == ultima.toUpperCase() && ultima.length > 3;
  return esMayusculas ? ultima[0] + ultima.substring(1).toLowerCase() : ultima;
}

// ── Secciones nuevas (Música, Radio...) ────────────────────────────

/// Una sección creada en el panel (además de En vivo, Películas y Series).
/// Su [forma] dice cómo se ve y se reproduce: "vivo" como En vivo (radios,
/// canales) o "pelicula" como Películas (videos que se eligen: música...).
/// Sus canales llegan con `contenido` = la forma, así el reproductor, los
/// favoritos y "lo que no anda" los tratan igual que a los de esas secciones.
class SeccionNueva {
  SeccionNueva({required this.clave, required this.nombre, required this.forma, required this.icono});

  SeccionNueva.desdeJson(Map<String, dynamic> json)
    : clave = '${json['clave'] ?? ''}',
      nombre = '${json['nombre'] ?? ''}',
      forma = json['forma'] == 'vivo' ? 'vivo' : 'pelicula',
      icono = '${json['icono'] ?? ''}';

  final String clave;
  final String nombre;

  /// "vivo" o "pelicula"
  final String forma;

  /// "musica", "radio", "deportes", "documentales", "infantil", "noticias" u "otro"
  final String icono;

  List<CategoriaCanales> categorias = [];

  bool get enVivo => forma == 'vivo';

  List<Canal> get canales => [for (final c in categorias) ...c.canales];
}

// ── Catálogo ───────────────────────────────────────────────────────

/// Lo que hay para ver. Se pide al abrir la app, al volver a ella y cada 15
/// minutos (una TV o un celular pueden quedar abiertos todo el día).
///
/// Solo trae lo que ESTE aparato puede ver ([_seVe]): saca lo que tiene un
/// códec que el aparato no muestra, lo que ya falló acá ([NoAnda]) y las
/// series a medias ([Serie.completa]).
class Catalogo extends ChangeNotifier {
  Catalogo(this.api) {
    NoAnda.cambios.addListener(_sacarLoQueNoAnda);
  }

  final ApiCliente api;

  static bool _seVe(Canal canal) => canal.fuentesReproducibles.isNotEmpty && !NoAnda.oculto(canal.id);

  /// Algo acaba de fallar en este aparato: se saca ya, sin esperar a la próxima carga.
  void _sacarLoQueNoAnda() {
    for (final categoria in categoriasEnVivo) {
      categoria.canales.removeWhere((c) => NoAnda.oculto(c.id));
    }
    categoriasEnVivo = categoriasEnVivo.where((c) => c.canales.isNotEmpty).toList();
    peliculas = peliculas.where((c) => !NoAnda.oculto(c.id)).toList();
    for (final serie in series) {
      for (final capitulos in serie.temporadas.values) {
        capitulos.removeWhere((e) => NoAnda.oculto(e.canal.id));
      }
      serie.temporadas.removeWhere((_, capitulos) => capitulos.isEmpty);
    }
    series = series.where((s) => s.completa).toList();
    for (final seccion in seccionesNuevas) {
      for (final categoria in seccion.categorias) {
        categoria.canales.removeWhere((c) => NoAnda.oculto(c.id));
      }
      seccion.categorias = seccion.categorias.where((c) => c.canales.isNotEmpty).toList();
    }
    seccionesNuevas = seccionesNuevas.where((s) => s.canales.isNotEmpty).toList();
    _numeros.clear();
    notifyListeners();
  }

  @override
  void dispose() {
    NoAnda.cambios.removeListener(_sacarLoQueNoAnda);
    super.dispose();
  }

  List<CategoriaCanales> categoriasEnVivo = [];
  List<Canal> peliculas = [];
  List<Serie> series = [];

  /// Las secciones creadas en el panel que tienen algo para ver acá, en el orden del menú.
  List<SeccionNueva> seccionesNuevas = [];

  /// Lo de las secciones nuevas "en vivo" (radios...) y "a demanda" (música...), para favoritos y búsquedas.
  List<Canal> get _vivosNuevos => [for (final s in seccionesNuevas.where((s) => s.enVivo)) ...s.canales];

  List<Canal> get _aDemandaNuevos => [for (final s in seccionesNuevas.where((s) => !s.enVivo)) ...s.canales];

  bool cargando = false;
  bool cargado = false;
  Object? error;

  /// Todo lo que mandó el servidor, antes de sacar lo que este aparato no ve.
  List<Canal> _recibidos = [];

  /// Lo que el servidor manda (en el panel "se ve") pero ESTE aparato no
  /// muestra, y por qué. Lo muestra Mi cuenta en la TV ("Lo que no se ve en esta TV").
  List<(Canal, String)> get escondidos => [
    for (final canal in _recibidos)
      if (!_seVe(canal)) (canal, porQueNoSeVe(canal)),
  ];

  /// Por qué este aparato no muestra [canal].
  static String porQueNoSeVe(Canal canal) {
    final hasta = NoAnda.hasta(canal.id);
    if (hasta != null) {
      return 'Falló acá: este aparato no lo pudo mostrar. Se vuelve a probar el ${hasta.day}/${hasta.month}.';
    }
    final codecs = {
      for (final f in canal.fuentes)
        if (f.esReproducible && !f.aparatoLoMuestra) f.codec,
    };
    if (codecs.isNotEmpty) return 'Este aparato no lee ${codecs.map(nombreDeCodec).join(' ni ')}.';
    return 'No tiene una señal que la app pueda abrir.';
  }

  List<Canal> get canales => [for (final c in categoriasEnVivo) ...c.canales];

  /// El número de cada canal en vivo: el que trae la lista, o si no tiene, su
  /// lugar en la grilla (1, 2, 3...). Con él se cambia de canal escribiendo el
  /// número con el control remoto.
  final Map<int, String> _numeros = {};

  String numeroDe(Canal canal) {
    if (_numeros.isEmpty && categoriasEnVivo.isNotEmpty) _numerar();
    return _numeros[canal.id] ?? canal.numero;
  }

  /// El canal con ese número (o null).
  Canal? canalPorNumero(String numero) {
    final buscado = int.tryParse(numero);
    if (buscado == null) return null;
    for (final canal in canales) {
      if (int.tryParse(numeroDe(canal)) == buscado) return canal;
    }
    return null;
  }

  void _numerar() {
    _numeros.clear();
    final usados = {for (final c in canales) int.tryParse(c.numero)}..remove(null);
    var siguiente = 1;
    for (final canal in canales) {
      if (int.tryParse(canal.numero) != null) {
        _numeros[canal.id] = '${int.parse(canal.numero)}';
        continue;
      }
      while (usados.contains(siguiente)) {
        siguiente++;
      }
      _numeros[canal.id] = '${siguiente++}';
    }
  }

  /// Los favoritos, separados por tipo (en el orden en que se agregaron).
  List<Canal> canalesFavoritos(Biblioteca biblioteca) => _deLaLista(biblioteca, [...canales, ..._vivosNuevos]);

  List<Canal> peliculasFavoritas(Biblioteca biblioteca) => _deLaLista(biblioteca, [...peliculas, ..._aDemandaNuevos]);

  List<Serie> seriesFavoritas(Biblioteca biblioteca) {
    final lista = biblioteca.miLista.toList();
    return series.where((s) => lista.contains(s.clave)).toList()
      ..sort((a, b) => lista.indexOf(a.clave).compareTo(lista.indexOf(b.clave)));
  }

  List<Canal> _deLaLista(Biblioteca biblioteca, List<Canal> todos) {
    final lista = biblioteca.miLista.toList();
    return todos.where((c) => lista.contains(Biblioteca.claveDe(c))).toList()
      ..sort((a, b) => lista.indexOf(Biblioteca.claveDe(a)).compareTo(lista.indexOf(Biblioteca.claveDe(b))));
  }

  /// Los últimos canales en vivo vistos en este aparato (el más reciente primero).
  List<Canal> canalesRecientes(Biblioteca biblioteca) => [
    for (final id in biblioteca.recientes) ?canales.where((c) => c.id == id).firstOrNull,
  ];

  Future<void> cargar() async {
    if (cargando) return;
    cargando = true;
    error = null;
    notifyListeners();
    final formatos = FuenteCanal.formatosQueReproduce.join(',');
    // Las portadas propias de las series (vienen con ?contenido=serie; un servidor viejo no las manda)
    var portadas = <String, String>{};
    Future<List<CategoriaCanales>> pedir(String contenido) async {
      final datos =
          await api.get('canales/', parametros: {'formatos': formatos, 'contenido': contenido}) as Map<String, dynamic>;
      if (datos['portadas'] case final Map<String, dynamic> recibidas) {
        portadas = {for (final p in recibidas.entries) p.key: '${p.value}'};
      }
      return [
        for (final c in datos['categorias'] as List) CategoriaCanales(c as Map<String, dynamic>, contenido: contenido),
      ];
    }

    // Las secciones nuevas: la lista y lo de cada una. Un servidor viejo no
    // tiene /secciones/: entonces no hay ninguna (no es un error).
    Future<List<SeccionNueva>> pedirSeccionesNuevas() async {
      final List<SeccionNueva> nuevas;
      try {
        final datos = await api.get('canales/secciones/') as Map<String, dynamic>;
        nuevas = [for (final s in datos['secciones'] as List) SeccionNueva.desdeJson(s as Map<String, dynamic>)];
      } catch (_) {
        return [];
      }
      await Future.wait([
        for (final seccion in nuevas)
          // Si una no llega, queda vacía (no se muestra) y el resto del catálogo sigue
          api
              .get('canales/', parametros: {'formatos': formatos, 'contenido': seccion.clave})
              .then((datos) {
                seccion.categorias = [
                  for (final c in (datos as Map<String, dynamic>)['categorias'] as List)
                    CategoriaCanales(c as Map<String, dynamic>, contenido: seccion.forma),
                ];
              })
              .catchError((_) {}),
      ]);
      return nuevas;
    }

    try {
      final resultados = await Future.wait([
        pedir('vivo'),
        pedir('pelicula'),
        pedir('serie'),
        NoAnda.cargar(),
        pedirSeccionesNuevas(),
        FuentePreferida.cargar(),
        CalidadYoutube.cargar(),
      ]);
      final vivo = resultados[0] as List<CategoriaCanales>;
      _recibidos = [
        for (final r in [vivo, resultados[1], resultados[2]])
          for (final c in r as List<CategoriaCanales>) ...c.canales,
        for (final seccion in resultados[4] as List<SeccionNueva>) ...seccion.canales,
      ];
      for (final categoria in vivo) {
        categoria.canales.retainWhere(_seVe);
      }
      categoriasEnVivo = vivo.where((c) => c.canales.isNotEmpty).toList();
      peliculas = [for (final c in resultados[1] as List<CategoriaCanales>) ...c.canales.where(_seVe)];
      series = agruparSeries([
        for (final c in resultados[2] as List<CategoriaCanales>) ...c.canales.where(_seVe),
      ], portadas: portadas).where((s) => s.completa).toList();
      final nuevas = resultados[4] as List<SeccionNueva>;
      for (final seccion in nuevas) {
        for (final categoria in seccion.categorias) {
          categoria.canales.retainWhere(_seVe);
        }
        seccion.categorias = seccion.categorias.where((c) => c.canales.isNotEmpty).toList();
      }
      seccionesNuevas = nuevas.where((s) => s.canales.isNotEmpty).toList();
      _numerar();
      cargado = true;
    } catch (e) {
      error = e;
    } finally {
      cargando = false;
      notifyListeners();
    }
  }

  Canal? canalPorId(int id) {
    for (final canal in canales) {
      if (canal.id == id) return canal;
    }
    for (final pelicula in peliculas) {
      if (pelicula.id == id) return pelicula;
    }
    for (final seccion in seccionesNuevas) {
      for (final canal in seccion.canales) {
        if (canal.id == id) return canal;
      }
    }
    for (final serie in series) {
      for (final episodio in serie.episodios) {
        if (episodio.canal.id == id) return episodio.canal;
      }
    }
    return null;
  }

  Serie? serieDe(Canal capitulo) {
    for (final serie in series) {
      if (serie.episodios.any((e) => e.canal.id == capitulo.id)) return serie;
    }
    return null;
  }

  SeccionNueva? seccionNueva(String clave) => seccionesNuevas.where((s) => s.clave == clave).firstOrNull;

  Serie? seriePorNombre(String nombre) {
    for (final serie in series) {
      if (serie.nombre == nombre) return serie;
    }
    return null;
  }
}

// ── Lo que no anda en este aparato ─────────────────────────────────

/// Lo que en ESTE aparato no se puede ver, y se deja de mostrar un tiempo
/// sin esperar al servidor:
///   - el decodificador del aparato no sabe mostrar ese video (con ninguna de
///     sus fuentes): 7 días. Ver ControlSenal.esconderDespuesDe.
///   - un video de YouTube que ya no existe o que su dueño no deja ver fuera
///     de YouTube: 3 días.
/// Lo que no conecta, tarda, manda basura o no muestra imagen un momento NO
/// se anota: suele ser pasajero (el canal sigue en la lista); si de verdad
/// está caído, lo saca el servidor. Mi cuenta en la TV lo muestra ("Lo que no
/// se ve en esta TV") y lo deja volver a mostrar ([volverAMostrarTodo]).
/// Se guarda en el aparato. La clave cambió en la 1.2.20: lo que habían
/// escondido las versiones anteriores (hasta 30 días, a veces por un error
/// pasajero) se olvida al actualizar.
class NoAnda {
  static const _clave = 'kairos.no_anda.2';
  static const _claveVieja = 'kairos.no_anda';
  static const _maximo = 500;

  static final Map<int, DateTime> _hasta = {};
  static bool _cargado = false;

  /// Avisa cuando se anota algo (el catálogo lo saca enseguida).
  static final cambios = ValueNotifier<int>(0);

  static bool oculto(int id) {
    final hasta = _hasta[id];
    return hasta != null && hasta.isAfter(DateTime.now());
  }

  /// Hasta cuándo está escondido (null = no lo está).
  static DateTime? hasta(int id) => oculto(id) ? _hasta[id] : null;

  /// Cuántos están escondidos ahora.
  static int get cuantos => _hasta.values.where((h) => h.isAfter(DateTime.now())).length;

  static Duration cuantoTiempo({required bool enVivo, required bool deFormato}) {
    if (deFormato) return const Duration(days: 7);
    return enVivo ? const Duration(hours: 1) : const Duration(days: 3);
  }

  /// Vuelve a mostrar todo lo escondido en este aparato (Mi cuenta en la TV).
  /// Para que reaparezca hay que volver a cargar el catálogo.
  static Future<void> volverAMostrarTodo() async {
    _hasta.clear();
    cambios.value++;
    await _guardar();
  }

  static Future<void> cargar() async {
    if (_cargado) return;
    _cargado = true;
    try {
      final preferencias = await SharedPreferences.getInstance();
      if (preferencias.containsKey(_claveVieja)) await preferencias.remove(_claveVieja);
      final guardados = jsonDecode(preferencias.getString(_clave) ?? '{}') as Map<String, dynamic>;
      for (final MapEntry(:key, :value) in guardados.entries) {
        final id = int.tryParse(key);
        if (id != null) _hasta[id] = DateTime.fromMillisecondsSinceEpoch(value as int);
      }
    } catch (_) {
      // Si no se puede leer, se arranca sin nada
    }
  }

  static void anotar(Canal canal, {required bool deFormato}) {
    final ahora = DateTime.now();
    _hasta
      ..removeWhere((_, hasta) => hasta.isBefore(ahora))
      ..[canal.id] = ahora.add(cuantoTiempo(enVivo: canal.contenido == 'vivo', deFormato: deFormato));
    while (_hasta.length > _maximo) {
      _hasta.remove(_hasta.keys.first);
    }
    cambios.value++;
    unawaited(_guardar());
  }

  static Future<void> _guardar() async {
    try {
      final preferencias = await SharedPreferences.getInstance();
      await preferencias.setString(
        _clave,
        jsonEncode({for (final MapEntry(:key, :value) in _hasta.entries) '$key': value.millisecondsSinceEpoch}),
      );
    } catch (_) {}
  }

  /// Solo para las pruebas.
  @visibleForTesting
  static void olvidarTodo() {
    _hasta.clear();
    _cargado = true;
  }
}

/// La fuente que mejor anduvo en ESTE aparato para cada canal (la que se vio
/// un buen rato sin cortarse, o la que eligió la persona y anduvo bien). La
/// próxima vez el canal arranca con esa, sin pasar por las que se trababan
/// (ej: en HBO la 1 se trababa y la 3 andaba perfecta: arranca en la 3).
/// Si la preferida empieza a cortarse, se olvida. Se guarda en el aparato.
class FuentePreferida {
  static const _clave = 'kairos.fuente_preferida';
  static const _maximo = 500;

  /// id del canal -> id de su fuente preferida.
  static final Map<int, int> _de = {};
  static bool _cargado = false;

  static int? de(int canal) => _de[canal];

  static Future<void> cargar() async {
    if (_cargado) return;
    _cargado = true;
    try {
      final preferencias = await SharedPreferences.getInstance();
      final guardados = jsonDecode(preferencias.getString(_clave) ?? '{}') as Map<String, dynamic>;
      for (final MapEntry(:key, :value) in guardados.entries) {
        final id = int.tryParse(key);
        if (id != null && value is int) _de[id] = value;
      }
    } catch (_) {
      // Si no se puede leer, se arranca sin nada
    }
  }

  static void anotar(int canal, int fuente) {
    if (_de[canal] == fuente) return;
    _de
      ..remove(canal) // al final: la más reciente
      ..[canal] = fuente;
    while (_de.length > _maximo) {
      _de.remove(_de.keys.first);
    }
    unawaited(_guardar());
  }

  static void olvidar(int canal, int fuente) {
    if (_de[canal] != fuente) return;
    _de.remove(canal);
    unawaited(_guardar());
  }

  static Future<void> _guardar() async {
    try {
      final preferencias = await SharedPreferences.getInstance();
      await preferencias.setString(_clave, jsonEncode({for (final e in _de.entries) '${e.key}': e.value}));
    } catch (_) {}
  }

  /// Solo para las pruebas.
  @visibleForTesting
  static void olvidarTodo() {
    _de.clear();
    _cargado = true;
  }
}

// ── Biblioteca (lo de este aparato) ────────────────────────────────

/// Por dónde iba una película o capítulo.
class Progreso {
  Progreso({required this.id, required this.posicion, required this.duracion, required this.cuando, this.aparato = ''});

  factory Progreso.desdeJson(Map<String, dynamic> json) => Progreso(
    id: json['id'] as int,
    posicion: Duration(seconds: json['p'] as int? ?? 0),
    duracion: Duration(seconds: json['d'] as int? ?? 0),
    cuando: DateTime.fromMillisecondsSinceEpoch(json['t'] as int? ?? 0),
    aparato: '${json['aparato'] ?? ''}',
  );

  final int id;
  final Duration posicion;
  final Duration duracion;
  final DateTime cuando;

  /// En qué aparato se miró (lo informa la app: "Smart TV Philips").
  final String aparato;

  double get fraccion => duracion.inSeconds == 0 ? 0 : (posicion.inSeconds / duracion.inSeconds).clamp(0, 1);

  /// Ya casi termina: cuenta como visto.
  bool get terminado => fraccion >= .95;

  Duration get falta => duracion - posicion;

  Map<String, dynamic> aJson() => {
    'id': id,
    'p': posicion.inSeconds,
    'd': duracion.inSeconds,
    't': cuando.millisecondsSinceEpoch,
    'aparato': aparato,
  };
}

/// Un canal en vivo que se miró hace poco: cuál, cuándo y en qué aparato.
class Visto {
  Visto({required this.id, required this.cuando, this.aparato = ''});

  factory Visto.desdeJson(Map<String, dynamic> json) => Visto(
    id: json['id'] as int,
    cuando: DateTime.fromMillisecondsSinceEpoch(json['t'] as int? ?? 0),
    aparato: '${json['aparato'] ?? ''}',
  );

  final int id;
  final DateTime cuando;
  final String aparato;

  Map<String, dynamic> aJson() => {'id': id, 't': cuando.millisecondsSinceEpoch, 'aparato': aparato};
}

/// "Estabas viendo X en la TV — Seguir acá": lo último que se miró en OTRO
/// aparato de la misma cuenta (una película o capítulo con su minuto, o un
/// canal en vivo).
class SeguirViendo {
  SeguirViendo({required this.id, required this.aparato, required this.cuando, this.progreso});

  final int id;
  final String aparato;
  final DateTime cuando;

  /// Null = un canal en vivo.
  final Progreso? progreso;

  String get clave => '$id@${cuando.millisecondsSinceEpoch}';
}

/// Los favoritos ("Mi lista"), "Continuar viendo" y los últimos canales
/// vistos son de la CUENTA, no del aparato (desde la 1.2.20): se guardan en
/// el servidor (/api/v1/biblioteca/) y los ven todos los aparatos de quien
/// entró. Si en una TV entra otro cliente, ve lo suyo, no lo del anterior.
/// Acá queda una copia por cuenta (abre al instante y anda sin internet) y
/// los cambios se mandan de a tandas (`_pendientes`): si la TV y el celular
/// cambian algo a la vez, se suman, no se pisan.
///
/// Lo que es del APARATO sigue acá nomás: volver al último canal al abrir
/// (con el último canal que se vio EN ESTE aparato), el modo de video y
/// "probar igual lo que quizá no lea".
///
/// Sin `api` (las pruebas) todo queda en memoria.
class Biblioteca extends ChangeNotifier {
  Biblioteca({this.api, this.cuenta = ''});

  final ApiCliente? api;

  /// Quién entró (el código del cliente o de la pantalla, o el usuario del
  /// panel): la copia guardada en el aparato es de esa cuenta.
  final String cuenta;

  // Lo que guardaban las versiones anteriores (en el aparato, de nadie): pasa a la cuenta del que esté
  static const _claveListaVieja = 'kairos.mi_lista';
  static const _claveProgresoViejo = 'kairos.progreso';
  static const _claveRecientesViejos = 'kairos.recientes';

  static const _claveVolverAlUltimo = 'kairos.volver_al_ultimo';
  static const _claveUltimoAca = 'kairos.ultimo_canal_aca';
  static const _claveVideoEnSuperficie = 'kairos.video_superficie';
  static const _claveProbarTodo = 'kairos.probar_todo';
  static const _claveSeguirDescartados = 'kairos.seguir_descartados';
  static const _maximoProgresos = 60;
  static const _maximoRecientes = 12;

  /// Cuánto espera para mandar los cambios (junta varios en un solo pedido).
  static const esperaParaMandar = Duration(seconds: 3);

  /// "Seguir acá" ofrece lo que se miró en otro aparato en estas últimas horas.
  static const seguirHasta = Duration(hours: 6);

  String get _claveCopia => 'kairos.biblioteca.$cuenta';

  SharedPreferences? _preferencias;
  final Set<String> _miLista = {};
  final Map<int, Progreso> _progresos = {};
  final List<Visto> _recientes = [];
  int? _ultimoAca;
  bool _volverAlUltimo = false;
  bool? _videoEnSuperficie;
  bool _probarTodo = false;
  final Set<String> _seguirDescartados = {};

  // Lo que todavía no llegó al servidor
  final Set<String> _agregar = {};
  final Set<String> _quitar = {};
  final Map<int, Progreso> _progresosPendientes = {};
  final Set<int> _olvidar = {};
  final Map<int, Visto> _vistosPendientes = {};
  Timer? _mandar;
  bool _mandando = false;
  bool _cerrada = false;

  bool get _hayPendientes =>
      _agregar.isNotEmpty ||
      _quitar.isNotEmpty ||
      _progresosPendientes.isNotEmpty ||
      _olvidar.isNotEmpty ||
      _vistosPendientes.isNotEmpty;

  Future<void> cargar() async {
    ControlSenal.enSuperficie = videoEnSuperficie;
    try {
      final preferencias = await SharedPreferences.getInstance();
      _preferencias = preferencias;
      _probarTodo = preferencias.getBool(_claveProbarTodo) ?? false;
      FuenteCanal.probarTodo = _probarTodo;
      _volverAlUltimo = preferencias.getBool(_claveVolverAlUltimo) ?? false;
      _ultimoAca = preferencias.getInt(_claveUltimoAca);
      _videoEnSuperficie = preferencias.getBool(_claveVideoEnSuperficie);
      ControlSenal.enSuperficie = videoEnSuperficie;
      _seguirDescartados.addAll(preferencias.getStringList(_claveSeguirDescartados) ?? []);
      if (api != null) {
        _leerCopia(preferencias);
        _pasarLoViejo(preferencias);
      }
    } catch (_) {
      // Si no se puede leer (ej: en los tests), se arranca vacía
    }
    notifyListeners();
    await sincronizar();
  }

  /// La copia de esta cuenta que quedó en el aparato (con lo que no se llegó a mandar).
  void _leerCopia(SharedPreferences preferencias) {
    final texto = preferencias.getString(_claveCopia);
    if (texto == null) return;
    final copia = jsonDecode(texto) as Map<String, dynamic>;
    _ponerDelServidor(copia);
    final pendientes = copia['pendientes'] as Map<String, dynamic>? ?? {};
    _agregar.addAll([for (final c in pendientes['agregar'] as List? ?? []) '$c']);
    _quitar.addAll([for (final c in pendientes['quitar'] as List? ?? []) '$c']);
    _olvidar.addAll([for (final i in pendientes['olvidar'] as List? ?? []) i as int]);
    for (final p in pendientes['progresos'] as List? ?? []) {
      final progreso = Progreso.desdeJson(p as Map<String, dynamic>);
      _progresosPendientes[progreso.id] = progreso;
    }
    for (final v in pendientes['vistos'] as List? ?? []) {
      final visto = Visto.desdeJson(v as Map<String, dynamic>);
      _vistosPendientes[visto.id] = visto;
    }
    _aplicarPendientes();
  }

  /// Hasta la 1.2.19 esto quedaba en el aparato: lo que había pasa a la cuenta del que está (una sola vez).
  void _pasarLoViejo(SharedPreferences preferencias) {
    final lista = preferencias.getStringList(_claveListaVieja);
    final progresos = preferencias.getString(_claveProgresoViejo);
    final recientes = preferencias.getStringList(_claveRecientesViejos);
    if (lista == null && progresos == null && recientes == null) return;
    _agregar.addAll((lista ?? []).where((c) => !_quitar.contains(c)));
    for (final p in jsonDecode(progresos ?? '[]') as List) {
      final progreso = Progreso.desdeJson(p as Map<String, dynamic>);
      _progresosPendientes[progreso.id] = progreso;
    }
    final ahora = DateTime.now();
    final ids = (recientes ?? []).map(int.tryParse).nonNulls.toList();
    for (final (orden, id) in ids.indexed) {
      // Sin hora guardada: se respeta el orden (el primero, el más reciente)
      _vistosPendientes[id] = Visto(
        id: id,
        cuando: ahora.subtract(Duration(minutes: 30 + orden)),
      );
    }
    _ultimoAca ??= ids.firstOrNull;
    if (_ultimoAca != null) preferencias.setInt(_claveUltimoAca, _ultimoAca!);
    _aplicarPendientes();
    _guardarCopia();
    preferencias
      ..remove(_claveListaVieja)
      ..remove(_claveProgresoViejo)
      ..remove(_claveRecientesViejos);
  }

  /// Manda lo pendiente y trae lo de la cuenta (lo que cambió en otros aparatos).
  /// Se llama al abrir, al volver a la app y cada tanto (ver estructura.dart).
  Future<void> sincronizar() async {
    final api = this.api;
    if (api == null || _mandando || _cerrada) return;
    _mandar?.cancel();
    _mandando = true;
    final enviados = (
      agregar: {..._agregar},
      quitar: {..._quitar},
      progresos: {..._progresosPendientes},
      olvidar: {..._olvidar},
      vistos: {..._vistosPendientes},
    );
    try {
      final respuesta = _hayPendientes
          ? await api.post('biblioteca/', {
              'aparato': Aparato.nombre,
              'agregar': enviados.agregar.toList(),
              'quitar': enviados.quitar.toList(),
              'progresos': [for (final p in enviados.progresos.values) p.aJson()],
              'olvidar': enviados.olvidar.toList(),
              'vistos': [for (final v in enviados.vistos.values) v.aJson()],
            })
          : await api.get('biblioteca/');
      if (_cerrada) return;
      // Ya llegó: se saca de pendientes (lo que cambió mientras tanto queda para la próxima)
      _agregar.removeAll(enviados.agregar);
      _quitar.removeAll(enviados.quitar);
      _olvidar.removeAll(enviados.olvidar);
      enviados.progresos.forEach((id, p) {
        if (identical(_progresosPendientes[id], p)) _progresosPendientes.remove(id);
      });
      enviados.vistos.forEach((id, v) {
        if (identical(_vistosPendientes[id], v)) _vistosPendientes.remove(id);
      });
      _ponerDelServidor(respuesta as Map<String, dynamic>);
      _aplicarPendientes();
      _guardarCopia();
      notifyListeners();
    } on ApiError {
      // Sin internet o el servidor no está: queda pendiente y se manda la próxima vez
    } catch (_) {
      // Una respuesta rara no puede romper la app
    } finally {
      _mandando = false;
    }
    if (_hayPendientes && !_cerrada) _programarEnvio();
  }

  void _ponerDelServidor(Map<String, dynamic> datos) {
    _miLista
      ..clear()
      ..addAll([for (final c in datos['favoritos'] as List? ?? []) '$c']);
    _progresos
      ..clear()
      ..addAll({
        for (final p in datos['progresos'] as List? ?? [])
          (p as Map<String, dynamic>)['id'] as int: Progreso.desdeJson(p),
      });
    _recientes
      ..clear()
      ..addAll([for (final v in datos['recientes'] as List? ?? []) Visto.desdeJson(v as Map<String, dynamic>)])
      ..sort((a, b) => b.cuando.compareTo(a.cuando));
  }

  /// Lo que se hizo acá y el servidor todavía no sabe, encima de lo que mandó.
  void _aplicarPendientes() {
    _miLista
      ..addAll(_agregar)
      ..removeAll(_quitar);
    for (final id in _olvidar) {
      _progresos.remove(id);
    }
    _progresosPendientes.forEach((id, p) {
      final actual = _progresos[id];
      if (actual == null || !actual.cuando.isAfter(p.cuando)) _progresos[id] = p;
    });
    for (final visto in _vistosPendientes.values) {
      final actual = _recientes.where((r) => r.id == visto.id).firstOrNull;
      if (actual != null && actual.cuando.isAfter(visto.cuando)) continue;
      _recientes
        ..remove(actual)
        ..add(visto);
    }
    _recientes.sort((a, b) => b.cuando.compareTo(a.cuando));
    if (_recientes.length > _maximoRecientes) _recientes.removeRange(_maximoRecientes, _recientes.length);
    while (_progresos.length > _maximoProgresos) {
      final viejo = _progresos.values.reduce((a, b) => a.cuando.isBefore(b.cuando) ? a : b);
      _progresos.remove(viejo.id);
    }
  }

  void _guardarCopia() {
    if (api == null) return;
    _preferencias?.setString(
      _claveCopia,
      jsonEncode({
        'favoritos': _miLista.toList(),
        'progresos': [for (final p in _progresos.values) p.aJson()],
        'recientes': [for (final v in _recientes) v.aJson()],
        'pendientes': {
          'agregar': _agregar.toList(),
          'quitar': _quitar.toList(),
          'olvidar': _olvidar.toList(),
          'progresos': [for (final p in _progresosPendientes.values) p.aJson()],
          'vistos': [for (final v in _vistosPendientes.values) v.aJson()],
        },
      }),
    );
  }

  /// Un cambio hecho acá: se ve ya y se manda al servidor en unos segundos.
  void _cambio() {
    _guardarCopia();
    notifyListeners();
    _programarEnvio();
  }

  void _programarEnvio() {
    if (api == null || _cerrada) return;
    _mandar?.cancel();
    _mandar = Timer(esperaParaMandar, sincronizar);
  }

  @override
  void dispose() {
    _cerrada = true;
    _mandar?.cancel();
    super.dispose();
  }

  // Mi lista: canales y películas por "c:<id>", series por "s:<nombre>"
  static String claveDe(Canal canal) => 'c:${canal.id}';

  bool estaEnMiLista(String clave) => _miLista.contains(clave);

  Iterable<String> get miLista => _miLista;

  void alternarMiLista(String clave) {
    if (_miLista.remove(clave)) {
      _agregar.remove(clave);
      _quitar.add(clave);
    } else {
      _miLista.add(clave);
      _quitar.remove(clave);
      _agregar.add(clave);
      Medidor.favorito(clave); // para "Lo más visto" del panel (sin decir quién)
    }
    _cambio();
  }

  // Últimos canales vistos (de la cuenta, en cualquier aparato)
  List<int> get recientes => [for (final v in _recientes) v.id];

  /// El último canal que se vio EN ESTE aparato (para "volver al último canal al abrir").
  int? get ultimoCanal => _ultimoAca;

  void registrarCanalVisto(int id) {
    if (_ultimoAca != id) {
      _ultimoAca = id;
      _preferencias?.setInt(_claveUltimoAca, id);
    }
    final visto = Visto(id: id, cuando: DateTime.now(), aparato: Aparato.nombre);
    _recientes
      ..removeWhere((r) => r.id == id)
      ..insert(0, visto);
    if (_recientes.length > _maximoRecientes) _recientes.removeLast();
    _vistosPendientes[id] = visto;
    _cambio();
  }

  /// Al abrir la app, ¿arrancar con el último canal que se vio? (Mi cuenta; es de este aparato)
  bool get volverAlUltimo => _volverAlUltimo;

  set volverAlUltimo(bool valor) {
    _volverAlUltimo = valor;
    _preferencias?.setBool(_claveVolverAlUltimo, valor);
    notifyListeners();
  }

  /// Modo de video (Mi cuenta en la TV): dibujarlo en una superficie de
  /// Android (ver ControlSenal.enSuperficie). Si no se eligió, en la TV sí:
  /// es lo que evita la imagen verde o negra en muchos TV box.
  bool get videoEnSuperficie => _videoEnSuperficie ?? Aparato.esTv;

  set videoEnSuperficie(bool valor) {
    _videoEnSuperficie = valor;
    ControlSenal.enSuperficie = valor;
    _preferencias?.setBool(_claveVideoEnSuperficie, valor);
    notifyListeners();
  }

  /// "Probar igual lo que quizá no lea" (Mi cuenta en la TV): mostrar también
  /// lo que tiene un códec que este aparato dice no leer (por si lo lee igual).
  /// Hay que volver a cargar el catálogo para que aparezca.
  bool get probarTodo => _probarTodo;

  set probarTodo(bool valor) {
    _probarTodo = valor;
    FuenteCanal.probarTodo = valor;
    _preferencias?.setBool(_claveProbarTodo, valor);
    notifyListeners();
  }

  // Continuar viendo
  Progreso? progresoDe(int id) => _progresos[id];

  /// Los que quedaron a medias, el último visto primero.
  List<Progreso> get continuarViendo =>
      _progresos.values.where((p) => p.fraccion > .01 && !p.terminado).toList()
        ..sort((a, b) => b.cuando.compareTo(a.cuando));

  void guardarProgreso(int id, Duration posicion, Duration duracion) {
    if (duracion.inSeconds < 60) return; // un vivo o algo muy corto: no tiene sentido
    final progreso = Progreso(
      id: id,
      posicion: posicion,
      duracion: duracion,
      cuando: DateTime.now(),
      aparato: Aparato.nombre,
    );
    _progresos[id] = progreso;
    _olvidar.remove(id);
    _progresosPendientes[id] = progreso;
    if (_progresos.length > _maximoProgresos) {
      final viejo = _progresos.values.reduce((a, b) => a.cuando.isBefore(b.cuando) ? a : b);
      _progresos.remove(viejo.id);
    }
    _cambio();
  }

  void olvidarProgreso(int id) {
    _progresos.remove(id);
    _progresosPendientes.remove(id);
    _olvidar.add(id);
    _cambio();
  }

  /// "Estabas viendo X en la TV — Seguir acá": lo último que se miró en OTRO
  /// aparato de esta cuenta en las últimas [seguirHasta] (null si no hay, o
  /// si ya se descartó o se siguió).
  SeguirViendo? get seguirDeOtroAparato {
    final desde = DateTime.now().subtract(seguirHasta);
    bool deOtro(String aparato, DateTime cuando) =>
        aparato.isNotEmpty && aparato != Aparato.nombre && cuando.isAfter(desde);
    final candidatos = [
      for (final p in _progresos.values)
        if (deOtro(p.aparato, p.cuando) && !p.terminado)
          SeguirViendo(id: p.id, aparato: p.aparato, cuando: p.cuando, progreso: p),
      for (final v in _recientes)
        if (deOtro(v.aparato, v.cuando)) SeguirViendo(id: v.id, aparato: v.aparato, cuando: v.cuando),
    ]..sort((a, b) => b.cuando.compareTo(a.cuando));
    final ultimo = candidatos.firstOrNull;
    if (ultimo == null || _seguirDescartados.contains(ultimo.clave)) return null;
    // Si después ya se miró algo en ESTE aparato, no se ofrece
    final aca = [
      ..._progresos.values.where((p) => p.aparato == Aparato.nombre).map((p) => p.cuando),
      ..._recientes.where((v) => v.aparato == Aparato.nombre).map((v) => v.cuando),
    ];
    if (aca.any((cuando) => cuando.isAfter(ultimo.cuando))) return null;
    return ultimo;
  }

  /// Ya se siguió o se cerró el aviso: no se vuelve a ofrecer ese mismo.
  void descartarSeguir(SeguirViendo seguir) {
    _seguirDescartados.add(seguir.clave);
    final ultimos = _seguirDescartados.toList();
    _preferencias?.setStringList(
      _claveSeguirDescartados,
      ultimos.sublist(ultimos.length > 20 ? ultimos.length - 20 : 0),
    );
    notifyListeners();
  }
}

/// Pone el catálogo y la biblioteca al alcance de todas las pantallas de celular.
class DatosScope extends InheritedWidget {
  const DatosScope({super.key, required this.catalogo, required this.biblioteca, required super.child});

  final Catalogo catalogo;
  final Biblioteca biblioteca;

  static DatosScope of(BuildContext context) => context.dependOnInheritedWidgetOfExactType<DatosScope>()!;

  @override
  bool updateShouldNotify(DatosScope oldWidget) => catalogo != oldWidget.catalogo || biblioteca != oldWidget.biblioteca;
}
