/// Inicio (Stitch: "stitch_modern_streaming_app_ui.zip", celular).
///
///   chips de categorías · portada destacada · Tus canales favoritos ·
///   Últimos canales vistos · Directos Destacados Ahora · Continuar Viendo ·
///   Tendencias en Kairos TV (grilla de pósters)
///
/// TV en vivo primero (diseno_kairos_tv/DESIGN.md, principio 1): la portada es
/// el portal de la marca (portal.dart) con un canal (los últimos que se vieron,
/// los favoritos...: va pasando de uno a otro); si no hay canales, una película
/// o serie. Todo con datos reales: favoritos, últimos vistos y
/// "Continuar Viendo" son de la cuenta (lo que se hizo en cualquiera de sus
/// aparatos). Arriba, si se estaba mirando algo en otro aparato: "Seguir acá".
library;

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../api/modelos.dart';
import '../utiles.dart';
import 'mi_agenda.dart';
import 'componentes.dart';
import 'datos.dart';
import 'detalle.dart';
import 'estilo.dart';
import 'estructura.dart';
import 'grilla.dart';
import 'movimiento.dart';
import 'portal.dart';
import 'reproductor_vod.dart';
import 'secciones_nuevas.dart';

class SeccionInicio extends StatefulWidget {
  const SeccionInicio({super.key});

  @override
  State<SeccionInicio> createState() => _SeccionInicioState();
}

class _SeccionInicioState extends State<SeccionInicio> {
  final ValueNotifier<double> _desplazamiento = ValueNotifier(0);

  @override
  void dispose() {
    _desplazamiento.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final datos = DatosScope.of(context);
    return ListenableBuilder(
      listenable: Listenable.merge([datos.catalogo, datos.biblioteca]),
      builder: (context, _) {
        final catalogo = datos.catalogo;
        if (!catalogo.cargado) {
          return catalogo.error != null
              ? Vacio(
                  icono: Icons.wifi_off_rounded,
                  texto: textoDeError(catalogo.error!),
                  accion: TextButton(onPressed: catalogo.cargar, child: const Text('Reintentar')),
                )
              : const Center(child: CircularProgressIndicator());
        }
        return NotificationListener<ScrollUpdateNotification>(
          onNotification: (aviso) {
            if (aviso.depth == 0 && aviso.metrics.axis == Axis.vertical) _desplazamiento.value = aviso.metrics.pixels;
            return false;
          },
          child: RefreshIndicator(
            onRefresh: catalogo.cargar,
            edgeOffset: altoBarraSuperior(context),
            child: ListView(
              padding: EdgeInsets.only(top: altoBarraSuperior(context), bottom: altoBarraInferior(context) + 40),
              children: [
                const Entrada(child: _Chips()),
                const _SeguirAca(),
                Entrada(orden: 1, child: _Portada(desplazamiento: _desplazamiento)),
                // Lo que cada uno anotó con "Recordarme" (mi_agenda.dart)
                const FilaMiAgenda(),
                Entrada(
                  orden: 2,
                  child: _FilaCanales(
                    titulo: 'Tus canales favoritos',
                    icono: const Icon(Icons.favorite_rounded, size: 20, color: Tono.rubi),
                    canales: catalogo.canalesFavoritos(datos.biblioteca),
                  ),
                ),
                Entrada(
                  orden: 3,
                  child: _FilaCanales(
                    titulo: 'Últimos canales vistos',
                    icono: const Icon(Icons.history_rounded, size: 20, color: Tono.celeste),
                    canales: catalogo.canalesRecientes(datos.biblioteca).take(10).toList(),
                  ),
                ),
                const Entrada(orden: 4, child: _DirectosDestacados()),
                const Entrada(orden: 4, child: _ContinuarViendo()),
                const Entrada(orden: 4, child: _Tendencias()),
                if (catalogo.canales.isEmpty &&
                    catalogo.peliculas.isEmpty &&
                    catalogo.series.isEmpty &&
                    catalogo.seccionesNuevas.isEmpty)
                  const Vacio(icono: Icons.tv_off_rounded, texto: 'Todavía no hay contenido disponible.'),
              ],
            ),
          ),
        );
      },
    );
  }
}

/// "Estabas viendo X en la TV — Seguir acá": lo último que se miró en otro
/// aparato de la misma cuenta (Biblioteca.seguirDeOtroAparato). Una
/// película o capítulo sigue en el mismo minuto; un canal, en vivo.
class _SeguirAca extends StatelessWidget {
  const _SeguirAca();

  @override
  Widget build(BuildContext context) {
    final datos = DatosScope.of(context);
    final seguir = datos.biblioteca.seguirDeOtroAparato;
    final canal = seguir == null ? null : datos.catalogo.canalPorId(seguir.id);
    if (seguir == null || canal == null) return const SizedBox.shrink();
    final serie = canal.contenido == 'serie' ? datos.catalogo.serieDe(canal) : null;
    final progreso = seguir.progreso;
    final titulo = serie?.nombre ?? sinAnio(canal.nombre);
    final detalle = progreso == null
        ? 'En vivo · ${hace(seguir.cuando)}'
        : 'Ibas por ${reloj(progreso.posicion)} · ${hace(seguir.cuando)}';
    void seguirAca() {
      datos.biblioteca.descartarSeguir(seguir);
      if (progreso == null) {
        NavegacionMovil.of(context).irA(Seccion.enVivo, canal: canal.id);
      } else {
        reproducirContenido(context, canal, serie: serie, desde: progreso.posicion);
      }
    }

    return Padding(
      padding: const EdgeInsets.fromLTRB(Espacio.margen, 0, Espacio.margen, Espacio.lg),
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: Tono.capa,
          borderRadius: BorderRadius.circular(Curva.tarjeta),
          border: Border.all(color: Tono.celeste.withValues(alpha: .35)),
        ),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(14, 10, 4, 14),
          child: Column(
            children: [
              Row(
                children: [
                  ClipRRect(
                    borderRadius: BorderRadius.circular(Curva.medio),
                    child: SizedBox(
                      width: 64,
                      height: 40,
                      child: Imagen(
                        url: canal.logo.isNotEmpty ? canal.logo : (serie?.imagen ?? ''),
                        nombre: titulo,
                        ajuste: progreso == null ? BoxFit.contain : BoxFit.cover,
                        relleno: progreso == null ? const EdgeInsets.all(4) : EdgeInsets.zero,
                        fondo: Tono.capaMinima,
                        tamanioIniciales: 14,
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Estabas viendo en ${seguir.aparato}',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: Letra.mini.copyWith(color: Tono.celeste),
                        ),
                        Text(titulo, maxLines: 1, overflow: TextOverflow.ellipsis, style: Letra.etiqueta),
                        Text(detalle, maxLines: 1, overflow: TextOverflow.ellipsis, style: Letra.mini),
                      ],
                    ),
                  ),
                  IconButton(
                    tooltip: 'No, gracias',
                    onPressed: () => datos.biblioteca.descartarSeguir(seguir),
                    icon: const Icon(Icons.close_rounded, size: 20, color: Tono.textoApagado),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              Padding(
                padding: const EdgeInsets.only(right: 10),
                child: BotonPrincipal(texto: 'Seguir acá', alto: 42, tamanioTexto: 13, alTocar: seguirAca),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// "Hace 5 min", "hace 2 h" (para lo que se miró en otro aparato).
String hace(DateTime cuando) {
  final diferencia = DateTime.now().difference(cuando);
  if (diferencia.inMinutes < 1) return 'recién';
  if (diferencia.inMinutes < 60) return 'hace ${diferencia.inMinutes} min';
  return 'hace ${diferencia.inHours} h';
}

/// "categoryChips": Todo · En Vivo · Películas · Series · las secciones nuevas
/// (Música, Radio...: se abren en su pantalla) · y las categorías de TV.
class _Chips extends StatelessWidget {
  const _Chips();

  @override
  Widget build(BuildContext context) {
    final catalogo = DatosScope.of(context).catalogo;
    final irA = NavegacionMovil.of(context).irA;
    final categorias = catalogo.categoriasEnVivo.take(8).toList();
    return SizedBox(
      height: 56,
      child: ListView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.fromLTRB(Espacio.margen, 8, Espacio.margen, 12),
        children: [
          ChipFiltro(texto: 'Todo', icono: Icons.auto_awesome_rounded, activo: true, alTocar: () {}),
          const SizedBox(width: Espacio.xs),
          if (catalogo.canales.isNotEmpty) ...[
            ChipFiltro(texto: 'En Vivo', puntoEnVivo: true, activo: false, alTocar: () => irA(Seccion.enVivo)),
            const SizedBox(width: Espacio.xs),
          ],
          if (catalogo.peliculas.isNotEmpty) ...[
            ChipFiltro(texto: 'Películas', activo: false, alTocar: () => irA(Seccion.peliculas)),
            const SizedBox(width: Espacio.xs),
          ],
          if (catalogo.series.isNotEmpty) ...[
            ChipFiltro(texto: 'Series', activo: false, alTocar: () => irA(Seccion.series)),
            const SizedBox(width: Espacio.xs),
          ],
          for (final seccion in catalogo.seccionesNuevas) ...[
            ChipFiltro(
              texto: seccion.nombre,
              icono: iconoDeSeccion(seccion.icono),
              activo: false,
              alTocar: () => abrirSeccionNueva(context, seccion),
            ),
            const SizedBox(width: Espacio.xs),
          ],
          for (final categoria in categorias) ...[
            ChipFiltro(
              texto: categoriaLegible(categoria.nombre),
              activo: false,
              alTocar: () => irA(Seccion.enVivo, categoria: categoria.nombre),
            ),
            const SizedBox(width: Espacio.xs),
          ],
        ],
      ),
    );
  }
}

/// Lo que muestra la portada en un momento dado.
class _Destacado {
  const _Destacado({
    required this.titulo,
    required this.imagen,
    required this.insignia,
    required this.etiqueta,
    required this.bajada,
    required this.clave,
    required this.reproducir,
    this.anio,
    this.info,
    this.numero = '',
    this.letras = '',
  });

  final String titulo;
  final String imagen;
  final String insignia;
  final String etiqueta;
  final String? anio;
  final String bajada;
  final String clave;
  final VoidCallback reproducir;
  final VoidCallback? info;
  final String numero;

  /// Las iniciales del portal; si está vacío, no es un canal: se ve su póster.
  final String letras;

  bool get esCanal => letras.isNotEmpty;
}

/// La portada: el portal de la marca con las iniciales del canal, que va pasando
/// por los canales destacados (cada tira corre por su lado). "Ver en vivo" y el
/// corazón siempre actúan sobre el que se está viendo. Si no hay canales, el
/// póster de la primera película o serie con imagen.
class _Portada extends StatefulWidget {
  const _Portada({required this.desplazamiento});

  /// Cuánto se bajó en Inicio: el portal se queda un poco atrás, como si estuviera más lejos.
  final ValueListenable<double> desplazamiento;

  @override
  State<_Portada> createState() => _PortadaState();
}

class _PortadaState extends State<_Portada> {
  static const _cadaCuanto = Duration(seconds: 7);

  /// Cuántos canales va mostrando.
  static const _maximo = 6;

  late final Timer _pase;
  int _indice = 0;
  bool _seVe = true;
  bool _quieta = false;

  @override
  void initState() {
    super.initState();
    _pase = Timer.periodic(_cadaCuanto, (_) {
      if (mounted && _seVe && !_quieta) setState(() => _indice++);
    });
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _seVe = TickerMode.valuesOf(context).enabled; // otra sección u otra pantalla encima: no pasa
    _quieta = MediaQuery.disableAnimationsOf(context);
  }

  @override
  void dispose() {
    _pase.cancel();
    super.dispose();
  }

  List<_Destacado> _destacados(BuildContext context) {
    final datos = DatosScope.of(context);
    final catalogo = datos.catalogo;
    final biblioteca = datos.biblioteca;
    // Un canal en vivo: los últimos vistos, los favoritos y los que tienen logo
    final vistos = <int>{};
    final canales = [
      ...catalogo.canalesRecientes(biblioteca),
      ...catalogo.canalesFavoritos(biblioteca),
      ...catalogo.canales.where((c) => c.logo.isNotEmpty),
      ...catalogo.canales,
    ].where((c) => vistos.add(c.id)).take(_maximo).toList();
    if (canales.isNotEmpty) {
      return [
        for (final canal in canales)
          () {
            final numero = catalogo.numeroDe(canal);
            final etiqueta = categoriaLegible(canal.categoria);
            return _Destacado(
              titulo: canal.nombre,
              imagen: canal.logo,
              insignia: 'EN VIVO',
              etiqueta: etiqueta,
              bajada: ['Señal en vivo', if (etiqueta.isNotEmpty) etiqueta].join(' · '),
              clave: Biblioteca.claveDe(canal),
              reproducir: () => NavegacionMovil.of(context).irA(Seccion.enVivo, canal: canal.id),
              numero: numero,
              letras: letrasDelPortal(canal.nombre),
            );
          }(),
      ];
    }
    final pelicula = catalogo.peliculas.where((p) => p.logo.isNotEmpty).firstOrNull;
    if (pelicula != null) {
      final etiqueta = categoriaLegible(pelicula.categoria);
      return [
        _Destacado(
          titulo: sinAnio(pelicula.nombre),
          imagen: pelicula.logo,
          insignia: 'DESTACADA',
          etiqueta: etiqueta,
          anio: anioDe(pelicula.nombre)?.toString(),
          bajada: 'Película${etiqueta.isEmpty ? '' : ' · $etiqueta'}',
          clave: Biblioteca.claveDe(pelicula),
          reproducir: () => reproducirPelicula(context, pelicula),
          info: () => abrirPantalla<void>(context, PantallaDetalle.pelicula(pelicula)),
        ),
      ];
    }
    final serie = catalogo.series.where((s) => s.imagen.isNotEmpty).firstOrNull;
    if (serie == null) return const [];
    final temporadas = serie.cantidadDeTemporadas;
    return [
      _Destacado(
        titulo: serie.nombre,
        imagen: serie.imagen,
        insignia: 'SERIE',
        etiqueta: categoriaLegible(serie.categoria),
        bajada: '$temporadas temporada${temporadas == 1 ? '' : 's'} · ${serie.cantidadDeCapitulos} capítulos',
        clave: serie.clave,
        reproducir: () => reproducirSerie(context, serie),
        info: () => abrirPantalla<void>(context, PantallaDetalle.serie(serie)),
      ),
    ];
  }

  @override
  Widget build(BuildContext context) {
    final destacados = _destacados(context);
    if (destacados.isEmpty) return const SizedBox.shrink();
    final d = destacados[_indice % destacados.length];
    return Padding(
      padding: const EdgeInsets.fromLTRB(Espacio.margen, 0, Espacio.margen, Espacio.lg),
      child: DecoratedBox(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(Curva.portada),
          border: Border.all(color: Tono.bordeSuave.withValues(alpha: .55)),
          gradient: const RadialGradient(
            center: Alignment(.5, -.7),
            radius: 1.25,
            colors: [Color(0xFF12414A), Color(0xFF181C20), Tono.fondo],
            stops: [0, .55, 1],
          ),
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(Curva.portada),
          child: d.esCanal
              ? _PortadaDeCanal(destacado: d, desplazamiento: widget.desplazamiento)
              : _PortadaDePoster(destacado: d),
        ),
      ),
    );
  }
}

/// La portada de un canal: el portal arriba (al costado, si hay lugar).
class _PortadaDeCanal extends StatelessWidget {
  const _PortadaDeCanal({required this.destacado, required this.desplazamiento});

  final _Destacado destacado;
  final ValueListenable<double> desplazamiento;

  @override
  Widget build(BuildContext context) {
    final d = destacado;
    final cabecera = Row(
      children: [
        const _InsigniaRubi(texto: 'EN VIVO', enVivo: true),
        const Spacer(),
        if (d.numero.isNotEmpty)
          AnimatedSwitcher(
            duration: const Duration(milliseconds: 300),
            child: Text(
              d.numero,
              key: ValueKey(d.numero),
              style: const TextStyle(
                fontFamily: Letra.titulos,
                fontSize: 18,
                fontWeight: FontWeight.w800,
                color: Tono.dorado,
                fontFeatures: [FontFeature.tabularFigures()],
              ),
            ),
          ),
      ],
    );
    final datos = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        _TextosDeLaPortada(destacado: d),
        const SizedBox(height: 14),
        _AccionesDeLaPortada(destacado: d),
      ],
    );
    return LayoutBuilder(
      builder: (context, lugar) {
        Widget portal(double alto) => SizedBox(
          height: alto,
          width: double.infinity,
          child: ValueListenableBuilder<double>(
            valueListenable: desplazamiento,
            builder: (_, bajado, hijo) {
              final cuanto = bajado.clamp(0.0, 400.0);
              return Transform.translate(
                offset: Offset(0, cuanto * .22),
                child: Transform.scale(scale: 1 - cuanto / 400 * .12, child: hijo),
              );
            },
            child: PortalCanal(letras: d.letras),
          ),
        );
        if (lugar.maxWidth >= 640) {
          // Tablet o celular acostado
          return Padding(
            padding: const EdgeInsets.all(Espacio.lg),
            child: Row(
              children: [
                Expanded(
                  flex: 11,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      cabecera,
                      const SizedBox(height: Espacio.lg),
                      datos,
                    ],
                  ),
                ),
                const SizedBox(width: Espacio.lg),
                Expanded(flex: 9, child: portal(280)),
              ],
            ),
          );
        }
        return Padding(
          padding: const EdgeInsets.fromLTRB(14, 14, 14, 16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [cabecera, portal((lugar.maxWidth * .6).clamp(150.0, 240.0)), const SizedBox(height: 6), datos],
          ),
        );
      },
    );
  }
}

/// La portada de una película o serie: su póster a todo el ancho.
class _PortadaDePoster extends StatelessWidget {
  const _PortadaDePoster({required this.destacado});

  final _Destacado destacado;

  @override
  Widget build(BuildContext context) {
    final d = destacado;
    return SizedBox(
      height: 460,
      child: Stack(
        fit: StackFit.expand,
        children: [
          Imagen(url: d.imagen, nombre: d.titulo),
          const DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.bottomCenter,
                end: Alignment.topCenter,
                colors: [Tono.fondo, Color(0xB3131317), Colors.transparent],
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.end,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Wrap(
                  spacing: 6,
                  runSpacing: 6,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    _InsigniaRubi(texto: d.insignia, icono: Icons.local_fire_department_rounded),
                    if (d.etiqueta.isNotEmpty) Etiqueta(d.etiqueta.toUpperCase(), color: Tono.dorado),
                    if (d.anio != null) _EtiquetaGris(d.anio!),
                  ],
                ),
                const SizedBox(height: 10),
                _TextosDeLaPortada(destacado: d),
                const SizedBox(height: 14),
                _AccionesDeLaPortada(destacado: d),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// El título y la bajada: al pasar de canal, los nuevos suben y los viejos se van.
class _TextosDeLaPortada extends StatelessWidget {
  const _TextosDeLaPortada({required this.destacado});

  final _Destacado destacado;

  @override
  Widget build(BuildContext context) {
    final d = destacado;
    // "Cyberpunk: Protocolo 2099": lo que va después de ":" en celeste
    final corte = d.titulo.indexOf(':');
    final principal = corte > 0 ? '${d.titulo.substring(0, corte + 1)}\n' : d.titulo;
    final resaltado = corte > 0 ? d.titulo.substring(corte + 1).trim() : '';
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 420),
      switchInCurve: Curves.easeOutCubic,
      switchOutCurve: Curves.easeInCubic,
      layoutBuilder: (actual, anteriores) => Stack(alignment: Alignment.centerLeft, children: [...anteriores, ?actual]),
      transitionBuilder: (hijo, avance) => FadeTransition(
        opacity: avance,
        child: SlideTransition(
          position: Tween(begin: const Offset(0, .22), end: Offset.zero).animate(avance),
          child: hijo,
        ),
      ),
      child: Row(
        key: ValueKey(d.clave),
        children: [
          if (d.esCanal && d.imagen.isNotEmpty) ...[
            ClipRRect(
              borderRadius: BorderRadius.circular(Curva.boton),
              child: SizedBox.square(
                dimension: 54,
                child: Imagen(
                  url: d.imagen,
                  nombre: d.titulo,
                  ajuste: BoxFit.contain,
                  relleno: const EdgeInsets.all(7),
                  fondo: Tono.capaMinima,
                  tamanioIniciales: 18,
                ),
              ),
            ),
            const SizedBox(width: 12),
          ],
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text.rich(
                  TextSpan(
                    children: [
                      TextSpan(text: principal),
                      if (resaltado.isNotEmpty)
                        TextSpan(
                          text: resaltado,
                          style: TextStyle(
                            color: Tono.celeste,
                            shadows: [Shadow(color: Tono.celeste.withValues(alpha: .4), blurRadius: 18)],
                          ),
                        ),
                    ],
                  ),
                  maxLines: 3,
                  overflow: TextOverflow.ellipsis,
                  style: Letra.display.copyWith(height: 1.08),
                ),
                const SizedBox(height: 4),
                Text(d.bajada, maxLines: 2, overflow: TextOverflow.ellipsis, style: Letra.cuerpo),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// "Ver en vivo" o "Reproducir", favorito y, en películas y series, más información.
class _AccionesDeLaPortada extends StatelessWidget {
  const _AccionesDeLaPortada({required this.destacado});

  final _Destacado destacado;

  @override
  Widget build(BuildContext context) {
    final biblioteca = DatosScope.of(context).biblioteca;
    final d = destacado;
    final favorito = biblioteca.estaEnMiLista(d.clave);
    return Row(
      children: [
        Expanded(
          child: Presionable(
            child: BotonPrincipal(
              texto: d.esCanal ? 'Ver en vivo' : 'Reproducir',
              alTocar: d.reproducir,
              alto: 52,
              tamanioTexto: 15,
            ),
          ),
        ),
        const SizedBox(width: Espacio.sm),
        BotonRedondo(
          icono: favorito ? Icons.favorite_rounded : Icons.favorite_border_rounded,
          color: favorito ? Tono.rubi : Tono.texto,
          ayuda: favorito ? 'Quitar de favoritos' : 'Agregar a favoritos',
          tamanio: 52,
          alTocar: () => biblioteca.alternarMiLista(d.clave),
        ),
        if (d.info != null) ...[
          const SizedBox(width: Espacio.sm),
          BotonRedondo(icono: Icons.info_outline_rounded, ayuda: 'Más información', tamanio: 52, alTocar: d.info),
        ],
      ],
    );
  }
}

class _InsigniaRubi extends StatelessWidget {
  const _InsigniaRubi({required this.texto, this.icono, this.enVivo = false});

  final String texto;
  final IconData? icono;
  final bool enVivo;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(color: Tono.rubi, borderRadius: BorderRadius.circular(99)),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (enVivo) ...[const PuntoEnVivo(), const SizedBox(width: 5)],
          if (icono != null) ...[Icon(icono, size: 13, color: Tono.sobreRubi), const SizedBox(width: 3)],
          Text(texto, style: Letra.mini.copyWith(color: Tono.sobreRubi, letterSpacing: .6)),
        ],
      ),
    );
  }
}

class _EtiquetaGris extends StatelessWidget {
  const _EtiquetaGris(this.texto);

  final String texto;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(color: Tono.capaMaxima, borderRadius: BorderRadius.circular(Curva.chico)),
      child: Text(texto, style: Letra.mini.copyWith(color: Tono.textoSuave)),
    );
  }
}

/// "Continuar Viendo": lo que quedó a medias en este aparato.
class _ContinuarViendo extends StatelessWidget {
  const _ContinuarViendo();

  @override
  Widget build(BuildContext context) {
    final datos = DatosScope.of(context);
    final catalogo = datos.catalogo;
    final tarjetas = <Widget>[];
    for (final progreso in datos.biblioteca.continuarViendo.take(10)) {
      final canal = catalogo.canalPorId(progreso.id);
      if (canal == null) continue; // ya no está en el catálogo
      final serie = canal.contenido == 'serie' ? catalogo.serieDe(canal) : null;
      final episodio = serie?.episodios.firstWhere((e) => e.canal.id == canal.id);
      tarjetas.add(
        TarjetaContinuar(
          titulo: serie?.nombre ?? sinAnio(canal.nombre),
          subtitulo: episodio == null
              ? 'Película'
              : 'Ep. ${episodio.numero}${episodio.titulo.isEmpty ? '' : ': ${episodio.titulo}'}',
          imagen: canal.logo.isNotEmpty ? canal.logo : (serie?.imagen ?? ''),
          etiqueta: episodio == null ? 'Película' : 'T${episodio.temporada} : E${episodio.numero}',
          progreso: progreso,
          alTocar: () => reproducirContenido(context, canal, serie: serie, desde: progreso.posicion),
          alQuitar: () => datos.biblioteca.olvidarProgreso(progreso.id),
        ),
      );
    }
    if (tarjetas.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(bottom: 28),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          EncabezadoSeccion(
            titulo: 'Continuar Viendo',
            icono: const Icon(Icons.history_rounded, size: 20, color: Tono.celeste),
            final_: VerTodo(alTocar: () => NavegacionMovil.of(context).irA(Seccion.miEspacio)),
          ),
          CarruselCurvo(cantidad: tarjetas.length, anchoItem: 256, alto: 256, item: (_, i) => tarjetas[i]),
        ],
      ),
    );
  }
}

/// Una fila de canales en vivo (favoritos, últimos vistos). Si no hay ninguno, no se muestra.
class _FilaCanales extends StatelessWidget {
  const _FilaCanales({required this.titulo, required this.icono, required this.canales});

  final String titulo;
  final Widget icono;
  final List<Canal> canales;

  @override
  Widget build(BuildContext context) {
    if (canales.isEmpty) return const SizedBox.shrink();
    final catalogo = DatosScope.of(context).catalogo;
    final irA = NavegacionMovil.of(context).irA;
    return Padding(
      padding: const EdgeInsets.only(bottom: 28),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          EncabezadoSeccion(titulo: titulo, icono: icono),
          CarruselCurvo(
            cantidad: canales.length,
            anchoItem: 208,
            alto: 190,
            item: (_, i) => TarjetaEnVivo(
              canal: canales[i],
              ancho: 208,
              numero: catalogo.numeroDe(canales[i]),
              alTocar: () => irA(Seccion.enVivo, canal: canales[i].id),
            ),
          ),
        ],
      ),
    );
  }
}

/// "Directos Destacados Ahora": canales en vivo (tarjetas 16:9).
class _DirectosDestacados extends StatelessWidget {
  const _DirectosDestacados();

  @override
  Widget build(BuildContext context) {
    final catalogo = DatosScope.of(context).catalogo;
    final canales = catalogo.canales;
    if (canales.isEmpty) return const SizedBox.shrink();
    // Primero los que tienen logo (se ven mejor), de distintas categorías
    final destacados = [
      ...canales.where((c) => c.logo.isNotEmpty),
      ...canales.where((c) => c.logo.isEmpty),
    ].take(12).toList();
    final irA = NavegacionMovil.of(context).irA;
    return Padding(
      padding: const EdgeInsets.only(bottom: 32),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          EncabezadoSeccion(
            titulo: 'Directos Destacados Ahora',
            icono: const PuntoEnVivo(tamanio: 12, color: Tono.rubi),
            final_: Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
              decoration: BoxDecoration(color: Tono.capaAlta, borderRadius: BorderRadius.circular(99)),
              child: Text('${canales.length} CANALES', style: Letra.mini.copyWith(color: Tono.textoSuave)),
            ),
          ),
          CarruselCurvo(
            cantidad: destacados.length,
            anchoItem: 208,
            alto: 190,
            item: (_, i) => TarjetaEnVivo(
              canal: destacados[i],
              ancho: 208,
              numero: catalogo.numeroDe(destacados[i]),
              alTocar: () => irA(Seccion.enVivo, canal: destacados[i].id),
            ),
          ),
        ],
      ),
    );
  }
}

/// "Tendencias en Kairos TV": grilla de pósters de 2 columnas (películas y series).
class _Tendencias extends StatelessWidget {
  const _Tendencias();

  @override
  Widget build(BuildContext context) {
    final catalogo = DatosScope.of(context).catalogo;
    final tarjetas = <Widget>[];
    final peliculas = catalogo.peliculas.where((p) => p.logo.isNotEmpty).take(6).toList();
    final series = catalogo.series.where((s) => s.imagen.isNotEmpty).take(6).toList();
    // Intercaladas: película, serie, película...
    for (var i = 0; i < 6; i++) {
      if (i < peliculas.length) tarjetas.add(tarjetaPelicula(context, peliculas[i]));
      if (i < series.length) tarjetas.add(tarjetaSerie(context, series[i]));
    }
    if (tarjetas.isEmpty) return const SizedBox.shrink();
    final irA = NavegacionMovil.of(context).irA;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(bottom: 4),
          child: EncabezadoSeccion(
            titulo: 'Tendencias en Kairos TV',
            icono: const Icon(Icons.trending_up_rounded, size: 20, color: Tono.dorado),
            final_: BotonRedondo(
              icono: Icons.tune_rounded,
              tamanio: 36,
              tamanioIcono: 18,
              fondo: Tono.capaAlta,
              color: Tono.textoSuave,
              ayuda: 'Ver todas las películas',
              alTocar: () => irA(catalogo.peliculas.isNotEmpty ? Seccion.peliculas : Seccion.series),
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: Espacio.margen),
          child: LayoutBuilder(
            builder: (context, limites) => GridView.builder(
              shrinkWrap: true,
              padding: EdgeInsets.zero,
              physics: const NeverScrollableScrollPhysics(),
              gridDelegate: grillaPosters(limites.maxWidth),
              itemCount: tarjetas.length,
              itemBuilder: (_, i) => tarjetas[i],
            ),
          ),
        ),
      ],
    );
  }
}

/// Reproduce un canal en vivo, una película o un capítulo, según qué sea.
void reproducirContenido(BuildContext context, Canal canal, {Serie? serie, Duration? desde}) {
  if (canal.contenido == 'vivo') {
    NavegacionMovil.of(context).irA(Seccion.enVivo, canal: canal.id);
  } else if (serie != null) {
    final episodio = serie.episodios.firstWhere((e) => e.canal.id == canal.id);
    abrirPantalla<void>(context, PantallaReproductorVod(canal: canal, serie: serie, episodio: episodio, desde: desde));
  } else {
    abrirPantalla<void>(context, PantallaReproductorVod(canal: canal, desde: desde));
  }
}
