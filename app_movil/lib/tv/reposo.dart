/// El modo reposo de la TV: si nadie toca el control durante un rato
/// (PantallaTv.esperaReposo, 1 minuto) y no se está reproduciendo nada,
/// aparece una "vidriera" a pantalla completa, como publicidad de Kairos TV.
///
/// Todo sale del catálogo DE ESE MOMENTO (no hay imágenes fijas dentro de la
/// app): si una película se saca o deja de ser estreno, desaparece sola de la
/// vidriera, sin sacar una versión nueva. Las escenas ([Escena]):
///
///   - logo:      el logo de Kairos TV y la hora. Siempre se vuelve a ella.
///   - titulo:    una película, serie o canal: la imagen grande y borrosa de
///                fondo con un zoom lento, el póster nítido, el título y qué es.
///                Va una distinta entre cada una de las otras. Lo marcado
///                en el panel como "Destacado en la TV" sale más seguido
///                ([intercalarDestacados]).
///   - estrenos:  los pósters de las películas más nuevas (por el año del nombre).
///   - cifras:    "Más de 700 películas · 400 series · 70 canales en vivo".
///   - enVivo:    los logos de los canales.
///   - series:    los pósters de algunas series.
///
/// Todas llevan el logo. Las de la marca (logo, cifras, grupos) van sobre el
/// escenario de neón DIBUJADO (tv/escenario.dart): nítido en cualquier TV.
///
/// Calidad: las imágenes del catálogo (las que traen las listas) muchas veces
/// son chicas. Al entrar se bajan TODAS y se mide cada una
/// ([_PantallaReposoTvState._preparar]): en grande (escena "titulo") solo van
/// las que tienen buena resolución, y en los grupos, las que alcanzan para su
/// tamaño. Si no hay suficientes, la escena se saltea: mejor no mostrarla que
/// mostrarla pixelada.
///
/// Fluidez (los TV box son lentos): cambia cada [_cadaCuanto]. Las escenas
/// solo muestran imágenes YA bajadas y decodificadas (nunca cargan nada al
/// aparecer), el escenario de fondo es uno solo para todas, y en el cambio la
/// escena que se va se apaga antes de que aparezca la nueva (nunca se dibujan
/// dos a la vez).
///
/// Cualquier botón la cierra y se vuelve a donde se estaba (esa tecla no hace
/// nada más). Mantiene la pantalla encendida [_encendidaHasta]; después deja
/// que la TV se apague o ponga su propio protector (no gastar ni marcar la pantalla).
library;

import 'dart:async';
import 'dart:math';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:wakelock_plus/wakelock_plus.dart';

import '../api/modelos.dart';
import '../marca.dart';
import '../movil/datos.dart';
import '../movil/estilo.dart';
import 'escenario.dart';

const _cadaCuanto = Duration(seconds: 12);
const _fundido = Duration(milliseconds: 1400);
const _encendidaHasta = Duration(minutes: 30);
const _maximoTitulos = 20;

/// Lo destacado en el panel ("Destacado en la TV") sale más seguido que lo
/// demás, pero no todo el tiempo: en la lista de títulos, uno de cada
/// [_cadaCuantosUnDestacado] lugares es para un destacado (como mucho
/// [_lugaresDestacados] destacados distintos por vez, cada uno hasta dos
/// veces); lo que sale al azar aparece una vez. En los grupos (series, canales)
/// van primero.
const _cadaCuantosUnDestacado = 3;
const _lugaresDestacados = 7;

/// Cuántos pósters o logos van en las escenas de grupo, y cuántos hacen falta para armarlas.
const _porGrupo = 5;
const _logosEnVivo = 12;
const _minimoGrupo = 4;

/// Se eligen el doble de candidatos: después se descartan los de mala calidad.
const _candidatos = 2;

/// Las imágenes se guardan achicadas a este ancho (más no hace falta para la
/// TV, y así entran todas en la memoria de un TV box).
const _anchoDecodificado = 400;

/// El ancho mínimo (en píxeles de la imagen original) para que se vea bien:
/// un póster en grande (380 px de ancho en la TV), un póster en un grupo
/// (~300 px), un logo en grande y un logo en la grilla.
const _minimoPosterGrande = 340.0;
const _minimoPosterGrupo = 220.0;
const _minimoLogoGrande = 240.0;
const _minimoLogoGrupo = 120.0;

enum Escena { logo, titulo, estrenos, cifras, enVivo, series }

/// Una película, serie o canal.
class Diapositiva {
  const Diapositiva({
    required this.titulo,
    required this.tipo,
    required this.imagen,
    this.detalle = '',
    this.poster = true,
  });

  final String titulo;

  /// "Película", "Serie", "En vivo".
  final String tipo;
  final String imagen;

  /// Ej: "3 temporadas", la categoría.
  final String detalle;

  /// Póster vertical (películas y series) o logo (canales).
  final bool poster;
}

/// Lo que muestra el modo reposo, sacado del catálogo.
class Vidriera {
  Vidriera({
    this.titulos = const [],
    this.estrenos = const [],
    this.canales = const [],
    this.series = const [],
    this.peliculas = 0,
    this.cantidadSeries = 0,
    this.cantidadCanales = 0,
    this.sonEstrenos = true,
  });

  /// Para la escena "titulo" (una por vez, mezclados).
  final List<Diapositiva> titulos;
  final List<Diapositiva> estrenos;
  final List<Diapositiva> canales;
  final List<Diapositiva> series;

  /// Para las cifras.
  final int peliculas;
  final int cantidadSeries;
  final int cantidadCanales;

  /// Si las películas de "estrenos" son de este año o el anterior. Si no, se
  /// titula "Películas destacadas" (no se le dice estreno a algo de hace años).
  final bool sonEstrenos;

  static Vidriera delCatalogo(Catalogo catalogo, {Random? azar, int? anioActual}) {
    azar ??= Random();
    anioActual ??= DateTime.now().year;
    List<T> algunos<T>(Iterable<T> lista, int cuantos) => (lista.toList()..shuffle(azar)).take(cuantos).toList();

    Diapositiva dePelicula(Canal pelicula) => Diapositiva(
      titulo: sinAnio(pelicula.nombre),
      tipo: 'Película',
      imagen: pelicula.logo,
      detalle: _anio(pelicula.nombre),
    );
    Diapositiva deSerie(Serie serie) => Diapositiva(
      titulo: serie.nombre,
      tipo: 'Serie',
      imagen: serie.imagen,
      detalle: serie.temporadas.length == 1 ? '1 temporada' : '${serie.temporadas.length} temporadas',
    );
    Diapositiva deCanal(Canal canal) => Diapositiva(
      titulo: canal.nombre,
      tipo: 'En vivo',
      imagen: canal.logo,
      detalle: categoriaLegible(canal.categoria),
      poster: false,
    );

    final peliculas = catalogo.peliculas.where((p) => p.logo.isNotEmpty).toList();
    final series = catalogo.series.where((s) => s.imagen.isNotEmpty).toList();
    final canales = catalogo.canales.where((c) => c.logo.isNotEmpty).toList();

    // Lo destacado en el panel y lo demás (que sale al azar)
    final destacados = [
      for (final p in peliculas.where((p) => p.destacado)) dePelicula(p),
      for (final s in series.where((s) => s.destacada)) deSerie(s),
      for (final c in canales.where((c) => c.destacado)) deCanal(c),
    ];
    final comunes = [
      for (final p in algunos(peliculas.where((p) => !p.destacado), 9)) dePelicula(p),
      for (final s in algunos(series.where((s) => !s.destacada), 7)) deSerie(s),
      for (final c in algunos(canales.where((c) => !c.destacado), 4)) deCanal(c),
    ]..shuffle(azar);

    /// [cuantos] de la lista, primero los destacados (al azar entre ellos) y después los demás.
    List<T> primeroDestacados<T>(List<T> lista, bool Function(T) destacado, int cuantos) => [
      ...algunos(lista.where(destacado), cuantos),
      ...algunos(lista.where((x) => !destacado(x)), cuantos),
    ].take(cuantos).toList();

    // Estrenos: de las 15 más nuevas, 5 al azar (así cambian de una vez a la otra)
    final conAnio = peliculas.where((p) => anioDe(p.nombre) != null).toList()
      ..sort((a, b) => anioDe(b.nombre)!.compareTo(anioDe(a.nombre)!));
    final nuevas = algunos(conAnio.take(20), _porGrupo * _candidatos);
    final masNueva = nuevas.isEmpty ? 0 : nuevas.map((p) => anioDe(p.nombre)!).reduce(max);

    return Vidriera(
      titulos: intercalarDestacados(comunes, algunos(destacados, _lugaresDestacados)),
      estrenos: [for (final p in nuevas) dePelicula(p)],
      sonEstrenos: masNueva >= anioActual - 1,
      canales: [for (final c in primeroDestacados(canales, (c) => c.destacado, _logosEnVivo * 2)) deCanal(c)],
      series: [for (final s in primeroDestacados(series, (s) => s.destacada, _porGrupo * _candidatos)) deSerie(s)],
      peliculas: catalogo.peliculas.length,
      cantidadSeries: catalogo.series.length,
      cantidadCanales: catalogo.canales.length,
    );
  }

  static String _anio(String nombre) => anioDe(nombre)?.toString() ?? '';

  /// El orden de las escenas: el logo, y entre cada una de las otras, un título.
  /// Las que no tienen con qué armarse no van.
  List<Escena> get recorrido {
    final grupos = [
      if (estrenos.length >= _minimoGrupo) Escena.estrenos,
      if (peliculas + cantidadSeries + cantidadCanales > 0) Escena.cifras,
      if (canales.length >= _minimoGrupo) Escena.enVivo,
      if (series.length >= _minimoGrupo) Escena.series,
    ];
    return [
      Escena.logo,
      for (final grupo in grupos) ...[if (titulos.isNotEmpty) Escena.titulo, grupo],
      if (grupos.isEmpty && titulos.isNotEmpty) ...List.filled(3, Escena.titulo),
    ];
  }
}

/// Los títulos del reposo: [comunes] (al azar) con [destacados] intercalados,
/// uno cada [_cadaCuantosUnDestacado] lugares (el segundo, el quinto...). Si
/// hay pocos destacados, cada uno va dos veces (nunca seguidas): así sale más
/// seguido que lo común, que va una sola vez.
List<T> intercalarDestacados<T>(List<T> comunes, List<T> destacados) {
  final lugares = [...destacados, ...destacados].take(_lugaresDestacados).toList();
  final titulos = <T>[];
  var comun = 0;
  var destacado = 0;
  while (titulos.length < _maximoTitulos && (comun < comunes.length || destacado < lugares.length)) {
    final tocaDestacado = titulos.length % _cadaCuantosUnDestacado == 1 || comun >= comunes.length;
    if (tocaDestacado && destacado < lugares.length) {
      titulos.add(lugares[destacado++]);
    } else if (comun < comunes.length) {
      titulos.add(comunes[comun++]);
    } else {
      break;
    }
  }
  return titulos;
}

/// "+700", "+1.000": redondea para abajo (a 10 o a 50/100), así la cifra nunca
/// promete de más. Si es justa, sin el "+".
String cifraRedonda(int cantidad) {
  if (cantidad < 10) return '$cantidad';
  final paso = cantidad < 100 ? 10 : (cantidad < 1000 ? 50 : 100);
  final redondo = cantidad ~/ paso * paso;
  final conPuntos = '$redondo'.replaceAllMapped(RegExp(r'(\d)(?=(\d{3})+$)'), (m) => '${m[1]}.');
  return redondo == cantidad ? conPuntos : '+$conPuntos';
}

class PantallaReposoTv extends StatefulWidget {
  const PantallaReposoTv({super.key, required this.vidriera, this.imagenDe = imagenDeInternet});

  final Vidriera vidriera;

  /// De dónde sale cada imagen (en las pruebas, imágenes armadas en memoria).
  final ImageProvider Function(String url) imagenDe;

  /// La imagen ya achicada a [_anchoDecodificado] (o menos, si es más chica).
  static ImageProvider imagenDeInternet(String url) => ResizeImage(NetworkImage(url), width: _anchoDecodificado);

  @override
  State<PantallaReposoTv> createState() => _PantallaReposoTvState();
}

/// Una diapositiva con su imagen ya bajada y lista para dibujarse.
class _Lista {
  const _Lista(this.diapositiva, this.imagen);

  final Diapositiva diapositiva;
  final ui.Image imagen;
}

class _PantallaReposoTvState extends State<PantallaReposoTv> {
  late final List<Escena> _recorrido = widget.vidriera.recorrido;
  int _paso = 0;

  /// El título que se muestra ahora y el próximo.
  _Lista? _titulo;
  int _siguienteTitulo = 0;
  Timer? _reloj;
  Timer? _apagar;

  /// Las imágenes que ya se bajaron, se midieron y alcanzan para mostrarse
  /// (url → imagen). Las escenas solo usan estas: así al cambiar de escena
  /// no hay nada que bajar ni que decodificar, y no se traba.
  final _listas = <String, ui.Image>{};
  final _escuchas = <(ImageStream, ImageStreamListener)>[];

  Escena get _escena => _recorrido[_paso];

  @override
  void initState() {
    super.initState();
    WakelockPlus.enable().catchError((Object _) {});
    _apagar = Timer(_encendidaHasta, () => WakelockPlus.disable().catchError((Object _) {}));
    _reloj = Timer.periodic(_cadaCuanto, (_) => _avanzar());
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _preparar();
    });
  }

  @override
  void dispose() {
    for (final (flujo, escucha) in _escuchas) {
      flujo.removeListener(escucha);
    }
    for (final imagen in _listas.values) {
      imagen.dispose();
    }
    _reloj?.cancel();
    _apagar?.cancel();
    WakelockPlus.disable().catchError((Object _) {});
    super.dispose();
  }

  /// Baja y decodifica todas las imágenes mientras se ve la escena del logo
  /// (que va primero y da tiempo de sobra). Se quedan las que tienen buena
  /// resolución; las chicas se sueltan enseguida (se verían pixeladas).
  void _preparar() {
    final vidriera = widget.vidriera;
    // El mínimo para entrar en alguna escena (en un grupo, que es lo más chico)
    final minimos = <String, double>{
      for (final d in [...vidriera.titulos, ...vidriera.estrenos, ...vidriera.series, ...vidriera.canales])
        d.imagen: d.poster ? _minimoPosterGrupo : _minimoLogoGrupo,
    };
    final configuracion = createLocalImageConfiguration(context);
    for (final MapEntry(key: url, value: minimo) in minimos.entries) {
      final flujo = widget.imagenDe(url).resolve(configuracion);
      late final (ImageStream, ImageStreamListener) par;
      void soltar() {
        if (_escuchas.remove(par)) flujo.removeListener(par.$2);
      }

      par = (
        flujo,
        ImageStreamListener((info, _) {
          soltar();
          if (mounted && info.image.width >= minimo && !_listas.containsKey(url)) {
            _listas[url] = info.image;
          } else {
            info.dispose();
          }
        }, onError: (_, _) => soltar()),
      );
      _escuchas.add(par);
      flujo.addListener(par.$2);
    }
  }

  /// La imagen lista, si se ve bien a este tamaño.
  _Lista? _lista(Diapositiva diapositiva, {required bool grande}) {
    final imagen = _listas[diapositiva.imagen];
    if (imagen == null) return null;
    final minimo = diapositiva.poster
        ? (grande ? _minimoPosterGrande : _minimoPosterGrupo)
        : (grande ? _minimoLogoGrande : _minimoLogoGrupo);
    return imagen.width >= minimo ? _Lista(diapositiva, imagen) : null;
  }

  List<_Lista> _buenas(List<Diapositiva> lista, int cuantas) =>
      [for (final d in lista) ?_lista(d, grande: false)].take(cuantas).toList();

  /// El próximo título que se ve bien en grande, o null.
  int? _proximoTitulo() {
    final lista = widget.vidriera.titulos;
    for (var i = 0; i < lista.length; i++) {
      final indice = (_siguienteTitulo + i) % lista.length;
      if (_lista(lista[indice], grande: true) != null) return indice;
    }
    return null;
  }

  /// ¿Esta escena tiene con qué armarse bien ahora?
  bool _sePuede(Escena escena) {
    final vidriera = widget.vidriera;
    return switch (escena) {
      Escena.logo || Escena.cifras => true,
      Escena.titulo => _proximoTitulo() != null,
      Escena.estrenos => _buenas(vidriera.estrenos, _porGrupo).length >= _minimoGrupo,
      Escena.series => _buenas(vidriera.series, _porGrupo).length >= _minimoGrupo,
      Escena.enVivo => _buenas(vidriera.canales, _logosEnVivo).length >= _minimoGrupo,
    };
  }

  void _avanzar() {
    if (!mounted) return;
    setState(() {
      // La siguiente que se pueda armar (el logo siempre se puede)
      do {
        _paso = (_paso + 1) % _recorrido.length;
      } while (!_sePuede(_escena));
      if (_escena != Escena.titulo) return;
      final indice = _proximoTitulo()!;
      _titulo = _lista(widget.vidriera.titulos[indice], grande: true);
      _siguienteTitulo = indice + 1;
    });
  }

  void _salir() {
    if (mounted) Navigator.of(context).maybePop();
  }

  Widget _pantalla() {
    final vidriera = widget.vidriera;
    return switch (_escena) {
      Escena.logo => const _PantallaLogo(),
      Escena.titulo => _PantallaTitulo(lista: _titulo!),
      Escena.estrenos => _PantallaGrupo(
        sobretitulo: vidriera.sonEstrenos ? 'Recién llegadas' : 'Para ver hoy',
        titulo: vidriera.sonEstrenos ? 'Estrenos' : 'Películas destacadas',
        bajada: vidriera.sonEstrenos ? 'Las películas más nuevas, ya en Kairos TV' : 'Elegí la tuya en Kairos TV',
        listas: _buenas(vidriera.estrenos, _porGrupo),
      ),
      Escena.series => _PantallaGrupo(
        sobretitulo: 'Series',
        titulo: 'Temporadas completas',
        bajada: 'Seguí tus series capítulo a capítulo',
        listas: _buenas(vidriera.series, _porGrupo),
      ),
      Escena.enVivo => _PantallaEnVivo(
        canales: _buenas(vidriera.canales, _logosEnVivo),
        cantidad: vidriera.cantidadCanales,
      ),
      Escena.cifras => _PantallaCifras(vidriera: vidriera),
    };
  }

  @override
  Widget build(BuildContext context) {
    final enElLogo = _escena == Escena.logo;
    return Focus(
      autofocus: true,
      // Cualquier botón vuelve (y no hace nada más). Se sale al SOLTARLO: si
      // no, el "soltar OK" llegaría a la pantalla de abajo y abriría lo elegido.
      onKeyEvent: (_, evento) {
        if (evento is KeyUpEvent) _salir();
        return KeyEventResult.handled;
      },
      child: GestureDetector(
        onTap: _salir,
        child: Material(
          color: Colors.black,
          child: Stack(
            fit: StackFit.expand,
            children: [
              // Un solo escenario de fondo para todas las escenas: a pleno y con
              // el punto rubí en la del logo, más tenue detrás de las demás.
              TweenAnimationBuilder<double>(
                tween: Tween(end: enElLogo ? 1 : 0),
                duration: _fundido,
                curve: Curves.easeInOut,
                builder: (_, logo, _) => EscenarioNeon(intensidad: .7 + .3 * logo, rubi: logo),
              ),
              // La escena que se va se apaga del todo antes de que aparezca la
              // nueva: así nunca se dibujan dos a la vez (en la TV, eso traba).
              AnimatedSwitcher(
                duration: _fundido,
                transitionBuilder: (hijo, animacion) => FadeTransition(
                  opacity: CurvedAnimation(
                    parent: animacion,
                    curve: const Interval(.5, 1, curve: Curves.easeOut),
                  ),
                  child: hijo,
                ),
                child: KeyedSubtree(key: ValueKey(_paso), child: _pantalla()),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// El logo abajo a la izquierda y la hora abajo a la derecha, en todas las escenas (menos la del logo).
class _Pie extends StatelessWidget {
  const _Pie();

  @override
  Widget build(BuildContext context) {
    return const Stack(
      children: [
        Positioned(left: 120, bottom: 48, child: LogoKairos(tamanio: 34)),
        Positioned(right: 120, bottom: 48, child: _Hora()),
      ],
    );
  }
}

/// Sobre el escenario de las escenas de grupo: oscurecido a la izquierda
/// (donde va el texto) para que se lea bien.
class _FondoMarca extends StatelessWidget {
  const _FondoMarca({this.centrado = false});

  /// El texto va al centro (las cifras): se oscurece el medio en vez de la izquierda.
  final bool centrado;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: centrado
            ? const RadialGradient(radius: .6, colors: [Color(0xB3040507), Color(0x00040507)])
            : const LinearGradient(
                begin: Alignment.centerLeft,
                end: Alignment.centerRight,
                colors: [Color(0xCC040507), Color(0x66040507), Color(0x33040507)],
              ),
      ),
    );
  }
}

/// "RECIÉN LLEGADAS" en celeste, el título grande y una bajada.
class _Encabezado extends StatelessWidget {
  const _Encabezado({required this.sobretitulo, required this.titulo, required this.bajada, this.color = Tono.celeste});

  final String sobretitulo;
  final String titulo;
  final String bajada;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          sobretitulo.toUpperCase(),
          style: TextStyle(
            fontFamily: Letra.texto,
            fontSize: 20,
            fontWeight: FontWeight.w800,
            letterSpacing: 3,
            color: color,
          ),
        ),
        const SizedBox(height: 10),
        Text(titulo, style: LetraTv.portada.copyWith(fontSize: 64)),
        const SizedBox(height: 8),
        Text(bajada, style: LetraTv.cuerpo.copyWith(fontSize: 24)),
      ],
    );
  }
}

/// La pantalla a la que siempre se vuelve: el logo, la hora y cómo salir.
class _PantallaLogo extends StatelessWidget {
  const _PantallaLogo();

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: [
        // El logo, un poco arriba del centro (sobre el punto de fuga del pasillo)
        const Align(alignment: Alignment(0, -.12), child: LogoKairos(tamanio: 150)),
        Align(
          alignment: const Alignment(0, .62),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const _Hora(grande: true),
              const SizedBox(height: 10),
              Text(
                'Apretá cualquier botón para volver',
                style: LetraTv.ayuda.copyWith(fontSize: 18, color: Tono.textoSuave),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

/// Una película, serie o canal: la imagen de fondo borrosa con zoom lento, el póster y el título.
class _PantallaTitulo extends StatefulWidget {
  const _PantallaTitulo({required this.lista});

  final _Lista lista;

  @override
  State<_PantallaTitulo> createState() => _PantallaTituloState();
}

class _PantallaTituloState extends State<_PantallaTitulo> {
  /// El fondo: la misma imagen, chiquita y ya borroneada UNA vez. Agrandada
  /// queda suave, y moverla no cuesta nada (difuminar la pantalla entera en
  /// cada cuadro, como antes, trababa los TV box).
  late final ui.Image _borrosa = _borronear(widget.lista.imagen);

  static ui.Image _borronear(ui.Image imagen) {
    const destino = Rect.fromLTWH(0, 0, 96, 54);
    final origen = Size(imagen.width.toDouble(), imagen.height.toDouble());
    final ajuste = applyBoxFit(BoxFit.cover, origen, destino.size);
    final recorte = Alignment.center.inscribe(ajuste.source, Offset.zero & origen);
    final grabadora = ui.PictureRecorder();
    Canvas(grabadora).drawImageRect(
      imagen,
      recorte,
      destino,
      Paint()
        ..filterQuality = FilterQuality.medium
        ..imageFilter = ui.ImageFilter.blur(sigmaX: 2.5, sigmaY: 2.5),
    );
    final dibujo = grabadora.endRecording();
    final resultado = dibujo.toImageSync(destino.width.toInt(), destino.height.toInt());
    dibujo.dispose();
    return resultado;
  }

  @override
  void dispose() {
    _borrosa.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final diapositiva = widget.lista.diapositiva;
    return Stack(
      fit: StackFit.expand,
      children: [
        // Fondo: la imagen enorme y borrosa, con un zoom lento ("Ken Burns")
        TweenAnimationBuilder<double>(
          tween: Tween(begin: 1.08, end: 1.22),
          duration: _cadaCuanto + _fundido,
          builder: (_, escala, hijo) => Transform.scale(scale: escala, child: hijo),
          child: RawImage(image: _borrosa, fit: BoxFit.cover, filterQuality: FilterQuality.medium),
        ),
        // Oscurecido para que se lea el texto
        const DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: [Color(0xF2131317), Color(0xB3131317), Color(0x66131317)],
              stops: [0, .5, 1],
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(120, 90, 120, 90),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 7),
                      decoration: BoxDecoration(
                        color: diapositiva.tipo == 'En vivo' ? Tono.rubi : Tono.celeste,
                        borderRadius: BorderRadius.circular(99),
                      ),
                      child: Text(
                        diapositiva.tipo.toUpperCase(),
                        style: TextStyle(
                          fontFamily: Letra.texto,
                          fontSize: 15,
                          fontWeight: FontWeight.w800,
                          letterSpacing: 1.4,
                          color: diapositiva.tipo == 'En vivo' ? Colors.white : Tono.sobreCelesteOscuro,
                        ),
                      ),
                    ),
                    const SizedBox(height: 26),
                    Text(
                      diapositiva.titulo,
                      maxLines: 3,
                      overflow: TextOverflow.ellipsis,
                      style: LetraTv.portada.copyWith(fontSize: 72),
                    ),
                    if (diapositiva.detalle.isNotEmpty) ...[
                      const SizedBox(height: 14),
                      Text(diapositiva.detalle, style: LetraTv.cuerpo.copyWith(fontSize: 24)),
                    ],
                    const SizedBox(height: 34),
                    Text(
                      'Disponible en Kairos TV',
                      style: LetraTv.ayuda.copyWith(fontSize: 20, color: Tono.celesteClaro),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 80),
              // El póster nítido (o el logo del canal sobre una tarjeta)
              Container(
                width: diapositiva.poster ? 380 : 420,
                height: diapositiva.poster ? 570 : 300,
                padding: diapositiva.poster ? EdgeInsets.zero : const EdgeInsets.all(48),
                decoration: BoxDecoration(
                  color: Tono.capaAlta,
                  borderRadius: BorderRadius.circular(Curva.portada),
                  boxShadow: const [BoxShadow(color: Colors.black54, blurRadius: 60, offset: Offset(0, 24))],
                ),
                clipBehavior: Clip.antiAlias,
                child: _Foto(imagen: widget.lista.imagen, poster: diapositiva.poster),
              ),
            ],
          ),
        ),
        const _Pie(),
      ],
    );
  }
}

/// Una imagen ya lista: el póster llena su lugar; el logo entra entero.
class _Foto extends StatelessWidget {
  const _Foto({required this.imagen, required this.poster});

  final ui.Image imagen;
  final bool poster;

  @override
  Widget build(BuildContext context) => SizedBox.expand(
    child: RawImage(image: imagen, fit: poster ? BoxFit.cover : BoxFit.contain, filterQuality: FilterQuality.medium),
  );
}

/// Estrenos o series: el encabezado y una fila de pósters que suben de a uno.
class _PantallaGrupo extends StatelessWidget {
  const _PantallaGrupo({required this.sobretitulo, required this.titulo, required this.bajada, required this.listas});

  final String sobretitulo;
  final String titulo;
  final String bajada;
  final List<_Lista> listas;

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: [
        const _FondoMarca(),
        Padding(
          padding: const EdgeInsets.fromLTRB(120, 110, 120, 150),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _Encabezado(sobretitulo: sobretitulo, titulo: titulo, bajada: bajada),
              const SizedBox(height: 56),
              Expanded(
                child: Row(
                  children: [
                    for (var i = 0; i < listas.length; i++) ...[
                      if (i > 0) const SizedBox(width: 36),
                      Expanded(
                        child: _Entrada(
                          orden: i,
                          child: _Poster(lista: listas[i]),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
        const _Pie(),
      ],
    );
  }
}

/// Los logos de los canales en una grilla, con "EN VIVO" en rubí.
class _PantallaEnVivo extends StatelessWidget {
  const _PantallaEnVivo({required this.canales, required this.cantidad});

  final List<_Lista> canales;
  final int cantidad;

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: [
        const _FondoMarca(),
        Padding(
          padding: const EdgeInsets.fromLTRB(120, 110, 120, 150),
          child: Row(
            children: [
              SizedBox(
                width: 560,
                child: _Encabezado(
                  sobretitulo: 'En vivo',
                  titulo: '${cifraRedonda(cantidad)} canales',
                  bajada: 'Noticias, deportes, películas y más, las 24 horas',
                  color: Tono.rubiClaro,
                ),
              ),
              const SizedBox(width: 80),
              Expanded(
                child: GridView.count(
                  crossAxisCount: 4,
                  mainAxisSpacing: 24,
                  crossAxisSpacing: 24,
                  childAspectRatio: 16 / 10,
                  physics: const NeverScrollableScrollPhysics(),
                  children: [
                    for (var i = 0; i < canales.length; i++)
                      _Entrada(
                        orden: i,
                        paso: const Duration(milliseconds: 60),
                        child: Container(
                          padding: const EdgeInsets.all(22),
                          decoration: BoxDecoration(
                            color: Tono.capaAlta,
                            borderRadius: BorderRadius.circular(Curva.panel),
                          ),
                          child: _Foto(imagen: canales[i].imagen, poster: false),
                        ),
                      ),
                  ],
                ),
              ),
            ],
          ),
        ),
        const _Pie(),
      ],
    );
  }
}

/// "Todo en un solo lugar": el logo grande y las cifras del catálogo.
class _PantallaCifras extends StatelessWidget {
  const _PantallaCifras({required this.vidriera});

  final Vidriera vidriera;

  @override
  Widget build(BuildContext context) {
    final cifras = [
      if (vidriera.peliculas > 0) (cifraRedonda(vidriera.peliculas), 'películas', Tono.celeste),
      if (vidriera.cantidadSeries > 0) (cifraRedonda(vidriera.cantidadSeries), 'series', Tono.dorado),
      if (vidriera.cantidadCanales > 0) (cifraRedonda(vidriera.cantidadCanales), 'canales en vivo', Tono.rubiClaro),
    ];
    return Stack(
      fit: StackFit.expand,
      children: [
        const _FondoMarca(centrado: true),
        Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const LogoKairos(tamanio: 80),
              const SizedBox(height: 28),
              Text('Todo en un solo lugar', style: LetraTv.portada.copyWith(fontSize: 56)),
              const SizedBox(height: 64),
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  for (var i = 0; i < cifras.length; i++) ...[
                    if (i > 0) Container(width: 1, height: 110, color: Tono.bordeSuave.withValues(alpha: .7)),
                    _Entrada(
                      orden: i,
                      paso: const Duration(milliseconds: 250),
                      child: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 72),
                        child: Column(
                          children: [
                            Text(
                              cifras[i].$1,
                              style: TextStyle(
                                fontFamily: Letra.titulos,
                                fontSize: 96,
                                fontWeight: FontWeight.w800,
                                letterSpacing: -1.5,
                                color: cifras[i].$3,
                              ),
                            ),
                            Text(
                              cifras[i].$2.toUpperCase(),
                              style: LetraTv.cuerpo.copyWith(fontSize: 20, letterSpacing: 4, color: Tono.textoSuave),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            ],
          ),
        ),
        const Positioned(right: 120, bottom: 48, child: _Hora()),
      ],
    );
  }
}

/// Un póster con su título debajo.
class _Poster extends StatelessWidget {
  const _Poster({required this.lista});

  final _Lista lista;

  @override
  Widget build(BuildContext context) {
    final diapositiva = lista.diapositiva;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Container(
            width: double.infinity,
            decoration: BoxDecoration(
              color: Tono.capaAlta,
              borderRadius: BorderRadius.circular(Curva.tarjeta),
              boxShadow: const [BoxShadow(color: Colors.black54, blurRadius: 40, offset: Offset(0, 16))],
            ),
            clipBehavior: Clip.antiAlias,
            child: _Foto(imagen: lista.imagen, poster: true),
          ),
        ),
        const SizedBox(height: 14),
        Text(
          diapositiva.titulo,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: LetraTv.cuerpo.copyWith(fontSize: 22, color: Tono.texto, fontWeight: FontWeight.w600),
        ),
        if (diapositiva.detalle.isNotEmpty) Text(diapositiva.detalle, style: LetraTv.ayuda.copyWith(fontSize: 18)),
      ],
    );
  }
}

/// Aparece subiendo y aclarándose, un poco después que el anterior ([orden] × [paso]).
class _Entrada extends StatefulWidget {
  const _Entrada({required this.orden, required this.child, this.paso = const Duration(milliseconds: 140)});

  final int orden;
  final Duration paso;
  final Widget child;

  @override
  State<_Entrada> createState() => _EntradaState();
}

class _EntradaState extends State<_Entrada> with SingleTickerProviderStateMixin {
  late final AnimationController _animacion = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 700),
  );
  Timer? _espera;

  @override
  void initState() {
    super.initState();
    _espera = Timer(_fundido ~/ 2 + widget.paso * widget.orden, () {
      if (mounted) _animacion.forward();
    });
  }

  @override
  void dispose() {
    _espera?.cancel();
    _animacion.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final curva = CurvedAnimation(parent: _animacion, curve: Curves.easeOutCubic);
    return FadeTransition(
      opacity: curva,
      child: SlideTransition(
        position: Tween(begin: const Offset(0, .12), end: Offset.zero).animate(curva),
        child: widget.child,
      ),
    );
  }
}

/// La hora (se actualiza sola).
class _Hora extends StatefulWidget {
  const _Hora({this.grande = false});

  final bool grande;

  @override
  State<_Hora> createState() => _HoraState();
}

class _HoraState extends State<_Hora> {
  late DateTime _ahora = DateTime.now();
  Timer? _reloj;

  @override
  void initState() {
    super.initState();
    _reloj = Timer.periodic(const Duration(seconds: 15), (_) => setState(() => _ahora = DateTime.now()));
  }

  @override
  void dispose() {
    _reloj?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final hora = '${_ahora.hour.toString().padLeft(2, '0')}:${_ahora.minute.toString().padLeft(2, '0')}';
    return Text(
      hora,
      style: TextStyle(
        fontFamily: Letra.titulos,
        fontSize: widget.grande ? 64 : 28,
        fontWeight: FontWeight.w700,
        letterSpacing: -1,
        color: widget.grande ? Tono.texto : Tono.textoSuave,
        fontFeatures: const [FontFeature.tabularFigures()],
      ),
    );
  }
}
