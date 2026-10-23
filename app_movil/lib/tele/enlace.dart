/// "Ver en la tele", del lado del CELULAR: sabe si hay una tele conectada
/// como pantalla y le va diciendo qué mostrar.
///
/// La tele es otro motor de Flutter en el mismo celular (ver
/// android/.../PantallaTele.kt y en_la_tele.dart): no comparte memoria con
/// este, así que no se le pasan pantallas sino una descripción de lo que el
/// celular está mostrando (el "estado"):
///
///   { seccion: 'peliculas',              <- la de la barra de abajo
///     nueva:   null,                     <- la clave de una sección del panel (Música, Radio...)
///     capas:   [ {clave: 'c3', tipo: 'detalle', canal: 812},
///                {clave: 'c4', tipo: 'pelicula', canal: 812, desde: 63000} ] }
///
/// Cada vez que algo cambia se manda el estado entero, y la tele se acomoda
/// (abre lo que falta y cierra lo que sobra). Las capas son lo que el celular
/// abrió encima (un detalle, un reproductor), en orden. Lo que se REPRODUCE
/// lo reproduce la tele: en el celular, en lugar del reproductor, queda el
/// control remoto (control_remoto.dart).
library;

import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

import '../api/modelos.dart';
import '../movil/datos.dart';
import '../movil/detalle.dart';
import '../movil/reproductor_vod.dart';
import '../movil/reproductor_youtube.dart';
import '../movil/secciones_nuevas.dart';
import 'control_remoto.dart';

/// Algo que el celular abrió encima y la tele también muestra.
class CapaTele {
  CapaTele(this.clave, this.datos, {this.enElCelular});

  /// Distinta para cada capa ('c1', 'c2'...): así la tele sabe si ya la tiene abierta.
  final String clave;
  final Map<String, Object?> datos;

  /// Lo que se ve en el celular en su lugar (el control remoto), o null si se ve lo mismo.
  final Widget? enElCelular;

  Map<String, Object?> aMapa() => {'clave': clave, ...datos};
}

class Tele extends ChangeNotifier {
  Tele._();

  static final instancia = Tele._();
  static const _canal = MethodChannel('kairos/tele');

  /// ¿Hay una tele conectada como pantalla?
  bool conectada = false;

  /// Cómo la llama Android (ej: "Kanji Smart TV"); puede venir vacío.
  String nombre = '';

  bool _escuchando = false;

  /// La sección de la barra de abajo del celular; null = no se está mostrando
  /// la app (está en el login): la tele muestra solo el logo.
  String? _seccion;
  final List<CapaTele> _pila = [];

  /// El canal en vivo que se está viendo en la tele (desde En Vivo o una radio).
  Canal? enVivo;
  String? _nuevaEnVivo;
  Object? _duenioEnVivo;
  int _numero = 0;

  /// Cambia cada vez que se pone un canal: la tele cambia de canal aunque sea el mismo (Reintentar).
  int _vezEnVivo = 0;

  final _cerradas = StreamController<String>.broadcast();

  /// Las capas que la tele cerró sola (terminó la película, Atrás en el reproductor).
  Stream<String> get cerradas => _cerradas.stream;

  /// Empieza a escuchar a Android (se llama una vez, al abrir la app).
  Future<void> escuchar() async {
    if (_escuchando) return;
    _escuchando = true;
    _canal.setMethodCallHandler(_recibir);
    try {
      final estado = await _canal.invokeMapMethod<String, Object?>('estado');
      _ponerConexion(estado?['conectada'] == true, '${estado?['nombre'] ?? ''}');
    } on MissingPluginException {
      // Fuera de Android (los tests) o en la TV: no hay tele que conectar
    } on PlatformException {
      // Idem
    }
  }

  Future<Object?> _recibir(MethodCall llamada) async {
    final datos = llamada.arguments is Map ? llamada.arguments as Map : const {};
    switch (llamada.method) {
      case 'conectada':
        _ponerConexion(true, '${datos['nombre'] ?? ''}');
      case 'desconectada':
        _ponerConexion(false, '');
      case 'cerrada':
        final clave = '${datos['clave']}';
        if (clave.startsWith('v')) {
          _sacarEnVivo();
          notifyListeners();
        }
        _cerradas.add(clave);
    }
    return null;
  }

  void _ponerConexion(bool si, String nombre) {
    final recien = si && !conectada;
    conectada = si;
    this.nombre = nombre;
    // El canal en vivo vuelve al celular (SeccionEnVivo). Lo abierto encima sigue
    // anotado mientras esté abierto en el celular: si la tele vuelve, lo muestra
    if (!si) _sacarEnVivo();
    if (recien) _mandar(); // que arranque mostrando lo mismo que el celular
    notifyListeners();
  }

  /// Abre los ajustes de Android para elegir la tele (o desconectarla).
  /// false = este celular no tiene esa pantalla de ajustes.
  Future<bool> conectar() async {
    try {
      return await _canal.invokeMethod<bool>('conectar') ?? false;
    } on MissingPluginException {
      return false;
    } on PlatformException {
      return false;
    }
  }

  /// ¿Está dado el permiso para que la tele muestre solo la app, siempre? ("Mostrar sobre otras apps", PantallaTele.kt)
  Future<bool> puedeQuedarFija() async {
    try {
      return await _canal.invokeMethod<bool>('puedeQuedarFija') ?? false;
    } on MissingPluginException {
      return false;
    } on PlatformException {
      return false;
    }
  }

  /// Abre la pantalla de Android para dar ese permiso (vuelve sola a la app con "Atrás").
  Future<void> pedirQuedarFija() async {
    try {
      await _canal.invokeMethod<bool>('pedirQuedarFija');
    } on MissingPluginException {
      // Fuera de Android
    } on PlatformException {
      // Idem
    }
  }

  /// Abre la pantalla de Kairos TV en los Ajustes de Android: ahí, en el menú ⋮, "Permitir configuración
  /// restringida", si Android no deja dar el permiso de arriba. false = este celular no la abre.
  Future<bool> abrirDatosDeLaApp() async {
    try {
      return await _canal.invokeMethod<bool>('abrirDatosDeLaApp') ?? false;
    } on MissingPluginException {
      return false;
    } on PlatformException {
      return false;
    }
  }

  /// Corta la conexión con la tele. Si el celular no la deja cortar desde una
  /// app (sigue conectada a los 3 segundos), abre la lista de Android para cortarla ahí.
  Future<void> desconectar() async {
    if (!conectada) return;
    try {
      await _canal.invokeMethod<Object?>('desconectar');
    } on MissingPluginException {
      return;
    } on PlatformException {
      // Se prueba con la lista de Android
    }
    await Future<void>.delayed(const Duration(seconds: 3));
    if (conectada) await conectar();
  }

  /// Un botón del control remoto ('ok', 'pausa', 'izquierda', 'canalMas'...: ver PantallaTele.kt).
  void tecla(String tecla) => _invocar('tecla', {'tecla': tecla});

  /// Como el botón Atrás del control de la tele.
  void atras() => _invocar('atras');

  // ── Lo que muestra el celular ──

  /// La sección de la barra de abajo (Seccion.name); null = el celular dejó de mostrar la app.
  void seccion(String? seccion) {
    if (seccion == _seccion) return;
    _seccion = seccion;
    // Fuera de En Vivo el canal deja de verse (como en el celular): sin
    // esperar a que En Vivo lo saque, así la tele no lo abre encima de la sección nueva
    if (seccion != 'enVivo' && _nuevaEnVivo == null) _sacarEnVivo();
    _mandar();
  }

  /// Si [pantalla] se tiene que ver también en la tele, la capa que la
  /// representa (y la anota). null = no hay tele, o eso no se muestra allá.
  /// Lo llama abrirPantalla (movil/componentes.dart), por donde se abre todo.
  CapaTele? abrir(Widget pantalla) {
    if (!conectada) return null;
    final capa = switch (pantalla) {
      PantallaDetalle(pelicula: final Canal pelicula) => _capa({'tipo': 'detalle', 'canal': pelicula.id}),
      PantallaDetalle(serie: final Serie serie) => _capa({'tipo': 'detalleSerie', 'serie': serie.nombre}),
      PantallaSeccionNueva(:final clave) => _capa({'tipo': 'seccion', 'nueva': clave}),
      PantallaReproductorVod(:final canal, :final serie, :final episodio, :final desde) ||
      PantallaYoutube(
        :final canal,
        :final serie,
        :final episodio,
        :final desde,
      ) => _capaReproductor(canal, serie, episodio, desde),
      _ => null,
    };
    if (capa == null) return null;
    _pila.add(capa);
    _mandar();
    return capa;
  }

  /// El celular cerró [capa] (volvió atrás): la tele también.
  void cerrar(CapaTele capa) {
    if (_pila.remove(capa)) _mandar();
  }

  CapaTele _capa(Map<String, Object?> datos, {Widget? enElCelular}) =>
      CapaTele('c${++_numero}', datos, enElCelular: enElCelular);

  CapaTele _capaReproductor(Canal canal, Serie? serie, Episodio? episodio, Duration? desde) {
    final clave = 'c${++_numero}';
    return CapaTele(
      clave,
      {
        'tipo': serie != null && episodio != null ? 'episodio' : 'pelicula',
        'canal': canal.id,
        'serie': ?serie?.nombre,
        'desde': ?desde?.inMilliseconds,
      },
      enElCelular: ControlRemotoTele(
        clave: clave,
        titulo: serie?.nombre ?? canal.nombre,
        detalle: episodio == null
            ? ''
            : 'T${episodio.temporada}:E${episodio.numero}${episodio.titulo.isEmpty ? '' : ' · ${episodio.titulo}'}',
      ),
    );
  }

  /// Poner [canal] en vivo en la tele. [duenio]: quién lo pidió (la pantalla
  /// de En Vivo o la de una radio), para que solo ese lo pueda sacar.
  void verEnVivo(Canal canal, {required Object duenio, String? nueva}) {
    enVivo = canal;
    _nuevaEnVivo = nueva;
    _duenioEnVivo = duenio;
    _vezEnVivo++;
    _mandar();
    notifyListeners();
  }

  /// Lo que se ve en vivo en la tele, si lo puso [duenio].
  Canal? enVivoDe(Object duenio) => identical(_duenioEnVivo, duenio) ? enVivo : null;

  /// [duenio] dejó de mostrarse (se fue de En Vivo): la tele deja de reproducir ese canal.
  void dejarEnVivo(Object duenio) {
    if (!identical(_duenioEnVivo, duenio)) return;
    _sacarEnVivo();
    _mandar();
    notifyListeners();
  }

  void _sacarEnVivo() {
    enVivo = null;
    _nuevaEnVivo = null;
    _duenioEnVivo = null;
  }

  // ── Mandarle el estado a la tele ──

  /// Lo que la tele tiene que mostrar (ver el comienzo del archivo).
  Map<String, Object?> get estado {
    final capas = [for (final capa in _pila) capa.aMapa()];
    final canal = enVivo;
    if (canal != null) {
      final vivo = {'clave': 'v$_vezEnVivo-${canal.id}', 'tipo': 'vivo', 'canal': canal.id, 'nueva': _nuevaEnVivo};
      // Va encima de la sección donde se eligió (una radio) o, si es En Vivo, primero
      final donde = capas.indexWhere((c) => c['tipo'] == 'seccion' && c['nueva'] == _nuevaEnVivo);
      capas.insert(_nuevaEnVivo == null || donde < 0 ? 0 : donde + 1, vivo);
    }
    return {'seccion': _seccion, 'capas': capas};
  }

  void _mandar() {
    if (conectada) _invocar('orden', estado);
  }

  void _invocar(String metodo, [Object? argumentos]) {
    if (!conectada) return;
    _canal.invokeMethod<Object?>(metodo, argumentos).catchError((_) => null);
  }
}
