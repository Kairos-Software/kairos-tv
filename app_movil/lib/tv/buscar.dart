/// Buscar en la TV (diseno_kairos_tv: tv-14): un teclado en pantalla que se
/// maneja con las flechas (también sirve un teclado o el micrófono del
/// control, si escribe), y los resultados a la derecha.
///
/// Con el control:
///   - el foco arranca en la letra "A";
///   - DERECHA (desde el borde derecho del teclado) pasa a los resultados, e
///     IZQUIERDA desde los resultados vuelve al teclado. Abajo del teclado lo
///     dice, para que se sepa;
///   - arriba de los resultados, los filtros Todo / En vivo / Películas /
///     Series, con cuántos encontró cada uno. Arranca en el de la sección
///     desde donde se vino (desde Series, series). En "Todo" también está lo
///     de las secciones nuevas (Música, Radio...).
/// La búsqueda en sí está en movil/busqueda.dart (es la misma del celular).
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../movil/busqueda.dart';
import '../movil/componentes.dart';
import '../movil/datos.dart';
import '../movil/estilo.dart';
import 'detalle.dart';
import 'estructura.dart';
import 'foco.dart';
import 'piezas.dart';
import 'reproductor.dart';

class BuscarTv extends StatefulWidget {
  const BuscarTv({super.key, this.que = QueBuscar.todo});

  /// Qué se busca al abrir.
  final QueBuscar que;

  /// Lo que se busca viniendo de cada sección.
  static QueBuscar queDesde(SeccionTv seccion) => switch (seccion) {
    SeccionTv.enVivo || SeccionTv.guia => QueBuscar.enVivo,
    SeccionTv.peliculas => QueBuscar.peliculas,
    SeccionTv.series => QueBuscar.series,
    _ => QueBuscar.todo,
  };

  @override
  State<BuscarTv> createState() => _BuscarTvState();
}

class _BuscarTvState extends State<BuscarTv> {
  static const _maximo = 40;
  String _texto = '';
  late QueBuscar _que = widget.que;

  /// El primer resultado: DERECHA desde el teclado lleva acá.
  final _primerResultado = FocusNode(debugLabel: 'primer resultado');

  /// Todo el teclado (para saber si el foco salió de él).
  final _teclado = FocusNode(debugLabel: 'teclado', canRequestFocus: false, skipTraversal: true);

  @override
  void dispose() {
    _primerResultado.dispose();
    _teclado.dispose();
    super.dispose();
  }

  void _escribir(String letra) => setState(() => _texto += letra);

  void _borrar() {
    if (_texto.isNotEmpty) setState(() => _texto = _texto.substring(0, _texto.length - 1));
  }

  /// Un teclado de verdad (o el micrófono del control) también escribe.
  KeyEventResult _tecla(FocusNode _, KeyEvent evento) {
    if (evento is KeyUpEvent) return KeyEventResult.ignored;
    if (evento.logicalKey == LogicalKeyboardKey.backspace) {
      _borrar();
      return KeyEventResult.handled;
    }
    final caracter = evento.character;
    if (caracter != null && RegExp(r'^[\p{L}\p{N} ]$', unicode: true).hasMatch(caracter)) {
      _escribir(caracter);
      return KeyEventResult.handled;
    }
    return KeyEventResult.ignored;
  }

  /// DERECHA en el teclado: se mueve entre las teclas y, desde la última de la
  /// fila, va SIEMPRE al primer resultado (no a los filtros, aunque queden
  /// más cerca de las filas de arriba). Sin resultados, a los filtros.
  KeyEventResult _teclaEnElTeclado(FocusNode _, KeyEvent evento) {
    if (evento is KeyUpEvent || evento.logicalKey != LogicalKeyboardKey.arrowRight) return KeyEventResult.ignored;
    final actual = FocusManager.instance.primaryFocus;
    if (actual == null) return KeyEventResult.ignored;
    // ¿Hay otra tecla a la derecha, en la misma fila?
    final fila = actual.rect;
    final hayOtra = _teclado.traversalDescendants.any(
      (tecla) =>
          tecla != actual && tecla.rect.left >= fila.right - 1 && (tecla.rect.center.dy - fila.center.dy).abs() < 4,
    );
    if (hayOtra || _primerResultado.context == null) return KeyEventResult.ignored; // se mueve como siempre
    _primerResultado.requestFocus();
    return KeyEventResult.handled;
  }

  List<Widget> _resultados(Encontrado encontrado) {
    final catalogo = DatosScope.of(context).catalogo;
    bool muestra(QueBuscar que) => _que == QueBuscar.todo || _que == que;
    final resultados = <Widget>[
      if (muestra(QueBuscar.enVivo))
        for (final canal in encontrado.canales)
          _Resultado(
            imagen: LogoCanalTv(canal: canal, tamanioIniciales: 20, relleno: const EdgeInsets.all(6)),
            titulo: canal.nombre,
            subtitulo: [
              'Canal ${catalogo.numeroDe(canal)}',
              if (categoriaLegible(canal.categoria).isNotEmpty) categoriaLegible(canal.categoria),
            ].join(' · '),
            alOk: () => verCanalTv(context, canal),
          ),
      if (muestra(QueBuscar.peliculas))
        for (final pelicula in encontrado.peliculas)
          _Resultado(
            imagen: Imagen(url: pelicula.logo, nombre: pelicula.nombre, tamanioIniciales: 16),
            poster: true,
            titulo: sinAnio(pelicula.nombre),
            subtitulo: anioDe(pelicula.nombre) == null ? 'Película' : 'Película · ${anioDe(pelicula.nombre)}',
            alOk: () => abrirTv<void>(context, DetalleTv.pelicula(pelicula)),
          ),
      if (muestra(QueBuscar.series))
        for (final serie in encontrado.series)
          _Resultado(
            imagen: Imagen(url: serie.imagen, nombre: serie.nombre, tamanioIniciales: 16),
            poster: true,
            titulo: serie.nombre,
            subtitulo: 'Serie · ${serie.cantidadDeCapitulos} capítulos',
            alOk: () => abrirTv<void>(context, DetalleTv.serie(serie)),
          ),
      if (_que == QueBuscar.todo)
        for (final (seccion, lista) in encontrado.nuevas)
          for (final canal in lista)
            seccion.enVivo
                ? _Resultado(
                    imagen: LogoCanalTv(canal: canal, tamanioIniciales: 20, relleno: const EdgeInsets.all(6)),
                    titulo: canal.nombre,
                    subtitulo: [
                      seccion.nombre,
                      if (categoriaLegible(canal.categoria).isNotEmpty) categoriaLegible(canal.categoria),
                    ].join(' · '),
                    alOk: () => verCanalTv(context, canal, lista: seccion.canales),
                  )
                : _Resultado(
                    imagen: Imagen(url: canal.logo, nombre: canal.nombre, tamanioIniciales: 16),
                    poster: true,
                    titulo: sinAnio(canal.nombre),
                    subtitulo: [
                      seccion.nombre,
                      if (categoriaLegible(canal.categoria).isNotEmpty) categoriaLegible(canal.categoria),
                    ].join(' · '),
                    alOk: () => abrirTv<void>(context, DetalleTv.pelicula(canal)),
                  ),
    ].take(_maximo).toList();
    if (resultados.isEmpty) return resultados;
    // El primero lleva el nodo al que se llega con DERECHA desde el teclado
    final primero = resultados.first as _Resultado;
    resultados[0] = primero.conNodo(_primerResultado);
    return resultados;
  }

  @override
  Widget build(BuildContext context) {
    final catalogo = DatosScope.of(context).catalogo;
    final buscado = _texto.trim();
    final encontrado = buscarEnCatalogo(catalogo, buscado, maximo: _maximo, conNumeros: true);
    final resultados = _resultados(encontrado);

    return Focus(
      // Solo escucha lo que se escribe con un teclado de verdad. NO se puede
      // elegir: antes sí, y DERECHA desde el final de una fila caía en "toda
      // la pantalla" (nada quedaba marcado y parecía que el control no andaba).
      canRequestFocus: false,
      skipTraversal: true,
      onKeyEvent: _tecla,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(MargenTv.izquierda, MargenTv.arriba + 14, MargenTv.derecha, 0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text('CATÁLOGO', style: LetraTv.sobretitulo),
            const SizedBox(height: 4),
            const Text('Buscar', style: LetraTv.pantalla),
            const SizedBox(height: 22),
            // Lo escrito (no es un campo de texto: se escribe con el teclado de abajo)
            Container(
              height: 68,
              padding: const EdgeInsets.symmetric(horizontal: 24),
              decoration: BoxDecoration(
                color: Tono.capaBaja,
                borderRadius: BorderRadius.circular(Curva.boton),
                border: Border.all(color: Tono.celeste.withValues(alpha: .7), width: 2),
                boxShadow: brilloCeleste(desenfoque: 24, opacidad: .2),
              ),
              child: Row(
                children: [
                  const Icon(Icons.search_rounded, color: Tono.textoSuave, size: 28),
                  const SizedBox(width: 16),
                  Text(
                    _texto.isEmpty ? _ayuda : _texto,
                    style: TextStyle(
                      fontFamily: Letra.texto,
                      fontSize: 24,
                      color: _texto.isEmpty ? Tono.textoApagado : Tono.texto,
                    ),
                  ),
                  if (_texto.isNotEmpty) Container(width: 2, height: 30, color: Tono.celeste),
                ],
              ),
            ),
            const SizedBox(height: 28),
            Expanded(
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SizedBox(
                    width: 560,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('Teclado', style: LetraTv.tarjeta),
                        const SizedBox(height: 14),
                        Focus(
                          focusNode: _teclado,
                          onKeyEvent: _teclaEnElTeclado,
                          child: _Teclado(
                            alLetra: _escribir,
                            alBorrar: _borrar,
                            alLimpiar: () => setState(() => _texto = ''),
                          ),
                        ),
                        const SizedBox(height: 20),
                        _Indicacion(
                          texto: resultados.isEmpty
                              ? 'También podés escribir con el micrófono del control.'
                              : 'Con la flecha DERECHA ▶ vas a los resultados.',
                          destacada: resultados.isNotEmpty,
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 48),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // Los filtros, en una fila
                        FocusTraversalGroup(
                          child: Row(
                            children: [
                              for (final que in QueBuscar.values) ...[
                                if (que != QueBuscar.values.first) const SizedBox(width: 12),
                                ChipTv(
                                  texto: buscado.isEmpty ? que.texto : '${que.texto} (${encontrado.cuantos(que)})',
                                  activo: _que == que,
                                  alOk: () => setState(() => _que = que),
                                ),
                              ],
                            ],
                          ),
                        ),
                        const SizedBox(height: 18),
                        Expanded(
                          child: buscado.isEmpty
                              ? Text('Escribí con el teclado de la izquierda.', style: LetraTv.cuerpo)
                              : resultados.isEmpty
                              ? Text(
                                  _que == QueBuscar.todo || encontrado.vacio(QueBuscar.todo)
                                      ? 'No encontramos "$_texto".'
                                      : 'No hay ${_que.texto.toLowerCase()} con "$_texto". Probá en "Todo".',
                                  style: LetraTv.cuerpo,
                                )
                              : FocusTraversalGroup(
                                  child: ListView.separated(
                                    clipBehavior: Clip.none,
                                    padding: const EdgeInsets.only(bottom: 40, right: 8),
                                    itemCount: resultados.length,
                                    separatorBuilder: (_, _) => const SizedBox(height: 14),
                                    itemBuilder: (_, i) => resultados[i],
                                  ),
                                ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  String get _ayuda => switch (_que) {
    QueBuscar.todo => 'Canal, película o serie',
    QueBuscar.enVivo => 'Nombre o número del canal',
    QueBuscar.peliculas => 'Nombre de la película',
    QueBuscar.series => 'Nombre de la serie',
  };
}

/// Una línea de ayuda debajo del teclado (celeste cuando hay algo que hacer).
class _Indicacion extends StatelessWidget {
  const _Indicacion({required this.texto, required this.destacada});

  final String texto;
  final bool destacada;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(
          destacada ? Icons.arrow_forward_rounded : Icons.mic_none_rounded,
          size: 22,
          color: destacada ? Tono.celeste : Tono.textoSuave,
        ),
        const SizedBox(width: 10),
        Expanded(
          child: Text(
            texto,
            style: LetraTv.ayuda.copyWith(
              fontSize: 17,
              color: destacada ? Tono.celesteClaro : Tono.textoSuave,
              fontWeight: destacada ? FontWeight.w700 : FontWeight.w500,
            ),
          ),
        ),
      ],
    );
  }
}

class _Teclado extends StatelessWidget {
  const _Teclado({required this.alLetra, required this.alBorrar, required this.alLimpiar});

  final ValueChanged<String> alLetra;
  final VoidCallback alBorrar;
  final VoidCallback alLimpiar;

  static const _filas = ['ABCDEFGHIJ', 'KLMNÑOPQRS', 'TUVWXYZ', '1234567890'];

  @override
  Widget build(BuildContext context) {
    Widget tecla(String texto, VoidCallback alOk, {double ancho = 48, bool autofocus = false}) => Padding(
      padding: const EdgeInsets.all(4),
      child: Enfocable(
        alOk: alOk,
        autofocus: autofocus,
        curva: Curva.medio + 2,
        escala: 1.1,
        etiqueta: texto,
        child: Container(
          width: ancho,
          height: 52,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: Tono.capaAlta,
            borderRadius: BorderRadius.circular(Curva.medio + 2),
            border: Border.all(color: Tono.bordeSuave.withValues(alpha: .45)),
          ),
          child: Text(
            texto,
            style: const TextStyle(
              fontFamily: Letra.texto,
              fontSize: 19,
              fontWeight: FontWeight.w700,
              color: Tono.texto,
            ),
          ),
        ),
      ),
    );

    return FocusTraversalGroup(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final (f, fila) in _filas.indexed)
            Row(
              children: [
                for (final (i, letra) in fila.split('').indexed)
                  tecla(letra, () => alLetra(letra.toLowerCase()), autofocus: f == 0 && i == 0),
                if (f == 2) tecla('Borrar', alBorrar, ancho: 112),
              ],
            ),
          Row(children: [tecla('Espacio', () => alLetra(' '), ancho: 216), tecla('Limpiar', alLimpiar, ancho: 160)]),
        ],
      ),
    );
  }
}

class _Resultado extends StatelessWidget {
  const _Resultado({
    required this.imagen,
    required this.titulo,
    required this.subtitulo,
    required this.alOk,
    this.poster = false,
    this.nodo,
  });

  final Widget imagen;
  final String titulo;
  final String subtitulo;
  final VoidCallback alOk;
  final bool poster;
  final FocusNode? nodo;

  _Resultado conNodo(FocusNode nodo) =>
      _Resultado(imagen: imagen, titulo: titulo, subtitulo: subtitulo, alOk: alOk, poster: poster, nodo: nodo);

  @override
  Widget build(BuildContext context) {
    return Enfocable(
      alOk: alOk,
      nodo: nodo,
      curva: Curva.tarjeta,
      escala: 1.02,
      etiqueta: '$titulo, $subtitulo',
      child: Container(
        height: 88,
        padding: const EdgeInsets.symmetric(horizontal: 18),
        decoration: BoxDecoration(
          color: Tono.capa,
          borderRadius: BorderRadius.circular(Curva.tarjeta),
          border: Border.all(color: Tono.bordeSuave.withValues(alpha: .45)),
        ),
        child: Row(
          children: [
            ClipRRect(
              borderRadius: BorderRadius.circular(Curva.medio),
              child: Container(width: poster ? 46 : 72, height: poster ? 68 : 52, color: Tono.capaAlta, child: imagen),
            ),
            const SizedBox(width: 18),
            Expanded(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    titulo,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontFamily: Letra.texto,
                      fontSize: 20,
                      fontWeight: FontWeight.w700,
                      color: Tono.texto,
                    ),
                  ),
                  Text(subtitulo, style: LetraTv.ayuda.copyWith(fontSize: 15)),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
