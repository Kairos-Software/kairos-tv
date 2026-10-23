/// La app en la TV (diseno_kairos_tv/DESIGN.md -> "Menú lateral TV"): el menú
/// de la izquierda y las ocho secciones (Inicio, En vivo, Guía, Películas,
/// Series, Buscar, Favoritos y Mi cuenta), más las que se crean en el panel
/// (Música, Radio...), que van en el menú después de Series.
///
/// El menú mide 88 px con solo íconos; al entrar en él (Izquierda desde el
/// borde izquierdo del contenido) se abre a 292 px con los nombres y el foco
/// cae en la sección actual. OK abre la sección; Derecha o "Atrás" vuelven al
/// contenido. "Atrás" en una sección vuelve a Inicio, y en Inicio pregunta si
/// salir.
///
/// El contenido y el menú son dos áreas de foco separadas (FocusScope): Flutter
/// no deja salir de un área con las flechas, así que el paso de una a otra se
/// hace a mano (_teclaEnContenido y _teclaEnMenu).
///
/// Acá se crean el catálogo y la biblioteca, igual que en el celular
/// (movil/estructura.dart): se pide el catálogo al abrir, al volver a la app
/// y cada 15 minutos.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/modelos.dart';
import '../marca.dart';
import '../movil/recordatorios.dart';
import '../movil/datos.dart';
import '../movil/estilo.dart';
import '../sesion.dart';
import '../tele/en_la_tele.dart';
import '../utiles.dart';
import 'mi_agenda.dart';
import 'buscar.dart';
import 'cuenta.dart';
import 'en_vivo.dart';
import 'favoritos.dart';
import 'foco.dart';
import 'grilla.dart';
import 'guia.dart';
import 'inicio.dart';
import '../movil/secciones_nuevas.dart';
import 'piezas.dart';
import 'reposo.dart';
import 'reproductor.dart';

/// `nueva`: una de las secciones creadas en el panel (cuál, en _PantallaTvState._nueva).
enum SeccionTv { inicio, enVivo, guia, peliculas, series, buscar, favoritos, cuenta, nueva }

/// Para cambiar de sección desde cualquier pantalla (ej: "Abrir guía" en Inicio).
class NavegacionTv extends InheritedWidget {
  const NavegacionTv({super.key, required this.irA, required super.child});

  final void Function(SeccionTv seccion) irA;

  static NavegacionTv of(BuildContext context) => context.dependOnInheritedWidgetOfExactType<NavegacionTv>()!;

  @override
  bool updateShouldNotify(NavegacionTv oldWidget) => false;
}

class PantallaTv extends StatefulWidget {
  const PantallaTv({
    super.key,
    this.catalogo,
    this.biblioteca,
    this.seccionInicial = SeccionTv.inicio,
    this.esperaReposo = const Duration(minutes: 1),
    this.espejo = false,
  });

  /// Solo para las pruebas: un catálogo y una biblioteca ya armados.
  final Catalogo? catalogo;
  final Biblioteca? biblioteca;
  final SeccionTv seccionInicial;

  /// Cuánto tiempo sin tocar el control (y sin nada reproduciéndose) hasta
  /// que aparece el modo reposo (tv/reposo.dart): 1 minuto. Menos que el
  /// protector de pantalla de Android TV (5 minutos o más), para que se vea el nuestro.
  final Duration esperaReposo;

  /// En la tele que se maneja desde el celular ("Ver en la tele", lib/tele/):
  /// lo que se ve lo decide el celular (tele/en_la_tele.dart -> EspejoTv).
  final bool espejo;

  @override
  State<PantallaTv> createState() => _PantallaTvState();
}

class _PantallaTvState extends State<PantallaTv> {
  static const _cadaCuanto = Duration(minutes: 15);

  late final Catalogo _catalogo = widget.catalogo ?? Catalogo(SesionScope.leer(context).api);
  // En la tele del celular, con su propia copia en el aparato (la del celular la escribe el otro motor)
  late final Biblioteca _biblioteca =
      widget.biblioteca ??
      Biblioteca(
        api: SesionScope.leer(context).api,
        cuenta: '${SesionScope.leer(context).cuenta}${widget.espejo ? '~tele' : ''}',
      );
  late SeccionTv _seccion = widget.seccionInicial;

  /// Dónde se estaba antes de ir a Buscar: desde Series se buscan series.
  SeccionTv _antesDeBuscar = SeccionTv.inicio;
  final _contenido = FocusScopeNode(debugLabel: 'contenido');
  final _menu = FocusScopeNode(debugLabel: 'menú');
  final _opcionesDelMenu = {for (final s in SeccionTv.values) s: FocusNode(debugLabel: 'menú: ${s.name}')};

  /// La sección nueva abierta (su clave), cuando _seccion es SeccionTv.nueva.
  String? _nueva;
  final _opcionesNuevas = <String, FocusNode>{};

  FocusNode _nodoNueva(String clave) => _opcionesNuevas.putIfAbsent(clave, () => FocusNode(debugLabel: 'menú: $clave'));
  bool _menuAbierto = false;
  AppLifecycleListener? _ciclo;
  Timer? _refresco;
  Timer? _reposo;
  bool _enReposo = false;

  /// Cada tanto se fija si empieza algo anotado en "Mi agenda" (tv/mi_agenda.dart).
  Timer? _vigiaAgenda;
  final Set<String> _yaAvisados = {};

  @override
  void initState() {
    super.initState();
    _menu.addListener(_alCambiarFocoDelMenu);
    HardwareKeyboard.instance.addHandler(_alTocarElControl);
    HardwareKeyboard.instance.addHandler(_teclaSinFoco);
    _esperarReposo();
    FocusManager.instance.addListener(_vigilarFoco);
    if (widget.espejo) {
      EspejoTv.instancia.conectar(contexto: () => _contexto, irA: _irA, despertar: _esperarReposo);
    }
    if (widget.biblioteca == null) _biblioteca.cargar();
    _catalogo.addListener(_alCargarPorPrimeraVez);
    _catalogo.addListener(_asegurarCapitulos);
    _biblioteca.addListener(_asegurarCapitulos);
    // En la tele del celular avisa el celular (con el aviso de Android)
    if (!widget.espejo) _vigiaAgenda = Timer.periodic(const Duration(seconds: 30), (_) => _mirarAgenda());
    if (widget.catalogo != null) return;
    WidgetsBinding.instance.addPostFrameCallback((_) => _catalogo.cargar());
    _ciclo = AppLifecycleListener(onResume: _alVolver, onHide: _biblioteca.sincronizar);
    _refresco = Timer.periodic(_cadaCuanto, (_) => _alVolver());
  }

  /// Al volver a la app y cada tanto: el catálogo y lo de la cuenta (lo que cambió en otros aparatos).
  void _alVolver() {
    _catalogo.cargar();
    _biblioteca.sincronizar();
  }

  @override
  void dispose() {
    if (widget.espejo) EspejoTv.instancia.desconectar();
    _catalogo.removeListener(_alCargarPorPrimeraVez);
    _catalogo.removeListener(_asegurarCapitulos);
    _biblioteca.removeListener(_asegurarCapitulos);
    _ciclo?.dispose();
    _refresco?.cancel();
    _reposo?.cancel();
    _vigiaAgenda?.cancel();
    _contenido.dispose();
    HardwareKeyboard.instance.removeHandler(_alTocarElControl);
    HardwareKeyboard.instance.removeHandler(_teclaSinFoco);
    FocusManager.instance.removeListener(_vigilarFoco);
    _menu
      ..removeListener(_alCambiarFocoDelMenu)
      ..dispose();
    for (final nodo in [..._opcionesDelMenu.values, ..._opcionesNuevas.values]) {
      nodo.dispose();
    }
    if (widget.catalogo == null) _catalogo.dispose();
    if (widget.biblioteca == null) _biblioteca.dispose();
    super.dispose();
  }

  /// "Continuar viendo" y "Seguir acá" pueden tener capítulos de series que todavía no se abrieron
  /// (desde la 1.2.38 los capítulos llegan a pedido): el catálogo trae esas series (una vez cada una).
  void _asegurarCapitulos() {
    if (!_catalogo.cargado) return;
    unawaited(
      _catalogo.asegurarCapitulos([
        for (final progreso in _biblioteca.continuarViendo) progreso.id,
        if (_biblioteca.seguirDeOtroAparato case final seguir?) seguir.id,
      ]),
    );
  }

  /// "Volver al último canal al abrir" (Mi cuenta): cuenta 3 segundos (se puede cancelar) y lo pone.
  void _alCargarPorPrimeraVez() {
    if (!_catalogo.cargado) return;
    _catalogo.removeListener(_alCargarPorPrimeraVez);
    // En la tele del celular: lo que el celular pidió mientras cargaba (y no "volver al último canal")
    if (widget.espejo) {
      WidgetsBinding.instance.addPostFrameCallback((_) => EspejoTv.instancia.catalogoListo());
      return;
    }
    final ultimo = _biblioteca.ultimoCanal == null ? null : _catalogo.canalPorId(_biblioteca.ultimoCanal!);
    if (!_biblioteca.volverAlUltimo || ultimo == null) return;
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted) return;
      final seguir = await showDialog<bool>(
        context: context,
        builder: (_) => CuentaRegresivaTv(canal: ultimo),
      );
      if (seguir == true && mounted) verCanalTv(_contexto, ultimo);
    });
  }

  /// Empezó algo anotado en "Mi agenda": "Empieza ..." con "Verlo" (encima de lo que se esté viendo).
  Future<void> _mirarAgenda() async {
    if (!mounted || !_catalogo.cargado) return;
    for (final (recordatorio, vez) in Recordatorios.empezandoAhora(_yaAvisados)) {
      _yaAvisados.add(Recordatorios.claveDeLaVez(recordatorio, vez));
      final canal = _catalogo.canalPorId(recordatorio.canal);
      if (canal != null) return _avisarQueEmpieza(recordatorio, canal, vez);
    }
  }

  Future<void> _avisarQueEmpieza(Recordatorio recordatorio, Canal canal, DateTime vez) async {
    final ver = await showDialog<bool>(
      context: _contexto,
      builder: (_) => CartelEmpiezaTv(recordatorio: recordatorio, canal: canal, vez: vez),
    );
    if (ver == true && mounted) {
      // Si se estaba viendo otra cosa, se cierra antes de poner el canal
      Navigator.of(_contexto).popUntil((ruta) => ruta.isFirst);
      await verCanalTv(_contexto, canal);
    }
  }

  /// Un contexto debajo de DatosScope (para abrir pantallas con el catálogo).
  BuildContext get _contexto => _claveContenido.currentContext ?? context;
  final _claveContenido = GlobalKey();

  void _irA(SeccionTv seccion, {String? nueva}) {
    setState(() {
      if (seccion == SeccionTv.buscar && _seccion != SeccionTv.buscar) _antesDeBuscar = _seccion;
      _seccion = seccion;
      _nueva = seccion == SeccionTv.nueva ? nueva : null;
      _menuAbierto = false;
    });
    // El foco pasa al contenido de la sección nueva (a su "foco inicial")
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _enfocarContenido();
    });
  }

  // ── Modo reposo (tv/reposo.dart) ──

  /// Cualquier tecla reinicia la cuenta (no la consume: sigue su camino).
  bool _alTocarElControl(KeyEvent evento) {
    if (!_enReposo) _esperarReposo();
    return false;
  }

  void _esperarReposo() {
    _reposo?.cancel();
    _reposo = Timer(widget.esperaReposo, _entrarEnReposo);
  }

  /// Solo si esta pantalla está adelante: con el reproductor o un cartel
  /// encima, no (se vuelve a esperar). Sin títulos con imagen, muestra solo el logo.
  Future<void> _entrarEnReposo() async {
    if (!mounted || _enReposo) return;
    if (!(ModalRoute.of(context)?.isCurrent ?? false) || !_catalogo.cargado) return _esperarReposo();
    _enReposo = true;
    await abrirTv<void>(_contexto, PantallaReposoTv(vidriera: Vidriera.delCatalogo(_catalogo)));
    _enReposo = false;
    if (mounted) _esperarReposo();
  }

  void _alCambiarFocoDelMenu() {
    if (_menu.hasFocus != _menuAbierto) setState(() => _menuAbierto = _menu.hasFocus);
  }

  void _abrirMenu() =>
      (_seccion == SeccionTv.nueva && _nueva != null ? _nodoNueva(_nueva!) : _opcionesDelMenu[_seccion]!)
          .requestFocus();

  void _cerrarMenu() => _enfocarContenido();

  /// El foco al contenido: a lo último que estaba elegido o, si no hay nada
  /// (sección recién abierta), a su "foco inicial" (el elemento con autofocus,
  /// ej: la primera película) o al primero que se pueda elegir. Nunca "a la
  /// pantalla en general": ahí el control no movería nada.
  void _enfocarContenido() {
    if (_contenido.focusedChild != null) return _contenido.requestFocus();
    final elegibles = _contenido.traversalDescendants.where((n) => n.canRequestFocus && !n.skipTraversal);
    final inicial = elegibles.where((n) {
      final widget = n.context?.widget;
      return widget is Focus && widget.autofocus;
    }).firstOrNull;
    (inicial ?? elegibles.firstOrNull ?? _contenido).requestFocus();
  }

  /// Si el foco cae en "la pantalla en general" (al abrir la app, al cerrar un
  /// cartel, si lo elegido desapareció), se lo pasa enseguida al contenido:
  /// desde ahí las flechas no llevarían a donde corresponde.
  void _vigilarFoco() {
    if (!mounted) return;
    final general = FocusScope.of(context, createDependency: false);
    if (FocusManager.instance.primaryFocus != general) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || FocusManager.instance.primaryFocus != general) return;
      if (ModalRoute.of(context)?.isCurrent ?? false) _enfocarContenido();
    });
  }

  /// Red de seguridad: si el foco quedó afuera del contenido y del menú (al
  /// abrir la app, o si lo elegido desapareció) y se aprieta una tecla, se
  /// recupera: Izquierda abre el menú y lo demás va al contenido. Así el
  /// control remoto nunca queda "muerto". Solo con esta pantalla adelante
  /// (no con un cartel o el reproductor encima).
  bool _teclaSinFoco(KeyEvent evento) {
    if (evento is KeyUpEvent || !mounted || _contenido.hasFocus || _menu.hasFocus) return false;
    if (!(ModalRoute.of(context)?.isCurrent ?? false)) return false;
    final tecla = evento.logicalKey;
    if (tecla == LogicalKeyboardKey.arrowLeft) {
      _abrirMenu();
    } else if (_teclasDeMovimiento.contains(tecla) || teclasOk.contains(tecla)) {
      _enfocarContenido();
    } else {
      return false;
    }
    return true;
  }

  static final _teclasDeMovimiento = {
    LogicalKeyboardKey.arrowUp,
    LogicalKeyboardKey.arrowDown,
    LogicalKeyboardKey.arrowRight,
  };

  /// Izquierda en el contenido: se mueve dentro de la sección y, si ya está en
  /// el borde izquierdo (no hay nada más a la izquierda), abre el menú.
  KeyEventResult _teclaEnContenido(FocusNode nodo, KeyEvent evento) {
    if (evento is KeyUpEvent || evento.logicalKey != LogicalKeyboardKey.arrowLeft) return KeyEventResult.ignored;
    final actual = FocusManager.instance.primaryFocus;
    if (actual == null || !actual.focusInDirection(TraversalDirection.left)) _abrirMenu();
    return KeyEventResult.handled;
  }

  /// En el menú: Arriba/Abajo se mueven entre las opciones (lo hace Flutter) y
  /// Derecha vuelve al contenido, a lo último que estaba elegido.
  KeyEventResult _teclaEnMenu(FocusNode nodo, KeyEvent evento) {
    if (evento is KeyUpEvent) return KeyEventResult.ignored;
    if (evento.logicalKey == LogicalKeyboardKey.arrowRight) {
      _cerrarMenu();
      return KeyEventResult.handled;
    }
    // Izquierda no lleva a ningún lado (ya está en el borde)
    if (evento.logicalKey == LogicalKeyboardKey.arrowLeft) return KeyEventResult.handled;
    return KeyEventResult.ignored;
  }

  Future<void> _atras() async {
    if (_menuAbierto) return _cerrarMenu();
    if (widget.espejo) return; // la sección la elige el celular
    if (_seccion != SeccionTv.inicio) return _irA(SeccionTv.inicio);
    final salir = await showDialog<bool>(context: context, builder: (_) => const _ConfirmarSalida());
    if (salir == true) await SystemNavigator.pop();
  }

  Widget _seccionActual() {
    return switch (_seccion) {
      SeccionTv.inicio => const InicioTv(),
      SeccionTv.enVivo => const EnVivoTv(),
      SeccionTv.guia => const GuiaTv(),
      SeccionTv.peliculas => const GrillaTv(contenido: 'pelicula', key: ValueKey('peliculas')),
      SeccionTv.series => const GrillaTv(contenido: 'serie', key: ValueKey('series')),
      SeccionTv.buscar => BuscarTv(que: BuscarTv.queDesde(_antesDeBuscar)),
      SeccionTv.favoritos => const FavoritosTv(),
      SeccionTv.cuenta => const CuentaTv(),
      SeccionTv.nueva => _seccionNueva(),
    };
  }

  /// Una sección del panel: "en vivo" como En vivo, "a demanda" como Películas.
  /// Si ya no está (se borró o quedó vacía), Inicio.
  Widget _seccionNueva() {
    final seccion = _catalogo.seccionNueva(_nueva ?? '');
    if (seccion == null) return const InicioTv();
    return seccion.enVivo
        ? EnVivoTv(nueva: seccion.clave)
        : GrillaTv(contenido: 'pelicula', nueva: seccion.clave, key: ValueKey('nueva:${seccion.clave}'));
  }

  @override
  Widget build(BuildContext context) {
    return Theme(
      data: temaMovil(),
      child: DatosScope(
        catalogo: _catalogo,
        biblioteca: _biblioteca,
        child: NavegacionTv(
          irA: _irA,
          child: PopScope(
            canPop: false,
            onPopInvokedWithResult: (salio, _) {
              if (!salio) _atras();
            },
            child: Scaffold(
              backgroundColor: Tono.fondo,
              body: Stack(
                children: [
                  Positioned.fill(
                    key: _claveContenido,
                    child: FocusScope(
                      node: _contenido,
                      onKeyEvent: _teclaEnContenido,
                      child: ListenableBuilder(
                        listenable: _catalogo,
                        builder: (context, _) {
                          if (!_catalogo.cargado) return _Cargando(catalogo: _catalogo);
                          return KeyedSubtree(
                            key: ValueKey(_seccion == SeccionTv.nueva ? 'nueva:$_nueva' : _seccion),
                            child: _seccionActual(),
                          );
                        },
                      ),
                    ),
                  ),
                  // Al abrirse, el menú oscurece el contenido
                  IgnorePointer(
                    child: AnimatedOpacity(
                      opacity: _menuAbierto ? 1 : 0,
                      duration: const Duration(milliseconds: 160),
                      child: const DecoratedBox(
                        decoration: BoxDecoration(
                          gradient: LinearGradient(colors: [Color(0xE6131317), Color(0x00131317)], stops: [.2, .6]),
                        ),
                        child: SizedBox.expand(),
                      ),
                    ),
                  ),
                  Positioned(
                    left: 32,
                    top: 54,
                    bottom: 54,
                    child: FocusScope(
                      node: _menu,
                      onKeyEvent: _teclaEnMenu,
                      // Se rearma cuando llega el catálogo: ahí se sabe qué secciones nuevas hay
                      child: ListenableBuilder(
                        listenable: _catalogo,
                        builder: (context, _) => _Menu(
                          seccion: _seccion,
                          nueva: _nueva,
                          abierto: _menuAbierto,
                          nodos: _opcionesDelMenu,
                          nuevas: _catalogo.seccionesNuevas,
                          nodoNueva: _nodoNueva,
                          alElegir: _irA,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _Menu extends StatelessWidget {
  const _Menu({
    required this.seccion,
    required this.nueva,
    required this.abierto,
    required this.nodos,
    required this.nuevas,
    required this.nodoNueva,
    required this.alElegir,
  });

  final SeccionTv seccion;

  /// La clave de la sección nueva abierta (si es una de ellas).
  final String? nueva;
  final bool abierto;

  /// Uno por opción: al abrir el menú, el foco va a la de la sección actual.
  final Map<SeccionTv, FocusNode> nodos;

  /// Las secciones creadas en el panel (Música, Radio...): van después de Series.
  final List<SeccionNueva> nuevas;
  final FocusNode Function(String clave) nodoNueva;
  final void Function(SeccionTv seccion, {String? nueva}) alElegir;

  static const _opciones = [
    (SeccionTv.inicio, Icons.home_rounded, 'Inicio'),
    (SeccionTv.enVivo, Icons.live_tv_rounded, 'En vivo'),
    (SeccionTv.guia, Icons.view_list_rounded, 'Guía'),
    (SeccionTv.peliculas, Icons.movie_rounded, 'Películas'),
    (SeccionTv.series, Icons.video_library_rounded, 'Series'),
    (SeccionTv.buscar, Icons.search_rounded, 'Buscar'),
    (SeccionTv.favoritos, Icons.favorite_rounded, 'Favoritos'),
  ];

  @override
  Widget build(BuildContext context) {
    Widget opcion(SeccionTv valor, IconData icono, String texto, {required bool conNombre, String? clave}) {
      final activa = valor == seccion && clave == nueva;
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 5),
        child: Enfocable(
          nodo: clave != null ? nodoNueva(clave) : nodos[valor],
          alOk: () => alElegir(valor, nueva: clave),
          curva: Curva.boton,
          escala: 1.0,
          etiqueta: texto,
          child: Container(
            height: 60,
            padding: const EdgeInsets.symmetric(horizontal: 18),
            decoration: BoxDecoration(
              color: activa ? Tono.celeste.withValues(alpha: .12) : Colors.transparent,
              borderRadius: BorderRadius.circular(Curva.boton),
            ),
            child: Row(
              children: [
                Icon(icono, size: 26, color: activa ? Tono.celeste : Tono.textoSuave),
                if (conNombre) ...[
                  const SizedBox(width: 18),
                  Expanded(
                    child: Text(
                      texto,
                      maxLines: 1,
                      overflow: TextOverflow.clip,
                      style: TextStyle(
                        fontFamily: Letra.texto,
                        fontSize: 19,
                        fontWeight: FontWeight.w700,
                        color: activa ? Tono.celesteClaro : Tono.texto,
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      );
    }

    return AnimatedContainer(
      duration: const Duration(milliseconds: 160),
      curve: Curves.easeOut,
      width: abierto ? 292 : 88,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 24),
      decoration: BoxDecoration(
        color: Tono.capaMinima.withValues(alpha: .92),
        borderRadius: BorderRadius.circular(Curva.panel + 4),
        border: Border.all(color: Tono.bordeSuave.withValues(alpha: .45)),
        boxShadow: abierto ? const [BoxShadow(color: Colors.black54, blurRadius: 40)] : const [],
      ),
      child: FocusTraversalGroup(
        policy: OrderedTraversalPolicy(),
        // Los nombres y el logo completo aparecen recién cuando el menú ya se
        // ensanchó lo suficiente (si no, se desbordan durante la animación).
        child: LayoutBuilder(
          builder: (context, medidas) {
            final conNombres = medidas.maxWidth >= 220;
            return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Align(
                  alignment: conNombres ? Alignment.centerLeft : Alignment.center,
                  child: Padding(
                    padding: EdgeInsets.only(left: conNombres ? 12 : 0, bottom: 34),
                    // El logo completo se achica si no entra en el ancho del menú
                    child: conNombres
                        ? const FittedBox(fit: BoxFit.scaleDown, child: LogoKairos(tamanio: 40))
                        : const SimboloKairos(tamanio: 42),
                  ),
                ),
                // Con varias secciones nuevas puede no entrar todo: el medio se desplaza
                Expanded(
                  child: SingleChildScrollView(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        for (final (valor, icono, texto) in _opciones) ...[
                          opcion(valor, icono, texto, conNombre: conNombres),
                          if (valor == SeccionTv.series)
                            for (final s in nuevas)
                              opcion(
                                SeccionTv.nueva,
                                iconoDeSeccion(s.icono),
                                s.nombre,
                                conNombre: conNombres,
                                clave: s.clave,
                              ),
                        ],
                      ],
                    ),
                  ),
                ),
                opcion(SeccionTv.cuenta, Icons.account_circle_rounded, 'Mi cuenta', conNombre: conNombres),
              ],
            );
          },
        ),
      ),
    );
  }
}

/// Mientras llega el catálogo (o si no llegó).
class _Cargando extends StatelessWidget {
  const _Cargando({required this.catalogo});

  final Catalogo catalogo;

  @override
  Widget build(BuildContext context) {
    final error = catalogo.error;
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const SimboloKairos(tamanio: 110),
          const SizedBox(height: 32),
          if (error == null) ...[
            const SizedBox(
              width: 260,
              child: LinearProgressIndicator(minHeight: 4, color: Tono.celeste, backgroundColor: Tono.capaMaxima),
            ),
            const SizedBox(height: 16),
            const Text('Preparando tu contenido…', style: LetraTv.cuerpo),
          ] else ...[
            Text(textoDeError(error), textAlign: TextAlign.center, style: LetraTv.cuerpo),
            const SizedBox(height: 24),
            BotonTv(
              texto: 'Reintentar',
              icono: Icons.refresh_rounded,
              principal: true,
              autofocus: true,
              alOk: catalogo.cargar,
            ),
          ],
        ],
      ),
    );
  }
}

/// "¿Querés salir de Kairos TV?" (tv-20): el foco arranca en "Seguir mirando".
class _ConfirmarSalida extends StatelessWidget {
  const _ConfirmarSalida();

  @override
  Widget build(BuildContext context) {
    return DialogoTv(
      icono: Icons.logout_rounded,
      titulo: '¿Querés salir de Kairos TV?',
      texto: 'Tu sesión queda abierta: la próxima vez entrás directo.',
      botones: [
        BotonTv(texto: 'Seguir mirando', principal: true, autofocus: true, alOk: () => Navigator.pop(context, false)),
        BotonTv(texto: 'Salir', alOk: () => Navigator.pop(context, true)),
      ],
    );
  }
}

/// Un cartel de la TV: ícono, título, texto y botones en fila.
class DialogoTv extends StatelessWidget {
  const DialogoTv({super.key, required this.titulo, required this.botones, this.texto, this.icono, this.hijo});

  final String titulo;
  final String? texto;
  final IconData? icono;
  final List<Widget> botones;
  final Widget? hijo;

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: Tono.capaBaja,
      insetPadding: const EdgeInsets.all(80),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(Curva.portada),
        side: BorderSide(color: Tono.bordeSuave.withValues(alpha: .5)),
      ),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 760),
        child: Padding(
          padding: const EdgeInsets.all(48),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (icono != null) ...[Icon(icono, size: 56, color: Tono.celeste), const SizedBox(height: 20)],
              Text(titulo, textAlign: TextAlign.center, style: LetraTv.pantalla),
              if (texto != null) ...[
                const SizedBox(height: 12),
                Text(texto!, textAlign: TextAlign.center, style: LetraTv.cuerpo),
              ],
              ?hijo,
              const SizedBox(height: 34),
              FocusTraversalGroup(
                child: Wrap(spacing: 18, runSpacing: 14, alignment: WrapAlignment.center, children: botones),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// "Volviendo a (canal) en 3…": cancelable (Mi cuenta -> "Volver al último canal al abrir").
class CuentaRegresivaTv extends StatefulWidget {
  const CuentaRegresivaTv({super.key, required this.canal});

  final Canal canal;

  @override
  State<CuentaRegresivaTv> createState() => _CuentaRegresivaTvState();
}

class _CuentaRegresivaTvState extends State<CuentaRegresivaTv> {
  int _faltan = 3;
  Timer? _reloj;

  @override
  void initState() {
    super.initState();
    _reloj = Timer.periodic(const Duration(seconds: 1), (_) {
      if (_faltan <= 1) {
        _reloj?.cancel();
        Navigator.pop(context, true);
      } else {
        setState(() => _faltan--);
      }
    });
  }

  @override
  void dispose() {
    _reloj?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return DialogoTv(
      icono: Icons.restore_rounded,
      titulo: 'Volviendo a ${widget.canal.nombre}',
      texto: 'En $_faltan…',
      botones: [
        BotonTv(texto: 'Verlo ahora', principal: true, alOk: () => Navigator.pop(context, true)),
        BotonTv(texto: 'Cancelar', autofocus: true, alOk: () => Navigator.pop(context, false)),
      ],
    );
  }
}
