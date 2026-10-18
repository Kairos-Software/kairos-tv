/// La guía de canales de la TV (diseno_kairos_tv: tv-06): a la izquierda
/// las categorías; a la derecha todos los canales en lista (número, logo o
/// iniciales, nombre y categoría). Sin programación: no hay EPG todavía y no
/// se inventan horarios.
///
///   Arriba/Abajo: recorre los canales.  Izquierda: a la categoría elegida
///   (y desde ahí, el menú).  Derecha desde las categorías: al último canal
///   elegido de esa categoría, o al primero.
///   OK: pantalla completa (con zapping por esta misma lista).
///   Los números del control saltan al canal con ese número.
///   Al volver de un canal el foco sigue en él; si no andaba y se escondió,
///   en el que quedó en su lugar ([LugarDelFoco]).
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/modelos.dart';
import '../movil/datos.dart';
import '../movil/estilo.dart';
import 'estructura.dart';
import 'foco.dart';
import 'piezas.dart';
import 'reproductor.dart';

class GuiaTv extends StatefulWidget {
  const GuiaTv({super.key});

  @override
  State<GuiaTv> createState() => _GuiaTvState();
}

class _GuiaTvState extends State<GuiaTv> {
  static const _altoFila = 96.0;

  String? _categoria;
  final _lista = ScrollController();
  String _numero = '';
  Timer? _numeroListo;

  /// Un nodo de foco por categoría ('' = Todos) y por canal, para llevar el
  /// foco a uno en particular al ir de un lado al otro.
  final _nodosDeCategorias = <String, FocusNode>{};
  final _nodosDeCanales = <int, FocusNode>{};

  /// El último canal elegido (para volver a él con Derecha).
  int? _ultimoCanal;

  final _lugar = LugarDelFoco();

  /// Lo que no anda se saca de la lista enseguida (y el foco pasa al de al lado).
  Catalogo? _catalogo;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final catalogo = DatosScope.of(context).catalogo;
    if (identical(catalogo, _catalogo)) return;
    _catalogo?.removeListener(_alCambiarElCatalogo);
    _catalogo = catalogo..addListener(_alCambiarElCatalogo);
  }

  void _alCambiarElCatalogo() {
    if (!mounted) return;
    setState(() {});
    final otro = _lugar.reemplazo(lista: _categoria ?? '', ids: [for (final c in _canales(_catalogo!)) c.id]);
    if (otro != null) _enfocarAlVolver(otro);
  }

  /// El canal elegido se escondió (no andaba), seguramente con el canal
  /// encima: apenas se vuelve a la guía, el foco va al que quedó en su lugar
  /// (si no, volvía al anterior). Solo si el foco está en la lista de canales.
  Timer? _esperaVolver;

  void _enfocarAlVolver(int id) {
    _esperaVolver?.cancel();
    _esperaVolver = Timer.periodic(const Duration(milliseconds: 250), (reloj) {
      if (!mounted) return reloj.cancel();
      if (!(ModalRoute.of(context)?.isCurrent ?? false)) return;
      reloj.cancel();
      final actual = FocusManager.instance.primaryFocus;
      final enLaLista = actual is FocusScopeNode || _nodosDeCanales.containsValue(actual);
      final nodo = _nodosDeCanales[id];
      if (enLaLista && nodo?.context != null) nodo!.requestFocus();
    });
  }

  List<Canal> _canales(Catalogo catalogo) =>
      _categoria == null ? catalogo.canales : catalogo.canales.where((c) => c.categoria == _categoria).toList();

  @override
  void dispose() {
    _catalogo?.removeListener(_alCambiarElCatalogo);
    _esperaVolver?.cancel();
    _lista.dispose();
    _numeroListo?.cancel();
    for (final nodo in [..._nodosDeCategorias.values, ..._nodosDeCanales.values]) {
      nodo.dispose();
    }
    super.dispose();
  }

  // Con el mismo nombre que les pone Enfocable (con un nodo propio no lo hace solo)
  FocusNode _nodoDeCategoria(String? valor, [String texto = '']) =>
      _nodosDeCategorias.putIfAbsent(valor ?? '', () => FocusNode(debugLabel: texto));

  FocusNode _nodoDeCanal(Canal canal) => _nodosDeCanales.putIfAbsent(
    canal.id,
    () => FocusNode(debugLabel: 'Canal ${DatosScope.of(context).catalogo.numeroDe(canal)}, ${canal.nombre}'),
  );

  /// Derecha en las categorías: a los canales (al último elegido de esta lista, o al primero).
  KeyEventResult _teclaEnCategorias(FocusNode _, KeyEvent evento, List<Canal> canales) {
    if (evento is KeyUpEvent || evento.logicalKey != LogicalKeyboardKey.arrowRight || canales.isEmpty) {
      return KeyEventResult.ignored;
    }
    final indice = canales.indexWhere((c) => c.id == _ultimoCanal);
    final destino = canales[indice < 0 ? 0 : indice];
    final nodo = _nodoDeCanal(destino);
    if (nodo.context != null) {
      nodo.requestFocus();
    } else if (_lista.hasClients) {
      // Todavía no está dibujado (quedó lejos en la lista): primero se lleva la lista hasta él
      final posicion = _lista.position;
      _lista.jumpTo(((indice < 0 ? 0 : indice) * _altoFila).clamp(0, posicion.maxScrollExtent));
      WidgetsBinding.instance.addPostFrameCallback((_) => _nodoDeCanal(destino).requestFocus());
    }
    return KeyEventResult.handled;
  }

  /// Izquierda en los canales: recuerda en cuál estaba y va a la categoría elegida.
  KeyEventResult _teclaEnCanales(FocusNode _, KeyEvent evento) {
    if (evento is KeyUpEvent || evento.logicalKey != LogicalKeyboardKey.arrowLeft) return KeyEventResult.ignored;
    final actual = FocusManager.instance.primaryFocus;
    for (final MapEntry(:key, :value) in _nodosDeCanales.entries) {
      if (value == actual) _ultimoCanal = key;
    }
    _nodoDeCategoria(_categoria).requestFocus();
    return KeyEventResult.handled;
  }

  /// Escribir un número con el control: a los 1,5 s abre ese canal.
  KeyEventResult _tecla(FocusNode _, KeyEvent evento) {
    if (evento is KeyUpEvent) return KeyEventResult.ignored;
    final caracter = evento.character;
    if (caracter == null || !RegExp(r'^\d$').hasMatch(caracter)) return KeyEventResult.ignored;
    _numeroListo?.cancel();
    setState(() => _numero = (_numero + caracter).length > 3 ? caracter : _numero + caracter);
    _numeroListo = Timer(const Duration(milliseconds: 1500), () {
      final catalogo = DatosScope.of(context).catalogo;
      final canal = catalogo.canalPorNumero(_numero);
      setState(() => _numero = '');
      if (canal != null) {
        verCanalTv(context, canal);
      } else {
        avisoTv(context, 'No hay un canal con ese número', icono: Icons.info_outline_rounded);
      }
    });
    return KeyEventResult.handled;
  }

  @override
  Widget build(BuildContext context) {
    final datos = DatosScope.of(context);
    final catalogo = datos.catalogo;
    final biblioteca = datos.biblioteca;
    final canales = _canales(catalogo);

    return Focus(
      // Solo escucha los números del control. No puede tener el foco: si no, Derecha desde las
      // categorías lo elegía a él (ocupa toda la pantalla) y no se llegaba nunca a los canales.
      canRequestFocus: false,
      skipTraversal: true,
      onKeyEvent: _tecla,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          EncabezadoTv(
            sobretitulo: 'Televisión',
            titulo: 'Guía de canales',
            accion: _numero.isNotEmpty
                ? Text(
                    _numero.padRight(3, '_'),
                    style: const TextStyle(
                      fontFamily: Letra.titulos,
                      fontSize: 44,
                      fontWeight: FontWeight.w800,
                      letterSpacing: 4,
                      color: Tono.dorado,
                    ),
                  )
                : BotonTv(
                    texto: 'Buscar canal',
                    icono: Icons.search_rounded,
                    alOk: () => NavegacionTv.of(context).irA(SeccionTv.buscar),
                  ),
          ),
          const SizedBox(height: 22),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(MargenTv.izquierda, 0, MargenTv.derecha, MargenTv.abajo),
              child: Container(
                decoration: BoxDecoration(
                  color: Tono.capaBaja,
                  borderRadius: BorderRadius.circular(Curva.panel),
                  border: Border.all(color: Tono.bordeSuave.withValues(alpha: .5)),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    // Categorías
                    SizedBox(
                      width: 330,
                      child: Focus(
                        canRequestFocus: false,
                        skipTraversal: true,
                        onKeyEvent: (nodo, evento) => _teclaEnCategorias(nodo, evento, canales),
                        child: FocusTraversalGroup(
                          child: ListView(
                            padding: const EdgeInsets.fromLTRB(24, 26, 24, 26),
                            children: [
                              const Padding(
                                padding: EdgeInsets.only(left: 4, bottom: 14),
                                child: Text('Categorías', style: LetraTv.tarjeta),
                              ),
                              for (final (valor, texto) in [
                                (null, 'Todos'),
                                for (final c in catalogo.categoriasEnVivo)
                                  (c.nombre, categoriaLegible(c.nombre).isEmpty ? 'Otros' : categoriaLegible(c.nombre)),
                              ])
                                Padding(
                                  padding: const EdgeInsets.only(bottom: 12),
                                  child: _Categoria(
                                    texto: texto,
                                    nodo: _nodoDeCategoria(valor, texto),
                                    activa: valor == _categoria,
                                    alOk: () {
                                      setState(() {
                                        _categoria = valor;
                                        _ultimoCanal = null;
                                      });
                                      if (_lista.hasClients) _lista.jumpTo(0);
                                    },
                                  ),
                                ),
                              const SizedBox(height: 14),
                              Container(
                                padding: const EdgeInsets.all(18),
                                decoration: BoxDecoration(
                                  color: Tono.celeste.withValues(alpha: .07),
                                  borderRadius: BorderRadius.circular(Curva.boton),
                                  border: Border.all(color: Tono.celeste.withValues(alpha: .25)),
                                ),
                                child: const Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      'Tip',
                                      style: TextStyle(
                                        fontFamily: Letra.texto,
                                        fontSize: 16,
                                        fontWeight: FontWeight.w800,
                                        color: Tono.celesteClaro,
                                      ),
                                    ),
                                    SizedBox(height: 4),
                                    Text(
                                      'Escribí el número de un canal con el control para ir directo.',
                                      style: LetraTv.ayuda,
                                    ),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                    const VerticalDivider(width: 1, color: Tono.capaMaxima),
                    // Canales
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Padding(
                            padding: const EdgeInsets.fromLTRB(32, 22, 32, 4),
                            child: Row(
                              children: [
                                const Expanded(
                                  child: Text(
                                    '↑ ↓ cambiar · OK pantalla completa · OK largo: favorito',
                                    style: LetraTv.ayuda,
                                  ),
                                ),
                                Text('${canales.length} canales', style: LetraTv.ayuda),
                              ],
                            ),
                          ),
                          Expanded(
                            child: Focus(
                              canRequestFocus: false,
                              skipTraversal: true,
                              onKeyEvent: _teclaEnCanales,
                              child: FocusTraversalGroup(
                                child: ListView.builder(
                                  key: ValueKey(_categoria),
                                  controller: _lista,
                                  clipBehavior: Clip.hardEdge,
                                  padding: const EdgeInsets.fromLTRB(28, 12, 28, 24),
                                  itemExtent: _altoFila,
                                  itemCount: canales.length,
                                  itemBuilder: (context, i) {
                                    final canal = canales[i];
                                    final clave = Biblioteca.claveDe(canal);
                                    final lista = _categoria ?? '';
                                    return Padding(
                                      padding: const EdgeInsets.symmetric(vertical: 8),
                                      child: _lugar.anotar(
                                        lista: lista,
                                        id: canal.id,
                                        lugar: i,
                                        child: FilaCanalTv(
                                          canal: canal,
                                          nodo: _nodoDeCanal(canal),
                                          numero: catalogo.numeroDe(canal),
                                          autofocus: _lugar.esInicial(
                                            lista: lista,
                                            ids: [for (final c in canales) c.id],
                                            lugar: i,
                                            primera: true,
                                            listas: [lista],
                                          ),
                                          favorito: biblioteca.estaEnMiLista(clave),
                                          ayuda: 'OK · Pantalla completa',
                                          alOk: () => verCanalTv(context, canal, lista: canales),
                                          alOkLargo: () => alternarFavoritoTv(context, clave),
                                        ),
                                      ),
                                    );
                                  },
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
          ),
        ],
      ),
    );
  }
}

class _Categoria extends StatelessWidget {
  const _Categoria({required this.texto, required this.nodo, required this.activa, required this.alOk});

  final String texto;
  final FocusNode nodo;
  final bool activa;
  final VoidCallback alOk;

  @override
  Widget build(BuildContext context) {
    return Enfocable(
      nodo: nodo,
      alOk: alOk,
      curva: 99,
      escala: 1.03,
      etiqueta: texto,
      child: Container(
        height: 54,
        padding: const EdgeInsets.symmetric(horizontal: 22),
        alignment: Alignment.centerLeft,
        decoration: BoxDecoration(
          color: activa ? Tono.celeste.withValues(alpha: .12) : Tono.capa,
          borderRadius: BorderRadius.circular(99),
          border: Border.all(color: activa ? Tono.celeste : Tono.bordeSuave.withValues(alpha: .5), width: 1.5),
        ),
        child: Text(
          texto,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            fontFamily: Letra.texto,
            fontSize: 18,
            fontWeight: FontWeight.w700,
            color: activa ? Tono.celesteClaro : Tono.texto,
          ),
        ),
      ),
    );
  }
}
