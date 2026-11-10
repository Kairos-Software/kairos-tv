/// Favoritos en la TV (diseno_kairos_tv: tv-15, tv-21): canales, películas
/// y series en filas separadas. OK abre; OK largo lo quita. Si no hay
/// ninguno: "Todavía no tenés favoritos" y "Explorar contenido".
library;

import 'package:flutter/material.dart';

import '../movil/datos.dart';
import '../movil/estilo.dart';
import 'estructura.dart';
import 'foco.dart';
import 'inicio.dart';
import 'piezas.dart';
import 'reproductor.dart';

class FavoritosTv extends StatelessWidget {
  const FavoritosTv({super.key});

  @override
  Widget build(BuildContext context) {
    final datos = DatosScope.of(context);
    return ListenableBuilder(
      listenable: datos.biblioteca,
      builder: (context, _) {
        final catalogo = datos.catalogo;
        final biblioteca = datos.biblioteca;
        final canales = catalogo.canalesFavoritos(biblioteca);
        final peliculas = catalogo.peliculasFavoritas(biblioteca);
        final series = catalogo.seriesFavoritas(biblioteca);
        final encabezado = const EncabezadoTv(sobretitulo: 'Tu selección', titulo: 'Favoritos');

        if (canales.isEmpty && peliculas.isEmpty && series.isEmpty) {
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              encabezado,
              Expanded(
                child: Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.favorite_border_rounded, size: 80, color: Tono.rubi),
                      const SizedBox(height: 22),
                      const Text('Todavía no tenés favoritos', style: LetraTv.pantalla),
                      const SizedBox(height: 10),
                      SizedBox(
                        width: 760,
                        child: Text(
                          '${enPc('Mantené apretado OK', 'Hacé clic derecho')} sobre un canal, una película o una '
                          'serie para guardarlo acá. También podés usar el botón "Favorito" del detalle.',
                          textAlign: TextAlign.center,
                          style: LetraTv.cuerpo,
                        ),
                      ),
                      const SizedBox(height: 30),
                      BotonTv(
                        texto: 'Explorar contenido',
                        icono: Icons.explore_rounded,
                        principal: true,
                        autofocus: true,
                        alOk: () => NavegacionTv.of(context).irA(SeccionTv.enVivo),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          );
        }

        return ListView(
          padding: const EdgeInsets.only(bottom: 80),
          children: [
            encabezado,
            Padding(
              padding: const EdgeInsets.fromLTRB(MargenTv.izquierda, 8, MargenTv.derecha, 0),
              child: Text(
                enPc('OK abre · OK largo lo quita de favoritos', 'Clic abre · clic derecho lo quita de favoritos'),
                style: LetraTv.ayuda,
              ),
            ),
            FilaTv(
              titulo: 'Canales',
              final_: '${canales.length}',
              alto: 164,
              tarjetas: [
                for (final (i, canal) in canales.indexed)
                  TarjetaCanalTv(
                    canal: canal,
                    numero: catalogo.numeroDe(canal),
                    autofocus: i == 0,
                    alOk: () => verCanalTv(context, canal, lista: canales),
                    alOkLargo: () => alternarFavoritoTv(context, Biblioteca.claveDe(canal)),
                  ),
              ],
            ),
            FilaTv(
              titulo: 'Películas',
              final_: '${peliculas.length}',
              alto: 276,
              tarjetas: [
                for (final (i, p) in peliculas.indexed)
                  posterPeliculaTv(context, p, autofocus: canales.isEmpty && i == 0),
              ],
            ),
            FilaTv(
              titulo: 'Series',
              final_: '${series.length}',
              alto: 276,
              tarjetas: [
                for (final (i, s) in series.indexed)
                  posterSerieTv(context, s, autofocus: canales.isEmpty && peliculas.isEmpty && i == 0),
              ],
            ),
          ],
        );
      },
    );
  }
}
