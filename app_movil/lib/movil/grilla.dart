/// Películas y Series: la grilla de pósters de "Tendencias" (Stitch, Inicio)
/// con chips para filtrar por categoría. También una sección nueva "a
/// demanda" (Música...: [SeccionGrilla.nueva]), igual que Películas.
library;

import 'package:flutter/material.dart';

import '../api/modelos.dart';
import 'componentes.dart';
import 'datos.dart';
import 'detalle.dart';
import 'estilo.dart';
import 'estructura.dart';

/// La grilla de pósters: 2 columnas en el celular (3 o más si entra).
/// El alto de cada tarjeta: el póster 2:3 más el título y la bajada.
SliverGridDelegate grillaPosters(double ancho) {
  final columnas = ancho >= 900 ? 5 : (ancho >= 600 ? 3 : 2);
  final columna = (ancho - Espacio.sm * (columnas - 1)) / columnas;
  return SliverGridDelegateWithFixedCrossAxisCount(
    crossAxisCount: columnas,
    mainAxisSpacing: Espacio.sm,
    crossAxisSpacing: Espacio.sm,
    mainAxisExtent: columna * 1.5 + 62,
  );
}

/// `tipo`: lo que dice abajo del título ("Película", o el nombre de una sección nueva: "Música").
Widget tarjetaPelicula(BuildContext context, Canal pelicula, {String tipo = 'Película'}) {
  final biblioteca = DatosScope.of(context).biblioteca;
  final anio = anioDe(pelicula.nombre);
  final progreso = biblioteca.progresoDe(pelicula.id);
  return TarjetaPoster(
    titulo: sinAnio(pelicula.nombre),
    subtitulo: anio == null ? tipo : '$tipo • $anio',
    imagen: pelicula.logo,
    etiqueta: categoriaLegible(pelicula.categoria),
    esquina: anio?.toString(),
    progreso: progreso == null || progreso.terminado ? null : progreso.fraccion,
    alTocar: () => abrirPantalla<void>(context, PantallaDetalle.pelicula(pelicula)),
  );
}

Widget tarjetaSerie(BuildContext context, Serie serie) {
  final temporadas = serie.cantidadDeTemporadas;
  return TarjetaPoster(
    titulo: serie.nombre,
    subtitulo: temporadas > 1
        ? 'Serie • $temporadas temporadas'
        : 'Serie • ${serie.cantidadDeCapitulos} capítulo${serie.cantidadDeCapitulos == 1 ? '' : 's'}',
    imagen: serie.imagen,
    etiqueta: categoriaLegible(serie.categoria),
    alTocar: () => abrirPantalla<void>(context, PantallaDetalle.serie(serie)),
  );
}

class SeccionGrilla extends StatefulWidget {
  const SeccionGrilla({super.key, required this.contenido, this.nueva});

  /// "pelicula" o "serie"
  final String contenido;

  /// La clave de una sección nueva (Música...) para mostrar lo suyo; null = Películas o Series.
  final String? nueva;

  @override
  State<SeccionGrilla> createState() => _SeccionGrillaState();
}

class _SeccionGrillaState extends State<SeccionGrilla> {
  String? _categoria;

  bool get _esSerie => widget.contenido == 'serie';

  @override
  Widget build(BuildContext context) {
    final datos = DatosScope.of(context);
    return ListenableBuilder(
      listenable: Listenable.merge([datos.catalogo, datos.biblioteca]),
      builder: (context, _) {
        final catalogo = datos.catalogo;
        if (!catalogo.cargado) return const Center(child: CircularProgressIndicator());
        final nueva = widget.nueva == null ? null : catalogo.seccionNueva(widget.nueva!);
        final todas = nueva?.canales ?? catalogo.peliculas;

        final categorias = <String>{
          for (final c in _esSerie ? catalogo.series.map((s) => s.categoria) : todas.map((p) => p.categoria))
            if (c.isNotEmpty) c,
        }.toList();
        final series = _esSerie
            ? catalogo.series.where((s) => _categoria == null || s.categoria == _categoria).toList()
            : const <Serie>[];
        final peliculas = _esSerie
            ? const <Canal>[]
            : todas.where((p) => _categoria == null || p.categoria == _categoria).toList();
        final cantidad = _esSerie ? series.length : peliculas.length;

        if (cantidad == 0 && _categoria == null) {
          return Vacio(
            icono: _esSerie ? Icons.video_library_outlined : Icons.movie_outlined,
            texto: _esSerie
                ? 'Todavía no hay series disponibles.'
                : (nueva != null ? 'Todavía no hay nada disponible acá.' : 'Todavía no hay películas disponibles.'),
          );
        }
        return RefreshIndicator(
          onRefresh: catalogo.cargar,
          edgeOffset: altoBarraSuperior(context),
          child: CustomScrollView(
            slivers: [
              SliverToBoxAdapter(child: SizedBox(height: altoBarraSuperior(context))),
              if (categorias.length > 1)
                SliverToBoxAdapter(
                  child: SizedBox(
                    height: 56,
                    child: ListView(
                      scrollDirection: Axis.horizontal,
                      padding: const EdgeInsets.fromLTRB(Espacio.margen, 8, Espacio.margen, 12),
                      children: [
                        ChipFiltro(
                          texto: 'Todas',
                          icono: Icons.auto_awesome_rounded,
                          activo: _categoria == null,
                          alTocar: () => setState(() => _categoria = null),
                        ),
                        for (final categoria in categorias) ...[
                          const SizedBox(width: Espacio.xs),
                          ChipFiltro(
                            texto: categoriaLegible(categoria),
                            activo: _categoria == categoria,
                            alTocar: () => setState(() => _categoria = categoria),
                          ),
                        ],
                      ],
                    ),
                  ),
                ),
              SliverToBoxAdapter(
                child: EncabezadoSeccion(
                  titulo: _esSerie ? 'Series' : (nueva?.nombre ?? 'Películas'),
                  icono: Icon(
                    _esSerie ? Icons.video_library_rounded : Icons.movie_rounded,
                    size: 20,
                    color: Tono.celeste,
                  ),
                  final_: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                    decoration: BoxDecoration(color: Tono.capaAlta, borderRadius: BorderRadius.circular(99)),
                    child: Text('$cantidad TÍTULOS', style: Letra.mini.copyWith(color: Tono.textoSuave)),
                  ),
                ),
              ),
              SliverPadding(
                padding: EdgeInsets.fromLTRB(Espacio.margen, 0, Espacio.margen, altoBarraInferior(context) + 32),
                sliver: SliverLayoutBuilder(
                  builder: (context, limites) => SliverGrid.builder(
                    gridDelegate: grillaPosters(limites.crossAxisExtent),
                    itemCount: cantidad,
                    itemBuilder: (context, i) => _esSerie
                        ? tarjetaSerie(context, series[i])
                        : tarjetaPelicula(context, peliculas[i], tipo: nueva?.nombre ?? 'Película'),
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
