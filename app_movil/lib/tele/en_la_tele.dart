/// "Ver en la tele", lo que corre EN LA TELE: la app con el diseño de TV
/// (lib/tv/) que sigue lo que se hace en el celular.
///
/// Es un segundo motor de Flutter que Android dibuja en la tele
/// (android/.../PantallaTele.kt) y arranca en `pantallaTele()` de main.dart.
/// No comparte memoria con el del celular:
///   - Entra con la MISMA sesión (el token que guardó el celular): para el
///     servidor es el mismo aparato, no ocupa otra pantalla del cliente.
///   - Pide su propio catálogo y lleva su propia copia de favoritos y "Continuar
///     viendo" (la de la cuenta, en el servidor: lo que se mira acá aparece en el celular).
///   - Del celular recibe el "estado" (enlace.dart) y se acomoda: la sección,
///     y encima lo que el celular abrió (detalle, reproductor) [EspejoTv].
/// El video lo decodifica el celular (es el mismo aparato) y Android lo manda a la tele.
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import '../aparato.dart';
import '../config.dart';
import '../marca.dart';
import '../movil/datos.dart';
import '../movil/estilo.dart';
import '../movil/reproductor_youtube.dart';
import '../sesion.dart';
import '../tema.dart';
import '../tv/detalle.dart';
import '../tv/escala.dart';
import '../tv/estructura.dart';
import '../tv/reproductor.dart';

/// Arranca la app de la tele (lo llama `pantallaTele()` de main.dart).
Future<void> iniciarTele() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Aparato.cargar();
  final sesion = Sesion();
  runApp(SesionScope(sesion: sesion, child: const AppTele()));
  await sesion.iniciar();
  await EspejoTv.instancia.escuchar(sesion);
}

class AppTele extends StatelessWidget {
  const AppTele({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: nombreSistema,
      debugShowCheckedModeBanner: false,
      theme: temaDeLaApp(),
      locale: const Locale('es', 'AR'),
      supportedLocales: const [Locale('es', 'AR'), Locale('es')],
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
      // Como en una TV: todo en 1920×1080 y escalado a la pantalla
      builder: (context, hijo) => EscalaTv(child: hijo!),
      home: const _RaizTele(),
    );
  }
}

/// La app de TV si hay sesión y el celular está mostrando la app; si no, el logo.
class _RaizTele extends StatelessWidget {
  const _RaizTele();

  @override
  Widget build(BuildContext context) {
    final sesion = SesionScope.of(context);
    return ValueListenableBuilder<bool>(
      valueListenable: EspejoTv.instancia.activa,
      builder: (context, activa, _) {
        if (sesion.estado == EstadoSesion.conSesion && activa) return const PantallaTv(espejo: true);
        return const PantallaEsperandoTele();
      },
    );
  }
}

/// Lo que muestra la tele mientras el celular no está en la app (login, cargando).
class PantallaEsperandoTele extends StatelessWidget {
  const PantallaEsperandoTele({super.key});

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      backgroundColor: Tono.fondo,
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            LogoKairos(tamanio: 72),
            SizedBox(height: 40),
            Text('Elegí qué ver desde el celular', style: LetraTv.pantalla),
            SizedBox(height: 12),
            Text('Todo lo que abras ahí se ve acá.', style: LetraTv.cuerpo),
          ],
        ),
      ),
    );
  }
}

/// Lo que la tele abrió encima de la sección porque el celular lo abrió.
typedef _Abierta = ({String clave, Route<void> ruta});

/// La tele copiando al celular: recibe su estado (enlace.dart) y abre o
/// cierra lo que haga falta. Se engancha a la PantallaTv (con `espejo: true`),
/// que le presta su contexto y su cambio de sección.
class EspejoTv {
  EspejoTv._();

  static final instancia = EspejoTv._();
  static const _canal = MethodChannel('kairos/tele');

  /// false = el celular no está mostrando la app (login): la tele muestra el logo.
  final activa = ValueNotifier<bool>(false);

  Sesion? _sesion;
  Map<String, Object?>? _ultimo;

  // Lo que presta PantallaTv
  BuildContext Function()? _contexto;
  void Function(SeccionTv seccion, {String? nueva})? _irA;
  VoidCallback? _despertar;

  String? _seccion;
  final List<_Abierta> _abiertas = [];

  Future<void> escuchar(Sesion sesion) async {
    _sesion = sesion;
    _canal.setMethodCallHandler((llamada) async {
      if (llamada.method == 'orden' && llamada.arguments is Map) recibir(llamada.arguments as Map);
      return null;
    });
    // Lo que el celular mandó antes de que esta app arrancara
    try {
      final ultima = await _canal.invokeMethod<Object?>('pedirOrden');
      if (ultima is Map) recibir(ultima);
    } on PlatformException {
      // Sin orden todavía: queda el logo
    } on MissingPluginException {
      // Idem
    }
  }

  /// Lo que manda el celular (ver enlace.dart).
  void recibir(Map estado) {
    _ultimo = {for (final e in estado.entries) '${e.key}': e.value};
    activa.value = _ultimo!['seccion'] != null;
    // El celular acaba de entrar (la tele arrancó en el login): se lee la sesión que guardó
    final sesion = _sesion;
    if (activa.value &&
        sesion != null &&
        (sesion.estado == EstadoSesion.sinSesion || sesion.estado == EstadoSesion.sinConexion)) {
      sesion.iniciar();
    }
    _aplicar();
  }

  /// PantallaTv (en modo espejo) se engancha al abrirse.
  void conectar({
    required BuildContext Function() contexto,
    required void Function(SeccionTv seccion, {String? nueva}) irA,
    required VoidCallback despertar,
  }) {
    _contexto = contexto;
    _irA = irA;
    _despertar = despertar;
    _seccion = null;
    _abiertas.clear();
  }

  void desconectar() {
    _contexto = null;
    _irA = null;
    _despertar = null;
    _abiertas.clear();
  }

  /// Ya llegó el catálogo: se muestra lo que el celular había pedido.
  void catalogoListo() => _aplicar();

  void _aplicar() {
    final estado = _ultimo;
    final contexto = _contexto?.call();
    final irA = _irA;
    if (estado == null || contexto == null || !contexto.mounted || irA == null) return;
    final datos = DatosScope.of(contexto);
    if (!datos.catalogo.cargado) return; // catalogoListo() lo vuelve a intentar
    _despertar?.call();

    final capas = [
      for (final c in estado['capas'] as List? ?? const [])
        if (c is Map) {for (final e in c.entries) '${e.key}': e.value},
    ];
    // Una sección del panel (Música, Radio...) que el celular abrió encima: en la TV es una sección
    var seccion = '${estado['seccion'] ?? 'inicio'}';
    String? nueva;
    for (final capa in capas.where((c) => c['tipo'] == 'seccion')) {
      seccion = 'nueva';
      nueva = '${capa['nueva']}';
    }
    final rutas = capas.where((c) => c['tipo'] != 'seccion').toList();

    final navegador = Navigator.of(contexto);
    final claveSeccion = seccion == 'nueva' ? 'nueva:$nueva' : seccion;
    if (claveSeccion != _seccion) {
      _cerrarDesde(0, navegador);
      _seccion = claveSeccion;
      irA(_seccionTv(seccion), nueva: nueva);
    }
    // Lo que ya está abierto y sigue igual queda; desde el primero distinto, se cierra y se abre lo nuevo
    var iguales = 0;
    while (iguales < _abiertas.length &&
        iguales < rutas.length &&
        _abiertas[iguales].clave == '${rutas[iguales]['clave']}') {
      iguales++;
    }
    _cerrarDesde(iguales, navegador);
    for (final capa in rutas.skip(iguales)) {
      final pantalla = _pantallaDe(capa, datos.catalogo);
      if (pantalla == null) break; // no está en el catálogo de acá: lo de encima tampoco
      _abrir('${capa['clave']}', pantalla, navegador, datos);
    }
  }

  static SeccionTv _seccionTv(String seccion) => switch (seccion) {
    'enVivo' => SeccionTv.enVivo,
    'series' => SeccionTv.series,
    'peliculas' => SeccionTv.peliculas,
    'favoritos' => SeccionTv.favoritos,
    'miEspacio' => SeccionTv.cuenta,
    'nueva' => SeccionTv.nueva,
    _ => SeccionTv.inicio,
  };

  /// Cierra lo abierto desde la posición [desde] (0 = todo), y también lo que
  /// la tele abrió sola encima (el modo reposo, un cuadro de Ajustes).
  void _cerrarDesde(int desde, NavigatorState navegador) {
    final queda = desde == 0 ? null : _abiertas[desde - 1].ruta;
    _abiertas.removeRange(desde, _abiertas.length);
    navegador.popUntil((ruta) => ruta.isFirst || ruta == queda);
  }

  Widget? _pantallaDe(Map<String, Object?> capa, Catalogo catalogo) {
    final canal = capa['canal'] is int ? catalogo.canalPorId(capa['canal'] as int) : null;
    final serie = capa['serie'] is String ? catalogo.seriePorNombre(capa['serie'] as String) : null;
    final desde = capa['desde'] is int ? Duration(milliseconds: capa['desde'] as int) : null;
    switch (capa['tipo']) {
      case 'detalle':
        return canal == null ? null : DetalleTv.pelicula(canal);
      case 'detalleSerie':
        return serie == null ? null : DetalleTv.serie(serie);
      case 'vivo':
        if (canal == null) return null;
        final nueva = capa['nueva'] is String ? catalogo.seccionNueva(capa['nueva'] as String) : null;
        return ReproductorVivoTv(canal: canal, lista: nueva?.canales ?? catalogo.canales);
      case 'pelicula':
        if (canal == null) return null;
        return fuenteDeYoutube(canal) != null
            ? ReproductorYoutubeTv(canal: canal, desde: desde)
            : ReproductorVodTv(canal: canal, desde: desde);
      case 'episodio':
        final episodio = serie?.episodios.where((e) => e.canal.id == capa['canal']).firstOrNull;
        if (serie == null || episodio == null) return null;
        return fuenteDeYoutube(episodio.canal) != null
            ? ReproductorYoutubeTv(canal: episodio.canal, serie: serie, episodio: episodio, desde: desde)
            : ReproductorVodTv(canal: episodio.canal, serie: serie, episodio: episodio, desde: desde);
    }
    return null;
  }

  /// Como abrirTv (tv/piezas.dart), pero guardando la ruta para poder cerrarla después.
  void _abrir(String clave, Widget pantalla, NavigatorState navegador, DatosScope datos) {
    final ruta = PageRouteBuilder<void>(
      transitionDuration: const Duration(milliseconds: 180),
      reverseTransitionDuration: const Duration(milliseconds: 140),
      pageBuilder: (_, _, _) => DatosScope(
        catalogo: datos.catalogo,
        biblioteca: datos.biblioteca,
        child: Theme(data: temaMovil(), child: pantalla),
      ),
      transitionsBuilder: (_, animacion, _, hijo) => FadeTransition(opacity: animacion, child: hijo),
    );
    _abiertas.add((clave: clave, ruta: ruta));
    navegador.push(ruta).whenComplete(() {
      // Si sigue anotada, la cerró la tele sola (terminó, Atrás): se le avisa al celular
      final donde = _abiertas.indexWhere((a) => a.ruta == ruta);
      if (donde < 0) return;
      _abiertas.removeRange(donde, _abiertas.length);
      _canal.invokeMethod<Object?>('cerrada', {'clave': clave}).catchError((_) => null);
    });
  }
}
