/// Detalle de una película o serie (Stitch: "(2)", celular).
///
///   imagen 16:10 con degradés · título · etiquetas · Reproducir ·
///   Favoritos / Desde el inicio · ficha · pestañas Episodios / Más similares
///
/// Lo que el diseño muestra y todavía no tenemos (sinopsis, puntaje, actores,
/// tráiler, descargar) no se inventa: queda para cuando se cargue esa info.
library;

import 'dart:ui';

import 'package:flutter/material.dart';

import '../api/modelos.dart';
import '../marca.dart';
import '../utiles.dart';
import 'componentes.dart';
import 'datos.dart';
import 'estilo.dart';
import 'grilla.dart';
import 'reproductor_vod.dart';

class PantallaDetalle extends StatefulWidget {
  const PantallaDetalle.pelicula(Canal this.pelicula, {super.key}) : serie = null;

  const PantallaDetalle.serie(Serie this.serie, {super.key}) : pelicula = null;

  final Canal? pelicula;
  final Serie? serie;

  @override
  State<PantallaDetalle> createState() => _PantallaDetalleState();
}

class _PantallaDetalleState extends State<PantallaDetalle> {
  bool _episodios = true;
  int? _temporada;

  /// La serie ya con sus capítulos (desde la 1.2.38 llegan al abrirla: Catalogo.abrirSerie).
  Serie? _abierta;
  Object? _errorAlAbrir;
  bool _pedida = false;

  Serie? get _serie => _abierta ?? widget.serie;
  Canal? get _pelicula => widget.pelicula;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_pedida && widget.serie != null) {
      _pedida = true;
      _abrirSerie();
    }
  }

  Future<void> _abrirSerie() async {
    setState(() => _errorAlAbrir = null);
    try {
      final abierta = await DatosScope.of(context).catalogo.abrirSerie(widget.serie!);
      if (mounted) setState(() => _abierta = abierta);
    } catch (error) {
      if (mounted) setState(() => _errorAlAbrir = error);
    }
  }

  @override
  Widget build(BuildContext context) {
    final datos = DatosScope.of(context);
    return ListenableBuilder(
      listenable: datos.biblioteca,
      builder: (context, _) {
        final serie = _serie;
        final pelicula = _pelicula;
        // Todavía sin capítulos (o ninguno se puede ver acá): la portada y lo que pasa
        if (serie != null && (!serie.cargada || serie.episodios.isEmpty)) return _sinCapitulos(serie);
        final biblioteca = datos.biblioteca;
        final titulo = serie?.nombre ?? sinAnio(pelicula!.nombre);
        final imagen = serie?.imagen ?? pelicula!.logo;
        final categoria = categoriaLegible(serie?.categoria ?? pelicula!.categoria);
        final anio = pelicula == null ? null : anioDe(pelicula.nombre);
        final clave = serie?.clave ?? Biblioteca.claveDe(pelicula!);
        final enMiLista = biblioteca.estaEnMiLista(clave);

        // Qué reproduce el botón grande: lo que quedó a medias, o el primero
        String textoBoton;
        Progreso? aMedias;
        Episodio? siguiente;
        if (serie != null) {
          siguiente = proximoEpisodio(serie, biblioteca);
          aMedias = biblioteca.progresoDe(siguiente.canal.id);
          textoBoton = aMedias != null && !aMedias.terminado
              ? 'Continuar ${siguiente.codigo} (min ${aMedias.posicion.inMinutes})'
              : 'Reproducir ${siguiente.codigo}';
        } else {
          aMedias = biblioteca.progresoDe(pelicula!.id);
          textoBoton = aMedias != null && !aMedias.terminado
              ? 'Continuar (${duracionLegible(aMedias.falta)} restantes)'
              : 'Reproducir';
        }
        final hayAvance = aMedias != null && !aMedias.terminado;

        return Scaffold(
          backgroundColor: Tono.fondo,
          extendBodyBehindAppBar: true,
          appBar: _BarraDetalle(titulo: titulo),
          body: ListView(
            padding: EdgeInsets.only(bottom: MediaQuery.paddingOf(context).bottom + Espacio.xl),
            children: [
              _Portada(
                imagen: imagen,
                titulo: titulo,
                insignia: serie != null ? 'SERIE' : 'PELÍCULA',
                detalle: serie != null
                    ? '${serie.cantidadDeTemporadas} temporada${serie.cantidadDeTemporadas == 1 ? '' : 's'} disponible${serie.cantidadDeTemporadas == 1 ? '' : 's'}'
                    : (anio?.toString() ?? ''),
              ),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: Espacio.margen),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    // Título (headline-lg 28/36, extrabold, mayúsculas) y bajada
                    Text(
                      titulo.toUpperCase(),
                      style: Letra.titulo.copyWith(
                        fontSize: 28,
                        height: 36 / 28,
                        fontWeight: FontWeight.w800,
                        letterSpacing: -0.5,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      serie != null
                          ? 'Serie • ${serie.cantidadDeCapitulos} capítulo${serie.cantidadDeCapitulos == 1 ? '' : 's'}'
                          : 'Película${categoria.isEmpty ? '' : ' • $categoria'}',
                      style: Letra.cuerpo.copyWith(fontWeight: FontWeight.w500),
                    ),
                    const SizedBox(height: Espacio.margen),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        if (categoria.isNotEmpty)
                          _Ficha(categoria.toUpperCase(), color: Tono.textoSuave, negrita: true),
                        if (serie != null)
                          _Ficha('${serie.temporadas.length} TEMP.', fondo: Tono.capaMaxima, color: Tono.textoSuave),
                        if (anio != null) _Ficha('$anio', fondo: Tono.capaMinima, color: Tono.textoSuave),
                        _Ficha(
                          serie != null ? 'SERIE' : 'PELÍCULA',
                          fondo: Tono.celeste.withValues(alpha: .1),
                          color: Tono.celeste,
                        ),
                      ],
                    ),
                    const SizedBox(height: 20),
                    // Botón principal (h-12, headline-sm bold)
                    DecoratedBox(
                      decoration: BoxDecoration(borderRadius: BorderRadius.circular(99), boxShadow: brilloCeleste()),
                      child: Material(
                        color: Tono.celeste,
                        borderRadius: BorderRadius.circular(99),
                        child: InkWell(
                          borderRadius: BorderRadius.circular(99),
                          onTap: () => serie != null
                              ? reproducirEpisodio(
                                  context,
                                  serie,
                                  siguiente!,
                                  desde: hayAvance ? aMedias!.posicion : null,
                                )
                              : reproducirPelicula(context, pelicula!),
                          child: SizedBox(
                            height: 48,
                            child: Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                const Icon(Icons.play_arrow_rounded, size: 26, color: Tono.sobreCeleste),
                                const SizedBox(width: 8),
                                Flexible(
                                  child: Text(
                                    textoBoton,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: Letra.titulo.copyWith(color: Tono.sobreCeleste, fontSize: 18),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(height: Espacio.margen),
                    // Botonera (grid-cols-4: acá van las que tienen sentido con lo que hay)
                    Row(
                      children: [
                        Expanded(
                          child: _BotonAccion(
                            icono: enMiLista ? Icons.favorite_rounded : Icons.favorite_border_rounded,
                            texto: enMiLista ? 'En Favoritos' : 'Favoritos',
                            activo: enMiLista,
                            alTocar: () => biblioteca.alternarMiLista(clave),
                          ),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: _BotonAccion(
                            icono: Icons.replay_rounded,
                            texto: 'Desde el inicio',
                            alTocar: () => serie != null
                                ? reproducirEpisodio(context, serie, siguiente!, desde: Duration.zero)
                                : reproducirPelicula(context, pelicula!, desde: Duration.zero),
                          ),
                        ),
                        if (serie != null) ...[
                          const SizedBox(width: 8),
                          Expanded(
                            child: _BotonAccion(
                              icono: Icons.playlist_play_rounded,
                              texto: 'Primer cap.',
                              alTocar: () => reproducirEpisodio(context, serie, serie.episodios.first),
                            ),
                          ),
                        ],
                      ],
                    ),
                    const SizedBox(height: Espacio.margen),
                    // Ficha (p-3.5 rounded-xl capa baja)
                    Container(
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(
                        color: Tono.capaBaja,
                        borderRadius: BorderRadius.circular(Curva.grande),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          _Dato('Título', serie?.nombre ?? pelicula!.nombre),
                          if (categoria.isNotEmpty) _Dato('Categoría', categoria),
                          if (serie != null)
                            _Dato('Temporadas', '${serie.temporadas.length} (${serie.episodios.length} capítulos)'),
                          if (anio != null) _Dato('Año', '$anio'),
                        ],
                      ),
                    ),
                    const SizedBox(height: Espacio.margen),
                    // Pestañas
                    Row(
                      children: [
                        if (serie != null) ...[
                          _Pestania(
                            texto: 'Episodios',
                            activa: _episodios,
                            alTocar: () => setState(() => _episodios = true),
                          ),
                          const SizedBox(width: Espacio.lg),
                        ],
                        _Pestania(
                          texto: 'Más Similares',
                          activa: serie == null || !_episodios,
                          alTocar: () => setState(() => _episodios = false),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    if (serie != null && _episodios)
                      _Episodios(
                        serie: serie,
                        temporada: _temporada ?? siguiente!.temporada,
                        alElegirTemporada: (t) => setState(() => _temporada = t),
                      )
                    else
                      _Similares(serie: serie, pelicula: pelicula),
                  ],
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

extension on _PantallaDetalleState {
  /// La serie mientras llegan sus capítulos (o si no se pudieron traer, o ninguno se ve en este aparato).
  Widget _sinCapitulos(Serie serie) {
    final Widget estado;
    if (_errorAlAbrir != null) {
      estado = Column(
        children: [
          Text(
            'No se pudieron traer los capítulos. ${textoDeError(_errorAlAbrir!)}',
            textAlign: TextAlign.center,
            style: Letra.cuerpo,
          ),
          const SizedBox(height: Espacio.margen),
          FilledButton.icon(
            onPressed: _abrirSerie,
            icon: const Icon(Icons.refresh_rounded),
            label: const Text('Reintentar'),
          ),
        ],
      );
    } else if (serie.cargada) {
      estado = Text(
        'Esta serie no tiene capítulos que se puedan ver en este aparato.',
        textAlign: TextAlign.center,
        style: Letra.cuerpo,
      );
    } else {
      estado = const Center(child: CircularProgressIndicator());
    }
    return Scaffold(
      backgroundColor: Tono.fondo,
      extendBodyBehindAppBar: true,
      appBar: _BarraDetalle(titulo: serie.nombre),
      body: ListView(
        padding: EdgeInsets.only(bottom: MediaQuery.paddingOf(context).bottom + Espacio.xl),
        children: [
          _Portada(
            imagen: serie.imagen,
            titulo: serie.nombre,
            insignia: 'SERIE',
            detalle: '${serie.cantidadDeTemporadas} temporada${serie.cantidadDeTemporadas == 1 ? '' : 's'}',
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: Espacio.margen),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  serie.nombre.toUpperCase(),
                  style: Letra.titulo.copyWith(fontSize: 28, height: 36 / 28, fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 4),
                Text(
                  'Serie • ${serie.cantidadDeCapitulos} capítulo${serie.cantidadDeCapitulos == 1 ? '' : 's'}',
                  style: Letra.cuerpo.copyWith(fontWeight: FontWeight.w500),
                ),
                const SizedBox(height: Espacio.xl),
                estado,
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// El capítulo por el que sigue: el que quedó a medias, o el siguiente al último visto.
Episodio proximoEpisodio(Serie serie, Biblioteca biblioteca) {
  final episodios = serie.episodios;
  Episodio? ultimo;
  DateTime? cuando;
  for (final episodio in episodios) {
    final progreso = biblioteca.progresoDe(episodio.canal.id);
    if (progreso != null && (cuando == null || progreso.cuando.isAfter(cuando))) {
      ultimo = episodio;
      cuando = progreso.cuando;
    }
  }
  if (ultimo == null) return episodios.first;
  if (!biblioteca.progresoDe(ultimo.canal.id)!.terminado) return ultimo;
  final indice = episodios.indexOf(ultimo);
  return indice + 1 < episodios.length ? episodios[indice + 1] : ultimo;
}

class _BarraDetalle extends StatelessWidget implements PreferredSizeWidget {
  const _BarraDetalle({required this.titulo});

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

/// "aspect-[16/10]" con la imagen, dos degradés y la insignia rubí.
class _Portada extends StatelessWidget {
  const _Portada({required this.imagen, required this.titulo, required this.insignia, required this.detalle});

  final String imagen;
  final String titulo;
  final String insignia;
  final String detalle;

  @override
  Widget build(BuildContext context) {
    return Padding(
      // Ya incluye el alto de la barra de arriba (extendBodyBehindAppBar)
      padding: EdgeInsets.only(top: MediaQuery.paddingOf(context).top, bottom: Espacio.margen),
      child: AspectRatio(
        aspectRatio: 16 / 10,
        child: Stack(
          fit: StackFit.expand,
          children: [
            Imagen(url: imagen, nombre: titulo, fondo: Tono.capaMinima, tamanioIniciales: 48),
            const DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.bottomCenter,
                  end: Alignment.topCenter,
                  colors: [Tono.fondo, Color(0x66131317), Colors.transparent],
                ),
              ),
            ),
            const DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(colors: [Color(0xCC131317), Colors.transparent], stops: [0, .5]),
              ),
            ),
            Positioned(
              left: 16,
              right: 16,
              bottom: 16,
              child: Row(
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                    decoration: BoxDecoration(color: Tono.rubi, borderRadius: BorderRadius.circular(99)),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const PuntoEnVivo(),
                        const SizedBox(width: 5),
                        Text(insignia, style: Letra.mini.copyWith(color: Tono.sobreRubi, letterSpacing: .6)),
                      ],
                    ),
                  ),
                  const SizedBox(width: 8),
                  if (detalle.isNotEmpty)
                    Expanded(
                      child: Text(
                        detalle,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: Letra.numeros.copyWith(color: Tono.celesteFijo),
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
}

class _Ficha extends StatelessWidget {
  const _Ficha(this.texto, {this.fondo = Tono.capaAlta, this.color = Tono.textoSuave, this.negrita = false});

  final String texto;
  final Color fondo;
  final Color color;
  final bool negrita;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(color: fondo, borderRadius: BorderRadius.circular(Curva.chico)),
      child: Text(
        texto,
        style: Letra.etiqueta.copyWith(color: color, fontWeight: negrita ? FontWeight.w700 : FontWeight.w600),
      ),
    );
  }
}

/// Botón de la botonera ("En Mi Lista", "Calificar"...): ícono arriba, texto abajo.
class _BotonAccion extends StatelessWidget {
  const _BotonAccion({required this.icono, required this.texto, required this.alTocar, this.activo = false});

  final IconData icono;
  final String texto;
  final VoidCallback alTocar;
  final bool activo;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Tono.capaBaja,
      borderRadius: BorderRadius.circular(Curva.grande),
      child: InkWell(
        onTap: alTocar,
        borderRadius: BorderRadius.circular(Curva.grande),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 10),
          child: Column(
            children: [
              Icon(icono, size: 24, color: activo ? Tono.celeste : Tono.textoSuave),
              const SizedBox(height: 6),
              Text(
                texto,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: Letra.mini.copyWith(color: Tono.textoSuave, fontWeight: FontWeight.w700),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Dato extends StatelessWidget {
  const _Dato(this.titulo, this.valor);

  final String titulo;
  final String valor;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Text.rich(
        TextSpan(
          children: [
            TextSpan(
              text: '$titulo: ',
              style: const TextStyle(color: Tono.textoApagado, fontWeight: FontWeight.w500),
            ),
            TextSpan(text: valor),
          ],
        ),
        style: Letra.cuerpo.copyWith(color: Tono.texto),
      ),
    );
  }
}

/// Pestaña (headline-sm bold; la activa celeste con una rayita que brilla).
class _Pestania extends StatelessWidget {
  const _Pestania({required this.texto, required this.activa, required this.alTocar});

  final String texto;
  final bool activa;
  final VoidCallback alTocar;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: alTocar,
      child: IntrinsicWidth(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              texto,
              maxLines: 1,
              style: Letra.titulo.copyWith(fontSize: 18, color: activa ? Tono.celeste : Tono.textoSuave),
            ),
            const SizedBox(height: 10),
            Container(
              height: 2,
              decoration: BoxDecoration(
                color: activa ? Tono.celeste : Colors.transparent,
                borderRadius: BorderRadius.circular(99),
                boxShadow: activa ? const [BoxShadow(color: Tono.celeste, blurRadius: 8)] : null,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Episodios extends StatelessWidget {
  const _Episodios({required this.serie, required this.temporada, required this.alElegirTemporada});

  final Serie serie;
  final int temporada;
  final ValueChanged<int> alElegirTemporada;

  Future<void> _elegirTemporada(BuildContext context) async {
    final elegida = await showModalBottomSheet<int>(
      context: context,
      builder: (context) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          padding: const EdgeInsets.symmetric(vertical: 8),
          children: [
            for (final t in serie.numerosDeTemporada)
              ListTile(
                title: Text(
                  'Temporada $t (${serie.temporadas[t]!.length} Ep.)',
                  style: Letra.etiqueta.copyWith(fontSize: 14, color: t == temporada ? Tono.texto : Tono.textoSuave),
                ),
                trailing: t == temporada ? const Icon(Icons.check_rounded, size: 18, color: Tono.celeste) : null,
                onTap: () => Navigator.pop(context, t),
              ),
          ],
        ),
      ),
    );
    if (elegida != null) alElegirTemporada(elegida);
  }

  @override
  Widget build(BuildContext context) {
    final biblioteca = DatosScope.of(context).biblioteca;
    final episodios = serie.temporadas[temporada] ?? serie.episodios;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Material(
              color: Tono.capaAlta,
              borderRadius: BorderRadius.circular(Curva.medio),
              child: InkWell(
                borderRadius: BorderRadius.circular(Curva.medio),
                onTap: serie.temporadas.length > 1 ? () => _elegirTemporada(context) : null,
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        'Temporada $temporada (${episodios.length} Episodio${episodios.length == 1 ? '' : 's'})',
                        style: Letra.etiqueta,
                      ),
                      if (serie.temporadas.length > 1) ...[
                        const SizedBox(width: 8),
                        const Icon(Icons.keyboard_arrow_down_rounded, size: 18, color: Tono.texto),
                      ],
                    ],
                  ),
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: Espacio.margen),
        for (final episodio in episodios) ...[
          _TarjetaEpisodio(episodio: episodio, serie: serie, progreso: biblioteca.progresoDe(episodio.canal.id)),
          const SizedBox(height: 12),
        ],
      ],
    );
  }
}

class _TarjetaEpisodio extends StatelessWidget {
  const _TarjetaEpisodio({required this.episodio, required this.serie, required this.progreso});

  final Episodio episodio;
  final Serie serie;
  final Progreso? progreso;

  @override
  Widget build(BuildContext context) {
    final empezado = progreso != null && !progreso!.terminado;
    final visto = progreso?.terminado ?? false;
    return Material(
      color: Tono.capaBaja,
      borderRadius: BorderRadius.circular(Curva.grande),
      child: InkWell(
        borderRadius: BorderRadius.circular(Curva.grande),
        onTap: () => reproducirEpisodio(context, serie, episodio, desde: empezado ? progreso!.posicion : null),
        child: Padding(
          padding: const EdgeInsets.all(10),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(Curva.medio),
                child: SizedBox(
                  width: 144,
                  child: AspectRatio(
                    aspectRatio: 16 / 9,
                    child: Stack(
                      fit: StackFit.expand,
                      children: [
                        Imagen(
                          url: episodio.canal.logo.isNotEmpty ? episodio.canal.logo : serie.imagen,
                          nombre: serie.nombre,
                          fondo: Tono.capaMaxima,
                          tamanioIniciales: 18,
                        ),
                        ColoredBox(color: Colors.black.withValues(alpha: empezado ? .3 : .4)),
                        Center(
                          child: Container(
                            width: 32,
                            height: 32,
                            decoration: BoxDecoration(
                              color: empezado ? Tono.celeste : Tono.capaAlta.withValues(alpha: .8),
                              shape: BoxShape.circle,
                              boxShadow: empezado ? const [BoxShadow(color: Colors.black45, blurRadius: 10)] : null,
                            ),
                            child: Icon(
                              Icons.play_arrow_rounded,
                              size: 18,
                              color: empezado ? Tono.sobreCeleste : Tono.texto,
                            ),
                          ),
                        ),
                        if (empezado)
                          Positioned(
                            left: 0,
                            right: 0,
                            bottom: 0,
                            child: BarraAvance(fraccion: progreso!.fraccion, alto: 4),
                          ),
                      ],
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: SizedBox(
                  height: 81,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Expanded(
                            child: Text(
                              'E${episodio.numero}${episodio.titulo.isEmpty ? '' : ': ${episodio.titulo}'}',
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: Letra.etiqueta.copyWith(fontWeight: FontWeight.w700),
                            ),
                          ),
                          if (visto) const Icon(Icons.check_rounded, size: 20, color: Tono.celesteFijo),
                        ],
                      ),
                      if (progreso != null && progreso!.duracion > Duration.zero)
                        Text(duracionLegible(progreso!.duracion), style: Letra.numeros),
                      const Spacer(),
                      Text(
                        visto
                            ? 'Visto'
                            : empezado
                            ? 'Visto hasta min ${progreso!.posicion.inMinutes}'
                            : 'No iniciado',
                        style: Letra.mini.copyWith(color: empezado || visto ? Tono.celesteFijo : Tono.textoSuave),
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

/// "Más Similares": de la misma categoría.
class _Similares extends StatelessWidget {
  const _Similares({required this.serie, required this.pelicula});

  final Serie? serie;
  final Canal? pelicula;

  @override
  Widget build(BuildContext context) {
    final catalogo = DatosScope.of(context).catalogo;
    final List<Widget> tarjetas;
    if (serie != null) {
      tarjetas = [
        for (final otra in catalogo.series.where((s) => s.categoria == serie!.categoria && s != serie).take(12))
          tarjetaSerie(context, otra),
      ];
    } else {
      tarjetas = [
        for (final otra
            in catalogo.peliculas.where((p) => p.categoria == pelicula!.categoria && p.id != pelicula!.id).take(12))
          tarjetaPelicula(context, otra),
      ];
    }
    if (tarjetas.isEmpty) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 24),
        child: Text('No hay otros títulos de esta categoría.', style: Letra.cuerpo, textAlign: TextAlign.center),
      );
    }
    return LayoutBuilder(
      builder: (context, limites) => GridView.builder(
        shrinkWrap: true,
        padding: EdgeInsets.zero,
        physics: const NeverScrollableScrollPhysics(),
        gridDelegate: grillaPosters(limites.maxWidth),
        itemCount: tarjetas.length,
        itemBuilder: (_, i) => tarjetas[i],
      ),
    );
  }
}
