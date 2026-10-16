/// "Ver en la tele", lo que se ve en el CELULAR mientras hay una tele conectada:
///
///   - BotonTele: el ícono de la barra de arriba (conectar / conectado).
///   - ControlRemotoTele: en lugar del reproductor, mientras la película o el
///     capítulo se ve en la tele (pausa, ±10 s, flechas y OK para las opciones
///     de la tele, Dejar de ver).
///   - PanelEnLaTele: arriba de En Vivo, en lugar del video (el canal que se ve
///     en la tele, anterior / siguiente, control, detener).
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../api/modelos.dart';
import '../movil/componentes.dart';
import '../movil/datos.dart';
import '../movil/estilo.dart';
import 'enlace.dart';

/// El ícono de la tele en la barra de arriba: celeste si está conectada.
///
/// Sin tele, tocarlo abre directo la lista de teles de Android. Antes, la
/// primera vez, pide el permiso para que la tele muestre SOLO la app (nunca el
/// celular). Si este celular no deja abrir la lista desde una app, explica
/// cómo abrirla. Con la tele conectada, muestra con cuál está y "Desconectar".
class BotonTele extends StatelessWidget {
  const BotonTele({super.key});

  Future<void> _alTocar(BuildContext context) async {
    final tele = Tele.instancia;
    if (!tele.conectada && await tele.puedeQuedarFija() && await tele.conectar()) return;
    if (!context.mounted) return;
    await showModalBottomSheet<void>(
      context: context,
      backgroundColor: Tono.capaBaja,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (_) => const _HojaTele(),
    );
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: Tele.instancia,
      builder: (context, _) {
        final conectada = Tele.instancia.conectada;
        return IconButton(
          tooltip: conectada ? 'Conectado a la tele' : 'Ver en la tele',
          onPressed: () => _alTocar(context),
          icon: Icon(
            conectada ? Icons.cast_connected_rounded : Icons.cast_rounded,
            size: 22,
            color: conectada ? Tono.celeste : Tono.textoSuave,
          ),
        );
      },
    );
  }
}

/// Cómo conectar la tele (o con cuál está conectado), y el permiso para que
/// la tele muestre solo la app.
class _HojaTele extends StatefulWidget {
  const _HojaTele();

  @override
  State<_HojaTele> createState() => _HojaTeleState();
}

class _HojaTeleState extends State<_HojaTele> {
  /// null = todavía no se sabe (se pregunta al abrir y al volver de los ajustes de Android).
  bool? _fija;
  bool _sinAjustes = false;
  AppLifecycleListener? _ciclo;

  @override
  void initState() {
    super.initState();
    _mirarPermiso();
    _ciclo = AppLifecycleListener(onResume: _mirarPermiso);
  }

  @override
  void dispose() {
    _ciclo?.dispose();
    super.dispose();
  }

  Future<void> _mirarPermiso() async {
    final fija = await Tele.instancia.puedeQuedarFija();
    if (mounted) setState(() => _fija = fija);
  }

  Future<void> _elegirTele() async {
    final pudo = await Tele.instancia.conectar();
    if (!mounted) return;
    if (pudo) {
      Navigator.pop(context);
    } else {
      setState(() => _sinAjustes = true);
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: Tele.instancia,
      builder: (context, _) {
        final tele = Tele.instancia;
        final sinPermiso = _fija == false;
        return SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(Espacio.lg, 0, Espacio.lg, Espacio.lg),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(
                      tele.conectada ? Icons.cast_connected_rounded : Icons.cast_rounded,
                      color: Tono.celeste,
                      size: 28,
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        tele.conectada
                            ? 'Conectado a ${tele.nombre.isEmpty ? 'la tele' : tele.nombre}'
                            : 'Ver en la tele',
                        style: Letra.titulo,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                if (sinPermiso) ...[const _Permiso(), const SizedBox(height: Espacio.lg)],
                if (tele.conectada) ...[
                  const Text(
                    'Lo que elijas acá se ve en la tele, con su diseño de TV. Lo que reproduzcas también: '
                    'en el celular te queda el control.',
                    style: Letra.cuerpo,
                  ),
                  const SizedBox(height: Espacio.lg),
                  OutlinedButton.icon(
                    onPressed: () {
                      Navigator.pop(context);
                      Tele.instancia.desconectar();
                    },
                    icon: const Icon(Icons.cancel_presentation_rounded),
                    label: const Text('Desconectar'),
                  ),
                ] else ...[
                  const _Paso(
                    numero: '1',
                    texto:
                        'En la tele, abrí la función para recibir la pantalla del celular (en una Kanji: '
                        'Screencast; en otras: Screen Mirroring o Duplicar pantalla).',
                  ),
                  const _Paso(
                    numero: '2',
                    texto:
                        'Tocá "Elegir la tele" y elegí la tuya. Si no aparece, en el menú ⋮ tildá '
                        '"Habilitar pantalla inalámbrica".',
                  ),
                  const _Paso(numero: '3', texto: 'Volvé a Kairos TV: cuando la tele muestra el logo, ya está.'),
                  const SizedBox(height: Espacio.lg),
                  if (sinPermiso)
                    // Se puede igual, pero la tele va a mostrar el celular cuando no estés en la app
                    OutlinedButton.icon(
                      onPressed: _elegirTele,
                      icon: const Icon(Icons.cast_rounded),
                      label: const Text('Elegir la tele sin el permiso'),
                    )
                  else
                    BotonPrincipal(texto: 'Elegir la tele', icono: Icons.cast_rounded, alTocar: _elegirTele),
                  if (_sinAjustes) ...[
                    const SizedBox(height: 12),
                    const Text(
                      'Este celular no deja abrir la lista desde acá: deslizá desde arriba de la pantalla y '
                      'tocá Transmitir, Smart View o Duplicar pantalla.',
                      style: Letra.cuerpo,
                    ),
                  ],
                ],
              ],
            ),
          ),
        );
      },
    );
  }
}

/// "Que la tele muestre solo la app": el permiso "Mostrar sobre otras apps",
/// una sola vez. Sin él, Android vuelve a mostrar el celular en la tele
/// mientras no se está en la app (al elegir la tele, al abrir WhatsApp).
class _Permiso extends StatelessWidget {
  const _Permiso();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(Espacio.margen),
      decoration: BoxDecoration(
        color: Tono.capa,
        borderRadius: BorderRadius.circular(Curva.tarjeta),
        border: Border.all(color: Tono.celeste.withValues(alpha: .35)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.lock_rounded, color: Tono.celeste, size: 20),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  'Que la tele muestre solo la app',
                  style: Letra.cuerpoGrande.copyWith(fontWeight: FontWeight.w700),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          const Text(
            'Así la tele nunca muestra tu celular: ni mientras elegís la tele, ni si salís de la app (WhatsApp, '
            'fotos). Android pide un permiso una sola vez: en la pantalla que se abre, activá '
            '"Permitir mostrar sobre otras apps" y volvé.',
            style: Letra.cuerpo,
          ),
          const SizedBox(height: 14),
          BotonPrincipal(texto: 'Dar el permiso', icono: Icons.lock_rounded, alTocar: Tele.instancia.pedirQuedarFija),
        ],
      ),
    );
  }
}

class _Paso extends StatelessWidget {
  const _Paso({required this.numero, required this.texto});

  final String numero;
  final String texto;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 24,
            height: 24,
            alignment: Alignment.center,
            decoration: const BoxDecoration(shape: BoxShape.circle, color: Tono.capaMaxima),
            child: Text(numero, style: Letra.mini.copyWith(color: Tono.celeste)),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Text(texto, style: Letra.cuerpo.copyWith(color: Tono.texto)),
          ),
        ],
      ),
    );
  }
}

/// El control remoto: lo que queda en el celular mientras algo se ve en la tele.
class ControlRemotoTele extends StatefulWidget {
  const ControlRemotoTele({super.key, this.clave, this.titulo = '', this.detalle = '', this.alCambiarCanal});

  /// La capa que se está viendo en la tele (enlace.dart): al salir de acá se
  /// deja de ver. null = solo es el control (el canal en vivo sigue en la tele).
  final String? clave;
  final String titulo;

  /// El capítulo ("T1:E3 · El regreso"), si es una serie.
  final String detalle;

  /// En vivo: cambia de canal (+1 el siguiente, -1 el anterior). null = película o capítulo.
  final void Function(int paso)? alCambiarCanal;

  bool get enVivo => alCambiarCanal != null;

  @override
  State<ControlRemotoTele> createState() => _ControlRemotoTeleState();
}

class _ControlRemotoTeleState extends State<ControlRemotoTele> {
  StreamSubscription<String>? _cerradas;
  Biblioteca? _biblioteca;
  bool _pausado = false;

  @override
  void initState() {
    super.initState();
    _cerradas = Tele.instancia.cerradas.listen((clave) {
      if (clave == widget.clave) _salir();
    });
    Tele.instancia.addListener(_alCambiarTele);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _biblioteca = context.dependOnInheritedWidgetOfExactType<DatosScope>()?.biblioteca;
  }

  @override
  void dispose() {
    _cerradas?.cancel();
    Tele.instancia.removeListener(_alCambiarTele);
    // La tele guarda por dónde iba y se lo manda al servidor: en unos segundos
    // el celular lo trae ("Continuar viendo")
    final biblioteca = _biblioteca;
    if (widget.clave != null && biblioteca != null) Timer(const Duration(seconds: 6), biblioteca.sincronizar);
    super.dispose();
  }

  /// Se desconectó la tele: el control ya no tiene sentido.
  void _alCambiarTele() {
    if (!Tele.instancia.conectada) _salir();
    if (mounted) setState(() {});
  }

  void _salir() {
    if (mounted && (ModalRoute.of(context)?.isCurrent ?? false)) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    final tele = Tele.instancia;
    final titulo = widget.enVivo ? tele.enVivo?.nombre ?? widget.titulo : widget.titulo;
    return Scaffold(
      backgroundColor: Tono.fondo,
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: Espacio.lg),
          child: Column(
            children: [
              Row(
                children: [
                  IconButton(
                    tooltip: 'Volver',
                    onPressed: () => Navigator.maybePop(context),
                    icon: const Icon(Icons.arrow_back_rounded, color: Tono.texto),
                  ),
                  const SizedBox(width: 4),
                  Expanded(
                    child: Text(
                      'EN LA TELE',
                      style: Letra.etiqueta.copyWith(color: Tono.celesteClaro, letterSpacing: 1.2),
                    ),
                  ),
                ],
              ),
              const Spacer(),
              Icon(Icons.connected_tv_rounded, size: 64, color: Tono.celeste, shadows: brilloCeleste()),
              const SizedBox(height: 16),
              Text(
                titulo,
                textAlign: TextAlign.center,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: Letra.titulo.copyWith(fontSize: 22),
              ),
              if (widget.detalle.isNotEmpty) ...[
                const SizedBox(height: 4),
                Text(
                  widget.detalle,
                  textAlign: TextAlign.center,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: Letra.cuerpo,
                ),
              ],
              const SizedBox(height: 6),
              Text(
                'Se está viendo en ${tele.nombre.isEmpty ? 'la tele' : tele.nombre}',
                textAlign: TextAlign.center,
                style: Letra.mini.copyWith(color: Tono.textoApagado),
              ),
              const Spacer(),
              if (widget.enVivo)
                _FilaBotones(
                  botones: [
                    _BotonControl(
                      icono: Icons.skip_previous_rounded,
                      texto: 'Anterior',
                      alTocar: () => widget.alCambiarCanal!(-1),
                    ),
                    _BotonControl(
                      icono: Icons.skip_next_rounded,
                      texto: 'Siguiente',
                      alTocar: () => widget.alCambiarCanal!(1),
                    ),
                  ],
                )
              else
                _FilaBotones(
                  botones: [
                    _BotonControl(
                      icono: Icons.replay_10_rounded,
                      texto: '10 s',
                      alTocar: () => tele.tecla('izquierda'),
                    ),
                    _BotonControl(
                      icono: _pausado ? Icons.play_arrow_rounded : Icons.pause_rounded,
                      texto: _pausado ? 'Seguir' : 'Pausa',
                      principal: true,
                      alTocar: () {
                        tele.tecla('pausa');
                        setState(() => _pausado = !_pausado);
                      },
                    ),
                    _BotonControl(icono: Icons.forward_10_rounded, texto: '10 s', alTocar: () => tele.tecla('derecha')),
                  ],
                ),
              const SizedBox(height: 28),
              const _Cruz(),
              const SizedBox(height: 8),
              Text(
                widget.enVivo
                    ? 'Con las flechas y OK: las opciones de la tele (favoritos, Ajustes, fuente).'
                    : 'Con las flechas y OK: las opciones de la tele (siguiente capítulo, Ajustes, subtítulos).',
                textAlign: TextAlign.center,
                style: Letra.mini.copyWith(color: Tono.textoApagado),
              ),
              const Spacer(),
              if (widget.clave != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: Espacio.lg),
                  child: SizedBox(
                    width: double.infinity,
                    child: OutlinedButton.icon(
                      onPressed: () => Navigator.maybePop(context),
                      icon: const Icon(Icons.stop_rounded),
                      label: const Text('Dejar de ver'),
                    ),
                  ),
                )
              else
                const SizedBox(height: Espacio.lg),
            ],
          ),
        ),
      ),
    );
  }
}

class _FilaBotones extends StatelessWidget {
  const _FilaBotones({required this.botones});

  final List<Widget> botones;

  @override
  Widget build(BuildContext context) {
    return Row(mainAxisAlignment: MainAxisAlignment.spaceEvenly, children: botones);
  }
}

class _BotonControl extends StatelessWidget {
  const _BotonControl({required this.icono, required this.texto, required this.alTocar, this.principal = false});

  final IconData icono;
  final String texto;
  final VoidCallback alTocar;
  final bool principal;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        BotonRedondo(
          icono: icono,
          alTocar: alTocar,
          tamanio: principal ? 76 : 60,
          tamanioIcono: principal ? 40 : 30,
          fondo: principal ? Tono.celeste : null,
          color: principal ? Tono.sobreCelesteOscuro : Tono.texto,
          ayuda: texto,
        ),
        const SizedBox(height: 6),
        Text(texto, style: Letra.mini.copyWith(color: Tono.textoSuave)),
      ],
    );
  }
}

/// Flechas, OK y Atrás: como el control de la tele.
class _Cruz extends StatelessWidget {
  const _Cruz();

  @override
  Widget build(BuildContext context) {
    final tele = Tele.instancia;
    Widget flecha(IconData icono, String tecla, String ayuda) =>
        BotonRedondo(icono: icono, ayuda: ayuda, tamanio: 52, tamanioIcono: 30, alTocar: () => tele.tecla(tecla));
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Tono.capaBaja,
        borderRadius: BorderRadius.circular(Curva.panel + 20),
        border: Border.all(color: Tono.bordeSuave.withValues(alpha: .5)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          flecha(Icons.keyboard_arrow_up_rounded, 'arriba', 'Arriba'),
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              flecha(Icons.keyboard_arrow_left_rounded, 'izquierda', 'Izquierda'),
              Padding(
                padding: const EdgeInsets.all(8),
                child: BotonRedondo(
                  icono: Icons.circle_outlined,
                  ayuda: 'OK',
                  tamanio: 60,
                  tamanioIcono: 26,
                  fondo: Tono.capaMaxima,
                  color: Tono.celeste,
                  alTocar: () => tele.tecla('ok'),
                ),
              ),
              flecha(Icons.keyboard_arrow_right_rounded, 'derecha', 'Derecha'),
            ],
          ),
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const SizedBox(width: 52),
              flecha(Icons.keyboard_arrow_down_rounded, 'abajo', 'Abajo'),
              BotonRedondo(
                icono: Icons.undo_rounded,
                ayuda: 'Atrás (en la tele)',
                tamanio: 52,
                tamanioIcono: 24,
                alTocar: tele.atras,
              ),
            ],
          ),
        ],
      ),
    );
  }
}

/// Arriba de En Vivo, en lugar del video, mientras hay tele: qué canal se ve allá.
class PanelEnLaTele extends StatelessWidget {
  const PanelEnLaTele({
    super.key,
    required this.canal,
    required this.alCambiarCanal,
    required this.alDetener,
    required this.alPrimerCanal,
  });

  /// El que se ve en la tele (null = todavía ninguno).
  final Canal? canal;
  final void Function(int paso) alCambiarCanal;
  final VoidCallback alDetener;
  final VoidCallback alPrimerCanal;

  @override
  Widget build(BuildContext context) {
    final tele = Tele.instancia;
    final canal = this.canal;
    return AspectRatio(
      aspectRatio: 16 / 9,
      child: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            colors: [Tono.capaMinima, Color(0xFF0B2A2D)],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
          boxShadow: [BoxShadow(color: Colors.black54, blurRadius: 20, offset: Offset(0, 8))],
        ),
        padding: const EdgeInsets.all(Espacio.margen),
        child: Column(
          children: [
            Row(
              children: [
                const Icon(Icons.cast_connected_rounded, size: 18, color: Tono.celeste),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    'EN LA TELE${tele.nombre.isEmpty ? '' : ' · ${tele.nombre.toUpperCase()}'}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: Letra.mini.copyWith(color: Tono.celesteClaro, letterSpacing: 1),
                  ),
                ),
              ],
            ),
            const Spacer(),
            if (canal == null) ...[
              Text(
                'Tocá un canal de la lista para verlo en la tele.',
                textAlign: TextAlign.center,
                style: Letra.cuerpo.copyWith(color: Tono.texto),
              ),
              const SizedBox(height: 12),
              SizedBox(
                width: 200,
                child: BotonPrincipal(texto: 'Ver el primero', alTocar: alPrimerCanal, alto: 40),
              ),
            ] else ...[
              Text(
                canal.nombre,
                textAlign: TextAlign.center,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: Letra.titulo.copyWith(fontSize: 20),
              ),
              const SizedBox(height: 14),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  BotonRedondo(
                    icono: Icons.skip_previous_rounded,
                    ayuda: 'Canal anterior',
                    alTocar: () => alCambiarCanal(-1),
                  ),
                  const SizedBox(width: 12),
                  BotonRedondo(
                    icono: Icons.settings_remote_rounded,
                    ayuda: 'Control remoto',
                    fondo: Tono.celeste,
                    color: Tono.sobreCelesteOscuro,
                    alTocar: () => _abrirControl(context),
                  ),
                  const SizedBox(width: 12),
                  BotonRedondo(
                    icono: Icons.skip_next_rounded,
                    ayuda: 'Canal siguiente',
                    alTocar: () => alCambiarCanal(1),
                  ),
                  const SizedBox(width: 12),
                  BotonRedondo(icono: Icons.stop_rounded, ayuda: 'Dejar de ver', alTocar: alDetener),
                ],
              ),
            ],
            const Spacer(),
          ],
        ),
      ),
    );
  }

  void _abrirControl(BuildContext context) {
    Navigator.push(
      context,
      MaterialPageRoute<void>(
        builder: (_) => Theme(
          data: temaMovil(),
          child: ControlRemotoTele(titulo: canal?.nombre ?? '', alCambiarCanal: alCambiarCanal),
        ),
      ),
    );
  }
}
