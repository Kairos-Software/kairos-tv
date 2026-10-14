/// Películas y capítulos de canales OFICIALES de YouTube (fuentes "yt_video",
/// ver canales/youtube.py en el servidor): se ven en el reproductor de YouTube,
/// el mismo que insertan las páginas web, con su logo y su publicidad. No hace
/// falta cuenta, se ve en alta calidad y anda lo infantil (que YouTube no deja
/// sacar para verlo en otro reproductor).
///
///   - [ControlYoutube]: el video en sí (lo comparten el celular y la TV):
///     guarda por dónde va cada 5 s ("Continuar viendo"), arranca desde ahí,
///     suma a "Lo más visto", al terminar un capítulo sigue con el próximo y,
///     si YouTube no lo deja ver, le avisa al servidor.
///   - [VistaYoutube]: el video en pantalla.
///   - [PantallaYoutube]: el celular, con los controles de YouTube (tocar el video).
///   - La TV usa su propia pantalla, igual a la de las demás películas
///     (tv/reproductor.dart -> ReproductorYoutubeTv): el control remoto no
///     llega a los botones de YouTube.
///
/// El video se carga en un WebView con la "IFrame API" de YouTube. La página
/// se presenta como de kairostv.grupokairosarg.com: YouTube pide saber desde
/// qué sitio se inserta el video (si no, da "error 153").
library;

import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:wakelock_plus/wakelock_plus.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:webview_flutter_android/webview_flutter_android.dart';

import '../api/cliente.dart';
import '../api/modelos.dart';
import '../sesion.dart';
import '../tv/escala.dart' show TamanioReal;
import 'calidad_youtube.dart';
import 'datos.dart';
import 'estilo.dart';
import 'medidor.dart';

/// Desde qué sitio se inserta el video (YouTube lo exige).
const sitioDeKairos = 'https://kairostv.grupokairosarg.com';

/// La fuente de YouTube oficial de un canal, si es lo primero que puede ver este aparato.
FuenteCanal? fuenteDeYoutube(Canal canal) {
  final fuentes = canal.fuentesReproducibles;
  return fuentes.isNotEmpty && fuentes.first.tipo == 'yt_video' ? fuentes.first : null;
}

/// El id del video ("https://www.youtube.com/watch?v=abc" -> "abc").
String? idDeVideo(String direccion) {
  final uri = Uri.tryParse(direccion);
  if (uri == null) return null;
  final id = uri.host.endsWith('youtu.be') ? uri.pathSegments.firstOrNull : uri.queryParameters['v'];
  return id != null && RegExp(r'^[\w-]{11}$').hasMatch(id) ? id : null;
}

/// La página con el reproductor.
///   [controles]: los de YouTube (celular) o ninguno (TV: se usa el control remoto).
///   [limite]: el ancho máximo, en píxeles de la pantalla, con que se pide el
///     video (0 = sin límite). YouTube elige la calidad según el tamaño del
///     reproductor: con el límite, el reproductor se arma más chico y se
///     agranda, y YouTube no manda más calidad que esa. Se cambia sin
///     recargar con `cambiarLimite(ancho)` (ver [CalidadYoutube]).
///
/// Cada 5 s avisa cuántos cuadros dibujó y cuántos tarde ("fluidez"): si el
/// aparato no da abasto, la app baja la calidad.
///
/// Subtítulos (la TV, que no tiene los botones de YouTube): `siguienteSubtitulo()`
/// pasa al siguiente (primero los en castellano, después los demás, al final
/// ninguno) y avisa cuál quedó ("subtitulos").
///
/// El idioma del audio no se puede elegir desde afuera de YouTube: en los
/// videos con varios audios, YouTube usa el del idioma del aparato, que la
/// app pone en castellano (MainActivity.preferirEspanol).
@visibleForTesting
String paginaDelReproductor(String id, {required bool controles, Duration desde = Duration.zero, int limite = 0}) {
  final opciones = jsonEncode({
    'autoplay': 1,
    'controls': controles ? 1 : 0,
    'disablekb': controles ? 0 : 1,
    'playsinline': 1,
    'rel': 0,
    'fs': 0,
    'iv_load_policy': 3,
    'cc_load_policy': 0,
    'hl': 'es-419',
    'cc_lang_pref': 'es',
    'start': desde.inSeconds,
    'origin': sitioDeKairos,
  });
  return '''
<!DOCTYPE html>
<html><head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>html,body{margin:0;height:100%;background:#000;overflow:hidden}#marco{position:absolute;left:0;top:0;transform-origin:0 0}#marco iframe,#video{width:100%;height:100%;border:0}</style>
</head><body>
<div id="marco"><div id="video"></div></div>
<script>
var LIMITE = $limite;
function acomodar() {
  var escala = LIMITE ? Math.max(1, innerWidth * devicePixelRatio / LIMITE) : 1;
  var marco = document.getElementById('marco');
  marco.style.width = (innerWidth / escala) + 'px';
  marco.style.height = (innerHeight / escala) + 'px';
  marco.style.transform = 'scale(' + escala + ')';
}
acomodar();
addEventListener('resize', acomodar);
function cambiarLimite(ancho) { LIMITE = ancho; acomodar(); }
var subtitulo = -1, conSubtitulos = false;
function pistasDeSubtitulos() {
  var lista = [];
  try { lista = reproductor.getOption('captions', 'tracklist') || []; } catch (e) {}
  var espanol = function (p) { return (p.languageCode || '').indexOf('es') === 0 ? 0 : 1; };
  return lista.slice().sort(function (a, b) { return espanol(a) - espanol(b); });
}
function siguienteSubtitulo() {
  var elegir = function () {
    var lista = pistasDeSubtitulos();
    if (!lista.length) { avisar({e: 'subtitulos', n: '', hay: false}); return; }
    subtitulo++;
    if (subtitulo >= lista.length) {
      subtitulo = -1; conSubtitulos = false;
      reproductor.unloadModule('captions');
      avisar({e: 'subtitulos', n: '', hay: true});
      return;
    }
    var pista = lista[subtitulo];
    reproductor.setOption('captions', 'track', {languageCode: pista.languageCode});
    avisar({e: 'subtitulos', n: pista.displayName || pista.languageName || pista.languageCode, hay: true});
  };
  if (conSubtitulos) { elegir(); return; }
  conSubtitulos = true;
  reproductor.loadModule('captions');
  setTimeout(elegir, 900);   // la lista llega cuando YouTube cargó los subtítulos
}
function avisar(datos) { Kairos.postMessage(JSON.stringify(datos)); }
var cuadros = 0, lentos = 0, anterior = 0;
function contarCuadro(ahora) {
  if (anterior) { cuadros++; if (ahora - anterior > ${CalidadYoutube.cuadroLentoMs}) lentos++; }
  anterior = ahora;
  requestAnimationFrame(contarCuadro);
}
requestAnimationFrame(contarCuadro);
setInterval(function () {
  avisar({e: 'fluidez', c: cuadros, l: lentos});
  cuadros = 0; lentos = 0;
}, ${CalidadYoutube.tanda.inMilliseconds});
var reproductor;
function onYouTubeIframeAPIReady() {
  reproductor = new YT.Player('video', {
    width: '100%', height: '100%',
    videoId: '$id', playerVars: $opciones,
    events: {
      onReady: function () { avisar({e: 'listo'}); reproductor.playVideo(); },
      onStateChange: function (ev) { avisar({e: 'estado', v: ev.data}); },
      onError: function (ev) { avisar({e: 'error', v: ev.data}); }
    }
  });
  setInterval(function () {
    if (reproductor && reproductor.getCurrentTime) {
      avisar({e: 'tiempo', t: reproductor.getCurrentTime() || 0, d: reproductor.getDuration() || 0});
    }
  }, 1000);
}
</script>
<script src="https://www.youtube.com/iframe_api"></script>
</body></html>''';
}

/// Lo que dice el reproductor de YouTube, en limpio (separado del WebView para poder probarlo).
///
/// Avisa (notifyListeners) solo cuando cambia algo que se ve: listo, el
/// estado o un error. Por dónde va cambia cada segundo y avisa aparte, en
/// [avance]: así la pantalla no se redibuja cada segundo encima del video
/// (en una TV eso solo ya lo hace menos fluido).
class EstadoYoutube extends ChangeNotifier {
  // Los estados del reproductor de YouTube
  static const _termino = 0, _reproduciendo = 1, _cargando = 3;

  bool listo = false;
  int estado = -1;
  Duration duracion = Duration.zero;

  /// Por dónde va (avisa cada vez que cambia).
  final ValueNotifier<Duration> avance = ValueNotifier(Duration.zero);

  Duration get posicion => avance.value;
  set posicion(Duration valor) => avance.value = valor;

  /// El error de YouTube (null = ninguno; -1 = no cargó, casi siempre la conexión).
  int? error;

  bool get reproduciendo => estado == _reproduciendo;
  bool get cargando => !listo || estado == _cargando || estado == -1;

  /// Se frenó a cargar (ya había arrancado).
  bool get frenado => listo && estado == _cargando;

  /// Lo que midió la página cada 5 s: cuántos cuadros dibujó y cuántos tarde.
  void Function(int cuadros, int lentos)? alMedirFluidez;

  /// Los subtítulos que se están mostrando ('' = ninguno).
  String subtitulos = '';

  /// Si el video tiene subtítulos (null = todavía no se preguntó).
  bool? haySubtitulos;
  bool get termino => estado == _termino;

  void recibir(String mensaje) {
    final Map<String, dynamic> datos;
    try {
      datos = jsonDecode(mensaje) as Map<String, dynamic>;
    } catch (_) {
      return;
    }
    switch (datos['e']) {
      case 'listo':
        listo = true;
      case 'estado':
        estado = (datos['v'] as num?)?.toInt() ?? estado;
      case 'error':
        error = (datos['v'] as num?)?.toInt() ?? 5;
      case 'subtitulos':
        subtitulos = (datos['n'] as String?) ?? '';
        haySubtitulos = datos['hay'] as bool?;
      case 'fluidez':
        alMedirFluidez?.call((datos['c'] as num?)?.toInt() ?? 0, (datos['l'] as num?)?.toInt() ?? 0);
        return;
      case 'tiempo':
        duracion = Duration(milliseconds: (((datos['d'] as num?) ?? 0) * 1000).round());
        posicion = Duration(milliseconds: (((datos['t'] as num?) ?? 0) * 1000).round());
        return;
      default:
        return;
    }
    notifyListeners();
  }

  /// Vuelve a como estaba antes de cargar un video.
  void reiniciar({int? error}) {
    listo = false;
    estado = -1;
    subtitulos = '';
    haySubtitulos = null;
    this.error = error;
    duracion = Duration.zero;
    posicion = Duration.zero;
    notifyListeners();
  }

  @override
  void dispose() {
    avance.dispose();
    super.dispose();
  }

  /// El error de YouTube, en castellano.
  static String mensajeDe(int codigo) => switch (codigo) {
    -1 => 'No se pudo cargar YouTube. Revisá la conexión a internet.',
    100 => 'Este video ya no está en YouTube (lo borraron o es privado).',
    101 || 150 => 'El dueño de este video no deja verlo fuera de YouTube.',
    152 || 153 => 'YouTube no aceptó el reproductor (error $codigo).',
    5 => 'Este aparato no pudo reproducir el video.',
    _ => 'YouTube no pudo reproducir el video (error $codigo).',
  };

  /// Cómo se le avisa al servidor (ver MOTIVOS_DE_LOS_APARATOS en canales/servicios.py).
  static String motivoDe(int codigo) => switch (codigo) {
    100 || 101 || 150 => 'rechazo',
    5 => 'formato',
    _ => 'error',
  };
}

/// Un video de YouTube oficial en reproducción (lo comparten el celular y la TV).
/// Avisa cuando cambia el estado ([estado]) o el video; por dónde va, en `estado.avance`.
class ControlYoutube extends ChangeNotifier {
  ControlYoutube({
    required this.api,
    required this.biblioteca,
    required this.canal,
    required this.tv,
    this.serie,
    this.episodio,
  }) {
    estado.addListener(_alCambiarEstado);
    estado.avance.addListener(_medir);
    if (tv) {
      final pantalla = WidgetsBinding.instance.platformDispatcher.views.first.physicalSize;
      calidad = CalidadYoutube(anchoDePantalla: pantalla.width, alCambiar: _cambiarLimite);
      estado.alMedirFluidez = (cuadros, lentos) {
        if (estado.reproduciendo) calidad?.medir(cuadros: cuadros, lentos: lentos);
      };
    }
    _guardar = Timer.periodic(const Duration(seconds: 5), (_) => guardarProgreso());
  }

  /// Si en este tiempo no cargó, casi siempre es la conexión.
  static const _sinRespuesta = Duration(seconds: 25);

  final ApiCliente api;
  final Biblioteca biblioteca;
  final bool tv;
  final Serie? serie;
  Canal canal;
  Episodio? episodio;

  final estado = EstadoYoutube();
  WebViewController? web;

  /// En la TV, la calidad que aguanta este aparato (se aprende sola). En el
  /// celular no hace falta: YouTube elige por el tamaño de la pantalla.
  CalidadYoutube? calidad;

  Timer? _guardar;
  Timer? _vigia;
  AppLifecycleListener? _ciclo;
  bool _seguirAlVolver = false;
  bool _avisado = false;
  bool _siguienteLanzado = false;
  bool _cerrado = false;
  Duration _vistoDeEstaVez = Duration.zero;
  bool _vistaContada = false;
  Duration? _ultimaPosicion;
  bool _seEstabaViendo = false;

  /// Carga el video de [canal] (desde [desde], si se dice).
  void abrir({Duration? desde}) {
    final fuente = fuenteDeYoutube(canal);
    final id = fuente == null ? null : idDeVideo(fuente.url);
    _avisado = false;
    _siguienteLanzado = false;
    _vistoDeEstaVez = Duration.zero;
    _vistaContada = false;
    _ultimaPosicion = null;
    _vigia?.cancel();
    if (id == null) {
      web = null;
      estado.reiniciar(error: 2);
      return;
    }
    final nuevo = WebViewController(onPermissionRequest: (pedido) => pedido.deny())
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(Colors.black)
      ..addJavaScriptChannel('Kairos', onMessageReceived: (mensaje) => estado.recibir(mensaje.message))
      ..setNavigationDelegate(
        NavigationDelegate(
          // Que un toque en el logo o en "más videos" no saque al usuario a youtube.com dentro de la app
          onNavigationRequest: (pedido) => pedido.isMainFrame && !pedido.url.startsWith(sitioDeKairos)
              ? NavigationDecision.prevent
              : NavigationDecision.navigate,
        ),
      );
    final android = nuevo.platform;
    if (android is AndroidWebViewController) {
      unawaited(android.setMediaPlaybackRequiresUserGesture(false)); // que arranque solo, con sonido
    }
    unawaited(
      nuevo.loadHtmlString(
        paginaDelReproductor(id, controles: !tv, desde: desde ?? Duration.zero, limite: calidad?.ancho ?? 0),
        baseUrl: '$sitioDeKairos/',
      ),
    );
    _vigia = Timer(_sinRespuesta, () {
      if (!_cerrado && !estado.listo && estado.error == null) estado.reiniciar(error: -1);
    });
    web = nuevo;
    _seEstabaViendo = false;
    calidad?.calmar();
    estado.reiniciar();
    // Si la app se va al fondo, el video se pausa (el WebView seguiría sonando)
    _ciclo ??= AppLifecycleListener(
      onHide: () {
        _seguirAlVolver = estado.reproduciendo;
        if (_seguirAlVolver) _js('reproductor.pauseVideo();');
        guardarProgreso();
      },
      onShow: () {
        if (_seguirAlVolver) _js('reproductor.playVideo();');
        _seguirAlVolver = false;
      },
    );
  }

  /// Después de un error: lo vuelve a cargar desde donde iba.
  void reintentar() => abrir(desde: estado.posicion);

  /// Pasa a otro capítulo (desde donde quedó, si lo había empezado).
  void pasarA(Episodio otro) {
    guardarProgreso();
    episodio = otro;
    canal = otro.canal;
    final progreso = biblioteca.progresoDe(otro.canal.id);
    abrir(desde: progreso == null || progreso.terminado ? null : progreso.posicion);
  }

  /// El capítulo que sigue (null: no es una serie o es el último).
  Episodio? get siguiente {
    final actual = episodio;
    final episodios = serie?.episodios;
    if (episodios == null || actual == null) return null;
    final indice = episodios.indexOf(actual);
    return indice >= 0 && indice + 1 < episodios.length ? episodios[indice + 1] : null;
  }

  /// Pasa a los subtítulos siguientes: en castellano, los demás idiomas, ninguno.
  void cambiarSubtitulos() => _js('siguienteSubtitulo();');

  void alternarPausa() => _js(estado.reproduciendo ? 'reproductor.pauseVideo();' : 'reproductor.playVideo();');

  /// Adelanta (o atrasa, si es negativo) [cuanto].
  void saltar(Duration cuanto) {
    final destino = estado.posicion + cuanto;
    final limite = estado.duracion > Duration.zero ? estado.duracion : destino;
    final segundo = (destino < Duration.zero ? Duration.zero : (destino > limite ? limite : destino)).inSeconds;
    _js('reproductor.seekTo($segundo, true);');
    estado.posicion = Duration(seconds: segundo);
    calidad?.calmar(); // al adelantar se frena a cargar: no es que no dé abasto
  }

  void _cambiarLimite(int ancho) {
    unawaited(web?.runJavaScript('cambiarLimite($ancho);').catchError((Object _) {}));
  }

  void _js(String codigo) {
    final controlador = web;
    if (controlador == null) return;
    unawaited(controlador.runJavaScript('if (reproductor) { $codigo }').catchError((Object _) {}));
  }

  void _alCambiarEstado() {
    if (_cerrado) return;
    if (estado.frenado && _seEstabaViendo) calidad?.anotarFrenada();
    _seEstabaViendo = estado.reproduciendo;
    final error = estado.error;
    if (error != null && !_avisado && error > 0) {
      _avisado = true;
      final fuente = fuenteDeYoutube(canal);
      if (fuente != null && error != 152 && error != 153) {
        api
            .post('canales/fuentes/${fuente.id}/falla/', {
              'motivo': EstadoYoutube.motivoDe(error),
              'detalle': 'YouTube oficial: error $error',
            })
            .catchError((Object _) => null);
        if (error == 100 || error == 101 || error == 150) NoAnda.anotar(canal, deFormato: false);
      }
    }
    if (estado.termino && !_siguienteLanzado) {
      _siguienteLanzado = true;
      guardarProgreso();
      final otro = siguiente;
      if (otro != null && fuenteDeYoutube(otro.canal) != null) {
        pasarA(otro);
        return; // abrir() ya avisó
      }
    }
    notifyListeners();
  }

  /// Lo más visto: lo que avanzó desde el aviso anterior, si se está viendo.
  void _medir() {
    final anterior = _ultimaPosicion;
    _ultimaPosicion = estado.posicion;
    if (!estado.reproduciendo || anterior == null) return;
    final rato = estado.posicion - anterior;
    if (rato <= Duration.zero || rato > const Duration(seconds: 3)) return; // saltó o recién arranca
    Medidor.sumar(api, canal.id, rato);
    _vistoDeEstaVez += rato;
    if (!_vistaContada && _vistoDeEstaVez >= Medidor.paraUnaVista) {
      _vistaContada = true;
      Medidor.contarVista(canal.id);
    }
  }

  void guardarProgreso() {
    if (estado.duracion == Duration.zero) return;
    biblioteca.guardarProgreso(canal.id, estado.termino ? estado.duracion : estado.posicion, estado.duracion);
  }

  @override
  void dispose() {
    guardarProgreso();
    _cerrado = true;
    _guardar?.cancel();
    _vigia?.cancel();
    _ciclo?.dispose();
    estado
      ..removeListener(_alCambiarEstado)
      ..dispose();
    unawaited(Medidor.enviar(api));
    super.dispose();
  }
}

/// El video, en 16:9 y centrado.
///
/// En Android, en "hybrid composition": se dibuja directo en la pantalla. La
/// forma de siempre copia cada imagen del video a una textura antes de
/// mostrarla, y en aparatos con poco procesador el video se traba.
///
/// En la TV no recibe el foco ni toques (las teclas las maneja la pantalla) y
/// se arma del tamaño REAL de la pantalla: la app de TV se dibuja en
/// 1920×1080 y se achica a la pantalla (tv/escala.dart), y sin esto el video
/// quedaba armado al doble (en una TV Full HD, como si fuera 4K): YouTube
/// mandaba esa calidad y la TV la tenía que achicar en cada cuadro.
class VistaYoutube extends StatelessWidget {
  const VistaYoutube({super.key, required this.control});

  final ControlYoutube control;

  @override
  Widget build(BuildContext context) {
    final web = control.web;
    if (web == null) return const SizedBox.expand();
    final android = web.platform;
    Widget video = KeyedSubtree(
      key: ObjectKey(web),
      child: android is AndroidWebViewController
          ? WebViewWidget.fromPlatformCreationParams(
              params: AndroidWebViewWidgetCreationParams(controller: android, displayWithHybridComposition: true),
            )
          : WebViewWidget(controller: web),
    );
    if (control.tv) {
      video = ExcludeFocus(
        child: IgnorePointer(child: TamanioReal(child: video)),
      );
    }
    return Center(
      child: AspectRatio(aspectRatio: 16 / 9, child: video),
    );
  }
}

/// El celular: el video a pantalla completa (acostado) con los controles de YouTube.
class PantallaYoutube extends StatefulWidget {
  const PantallaYoutube({super.key, required this.canal, this.serie, this.episodio, this.desde});

  final Canal canal;
  final Serie? serie;
  final Episodio? episodio;
  final Duration? desde;

  @override
  State<PantallaYoutube> createState() => _PantallaYoutubeState();
}

class _PantallaYoutubeState extends State<PantallaYoutube> {
  ControlYoutube? _control;

  @override
  void initState() {
    super.initState();
    WakelockPlus.enable();
    SystemChrome.setPreferredOrientations([DeviceOrientation.landscapeLeft, DeviceOrientation.landscapeRight]);
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _control ??= ControlYoutube(
      api: SesionScope.leer(context).api,
      biblioteca: DatosScope.of(context).biblioteca,
      canal: widget.canal,
      serie: widget.serie,
      episodio: widget.episodio,
      tv: false,
    )..abrir(desde: widget.desde);
  }

  @override
  void dispose() {
    _control?.dispose();
    WakelockPlus.disable();
    SystemChrome.setPreferredOrientations([]);
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final control = _control!;
    return Scaffold(
      backgroundColor: Colors.black,
      body: ListenableBuilder(
        listenable: control,
        builder: (context, _) {
          final error = control.estado.error;
          return Stack(
            fit: StackFit.expand,
            children: [
              VistaYoutube(control: control),
              if (error == null && !control.estado.listo)
                const Center(child: CircularProgressIndicator(color: Tono.celeste)),
              if (error != null) _Falla(mensaje: EstadoYoutube.mensajeDe(error)),
            ],
          );
        },
      ),
    );
  }
}

/// No se pudo ver: el motivo y cómo salir.
class _Falla extends StatelessWidget {
  const _Falla({required this.mensaje});

  final String mensaje;

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: Colors.black,
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline_rounded, color: Tono.rubiClaro, size: 48),
              const SizedBox(height: 16),
              Text(
                mensaje,
                textAlign: TextAlign.center,
                style: const TextStyle(color: Tono.texto, fontSize: 18, fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 8),
              const Text('Tocá Atrás para volver', style: TextStyle(color: Tono.textoApagado, fontSize: 14)),
            ],
          ),
        ),
      ),
    );
  }
}
