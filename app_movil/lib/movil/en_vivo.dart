/// En Vivo (Stitch: "(1)", celular).
///
///   reproductor 16:9 con el canal elegido (EN VIVO, sonido, fuente, nombre,
///   Expandir) · Categorías con su cantidad y Favoritos · lista de canales
///
/// Tocar un canal lo reproduce arriba; "Expandir" lo abre a pantalla
/// completa (horizontal, con zapping). La guía de programación ("Ahora en
/// vivo / Próx. 2 horas", "A continuación") va a aparecer cuando se cargue
/// la guía (EPG); hasta entonces no se muestra nada inventado.
///
/// Con una tele conectada ("Ver en la tele", lib/tele/) el canal se ve en la
/// tele y arriba queda el panel con el control (PanelEnLaTele); si la tele se
/// desconecta, sigue en el celular.
///
/// La misma pantalla muestra una sección nueva "en vivo" (Radio...: [nueva]),
/// con sus categorías y sin la guía. Lo que no tiene imagen (una radio) deja
/// ver su logo mientras suena.
library;

import 'dart:async';
import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:video_player/video_player.dart';
import 'package:wakelock_plus/wakelock_plus.dart';

import '../api/modelos.dart';
import '../sesion.dart';
import '../tele/control_remoto.dart';
import '../tele/enlace.dart';
import 'ajustes_video.dart';
import 'componentes.dart';
import 'control_senal.dart';
import 'datos.dart';
import 'estilo.dart';
import 'guia.dart';
import 'mi_agenda.dart';
import 'estructura.dart';

/// Lo que se pidió al venir a En Vivo desde otra sección.
class PedidoEnVivo {
  PedidoEnVivo({this.categoria, this.canal});

  final String? categoria;
  final int? canal;
}

class SeccionEnVivo extends StatefulWidget {
  const SeccionEnVivo({super.key, required this.visible, this.pedido, this.nueva});

  /// Si la sección está a la vista: si no, se corta el video (no gasta datos
  /// ni ocupa la conexión, que en algunas listas es una sola).
  final bool visible;
  final PedidoEnVivo? pedido;

  /// La clave de una sección nueva (Radio...) para mostrar lo suyo; null = En Vivo.
  final String? nueva;

  @override
  State<SeccionEnVivo> createState() => _SeccionEnVivoState();
}

class _SeccionEnVivoState extends State<SeccionEnVivo> {
  // Se crea recién cuando hace falta (si no hay nada para ver, nunca): así
  // dispose no lo crea cuando la pantalla ya se está cerrando
  ControlSenal? _controlCreado;

  ControlSenal get _control => _controlCreado ??= ControlSenal(SesionScope.leer(context).api)
    ..alVerCanal = ((canal) => DatosScope.of(context).biblioteca.registrarCanalVisto(canal.id))
    ..addListener(_alCambiar);
  final _desplazamiento = ScrollController();
  String? _categoria; // null = todos
  bool _soloFavoritos = false;
  bool _controles = true;
  Timer? _ocultar;

  /// El último canal que se puso en la tele (al volver a En Vivo sigue ese).
  Canal? _ultimoEnLaTele;
  bool _teleConectada = Tele.instancia.conectada;

  @override
  void initState() {
    super.initState();
    Tele.instancia.addListener(_alCambiarTele);
  }

  @override
  void didUpdateWidget(SeccionEnVivo anterior) {
    super.didUpdateWidget(anterior);
    if (widget.pedido != anterior.pedido && widget.pedido != null) _atenderPedido(widget.pedido!);
    if (widget.visible && !anterior.visible) {
      WakelockPlus.enable();
      if (Tele.instancia.conectada) {
        if (_ultimoEnLaTele != null) _verEnLaTele(_ultimoEnLaTele!);
      } else if (_control.canal != null && _control.video == null) {
        _control.reintentar();
      }
    }
    if (!widget.visible && anterior.visible) {
      WakelockPlus.disable();
      _control.detener();
      Tele.instancia.dejarEnVivo(this);
    }
  }

  /// Se conectó la tele: lo que se veía en el celular pasa a la tele. Se
  /// desconectó: vuelve al celular.
  void _alCambiarTele() {
    final conectada = Tele.instancia.conectada;
    if (conectada == _teleConectada || !mounted) return;
    _teleConectada = conectada;
    if (!widget.visible) return;
    if (conectada) {
      final canal = _controlCreado?.canal;
      if (canal != null) {
        _controlCreado!.detener();
        _verEnLaTele(canal);
      }
    } else if (_ultimoEnLaTele != null) {
      _control.abrir(_ultimoEnLaTele!);
      _mostrarControles();
    }
  }

  @override
  void dispose() {
    Tele.instancia
      ..removeListener(_alCambiarTele)
      ..dejarEnVivo(this);
    _ocultar?.cancel();
    _controlCreado?.dispose();
    _desplazamiento.dispose();
    super.dispose();
  }

  void _alCambiar() {
    if (mounted) setState(() {});
  }

  void _atenderPedido(PedidoEnVivo pedido) {
    final catalogo = DatosScope.of(context).catalogo;
    setState(() {
      _categoria = pedido.categoria;
      _soloFavoritos = false;
    });
    // Cambió la categoría: la lista es otra, se empieza desde arriba
    if (_desplazamiento.hasClients) _desplazamiento.jumpTo(0);
    final canal = pedido.canal == null ? null : catalogo.canalPorId(pedido.canal!);
    if (canal != null) _ver(canal);
  }

  /// Pone el canal. La lista se queda donde está (el reproductor está fijo
  /// arriba): si ese no anda, el de al lado está ahí mismo, sin volver a bajar.
  void _ver(Canal canal) {
    if (Tele.instancia.conectada) {
      _verEnLaTele(canal);
    } else {
      _control.abrir(canal);
      _mostrarControles();
    }
  }

  void _verEnLaTele(Canal canal) {
    _ultimoEnLaTele = canal;
    Tele.instancia.verEnVivo(canal, duenio: this, nueva: widget.nueva);
    DatosScope.of(context).biblioteca.registrarCanalVisto(canal.id);
  }

  /// Anterior (-1) o siguiente (+1) en la lista que se está viendo.
  void _cambiarEnLaTele(int paso, List<Canal> lista) {
    if (lista.isEmpty) return;
    final actual = lista.indexWhere((c) => c.id == _ultimoEnLaTele?.id);
    _verEnLaTele(lista[actual < 0 ? 0 : (actual + paso) % lista.length]);
  }

  void _mostrarControles() {
    setState(() => _controles = true);
    _ocultar?.cancel();
    _ocultar = Timer(const Duration(seconds: 4), () {
      if (mounted && _control.video != null) setState(() => _controles = false);
    });
  }

  Future<void> _expandir(List<Canal> todos) async {
    if (_control.canal == null) return;
    // La pantalla completa usa esta misma señal (no abre otra conexión): si se
    // reconectara, el servidor IPTV repetiría sus últimos segundos guardados.
    await abrirPantalla<void>(context, PantallaEnVivoCompleta(control: _control, todos: todos));
    if (mounted) _mostrarControles();
  }

  Future<void> _ajustes() => ajustesDeVideoMovil(context, _control);

  @override
  Widget build(BuildContext context) {
    final datos = DatosScope.of(context);
    return ListenableBuilder(
      listenable: Listenable.merge([datos.catalogo, datos.biblioteca, Tele.instancia]),
      builder: (context, _) {
        final catalogo = datos.catalogo;
        final biblioteca = datos.biblioteca;
        if (!catalogo.cargado) return const Center(child: CircularProgressIndicator());
        final nueva = widget.nueva == null ? null : catalogo.seccionNueva(widget.nueva!);
        final todos = nueva?.canales ?? catalogo.canales;
        final categorias = nueva?.categorias ?? catalogo.categoriasEnVivo;
        if (todos.isEmpty) {
          return Vacio(
            icono: Icons.tv_off_rounded,
            texto: widget.nueva != null
                ? 'Todavía no hay nada disponible acá.'
                : 'Todavía no hay canales en vivo disponibles.',
          );
        }
        final visibles = [
          for (final canal in todos)
            if ((_categoria == null || canal.categoria == _categoria) &&
                (!_soloFavoritos || biblioteca.estaEnMiLista(Biblioteca.claveDe(canal))))
              canal,
        ];
        final favoritos = todos.where((c) => biblioteca.estaEnMiLista(Biblioteca.claveDe(c))).length;

        return Padding(
          padding: EdgeInsets.only(top: altoBarraSuperior(context)),
          child: Column(
            children: [
              // Con la tele: el canal se ve allá y acá queda el control
              if (Tele.instancia.conectada)
                PanelEnLaTele(
                  canal: Tele.instancia.enVivoDe(this),
                  alCambiarCanal: (paso) => _cambiarEnLaTele(paso, visibles.isNotEmpty ? visibles : todos),
                  alDetener: () {
                    _ultimoEnLaTele = null;
                    Tele.instancia.dejarEnVivo(this);
                  },
                  alPrimerCanal: () => _ver(visibles.isNotEmpty ? visibles.first : todos.first),
                )
              else
                // El reproductor queda fijo arriba mientras se recorre la lista
                _Reproductor(
                  control: _control,
                  controles: _controles,
                  alTocar: () => _controles ? setState(() => _controles = false) : _mostrarControles(),
                  alExpandir: () => _expandir(todos),
                  alAjustes: _ajustes,
                  alPrimerCanal: () => _ver(visibles.isNotEmpty ? visibles.first : todos.first),
                ),
              Expanded(
                child: RefreshIndicator(
                  onRefresh: catalogo.cargar,
                  child: CustomScrollView(
                    controller: _desplazamiento,
                    slivers: [
                      SliverToBoxAdapter(
                        child: Padding(
                          padding: const EdgeInsets.fromLTRB(Espacio.margen, Espacio.margen, Espacio.margen, 10),
                          child: Row(
                            children: [
                              Expanded(child: Text('Categorías', style: Letra.titulo)),
                              if (nueva == null) ...[
                                _Pildora(
                                  icono: Icons.view_list_rounded,
                                  texto: 'Guía',
                                  activo: false,
                                  alTocar: () => abrirPantalla<void>(context, PantallaGuia(alElegir: _ver)),
                                ),
                                const SizedBox(width: Espacio.sm),
                              ],
                              _Pildora(
                                icono: Icons.favorite_rounded,
                                texto: favoritos > 0 ? 'Favoritos ($favoritos)' : 'Favoritos',
                                activo: _soloFavoritos,
                                alTocar: () => setState(() => _soloFavoritos = !_soloFavoritos),
                              ),
                            ],
                          ),
                        ),
                      ),
                      SliverToBoxAdapter(
                        child: SizedBox(
                          height: 32,
                          child: ListView(
                            scrollDirection: Axis.horizontal,
                            padding: const EdgeInsets.symmetric(horizontal: Espacio.margen),
                            children: [
                              ChipFiltro(
                                texto: 'Todos (${todos.length})',
                                activo: _categoria == null,
                                compacto: true,
                                alTocar: () => setState(() => _categoria = null),
                              ),
                              for (final categoria in categorias) ...[
                                const SizedBox(width: Espacio.sm),
                                ChipFiltro(
                                  texto: '${categoriaLegible(categoria.nombre)} (${categoria.canales.length})',
                                  activo: _categoria == categoria.nombre,
                                  compacto: true,
                                  alTocar: () => setState(() => _categoria = categoria.nombre),
                                ),
                              ],
                            ],
                          ),
                        ),
                      ),
                      const SliverToBoxAdapter(child: SizedBox(height: Espacio.margen)),
                      if (visibles.isEmpty)
                        SliverToBoxAdapter(
                          child: Vacio(
                            icono: _soloFavoritos ? Icons.favorite_border_rounded : Icons.tv_off_rounded,
                            texto: _soloFavoritos
                                ? 'Todavía no marcaste canales favoritos. Tocá el corazón de un canal.'
                                : 'No hay canales en esta categoría.',
                          ),
                        ),
                      SliverPadding(
                        padding: EdgeInsets.fromLTRB(
                          Espacio.margen,
                          0,
                          Espacio.margen,
                          altoBarraInferior(context) + Espacio.lg,
                        ),
                        sliver: SliverList.separated(
                          itemCount: visibles.length,
                          separatorBuilder: (_, _) => const SizedBox(height: 12),
                          itemBuilder: (context, i) {
                            final canal = visibles[i];
                            return _TarjetaCanal(
                              canal: canal,
                              enReproduccion:
                                  (Tele.instancia.conectada ? Tele.instancia.enVivoDe(this) : _control.canal)?.id ==
                                  canal.id,
                              control: _control,
                              favorito: biblioteca.estaEnMiLista(Biblioteca.claveDe(canal)),
                              alTocar: () => _ver(canal),
                              alFavorito: () => biblioteca.alternarMiLista(Biblioteca.claveDe(canal)),
                            );
                          },
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

/// El reproductor 16:9 de arriba ("Live Stream Hero Player").
class _Reproductor extends StatelessWidget {
  const _Reproductor({
    required this.control,
    required this.controles,
    required this.alTocar,
    required this.alExpandir,
    required this.alAjustes,
    required this.alPrimerCanal,
  });

  final ControlSenal control;
  final bool controles;
  final VoidCallback alTocar;
  final VoidCallback alExpandir;
  final VoidCallback alAjustes;
  final VoidCallback alPrimerCanal;

  @override
  Widget build(BuildContext context) {
    final canal = control.canal;
    final video = control.video;
    final visibles = controles || video == null || control.error != null;
    return AspectRatio(
      aspectRatio: 16 / 9,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: canal == null ? alPrimerCanal : alTocar,
        child: Container(
          decoration: const BoxDecoration(
            color: Tono.capaMinima,
            boxShadow: [BoxShadow(color: Colors.black54, blurRadius: 20, offset: Offset(0, 8))],
          ),
          child: Stack(
            fit: StackFit.expand,
            children: [
              // Sin imagen (una radio): se ve su logo mientras suena
              if (video != null && video.value.size.height > 0)
                Center(
                  child: AspectRatio(aspectRatio: video.value.aspectRatio, child: VideoPlayer(video)),
                )
              else if (canal != null)
                Imagen(
                  url: canal.logo,
                  nombre: canal.nombre,
                  ajuste: BoxFit.contain,
                  relleno: const EdgeInsets.symmetric(horizontal: 110, vertical: 56),
                  fondo: Tono.capaMinima,
                  tamanioIniciales: 40,
                ),
              if (canal == null)
                Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.live_tv_rounded, size: 40, color: Tono.celeste),
                      const SizedBox(height: 10),
                      Text('Elegí un canal para verlo acá', style: Letra.cuerpo),
                    ],
                  ),
                ),
              if (control.cargando && canal != null) const Center(child: CircularProgressIndicator()),
              if (control.error != null)
                Center(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 32),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          control.error!,
                          textAlign: TextAlign.center,
                          style: Letra.cuerpo.copyWith(color: Tono.texto),
                        ),
                        TextButton.icon(
                          onPressed: control.reintentar,
                          icon: const Icon(Icons.refresh_rounded, color: Tono.celeste),
                          label: Text('Reintentar', style: Letra.etiqueta.copyWith(color: Tono.celeste)),
                        ),
                      ],
                    ),
                  ),
                ),
              if (canal != null)
                AnimatedOpacity(
                  opacity: visibles ? 1 : 0,
                  duration: const Duration(milliseconds: 250),
                  child: IgnorePointer(
                    ignoring: !visibles,
                    child: Stack(
                      fit: StackFit.expand,
                      children: [
                        // "from-surface-container-lowest via-.../30 to-.../60" y el lateral
                        const DecoratedBox(
                          decoration: BoxDecoration(
                            gradient: LinearGradient(
                              begin: Alignment.bottomCenter,
                              end: Alignment.topCenter,
                              colors: [Tono.capaMinima, Color(0x4D0E0E12), Color(0x990E0E12)],
                            ),
                          ),
                        ),
                        const DecoratedBox(
                          decoration: BoxDecoration(
                            gradient: LinearGradient(colors: [Color(0x990E0E12), Colors.transparent], stops: [0, .6]),
                          ),
                        ),
                        Positioned(
                          top: 12,
                          left: 12,
                          right: 12,
                          child: Row(
                            children: [
                              const InsigniaEnVivo(),
                              const SizedBox(width: 6),
                              if (control.fuentes.length > 1)
                                _PildoraVidrio('FUENTE ${control.fuente + 1}/${control.fuentes.length}'),
                              const Spacer(),
                              BotonRedondo(
                                icono: control.silenciado ? Icons.volume_off_rounded : Icons.volume_up_rounded,
                                tamanio: 32,
                                tamanioIcono: 18,
                                ayuda: control.silenciado ? 'Activar sonido' : 'Silenciar',
                                alTocar: control.alternarSonido,
                              ),
                              const SizedBox(width: 4),
                              BotonRedondo(
                                icono: Icons.tune_rounded,
                                tamanio: 32,
                                tamanioIcono: 18,
                                ayuda: 'Ajustes (calidad, idioma, imagen, fuente)',
                                alTocar: alAjustes,
                              ),
                            ],
                          ),
                        ),
                        Positioned(
                          left: 12,
                          right: 12,
                          bottom: 12,
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.end,
                            children: [
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    Row(
                                      children: [
                                        if (canal.numero.isNotEmpty) ...[
                                          Container(
                                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                            decoration: BoxDecoration(
                                              color: Tono.capa,
                                              borderRadius: BorderRadius.circular(Curva.chico),
                                            ),
                                            child: Text(
                                              'CH ${canal.numero}',
                                              style: Letra.mini.copyWith(color: Tono.celesteClaro),
                                            ),
                                          ),
                                          const SizedBox(width: 8),
                                        ],
                                        Flexible(
                                          child: Text(
                                            categoriaLegible(canal.categoria),
                                            maxLines: 1,
                                            overflow: TextOverflow.ellipsis,
                                            style: Letra.etiqueta.copyWith(color: Tono.celesteFijo),
                                          ),
                                        ),
                                      ],
                                    ),
                                    const SizedBox(height: 2),
                                    Text(
                                      canal.nombre,
                                      maxLines: 1,
                                      overflow: TextOverflow.ellipsis,
                                      style: Letra.titulo,
                                    ),
                                  ],
                                ),
                              ),
                              const SizedBox(width: 8),
                              Material(
                                color: Tono.celeste,
                                borderRadius: BorderRadius.circular(Curva.medio),
                                elevation: 6,
                                child: InkWell(
                                  onTap: alExpandir,
                                  borderRadius: BorderRadius.circular(Curva.medio),
                                  child: Padding(
                                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                                    child: Row(
                                      mainAxisSize: MainAxisSize.min,
                                      children: [
                                        const Icon(Icons.fullscreen_rounded, size: 18, color: Tono.sobreCeleste),
                                        const SizedBox(width: 4),
                                        Text(
                                          'Expandir',
                                          style: Letra.etiqueta.copyWith(
                                            color: Tono.sobreCeleste,
                                            fontWeight: FontWeight.w700,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                ),
                              ),
                            ],
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
    );
  }
}

class _PildoraVidrio extends StatelessWidget {
  const _PildoraVidrio(this.texto);

  final String texto;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(99),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 12, sigmaY: 12),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
          color: Tono.capaAlta.withValues(alpha: .8),
          child: Text(texto, style: Letra.mini),
        ),
      ),
    );
  }
}

/// "Favoritos" arriba a la derecha de Categorías.
class _Pildora extends StatelessWidget {
  const _Pildora({required this.icono, required this.texto, required this.activo, required this.alTocar});

  final IconData icono;
  final String texto;
  final bool activo;
  final VoidCallback alTocar;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: activo ? Tono.rubi.withValues(alpha: .2) : Tono.capaAlta,
      borderRadius: BorderRadius.circular(99),
      child: InkWell(
        onTap: alTocar,
        borderRadius: BorderRadius.circular(99),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icono, size: 14, color: activo ? Tono.rubiClaro : Tono.textoSuave),
              const SizedBox(width: 4),
              Text(
                texto,
                style: Letra.mini.copyWith(
                  color: activo ? Tono.rubiClaro : Tono.textoSuave,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Un canal de la lista ("epg-card"): logo, nombre con el punto rubí,
/// categoría y número, la campanita de "Recordarme" (mi_agenda.dart) y el
/// corazón de favoritos. El que se está viendo
/// tiene el recuadro de "Viendo ahora".
class _TarjetaCanal extends StatelessWidget {
  const _TarjetaCanal({
    required this.canal,
    required this.enReproduccion,
    required this.control,
    required this.favorito,
    required this.alTocar,
    required this.alFavorito,
  });

  final Canal canal;
  final bool enReproduccion;
  final ControlSenal control;
  final bool favorito;
  final VoidCallback alTocar;
  final VoidCallback alFavorito;

  @override
  Widget build(BuildContext context) {
    final categoria = categoriaLegible(canal.categoria);
    return Material(
      color: Tono.capa,
      borderRadius: BorderRadius.circular(Curva.tarjeta),
      elevation: 3,
      shadowColor: Colors.black54,
      child: InkWell(
        onTap: alTocar,
        borderRadius: BorderRadius.circular(Curva.tarjeta),
        child: Container(
          padding: const EdgeInsets.all(12),
          decoration: enReproduccion
              ? BoxDecoration(
                  borderRadius: BorderRadius.circular(Curva.tarjeta),
                  border: Border.all(color: Tono.celeste.withValues(alpha: .6)),
                )
              : null,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  ClipRRect(
                    borderRadius: BorderRadius.circular(Curva.grande),
                    child: SizedBox.square(
                      dimension: 48,
                      child: Imagen(
                        url: canal.logo,
                        nombre: canal.nombre,
                        ajuste: BoxFit.contain,
                        relleno: const EdgeInsets.all(6),
                        fondo: Tono.capaMinima,
                        tamanioIniciales: 16,
                      ),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Flexible(
                              child: Text(
                                canal.nombre,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: Letra.titulo.copyWith(fontSize: 16, height: 1.25),
                              ),
                            ),
                            const SizedBox(width: 6),
                            Container(
                              width: 6,
                              height: 6,
                              decoration: const BoxDecoration(color: Tono.rubi, shape: BoxShape.circle),
                            ),
                          ],
                        ),
                        Text(
                          [
                            if (categoria.isNotEmpty) categoria,
                            if (canal.numero.isNotEmpty) 'CH ${canal.numero}',
                          ].join(' • '),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: Letra.cuerpo,
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 8),
                  BotonRecordarme(canal: canal),
                  const SizedBox(width: 6),
                  BotonRedondo(
                    icono: favorito ? Icons.favorite_rounded : Icons.favorite_border_rounded,
                    tamanio: 36,
                    tamanioIcono: 18,
                    fondo: Tono.capaMinima,
                    color: favorito ? Tono.rubiClaro : Tono.textoSuave,
                    ayuda: favorito ? 'Quitar de favoritos' : 'Agregar a favoritos',
                    alTocar: alFavorito,
                  ),
                ],
              ),
              if (enReproduccion) ...[
                const SizedBox(height: 12),
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(color: Tono.capaMinima, borderRadius: BorderRadius.circular(Curva.grande)),
                  child: Row(
                    children: [
                      Icon(
                        control.error != null ? Icons.error_outline_rounded : Icons.play_circle_rounded,
                        size: 14,
                        color: control.error != null ? Tono.rubiClaro : Tono.celesteClaro,
                      ),
                      const SizedBox(width: 6),
                      Expanded(
                        child: Text(
                          control.error != null
                              ? 'Sin señal'
                              : control.cargando
                              ? 'Conectando…'
                              : 'Viendo ahora',
                          style: Letra.numeros.copyWith(
                            color: control.error != null ? Tono.rubiClaro : Tono.celesteClaro,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                      if (control.fuentes.length > 1)
                        Text(
                          'Fuente ${control.fuente + 1} de ${control.fuentes.length}',
                          style: Letra.numeros.copyWith(color: Tono.texto),
                        ),
                    ],
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

// ── Pantalla completa ──────────────────────────────────────────────

/// Un canal en vivo a pantalla completa (horizontal). Arriba / abajo (o
/// CH+ / CH−, o las flechas de la barra) cambian de canal sin salir.
/// Usa la misma señal que el reproductor chico ([control]): no se corta ni se
/// vuelve a conectar al expandir, y al volver sigue el último canal elegido.
class PantallaEnVivoCompleta extends StatefulWidget {
  const PantallaEnVivoCompleta({super.key, required this.control, required this.todos});

  final ControlSenal control;
  final List<Canal> todos;

  @override
  State<PantallaEnVivoCompleta> createState() => _PantallaEnVivoCompletaState();
}

class _PantallaEnVivoCompletaState extends State<PantallaEnVivoCompleta> {
  late final ControlSenal _control = widget.control;
  bool _controles = true;
  Timer? _ocultar;

  @override
  void initState() {
    super.initState();
    SystemChrome.setPreferredOrientations([DeviceOrientation.landscapeLeft, DeviceOrientation.landscapeRight]);
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);
    WakelockPlus.enable();
    _control.addListener(_alCambiar);
    _mostrarControles();
  }

  @override
  void dispose() {
    _ocultar?.cancel();
    _control.removeListener(_alCambiar); // la señal sigue: es la del reproductor chico
    SystemChrome.setPreferredOrientations([]);
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
    super.dispose();
  }

  void _alCambiar() {
    if (mounted) setState(() {});
  }

  void _mostrarControles() {
    setState(() => _controles = true);
    _ocultar?.cancel();
    _ocultar = Timer(const Duration(seconds: 4), () {
      if (mounted) setState(() => _controles = false);
    });
  }

  void _zapping(int paso) {
    final todos = widget.todos;
    final actual = todos.indexWhere((c) => c.id == _control.canal?.id);
    if (todos.length < 2 || actual < 0) return;
    _control.abrir(todos[(actual + paso) % todos.length]);
    _mostrarControles();
  }

  KeyEventResult _tecla(FocusNode nodo, KeyEvent evento) {
    if (evento is! KeyDownEvent) return KeyEventResult.ignored;
    final tecla = evento.logicalKey;
    // Como en la lista: Arriba, el de arriba; Abajo, el de abajo. CH+ sube el número, como en cualquier TV.
    if (tecla == LogicalKeyboardKey.arrowDown || tecla == LogicalKeyboardKey.channelUp) {
      _zapping(1);
      return KeyEventResult.handled;
    }
    if (tecla == LogicalKeyboardKey.arrowUp || tecla == LogicalKeyboardKey.channelDown) {
      _zapping(-1);
      return KeyEventResult.handled;
    }
    return KeyEventResult.ignored;
  }

  @override
  Widget build(BuildContext context) {
    final canal = _control.canal!;
    final video = _control.video;
    final visibles = _controles || _control.error != null;
    return Scaffold(
      backgroundColor: Colors.black,
      body: Focus(
        autofocus: true,
        onKeyEvent: _tecla,
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () => _controles ? setState(() => _controles = false) : _mostrarControles(),
          onVerticalDragEnd: (d) {
            final velocidad = d.primaryVelocity ?? 0;
            if (velocidad.abs() > 300) _zapping(velocidad < 0 ? 1 : -1);
          },
          child: Stack(
            fit: StackFit.expand,
            children: [
              if (video != null) VideoAjustado(video: video, ajuste: ControlSenal.ajuste),
              if (_control.cargando)
                Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const CircularProgressIndicator(),
                      // Con varias señales, cuál se está probando (que no parezca colgada)
                      if (_control.avisoDeConexion case final aviso?) ...[
                        const SizedBox(height: 14),
                        Text(
                          aviso,
                          textAlign: TextAlign.center,
                          style: Letra.cuerpo.copyWith(color: Tono.texto),
                        ),
                      ],
                    ],
                  ),
                ),
              if (_control.error != null)
                Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.signal_wifi_connected_no_internet_4_rounded, size: 48, color: Tono.textoSuave),
                      const SizedBox(height: 12),
                      Text(
                        _control.error!,
                        textAlign: TextAlign.center,
                        style: Letra.cuerpo.copyWith(color: Tono.texto),
                      ),
                      const SizedBox(height: 16),
                      SizedBox(
                        width: 180,
                        child: BotonPrincipal(
                          texto: 'Reintentar',
                          icono: Icons.refresh_rounded,
                          alto: 40,
                          alTocar: _control.reintentar,
                        ),
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
                      const Align(
                        alignment: Alignment.topCenter,
                        child: SizedBox(
                          height: 120,
                          width: double.infinity,
                          child: DecoratedBox(
                            decoration: BoxDecoration(
                              gradient: LinearGradient(
                                begin: Alignment.topCenter,
                                end: Alignment.bottomCenter,
                                colors: [Color(0xCC0E0E12), Colors.transparent],
                              ),
                            ),
                          ),
                        ),
                      ),
                      SafeArea(
                        child: Padding(
                          padding: const EdgeInsets.fromLTRB(12, 12, 20, 0),
                          child: Align(
                            alignment: Alignment.topCenter,
                            child: Row(
                              children: [
                                BotonRedondo(
                                  icono: Icons.arrow_back_rounded,
                                  tamanio: 40,
                                  tamanioIcono: 20,
                                  fondo: Tono.capaMaxima.withValues(alpha: .6),
                                  alTocar: () => Navigator.pop(context),
                                ),
                                const SizedBox(width: 12),
                                ClipRRect(
                                  borderRadius: BorderRadius.circular(Curva.medio),
                                  child: SizedBox(
                                    width: 52,
                                    height: 40,
                                    child: Imagen(
                                      url: canal.logo,
                                      nombre: canal.nombre,
                                      ajuste: BoxFit.contain,
                                      relleno: const EdgeInsets.all(4),
                                      fondo: Tono.capaMinima.withValues(alpha: .8),
                                      tamanioIniciales: 14,
                                    ),
                                  ),
                                ),
                                const SizedBox(width: 12),
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      Text(
                                        canal.nombre,
                                        maxLines: 1,
                                        overflow: TextOverflow.ellipsis,
                                        style: Letra.titulo,
                                      ),
                                      Text(
                                        [
                                          categoriaLegible(canal.categoria),
                                          if (canal.numero.isNotEmpty) 'CH ${canal.numero}',
                                          if (_control.fuentes.length > 1)
                                            'Fuente ${_control.fuente + 1} de ${_control.fuentes.length}',
                                        ].where((t) => t.isNotEmpty).join(' • '),
                                        style: Letra.numeros,
                                      ),
                                    ],
                                  ),
                                ),
                                BotonRedondo(
                                  icono: Icons.keyboard_arrow_up_rounded,
                                  tamanio: 40,
                                  tamanioIcono: 24,
                                  fondo: Tono.capaMaxima.withValues(alpha: .6),
                                  ayuda: 'Canal siguiente',
                                  alTocar: () => _zapping(1),
                                ),
                                const SizedBox(width: 6),
                                BotonRedondo(
                                  icono: Icons.keyboard_arrow_down_rounded,
                                  tamanio: 40,
                                  tamanioIcono: 24,
                                  fondo: Tono.capaMaxima.withValues(alpha: .6),
                                  ayuda: 'Canal anterior',
                                  alTocar: () => _zapping(-1),
                                ),
                                const SizedBox(width: 6),
                                BotonRedondo(
                                  icono: Icons.tune_rounded,
                                  tamanio: 40,
                                  tamanioIcono: 20,
                                  fondo: Tono.capaMaxima.withValues(alpha: .6),
                                  ayuda: 'Ajustes',
                                  alTocar: () => ajustesDeVideoMovil(context, _control),
                                ),
                                const SizedBox(width: 12),
                                const InsigniaEnVivo(),
                              ],
                            ),
                          ),
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
    );
  }
}
