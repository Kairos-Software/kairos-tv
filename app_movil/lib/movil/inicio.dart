/// Inicio (Stitch: "stitch_modern_streaming_app_ui.zip", celular).
///
///   chips de categorías · portada destacada · Tus canales favoritos ·
///   Últimos canales vistos · Directos Destacados Ahora · Continuar Viendo ·
///   Tendencias en Kairos TV (grilla de pósters)
///
/// TV en vivo primero (diseno_kairos_tv/DESIGN.md, principio 1): la portada es
/// un canal (el último que se vio, o un favorito); si no hay canales, una
/// película o serie. Todo con datos reales: favoritos, últimos vistos y
/// "Continuar Viendo" son de la cuenta (lo que se hizo en cualquiera de sus
/// aparatos). Arriba, si se estaba mirando algo en otro aparato: "Seguir acá".
library;

import 'package:flutter/material.dart';

import '../api/modelos.dart';
import '../utiles.dart';
import 'componentes.dart';
import 'datos.dart';
import 'detalle.dart';
import 'estilo.dart';
import 'estructura.dart';
import 'grilla.dart';
import 'reproductor_vod.dart';
import 'secciones_nuevas.dart';

class SeccionInicio extends StatelessWidget {
  const SeccionInicio({super.key});

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
        return RefreshIndicator(
          onRefresh: catalogo.cargar,
          edgeOffset: altoBarraSuperior(context),
          child: ListView(
            padding: EdgeInsets.only(top: altoBarraSuperior(context), bottom: altoBarraInferior(context) + 40),
            children: [
              const _Chips(),
              const _SeguirAca(),
              const _Portada(),
              _FilaCanales(
                titulo: 'Tus canales favoritos',
                icono: const Icon(Icons.favorite_rounded, size: 20, color: Tono.rubi),
                canales: catalogo.canalesFavoritos(datos.biblioteca),
              ),
              _FilaCanales(
                titulo: 'Últimos canales vistos',
                icono: const Icon(Icons.history_rounded, size: 20, color: Tono.celeste),
                canales: catalogo.canalesRecientes(datos.biblioteca).take(10).toList(),
              ),
              const _DirectosDestacados(),
              const _ContinuarViendo(),
              const _Tendencias(),
              if (catalogo.canales.isEmpty &&
                  catalogo.peliculas.isEmpty &&
                  catalogo.series.isEmpty &&
                  catalogo.seccionesNuevas.isEmpty)
                const Vacio(icono: Icons.tv_off_rounded, texto: 'Todavía no hay contenido disponible.'),
            ],
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

/// La portada (470 px): imagen a todo el ancho con tres degradés, insignias,
/// título grande con la segunda parte en celeste, y Reproducir · + · i.
class _Portada extends StatelessWidget {
  const _Portada();

  @override
  Widget build(BuildContext context) {
    final datos = DatosScope.of(context);
    final catalogo = datos.catalogo;

    // Lo destacado: un canal en vivo (el último visto, un favorito o uno con logo);
    // si no hay canales, la primera película o serie con imagen
    final biblioteca = datos.biblioteca;
    final canal = [
      ...catalogo.canalesRecientes(biblioteca),
      ...catalogo.canalesFavoritos(biblioteca),
      ...catalogo.canales.where((c) => c.logo.isNotEmpty),
      ...catalogo.canales,
    ].firstOrNull;
    final pelicula = canal != null ? null : catalogo.peliculas.where((p) => p.logo.isNotEmpty).firstOrNull;
    final serie = canal != null || pelicula != null
        ? null
        : catalogo.series.where((s) => s.imagen.isNotEmpty).firstOrNull;
    if (pelicula == null && serie == null && canal == null) return const SizedBox.shrink();

    final String titulo;
    final String imagen;
    final String insignia;
    final String? etiqueta;
    final String? anio;
    final String bajada;
    final String clave;
    final VoidCallback reproducir;
    final VoidCallback? info;
    final bool esCanal;
    if (canal != null) {
      titulo = canal.nombre;
      imagen = canal.logo;
      insignia = 'EN VIVO';
      etiqueta = categoriaLegible(canal.categoria);
      anio = null;
      final numero = catalogo.numeroDe(canal);
      bajada = [if (numero.isNotEmpty) 'Canal $numero', 'Señal en vivo', if (etiqueta.isNotEmpty) etiqueta].join(' · ');
      clave = Biblioteca.claveDe(canal);
      reproducir = () => NavegacionMovil.of(context).irA(Seccion.enVivo, canal: canal.id);
      info = null;
      esCanal = true;
    } else if (pelicula != null) {
      titulo = sinAnio(pelicula.nombre);
      imagen = pelicula.logo;
      insignia = 'DESTACADA';
      etiqueta = categoriaLegible(pelicula.categoria);
      anio = anioDe(pelicula.nombre)?.toString();
      bajada = 'Película${etiqueta.isEmpty ? '' : ' · $etiqueta'}';
      clave = Biblioteca.claveDe(pelicula);
      reproducir = () => reproducirPelicula(context, pelicula);
      info = () => abrirPantalla<void>(context, PantallaDetalle.pelicula(pelicula));
      esCanal = false;
    } else {
      final laSerie = serie!;
      titulo = laSerie.nombre;
      imagen = laSerie.imagen;
      insignia = 'SERIE';
      etiqueta = categoriaLegible(laSerie.categoria);
      anio = null;
      final temporadas = laSerie.temporadas.length;
      bajada = '$temporadas temporada${temporadas == 1 ? '' : 's'} · ${laSerie.episodios.length} capítulos';
      clave = laSerie.clave;
      reproducir = () => reproducirSerie(context, laSerie);
      info = () => abrirPantalla<void>(context, PantallaDetalle.serie(laSerie));
      esCanal = false;
    }

    // "CYBERPUNK: PROTOCOLO 2099": lo que va después de ":" en celeste
    final corte = titulo.indexOf(':');
    final principal = corte > 0 ? '${titulo.substring(0, corte + 1)}\n' : titulo;
    final resaltado = corte > 0 ? titulo.substring(corte + 1).trim() : '';

    return Padding(
      padding: const EdgeInsets.only(bottom: Espacio.lg),
      child: SizedBox(
        height: 470,
        child: Stack(
          fit: StackFit.expand,
          children: [
            if (esCanal)
              DecoratedBox(
                decoration: const BoxDecoration(
                  gradient: RadialGradient(
                    center: Alignment(0, -.35),
                    radius: .9,
                    colors: [Color(0xFF0B3B42), Tono.fondo],
                  ),
                ),
                child: Imagen(
                  url: imagen,
                  nombre: titulo,
                  ajuste: BoxFit.contain,
                  relleno: const EdgeInsets.fromLTRB(70, 70, 70, 220),
                  fondo: Colors.transparent,
                  tamanioIniciales: 64,
                ),
              )
            else
              Imagen(url: imagen, nombre: titulo),
            // "bg-gradient-to-t from-background via-background/70 to-transparent"
            const DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.bottomCenter,
                  end: Alignment.topCenter,
                  colors: [Tono.fondo, Color(0xB3131317), Colors.transparent],
                ),
              ),
            ),
            // "bg-gradient-to-r from-background/90 via-transparent to-background/30"
            const DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(colors: [Color(0xE6131317), Colors.transparent, Color(0x4D131317)]),
              ),
            ),
            // "h-16 bg-gradient-to-b from-background/60"
            const Align(
              alignment: Alignment.topCenter,
              child: SizedBox(
                height: 64,
                width: double.infinity,
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topCenter,
                      end: Alignment.bottomCenter,
                      colors: [Color(0x99131317), Colors.transparent],
                    ),
                  ),
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(Espacio.margen, 0, Espacio.margen, Espacio.margen),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.end,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      _InsigniaRubi(
                        texto: insignia,
                        icono: esCanal ? null : Icons.local_fire_department_rounded,
                        enVivo: esCanal,
                      ),
                      if (etiqueta.isNotEmpty) Etiqueta(etiqueta.toUpperCase(), color: Tono.dorado),
                      if (anio != null) _EtiquetaGris(anio),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Text.rich(
                    TextSpan(
                      children: [
                        TextSpan(text: principal.toUpperCase()),
                        if (resaltado.isNotEmpty)
                          TextSpan(
                            text: resaltado.toUpperCase(),
                            style: TextStyle(
                              color: Tono.celeste,
                              shadows: [Shadow(color: Tono.celeste.withValues(alpha: .4), blurRadius: 18)],
                            ),
                          ),
                      ],
                    ),
                    maxLines: 3,
                    overflow: TextOverflow.ellipsis,
                    style: Letra.display.copyWith(
                      height: 1.05,
                      shadows: const [Shadow(color: Colors.black54, blurRadius: 12, offset: Offset(0, 4))],
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(bajada, maxLines: 2, overflow: TextOverflow.ellipsis, style: Letra.cuerpo),
                  const SizedBox(height: Espacio.margen),
                  Row(
                    children: [
                      Expanded(
                        child: BotonPrincipal(
                          texto: esCanal ? 'Ver en vivo' : 'Reproducir',
                          alTocar: reproducir,
                          tamanioTexto: 12,
                        ),
                      ),
                      const SizedBox(width: Espacio.xs),
                      BotonRedondo(
                        icono: datos.biblioteca.estaEnMiLista(clave)
                            ? Icons.favorite_rounded
                            : Icons.favorite_border_rounded,
                        color: datos.biblioteca.estaEnMiLista(clave) ? Tono.rubiClaro : Tono.texto,
                        ayuda: datos.biblioteca.estaEnMiLista(clave) ? 'Quitar de favoritos' : 'Agregar a favoritos',
                        alTocar: () => datos.biblioteca.alternarMiLista(clave),
                      ),
                      if (info != null) ...[
                        const SizedBox(width: Espacio.xs),
                        BotonRedondo(icono: Icons.info_outline_rounded, ayuda: 'Más información', alTocar: info),
                      ],
                    ],
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
          SizedBox(
            height: 256,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: Espacio.margen),
              itemCount: tarjetas.length,
              separatorBuilder: (_, _) => const SizedBox(width: Espacio.sm),
              itemBuilder: (_, i) => Align(alignment: Alignment.topCenter, child: tarjetas[i]),
            ),
          ),
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
          SizedBox(
            height: 210,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: Espacio.margen),
              itemCount: canales.length,
              separatorBuilder: (_, _) => const SizedBox(width: Espacio.sm),
              itemBuilder: (_, i) => Align(
                alignment: Alignment.topCenter,
                child: TarjetaEnVivo(
                  canal: canales[i],
                  ancho: 240,
                  numero: catalogo.numeroDe(canales[i]),
                  alTocar: () => irA(Seccion.enVivo, canal: canales[i].id),
                ),
              ),
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
          SizedBox(
            height: 238,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: Espacio.margen),
              itemCount: destacados.length,
              separatorBuilder: (_, _) => const SizedBox(width: Espacio.sm),
              itemBuilder: (_, i) => Align(
                alignment: Alignment.topCenter,
                child: TarjetaEnVivo(
                  canal: destacados[i],
                  numero: catalogo.numeroDe(destacados[i]),
                  alTocar: () => irA(Seccion.enVivo, canal: destacados[i].id),
                ),
              ),
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
