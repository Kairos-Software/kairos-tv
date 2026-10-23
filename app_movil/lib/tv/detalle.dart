/// Detalle de una película o serie en la TV (diseno_kairos_tv: tv-10, tv-11).
///
///   Película: póster, "Película · categoría · año", Reproducir (o Continuar
///             y Desde el inicio), Favoritos, "También puede interesarte".
///   Serie:    póster y Favorito, "N temporadas · M episodios", Continuar,
///             temporadas y la lista de episodios con lo visto.
///
/// Solo datos que existen: sin sinopsis, puntajes ni actores.
library;

import 'package:flutter/material.dart';

import '../api/modelos.dart';
import '../movil/componentes.dart';
import '../movil/datos.dart';
import '../movil/detalle.dart' show proximoEpisodio;
import '../movil/estilo.dart';
import '../utiles.dart';
import 'foco.dart';
import 'inicio.dart';
import 'piezas.dart';
import 'reproductor.dart';

class DetalleTv extends StatefulWidget {
  const DetalleTv.pelicula(Canal this.pelicula, {super.key}) : serie = null;
  const DetalleTv.serie(Serie this.serie, {super.key}) : pelicula = null;

  final Canal? pelicula;
  final Serie? serie;

  @override
  State<DetalleTv> createState() => _DetalleTvState();
}

class _DetalleTvState extends State<DetalleTv> {
  int? _temporada;

  /// La serie ya con sus capítulos (desde la 1.2.38 llegan al abrirla: Catalogo.abrirSerie).
  Serie? _abierta;
  Object? _errorAlAbrir;
  bool _pedida = false;

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
      builder: (context, _) => Scaffold(
        backgroundColor: Tono.fondo,
        body: Stack(
          fit: StackFit.expand,
          children: [
            // El póster de fondo, muy oscurecido
            Opacity(
              opacity: .18,
              child: Imagen(url: widget.pelicula?.logo ?? widget.serie!.imagen, nombre: '', fondo: Tono.fondo),
            ),
            const DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(colors: [Tono.fondo, Color(0xCC131317), Color(0x99131317)]),
              ),
            ),
            widget.pelicula != null ? _pelicula(context, widget.pelicula!) : _serie(context, _abierta ?? widget.serie!),
          ],
        ),
      ),
    );
  }

  Widget _encabezado(String sobretitulo) => Padding(
    padding: const EdgeInsets.only(bottom: 26),
    child: Text(sobretitulo.toUpperCase(), style: LetraTv.sobretitulo),
  );

  Widget _poster(String imagen, String titulo, {double ancho = 360}) => Container(
    width: ancho,
    height: ancho * 1.5,
    decoration: BoxDecoration(
      borderRadius: BorderRadius.circular(Curva.portada),
      border: Border.all(color: Tono.bordeSuave.withValues(alpha: .5)),
      boxShadow: const [BoxShadow(color: Colors.black54, blurRadius: 40, offset: Offset(0, 18))],
    ),
    clipBehavior: Clip.antiAlias,
    child: Imagen(url: imagen, nombre: titulo, tamanioIniciales: 60),
  );

  Widget _pelicula(BuildContext context, Canal pelicula) {
    final datos = DatosScope.of(context);
    final biblioteca = datos.biblioteca;
    final clave = Biblioteca.claveDe(pelicula);
    final favorito = biblioteca.estaEnMiLista(clave);
    final progreso = biblioteca.progresoDe(pelicula.id);
    final aMedias = progreso != null && !progreso.terminado && progreso.fraccion > .01;
    final categoria = categoriaLegible(pelicula.categoria);
    final anio = anioDe(pelicula.nombre);
    final similares = [
      ...datos.catalogo.peliculas.where((p) => p.id != pelicula.id && p.categoria == pelicula.categoria),
      ...datos.catalogo.peliculas.where((p) => p.id != pelicula.id && p.categoria != pelicula.categoria),
    ].take(12).toList();

    return ListView(
      padding: const EdgeInsets.fromLTRB(MargenTv.derecha, MargenTv.arriba + 14, MargenTv.derecha, 60),
      children: [
        _encabezado('Película'),
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _poster(pelicula.logo, pelicula.nombre),
            const SizedBox(width: 64),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const SizedBox(height: 20),
                  Wrap(
                    spacing: 12,
                    children: [
                      _Pastilla('Película'),
                      if (categoria.isNotEmpty) _Pastilla(categoria),
                      if (anio != null) _Pastilla('$anio', color: Tono.dorado),
                    ],
                  ),
                  const SizedBox(height: 22),
                  Text(sinAnio(pelicula.nombre), maxLines: 3, overflow: TextOverflow.ellipsis, style: LetraTv.portada),
                  if (aMedias) ...[
                    const SizedBox(height: 18),
                    SizedBox(width: 520, child: BarraAvance(fraccion: progreso.fraccion, alto: 6)),
                    const SizedBox(height: 8),
                    Text('Te quedan ${duracionLegible(progreso.falta)}', style: LetraTv.ayuda.copyWith(fontSize: 16)),
                  ],
                  const SizedBox(height: 34),
                  FocusTraversalGroup(
                    child: Wrap(
                      spacing: 18,
                      runSpacing: 14,
                      children: [
                        BotonTv(
                          texto: aMedias ? 'Continuar' : 'Reproducir',
                          icono: Icons.play_arrow_rounded,
                          principal: true,
                          autofocus: true,
                          alOk: () => reproducirPeliculaTv(context, pelicula),
                        ),
                        if (aMedias)
                          BotonTv(
                            texto: 'Desde el inicio',
                            icono: Icons.replay_rounded,
                            alOk: () => reproducirPeliculaTv(context, pelicula, desdeElInicio: true),
                          ),
                        BotonTv(
                          texto: favorito ? 'En favoritos' : 'Agregar a favoritos',
                          icono: favorito ? Icons.favorite_rounded : Icons.favorite_border_rounded,
                          color: favorito ? Tono.rubi : null,
                          alOk: () => alternarFavoritoTv(context, clave),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
        if (similares.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 20),
            child: FilaTv(
              titulo: 'También puede interesarte',
              alto: 276,
              margenIzquierdo: 0,
              margenDerecho: 0,
              tarjetas: [for (final p in similares) posterPeliculaTv(context, p)],
            ),
          ),
      ],
    );
  }

  Widget _serie(BuildContext context, Serie serie) {
    final biblioteca = DatosScope.of(context).biblioteca;
    final favorito = biblioteca.estaEnMiLista(serie.clave);
    // Todavía sin capítulos (o ninguno se puede ver acá): el póster y lo que pasa
    if (!serie.cargada || serie.episodios.isEmpty) return _sinCapitulos(context, serie, favorito);
    final siguiente = proximoEpisodio(serie, biblioteca);
    final progresoSiguiente = biblioteca.progresoDe(siguiente.canal.id);
    final empezada = serie.episodios.any((e) => biblioteca.progresoDe(e.canal.id) != null);
    final temporada = _temporada ?? siguiente.temporada;
    final episodios = serie.temporadas[temporada] ?? const <Episodio>[];
    final cantidadTemporadas = serie.temporadas.length;

    return Padding(
      padding: const EdgeInsets.fromLTRB(MargenTv.derecha, MargenTv.arriba + 14, MargenTv.derecha, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _encabezado('Serie'),
          Expanded(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Column(
                  children: [
                    _poster(serie.imagen, serie.nombre, ancho: 300),
                    const SizedBox(height: 22),
                    BotonTv(
                      texto: favorito ? 'En favoritos' : 'Favorito',
                      icono: favorito ? Icons.favorite_rounded : Icons.favorite_border_rounded,
                      color: favorito ? Tono.rubi : null,
                      ancho: 300,
                      alOk: () => alternarFavoritoTv(context, serie.clave),
                    ),
                  ],
                ),
                const SizedBox(width: 56),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(serie.nombre, maxLines: 2, overflow: TextOverflow.ellipsis, style: LetraTv.portada),
                      const SizedBox(height: 8),
                      Text(
                        '$cantidadTemporadas temporada${cantidadTemporadas == 1 ? '' : 's'} · '
                        '${serie.episodios.length} episodio${serie.episodios.length == 1 ? '' : 's'}',
                        style: LetraTv.cuerpo,
                      ),
                      const SizedBox(height: 24),
                      FocusTraversalGroup(
                        child: SingleChildScrollView(
                          scrollDirection: Axis.horizontal,
                          clipBehavior: Clip.none,
                          child: Row(
                            children: [
                              BotonTv(
                                texto: empezada
                                    ? 'Continuar T${siguiente.temporada}:E${siguiente.numero}'
                                    : 'Reproducir T${siguiente.temporada}:E${siguiente.numero}',
                                icono: Icons.play_arrow_rounded,
                                principal: true,
                                alOk: () => reproducirSerieTv(context, serie, episodio: siguiente),
                              ),
                              if (cantidadTemporadas > 1)
                                for (final numero in serie.numerosDeTemporada) ...[
                                  const SizedBox(width: 14),
                                  ChipTv(
                                    texto: 'Temporada $numero',
                                    activo: numero == temporada,
                                    alOk: () => setState(() => _temporada = numero),
                                  ),
                                ],
                            ],
                          ),
                        ),
                      ),
                      const SizedBox(height: 18),
                      Expanded(
                        child: FocusTraversalGroup(
                          child: ListView.separated(
                            clipBehavior: Clip.none,
                            padding: const EdgeInsets.fromLTRB(4, 12, 4, 60),
                            itemCount: episodios.length,
                            separatorBuilder: (_, _) => const SizedBox(height: 14),
                            itemBuilder: (context, i) {
                              final episodio = episodios[i];
                              final progreso = biblioteca.progresoDe(episodio.canal.id);
                              return _FilaEpisodio(
                                episodio: episodio,
                                progreso: progreso,
                                autofocus:
                                    episodio == siguiente ||
                                    (i == 0 && siguiente.temporada != temporada && _temporada == null),
                                actual: episodio == siguiente && progresoSiguiente != null,
                                alOk: () => reproducirSerieTv(context, serie, episodio: episodio),
                              );
                            },
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
    );
  }
}

extension on _DetalleTvState {
  /// La serie mientras llegan sus capítulos (o si no se pudieron traer, o ninguno se ve en esta TV).
  /// El foco queda en Favorito (o en Reintentar): el control nunca queda sin nada para elegir.
  Widget _sinCapitulos(BuildContext context, Serie serie, bool favorito) {
    final Widget estado;
    if (_errorAlAbrir != null) {
      estado = Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('No se pudieron traer los capítulos. ${textoDeError(_errorAlAbrir!)}', style: LetraTv.cuerpo),
          const SizedBox(height: 22),
          BotonTv(
            texto: 'Reintentar',
            icono: Icons.refresh_rounded,
            principal: true,
            autofocus: true,
            alOk: _abrirSerie,
          ),
        ],
      );
    } else if (serie.cargada) {
      estado = Text('Esta serie no tiene capítulos que se puedan ver en esta TV.', style: LetraTv.cuerpo);
    } else {
      estado = const Padding(
        padding: EdgeInsets.only(top: 12),
        child: SizedBox(width: 48, height: 48, child: CircularProgressIndicator()),
      );
    }
    return Padding(
      padding: const EdgeInsets.fromLTRB(MargenTv.derecha, MargenTv.arriba + 14, MargenTv.derecha, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _encabezado('Serie'),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Column(
                children: [
                  _poster(serie.imagen, serie.nombre, ancho: 300),
                  const SizedBox(height: 22),
                  BotonTv(
                    texto: favorito ? 'En favoritos' : 'Favorito',
                    icono: favorito ? Icons.favorite_rounded : Icons.favorite_border_rounded,
                    color: favorito ? Tono.rubi : null,
                    ancho: 300,
                    autofocus: _errorAlAbrir == null,
                    alOk: () => alternarFavoritoTv(context, serie.clave),
                  ),
                ],
              ),
              const SizedBox(width: 56),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(serie.nombre, maxLines: 2, overflow: TextOverflow.ellipsis, style: LetraTv.portada),
                    const SizedBox(height: 8),
                    Text(
                      '${serie.cantidadDeTemporadas} temporada${serie.cantidadDeTemporadas == 1 ? '' : 's'} · '
                      '${serie.cantidadDeCapitulos} episodio${serie.cantidadDeCapitulos == 1 ? '' : 's'}',
                      style: LetraTv.cuerpo,
                    ),
                    const SizedBox(height: 24),
                    estado,
                  ],
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _Pastilla extends StatelessWidget {
  const _Pastilla(this.texto, {this.color = Tono.texto});

  final String texto;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 8),
      decoration: BoxDecoration(
        color: Tono.capaAlta,
        borderRadius: BorderRadius.circular(99),
        border: Border.all(color: Tono.bordeSuave.withValues(alpha: .6)),
      ),
      child: Text(
        texto,
        style: TextStyle(fontFamily: Letra.texto, fontSize: 16, fontWeight: FontWeight.w700, color: color),
      ),
    );
  }
}

/// "T1 · E1   Episodio 1   ━━━━━━──  Continuar"
class _FilaEpisodio extends StatelessWidget {
  const _FilaEpisodio({
    required this.episodio,
    required this.progreso,
    required this.autofocus,
    required this.actual,
    required this.alOk,
  });

  final Episodio episodio;
  final Progreso? progreso;
  final bool autofocus;
  final bool actual;
  final VoidCallback alOk;

  @override
  Widget build(BuildContext context) {
    final visto = progreso?.terminado ?? false;
    final titulo = episodio.titulo.isEmpty ? 'Episodio ${episodio.numero}' : episodio.titulo;
    return Enfocable(
      alOk: alOk,
      autofocus: autofocus,
      curva: Curva.tarjeta,
      escala: 1.02,
      etiqueta: 'Temporada ${episodio.temporada}, episodio ${episodio.numero}: $titulo',
      child: Container(
        height: 84,
        padding: const EdgeInsets.symmetric(horizontal: 26),
        decoration: BoxDecoration(
          color: Tono.capa.withValues(alpha: .85),
          borderRadius: BorderRadius.circular(Curva.tarjeta),
          border: Border.all(color: Tono.bordeSuave.withValues(alpha: .45)),
        ),
        child: Row(
          children: [
            SizedBox(
              width: 120,
              child: Text(
                'T${episodio.temporada} · E${episodio.numero}',
                style: const TextStyle(
                  fontFamily: Letra.texto,
                  fontSize: 19,
                  fontWeight: FontWeight.w800,
                  color: Tono.dorado,
                ),
              ),
            ),
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
                      fontWeight: FontWeight.w600,
                      color: Tono.texto,
                    ),
                  ),
                  if (progreso != null && !visto) ...[
                    const SizedBox(height: 10),
                    BarraAvance(fraccion: progreso!.fraccion, alto: 5),
                  ],
                ],
              ),
            ),
            const SizedBox(width: 40),
            if (visto)
              const Row(
                children: [
                  Icon(Icons.check_circle_rounded, color: Tono.celeste, size: 22),
                  SizedBox(width: 8),
                  Text('Visto', style: LetraTv.ayuda),
                ],
              )
            else
              Text(actual ? 'Continuar' : 'Reproducir', style: LetraTv.ayuda.copyWith(fontSize: 16)),
          ],
        ),
      ),
    );
  }
}
