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
import 'copia_catalogo.dart';
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

/// Lo que manda el servidor de una serie SIN sus capítulos (GET /canales/series/, desde la 1.2.38): con
/// decenas de miles de capítulos, bajarlos todos al abrir la app ya no entraba en un TV box. Los capítulos
/// se piden al abrir la serie ([Catalogo.abrirSerie]).
class ResumenDeSerie {
  ResumenDeSerie({
    required this.capitulos,
    required this.temporadas,
    this.imagen = '',
    this.destacada = false,
    this.codecs = const [],
  });

  ResumenDeSerie.desdeJson(Map<String, dynamic> json)
    : capitulos = json['capitulos'] as int? ?? 0,
      temporadas = [
        for (final t in json['temporadas'] as List? ?? const [])
          if (t is List && t.length >= 2) (t[0] as int, t[1] as int),
      ],
      imagen = '${json['imagen'] ?? ''}',
      destacada = json['destacada'] == true,
      codecs = [for (final c in json['codecs'] as List? ?? const []) '$c'];

  /// Cuántos capítulos manda el servidor (este aparato puede ver alguno menos).
  final int capitulos;

  /// (número, cuántos capítulos) de cada temporada.
  final List<(int, int)> temporadas;

  /// La portada propia o la imagen del primer capítulo que tiene.
  final String imagen;
  final bool destacada;

  /// Los códecs de sus señales ('' = no se sabe).
  final List<String> codecs;
}

/// Una serie con sus temporadas (armada a partir de los capítulos sueltos), o
/// todavía resumida: con [resumen] y sin capítulos hasta que se abre.
class Serie {
  Serie({required this.nombre, required this.categoria, this.portada = '', this.resumen}) : cargada = resumen == null;

  /// Una de la lista del servidor (GET /canales/series/): sin capítulos todavía.
  factory Serie.resumida(Map<String, dynamic> json) => Serie(
    nombre: '${json['nombre'] ?? ''}',
    categoria: '${json['categoria'] ?? ''}',
    resumen: ResumenDeSerie.desdeJson(json),
  );

  final String nombre;
  final String categoria;
  final Map<int, List<Episodio>> temporadas = {};

  /// La portada propia de la serie, si se la pusieron en el panel ('' = no tiene).
  final String portada;

  /// Lo que dijo el servidor antes de traer los capítulos (null: se armó de los capítulos).
  final ResumenDeSerie? resumen;

  /// Ya tiene sus capítulos (los de este aparato). Una resumida, recién cuando se abre.
  bool cargada;

  /// La imagen de la serie: su portada o, si no tiene, la del primer capítulo que tenga.
  String get imagen {
    if (portada.isNotEmpty) return portada;
    final delPrimero = episodios.map((e) => e.canal.logo).firstWhere((logo) => logo.isNotEmpty, orElse: () => '');
    return delPrimero.isNotEmpty ? delPrimero : (resumen?.imagen ?? '');
  }

  List<int> get numerosDeTemporada =>
      cargada ? (temporadas.keys.toList()..sort()) : [for (final (t, _) in resumen!.temporadas) t];

  /// Cuántos capítulos y temporadas tiene (antes de abrirla, lo que dijo el servidor).
  int get cantidadDeCapitulos => cargada ? episodios.length : resumen!.capitulos;

  int get cantidadDeTemporadas => cargada ? temporadas.length : resumen!.temporadas.length;

  /// Si este aparato la puede mostrar por el códec de sus señales (antes de abrirla: después lo
  /// decide cada capítulo, como siempre).
  bool get aparatoLaMuestra {
    final codecs = resumen?.codecs ?? const <String>[];
    if (cargada || codecs.isEmpty || FuenteCanal.probarTodo || Aparato.codecs.isEmpty) return true;
    return codecs.any((c) => c.isEmpty || Aparato.codecs.contains(c));
  }

  /// Si sus capítulos dicen temporada y capítulo ("S01 E02"). Un video suelto
  /// cargado como serie no lo dice: no se puede saber cuál es el primero.
  bool numerada = false;

  /// Se puede seguir desde el principio: tiene el T1:E1. Una serie nueva se
  /// muestra desde su primer capítulo; las que empiezan a mitad no se muestran.
  /// Una resumida, sí (el servidor solo manda las que tienen el T1:E1).
  bool get completa => !cargada || (numerada && (temporadas[1]?.any((e) => e.numero == 1) ?? false));

  /// Sus capítulos, en orden (vacío si todavía no se abrió: ver [cargada]).
  List<Episodio> get episodios => [for (final t in temporadas.keys.toList()..sort()) ...temporadas[t]!];

  /// Destacada en el panel (se marcan sus capítulos): el modo reposo la muestra más seguido.
  bool get destacada => cargada ? episodios.any((e) => e.canal.destacado) : resumen!.destacada;

  /// Para "Mi lista": las series se guardan por nombre (sus capítulos tienen cada uno su id).
  String get clave => 's:$nombre';

  /// Una copia con solo los capítulos que cumplen [queda] (sin las temporadas
  /// que quedan vacías). Esta no se toca: es la que mandó el servidor.
  Serie soloCon(bool Function(Canal) queda) {
    final copia = Serie(nombre: nombre, categoria: categoria, portada: portada, resumen: resumen)
      ..numerada = numerada
      ..cargada = cargada;
    for (final MapEntry(key: numero, value: capitulos) in temporadas.entries) {
      final quedan = [
        for (final e in capitulos)
          if (queda(e.canal)) e,
      ];
      if (quedan.isNotEmpty) copia.temporadas[numero] = quedan;
    }
    return copia;
  }
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
///
/// Queda guardado en el aparato (movil/copia_catalogo.dart): al abrir la app
/// se muestra enseguida lo guardado y por detrás se pregunta si cambió. Lo que
/// mandó el servidor queda tal cual en [_partes] (sin filtrar): si no cambió,
/// no se baja ni se lee nada.
class Catalogo extends ChangeNotifier {
  Catalogo(this.api) : _copia = CopiaCatalogo(api.urlBase) {
    NoAnda.cambios.addListener(_sacarLoQueNoAnda);
  }

  final ApiCliente api;
  final CopiaCatalogo _copia;

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

  // Lo que se muestra. Al cambiar una lista se olvidan los índices ([_indices]).
  List<CategoriaCanales> _categoriasEnVivo = [];
  List<Canal> _peliculas = [];
  List<Serie> _series = [];
  List<SeccionNueva> _seccionesNuevas = [];

  List<CategoriaCanales> get categoriasEnVivo => _categoriasEnVivo;
  set categoriasEnVivo(List<CategoriaCanales> valor) {
    _categoriasEnVivo = valor;
    _olvidarIndices();
  }

  List<Canal> get peliculas => _peliculas;
  set peliculas(List<Canal> valor) {
    _peliculas = valor;
    _olvidarIndices();
  }

  List<Serie> get series => _series;
  set series(List<Serie> valor) {
    _series = valor;
    _olvidarIndices();
  }

  /// Las secciones creadas en el panel que tienen algo para ver acá, en el orden del menú.
  List<SeccionNueva> get seccionesNuevas => _seccionesNuevas;
  set seccionesNuevas(List<SeccionNueva> valor) {
    _seccionesNuevas = valor;
    _olvidarIndices();
  }

  /// Lo de las secciones nuevas "en vivo" (radios...) y "a demanda" (música...), para favoritos y búsquedas.
  List<Canal> get _vivosNuevos => [for (final s in seccionesNuevas.where((s) => s.enVivo)) ...s.canales];

  List<Canal> get _aDemandaNuevos => [for (final s in seccionesNuevas.where((s) => !s.enVivo)) ...s.canales];

  bool cargando = false;
  bool cargado = false;
  Object? error;

  /// Los capítulos que ya se trajeron de cada serie resumida (por nombre en minúsculas), sin filtrar.
  final Map<String, List<Canal>> _capitulosTraidos = {};

  /// Los capítulos (de "Continuar viendo") cuya serie ya se pidió: no se vuelven a pedir.
  final Set<int> _idsPedidos = {};

  /// Las series que se están trayendo (si dos pantallas piden la misma, se pide una vez).
  final Map<String, Future<void>> _trayendo = {};

  /// Lo que mandó el servidor de cada parte ("vivo", "pelicula", "serie" y
  /// `s:clave` de cada sección nueva), con su huella, sin filtrar.
  final Map<String, ({String huella, ParteCatalogo parte})> _partes = {};

  /// Las secciones nuevas como las mandó el servidor (sin sus canales).
  List<SeccionNueva> _definiciones = [];

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

  /// Todos los canales en vivo, en el orden de la grilla.
  List<Canal> get canales => _canales ??= [for (final c in categoriasEnVivo) ...c.canales];

  // ── Índices: para no recorrer miles de películas y capítulos cada vez ──
  List<Canal>? _canales;
  Map<int, Canal>? _porId;
  Map<int, Serie>? _serieDelCapitulo;
  Map<String, Serie>? _seriePorNombre;

  void _olvidarIndices() {
    _canales = null;
    _porId = null;
    _serieDelCapitulo = null;
    _seriePorNombre = null;
  }

  /// Se arman la primera vez que se buscan (y se olvidan cuando cambia una lista).
  void _indices() {
    // En el mismo orden en que se buscaba antes: en vivo, películas, secciones nuevas, capítulos
    final porId = <int, Canal>{};
    for (final canal in [...canales, ...peliculas, for (final s in seccionesNuevas) ...s.canales]) {
      porId.putIfAbsent(canal.id, () => canal);
    }
    final serieDelCapitulo = <int, Serie>{};
    final seriePorNombre = <String, Serie>{};
    for (final serie in series) {
      seriePorNombre.putIfAbsent(serie.nombre, () => serie);
      for (final episodio in serie.episodios) {
        porId.putIfAbsent(episodio.canal.id, () => episodio.canal);
        serieDelCapitulo.putIfAbsent(episodio.canal.id, () => serie);
      }
    }
    _porId = porId;
    _serieDelCapitulo = serieDelCapitulo;
    _seriePorNombre = seriePorNombre;
  }

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
    final lugar = _lugarEnLaLista(biblioteca);
    return series.where((s) => lugar.containsKey(s.clave)).toList()
      ..sort((a, b) => lugar[a.clave]!.compareTo(lugar[b.clave]!));
  }

  List<Canal> _deLaLista(Biblioteca biblioteca, List<Canal> todos) {
    final lugar = _lugarEnLaLista(biblioteca);
    return todos.where((c) => lugar.containsKey(Biblioteca.claveDe(c))).toList()
      ..sort((a, b) => lugar[Biblioteca.claveDe(a)]!.compareTo(lugar[Biblioteca.claveDe(b)]!));
  }

  /// {clave: lugar en Mi lista}: buscar en un Map es al instante (en la lista había que recorrerla).
  static Map<String, int> _lugarEnLaLista(Biblioteca biblioteca) => {
    for (final (lugar, clave) in biblioteca.miLista.indexed) clave: lugar,
  };

  /// Los últimos canales en vivo vistos en este aparato (el más reciente primero).
  List<Canal> canalesRecientes(Biblioteca biblioteca) {
    final enVivo = {for (final c in canales) c.id: c};
    return [for (final id in biblioteca.recientes) ?enVivo[id]];
  }

  Future<void> cargar() async {
    if (cargando) return;
    cargando = true;
    error = null;
    notifyListeners();
    try {
      await Future.wait([NoAnda.cargar(), FuentePreferida.cargar(), CalidadYoutube.cargar()]);
      // La primera vez: lo guardado en el aparato, para mostrar algo enseguida
      if (!cargado && await _abrirLoGuardado()) {
        _aplicar();
        cargado = true;
        notifyListeners();
      }
      await _traerDelServidor();
      // Siempre se vuelve a filtrar (es rápido): lo que se volvió a mostrar en
      // Mi cuenta o "Probar igual lo que quizá no lea" aparecen aunque el
      // servidor no haya cambiado nada
      _aplicar();
      cargado = true;
    } catch (e) {
      error = e;
    } finally {
      cargando = false;
      notifyListeners();
    }
  }

  /// Lee lo guardado en el aparato (en otro hilo). False si no hay (o le falta una parte).
  Future<bool> _abrirLoGuardado() async {
    // Las series: la lista resumida (desde la 1.2.38) o, de un servidor viejo, todos los capítulos
    final resumidas = await _copia.leer('series');
    final claveSeries = resumidas != null ? 'series' : 'serie';
    final guardadas = await Future.wait([
      for (final p in ['vivo', 'pelicula']) _copia.leer(p),
      if (resumidas != null) Future.value(resumidas) else _copia.leer('serie'),
      _copia.leer('secciones'),
    ]);
    if (guardadas.any((g) => g == null)) return false;
    try {
      final definiciones = _leerSecciones(guardadas[3]!.bytes);
      final deSecciones = await Future.wait([for (final s in definiciones) _copia.leer('s:${s.clave}')]);
      final leidas = await Future.wait([
        leerParteAparte(guardadas[0]!.bytes, 'vivo'),
        leerParteAparte(guardadas[1]!.bytes, 'pelicula'),
        if (resumidas != null) leerSeriesAparte(guardadas[2]!.bytes) else leerParteAparte(guardadas[2]!.bytes, 'serie'),
        for (final (i, s) in definiciones.indexed)
          if (deSecciones[i] case final guardada?) leerParteAparte(guardada.bytes, s.forma),
      ]);
      for (final (i, clave) in ['vivo', 'pelicula', claveSeries].indexed) {
        _partes[clave] = (huella: guardadas[i]!.huella, parte: leidas[i]);
      }
      var siguiente = 3;
      for (final (i, s) in definiciones.indexed) {
        if (deSecciones[i] case final guardada?) {
          _partes['s:${s.clave}'] = (huella: guardada.huella, parte: leidas[siguiente++]);
        }
      }
      _definiciones = definiciones;
      return true;
    } catch (_) {
      // Una copia rota (o de otra versión): se baja de nuevo
      _partes.clear();
      return false;
    }
  }

  static List<SeccionNueva> _leerSecciones(List<int> bytes) {
    final datos = jsonDecode(utf8.decode(bytes)) as Map<String, dynamic>;
    return [for (final s in datos['secciones'] as List) SeccionNueva.desdeJson(s as Map<String, dynamic>)];
  }

  /// Le pregunta al servidor por cada parte (con su huella). True si algo cambió.
  Future<bool> _traerDelServidor() async {
    final formatos = FuenteCanal.formatosQueReproduce.join(',');

    // Una parte: si no cambió (304) queda la que había; si cambió, se lee en otro hilo y se guarda
    Future<bool> traer(String clave, String contenido, String forma) async {
      final anterior = _partes[clave];
      final llegado = await api.getCrudo(
        'canales/',
        parametros: {'formatos': formatos, 'contenido': contenido},
        huella: anterior?.huella ?? '',
      );
      final bytes = llegado.bytes;
      if (bytes == null) {
        if (anterior != null) return false;
        throw ApiError(status: 304, codigo: 'respuesta_invalida', detalle: 'El servidor respondió algo inesperado.');
      }
      _partes[clave] = (huella: llegado.huella, parte: await leerParteAparte(bytes, forma));
      await _copia.guardar(clave, bytes, llegado.huella);
      return true;
    }

    // Las secciones nuevas: la lista y lo de cada una. Un servidor viejo no
    // tiene /secciones/: entonces no hay ninguna (no es un error).
    Future<bool> traerSeccionesNuevas() async {
      final List<SeccionNueva> nuevas;
      final List<int> bytes;
      try {
        bytes = (await api.getCrudo('canales/secciones/')).bytes ?? const [];
        nuevas = _leerSecciones(bytes);
      } catch (_) {
        final habia = _definiciones.isNotEmpty;
        _definiciones = [];
        _partes.removeWhere((clave, _) => clave.startsWith('s:'));
        return habia;
      }
      String forma(List<SeccionNueva> secciones) => jsonEncode([
        for (final s in secciones) [s.clave, s.nombre, s.forma, s.icono],
      ]);
      var cambio = forma(nuevas) != forma(_definiciones);
      _definiciones = nuevas;
      await _copia.guardar('secciones', bytes, '');
      // Las que ya no están
      final siguen = {for (final s in nuevas) 's:${s.clave}'};
      for (final clave in _partes.keys.where((c) => c.startsWith('s:') && !siguen.contains(c)).toList()) {
        _partes.remove(clave);
        unawaited(_copia.borrar(clave));
        cambio = true;
      }
      final cambiadas = await Future.wait([
        for (final seccion in nuevas)
          // Si una no llega, queda la que había (o vacía: no se muestra) y el resto del catálogo sigue
          traer('s:${seccion.clave}', seccion.clave, seccion.forma).catchError((_) => false),
      ]);
      return cambio || cambiadas.contains(true);
    }

    // Las series SIN capítulos (desde la 1.2.38). Un servidor viejo no las tiene (404, o no manda
    // "series"): entonces todos los capítulos, como antes
    Future<bool> traerSeries() async {
      if (!_partes.containsKey('serie')) {
        final anterior = _partes['series'];
        try {
          final llegado = await api.getCrudo(
            'canales/series/',
            parametros: {'formatos': formatos},
            huella: anterior?.huella ?? '',
          );
          final bytes = llegado.bytes;
          if (bytes == null && anterior != null) return false;
          if (bytes != null) {
            _partes['series'] = (huella: llegado.huella, parte: await leerSeriesAparte(bytes));
            // Cambió la lista: los capítulos ya traídos pueden haber cambiado también (se vuelven a pedir)
            _capitulosTraidos.clear();
            _idsPedidos.clear();
            await _copia.guardar('series', bytes, llegado.huella);
            return true;
          }
        } on ApiError catch (error) {
          if (error.status != 404) rethrow;
        } on FormatException {
          // No es la lista nueva: un servidor viejo
        }
      }
      _partes.remove('series');
      return traer('serie', 'serie', 'serie');
    }

    final cambios = await Future.wait([
      traer('vivo', 'vivo', 'vivo'),
      traer('pelicula', 'pelicula', 'pelicula'),
      traerSeries(),
      traerSeccionesNuevas(),
    ]);
    return cambios.contains(true);
  }

  /// Los capítulos de [serie] (si es resumida, se piden al servidor). Devuelve la serie ya con sus
  /// capítulos (la que queda en [series]); si no se pudo, tira el error (sin internet...).
  Future<Serie> abrirSerie(Serie serie) async {
    final clave = serie.nombre.toLowerCase();
    if (serie.cargada) return seriePorNombre(serie.nombre) ?? serie;
    if (!_capitulosTraidos.containsKey(clave)) await _traerCapitulos(nombres: [serie.nombre]);
    return seriePorNombre(serie.nombre) ?? _llena(serie);
  }

  /// Trae las series de estos capítulos (los de "Continuar viendo" y "Seguir acá"), si todavía no se
  /// sabe de cuál son: así esas filas pueden mostrarlos. Lo llaman las estructuras del celular y la TV.
  Future<void> asegurarCapitulos(Iterable<int> ids) async {
    final faltan = {
      for (final id in ids)
        if (!_idsPedidos.contains(id) && canalPorId(id) == null) id,
    };
    if (faltan.isEmpty || !_partes.containsKey('series')) return;
    _idsPedidos.addAll(faltan);
    try {
      await _traerCapitulos(ids: faltan);
    } catch (_) {
      _idsPedidos.removeAll(faltan); // se reintenta la próxima vez
    }
  }

  Future<void> _traerCapitulos({List<String> nombres = const [], Set<int> ids = const {}}) {
    final clave = [...nombres.map((n) => n.toLowerCase()), ...ids.map((i) => '#$i')].join('|');
    return _trayendo[clave] ??= () async {
      try {
        final consulta = [
          'formatos=${Uri.encodeQueryComponent(FuenteCanal.formatosQueReproduce.join(','))}',
          for (final nombre in nombres) 'nombre=${Uri.encodeQueryComponent(nombre)}',
          if (ids.isNotEmpty) 'ids=${ids.join(',')}',
        ].join('&');
        final datos = await api.get('canales/series/capitulos/?$consulta') as Map<String, dynamic>;
        final canales = [
          for (final c in datos['categorias'] as List? ?? const [])
            ...CategoriaCanales(c as Map<String, dynamic>, contenido: 'serie').canales,
        ];
        // Cada capítulo a su serie (con la misma regla que agruparSeries)
        for (final nombre in nombres) {
          _capitulosTraidos.putIfAbsent(nombre.toLowerCase(), () => []);
        }
        final porSerie = <String, List<Canal>>{};
        for (final serie in agruparSeries(canales)) {
          porSerie[serie.nombre.toLowerCase()] = [for (final e in serie.episodios) e.canal];
        }
        _capitulosTraidos.addAll(porSerie);
        final yaEstaban = {for (final c in _recibidos) c.id};
        _recibidos = [..._recibidos, ...canales.where((c) => !yaEstaban.contains(c.id))];
        // Las que llegaron, ya con sus capítulos, en el mismo lugar de la lista
        final llegaron = {...porSerie.keys, ...nombres.map((n) => n.toLowerCase())};
        series = [
          for (final serie in series)
            if (llegaron.contains(serie.nombre.toLowerCase())) _llena(serie) else serie,
        ];
        notifyListeners();
      } finally {
        _trayendo.remove(clave);
      }
    }();
  }

  /// Una serie resumida con los capítulos que ya se trajeron, solo los que este aparato ve.
  Serie _llena(Serie serie) {
    final capitulos = _capitulosTraidos[serie.nombre.toLowerCase()];
    if (capitulos == null) return serie;
    final armada = agruparSeries(capitulos.where(_seVe).toList()).firstOrNull;
    final llena =
        Serie(nombre: serie.nombre, categoria: serie.categoria, portada: serie.portada, resumen: serie.resumen)
          ..cargada = true
          ..numerada = armada?.numerada ?? false;
    armada?.temporadas.forEach((numero, lista) => llena.temporadas[numero] = lista);
    return llena;
  }

  /// Arma lo que se muestra a partir de lo que mandó el servidor ([_partes]),
  /// sacando lo que este aparato no ve. No toca [_partes]: arma listas nuevas.
  void _aplicar() {
    List<CategoriaCanales> filtrar(List<CategoriaCanales> categorias) => [
      for (final categoria in categorias)
        if (categoria.canales.where(_seVe).toList() case final quedan when quedan.isNotEmpty)
          CategoriaCanales.con(categoria.nombre, quedan),
    ];

    final vivo = _partes['vivo']?.parte;
    final pelicula = _partes['pelicula']?.parte;
    final serie = _partes['serie']?.parte;
    final resumidas = _partes['series']?.parte;
    final secciones = [for (final s in _definiciones) (s, _partes['s:${s.clave}']?.parte)];
    _recibidos = [
      ...?vivo?.canales,
      ...?pelicula?.canales,
      ...?serie?.canales,
      for (final (_, parte) in secciones) ...?parte?.canales,
    ];
    categoriasEnVivo = filtrar(vivo?.categorias ?? const []);
    peliculas = [for (final c in pelicula?.categorias ?? const <CategoriaCanales>[]) ...c.canales.where(_seVe)];
    series = resumidas != null
        ? [
            for (final s in resumidas.series)
              if (s.aparatoLaMuestra)
                if (_llena(s) case final llena when llena.completa) llena,
          ]
        : [
            for (final s in serie?.series ?? const <Serie>[])
              if (s.soloCon(_seVe) case final quedan when quedan.completa) quedan,
          ];
    // Los capítulos ya traídos también cuentan como recibidos ("Lo que no se ve en esta TV")
    _recibidos = [..._recibidos, for (final capitulos in _capitulosTraidos.values) ...capitulos];
    seccionesNuevas = [
      for (final (definicion, parte) in secciones)
        if (filtrar(parte?.categorias ?? const []) case final categorias when categorias.isNotEmpty)
          SeccionNueva(
            clave: definicion.clave,
            nombre: definicion.nombre,
            forma: definicion.forma,
            icono: definicion.icono,
          )..categorias = categorias,
    ];
    _numerar();
  }

  Canal? canalPorId(int id) {
    if (_porId == null) _indices();
    return _porId![id];
  }

  Serie? serieDe(Canal capitulo) {
    if (_serieDelCapitulo == null) _indices();
    return _serieDelCapitulo![capitulo.id];
  }

  SeccionNueva? seccionNueva(String clave) => seccionesNuevas.where((s) => s.clave == clave).firstOrNull;

  Serie? seriePorNombre(String nombre) {
    if (_seriePorNombre == null) _indices();
    return _seriePorNombre![nombre];
  }

  /// Al cerrar sesión: que no quede el catálogo guardado en el aparato.
  static Future<void> olvidarLoGuardado() => CopiaCatalogo.borrarTodo();
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
