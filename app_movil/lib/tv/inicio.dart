/// Inicio de la TV (diseno_kairos_tv: tv-04). TV en vivo primero:
///
///   portada con un canal (el último visto, un favorito o uno con logo):
///     Ver en vivo · Favorito · Abrir guía
///   Tus canales favoritos · Últimos canales vistos · Continuar viendo ·
///   una fila por categoría de TV · Películas · Series · una fila por sección
///   nueva (Música, Radio...)
///
/// El foco arranca en "Ver en vivo". OK largo sobre una tarjeta la agrega o
/// quita de favoritos.
library;

import 'package:flutter/material.dart';

import '../api/modelos.dart';
import '../movil/componentes.dart' show reloj;
import '../movil/datos.dart';
import '../movil/estilo.dart';
import '../sesion.dart';
import 'detalle.dart';
import 'estructura.dart';
import 'foco.dart';
import 'piezas.dart';
import 'reproductor.dart';

class InicioTv extends StatelessWidget {
  const InicioTv({super.key});

  @override
  Widget build(BuildContext context) {
    final datos = DatosScope.of(context);
    return ListenableBuilder(
      listenable: Listenable.merge([datos.catalogo, datos.biblioteca]),
      builder: (context, _) {
        final catalogo = datos.catalogo;
        final biblioteca = datos.biblioteca;
        final seguir = biblioteca.seguirDeOtroAparato;
        final hayQueSeguir = seguir != null && catalogo.canalPorId(seguir.id) != null;
        final favoritos = catalogo.canalesFavoritos(biblioteca);
        final recientes = catalogo.canalesRecientes(biblioteca);
        final destacado = [
          ...recientes,
          ...favoritos,
          ...catalogo.canales.where((c) => c.logo.isNotEmpty),
          ...catalogo.canales,
        ].firstOrNull;

        Widget filaCanales(String titulo, List<Canal> canales, {Widget? icono, String? final_}) => FilaTv(
          titulo: titulo,
          icono: icono,
          final_: final_,
          alto: 164,
          tarjetas: [
            for (final canal in canales)
              TarjetaCanalTv(
                canal: canal,
                numero: catalogo.numeroDe(canal),
                favorito: biblioteca.estaEnMiLista(Biblioteca.claveDe(canal)),
                alOk: () => verCanalTv(context, canal, lista: canales),
                alOkLargo: () => alternarFavoritoTv(context, Biblioteca.claveDe(canal)),
              ),
          ],
        );

        return ListView(
          padding: const EdgeInsets.only(bottom: 80),
          children: [
            EncabezadoTv(
              sobretitulo: 'Inicio',
              titulo: _saludo(SesionScope.of(context)),
              accion: BotonTv(
                texto: 'Buscar',
                icono: Icons.search_rounded,
                alOk: () => NavegacionTv.of(context).irA(SeccionTv.buscar),
              ),
            ),
            if (hayQueSeguir) _SeguirAca(seguir: seguir),
            if (destacado != null) _Portada(canal: destacado, foco: !hayQueSeguir),
            if (catalogo.canales.isEmpty &&
                catalogo.peliculas.isEmpty &&
                catalogo.series.isEmpty &&
                catalogo.seccionesNuevas.isEmpty)
              const Padding(
                padding: EdgeInsets.all(120),
                child: Center(child: Text('Todavía no hay contenido disponible.', style: LetraTv.cuerpo)),
              ),
            filaCanales(
              'Tus canales favoritos',
              favoritos,
              icono: const Icon(Icons.favorite_rounded, color: Tono.rubi, size: 26),
            ),
            filaCanales(
              'Últimos canales vistos',
              recientes,
              icono: const Icon(Icons.history_rounded, color: Tono.celeste, size: 26),
            ),
            _ContinuarViendo(),
            for (final categoria in catalogo.categoriasEnVivo.take(10))
              filaCanales(
                categoriaLegible(categoria.nombre).isEmpty ? 'TV en vivo' : categoriaLegible(categoria.nombre),
                categoria.canales.take(20).toList(),
                final_: '${categoria.canales.length} canales',
              ),
            FilaTv(
              titulo: 'Películas',
              alto: 276,
              final_: catalogo.peliculas.isEmpty ? null : '${catalogo.peliculas.length}',
              tarjetas: [for (final p in catalogo.peliculas.take(20)) posterPeliculaTv(context, p)],
            ),
            FilaTv(
              titulo: 'Series',
              alto: 276,
              final_: catalogo.series.isEmpty ? null : '${catalogo.series.length}',
              tarjetas: [for (final s in catalogo.series.take(20)) posterSerieTv(context, s)],
            ),
            for (final seccion in catalogo.seccionesNuevas)
              seccion.enVivo
                  ? filaCanales(seccion.nombre, seccion.canales.take(20).toList(), final_: '${seccion.canales.length}')
                  : FilaTv(
                      titulo: seccion.nombre,
                      alto: 276,
                      final_: '${seccion.canales.length}',
                      tarjetas: [for (final p in seccion.canales.take(20)) posterPeliculaTv(context, p)],
                    ),
          ],
        );
      },
    );
  }

  static String _saludo(Sesion sesion) {
    final hora = DateTime.now().hour;
    final saludo = hora < 6 || hora >= 20 ? 'Buenas noches' : (hora < 13 ? 'Buen día' : 'Buenas tardes');
    final nombre = (sesion.cliente?.nombre ?? sesion.perfil?.nombreCompleto ?? '').split(' ').first;
    return nombre.isEmpty ? saludo : '$saludo, $nombre';
  }
}

/// La portada: el canal destacado, con su logo grande a la derecha sobre una luz celeste.
class _Portada extends StatelessWidget {
  const _Portada({required this.canal, this.foco = true});

  final Canal canal;

  /// El foco arranca en "Ver en vivo" (salvo que arriba esté "Seguir acá").
  final bool foco;

  @override
  Widget build(BuildContext context) {
    final datos = DatosScope.of(context);
    final clave = Biblioteca.claveDe(canal);
    final favorito = datos.biblioteca.estaEnMiLista(clave);
    final numero = datos.catalogo.numeroDe(canal);
    final categoria = categoriaLegible(canal.categoria);
    return Padding(
      padding: const EdgeInsets.fromLTRB(MargenTv.izquierda, 24, MargenTv.derecha, 0),
      child: Container(
        height: 410,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(Curva.portada),
          border: Border.all(color: Tono.bordeSuave.withValues(alpha: .5)),
          gradient: const RadialGradient(
            center: Alignment(.6, -.1),
            radius: 1.0,
            colors: [Color(0xFF0B3B42), Color(0xFF16181C), Tono.capaMinima],
            stops: [0, .45, 1],
          ),
        ),
        child: Row(
          children: [
            Expanded(
              flex: 11,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(48, 44, 24, 44),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Row(
                      children: [
                        const InsigniaEnVivoTv(grande: true),
                        if (categoria.isNotEmpty) ...[
                          const SizedBox(width: 12),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 7),
                            decoration: BoxDecoration(
                              color: Tono.capaAlta,
                              borderRadius: BorderRadius.circular(99),
                              border: Border.all(color: Tono.bordeSuave.withValues(alpha: .6)),
                            ),
                            child: Text(
                              categoria,
                              style: const TextStyle(
                                fontFamily: Letra.texto,
                                fontSize: 15,
                                fontWeight: FontWeight.w700,
                                color: Tono.texto,
                              ),
                            ),
                          ),
                        ],
                      ],
                    ),
                    const SizedBox(height: 22),
                    Text(canal.nombre, maxLines: 2, overflow: TextOverflow.ellipsis, style: LetraTv.portada),
                    const SizedBox(height: 10),
                    Text([if (numero.isNotEmpty) 'Canal $numero', 'Señal en vivo'].join(' · '), style: LetraTv.cuerpo),
                    const SizedBox(height: 30),
                    FocusTraversalGroup(
                      child: Row(
                        children: [
                          BotonTv(
                            texto: 'Ver en vivo',
                            icono: Icons.play_arrow_rounded,
                            principal: true,
                            autofocus: foco,
                            alOk: () => verCanalTv(context, canal),
                          ),
                          const SizedBox(width: 18),
                          BotonTv(
                            texto: favorito ? 'En favoritos' : 'Favorito',
                            icono: favorito ? Icons.favorite_rounded : Icons.favorite_border_rounded,
                            color: favorito ? Tono.rubi : null,
                            alOk: () => alternarFavoritoTv(context, clave),
                          ),
                          const SizedBox(width: 18),
                          BotonTv(
                            texto: 'Abrir guía',
                            icono: Icons.view_list_rounded,
                            alOk: () => NavegacionTv.of(context).irA(SeccionTv.guia),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
            Expanded(
              flex: 9,
              child: Center(
                child: Container(
                  width: 360,
                  height: 230,
                  decoration: BoxDecoration(
                    color: Tono.capaMinima.withValues(alpha: .7),
                    borderRadius: BorderRadius.circular(Curva.portada),
                    border: Border.all(color: Tono.celeste.withValues(alpha: .25)),
                    boxShadow: [
                      BoxShadow(color: Tono.celeste.withValues(alpha: .18), blurRadius: 80, spreadRadius: 10),
                    ],
                  ),
                  child: LogoCanalTv(canal: canal, tamanioIniciales: 84, relleno: const EdgeInsets.all(34)),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// "Estabas viendo X en el celular — Seguir acá": lo último que se miró en
/// otro aparato de la misma cuenta (Biblioteca.seguirDeOtroAparato). Una
/// película o capítulo sigue en el mismo minuto; un canal, en vivo. El foco
/// arranca en "Seguir acá".
class _SeguirAca extends StatelessWidget {
  const _SeguirAca({required this.seguir});

  final SeguirViendo seguir;

  @override
  Widget build(BuildContext context) {
    final datos = DatosScope.of(context);
    final canal = datos.catalogo.canalPorId(seguir.id)!;
    final serie = canal.contenido == 'serie' ? datos.catalogo.serieDe(canal) : null;
    final episodio = serie?.episodios.where((e) => e.canal.id == canal.id).firstOrNull;
    final progreso = seguir.progreso;
    final titulo = serie == null
        ? sinAnio(canal.nombre)
        : '${serie.nombre} · T${episodio?.temporada ?? 1} E${episodio?.numero ?? 1}';
    final minutos = DateTime.now().difference(seguir.cuando).inMinutes;
    final cuando = minutos < 1 ? 'recién' : (minutos < 60 ? 'hace $minutos min' : 'hace ${minutos ~/ 60} h');
    void seguirAca() {
      datos.biblioteca.descartarSeguir(seguir);
      if (progreso == null) {
        verCanalTv(context, canal);
      } else if (serie != null && episodio != null) {
        reproducirSerieTv(context, serie, episodio: episodio);
      } else {
        reproducirPeliculaTv(context, canal);
      }
    }

    return Padding(
      padding: const EdgeInsets.fromLTRB(MargenTv.izquierda, 16, MargenTv.derecha, 0),
      child: Container(
        padding: const EdgeInsets.fromLTRB(28, 18, 22, 18),
        decoration: BoxDecoration(
          color: Tono.capa,
          borderRadius: BorderRadius.circular(Curva.panel),
          border: Border.all(color: Tono.celeste.withValues(alpha: .4)),
        ),
        child: Row(
          children: [
            const Icon(Icons.devices_rounded, color: Tono.celeste, size: 34),
            const SizedBox(width: 22),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Estabas viendo en ${seguir.aparato}', style: LetraTv.ayuda.copyWith(color: Tono.celeste)),
                  const SizedBox(height: 4),
                  Text(titulo, maxLines: 1, overflow: TextOverflow.ellipsis, style: LetraTv.tarjeta),
                  const SizedBox(height: 2),
                  Text(
                    progreso == null ? 'En vivo · $cuando' : 'Ibas por ${reloj(progreso.posicion)} · $cuando',
                    style: LetraTv.ayuda,
                  ),
                ],
              ),
            ),
            FocusTraversalGroup(
              child: Row(
                children: [
                  BotonTv(
                    texto: 'Seguir acá',
                    icono: Icons.play_arrow_rounded,
                    principal: true,
                    autofocus: true,
                    alOk: seguirAca,
                  ),
                  const SizedBox(width: 16),
                  BotonTv(texto: 'No, gracias', alOk: () => datos.biblioteca.descartarSeguir(seguir)),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// "Continuar viendo": películas y capítulos que quedaron a medias.
class _ContinuarViendo extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final datos = DatosScope.of(context);
    final tarjetas = <Widget>[];
    for (final progreso in datos.biblioteca.continuarViendo.take(15)) {
      final canal = datos.catalogo.canalPorId(progreso.id);
      if (canal == null) continue;
      final serie = canal.contenido == 'serie' ? datos.catalogo.serieDe(canal) : null;
      final episodio = serie?.episodios.where((e) => e.canal.id == canal.id).firstOrNull;
      tarjetas.add(
        TarjetaPosterTv(
          titulo: serie == null
              ? sinAnio(canal.nombre)
              : '${serie.nombre}\nT${episodio?.temporada ?? 1} · E${episodio?.numero ?? 1}',
          imagen: canal.logo.isNotEmpty ? canal.logo : (serie?.imagen ?? ''),
          progreso: progreso.fraccion,
          alOk: () => serie != null && episodio != null
              ? reproducirSerieTv(context, serie, episodio: episodio)
              : reproducirPeliculaTv(context, canal),
        ),
      );
    }
    return FilaTv(
      titulo: 'Continuar viendo',
      icono: const Icon(Icons.play_circle_outline_rounded, color: Tono.celeste, size: 26),
      alto: 276,
      tarjetas: tarjetas,
    );
  }
}

/// El póster de una película: OK abre el detalle, OK largo la agrega o quita de favoritos.
Widget posterPeliculaTv(BuildContext context, Canal pelicula, {bool autofocus = false, double ancho = 184}) {
  final biblioteca = DatosScope.of(context).biblioteca;
  final clave = Biblioteca.claveDe(pelicula);
  final progreso = biblioteca.progresoDe(pelicula.id);
  return TarjetaPosterTv(
    titulo: sinAnio(pelicula.nombre),
    imagen: pelicula.logo,
    ancho: ancho,
    autofocus: autofocus,
    favorito: biblioteca.estaEnMiLista(clave),
    progreso: progreso == null || progreso.terminado ? null : progreso.fraccion,
    alOk: () => abrirTv<void>(context, DetalleTv.pelicula(pelicula)),
    alOkLargo: () => alternarFavoritoTv(context, clave),
  );
}

Widget posterSerieTv(BuildContext context, Serie serie, {bool autofocus = false, double ancho = 184}) {
  final biblioteca = DatosScope.of(context).biblioteca;
  return TarjetaPosterTv(
    titulo: serie.nombre,
    imagen: serie.imagen,
    ancho: ancho,
    autofocus: autofocus,
    favorito: biblioteca.estaEnMiLista(serie.clave),
    alOk: () => abrirTv<void>(context, DetalleTv.serie(serie)),
    alOkLargo: () => alternarFavoritoTv(context, serie.clave),
  );
}
