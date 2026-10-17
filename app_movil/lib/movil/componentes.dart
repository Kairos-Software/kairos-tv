/// Las piezas del diseño de Stitch que se repiten en varias pantallas. Cada
/// una dice entre comillas de qué parte del code.html sale.
library;

import 'package:flutter/material.dart';

import '../api/modelos.dart';
import '../tele/enlace.dart';
import 'datos.dart';
import 'estilo.dart';
import 'logo_legible.dart';

/// Iniciales de un nombre ("Canal 26" -> "C2"), lo que se ve si no hay imagen.
String inicialesDe(String nombre) =>
    nombre.split(' ').where((p) => p.isNotEmpty).take(2).map((p) => p[0]).join().toUpperCase();

/// Una imagen de internet (logo, póster). Mientras carga o si falla, queda
/// el fondo con las iniciales del nombre.
class Imagen extends StatelessWidget {
  const Imagen({
    super.key,
    required this.url,
    required this.nombre,
    this.ajuste = BoxFit.cover,
    this.relleno = EdgeInsets.zero,
    this.fondo = Tono.capaAlta,
    this.tamanioIniciales = 22,
  });

  final String url;
  final String nombre;
  final BoxFit ajuste;
  final EdgeInsets relleno;
  final Color fondo;
  final double tamanioIniciales;

  @override
  Widget build(BuildContext context) {
    final iniciales = Center(
      child: Text(
        inicialesDe(nombre),
        style: TextStyle(
          fontFamily: Letra.titulos,
          fontSize: tamanioIniciales,
          fontWeight: FontWeight.w800,
          letterSpacing: -0.5,
          color: Tono.textoSuave,
        ),
      ),
    );
    final imagen = Image.network(
      url,
      fit: ajuste,
      width: double.infinity,
      height: double.infinity,
      errorBuilder: (_, _, _) => iniciales,
      frameBuilder: (_, imagen, cuadro, sincronica) => sincronica || cuadro != null ? imagen : iniciales,
    );
    return ColoredBox(
      color: fondo,
      child: url.isEmpty
          ? iniciales
          : Padding(
              padding: relleno,
              // Entera (un logo): si es oscuro, va sobre una placa clara (logo_legible.dart)
              child: ajuste == BoxFit.contain ? LogoLegible(url: url, imagen: imagen) : imagen,
            ),
    );
  }
}

/// El punto que "late" de lo que está en vivo ("animate-ping": crece y se apaga, 1,5 s).
class PuntoEnVivo extends StatefulWidget {
  const PuntoEnVivo({super.key, this.tamanio = 6, this.color = Tono.sobreRubi});

  final double tamanio;
  final Color color;

  @override
  State<PuntoEnVivo> createState() => _PuntoEnVivoState();
}

class _PuntoEnVivoState extends State<PuntoEnVivo> with SingleTickerProviderStateMixin {
  late final AnimationController _latido = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1500),
  )..repeat();

  @override
  void dispose() {
    _latido.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final punto = Container(
      width: widget.tamanio,
      height: widget.tamanio,
      decoration: BoxDecoration(color: widget.color, shape: BoxShape.circle),
    );
    return SizedBox.square(
      dimension: widget.tamanio,
      child: Stack(
        clipBehavior: Clip.none,
        alignment: Alignment.center,
        children: [
          AnimatedBuilder(
            animation: _latido,
            builder: (_, hijo) => Opacity(
              opacity: (1 - _latido.value) * .75,
              child: Transform.scale(scale: 1 + _latido.value, child: hijo),
            ),
            child: punto,
          ),
          punto,
        ],
      ),
    );
  }
}

/// "EN VIVO": píldora rubí con el punto que late.
class InsigniaEnVivo extends StatelessWidget {
  const InsigniaEnVivo({super.key, this.texto = 'EN VIVO'});

  final String texto;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: Tono.rubi,
        borderRadius: BorderRadius.circular(99),
        boxShadow: const [BoxShadow(color: Colors.black38, blurRadius: 10, offset: Offset(0, 4))],
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          const PuntoEnVivo(),
          const SizedBox(width: 6),
          Text(
            texto,
            style: Letra.mini.copyWith(color: Tono.sobreRubi, fontWeight: FontWeight.w800, letterSpacing: .6),
          ),
        ],
      ),
    );
  }
}

/// Las etiquetas chicas sobre las imágenes ("T2 : E4", "Película", "Sci-Fi").
class Etiqueta extends StatelessWidget {
  const Etiqueta(this.texto, {super.key, this.color = Tono.texto, this.icono, this.redondeada = false});

  final String texto;
  final Color color;
  final IconData? icono;
  final bool redondeada;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: Tono.capaMinima.withValues(alpha: .8),
        borderRadius: BorderRadius.circular(redondeada ? 99 : Curva.chico),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icono != null) ...[Icon(icono, size: 12, color: color), const SizedBox(width: 3)],
          Flexible(
            child: Text(
              texto,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: Letra.mini.copyWith(color: color, letterSpacing: .3),
            ),
          ),
        ],
      ),
    );
  }
}

/// Los chips para filtrar ("category-chip"): el activo celeste con brillo.
class ChipFiltro extends StatelessWidget {
  const ChipFiltro({
    super.key,
    required this.texto,
    required this.activo,
    required this.alTocar,
    this.icono,
    this.puntoEnVivo = false,
    this.compacto = false,
  });

  final String texto;
  final bool activo;
  final VoidCallback alTocar;
  final IconData? icono;
  final bool puntoEnVivo;

  /// "cat-pill" de En Vivo: un poco más chico.
  final bool compacto;

  @override
  Widget build(BuildContext context) {
    final colorTexto = activo ? Tono.sobreCeleste : Tono.textoSuave;
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: alTocar,
        borderRadius: BorderRadius.circular(99),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          padding: EdgeInsets.symmetric(horizontal: compacto ? 14 : 16, vertical: compacto ? 6 : 8),
          decoration: BoxDecoration(
            color: activo ? Tono.celeste : (compacto ? Tono.capa : Tono.capaAlta),
            borderRadius: BorderRadius.circular(99),
            boxShadow: activo ? brilloCeleste(desenfoque: 12, opacidad: .25) : null,
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (icono != null) ...[Icon(icono, size: 16, color: colorTexto), const SizedBox(width: 6)],
              if (puntoEnVivo) ...[const PuntoEnVivo(tamanio: 8, color: Tono.rubi), const SizedBox(width: 6)],
              Text(
                texto,
                style: Letra.etiqueta.copyWith(
                  color: colorTexto,
                  fontWeight: activo ? FontWeight.w700 : FontWeight.w600,
                  letterSpacing: -0.2,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// El título de cada sección ("Continuar Viendo", "Directos Destacados Ahora"...).
class EncabezadoSeccion extends StatelessWidget {
  const EncabezadoSeccion({super.key, required this.titulo, this.icono, this.colorIcono = Tono.celeste, this.final_});

  final String titulo;
  final Widget? icono;
  final Color colorIcono;

  /// Lo de la derecha: "Ver todo >", un contador, un botón...
  final Widget? final_;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(Espacio.margen, 0, Espacio.margen, 12),
      child: Row(
        children: [
          if (icono != null) ...[icono!, const SizedBox(width: 8)],
          Expanded(
            child: Text(titulo, maxLines: 2, overflow: TextOverflow.ellipsis, style: Letra.titulo),
          ),
          ?final_,
        ],
      ),
    );
  }
}

/// "Ver todo >" en celeste.
class VerTodo extends StatelessWidget {
  const VerTodo({super.key, required this.alTocar, this.texto = 'Ver todo'});

  final VoidCallback alTocar;
  final String texto;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: alTocar,
      borderRadius: BorderRadius.circular(8),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 4, horizontal: 2),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(texto, style: Letra.etiqueta.copyWith(color: Tono.celeste)),
            const Icon(Icons.chevron_right_rounded, size: 16, color: Tono.celeste),
          ],
        ),
      ),
    );
  }
}

/// El botón principal: píldora celeste con brillo ("Reproducir").
class BotonPrincipal extends StatelessWidget {
  const BotonPrincipal({
    super.key,
    required this.texto,
    required this.alTocar,
    this.icono = Icons.play_arrow_rounded,
    this.alto = 48,
    this.tamanioTexto = 12,
  });

  final String texto;
  final VoidCallback? alTocar;
  final IconData icono;
  final double alto;
  final double tamanioTexto;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(borderRadius: BorderRadius.circular(99), boxShadow: brilloCeleste()),
      child: Material(
        color: Tono.celeste,
        borderRadius: BorderRadius.circular(99),
        child: InkWell(
          onTap: alTocar,
          borderRadius: BorderRadius.circular(99),
          child: SizedBox(
            height: alto,
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(icono, size: tamanioTexto + 8, color: Tono.sobreCelesteOscuro),
                const SizedBox(width: 8),
                Flexible(
                  child: Text(
                    texto,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: Letra.etiqueta.copyWith(color: Tono.sobreCelesteOscuro, fontSize: tamanioTexto),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Botón redondo traslúcido (el "+" y la "i" de la portada, volumen, etc.).
class BotonRedondo extends StatelessWidget {
  const BotonRedondo({
    super.key,
    required this.icono,
    required this.alTocar,
    this.tamanio = 48,
    this.tamanioIcono = 22,
    this.fondo,
    this.color = Tono.texto,
    this.ayuda,
  });

  final IconData icono;
  final VoidCallback? alTocar;
  final double tamanio;
  final double tamanioIcono;
  final Color? fondo;
  final Color color;
  final String? ayuda;

  @override
  Widget build(BuildContext context) {
    final boton = Material(
      color: fondo ?? Tono.capaAlta.withValues(alpha: .8),
      shape: const CircleBorder(),
      child: InkWell(
        onTap: alTocar,
        customBorder: const CircleBorder(),
        child: SizedBox.square(
          dimension: tamanio,
          child: Icon(icono, size: tamanioIcono, color: color),
        ),
      ),
    );
    return ayuda == null ? boton : Tooltip(message: ayuda!, child: boton);
  }
}

/// La barra de avance de "Continuar viendo" (3-4 px, celeste con brillo).
class BarraAvance extends StatelessWidget {
  const BarraAvance({super.key, required this.fraccion, this.alto = 4});

  final double fraccion;
  final double alto;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: alto,
      child: Stack(
        children: [
          const Positioned.fill(child: ColoredBox(color: Tono.capaMaxima)),
          FractionallySizedBox(
            widthFactor: fraccion.clamp(0, 1),
            child: Container(
              decoration: BoxDecoration(
                color: Tono.celeste,
                boxShadow: [BoxShadow(color: Tono.celeste.withValues(alpha: .7), blurRadius: 8)],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// "2h 05m" / "24 min"
String duracionLegible(Duration duracion) {
  if (duracion.inMinutes >= 60) return '${duracion.inHours}h ${(duracion.inMinutes % 60).toString().padLeft(2, '0')}m';
  return '${duracion.inMinutes.clamp(1, 59)} min';
}

/// "28:45" / "1:02:10"
String reloj(Duration duracion) {
  final segundos = (duracion.inSeconds % 60).toString().padLeft(2, '0');
  final minutos = (duracion.inMinutes % 60).toString().padLeft(duracion.inHours > 0 ? 2 : 1, '0');
  return duracion.inHours > 0 ? '${duracion.inHours}:$minutos:$segundos' : '$minutos:$segundos';
}

// ── Tarjetas ───────────────────────────────────────────────────────

/// Póster vertical 2:3 de la grilla "Tendencias" (película o serie).
class TarjetaPoster extends StatelessWidget {
  const TarjetaPoster({
    super.key,
    required this.titulo,
    required this.subtitulo,
    required this.imagen,
    required this.alTocar,
    this.etiqueta,
    this.esquina,
    this.progreso,
  });

  final String titulo;
  final String subtitulo;
  final String imagen;
  final VoidCallback alTocar;

  /// Arriba a la izquierda (la categoría).
  final String? etiqueta;

  /// Arriba a la derecha, en dorado (el año).
  final String? esquina;

  /// Por dónde iba (0 a 1), si la empezó.
  final double? progreso;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Tono.capa,
      borderRadius: BorderRadius.circular(Curva.grande),
      clipBehavior: Clip.antiAlias,
      elevation: 4,
      shadowColor: Colors.black54,
      child: InkWell(
        onTap: alTocar,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            AspectRatio(
              aspectRatio: 2 / 3,
              child: Stack(
                fit: StackFit.expand,
                children: [
                  Imagen(url: imagen, nombre: titulo),
                  const DecoratedBox(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.bottomCenter,
                        end: Alignment.topCenter,
                        colors: [Color(0xCC1F1F24), Colors.transparent],
                        stops: [0, .5],
                      ),
                    ),
                  ),
                  if (etiqueta != null && etiqueta!.isNotEmpty)
                    Positioned(
                      top: 8,
                      left: 8,
                      right: 52,
                      child: Align(
                        alignment: Alignment.topLeft,
                        child: Etiqueta(etiqueta!, color: Tono.celesteClaro),
                      ),
                    ),
                  if (esquina != null) Positioned(top: 8, right: 8, child: Etiqueta(esquina!, color: Tono.dorado)),
                  if (progreso != null)
                    Positioned(left: 0, right: 0, bottom: 0, child: BarraAvance(fraccion: progreso!)),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    titulo,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: Letra.etiqueta.copyWith(fontWeight: FontWeight.w700),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    subtitulo,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: Letra.cuerpo.copyWith(fontSize: 12),
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

/// Tarjeta 16:9 de "Directos Destacados Ahora" (un canal en vivo).
class TarjetaEnVivo extends StatelessWidget {
  const TarjetaEnVivo({super.key, required this.canal, required this.alTocar, this.ancho = 288, this.numero});

  final Canal canal;
  final VoidCallback alTocar;
  final double ancho;

  /// El número del canal (Catalogo.numeroDe); si no se pasa, el que trae la lista.
  final String? numero;

  @override
  Widget build(BuildContext context) {
    final categoria = categoriaLegible(canal.categoria);
    return SizedBox(
      width: ancho,
      child: Material(
        color: Tono.capaBaja,
        borderRadius: BorderRadius.circular(Curva.grande),
        clipBehavior: Clip.antiAlias,
        elevation: 6,
        shadowColor: Colors.black54,
        child: InkWell(
          onTap: alTocar,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              AspectRatio(
                aspectRatio: 16 / 9,
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    // No hay captura del vivo: el logo del canal sobre un fondo con luz
                    DecoratedBox(
                      decoration: const BoxDecoration(
                        gradient: RadialGradient(
                          center: Alignment(0, -.2),
                          radius: 1.1,
                          colors: [Color(0xFF2A292E), Tono.capaMinima],
                        ),
                      ),
                      child: Imagen(
                        url: canal.logo,
                        nombre: canal.nombre,
                        ajuste: BoxFit.contain,
                        relleno: const EdgeInsets.fromLTRB(56, 30, 56, 30),
                        fondo: Colors.transparent,
                        tamanioIniciales: 34,
                      ),
                    ),
                    const DecoratedBox(
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          begin: Alignment.bottomCenter,
                          end: Alignment.topCenter,
                          colors: [Tono.capaMinima, Colors.transparent],
                          stops: [0, .45],
                        ),
                      ),
                    ),
                    const Positioned(top: 10, left: 10, child: InsigniaEnVivo()),
                    if ((numero ?? canal.numero).isNotEmpty)
                      Positioned(bottom: 10, right: 10, child: Etiqueta('CH ${numero ?? canal.numero}')),
                  ],
                ),
              ),
              Padding(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Container(
                          width: 8,
                          height: 8,
                          decoration: const BoxDecoration(color: Tono.celeste, shape: BoxShape.circle),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            categoria.isEmpty ? 'TV EN VIVO' : categoria.toUpperCase(),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: Letra.mini.copyWith(
                              color: Tono.celeste,
                              fontWeight: FontWeight.w600,
                              letterSpacing: .6,
                            ),
                          ),
                        ),
                        Text('En Directo', style: Letra.numeros),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      canal.nombre,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: Letra.titulo.copyWith(fontSize: 16, height: 20 / 16),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Tarjeta de "Continuar Viendo" (w-64, imagen 16:9 con el botón de play y la barra).
class TarjetaContinuar extends StatelessWidget {
  const TarjetaContinuar({
    super.key,
    required this.titulo,
    required this.subtitulo,
    required this.imagen,
    required this.etiqueta,
    required this.progreso,
    required this.alTocar,
    required this.alQuitar,
  });

  final String titulo;
  final String subtitulo;
  final String imagen;
  final String etiqueta;
  final Progreso progreso;
  final VoidCallback alTocar;
  final VoidCallback alQuitar;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 256,
      child: Material(
        color: Tono.capa,
        borderRadius: BorderRadius.circular(Curva.grande),
        clipBehavior: Clip.antiAlias,
        elevation: 4,
        shadowColor: Colors.black54,
        child: InkWell(
          onTap: alTocar,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              AspectRatio(
                aspectRatio: 16 / 9,
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    Imagen(url: imagen, nombre: titulo),
                    ColoredBox(color: Tono.fondo.withValues(alpha: .4)),
                    Center(
                      child: Container(
                        width: 44,
                        height: 44,
                        decoration: BoxDecoration(
                          color: Tono.capaMinima.withValues(alpha: .8),
                          shape: BoxShape.circle,
                          boxShadow: const [BoxShadow(color: Colors.black45, blurRadius: 12)],
                        ),
                        child: const Icon(Icons.play_arrow_rounded, size: 24, color: Tono.celeste),
                      ),
                    ),
                    Positioned(top: 8, right: 8, child: Etiqueta(etiqueta)),
                    Positioned(left: 0, right: 0, bottom: 0, child: BarraAvance(fraccion: progreso.fraccion)),
                  ],
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(12, 12, 4, 6),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            titulo,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: Letra.etiqueta.copyWith(fontWeight: FontWeight.w700),
                          ),
                        ),
                        const SizedBox(width: 4),
                        Padding(
                          padding: const EdgeInsets.only(right: 8),
                          child: Text(
                            '${(progreso.fraccion * 100).round()}%',
                            style: Letra.numeros.copyWith(color: Tono.celeste),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(subtitulo, maxLines: 1, overflow: TextOverflow.ellipsis, style: Letra.cuerpo),
                    Row(
                      children: [
                        const Icon(Icons.schedule_rounded, size: 14, color: Tono.textoSuave),
                        const SizedBox(width: 4),
                        Expanded(child: Text('${duracionLegible(progreso.falta)} restantes', style: Letra.numeros)),
                        IconButton(
                          tooltip: 'Quitar de Continuar viendo',
                          visualDensity: VisualDensity.compact,
                          onPressed: alQuitar,
                          icon: const Icon(Icons.more_vert_rounded, size: 16, color: Tono.textoSuave),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Lo que se muestra mientras no hay nada (sin películas cargadas, búsqueda vacía...).
class Vacio extends StatelessWidget {
  const Vacio({super.key, required this.icono, required this.texto, this.accion});

  final IconData icono;
  final String texto;
  final Widget? accion;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icono, size: 48, color: Tono.textoApagado),
            const SizedBox(height: 12),
            Text(texto, textAlign: TextAlign.center, style: Letra.cuerpo),
            if (accion != null) ...[const SizedBox(height: 16), accion!],
          ],
        ),
      ),
    );
  }
}

/// Abre una pantalla nueva llevándole el catálogo, la biblioteca y el diseño
/// (las pantallas que se abren encima no los "heredan" solas).
///
/// Con una tele conectada ("Ver en la tele", lib/tele/), la tele muestra lo
/// mismo y, si es un reproductor, en el celular queda el control remoto.
Future<T?> abrirPantalla<T>(BuildContext context, Widget pantalla) {
  final datos = DatosScope.of(context);
  final enLaTele = Tele.instancia.abrir(pantalla);
  final abierta = Navigator.push<T>(
    context,
    MaterialPageRoute<T>(
      builder: (_) => DatosScope(
        catalogo: datos.catalogo,
        biblioteca: datos.biblioteca,
        child: Theme(data: temaMovil(), child: enLaTele?.enElCelular ?? pantalla),
      ),
    ),
  );
  if (enLaTele != null) abierta.whenComplete(() => Tele.instancia.cerrar(enLaTele));
  return abierta;
}
