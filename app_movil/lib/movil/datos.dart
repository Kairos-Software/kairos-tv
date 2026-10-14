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

/// Lo que en ESTE aparato no se puede ver nunca, y se deja de mostrar un
/// tiempo sin esperar al servidor:
///   - formato (el aparato no sabe mostrar ese video, con ninguna de sus
///     fuentes): 30 días; no va a cambiar. Ver ControlSenal.esconderDespuesDe.
///   - un video de YouTube que ya no existe o que su dueño no deja ver fuera
///     de YouTube: 3 días.
/// Lo que no conecta o tarda NO se anota: suele ser pasajero (el canal sigue
/// en la lista); si de verdad está caído, lo saca el servidor.
/// Se guarda en el aparato.
class NoAnda {
  static const _clave = 'kairos.no_anda';
  static const _maximo = 500;

  static final Map<int, DateTime> _hasta = {};
  static bool _cargado = false;

  /// Avisa cuando se anota algo (el catálogo lo saca enseguida).
  static final cambios = ValueNotifier<int>(0);

  static bool oculto(int id) {
    final hasta = _hasta[id];
    return hasta != null && hasta.isAfter(DateTime.now());
  }

  static Duration cuantoTiempo({required bool enVivo, required bool deFormato}) {
    if (deFormato) return const Duration(days: 30);
    return enVivo ? const Duration(hours: 1) : const Duration(days: 3);
  }

  static Future<void> cargar() async {
    if (_cargado) return;
    _cargado = true;
    try {
      final preferencias = await SharedPreferences.getInstance();
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
  Progreso({required this.id, required this.posicion, required this.duracion, required this.cuando});

  factory Progreso.desdeJson(Map<String, dynamic> json) => Progreso(
    id: json['id'] as int,
    posicion: Duration(seconds: json['p'] as int? ?? 0),
    duracion: Duration(seconds: json['d'] as int? ?? 0),
    cuando: DateTime.fromMillisecondsSinceEpoch(json['t'] as int? ?? 0),
  );

  final int id;
  final Duration posicion;
  final Duration duracion;
  final DateTime cuando;

  double get fraccion => duracion.inSeconds == 0 ? 0 : (posicion.inSeconds / duracion.inSeconds).clamp(0, 1);

  /// Ya casi termina: cuenta como visto.
  bool get terminado => fraccion >= .95;

  Duration get falta => duracion - posicion;

  Map<String, dynamic> aJson() => {
    'id': id,
    'p': posicion.inSeconds,
    'd': duracion.inSeconds,
    't': cuando.millisecondsSinceEpoch,
  };
}

/// Los favoritos ("Mi lista"), "Continuar viendo", los últimos canales vistos
/// y las preferencias. Se guarda en el aparato (no en el servidor).
class Biblioteca extends ChangeNotifier {
  static const _claveLista = 'kairos.mi_lista';
  static const _claveProgreso = 'kairos.progreso';
  static const _claveRecientes = 'kairos.recientes';
  static const _claveVolverAlUltimo = 'kairos.volver_al_ultimo';
  static const _maximoProgresos = 60;
  static const _maximoRecientes = 12;

  SharedPreferences? _preferencias;
  final Set<String> _miLista = {};
  final Map<int, Progreso> _progresos = {};
  final List<int> _recientes = [];
  bool _volverAlUltimo = false;
  static const _claveVideoEnSuperficie = 'kairos.video_superficie';
  bool? _videoEnSuperficie;

  Future<void> cargar() async {
    ControlSenal.enSuperficie = videoEnSuperficie;
    try {
      final preferencias = await SharedPreferences.getInstance();
      _preferencias = preferencias;
      _miLista.addAll(preferencias.getStringList(_claveLista) ?? []);
      _recientes.addAll((preferencias.getStringList(_claveRecientes) ?? []).map(int.tryParse).nonNulls);
      _volverAlUltimo = preferencias.getBool(_claveVolverAlUltimo) ?? false;
      _videoEnSuperficie = preferencias.getBool(_claveVideoEnSuperficie);
      ControlSenal.enSuperficie = videoEnSuperficie;
      final guardados = jsonDecode(preferencias.getString(_claveProgreso) ?? '[]') as List;
      for (final p in guardados) {
        final progreso = Progreso.desdeJson(p as Map<String, dynamic>);
        _progresos[progreso.id] = progreso;
      }
    } catch (_) {
      // Si no se puede leer (ej: en los tests), se arranca vacía
    }
    notifyListeners();
  }

  // Mi lista: canales y películas por "c:<id>", series por "s:<nombre>"
  static String claveDe(Canal canal) => 'c:${canal.id}';

  bool estaEnMiLista(String clave) => _miLista.contains(clave);

  Iterable<String> get miLista => _miLista;

  void alternarMiLista(String clave) {
    if (!_miLista.remove(clave)) {
      _miLista.add(clave);
      Medidor.favorito(clave); // para "Lo más visto" del panel (sin decir quién)
    }
    _preferencias?.setStringList(_claveLista, _miLista.toList());
    notifyListeners();
  }

  // Últimos canales vistos
  List<int> get recientes => List.unmodifiable(_recientes);

  int? get ultimoCanal => _recientes.firstOrNull;

  void registrarCanalVisto(int id) {
    if (_recientes.firstOrNull == id) return;
    _recientes
      ..remove(id)
      ..insert(0, id);
    if (_recientes.length > _maximoRecientes) _recientes.removeLast();
    _preferencias?.setStringList(_claveRecientes, [for (final r in _recientes) '$r']);
    notifyListeners();
  }

  /// Al abrir la app, ¿arrancar con el último canal que se vio? (Mi cuenta)
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

  // Continuar viendo
  Progreso? progresoDe(int id) => _progresos[id];

  /// Los que quedaron a medias, el último visto primero.
  List<Progreso> get continuarViendo =>
      _progresos.values.where((p) => p.fraccion > .01 && !p.terminado).toList()
        ..sort((a, b) => b.cuando.compareTo(a.cuando));

  void guardarProgreso(int id, Duration posicion, Duration duracion) {
    if (duracion.inSeconds < 60) return; // un vivo o algo muy corto: no tiene sentido
    _progresos[id] = Progreso(id: id, posicion: posicion, duracion: duracion, cuando: DateTime.now());
    if (_progresos.length > _maximoProgresos) {
      final viejo = _progresos.values.reduce((a, b) => a.cuando.isBefore(b.cuando) ? a : b);
      _progresos.remove(viejo.id);
    }
    _preferencias?.setString(_claveProgreso, jsonEncode([for (final p in _progresos.values) p.aJson()]));
    notifyListeners();
  }

  void olvidarProgreso(int id) {
    _progresos.remove(id);
    _preferencias?.setString(_claveProgreso, jsonEncode([for (final p in _progresos.values) p.aJson()]));
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
