/// Las piezas que se repiten en las pantallas de la TV (diseno_kairos_tv/html/tv-*):
/// encabezado, chips, tarjetas de canal y de póster, filas, avisos.
/// Medidas en el lienzo de 1920×1080 (ver escala.dart).
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../api/modelos.dart';
import '../movil/componentes.dart';
import '../movil/datos.dart';
import '../movil/estilo.dart';
import '../movil/logo_legible.dart';
import 'foco.dart';

/// Márgenes: a la izquierda queda el menú (88 px cerrado); a la derecha, el margen seguro de la TV.
class MargenTv {
  static const izquierda = 152.0;
  static const derecha = 96.0;
  static const arriba = 54.0;
  static const abajo = 54.0;
}

/// "TELEVISIÓN" en celeste y el título grande; a la derecha, una acción (ej: "Buscar").
class EncabezadoTv extends StatelessWidget {
  const EncabezadoTv({super.key, required this.sobretitulo, required this.titulo, this.accion});

  final String sobretitulo;
  final String titulo;
  final Widget? accion;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(MargenTv.izquierda, MargenTv.arriba + 14, MargenTv.derecha, 0),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(sobretitulo.toUpperCase(), style: LetraTv.sobretitulo),
                const SizedBox(height: 4),
                Text(titulo, maxLines: 1, overflow: TextOverflow.ellipsis, style: LetraTv.pantalla),
              ],
            ),
          ),
          ?accion,
        ],
      ),
    );
  }
}

/// Un filtro (categoría). El activo: borde y texto celestes.
class ChipTv extends StatelessWidget {
  const ChipTv({super.key, required this.texto, required this.activo, required this.alOk, this.autofocus = false});

  final String texto;
  final bool activo;
  final VoidCallback alOk;
  final bool autofocus;

  @override
  Widget build(BuildContext context) {
    return Enfocable(
      alOk: alOk,
      autofocus: autofocus,
      curva: 99,
      escala: 1.05,
      etiqueta: texto,
      child: Container(
        height: 46,
        padding: const EdgeInsets.symmetric(horizontal: 22),
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: activo ? Tono.celeste.withValues(alpha: .12) : Tono.capa,
          borderRadius: BorderRadius.circular(99),
          border: Border.all(color: activo ? Tono.celeste : Tono.bordeSuave.withValues(alpha: .6), width: 1.5),
        ),
        child: Text(
          texto,
          style: TextStyle(
            fontFamily: Letra.texto,
            fontSize: 17,
            fontWeight: FontWeight.w700,
            color: activo ? Tono.celesteClaro : Tono.textoSuave,
          ),
        ),
      ),
    );
  }
}

/// La fila de chips de categorías, con desplazamiento horizontal.
class FilaChipsTv extends StatelessWidget {
  const FilaChipsTv({super.key, required this.opciones, required this.activa, required this.alElegir});

  /// (valor, texto). El valor null es "Todo".
  final List<(String?, String)> opciones;
  final String? activa;
  final ValueChanged<String?> alElegir;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 70,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        clipBehavior: Clip.none,
        padding: const EdgeInsets.fromLTRB(MargenTv.izquierda, 12, MargenTv.derecha, 12),
        itemCount: opciones.length,
        separatorBuilder: (_, _) => const SizedBox(width: 12),
        itemBuilder: (_, i) {
          final (valor, texto) = opciones[i];
          return ChipTv(texto: texto, activo: valor == activa, alOk: () => alElegir(valor));
        },
      ),
    );
  }
}

/// "● EN VIVO" en rubí, tamaño TV.
class InsigniaEnVivoTv extends StatelessWidget {
  const InsigniaEnVivoTv({super.key, this.grande = false});

  final bool grande;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(horizontal: grande ? 16 : 12, vertical: grande ? 8 : 6),
      decoration: BoxDecoration(color: Tono.rubi, borderRadius: BorderRadius.circular(99)),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          PuntoEnVivo(tamanio: grande ? 9 : 7),
          SizedBox(width: grande ? 8 : 7),
          Text(
            'EN VIVO',
            style: TextStyle(
              fontFamily: Letra.texto,
              fontSize: grande ? 15 : 13,
              fontWeight: FontWeight.w800,
              letterSpacing: 1,
              color: Tono.sobreRubi,
            ),
          ),
        ],
      ),
    );
  }
}

/// Las iniciales de un canal sin logo (hasta 3 letras), grandes.
String inicialesCanal(String nombre) {
  final palabras = nombre.split(RegExp(r'\s+')).where((p) => p.isNotEmpty).toList();
  if (palabras.isEmpty) return 'TV';
  if (palabras.length == 1) {
    final p = palabras.first;
    return (p.length <= 3 ? p : p.substring(0, 2)).toUpperCase();
  }
  return palabras.take(3).map((p) => p[0]).join().toUpperCase();
}

/// El logo de un canal (sin deformar: "contain") o sus iniciales.
class LogoCanalTv extends StatelessWidget {
  const LogoCanalTv({super.key, required this.canal, this.tamanioIniciales = 46, this.relleno = EdgeInsets.zero});

  final Canal canal;
  final double tamanioIniciales;
  final EdgeInsets relleno;

  @override
  Widget build(BuildContext context) {
    final iniciales = Center(
      child: Text(
        inicialesCanal(canal.nombre),
        maxLines: 1,
        style: TextStyle(
          fontFamily: Letra.titulos,
          fontSize: tamanioIniciales,
          fontWeight: FontWeight.w800,
          letterSpacing: -1,
          color: Tono.celesteClaro,
        ),
      ),
    );
    if (canal.logo.isEmpty) return iniciales;
    return Padding(
      padding: relleno,
      // Si es oscuro, sobre una placa clara (movil/logo_legible.dart)
      child: LogoLegible(
        url: canal.logo,
        imagen: Image.network(
          canal.logo,
          fit: BoxFit.contain,
          errorBuilder: (_, _, _) => iniciales,
          frameBuilder: (_, imagen, cuadro, sincronica) => sincronica || cuadro != null ? imagen : iniciales,
        ),
      ),
    );
  }
}

/// La tarjeta de un canal en vivo: EN VIVO, número, logo y nombre.
class TarjetaCanalTv extends StatelessWidget {
  const TarjetaCanalTv({
    super.key,
    required this.canal,
    required this.numero,
    required this.alOk,
    this.alOkLargo,
    this.favorito = false,
    this.autofocus = false,
    this.ancho = 290,
    this.nodo,
  });

  final Canal canal;
  final String numero;
  final VoidCallback alOk;
  final VoidCallback? alOkLargo;
  final bool favorito;
  final bool autofocus;
  final double ancho;
  final FocusNode? nodo;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: ancho,
      height: ancho * 164 / 290,
      child: Enfocable(
        alOk: alOk,
        alOkLargo: alOkLargo,
        autofocus: autofocus,
        nodo: nodo,
        curva: Curva.tarjeta,
        etiqueta: 'Canal $numero, ${canal.nombre}',
        child: DecoratedBox(
          decoration: BoxDecoration(
            gradient: const LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [Tono.capa, Tono.capaMinima],
            ),
            borderRadius: BorderRadius.circular(Curva.tarjeta),
            border: Border.all(color: Tono.bordeSuave.withValues(alpha: .55)),
          ),
          child: Stack(
            fit: StackFit.expand,
            children: [
              Positioned.fill(
                top: 40,
                bottom: 40,
                child: LogoCanalTv(canal: canal, relleno: const EdgeInsets.symmetric(horizontal: 60, vertical: 4)),
              ),
              const Positioned(top: 12, left: 12, child: InsigniaEnVivoTv()),
              Positioned(
                top: 14,
                right: 16,
                child: Row(
                  children: [
                    if (favorito) ...[
                      const Icon(Icons.favorite_rounded, size: 17, color: Tono.rubi),
                      const SizedBox(width: 8),
                    ],
                    Text(
                      numero,
                      style: const TextStyle(
                        fontFamily: Letra.texto,
                        fontSize: 17,
                        fontWeight: FontWeight.w700,
                        color: Tono.textoSuave,
                      ),
                    ),
                  ],
                ),
              ),
              Positioned(
                left: 16,
                right: 16,
                bottom: 14,
                child: Text(
                  canal.nombre,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontFamily: Letra.texto,
                    fontSize: 18,
                    fontWeight: FontWeight.w700,
                    color: Tono.texto,
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

/// El póster 2:3 de una película o serie, con el título abajo y la barra de lo visto.
class TarjetaPosterTv extends StatelessWidget {
  const TarjetaPosterTv({
    super.key,
    required this.titulo,
    required this.imagen,
    required this.alOk,
    this.alOkLargo,
    this.progreso,
    this.favorito = false,
    this.autofocus = false,
    this.ancho = 184,
  });

  final String titulo;
  final String imagen;
  final VoidCallback alOk;
  final VoidCallback? alOkLargo;
  final double? progreso;
  final bool favorito;
  final bool autofocus;
  final double ancho;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: ancho,
      height: ancho * 1.5,
      child: Enfocable(
        alOk: alOk,
        alOkLargo: alOkLargo,
        autofocus: autofocus,
        curva: Curva.tarjeta,
        etiqueta: titulo,
        child: DecoratedBox(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(Curva.tarjeta),
            border: Border.all(color: Tono.bordeSuave.withValues(alpha: .45)),
          ),
          child: Stack(
            fit: StackFit.expand,
            children: [
              Imagen(url: imagen, nombre: titulo, tamanioIniciales: 34),
              const DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.bottomCenter,
                    end: Alignment.topCenter,
                    colors: [Color(0xF00E0E12), Colors.transparent],
                    stops: [0, .55],
                  ),
                ),
              ),
              if (favorito)
                const Positioned(top: 12, right: 12, child: Icon(Icons.favorite_rounded, size: 22, color: Tono.rubi)),
              Positioned(
                left: 16,
                right: 16,
                bottom: progreso != null ? 22 : 16,
                child: Text(
                  titulo,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: LetraTv.tarjeta.copyWith(
                    fontSize: 19,
                    height: 1.2,
                    shadows: const [Shadow(color: Colors.black87, blurRadius: 8)],
                  ),
                ),
              ),
              if (progreso != null)
                Positioned(left: 0, right: 0, bottom: 0, child: BarraAvance(fraccion: progreso!, alto: 5)),
            ],
          ),
        ),
      ),
    );
  }
}

/// Una fila con título y tarjetas que se recorren con izquierda/derecha.
/// Deja 12 px arriba y abajo para que el foco (que agranda) no se corte.
class FilaTv extends StatelessWidget {
  const FilaTv({
    super.key,
    required this.titulo,
    required this.alto,
    required this.tarjetas,
    this.icono,
    this.final_,
    this.margenIzquierdo = MargenTv.izquierda,
    this.margenDerecho = MargenTv.derecha,
  });

  final String titulo;
  final double alto;
  final List<Widget> tarjetas;
  final Widget? icono;

  /// A la derecha del título (ej: la cantidad).
  final String? final_;

  /// Donde empieza (por defecto, después del menú).
  final double margenIzquierdo;
  final double margenDerecho;

  @override
  Widget build(BuildContext context) {
    if (tarjetas.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(top: 22),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: EdgeInsets.fromLTRB(margenIzquierdo, 0, margenDerecho, 4),
            child: Row(
              children: [
                if (icono != null) ...[icono!, const SizedBox(width: 10)],
                Expanded(child: Text(titulo, style: LetraTv.seccion)),
                if (final_ != null) Text(final_!, style: LetraTv.ayuda),
              ],
            ),
          ),
          SizedBox(
            height: alto + 36,
            child: FocusTraversalGroup(
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                clipBehavior: Clip.none,
                padding: EdgeInsets.fromLTRB(margenIzquierdo, 18, margenDerecho, 18),
                itemCount: tarjetas.length,
                separatorBuilder: (_, _) => const SizedBox(width: 22),
                itemBuilder: (_, i) => tarjetas[i],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Un aviso corto abajo al centro ("Agregado a favoritos"). Se va solo.
void avisoTv(BuildContext context, String texto, {IconData icono = Icons.check_circle_rounded}) {
  final overlay = Overlay.maybeOf(context, rootOverlay: true);
  if (overlay == null) return;
  late final OverlayEntry entrada;
  entrada = OverlayEntry(
    builder: (_) => Positioned(
      left: 0,
      right: 0,
      bottom: 80,
      child: IgnorePointer(
        child: Center(
          child: TweenAnimationBuilder<double>(
            tween: Tween(begin: 0, end: 1),
            duration: const Duration(milliseconds: 180),
            builder: (_, valor, hijo) => Opacity(opacity: valor, child: hijo),
            child: Material(
              color: Colors.transparent,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 26, vertical: 16),
                decoration: BoxDecoration(
                  color: Tono.capaAlta,
                  borderRadius: BorderRadius.circular(Curva.boton),
                  border: Border.all(color: Tono.bordeSuave.withValues(alpha: .6)),
                  boxShadow: const [BoxShadow(color: Colors.black54, blurRadius: 24)],
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(icono, color: Tono.celeste, size: 26),
                    const SizedBox(width: 12),
                    Text(
                      texto,
                      style: const TextStyle(
                        fontFamily: Letra.texto,
                        fontSize: 19,
                        fontWeight: FontWeight.w600,
                        color: Tono.texto,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    ),
  );
  overlay.insert(entrada);
  Timer(const Duration(milliseconds: 2200), entrada.remove);
}

/// Agrega o quita de favoritos y avisa (OK largo sobre una tarjeta).
void alternarFavoritoTv(BuildContext context, String clave) {
  final biblioteca = DatosScope.of(context).biblioteca;
  final estaba = biblioteca.estaEnMiLista(clave);
  biblioteca.alternarMiLista(clave);
  avisoTv(
    context,
    estaba ? 'Quitado de favoritos' : 'Agregado a favoritos',
    icono: estaba ? Icons.heart_broken_rounded : Icons.favorite_rounded,
  );
}

/// Abre una pantalla de la TV encima de la actual, llevándole el catálogo y la biblioteca.
Future<T?> abrirTv<T>(BuildContext context, Widget pantalla) {
  final datos = DatosScope.of(context);
  return Navigator.push<T>(
    context,
    PageRouteBuilder<T>(
      transitionDuration: const Duration(milliseconds: 180),
      reverseTransitionDuration: const Duration(milliseconds: 140),
      pageBuilder: (_, _, _) => DatosScope(
        catalogo: datos.catalogo,
        biblioteca: datos.biblioteca,
        child: Theme(data: temaMovil(), child: pantalla),
      ),
      transitionsBuilder: (_, animacion, _, hijo) => FadeTransition(opacity: animacion, child: hijo),
    ),
  );
}
