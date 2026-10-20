/// Reproductor de películas y capítulos (Stitch: "(3)", celular).
///
///   video 16:9 con -10 s · pausa · +10 s · barra para adelantar con los
///   tiempos · botonera (velocidad, fuente, siguiente capítulo, girar) ·
///   capítulos de la temporada (o más para ver)
///
/// "Girar" lo pasa a pantalla completa horizontal. Cada 5 segundos se guarda
/// por dónde va (para "Continuar viendo"); al terminar un capítulo sigue
/// solo con el próximo.
library;

import 'dart:async';
import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:video_player/video_player.dart';
import 'package:wakelock_plus/wakelock_plus.dart';

import '../api/modelos.dart';
import '../sesion.dart';
import '../marca.dart';
import '../widgets/espera_larga.dart';
import 'ajustes_video.dart';
import 'componentes.dart';
import 'control_senal.dart';
import 'datos.dart';
import 'detalle.dart';
import 'estilo.dart';
import 'reproductor_youtube.dart';

/// Reproduce una película (si quedó a medias, sigue desde ahí). Las de
/// YouTube oficial, en el reproductor de YouTube (reproductor_youtube.dart).
void reproducirPelicula(BuildContext context, Canal pelicula, {Duration? desde}) {
  final dondeQuedo = desde ?? _dondeQuedo(context, pelicula);
  abrirPantalla<void>(
    context,
    fuenteDeYoutube(pelicula) != null
        ? PantallaYoutube(canal: pelicula, desde: dondeQuedo)
        : PantallaReproductorVod(canal: pelicula, desde: dondeQuedo),
  );
}

/// Reproduce una serie por el capítulo que corresponde (el que quedó a medias o el siguiente).
void reproducirSerie(BuildContext context, Serie serie) {
  final episodio = proximoEpisodio(serie, DatosScope.of(context).biblioteca);
  reproducirEpisodio(context, serie, episodio);
}

void reproducirEpisodio(BuildContext context, Serie serie, Episodio episodio, {Duration? desde}) {
  final dondeQuedo = desde ?? _dondeQuedo(context, episodio.canal);
  abrirPantalla<void>(
    context,
    fuenteDeYoutube(episodio.canal) != null
        ? PantallaYoutube(canal: episodio.canal, serie: serie, episodio: episodio, desde: dondeQuedo)
        : PantallaReproductorVod(canal: episodio.canal, serie: serie, episodio: episodio, desde: dondeQuedo),
  );
}

Duration? _dondeQuedo(BuildContext context, Canal canal) {
  final progreso = DatosScope.of(context).biblioteca.progresoDe(canal.id);
  return progreso == null || progreso.terminado ? null : progreso.posicion;
}

class PantallaReproductorVod extends StatefulWidget {
  const PantallaReproductorVod({super.key, required this.canal, this.serie, this.episodio, this.desde});

  final Canal canal;
  final Serie? serie;
  final Episodio? episodio;
  final Duration? desde;

  @override
  State<PantallaReproductorVod> createState() => _PantallaReproductorVodState();
}

class _PantallaReproductorVodState extends State<PantallaReproductorVod> {
  static const _velocidades = [1.0, 1.25, 1.5, 2.0, 0.75];

  late final ControlSenal _control = ControlSenal(SesionScope.leer(context).api)..addListener(_alCambiar);
  late Biblioteca _biblioteca;
  late Canal _canal = widget.canal;
  late Episodio? _episodio = widget.episodio;
  bool _controles = true;
  bool _pantallaCompleta = false;
  int _velocidad = 0;
  bool _siguienteLanzado = false;
  Timer? _ocultar;
  Timer? _guardar;

  /// Mientras se arrastra la barra: hasta dónde (0 a 1).
  double? _arrastre;

  @override
  void initState() {
    super.initState();
    WakelockPlus.enable();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _biblioteca = DatosScope.of(context).biblioteca;
      _control.abrir(_canal, desde: widget.desde);
    });
    _guardar = Timer.periodic(const Duration(seconds: 5), (_) => _guardarProgreso());
  }

  @override
  void dispose() {
    _guardarProgreso();
    _ocultar?.cancel();
    _guardar?.cancel();
    _control.dispose();
    WakelockPlus.disable();
    SystemChrome.setPreferredOrientations([]);
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
    super.dispose();
  }

  VideoPlayerValue? get _valor => _control.video?.value;

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
    setState(() {});
  }

  void _guardarProgreso() {
    final valor = _valor;
    if (valor == null || !valor.isInitialized || valor.duration == Duration.zero) return;
    try {
      _biblioteca.guardarProgreso(_canal.id, valor.position, valor.duration);
    } catch (_) {
      // Todavía no estaba lista la biblioteca
    }
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
  }

  void _mostrarControles() {
    setState(() => _controles = true);
    _ocultar?.cancel();
    _ocultar = Timer(const Duration(seconds: 4), () {
      if (mounted && (_valor?.isPlaying ?? false)) setState(() => _controles = false);
    });
  }

  void _alternarPantallaCompleta() {
    setState(() => _pantallaCompleta = !_pantallaCompleta);
    if (_pantallaCompleta) {
      SystemChrome.setPreferredOrientations([DeviceOrientation.landscapeLeft, DeviceOrientation.landscapeRight]);
      SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);
    } else {
      SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
      SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
      // Después de volver, que el celular pueda girar libre otra vez
      Future<void>.delayed(const Duration(seconds: 1), () => SystemChrome.setPreferredOrientations([]));
    }
    _mostrarControles();
  }

  void _cambiarVelocidad() {
    setState(() => _velocidad = (_velocidad + 1) % _velocidades.length);
    _control.video?.setPlaybackSpeed(_velocidades[_velocidad]);
  }

  Future<void> _ajustes() => ajustesDeVideoMovil(context, _control);

  String get _titulo => widget.serie?.nombre ?? sinAnio(_canal.nombre);

  String get _subtitulo {
    final episodio = _episodio;
    if (episodio == null) return anioDe(_canal.nombre)?.toString() ?? 'Película';
    return '${episodio.codigo}${episodio.titulo.isEmpty ? '' : ' "${episodio.titulo}"'}';
  }

  @override
  Widget build(BuildContext context) {
    if (_pantallaCompleta) {
      return PopScope(
        canPop: false,
        onPopInvokedWithResult: (_, _) => _alternarPantallaCompleta(),
        child: Scaffold(
          backgroundColor: Colors.black,
          body: _Video(
            control: _control,
            controles: _controles,
            titulo: _titulo,
            subtitulo: _subtitulo,
            pantallaCompleta: true,
            alTocar: () => _controles ? setState(() => _controles = false) : _mostrarControles(),
            alVolver: _alternarPantallaCompleta,
            alAjustes: _ajustes,
            alMostrarControles: _mostrarControles,
            barra: _barra(compacta: true),
          ),
        ),
      );
    }

    return Scaffold(
      backgroundColor: Tono.fondo,
      appBar: _BarraReproductor(titulo: _titulo),
      body: ListView(
        padding: EdgeInsets.only(bottom: MediaQuery.paddingOf(context).bottom + Espacio.xl),
        children: [
          AspectRatio(
            aspectRatio: 16 / 9,
            child: _Video(
              control: _control,
              controles: _controles,
              titulo: _titulo,
              subtitulo: _subtitulo,
              pantallaCompleta: false,
              alTocar: () => _controles ? setState(() => _controles = false) : _mostrarControles(),
              alVolver: () => Navigator.maybePop(context),
              alAjustes: _ajustes,
              alMostrarControles: _mostrarControles,
            ),
          ),
          ColoredBox(
            color: Tono.capaMinima,
            child: Column(
              children: [
                Padding(padding: const EdgeInsets.fromLTRB(Espacio.margen, 12, Espacio.margen, 0), child: _barra()),
                Padding(
                  padding: const EdgeInsets.fromLTRB(Espacio.margen, 8, Espacio.margen, Espacio.sm),
                  child: Row(
                    children: [
                      _Accion(
                        icono: Icons.speed_rounded,
                        texto: '${_velocidades[_velocidad]}x',
                        alTocar: _cambiarVelocidad,
                      ),
                      const SizedBox(width: Espacio.xs),
                      _Accion(icono: Icons.tune_rounded, color: Tono.doradoClaro, texto: 'Ajustes', alTocar: _ajustes),
                      const SizedBox(width: Espacio.xs),
                      _Accion(
                        icono: Icons.skip_next_rounded,
                        texto: 'Sig. Ep.',
                        alTocar: _siguiente == null ? null : () => _pasarA(_siguiente!),
                      ),
                      const SizedBox(width: Espacio.xs),
                      _Accion(
                        icono: Icons.screen_rotation_rounded,
                        color: Tono.textoSuave,
                        texto: 'Girar',
                        alTocar: _alternarPantallaCompleta,
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: Espacio.sm),
          if (widget.serie != null) _Capitulos(serie: widget.serie!, actual: _episodio, alElegir: _pasarA),
        ],
      ),
    );
  }

  /// La barra para adelantar con los tiempos (ver "Interactive Timeline Scrubber").
  Widget _barra({bool compacta = false}) {
    final valor = _valor;
    final duracion = valor?.duration ?? Duration.zero;
    final posicion = _control.posicion;
    final total = duracion.inMilliseconds;
    final fraccion = _arrastre ?? (total == 0 ? 0.0 : posicion.inMilliseconds / total);
    var cargado = 0.0;
    if (valor != null && total > 0) {
      for (final rango in valor.buffered) {
        cargado = cargado < rango.end.inMilliseconds / total ? rango.end.inMilliseconds / total : cargado;
      }
    }
    final alto = valor?.size.height.round() ?? 0;
    final calidad = alto >= 2000
        ? '4K'
        : alto >= 1000
        ? 'FULL HD'
        : alto >= 700
        ? 'HD'
        : alto > 0
        ? 'SD'
        : '';

    void irA(double x, double ancho) {
      if (total == 0) return;
      final nueva = (x / ancho).clamp(0.0, 1.0);
      setState(() => _arrastre = nueva);
    }

    Future<void> soltar() async {
      final destino = _arrastre;
      if (destino != null && total > 0) {
        await _control.irA(Duration(milliseconds: (destino * total).round()));
      }
      if (mounted) setState(() => _arrastre = null);
      _mostrarControles();
    }

    return Column(
      children: [
        LayoutBuilder(
          builder: (context, limites) => GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTapDown: (d) => irA(d.localPosition.dx, limites.maxWidth),
            onTapUp: (_) => soltar(),
            onHorizontalDragStart: (d) => irA(d.localPosition.dx, limites.maxWidth),
            onHorizontalDragUpdate: (d) => irA(d.localPosition.dx, limites.maxWidth),
            onHorizontalDragEnd: (_) => soltar(),
            child: SizedBox(
              height: 24,
              child: Stack(
                alignment: Alignment.centerLeft,
                clipBehavior: Clip.none,
                children: [
                  Container(
                    height: 6,
                    decoration: BoxDecoration(
                      color: Tono.capaMaxima.withValues(alpha: .4),
                      borderRadius: BorderRadius.circular(99),
                    ),
                  ),
                  FractionallySizedBox(
                    widthFactor: cargado.clamp(0.0, 1.0),
                    child: Container(
                      height: 6,
                      decoration: BoxDecoration(color: Tono.capaMaxima, borderRadius: BorderRadius.circular(99)),
                    ),
                  ),
                  FractionallySizedBox(
                    widthFactor: fraccion.clamp(0.0, 1.0),
                    child: Container(
                      height: 6,
                      decoration: BoxDecoration(
                        color: Tono.celeste,
                        borderRadius: BorderRadius.circular(99),
                        boxShadow: [BoxShadow(color: Tono.celeste.withValues(alpha: .6), blurRadius: 8)],
                      ),
                    ),
                  ),
                  Positioned(
                    left: (limites.maxWidth * fraccion.clamp(0.0, 1.0)) - 8,
                    child: Container(
                      width: 16,
                      height: 16,
                      decoration: BoxDecoration(
                        color: Tono.celeste,
                        shape: BoxShape.circle,
                        border: Border.all(color: Tono.capaMinima, width: 2),
                        boxShadow: [BoxShadow(color: Tono.celeste.withValues(alpha: .8), blurRadius: 10)],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.only(top: 2),
          child: Row(
            children: [
              Text(
                reloj(_arrastre == null ? posicion : Duration(milliseconds: (fraccion * total).round())),
                style: Letra.numeros.copyWith(color: Tono.celeste, fontWeight: FontWeight.w600),
              ),
              const Spacer(),
              if (calidad.isNotEmpty) ...[
                const PuntoEnVivo(tamanio: 6, color: Tono.rubiClaro),
                const SizedBox(width: 6),
                Text(calidad, style: Letra.mini.copyWith(color: Tono.rubiClaro, letterSpacing: .6)),
              ],
              const Spacer(),
              Text(reloj(duracion), style: Letra.numeros),
              if (compacta) ...[
                const SizedBox(width: 12),
                InkWell(
                  onTap: _alternarPantallaCompleta,
                  child: const Icon(Icons.fullscreen_exit_rounded, color: Tono.texto, size: 24),
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }
}

class _BarraReproductor extends StatelessWidget implements PreferredSizeWidget {
  const _BarraReproductor({required this.titulo});

  final String titulo;

  @override
  Size get preferredSize => const Size.fromHeight(56);

  @override
  Widget build(BuildContext context) {
    return ClipRect(
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 24, sigmaY: 24),
        child: Container(
          color: Tono.capaMinima.withValues(alpha: .8),
          padding: EdgeInsets.only(top: MediaQuery.paddingOf(context).top),
          child: SizedBox(
            height: 56,
            child: Row(
              children: [
                const SizedBox(width: 4),
                IconButton(
                  tooltip: 'Volver',
                  onPressed: () => Navigator.maybePop(context),
                  icon: const Icon(Icons.arrow_back_rounded, size: 24, color: Tono.texto),
                ),
                const SimboloKairos(tamanio: 22),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(titulo, maxLines: 1, overflow: TextOverflow.ellipsis, style: Letra.titulo),
                ),
                const SizedBox(width: Espacio.margen),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// El video con sus controles encima (los mismos en vertical y en pantalla completa).
class _Video extends StatelessWidget {
  const _Video({
    required this.control,
    required this.controles,
    required this.titulo,
    required this.subtitulo,
    required this.pantallaCompleta,
    required this.alTocar,
    required this.alVolver,
    required this.alAjustes,
    required this.alMostrarControles,
    this.barra,
  });

  final ControlSenal control;
  final bool controles;
  final String titulo;
  final String subtitulo;
  final bool pantallaCompleta;
  final VoidCallback alTocar;
  final VoidCallback alVolver;
  final VoidCallback alAjustes;
  final VoidCallback alMostrarControles;
  final Widget? barra;

  @override
  Widget build(BuildContext context) {
    final video = control.video;
    final reproduciendo = video?.value.isPlaying ?? false;
    final visibles = controles || !reproduciendo || control.error != null;
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: alTocar,
      child: ColoredBox(
        color: Tono.capaMinima,
        child: Stack(
          fit: StackFit.expand,
          children: [
            if (video != null)
              pantallaCompleta
                  ? VideoAjustado(video: video, ajuste: ControlSenal.ajuste)
                  : Center(
                      child: AspectRatio(aspectRatio: video.value.aspectRatio, child: VideoPlayer(video)),
                    ),
            if (control.cargando)
              Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const CircularProgressIndicator(),
                    const SizedBox(height: 14),
                    // Si tarda: que es el servidor preparando la película (no se colgó)
                    EsperaLarga(
                      control: control,
                      estilo: const TextStyle(color: Colors.white70, fontSize: 13, height: 1.35),
                    ),
                  ],
                ),
              ),
            AnimatedOpacity(
              opacity: visibles ? 1 : 0,
              duration: const Duration(milliseconds: 250),
              child: IgnorePointer(
                ignoring: !visibles,
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    // Degradés: "from-surface-container-lowest via-transparent to-.../80" y los laterales
                    const DecoratedBox(
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          begin: Alignment.bottomCenter,
                          end: Alignment.topCenter,
                          colors: [Color(0xCC0E0E12), Colors.transparent, Color(0xCC0E0E12)],
                        ),
                      ),
                    ),
                    // Arriba: volver, título y fuente
                    Positioned(
                      top: pantallaCompleta ? 16 : 8,
                      left: pantallaCompleta ? 16 : 8,
                      right: pantallaCompleta ? 16 : 8,
                      child: Row(
                        children: [
                          BotonRedondo(
                            icono: Icons.arrow_back_rounded,
                            tamanio: 40,
                            tamanioIcono: 20,
                            fondo: Tono.capaMaxima.withValues(alpha: .6),
                            alTocar: alVolver,
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Text(
                                  titulo,
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: Letra.titulo.copyWith(fontSize: 15, height: 1.2),
                                ),
                                Text(
                                  subtitulo,
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: Letra.mini.copyWith(color: Tono.textoSuave, fontWeight: FontWeight.w600),
                                ),
                              ],
                            ),
                          ),
                          BotonRedondo(
                            icono: Icons.tune_rounded,
                            tamanio: 36,
                            tamanioIcono: 18,
                            fondo: Tono.capaMaxima.withValues(alpha: .6),
                            color: Tono.textoSuave,
                            ayuda: 'Ajustes',
                            alTocar: alAjustes,
                          ),
                        ],
                      ),
                    ),
                    // Centro: -10 · pausa · +10
                    if (control.error == null && video != null)
                      Center(
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            _Salto(
                              atras: true,
                              alTocar: () {
                                control.saltar(const Duration(seconds: -10));
                                alMostrarControles();
                              },
                            ),
                            const SizedBox(width: Espacio.lg),
                            DecoratedBox(
                              decoration: BoxDecoration(
                                shape: BoxShape.circle,
                                boxShadow: brilloCeleste(desenfoque: 24, opacidad: .45),
                              ),
                              child: BotonRedondo(
                                icono: reproduciendo ? Icons.pause_rounded : Icons.play_arrow_rounded,
                                tamanio: 64,
                                tamanioIcono: 36,
                                fondo: Tono.celeste,
                                color: Tono.sobreCeleste,
                                alTocar: () {
                                  control.alternarPausa();
                                  alMostrarControles();
                                },
                              ),
                            ),
                            const SizedBox(width: Espacio.lg),
                            _Salto(
                              atras: false,
                              alTocar: () {
                                control.saltar(const Duration(seconds: 10));
                                alMostrarControles();
                              },
                            ),
                          ],
                        ),
                      ),
                    if (barra != null) Positioned(left: 24, right: 24, bottom: 16, child: barra!),
                  ],
                ),
              ),
            ),
            if (control.error != null)
              Center(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        control.error!,
                        textAlign: TextAlign.center,
                        style: Letra.cuerpo.copyWith(color: Tono.texto),
                      ),
                      const SizedBox(height: 12),
                      SizedBox(
                        width: 180,
                        child: BotonPrincipal(
                          texto: 'Reintentar',
                          icono: Icons.refresh_rounded,
                          alto: 40,
                          alTocar: control.reintentar,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

/// -10 s / +10 s (círculo de 48 con el ícono y el texto chiquito abajo).
class _Salto extends StatelessWidget {
  const _Salto({required this.atras, required this.alTocar});

  final bool atras;
  final VoidCallback alTocar;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Tono.capaMaxima.withValues(alpha: .5),
      shape: const CircleBorder(),
      child: InkWell(
        customBorder: const CircleBorder(),
        onTap: alTocar,
        child: SizedBox.square(
          dimension: 48,
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(atras ? Icons.replay_10_rounded : Icons.forward_10_rounded, size: 22, color: Tono.texto),
              Text(atras ? '-10s' : '+10s', style: Letra.mini.copyWith(fontSize: 9, height: 1)),
            ],
          ),
        ),
      ),
    );
  }
}

/// Un botón de la botonera (grid-cols-4: ícono de color arriba, texto abajo).
class _Accion extends StatelessWidget {
  const _Accion({required this.icono, required this.texto, required this.alTocar, this.color = Tono.celeste});

  final IconData icono;
  final String texto;
  final VoidCallback? alTocar;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final activo = alTocar != null;
    return Expanded(
      child: Material(
        color: Tono.capa,
        borderRadius: BorderRadius.circular(Curva.grande),
        child: InkWell(
          onTap: alTocar,
          borderRadius: BorderRadius.circular(Curva.grande),
          child: Padding(
            padding: const EdgeInsets.all(8),
            child: Column(
              children: [
                Icon(icono, size: 20, color: activo ? color : Tono.textoApagado),
                const SizedBox(height: 4),
                Text(
                  texto,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: Letra.mini.copyWith(color: activo ? Tono.texto : Tono.textoApagado),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// "Capítulos y Momentos": acá, los capítulos de la temporada (el actual marcado).
class _Capitulos extends StatefulWidget {
  const _Capitulos({required this.serie, required this.actual, required this.alElegir});

  final Serie serie;
  final Episodio? actual;
  final ValueChanged<Episodio> alElegir;

  @override
  State<_Capitulos> createState() => _CapitulosState();
}

class _CapitulosState extends State<_Capitulos> {
  final _desplazamiento = ScrollController();

  @override
  void initState() {
    super.initState();
    // Que el capítulo actual quede a la vista
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final indice = _episodios.indexOf(widget.actual ?? _episodios.first);
      if (_desplazamiento.hasClients && indice > 0) _desplazamiento.jumpTo((indice * 152.0) - 16);
    });
  }

  @override
  void dispose() {
    _desplazamiento.dispose();
    super.dispose();
  }

  List<Episodio> get _episodios => widget.serie.temporadas[widget.actual?.temporada] ?? widget.serie.episodios;

  @override
  Widget build(BuildContext context) {
    final episodios = _episodios;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(Espacio.margen, 8, Espacio.margen, 8),
          child: Row(
            children: [
              const Icon(Icons.bookmark_outline_rounded, size: 18, color: Tono.celeste),
              const SizedBox(width: Espacio.xs),
              Expanded(
                child: Text(
                  'Temporada ${widget.actual?.temporada ?? 1}',
                  style: Letra.titulo.copyWith(fontSize: 16, height: 1.25),
                ),
              ),
              Text('${episodios.length} capítulos', style: Letra.etiqueta.copyWith(color: Tono.celeste)),
            ],
          ),
        ),
        SizedBox(
          height: 136,
          child: ListView.separated(
            controller: _desplazamiento,
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: Espacio.margen, vertical: 4),
            itemCount: episodios.length,
            separatorBuilder: (_, _) => const SizedBox(width: Espacio.sm),
            itemBuilder: (context, i) {
              final episodio = episodios[i];
              final actual = episodio == widget.actual;
              return GestureDetector(
                onTap: actual ? null : () => widget.alElegir(episodio),
                child: SizedBox(
                  width: 144,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Container(
                        height: 80,
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(Curva.grande),
                          border: actual ? Border.all(color: Tono.celeste, width: 2) : null,
                          boxShadow: actual ? brilloCeleste(desenfoque: 12, opacidad: .35) : null,
                        ),
                        child: ClipRRect(
                          borderRadius: BorderRadius.circular(actual ? 10 : Curva.grande),
                          child: Stack(
                            fit: StackFit.expand,
                            children: [
                              Imagen(
                                url: episodio.canal.logo.isNotEmpty ? episodio.canal.logo : widget.serie.imagen,
                                nombre: widget.serie.nombre,
                                fondo: Tono.capa,
                                tamanioIniciales: 16,
                              ),
                              ColoredBox(
                                color: actual
                                    ? Tono.celeste.withValues(alpha: .1)
                                    : Tono.capaMinima.withValues(alpha: .35),
                              ),
                              if (actual)
                                Positioned(
                                  top: 4,
                                  left: 4,
                                  child: Container(
                                    padding: const EdgeInsets.symmetric(horizontal: 4),
                                    decoration: BoxDecoration(
                                      color: Tono.celeste,
                                      borderRadius: BorderRadius.circular(Curva.chico),
                                    ),
                                    child: Text(
                                      'REPRODUCIENDO',
                                      style: Letra.mini.copyWith(fontSize: 9, color: Tono.sobreCeleste),
                                    ),
                                  ),
                                ),
                              Positioned(
                                right: 4,
                                bottom: 4,
                                child: Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                  decoration: BoxDecoration(
                                    color: Tono.capaMinima.withValues(alpha: .9),
                                    borderRadius: BorderRadius.circular(Curva.chico),
                                  ),
                                  child: Text(
                                    'E${episodio.numero}',
                                    style: Letra.numeros.copyWith(
                                      fontSize: 10,
                                      color: actual ? Tono.celeste : Tono.texto,
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        episodio.titulo.isEmpty ? 'Capítulo ${episodio.numero}' : episodio.titulo,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: Letra.etiqueta.copyWith(
                          color: actual ? Tono.celeste : Tono.texto,
                          fontWeight: actual ? FontWeight.w700 : FontWeight.w600,
                        ),
                      ),
                      Text(
                        episodio.codigo,
                        style: Letra.mini.copyWith(color: Tono.textoSuave, fontWeight: FontWeight.w600),
                      ),
                    ],
                  ),
                ),
              );
            },
          ),
        ),
      ],
    );
  }
}
