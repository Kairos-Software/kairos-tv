/// Los reproductores de la TV (diseno_kairos_tv: tv-12, tv-13, tv-19).
///
/// Pensados para el control remoto: nada "atrapa" el botón Atrás sin que se
/// vea, y lo que se abre encima del video lleva el foco a su primer botón y
/// se cierra solo si no se toca.
///
/// EN VIVO (ReproductorVivoTv):
///   Al abrir o cambiar de canal: un cartel con el canal que SOLO informa
///   (4 s; no toma el foco: Atrás sale directo).
///   OK (o la tecla Guía): la GUÍA encima del video, parada en el canal que
///       se ve. Arriba/Abajo la recorren, OK cambia de canal, Atrás la cierra.
///   Arriba/Abajo (o CH+/CH-): zapping.
///   Izquierda/Derecha (o Info/Menú): las opciones (Guía, canal anterior y
///       siguiente, favoritos, Recordarme, Ajustes: calidad, idioma, imagen y fuente).
///   Números: se escribe el número del canal (hasta 3, 1,5 s) y cambia solo.
///   Atrás: cierra lo que esté abierto; si no hay nada, sale.
///
/// PELÍCULAS Y CAPÍTULOS (ReproductorVodTv):
///   OK (o Play/Pausa): pausa / sigue y muestra la barra.
///   Izquierda/Derecha: -10 s / +10 s (y la barra queda en la línea de tiempo).
///   Arriba/Abajo: la barra (pausa, siguiente episodio, favoritos, Ajustes).
///   En la barra: Izquierda/Derecha van de botón en botón (en los bordes se
///       quedan), Abajo va a la línea de tiempo y, desde ahí, Arriba vuelve a Pausa.
///   Atrás: esconde la barra; si no está, sale.
///   Guarda por dónde va cada 5 s y al terminar un capítulo sigue con el próximo.
///
/// YOUTUBE OFICIAL (ReproductorYoutubeTv): igual que las películas, pero el
///   video es el reproductor de YouTube (movil/reproductor_youtube.dart). Sin
///   Ajustes: la calidad la elige YouTube.
///
/// Las opciones y la barra se esconden solas a los 5 s (en pausa, no); la guía a los 15 s.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:video_player/video_player.dart';
import 'package:wakelock_plus/wakelock_plus.dart';

import '../api/modelos.dart';
import '../movil/ajustes_video.dart';
import '../movil/componentes.dart';
import '../movil/control_senal.dart';
import '../movil/datos.dart';
import '../movil/detalle.dart' show proximoEpisodio;
import '../movil/estilo.dart';
import '../movil/reproductor_youtube.dart';
import '../sesion.dart';
import '../widgets/espera_larga.dart';
import 'estructura.dart' show DialogoTv;
import 'foco.dart';
import 'mi_agenda.dart';
import 'piezas.dart';

/// Las opciones y la barra se cierran solas si no se toca nada en este tiempo.
const _esperaControles = Duration(seconds: 5);

/// El cartel con el nombre del canal (solo informa).
const _esperaCartel = Duration(seconds: 4);

/// La guía encima del video (da más tiempo: se está eligiendo).
const _esperaGuia = Duration(seconds: 15);

/// Pone un canal en vivo a pantalla completa. [lista]: los canales para el zapping (por defecto, todos).
Future<void> verCanalTv(BuildContext context, Canal canal, {List<Canal>? lista}) {
  final catalogo = DatosScope.of(context).catalogo;
  return abrirTv<void>(context, ReproductorVivoTv(canal: canal, lista: lista ?? catalogo.canales));
}

/// Reproduce una película (si quedó a medias, desde ahí). Las de YouTube
/// oficial, en el reproductor de YouTube (movil/reproductor_youtube.dart).
Future<void> reproducirPeliculaTv(BuildContext context, Canal pelicula, {bool desdeElInicio = false}) {
  final desde = desdeElInicio ? null : _dondeQuedo(context, pelicula);
  return abrirTv<void>(
    context,
    fuenteDeYoutube(pelicula) != null
        ? ReproductorYoutubeTv(canal: pelicula, desde: desde)
        : ReproductorVodTv(canal: pelicula, desde: desde),
  );
}

/// Reproduce un capítulo (si no se dice cuál, el que corresponde: el que quedó a medias o el siguiente).
Future<void> reproducirSerieTv(BuildContext context, Serie serie, {Episodio? episodio, bool desdeElInicio = false}) {
  final elegido = episodio ?? proximoEpisodio(serie, DatosScope.of(context).biblioteca);
  final desde = desdeElInicio ? null : _dondeQuedo(context, elegido.canal);
  return abrirTv<void>(
    context,
    fuenteDeYoutube(elegido.canal) != null
        ? ReproductorYoutubeTv(canal: elegido.canal, serie: serie, episodio: elegido, desde: desde)
        : ReproductorVodTv(canal: elegido.canal, serie: serie, episodio: elegido, desde: desde),
  );
}

Duration? _dondeQuedo(BuildContext context, Canal canal) {
  final progreso = DatosScope.of(context).biblioteca.progresoDe(canal.id);
  return progreso == null || progreso.terminado ? null : progreso.posicion;
}

// ── En vivo ────────────────────────────────────────────────────────

class ReproductorVivoTv extends StatefulWidget {
  const ReproductorVivoTv({super.key, required this.canal, required this.lista});

  final Canal canal;
  final List<Canal> lista;

  @override
  State<ReproductorVivoTv> createState() => _ReproductorVivoTvState();
}

/// Lo que está abierto encima del video en vivo.
enum _CapaVivo { nada, opciones, guia }

class _ReproductorVivoTvState extends State<ReproductorVivoTv> {
  late final ControlSenal _control = ControlSenal(SesionScope.leer(context).api)
    ..alVerCanal = ((canal) => DatosScope.of(context).biblioteca.registrarCanalVisto(canal.id))
    ..addListener(_alCambiar);
  // No entra en el recorrido de las flechas: si no, desde un botón de la
  // barra "Derecha" saltaba al video (que ocupa toda la pantalla)
  final _raiz = FocusNode(debugLabel: 'reproductor', skipTraversal: true);
  final _primeraOpcion = FocusNode(debugLabel: 'opciones: guía');
  final _canalEnLaGuia = FocusNode(debugLabel: 'guía: canal actual');
  final _reintentar = FocusNode(debugLabel: 'probar de nuevo');
  _CapaVivo _capa = _CapaVivo.nada;

  /// El cartel con el nombre del canal: solo informa (no toma el foco ni atrapa "Atrás").
  bool _cartel = true;
  Timer? _cerrarCartel;
  Timer? _cerrarCapa;
  String? _errorAnterior;

  /// El número que se está escribiendo con el control ("10_").
  String _numero = '';
  Timer? _numeroListo;

  @override
  void initState() {
    super.initState();
    WakelockPlus.enable().catchError((Object _) {});
    _control.abrir(widget.canal);
    _esconderCartelDespues();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _raiz.requestFocus();
    });
  }

  @override
  void dispose() {
    _cerrarCartel?.cancel();
    _cerrarCapa?.cancel();
    _numeroListo?.cancel();
    _control.dispose();
    for (final nodo in [_raiz, _primeraOpcion, _canalEnLaGuia, _reintentar]) {
      nodo.dispose();
    }
    WakelockPlus.disable().catchError((Object _) {});
    super.dispose();
  }

  void _alCambiar() {
    if (!mounted) return;
    // Si la señal falló, el foco va a "Probar de nuevo" (si no hay nada abierto encima)
    final error = _control.error;
    if (error != null && error != _errorAnterior && _capa == _CapaVivo.nada) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && _reintentar.context != null) _reintentar.requestFocus();
      });
    }
    _errorAnterior = error;
    setState(() {});
  }

  Canal get _canal => _control.canal ?? widget.canal;

  void _mostrarCartel() {
    setState(() => _cartel = true);
    _esconderCartelDespues();
  }

  /// (El cartel arranca visible: al abrir solo hace falta esto.)
  void _esconderCartelDespues() {
    _cerrarCartel?.cancel();
    _cerrarCartel = Timer(_esperaCartel, () {
      if (mounted) setState(() => _cartel = false);
    });
  }

  /// Abre las opciones o la guía y les lleva el foco. Se cierran solas si no se toca nada.
  void _abrir(_CapaVivo capa) {
    setState(() {
      _capa = capa;
      _cartel = false;
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || _capa != capa) return;
      (capa == _CapaVivo.guia ? _canalEnLaGuia : _primeraOpcion).requestFocus();
    });
    _esperarParaCerrar();
  }

  void _esperarParaCerrar() {
    _cerrarCapa?.cancel();
    _cerrarCapa = Timer(_capa == _CapaVivo.guia ? _esperaGuia : _esperaControles, () {
      if (mounted && _capa != _CapaVivo.nada) _cerrar();
    });
  }

  void _cerrar() {
    _cerrarCapa?.cancel();
    setState(() => _capa = _CapaVivo.nada);
    (_control.error != null && _reintentar.context != null ? _reintentar : _raiz).requestFocus();
  }

  void _zapping(int paso) {
    final lista = widget.lista;
    if (lista.length < 2) return;
    final actual = lista.indexWhere((c) => c.id == _canal.id);
    _control.abrir(lista[((actual < 0 ? 0 : actual) + paso) % lista.length]);
    _mostrarCartel();
  }

  void _ver(Canal canal) {
    if (canal.id != _canal.id) _control.abrir(canal);
    _cerrar();
    _mostrarCartel();
  }

  void _escribirNumero(String digito) {
    _numeroListo?.cancel();
    setState(() => _numero = (_numero + digito).length > 3 ? digito : _numero + digito);
    _numeroListo = Timer(const Duration(milliseconds: 1500), () {
      if (!mounted) return;
      final canal = DatosScope.of(context).catalogo.canalPorNumero(_numero);
      setState(() => _numero = '');
      if (canal != null) {
        _ver(canal);
      } else {
        avisoTv(context, 'No hay un canal con ese número', icono: Icons.info_outline_rounded);
      }
    });
  }

  KeyEventResult _tecla(FocusNode _, KeyEvent evento) {
    if (evento is KeyUpEvent) return KeyEventResult.ignored;
    final tecla = evento.logicalKey;
    final digito = evento.character != null && RegExp(r'^\d$').hasMatch(evento.character!) ? evento.character : null;
    if (digito != null && _capa != _CapaVivo.guia) {
      _escribirNumero(digito);
      return KeyEventResult.handled;
    }
    if (tecla == LogicalKeyboardKey.channelUp || tecla == LogicalKeyboardKey.channelDown) {
      _zapping(tecla == LogicalKeyboardKey.channelUp ? 1 : -1);
      return KeyEventResult.handled;
    }
    if (tecla == LogicalKeyboardKey.guide) {
      _capa == _CapaVivo.guia ? _cerrar() : _abrir(_CapaVivo.guia);
      return KeyEventResult.handled;
    }
    if (_capa != _CapaVivo.nada) {
      _esperarParaCerrar(); // se está usando: no se cierra
      return KeyEventResult.ignored; // las flechas recorren la guía o las opciones
    }
    // Como en la guía: Arriba, el canal de arriba (el anterior); Abajo, el de abajo (el siguiente).
    // CH+ / CH- siguen como en cualquier TV: CH+ sube el número.
    if (tecla == LogicalKeyboardKey.arrowUp || tecla == LogicalKeyboardKey.arrowDown) {
      _zapping(tecla == LogicalKeyboardKey.arrowDown ? 1 : -1);
      return KeyEventResult.handled;
    }
    // Con el error a la vista, Izquierda/Derecha recorren sus botones ("Probar de nuevo", "Ver la guía")
    if (_control.error != null && !_raiz.hasPrimaryFocus) return KeyEventResult.ignored;
    if (teclasOk.contains(tecla)) {
      _abrir(_CapaVivo.guia);
      return KeyEventResult.handled;
    }
    if (tecla == LogicalKeyboardKey.arrowLeft ||
        tecla == LogicalKeyboardKey.arrowRight ||
        tecla == LogicalKeyboardKey.info ||
        tecla == LogicalKeyboardKey.contextMenu) {
      _abrir(_CapaVivo.opciones);
      return KeyEventResult.handled;
    }
    return KeyEventResult.ignored;
  }

  Future<void> _ajustes() async {
    _cerrarCapa?.cancel();
    await ajustesDeVideoTv(context, _control);
    if (mounted) _cerrar();
  }

  /// "Recordarme" en este canal (Mi agenda: tv/mi_agenda.dart).
  Future<void> _recordarme() async {
    _cerrarCapa?.cancel();
    await recordarmeTv(context, canal: _canal);
    if (mounted) _cerrar();
  }

  @override
  Widget build(BuildContext context) {
    final biblioteca = DatosScope.of(context).biblioteca;
    final catalogo = DatosScope.of(context).catalogo;
    final canal = _canal;
    final clave = Biblioteca.claveDe(canal);
    final favorito = biblioteca.estaEnMiLista(clave);
    final numero = catalogo.numeroDe(canal);
    final categoria = categoriaLegible(canal.categoria);
    final escrito = _numero.isEmpty ? null : catalogo.canalPorNumero(_numero);

    final datosDelCanal = [
      Container(
        width: 104,
        height: 74,
        decoration: BoxDecoration(
          color: Tono.capa.withValues(alpha: .85),
          borderRadius: BorderRadius.circular(Curva.grande),
          border: Border.all(color: Colors.white.withValues(alpha: .12)),
        ),
        child: LogoCanalTv(canal: canal, tamanioIniciales: 24, relleno: const EdgeInsets.all(9)),
      ),
      const SizedBox(width: 22),
      Expanded(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              canal.nombre,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: LetraTv.tarjeta.copyWith(fontSize: 30, height: 1.1),
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                if (numero.isNotEmpty) _Insignia('CANAL $numero', destacada: true),
                for (final texto in _insigniasDeLaSenal(_control)) _Insignia(texto),
                if (categoria.isNotEmpty)
                  Flexible(
                    child: Text(
                      categoria,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: LetraTv.ayuda.copyWith(fontSize: 17, color: Tono.textoSuave),
                    ),
                  ),
              ],
            ),
          ],
        ),
      ),
    ];

    return PopScope(
      // "Atrás": cierra lo que esté abierto; si no hay nada, sale
      canPop: _capa == _CapaVivo.nada,
      onPopInvokedWithResult: (salio, _) {
        if (!salio) _cerrar();
      },
      child: Scaffold(
        backgroundColor: Colors.black,
        body: Focus(
          focusNode: _raiz,
          onKeyEvent: _tecla,
          child: Stack(
            fit: StackFit.expand,
            children: [
              _Video(control: _control),
              _EstadoSenal(
                control: _control,
                alReintentar: _control.reintentar,
                alGuia: () => _abrir(_CapaVivo.guia),
                nodoReintentar: _reintentar,
              ),
              if (_cartel || _capa != _CapaVivo.nada)
                const Positioned(top: MargenTv.arriba, left: MargenTv.derecha, child: InsigniaEnVivoTv(grande: true)),
              if (_numero.isNotEmpty)
                Positioned(
                  top: MargenTv.arriba,
                  right: MargenTv.derecha,
                  child: _NumeroEscrito(numero: _numero, canal: escrito?.nombre),
                ),
              // El cartel: solo informa
              if (_cartel && _capa == _CapaVivo.nada && _control.error == null)
                Positioned(
                  left: 0,
                  right: 0,
                  bottom: 0,
                  child: _PanelControles(
                    ayuda: 'OK: guía  ·  ↑ ↓ cambiar de canal  ·  ← →: opciones  ·  Atrás: salir',
                    fila: datosDelCanal,
                  ),
                ),
              if (_capa == _CapaVivo.opciones)
                Positioned(
                  left: 0,
                  right: 0,
                  bottom: 0,
                  child: _PanelControles(
                    ayuda: '← → elegir  ·  OK: confirmar  ·  Atrás: cerrar',
                    alMoverse: _esperarParaCerrar,
                    fila: [
                      _BotonCuadrado(
                        icono: Icons.view_list_rounded,
                        etiqueta: 'Guía',
                        nodo: _primeraOpcion,
                        alOk: () => _abrir(_CapaVivo.guia),
                      ),
                      const SizedBox(width: 14),
                      _BotonCuadrado(
                        icono: Icons.skip_previous_rounded,
                        etiqueta: 'Canal anterior',
                        alOk: () {
                          _zapping(-1);
                          _esperarParaCerrar();
                        },
                      ),
                      const SizedBox(width: 14),
                      _BotonCuadrado(
                        icono: Icons.skip_next_rounded,
                        etiqueta: 'Canal siguiente',
                        alOk: () {
                          _zapping(1);
                          _esperarParaCerrar();
                        },
                      ),
                      const SizedBox(width: 20),
                      ...datosDelCanal,
                      _BotonCuadrado(
                        icono: favorito ? Icons.favorite_rounded : Icons.favorite_border_rounded,
                        color: favorito ? Tono.rubi : null,
                        etiqueta: favorito ? 'Quitar de favoritos' : 'Agregar a favoritos',
                        alOk: () {
                          alternarFavoritoTv(context, clave);
                          _esperarParaCerrar();
                        },
                      ),
                      const SizedBox(width: 14),
                      _BotonCuadrado(
                        icono: Icons.notifications_none_rounded,
                        etiqueta: 'Recordarme',
                        alOk: _recordarme,
                      ),
                      const SizedBox(width: 18),
                      _BotonCuadrado(icono: Icons.settings_rounded, etiqueta: 'Ajustes', alOk: _ajustes),
                    ],
                  ),
                ),
              if (_capa == _CapaVivo.guia)
                _GuiaEncima(
                  lista: widget.lista,
                  actual: canal,
                  numeroDe: catalogo.numeroDe,
                  nodoActual: _canalEnLaGuia,
                  alElegir: _ver,
                ),
            ],
          ),
        ),
      ),
    );
  }
}

/// El número que se está escribiendo, arriba a la derecha ("10_", y el canal si existe).
class _NumeroEscrito extends StatelessWidget {
  const _NumeroEscrito({required this.numero, this.canal});

  final String numero;
  final String? canal;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 30, vertical: 18),
      decoration: BoxDecoration(
        color: Tono.capaMinima.withValues(alpha: .9),
        borderRadius: BorderRadius.circular(Curva.panel),
        border: Border.all(color: Tono.bordeSuave.withValues(alpha: .5)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Text(
            numero.padRight(3, '_'),
            style: const TextStyle(
              fontFamily: Letra.titulos,
              fontSize: 64,
              fontWeight: FontWeight.w800,
              letterSpacing: 6,
              color: Tono.dorado,
            ),
          ),
          if (canal != null) Text(canal!, style: LetraTv.cuerpo.copyWith(color: Tono.texto)),
        ],
      ),
    );
  }
}

/// La guía encima del video: la lista de canales a la izquierda, parada en el que se ve.
class _GuiaEncima extends StatelessWidget {
  const _GuiaEncima({
    required this.lista,
    required this.actual,
    required this.numeroDe,
    required this.alElegir,
    required this.nodoActual,
  });

  final List<Canal> lista;
  final Canal actual;
  final String Function(Canal) numeroDe;
  final ValueChanged<Canal> alElegir;

  /// El del canal que se está viendo: ahí arranca el foco al abrir la guía.
  final FocusNode nodoActual;

  static const _altoFila = 92.0;

  @override
  Widget build(BuildContext context) {
    final indice = lista.indexWhere((c) => c.id == actual.id).clamp(0, lista.length);
    return Positioned(
      left: 0,
      top: 0,
      bottom: 0,
      width: 720,
      child: DecoratedBox(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            colors: [Color(0xF20E0E12), Color(0xD90E0E12), Color(0x000E0E12)],
            stops: [0, .8, 1],
          ),
        ),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(MargenTv.derecha, 120, 60, 0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('GUÍA DE CANALES', style: LetraTv.sobretitulo),
              const SizedBox(height: 14),
              Expanded(
                child: FocusTraversalGroup(
                  child: ListView.builder(
                    controller: ScrollController(initialScrollOffset: (indice - 2).clamp(0, 1 << 20) * _altoFila),
                    clipBehavior: Clip.none,
                    itemExtent: _altoFila,
                    padding: const EdgeInsets.only(bottom: 60, right: 14),
                    itemCount: lista.length,
                    itemBuilder: (context, i) {
                      final canal = lista[i];
                      return Padding(
                        padding: const EdgeInsets.symmetric(vertical: 7),
                        child: FilaCanalTv(
                          canal: canal,
                          numero: numeroDe(canal),
                          nodo: i == indice ? nodoActual : null,
                          enReproduccion: canal.id == actual.id,
                          alOk: () => alElegir(canal),
                        ),
                      );
                    },
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Una fila de la guía: número dorado, logo o iniciales, nombre y categoría.
class FilaCanalTv extends StatelessWidget {
  const FilaCanalTv({
    super.key,
    required this.canal,
    required this.numero,
    required this.alOk,
    this.alOkLargo,
    this.autofocus = false,
    this.enReproduccion = false,
    this.favorito = false,
    this.ayuda,
    this.nodo,
  });

  final Canal canal;
  final String numero;
  final VoidCallback alOk;
  final VoidCallback? alOkLargo;
  final bool autofocus;

  /// Para llevarle el foco desde afuera (ej: al abrir la guía, al canal que se ve).
  final FocusNode? nodo;
  final bool enReproduccion;
  final bool favorito;

  /// A la derecha ("OK · Pantalla completa").
  final String? ayuda;

  @override
  Widget build(BuildContext context) {
    final categoria = categoriaLegible(canal.categoria);
    return Enfocable(
      alOk: alOk,
      alOkLargo: alOkLargo,
      autofocus: autofocus,
      nodo: nodo,
      curva: Curva.boton,
      escala: 1.02,
      etiqueta: 'Canal $numero, ${canal.nombre}',
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 18),
        decoration: BoxDecoration(
          color: enReproduccion ? Tono.celeste.withValues(alpha: .1) : Tono.capa.withValues(alpha: .7),
          borderRadius: BorderRadius.circular(Curva.boton),
        ),
        child: Row(
          children: [
            SizedBox(
              width: 74,
              child: Text(
                numero,
                style: const TextStyle(
                  fontFamily: Letra.texto,
                  fontSize: 20,
                  fontWeight: FontWeight.w800,
                  color: Tono.dorado,
                ),
              ),
            ),
            Container(
              width: 96,
              height: 62,
              decoration: BoxDecoration(color: Tono.capaAlta, borderRadius: BorderRadius.circular(Curva.medio)),
              child: LogoCanalTv(canal: canal, tamanioIniciales: 21, relleno: const EdgeInsets.all(6)),
            ),
            const SizedBox(width: 20),
            Expanded(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Flexible(
                        child: Text(
                          canal.nombre,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontFamily: Letra.texto,
                            fontSize: 20,
                            fontWeight: FontWeight.w700,
                            color: Tono.texto,
                          ),
                        ),
                      ),
                      if (favorito) ...[
                        const SizedBox(width: 10),
                        const Icon(Icons.favorite_rounded, size: 18, color: Tono.rubi),
                      ],
                      if (enReproduccion) ...[
                        const SizedBox(width: 12),
                        const PuntoEnVivo(tamanio: 9, color: Tono.rubi),
                      ],
                    ],
                  ),
                  if (categoria.isNotEmpty) Text(categoria, style: LetraTv.ayuda.copyWith(fontSize: 15)),
                ],
              ),
            ),
            if (ayuda != null) Text(ayuda!, style: LetraTv.ayuda.copyWith(fontSize: 15)),
          ],
        ),
      ),
    );
  }
}

// ── Películas y capítulos ──────────────────────────────────────────

class ReproductorVodTv extends StatefulWidget {
  const ReproductorVodTv({super.key, required this.canal, this.serie, this.episodio, this.desde});

  final Canal canal;
  final Serie? serie;
  final Episodio? episodio;
  final Duration? desde;

  @override
  State<ReproductorVodTv> createState() => _ReproductorVodTvState();
}

class _ReproductorVodTvState extends State<ReproductorVodTv> {
  static const _salto = Duration(seconds: 10);

  late final ControlSenal _control = ControlSenal(SesionScope.leer(context).api)..addListener(_alCambiar);
  late final Biblioteca _biblioteca = DatosScope.of(context).biblioteca;
  // No entra en el recorrido de las flechas: si no, desde un botón de la
  // barra "Derecha" saltaba al video (que ocupa toda la pantalla)
  final _raiz = FocusNode(debugLabel: 'reproductor', skipTraversal: true);
  final _botonPausa = FocusNode(debugLabel: 'pausa');
  final _linea = FocusNode(debugLabel: 'línea de tiempo');
  final _reintentar = FocusNode(debugLabel: 'probar de nuevo');
  late Canal _canal = widget.canal;
  late Episodio? _episodio = widget.episodio;

  /// La barra con los botones y la línea de tiempo (toma el foco).
  bool _controles = false;

  /// El título arriba, al empezar (solo informa: no atrapa "Atrás").
  bool _cartel = true;
  bool _siguienteLanzado = false;
  String? _errorAnterior;
  Timer? _ocultar;
  Timer? _cerrarCartel;
  Timer? _guardar;

  @override
  void initState() {
    super.initState();
    WakelockPlus.enable().catchError((Object _) {});
    _control.abrir(_canal, desde: widget.desde);
    _guardar = Timer.periodic(const Duration(seconds: 5), (_) => _guardarProgreso());
    _esconderCartelDespues();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _raiz.requestFocus();
    });
  }

  @override
  void dispose() {
    _guardarProgreso();
    _ocultar?.cancel();
    _cerrarCartel?.cancel();
    _guardar?.cancel();
    _control.dispose();
    for (final nodo in [_raiz, _botonPausa, _linea, _reintentar]) {
      nodo.dispose();
    }
    WakelockPlus.disable().catchError((Object _) {});
    super.dispose();
  }

  VideoPlayerValue? get _valor => _control.video?.value;

  bool get _reproduciendo => _valor?.isPlaying ?? false;

  void _alCambiar() {
    if (!mounted) return;
    final valor = _valor;
    // Terminó: el capítulo siguiente sigue solo
    if (valor != null &&
        valor.isInitialized &&
        valor.duration > Duration.zero &&
        valor.position >= valor.duration - const Duration(milliseconds: 800) &&
        !_siguienteLanzado) {
      _siguienteLanzado = true;
      _guardarProgreso();
      if (_siguiente != null) _pasarA(_siguiente!);
    }
    // Si falló, el foco va a "Probar de nuevo"
    final error = _control.error;
    if (error != null && error != _errorAnterior) {
      _controles = false;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && _reintentar.context != null) _reintentar.requestFocus();
      });
    }
    _errorAnterior = error;
    setState(() {});
  }

  void _guardarProgreso() {
    final valor = _valor;
    if (valor == null || !valor.isInitialized || valor.duration == Duration.zero) return;
    _biblioteca.guardarProgreso(_canal.id, valor.position, valor.duration);
  }

  Episodio? get _siguiente {
    final serie = widget.serie;
    final actual = _episodio;
    if (serie == null || actual == null) return null;
    final episodios = serie.episodios;
    final indice = episodios.indexOf(actual);
    return indice >= 0 && indice + 1 < episodios.length ? episodios[indice + 1] : null;
  }

  void _pasarA(Episodio episodio) {
    _guardarProgreso();
    setState(() {
      _episodio = episodio;
      _canal = episodio.canal;
      _siguienteLanzado = false;
    });
    final progreso = _biblioteca.progresoDe(episodio.canal.id);
    _control.abrir(episodio.canal, desde: progreso == null || progreso.terminado ? null : progreso.posicion);
    _cerrarControles();
    _mostrarCartel();
  }

  void _mostrarCartel() {
    setState(() => _cartel = true);
    _esconderCartelDespues();
  }

  /// (El cartel arranca visible: al abrir solo hace falta esto.)
  void _esconderCartelDespues() {
    _cerrarCartel?.cancel();
    _cerrarCartel = Timer(_esperaCartel, () {
      if (mounted) setState(() => _cartel = false);
    });
  }

  /// Muestra la barra y le lleva el foco a [nodo] (Pausa, o la línea de tiempo si se está adelantando).
  void _abrirControles(FocusNode nodo) {
    final yaEstaban = _controles;
    setState(() {
      _controles = true;
      _cartel = false;
    });
    if (!yaEstaban) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && _controles) nodo.requestFocus();
      });
    }
    _reiniciarEspera();
  }

  /// Mientras se reproduce, la barra se esconde sola. En pausa queda a la vista.
  void _reiniciarEspera() {
    _ocultar?.cancel();
    _ocultar = Timer(_esperaControles, () {
      if (mounted && _controles && _reproduciendo) _cerrarControles();
    });
  }

  void _cerrarControles() {
    _ocultar?.cancel();
    setState(() => _controles = false);
    (_control.error != null && _reintentar.context != null ? _reintentar : _raiz).requestFocus();
  }

  void _saltar(Duration cuanto) {
    _control.saltar(cuanto);
    _abrirControles(_linea);
  }

  void _pausa() {
    _control.alternarPausa();
    _abrirControles(_botonPausa);
  }

  KeyEventResult _tecla(FocusNode _, KeyEvent evento) {
    if (evento is KeyUpEvent) return KeyEventResult.ignored;
    final tecla = evento.logicalKey;
    // Las teclas de reproducción del control funcionan siempre
    if (tecla == LogicalKeyboardKey.mediaPlayPause ||
        tecla == LogicalKeyboardKey.mediaPlay ||
        tecla == LogicalKeyboardKey.mediaPause) {
      _pausa();
      return KeyEventResult.handled;
    }
    if (tecla == LogicalKeyboardKey.mediaFastForward || tecla == LogicalKeyboardKey.mediaRewind) {
      _saltar(tecla == LogicalKeyboardKey.mediaFastForward ? _salto * 3 : -_salto * 3);
      return KeyEventResult.handled;
    }
    if (_controles) {
      _reiniciarEspera(); // se está usando: no se esconde
      return KeyEventResult.ignored; // las flechas recorren la barra
    }
    // Con el error a la vista, las flechas y OK son de sus botones
    if (_control.error != null && !_raiz.hasPrimaryFocus) return KeyEventResult.ignored;
    if (tecla == LogicalKeyboardKey.arrowLeft || tecla == LogicalKeyboardKey.arrowRight) {
      _saltar(tecla == LogicalKeyboardKey.arrowRight ? _salto : -_salto);
      return KeyEventResult.handled;
    }
    if (teclasOk.contains(tecla)) {
      _pausa();
      return KeyEventResult.handled;
    }
    if (tecla == LogicalKeyboardKey.arrowUp ||
        tecla == LogicalKeyboardKey.arrowDown ||
        tecla == LogicalKeyboardKey.info ||
        tecla == LogicalKeyboardKey.contextMenu) {
      _abrirControles(_botonPausa);
      return KeyEventResult.handled;
    }
    return KeyEventResult.ignored;
  }

  Future<void> _ajustes() async {
    _ocultar?.cancel();
    await ajustesDeVideoTv(context, _control);
    if (mounted) _cerrarControles();
  }

  @override
  Widget build(BuildContext context) {
    final valor = _valor;
    final serie = widget.serie;
    final episodio = _episodio;
    final clave = serie?.clave ?? Biblioteca.claveDe(_canal);
    final favorito = _biblioteca.estaEnMiLista(clave);
    final titulo = serie?.nombre ?? sinAnio(_canal.nombre);
    final subtitulo = episodio == null
        ? 'Película'
        : 'Temporada ${episodio.temporada} · Episodio ${episodio.numero}'
              '${episodio.titulo.isEmpty ? '' : ' · ${episodio.titulo}'}';
    final duracion = valor?.duration ?? Duration.zero;
    final posicion = _control.posicion;
    final siguiente = _siguiente;
    final textoDelTitulo = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(titulo, maxLines: 1, overflow: TextOverflow.ellipsis, style: LetraTv.tarjeta.copyWith(fontSize: 24)),
        Text(
          subtitulo,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: LetraTv.ayuda.copyWith(fontSize: 17, color: Tono.textoSuave),
        ),
      ],
    );

    return PopScope(
      // "Atrás": si la barra está a la vista, la esconde; si no, sale
      canPop: !_controles,
      onPopInvokedWithResult: (salio, _) {
        if (!salio) _cerrarControles();
      },
      child: Scaffold(
        backgroundColor: Colors.black,
        body: Focus(
          focusNode: _raiz,
          onKeyEvent: _tecla,
          child: Stack(
            fit: StackFit.expand,
            children: [
              _Video(control: _control),
              _EstadoSenal(control: _control, alReintentar: _control.reintentar, nodoReintentar: _reintentar),
              if (_controles || _cartel)
                Positioned(
                  top: MargenTv.arriba,
                  left: MargenTv.derecha,
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 9),
                    decoration: BoxDecoration(
                      color: Tono.capaAlta.withValues(alpha: .85),
                      borderRadius: BorderRadius.circular(99),
                      border: Border.all(color: Tono.bordeSuave.withValues(alpha: .6)),
                    ),
                    child: Text(
                      episodio == null ? 'PELÍCULA' : 'T${episodio.temporada} · E${episodio.numero}',
                      style: const TextStyle(
                        fontFamily: Letra.texto,
                        fontSize: 16,
                        fontWeight: FontWeight.w800,
                        letterSpacing: .6,
                        color: Tono.texto,
                      ),
                    ),
                  ),
                ),
              // El cartel del principio: título y cómo se maneja (solo informa)
              if (_cartel && !_controles && _control.error == null)
                Positioned(
                  left: 0,
                  right: 0,
                  bottom: 0,
                  child: _PanelControles(
                    fila: [Expanded(child: textoDelTitulo)],
                    ayuda: 'OK: pausa  ·  ← →: atrasar / adelantar 10 s  ·  ↑ ↓: opciones  ·  Atrás: salir',
                  ),
                ),
              if (_controles)
                Positioned(
                  left: 0,
                  right: 0,
                  bottom: 0,
                  child: _PanelControles(
                    ayuda: '← →: elegir  ·  ↓: línea de tiempo  ·  Atrás: ocultar',
                    alMoverse: _reiniciarEspera,
                    fila: [
                      _BotonCuadrado(
                        icono: _reproduciendo ? Icons.pause_rounded : Icons.play_arrow_rounded,
                        etiqueta: _reproduciendo ? 'Pausa' : 'Seguir',
                        nodo: _botonPausa,
                        alOk: () {
                          _control.alternarPausa();
                          _reiniciarEspera();
                        },
                      ),
                      const SizedBox(width: 20),
                      Expanded(child: textoDelTitulo),
                      if (siguiente != null) ...[
                        _BotonCuadrado(
                          icono: Icons.skip_next_rounded,
                          etiqueta: 'Siguiente episodio',
                          alOk: () => _pasarA(siguiente),
                        ),
                        const SizedBox(width: 18),
                      ],
                      _BotonCuadrado(
                        icono: favorito ? Icons.favorite_rounded : Icons.favorite_border_rounded,
                        color: favorito ? Tono.rubi : null,
                        etiqueta: favorito ? 'Quitar de favoritos' : 'Agregar a favoritos',
                        alOk: () {
                          alternarFavoritoTv(context, clave);
                          _reiniciarEspera();
                        },
                      ),
                      const SizedBox(width: 18),
                      _BotonCuadrado(icono: Icons.settings_rounded, etiqueta: 'Ajustes', alOk: _ajustes),
                    ],
                    debajo: _LineaDeTiempo(
                      nodo: _linea,
                      posicion: posicion,
                      duracion: duracion,
                      alSaltar: (cuanto) {
                        _control.saltar(cuanto);
                        _reiniciarEspera();
                      },
                      alSubir: () {
                        _botonPausa.requestFocus();
                        _reiniciarEspera();
                      },
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

// ── Películas y capítulos de YouTube oficial ───────────────────────

/// Se maneja igual que [ReproductorVodTv] (el cartel al empezar, la barra con
/// Pausa, Siguiente episodio, Favoritos y la línea de tiempo, que se esconde
/// sola), pero el video es el reproductor oficial de YouTube.
///
/// Mientras se ve, encima del video no queda nada dibujado y la pantalla no
/// se redibuja cada segundo (por dónde va lo escucha solo la línea de tiempo,
/// y solo con la barra a la vista): todo lo que se dibuja encima de un video
/// de YouTube le cuesta a la TV.
class ReproductorYoutubeTv extends StatefulWidget {
  const ReproductorYoutubeTv({super.key, required this.canal, this.serie, this.episodio, this.desde});

  final Canal canal;
  final Serie? serie;
  final Episodio? episodio;
  final Duration? desde;

  @override
  State<ReproductorYoutubeTv> createState() => _ReproductorYoutubeTvState();
}

class _ReproductorYoutubeTvState extends State<ReproductorYoutubeTv> {
  static const _salto = Duration(seconds: 10);

  ControlYoutube? _control;
  final _raiz = FocusNode(debugLabel: 'reproductor de YouTube', skipTraversal: true);
  final _botonPausa = FocusNode(debugLabel: 'pausa');
  final _linea = FocusNode(debugLabel: 'línea de tiempo');
  final _reintentar = FocusNode(debugLabel: 'probar de nuevo');

  /// La barra con los botones y la línea de tiempo (toma el foco).
  bool _controles = false;

  /// El título abajo, al empezar (solo informa: no atrapa "Atrás").
  bool _cartel = true;
  bool _habiaError = false;
  Episodio? _episodioDelCartel;
  Timer? _ocultar;
  Timer? _cerrarCartel;

  ControlYoutube get _video => _control!;

  @override
  void initState() {
    super.initState();
    WakelockPlus.enable().catchError((Object _) {});
    _episodioDelCartel = widget.episodio;
    _esconderCartelDespues();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _raiz.requestFocus();
    });
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _control ??=
        ControlYoutube(
            api: SesionScope.leer(context).api,
            biblioteca: DatosScope.of(context).biblioteca,
            canal: widget.canal,
            serie: widget.serie,
            episodio: widget.episodio,
            tv: true,
          )
          ..abrir(desde: widget.desde)
          ..addListener(_alCambiar); // después de abrir: acá todavía no se puede redibujar
  }

  @override
  void dispose() {
    _ocultar?.cancel();
    _cerrarCartel?.cancel();
    _control?.dispose();
    for (final nodo in [_raiz, _botonPausa, _linea, _reintentar]) {
      nodo.dispose();
    }
    WakelockPlus.disable().catchError((Object _) {});
    super.dispose();
  }

  void _alCambiar() {
    if (!mounted) return;
    final estado = _video.estado;
    // Si falló, el foco va a "Probar de nuevo"
    final error = estado.error != null;
    if (error && !_habiaError) {
      _controles = false;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && _reintentar.context != null) _reintentar.requestFocus();
      });
    }
    _habiaError = error;
    // Arrancó (o siguió) con la barra a la vista: que se esconda sola
    if (estado.reproduciendo && _controles && !(_ocultar?.isActive ?? false)) _reiniciarEspera();
    // Pasó solo al capítulo siguiente: el cartel con el título nuevo
    if (_video.episodio != _episodioDelCartel) {
      _episodioDelCartel = _video.episodio;
      _cartel = true;
      _esconderCartelDespues();
    }
    setState(() {});
  }

  void _pasarA(Episodio episodio) {
    _video.pasarA(episodio);
    _cerrarControles();
  }

  void _esconderCartelDespues() {
    _cerrarCartel?.cancel();
    _cerrarCartel = Timer(_esperaCartel, () {
      if (mounted) setState(() => _cartel = false);
    });
  }

  /// Muestra la barra y le lleva el foco a [nodo] (Pausa, o la línea de tiempo si se está adelantando).
  void _abrirControles(FocusNode nodo) {
    final yaEstaban = _controles;
    setState(() {
      _controles = true;
      _cartel = false;
    });
    if (!yaEstaban) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && _controles) nodo.requestFocus();
      });
    }
    _reiniciarEspera();
  }

  /// Mientras se reproduce, la barra se esconde sola. En pausa queda a la vista.
  void _reiniciarEspera() {
    _ocultar?.cancel();
    _ocultar = Timer(_esperaControles, () {
      if (mounted && _controles && _video.estado.reproduciendo) _cerrarControles();
    });
  }

  void _cerrarControles() {
    _ocultar?.cancel();
    setState(() => _controles = false);
    (_video.estado.error != null && _reintentar.context != null ? _reintentar : _raiz).requestFocus();
  }

  void _saltar(Duration cuanto) {
    _video.saltar(cuanto);
    _abrirControles(_linea);
  }

  void _pausa() {
    _video.alternarPausa();
    _abrirControles(_botonPausa);
  }

  KeyEventResult _tecla(FocusNode _, KeyEvent evento) {
    if (evento is KeyUpEvent) return KeyEventResult.ignored;
    final tecla = evento.logicalKey;
    // Las teclas de reproducción del control funcionan siempre
    if (tecla == LogicalKeyboardKey.mediaPlayPause ||
        tecla == LogicalKeyboardKey.mediaPlay ||
        tecla == LogicalKeyboardKey.mediaPause) {
      _pausa();
      return KeyEventResult.handled;
    }
    if (tecla == LogicalKeyboardKey.mediaFastForward || tecla == LogicalKeyboardKey.mediaRewind) {
      _saltar(tecla == LogicalKeyboardKey.mediaFastForward ? _salto * 3 : -_salto * 3);
      return KeyEventResult.handled;
    }
    if (_controles) {
      _reiniciarEspera(); // se está usando: no se esconde
      return KeyEventResult.ignored; // las flechas recorren la barra
    }
    // Con el error a la vista, las flechas y OK son de sus botones
    if (_video.estado.error != null && !_raiz.hasPrimaryFocus) return KeyEventResult.ignored;
    if (tecla == LogicalKeyboardKey.arrowLeft || tecla == LogicalKeyboardKey.arrowRight) {
      _saltar(tecla == LogicalKeyboardKey.arrowRight ? _salto : -_salto);
      return KeyEventResult.handled;
    }
    if (teclasOk.contains(tecla)) {
      _pausa();
      return KeyEventResult.handled;
    }
    if (tecla == LogicalKeyboardKey.arrowUp ||
        tecla == LogicalKeyboardKey.arrowDown ||
        tecla == LogicalKeyboardKey.info ||
        tecla == LogicalKeyboardKey.contextMenu) {
      _abrirControles(_botonPausa);
      return KeyEventResult.handled;
    }
    return KeyEventResult.ignored;
  }

  @override
  Widget build(BuildContext context) {
    final video = _video;
    final estado = video.estado;
    final serie = widget.serie;
    final episodio = video.episodio;
    final clave = serie?.clave ?? Biblioteca.claveDe(video.canal);
    final favorito = video.biblioteca.estaEnMiLista(clave);
    final titulo = serie?.nombre ?? sinAnio(video.canal.nombre);
    final subtitulo = episodio == null
        ? 'Película'
        : 'Temporada ${episodio.temporada} · Episodio ${episodio.numero}'
              '${episodio.titulo.isEmpty ? '' : ' · ${episodio.titulo}'}';
    final siguiente = video.siguiente;
    final error = estado.error;
    final textoDelTitulo = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(titulo, maxLines: 1, overflow: TextOverflow.ellipsis, style: LetraTv.tarjeta.copyWith(fontSize: 24)),
        Text(
          subtitulo,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: LetraTv.ayuda.copyWith(fontSize: 17, color: Tono.textoSuave),
        ),
      ],
    );

    return PopScope(
      // "Atrás": si la barra está a la vista, la esconde; si no, sale
      canPop: !_controles,
      onPopInvokedWithResult: (salio, _) {
        if (!salio) _cerrarControles();
      },
      child: Scaffold(
        backgroundColor: Colors.black,
        body: Focus(
          focusNode: _raiz,
          onKeyEvent: _tecla,
          child: Stack(
            fit: StackFit.expand,
            children: [
              VistaYoutube(control: video),
              if (error == null && !estado.listo) const _CargandoYoutube(),
              if (error != null)
                _FallaYoutubeTv(
                  mensaje: EstadoYoutube.mensajeDe(error),
                  nodo: _reintentar,
                  alReintentar: video.reintentar,
                ),
              if (_controles || _cartel)
                Positioned(
                  top: MargenTv.arriba,
                  left: MargenTv.derecha,
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 9),
                    decoration: BoxDecoration(
                      color: Tono.capaAlta.withValues(alpha: .85),
                      borderRadius: BorderRadius.circular(99),
                      border: Border.all(color: Tono.bordeSuave.withValues(alpha: .6)),
                    ),
                    child: Text(
                      episodio == null ? 'PELÍCULA' : 'T${episodio.temporada} · E${episodio.numero}',
                      style: const TextStyle(
                        fontFamily: Letra.texto,
                        fontSize: 16,
                        fontWeight: FontWeight.w800,
                        letterSpacing: .6,
                        color: Tono.texto,
                      ),
                    ),
                  ),
                ),
              // El cartel del principio: título y cómo se maneja (solo informa)
              if (_cartel && !_controles && error == null)
                Positioned(
                  left: 0,
                  right: 0,
                  bottom: 0,
                  child: _PanelControles(
                    fila: [Expanded(child: textoDelTitulo)],
                    ayuda: 'OK: pausa  ·  ← →: atrasar / adelantar 10 s  ·  ↑ ↓: opciones  ·  Atrás: salir',
                  ),
                ),
              if (_controles)
                Positioned(
                  left: 0,
                  right: 0,
                  bottom: 0,
                  child: _PanelControles(
                    ayuda: '← →: elegir  ·  ↓: línea de tiempo  ·  Atrás: ocultar',
                    alMoverse: _reiniciarEspera,
                    fila: [
                      _BotonCuadrado(
                        icono: estado.reproduciendo ? Icons.pause_rounded : Icons.play_arrow_rounded,
                        etiqueta: estado.reproduciendo ? 'Pausa' : 'Seguir',
                        nodo: _botonPausa,
                        alOk: () {
                          video.alternarPausa();
                          _reiniciarEspera();
                        },
                      ),
                      const SizedBox(width: 20),
                      Expanded(child: textoDelTitulo),
                      if (siguiente != null && fuenteDeYoutube(siguiente.canal) != null) ...[
                        _BotonCuadrado(
                          icono: Icons.skip_next_rounded,
                          etiqueta: 'Siguiente episodio',
                          alOk: () => _pasarA(siguiente),
                        ),
                        const SizedBox(width: 18),
                      ],
                      if (estado.audios.length > 1) ...[
                        _BotonCuadrado(
                          icono: Icons.record_voice_over_rounded,
                          etiqueta: 'Idioma: ${estado.nombreDelAudio.isEmpty ? 'cambiar' : estado.nombreDelAudio}',
                          alOk: () {
                            video.cambiarAudio();
                            _reiniciarEspera();
                          },
                        ),
                        const SizedBox(width: 18),
                      ],
                      _BotonCuadrado(
                        icono: estado.subtitulos.isEmpty
                            ? Icons.closed_caption_off_outlined
                            : Icons.closed_caption_rounded,
                        etiqueta: switch ((estado.haySubtitulos, estado.subtitulos)) {
                          (false, _) => 'Este video no tiene subtítulos',
                          (_, '') => 'Subtítulos: no',
                          (_, final idioma) => 'Subtítulos: $idioma',
                        },
                        alOk: () {
                          video.cambiarSubtitulos();
                          _reiniciarEspera();
                        },
                      ),
                      const SizedBox(width: 18),
                      _BotonCuadrado(
                        icono: favorito ? Icons.favorite_rounded : Icons.favorite_border_rounded,
                        color: favorito ? Tono.rubi : null,
                        etiqueta: favorito ? 'Quitar de favoritos' : 'Agregar a favoritos',
                        alOk: () {
                          alternarFavoritoTv(context, clave);
                          _reiniciarEspera();
                          setState(() {});
                        },
                      ),
                    ],
                    // Por dónde va: lo único que se redibuja cada segundo, y solo con la barra a la vista
                    debajo: ValueListenableBuilder<Duration>(
                      valueListenable: estado.avance,
                      builder: (context, posicion, _) => _LineaDeTiempo(
                        nodo: _linea,
                        posicion: posicion,
                        duracion: estado.duracion,
                        alSaltar: (cuanto) {
                          video.saltar(cuanto);
                          _reiniciarEspera();
                        },
                        alSubir: () {
                          _botonPausa.requestFocus();
                          _reiniciarEspera();
                        },
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Mientras YouTube carga (se saca apenas arranca: una animación encima del video también cuesta).
class _CargandoYoutube extends StatelessWidget {
  const _CargandoYoutube();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const SizedBox(width: 64, height: 64, child: CircularProgressIndicator(strokeWidth: 5, color: Tono.celeste)),
          const SizedBox(height: 22),
          Text('Conectando con YouTube…', style: LetraTv.cuerpo.copyWith(color: Tono.texto)),
        ],
      ),
    );
  }
}

/// YouTube no lo dejó ver (o no cargó): el motivo y "Probar de nuevo".
class _FallaYoutubeTv extends StatelessWidget {
  const _FallaYoutubeTv({required this.mensaje, required this.nodo, required this.alReintentar});

  final String mensaje;
  final FocusNode nodo;
  final VoidCallback alReintentar;

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: Colors.black,
      child: Center(
        child: Container(
          width: 820,
          padding: const EdgeInsets.all(48),
          decoration: BoxDecoration(
            color: Tono.capaBaja.withValues(alpha: .95),
            borderRadius: BorderRadius.circular(Curva.portada),
            border: Border.all(color: Tono.rubi.withValues(alpha: .5)),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline_rounded, size: 56, color: Tono.rubiClaro),
              const SizedBox(height: 18),
              const Text('Esto no está disponible ahora', textAlign: TextAlign.center, style: LetraTv.pantalla),
              const SizedBox(height: 10),
              Text(mensaje, textAlign: TextAlign.center, style: LetraTv.cuerpo),
              const SizedBox(height: 30),
              BotonTv(
                texto: 'Probar de nuevo',
                icono: Icons.refresh_rounded,
                principal: true,
                autofocus: true,
                nodo: nodo,
                alOk: alReintentar,
              ),
              const SizedBox(height: 14),
              const Text('Atrás: volver', style: LetraTv.ayuda),
            ],
          ),
        ),
      ),
    );
  }
}

// La línea de tiempo: con el foco, Izquierda/Derecha mueven ±10 s.
class _LineaDeTiempo extends StatelessWidget {
  const _LineaDeTiempo({
    required this.posicion,
    required this.duracion,
    required this.alSaltar,
    required this.alSubir,
    this.nodo,
  });

  final Duration posicion;
  final Duration duracion;
  final ValueChanged<Duration> alSaltar;

  /// Arriba: a los botones (el reproductor lo lleva a Pausa).
  final VoidCallback alSubir;
  final FocusNode? nodo;

  @override
  Widget build(BuildContext context) {
    final fraccion = duracion.inMilliseconds == 0
        ? 0.0
        : (posicion.inMilliseconds / duracion.inMilliseconds).clamp(0.0, 1.0);
    return Column(
      children: [
        Enfocable(
          nodo: nodo,
          curva: 99,
          escala: 1.0,
          etiqueta: 'Línea de tiempo: ${reloj(posicion)} de ${reloj(duracion)}',
          alTecla: (evento) {
            if (evento is KeyUpEvent) return KeyEventResult.ignored;
            if (evento.logicalKey == LogicalKeyboardKey.arrowLeft) {
              alSaltar(const Duration(seconds: -10));
              return KeyEventResult.handled;
            }
            if (evento.logicalKey == LogicalKeyboardKey.arrowRight) {
              alSaltar(const Duration(seconds: 10));
              return KeyEventResult.handled;
            }
            if (evento.logicalKey == LogicalKeyboardKey.arrowUp) {
              alSubir();
              return KeyEventResult.handled;
            }
            return KeyEventResult.ignored;
          },
          child: SizedBox(
            height: 26,
            child: LayoutBuilder(
              builder: (context, limites) => Stack(
                alignment: Alignment.centerLeft,
                children: [
                  Container(
                    height: 8,
                    decoration: BoxDecoration(color: Tono.capaMaxima, borderRadius: BorderRadius.circular(99)),
                  ),
                  Container(
                    height: 8,
                    width: limites.maxWidth * fraccion,
                    decoration: BoxDecoration(
                      color: Tono.celeste,
                      borderRadius: BorderRadius.circular(99),
                      boxShadow: brilloCeleste(desenfoque: 10, opacidad: .6),
                    ),
                  ),
                  Positioned(
                    left: (limites.maxWidth * fraccion - 11).clamp(0, limites.maxWidth - 22),
                    child: Container(
                      width: 22,
                      height: 22,
                      decoration: BoxDecoration(
                        color: Tono.celesteClaro,
                        shape: BoxShape.circle,
                        boxShadow: brilloCeleste(desenfoque: 14, opacidad: .8),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
        const SizedBox(height: 10),
        Row(
          children: [
            Text(reloj(posicion), style: _estiloTiempo),
            const Spacer(),
            Text(duracion == Duration.zero ? '--:--' : reloj(duracion), style: _estiloTiempo),
          ],
        ),
      ],
    );
  }

  static const _estiloTiempo = TextStyle(
    fontFamily: Letra.texto,
    fontSize: 15,
    fontWeight: FontWeight.w700,
    color: Tono.texto,
    fontFeatures: [FontFeature.tabularFigures()],
  );
}

// ── Piezas compartidas ─────────────────────────────────────────────

class _Video extends StatelessWidget {
  const _Video({required this.control});

  final ControlSenal control;

  @override
  Widget build(BuildContext context) {
    final video = control.video;
    if (video == null || !video.value.isInitialized) return const SizedBox.expand();
    final canal = control.canal;
    // Sin imagen (una radio): su logo grande mientras suena
    if (video.value.size.height == 0 && canal != null) {
      return Imagen(
        url: canal.logo,
        nombre: canal.nombre,
        ajuste: BoxFit.contain,
        relleno: const EdgeInsets.symmetric(horizontal: 560, vertical: 300),
        fondo: Tono.fondo,
        tamanioIniciales: 120,
      );
    }
    return VideoAjustado(video: video, ajuste: ControlSenal.ajuste);
  }
}

/// Cargando, "probando otra señal…" o el error con "Probar de nuevo" (tv-19).
class _EstadoSenal extends StatelessWidget {
  const _EstadoSenal({required this.control, required this.alReintentar, this.alGuia, this.nodoReintentar});

  final ControlSenal control;
  final VoidCallback alReintentar;
  final VoidCallback? alGuia;

  /// El de "Probar de nuevo": el reproductor le lleva el foco cuando aparece el error.
  final FocusNode? nodoReintentar;

  @override
  Widget build(BuildContext context) {
    final error = control.error;
    if (error != null) {
      return Center(
        child: Container(
          width: 820,
          padding: const EdgeInsets.all(48),
          decoration: BoxDecoration(
            color: Tono.capaBaja.withValues(alpha: .95),
            borderRadius: BorderRadius.circular(Curva.portada),
            border: Border.all(color: Tono.rubi.withValues(alpha: .5)),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.signal_wifi_connected_no_internet_4_rounded, size: 56, color: Tono.rubiClaro),
              const SizedBox(height: 18),
              const Text('Esto no está disponible ahora', textAlign: TextAlign.center, style: LetraTv.pantalla),
              const SizedBox(height: 10),
              Text(error, textAlign: TextAlign.center, style: LetraTv.cuerpo),
              // Varios canales seguidos sin andar: casi siempre es la TV (ver ControlSenal.canalesSinAndar)
              if (control.sugerirReiniciarAparato) ...[
                const SizedBox(height: 14),
                const Text(
                  'Si varios canales no andan o se ven en verde, desenchufá la TV 30 segundos y volvé a abrir '
                  'Kairos TV: algunos televisores lo necesitan después de muchos días encendidos.',
                  textAlign: TextAlign.center,
                  style: LetraTv.ayuda,
                ),
              ],
              const SizedBox(height: 30),
              FocusTraversalGroup(
                child: Wrap(
                  spacing: 18,
                  children: [
                    BotonTv(
                      texto: 'Probar de nuevo',
                      icono: Icons.refresh_rounded,
                      principal: true,
                      autofocus: true,
                      nodo: nodoReintentar,
                      alOk: alReintentar,
                    ),
                    if (alGuia != null) BotonTv(texto: 'Ver la guía', icono: Icons.view_list_rounded, alOk: alGuia),
                  ],
                ),
              ),
            ],
          ),
        ),
      );
    }
    if (!control.cargando) return const SizedBox.shrink();
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const SizedBox(width: 64, height: 64, child: CircularProgressIndicator(strokeWidth: 5, color: Tono.celeste)),
          const SizedBox(height: 22),
          Text(
            control.fuente > 0 ? 'Esta señal no responde. Probando otra señal…' : 'Conectando…',
            style: LetraTv.cuerpo.copyWith(color: Tono.texto),
          ),
          // Si una película tarda: que es el servidor y que la app sigue intentando (no se colgó)
          const SizedBox(height: 12),
          EsperaLarga(control: control, estilo: LetraTv.ayuda, ancho: 640),
        ],
      ),
    );
  }
}

/// La barra de abajo del reproductor: un degradé que sube desde el borde
/// (el video se sigue viendo arriba), la fila de controles, lo que vaya
/// debajo (la línea de tiempo) y la ayuda de las teclas como teclas
/// dibujadas. Ocupa todo el ancho de la pantalla.
class _PanelControles extends StatelessWidget {
  const _PanelControles({required this.fila, this.debajo, this.ayuda, this.alMoverse});

  final List<Widget> fila;
  final Widget? debajo;

  /// 'OK: guía  ·  ↑ ↓ cambiar de canal  ·  Atrás: salir' (ver [_AyudaDeTeclas]).
  final String? ayuda;

  /// Avisa que se movió por la fila (para que la barra no se esconda mientras se usa).
  final VoidCallback? alMoverse;

  /// Izquierda/Derecha en la fila: al botón de al lado, en el orden en que se
  /// ven. Sin esto Flutter elegía "el más cercano" mirando toda la barra, y a
  /// veces saltaba a otro lado. En los bordes se queda (no se escapa de la fila).
  KeyEventResult _moverEnLaFila(FocusNode fila, KeyEvent evento) {
    final tecla = evento.logicalKey;
    if (evento is KeyUpEvent || (tecla != LogicalKeyboardKey.arrowLeft && tecla != LogicalKeyboardKey.arrowRight)) {
      return KeyEventResult.ignored;
    }
    final botones = fila.traversalDescendants.where((n) => n.canRequestFocus && n.context != null).toList()
      ..sort((a, b) => a.rect.left.compareTo(b.rect.left));
    final actual = botones.indexWhere((n) => n.hasPrimaryFocus);
    if (actual < 0) return KeyEventResult.ignored;
    final otro = actual + (tecla == LogicalKeyboardKey.arrowRight ? 1 : -1);
    if (otro >= 0 && otro < botones.length) botones[otro].requestFocus();
    alMoverse?.call();
    return KeyEventResult.handled;
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(MargenTv.derecha, 150, MargenTv.derecha, MargenTv.abajo),
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Color(0x0007090C), Color(0xA607090C), Color(0xEB07090C)],
          stops: [0, .42, 1],
        ),
      ),
      child: FocusTraversalGroup(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Focus(
              canRequestFocus: false,
              skipTraversal: true,
              onKeyEvent: _moverEnLaFila,
              child: Row(children: fila),
            ),
            if (debajo != null) ...[const SizedBox(height: 26), debajo!],
            if (ayuda != null) ...[
              const SizedBox(height: 22),
              // Una línea fina celeste que se apaga hacia los costados separa la ayuda
              Container(
                height: 1,
                margin: const EdgeInsets.only(bottom: 16),
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    colors: [Tono.celeste.withValues(alpha: .55), Tono.celeste.withValues(alpha: 0)],
                  ),
                ),
              ),
              _AyudaDeTeclas(ayuda!),
            ],
          ],
        ),
      ),
    );
  }
}

/// La ayuda de las teclas, con cada tecla dibujada: [OK] guía   [↑ ↓] cambiar de canal ...
/// Lee el texto de siempre: partes separadas por '·'; en cada parte, la
/// tecla va antes de ':' (o son las flechas del principio).
class _AyudaDeTeclas extends StatelessWidget {
  const _AyudaDeTeclas(this.texto);

  final String texto;

  static (String, String) separar(String parte) {
    final dosPuntos = parte.indexOf(':');
    if (dosPuntos > 0) return (parte.substring(0, dosPuntos).trim(), parte.substring(dosPuntos + 1).trim());
    final flechas = RegExp(r'^([←→↑↓ ]+)').firstMatch(parte);
    if (flechas != null) return (flechas.group(1)!.trim(), parte.substring(flechas.end).trim());
    return ('', parte.trim());
  }

  @override
  Widget build(BuildContext context) {
    final partes = texto.split('·').map((p) => p.trim()).where((p) => p.isNotEmpty);
    return Wrap(
      spacing: 30,
      runSpacing: 10,
      children: [
        for (final parte in partes)
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (separar(parte).$1.isNotEmpty) ...[
                Container(
                  constraints: const BoxConstraints(minWidth: 34),
                  padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 3),
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: .08),
                    borderRadius: BorderRadius.circular(7),
                    border: Border.all(color: Colors.white.withValues(alpha: .28)),
                  ),
                  child: Text(
                    separar(parte).$1,
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                      fontFamily: Letra.texto,
                      fontSize: 14,
                      fontWeight: FontWeight.w800,
                      color: Tono.texto,
                    ),
                  ),
                ),
                const SizedBox(width: 9),
              ],
              Text(separar(parte).$2, style: LetraTv.ayuda.copyWith(fontSize: 16, color: Tono.textoSuave)),
            ],
          ),
      ],
    );
  }
}

/// Una insignia chica: 'CANAL 12' (dorada), 'FULL HD', '4:3', 'SEÑAL 2/3'.
class _Insignia extends StatelessWidget {
  const _Insignia(this.texto, {this.destacada = false});

  final String texto;
  final bool destacada;

  @override
  Widget build(BuildContext context) {
    final color = destacada ? Tono.dorado : Tono.textoSuave;
    return Container(
      margin: const EdgeInsets.only(right: 12),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: .1),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: color.withValues(alpha: .45)),
      ),
      child: Text(
        texto,
        style: TextStyle(
          fontFamily: Letra.texto,
          fontSize: 13,
          fontWeight: FontWeight.w800,
          letterSpacing: .8,
          color: color,
        ),
      ),
    );
  }
}

/// Lo que se sabe de la señal que se está viendo: la calidad ('FULL HD'),
/// si es "cuadrada" ('4:3') y, si el canal tiene varias, cuál es ('SEÑAL 2/3').
List<String> _insigniasDeLaSenal(ControlSenal control) {
  final tamanio = control.video?.value.size ?? Size.zero;
  final cuantas = control.fuentes.length;
  return [
    if (tamanio.height > 0)
      switch (tamanio.height) {
        >= 2000 => '4K',
        >= 1000 => 'FULL HD',
        >= 700 => 'HD',
        _ => 'SD',
      },
    if (tamanio.height > 0 && tamanio.width / tamanio.height < 1.5) '4:3',
    if (cuantas > 1) 'SEÑAL ${control.fuente + 1}/$cuantas',
  ];
}

/// Un botón de la barra: redondo con su ícono; con el foco se llena de
/// celeste y se abre para mostrar qué hace ("Agregar a favoritos").
class _BotonCuadrado extends StatefulWidget {
  const _BotonCuadrado({required this.icono, required this.etiqueta, required this.alOk, this.color, this.nodo});

  final IconData icono;
  final String etiqueta;
  final VoidCallback alOk;
  final Color? color;

  /// Para llevarle el foco al abrir la barra (el reproductor lo pide explícitamente).
  final FocusNode? nodo;

  @override
  State<_BotonCuadrado> createState() => _BotonCuadradoState();
}

class _BotonCuadradoState extends State<_BotonCuadrado> {
  bool _enfocado = false;

  @override
  Widget build(BuildContext context) {
    const alto = 64.0;
    final sobreCeleste = Tono.sobreCelesteOscuro;
    return Enfocable(
      alOk: widget.alOk,
      nodo: widget.nodo,
      curva: alto / 2,
      escala: 1.0,
      etiqueta: widget.etiqueta,
      alEnfocar: (enfocado) => setState(() => _enfocado = enfocado),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 160),
        curve: Curves.easeOut,
        height: alto,
        padding: EdgeInsets.symmetric(horizontal: _enfocado ? 22 : 0),
        constraints: const BoxConstraints(minWidth: alto),
        decoration: BoxDecoration(
          color: _enfocado ? Tono.celeste : Colors.white.withValues(alpha: .1),
          borderRadius: BorderRadius.circular(alto / 2),
          border: Border.all(color: Colors.white.withValues(alpha: _enfocado ? 0 : .22)),
        ),
        child: AnimatedSize(
          duration: const Duration(milliseconds: 160),
          curve: Curves.easeOut,
          child: Row(
            mainAxisSize: MainAxisSize.min,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(widget.icono, size: 30, color: _enfocado ? sobreCeleste : (widget.color ?? Tono.texto)),
              if (_enfocado) ...[
                const SizedBox(width: 10),
                Text(
                  widget.etiqueta,
                  style: TextStyle(
                    fontFamily: Letra.texto,
                    fontSize: 18,
                    fontWeight: FontWeight.w800,
                    color: sobreCeleste,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

/// Los ajustes del video (movil/ajustes_video.dart), con el control remoto:
/// una fila por ajuste (Calidad, Idioma, Imagen, Fuente). Arriba/Abajo pasan
/// de fila, Izquierda/Derecha recorren las opciones y OK elige (se aplica en
/// el momento y el cuadro queda abierto). Atrás lo cierra.
Future<void> ajustesDeVideoTv(BuildContext context, ControlSenal control) async {
  final opciones = await OpcionesDeVideo.de(control);
  if (!context.mounted) return;
  await showDialog<void>(
    context: context,
    builder: (contexto) => ListenableBuilder(
      listenable: control,
      builder: (contexto, _) => _AjustesTv(control: control, opciones: opciones),
    ),
  );
}

/// Una opción de los ajustes: el texto, si es la que está puesta y qué hace.
typedef _Opcion = ({String texto, bool elegida, VoidCallback alOk});

class _AjustesTv extends StatelessWidget {
  const _AjustesTv({required this.control, required this.opciones});

  final ControlSenal control;
  final OpcionesDeVideo opciones;

  @override
  Widget build(BuildContext context) {
    final idiomaActual = control.idiomaElegido;
    final filas = <(String, List<_Opcion>)>[
      if (opciones.calidades.length > 1)
        (
          'Calidad',
          [
            (texto: 'Automática', elegida: control.calidadElegida == null, alOk: () => control.elegirCalidad(null)),
            for (final calidad in opciones.calidades)
              (
                texto: [calidad.nombre, if (calidad.detalle.isNotEmpty) calidad.detalle].join(' · '),
                elegida: control.calidadElegida == calidad.pista.id,
                alOk: () => control.elegirCalidad(calidad),
              ),
          ],
        ),
      if (opciones.idiomas.length > 1)
        (
          'Idioma',
          [
            for (final (idioma, nombre) in Idioma.conNombres(opciones.idiomas))
              (
                texto: nombre,
                elegida: idiomaActual == idioma.pista.id || (idiomaActual == null && idioma.pista.isSelected),
                alOk: () => control.elegirIdioma(idioma.pista.id),
              ),
          ],
        ),
      (
        'Imagen',
        [
          for (final ajuste in AjusteImagen.values)
            (texto: ajuste.nombre, elegida: ControlSenal.ajuste == ajuste, alOk: () => control.cambiarAjuste(ajuste)),
        ],
      ),
      if (control.fuentes.length > 1)
        (
          'Fuente',
          [
            for (final (i, _) in control.fuentes.indexed)
              (
                texto: 'Fuente ${i + 1}',
                elegida: i == control.fuente,
                alOk: () {
                  if (i != control.fuente) control.usarFuente(i);
                  Navigator.pop(context);
                },
              ),
          ],
        ),
    ];
    return DialogoTv(
      icono: Icons.settings_rounded,
      titulo: 'Ajustes',
      botones: const [],
      hijo: FocusTraversalGroup(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (final (i, (nombre, opciones)) in filas.indexed) ...[
              if (i > 0) const SizedBox(height: 22),
              Text(nombre.toUpperCase(), style: LetraTv.sobretitulo),
              const SizedBox(height: 10),
              SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                clipBehavior: Clip.none,
                child: Row(
                  children: [
                    for (final (j, opcion) in opciones.indexed) ...[
                      if (j > 0) const SizedBox(width: 12),
                      BotonTv(
                        texto: opcion.texto,
                        icono: opcion.elegida ? Icons.check_rounded : null,
                        principal: opcion.elegida,
                        autofocus: i == 0 && opcion.elegida,
                        alto: 52,
                        tamanioTexto: 16,
                        alOk: opcion.alOk,
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
