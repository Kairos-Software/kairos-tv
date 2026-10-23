/// La app en el celular (diseño de Stitch): la barra de arriba con el logo y
/// la sección, las seis secciones y la barra de abajo
/// (Inicio · En Vivo · Series · Películas · Favoritos · Mi Espacio).
/// Favoritos se sumó con el diseño de ChatGPT (diseno_kairos_tv/DESIGN.md -> Celular).
///
/// Acá se crean el catálogo y la biblioteca, y se vuelve a pedir el catálogo
/// al volver a la app y cada 15 minutos.
library;

import 'dart:async';
import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../sesion.dart';
import '../marca.dart';
import '../tele/control_remoto.dart';
import '../tele/enlace.dart';
import 'buscar.dart';
import 'datos.dart';
import 'en_vivo.dart';
import 'favoritos.dart';
import 'estilo.dart';
import 'grilla.dart';
import 'inicio.dart';
import 'mi_espacio.dart';
import 'recordatorios.dart';

/// Las secciones de la barra de abajo.
enum Seccion { inicio, enVivo, series, peliculas, favoritos, miEspacio }

/// Para que cualquier pantalla pueda cambiar de sección (ej: un chip de
/// Inicio que lleva a En Vivo con una categoría elegida).
class NavegacionMovil extends InheritedWidget {
  const NavegacionMovil({super.key, required this.irA, required super.child});

  final void Function(Seccion seccion, {String? categoria, int? canal}) irA;

  static NavegacionMovil of(BuildContext context) => context.dependOnInheritedWidgetOfExactType<NavegacionMovil>()!;

  @override
  bool updateShouldNotify(NavegacionMovil oldWidget) => false;
}

class PantallaMovil extends StatefulWidget {
  const PantallaMovil({super.key, this.catalogo, this.biblioteca, this.seccionInicial = Seccion.inicio});

  /// Solo para las pruebas: un catálogo y una biblioteca ya armados (no se pide nada a la API).
  final Catalogo? catalogo;
  final Biblioteca? biblioteca;
  final Seccion seccionInicial;

  @override
  State<PantallaMovil> createState() => _PantallaMovilState();
}

class _PantallaMovilState extends State<PantallaMovil> {
  static const _cadaCuanto = Duration(minutes: 15);

  late final Catalogo _catalogo = widget.catalogo ?? Catalogo(SesionScope.leer(context).api);
  late final Biblioteca _biblioteca =
      widget.biblioteca ?? Biblioteca(api: SesionScope.leer(context).api, cuenta: SesionScope.leer(context).cuenta);
  late Seccion _seccion = widget.seccionInicial;

  /// Lo que se pidió al saltar a En Vivo (ej: un chip o una tarjeta de Inicio).
  PedidoEnVivo? _pedidoEnVivo;
  AppLifecycleListener? _ciclo;
  Timer? _refresco;

  @override
  void initState() {
    super.initState();
    Tele.instancia.seccion(_seccion.name); // si hay una tele conectada, que muestre lo mismo
    if (widget.biblioteca == null) _biblioteca.cargar();
    _catalogo.addListener(_volverAlUltimoCanal);
    _catalogo.addListener(_asegurarCapitulos);
    _biblioteca.addListener(_asegurarCapitulos);
    // Un aviso de "Mi agenda" tocado (o "Ver" en Mi agenda): a En Vivo con ese canal
    Recordatorios.canalPedido.addListener(_abrirCanalPedido);
    _catalogo.addListener(_abrirCanalPedido);
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
    Tele.instancia.seccion(null); // salió (cerró sesión): la tele vuelve al logo
    Recordatorios.canalPedido.removeListener(_abrirCanalPedido);
    _catalogo.removeListener(_abrirCanalPedido);
    _catalogo.removeListener(_volverAlUltimoCanal);
    _catalogo.removeListener(_asegurarCapitulos);
    _biblioteca.removeListener(_asegurarCapitulos);
    _ciclo?.dispose();
    _refresco?.cancel();
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

  /// "Volver al último canal al abrir" (Mi Espacio): apenas llega el catálogo, a En Vivo con ese canal.
  void _volverAlUltimoCanal() {
    if (!_catalogo.cargado) return;
    _catalogo.removeListener(_volverAlUltimoCanal);
    final ultimo = _biblioteca.ultimoCanal;
    if (_biblioteca.volverAlUltimo && ultimo != null && _catalogo.canalPorId(ultimo) != null) {
      _irA(Seccion.enVivo, canal: ultimo);
    }
  }

  /// El canal de un aviso de "Mi agenda" que se tocó (la app pudo abrirse con el aviso: espera al catálogo).
  void _abrirCanalPedido() {
    final id = Recordatorios.canalPedido.value;
    if (id == null || !_catalogo.cargado || !mounted) return;
    Recordatorios.canalPedido.value = null;
    if (_catalogo.canalPorId(id) == null) return;
    Navigator.of(context).popUntil((ruta) => ruta.isFirst);
    _irA(Seccion.enVivo, canal: id);
  }

  void _irA(Seccion seccion, {String? categoria, int? canal}) {
    Tele.instancia.seccion(seccion.name);
    setState(() {
      _seccion = seccion;
      if (seccion == Seccion.enVivo && (categoria != null || canal != null)) {
        _pedidoEnVivo = PedidoEnVivo(categoria: categoria, canal: canal);
      }
    });
  }

  static const _titulos = {
    Seccion.inicio: 'Inicio',
    Seccion.enVivo: 'En Vivo',
    Seccion.series: 'Series',
    Seccion.peliculas: 'Películas',
    Seccion.favoritos: 'Favoritos',
    Seccion.miEspacio: 'Mi Espacio',
  };

  @override
  Widget build(BuildContext context) {
    return Theme(
      data: temaMovil(),
      child: AnnotatedRegion<SystemUiOverlayStyle>(
        value: SystemUiOverlayStyle.light.copyWith(
          statusBarColor: Colors.transparent,
          systemNavigationBarColor: Tono.capaMinima,
        ),
        child: DatosScope(
          catalogo: _catalogo,
          biblioteca: _biblioteca,
          child: NavegacionMovil(
            irA: _irA,
            child: PopScope(
              // "Atrás" en otra sección vuelve a Inicio antes de salir de la app
              canPop: _seccion == Seccion.inicio,
              onPopInvokedWithResult: (salio, _) {
                if (!salio) _irA(Seccion.inicio);
              },
              child: Scaffold(
                backgroundColor: Tono.fondo,
                extendBody: true,
                extendBodyBehindAppBar: true,
                appBar: _BarraSuperior(
                  titulo: _titulos[_seccion]!,
                  alBuscar: () => Navigator.push(
                    context,
                    MaterialPageRoute<void>(
                      builder: (_) => DatosScope(
                        catalogo: _catalogo,
                        biblioteca: _biblioteca,
                        child: Theme(
                          data: temaMovil(),
                          child: PantallaBuscar(irA: _irA, que: PantallaBuscar.queDesde(_seccion)),
                        ),
                      ),
                    ),
                  ),
                  alPerfil: () => _irA(Seccion.miEspacio),
                ),
                body: IndexedStack(
                  index: _seccion.index,
                  children: [
                    const SeccionInicio(),
                    SeccionEnVivo(visible: _seccion == Seccion.enVivo, pedido: _pedidoEnVivo),
                    const SeccionGrilla(contenido: 'serie'),
                    const SeccionGrilla(contenido: 'pelicula'),
                    const SeccionFavoritos(),
                    const SeccionMiEspacio(),
                  ],
                ),
                bottomNavigationBar: _BarraInferior(seccion: _seccion, alElegir: _irA),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Lo que ocupan las barras de arriba y de abajo, para dejarle lugar al
/// contenido de las secciones (que pasa por detrás de las barras de vidrio).
/// Como el Scaffold tiene extendBody y extendBodyBehindAppBar, Flutter ya
/// suma el alto de cada barra al "padding" de las secciones.
double altoBarraSuperior(BuildContext context) => MediaQuery.paddingOf(context).top;

double altoBarraInferior(BuildContext context) => MediaQuery.paddingOf(context).bottom;

/// "header": vidrio oscuro (capa mínima al 80 % con desenfoque), el logo y la
/// sección en celeste; a la derecha buscar y el avatar.
class _BarraSuperior extends StatelessWidget implements PreferredSizeWidget {
  const _BarraSuperior({required this.titulo, required this.alBuscar, required this.alPerfil});

  final String titulo;
  final VoidCallback alBuscar;
  final VoidCallback alPerfil;

  @override
  Size get preferredSize => const Size.fromHeight(56);

  @override
  Widget build(BuildContext context) {
    final sesion = SesionScope.of(context);
    final nombre = sesion.cliente?.nombre ?? sesion.perfil?.nombreCompleto ?? '';
    return ClipRect(
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 24, sigmaY: 24),
        child: Container(
          decoration: BoxDecoration(
            color: Tono.capaMinima.withValues(alpha: .8),
            boxShadow: const [BoxShadow(color: Color(0x66000000), blurRadius: 8, offset: Offset(0, 1))],
          ),
          padding: EdgeInsets.only(top: MediaQuery.paddingOf(context).top),
          child: SizedBox(
            height: 56,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: Espacio.margen),
              child: Row(
                children: [
                  const SimboloKairos(tamanio: 26),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      titulo.toUpperCase(),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: Letra.etiqueta.copyWith(
                        color: Tono.celesteClaro,
                        fontWeight: FontWeight.w700,
                        letterSpacing: 1.2,
                      ),
                    ),
                  ),
                  // "Ver en la tele" (lib/tele/)
                  const BotonTele(),
                  IconButton(
                    tooltip: 'Buscar',
                    onPressed: alBuscar,
                    icon: const Icon(Icons.search_rounded, size: 22, color: Tono.textoSuave),
                  ),
                  const SizedBox(width: 4),
                  Tooltip(
                    message: 'Mi Espacio',
                    child: InkWell(
                      onTap: alPerfil,
                      customBorder: const CircleBorder(),
                      child: Container(
                        width: 34,
                        height: 34,
                        alignment: Alignment.center,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          gradient: const LinearGradient(
                            colors: [Tono.celeste, Color(0xFF006970)],
                            begin: Alignment.topLeft,
                            end: Alignment.bottomRight,
                          ),
                          border: Border.all(color: Tono.capaMaxima, width: 2),
                        ),
                        child: Text(
                          _iniciales(nombre),
                          style: Letra.mini.copyWith(fontSize: 12, color: Tono.sobreCelesteOscuro),
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

  static String _iniciales(String nombre) {
    final letras = nombre.split(' ').where((p) => p.isNotEmpty).take(2).map((p) => p[0]).join().toUpperCase();
    return letras.isEmpty ? 'TV' : letras;
  }
}

/// "nav": vidrio oscuro (capa mínima al 90 %), seis botones; el activo en celeste.
class _BarraInferior extends StatelessWidget {
  const _BarraInferior({required this.seccion, required this.alElegir});

  final Seccion seccion;
  final void Function(Seccion) alElegir;

  static const _items = [
    (Seccion.inicio, Icons.home_outlined, Icons.home_rounded, 'Inicio'),
    (Seccion.enVivo, Icons.live_tv_outlined, Icons.live_tv_rounded, 'En Vivo'),
    (Seccion.series, Icons.video_library_outlined, Icons.video_library_rounded, 'Series'),
    (Seccion.peliculas, Icons.movie_outlined, Icons.movie_rounded, 'Películas'),
    (Seccion.favoritos, Icons.favorite_border_rounded, Icons.favorite_rounded, 'Favoritos'),
    (Seccion.miEspacio, Icons.account_circle_outlined, Icons.account_circle_rounded, 'Mi Espacio'),
  ];

  @override
  Widget build(BuildContext context) {
    return ClipRect(
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 24, sigmaY: 24),
        child: Container(
          decoration: BoxDecoration(
            color: Tono.capaMinima.withValues(alpha: .9),
            boxShadow: const [BoxShadow(color: Color(0x80000000), blurRadius: 12, offset: Offset(0, -1))],
          ),
          padding: EdgeInsets.only(bottom: MediaQuery.paddingOf(context).bottom),
          child: SizedBox(
            height: 64,
            child: Row(
              children: [
                for (final (valor, icono, iconoActivo, texto) in _items)
                  Expanded(
                    child: InkWell(
                      onTap: () => alElegir(valor),
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(
                            valor == seccion ? iconoActivo : icono,
                            size: 24,
                            color: valor == seccion ? Tono.celeste : Tono.textoSuave,
                          ),
                          const SizedBox(height: 2),
                          Text(
                            texto,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: Letra.mini.copyWith(
                              color: valor == seccion ? Tono.celeste : Tono.textoSuave,
                              fontWeight: valor == seccion ? FontWeight.w700 : FontWeight.w600,
                              fontSize: 9.5,
                              letterSpacing: -0.2,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
