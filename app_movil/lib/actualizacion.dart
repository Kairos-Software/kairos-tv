/// El aviso "Hay una versión nueva".
///
/// Al abrir la app (y al volver a ella, cada tanto) se le pregunta al servidor
/// cuál es la última versión publicada en el panel (GET /api/v1/app/). Si la
/// instalada es más vieja, aparece un cartel con lo que cambió y el botón
/// "Actualizar": la app baja la APK nueva y abre el instalador de Android
/// (MainActivity.kt -> "instalar"). Se instala encima: la sesión sigue (y si el
/// aparato pierde el almacén seguro, queda su copia: ver lib/sesion.dart).
///
/// Es la única forma de actualizar sin reinstalar a mano, así que tiene que
/// andar aunque el resto de la app falle (como el login trabado de la 1.2.0
/// en la TV):
///   - si no hay internet (la TV recién prendida, el Wi-Fi todavía
///     conectando), se reintenta cada minuto hasta poder preguntar;
///   - se vuelve a preguntar cada 6 horas aunque la app nunca se cierre;
///   - antes de mostrar el cartel se cierra el teclado de Android y se suelta
///     el foco, para que el control remoto llegue al botón "Actualizar";
///   - el login tiene su propio "Buscar actualización" ([buscarAhora]).
library;

import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;

import 'aparato.dart';
import 'movil/estilo.dart';
import 'sesion.dart';

/// ¿[nueva] es mayor que [instalada]? Compara número por número: "1.10.0" > "1.9.3".
bool esMasNueva(String nueva, String instalada) {
  List<int> numeros(String version) =>
      RegExp(r'\d+').allMatches(version.split('+').first).map((m) => int.parse(m.group(0)!)).toList();
  final a = numeros(nueva);
  final b = numeros(instalada);
  if (a.isEmpty || b.isEmpty) return false;
  for (var i = 0; i < a.length || i < b.length; i++) {
    final x = i < a.length ? a[i] : 0;
    final y = i < b.length ? b[i] : 0;
    if (x != y) return x > y;
  }
  return false;
}

/// Envuelve la app y muestra el cartel cuando hace falta.
class VigilarActualizacion extends StatefulWidget {
  const VigilarActualizacion({super.key, required this.sesion, required this.navegador, required this.child});

  /// Para saber a qué servidor preguntar (el que se eligió en el login).
  final Sesion sesion;

  /// El de MaterialApp: el cartel se abre encima de cualquier pantalla.
  final GlobalKey<NavigatorState> navegador;
  final Widget child;

  @override
  State<VigilarActualizacion> createState() => _VigilarActualizacionState();

  /// "Buscar actualizaciones" (Mi cuenta): pregunta ya, sin esperar.
  /// true = había una nueva (se mostró el cartel); false = ya tiene la última; null = no se pudo preguntar.
  static Future<bool?> buscarAhora(BuildContext context) async =>
      context.findAncestorStateOfType<_VigilarActualizacionState>()?._consultar(forzar: true);
}

class _VigilarActualizacionState extends State<VigilarActualizacion> with WidgetsBindingObserver {
  /// Una TV queda prendida días: al volver a la app se pregunta de nuevo, pero no más seguido que esto.
  static const _cadaCuanto = Duration(hours: 6);

  /// Si no se pudo preguntar (sin internet), se reintenta tras este tiempo.
  static const _reintento = Duration(minutes: 1);

  DateTime? _ultimaConsulta;
  bool _mostrando = false;
  Timer? _proxima;

  /// La que la persona dejó para "Más tarde": no se le vuelve a ofrecer hasta que abra la app de nuevo.
  String? _postergada;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    // Se pregunta apenas la sesión sabe cuál es el servidor (y no más seguido que _cadaCuanto)
    widget.sesion.addListener(_consultar);
    WidgetsBinding.instance.addPostFrameCallback((_) => _consultar());
  }

  @override
  void dispose() {
    _proxima?.cancel();
    widget.sesion.removeListener(_consultar);
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState estado) {
    if (estado == AppLifecycleState.resumed) _consultar();
  }

  Future<bool?> _consultar({bool forzar = false}) async {
    // Sin versión conocida (tests, o fuera de Android) no se puede comparar
    if (Aparato.version.isEmpty || _mostrando || widget.sesion.estado == EstadoSesion.cargando) return null;
    final ahora = DateTime.now();
    if (!forzar && _ultimaConsulta != null && ahora.difference(_ultimaConsulta!) < _cadaCuanto) return null;
    _ultimaConsulta = ahora;
    _programar(_cadaCuanto);
    try {
      final datos = await widget.sesion.api.get('app/') as Map<String, dynamic>;
      final version = datos['version'] as String?;
      final descarga = datos['descarga'] as String?;
      if (version == null || descarga == null || (!forzar && version == _postergada)) return false;
      if (!esMasNueva(version, Aparato.version)) return false;
      final contexto = widget.navegador.currentContext;
      if (contexto == null || !contexto.mounted) return null;
      // Que nada le robe el control remoto al cartel: ni un campo de texto
      // con el teclado de Android abierto, ni lo que estaba elegido abajo.
      FocusManager.instance.primaryFocus?.unfocus();
      unawaited(SystemChannels.textInput.invokeMethod<void>('TextInput.hide'));
      _mostrando = true;
      final actualizo = await showDialog<bool>(
        context: contexto,
        barrierDismissible: false,
        builder: (_) =>
            _CartelActualizacion(version: version, notas: '${datos['notas'] ?? ''}'.trim(), descarga: descarga),
      );
      _mostrando = false;
      if (actualizo != true) _postergada = version;
      return true;
    } catch (_) {
      // Sin conexión o un servidor viejo (sin /app/): se reintenta en un minuto
      _ultimaConsulta = null;
      _programar(_reintento);
      return null;
    }
  }

  /// La próxima consulta automática (reemplaza a la que hubiera programada).
  void _programar(Duration dentroDe) {
    _proxima?.cancel();
    _proxima = Timer(dentroDe, () {
      if (mounted) _consultar();
    });
  }

  @override
  Widget build(BuildContext context) => widget.child;
}

enum _Paso { preguntar, bajando, listo, error }

/// El cartel solo (para las pruebas: normalmente lo abre [VigilarActualizacion]).
@visibleForTesting
Widget cartelDeActualizacion({required String version, String notas = '', String descarga = ''}) =>
    _CartelActualizacion(version: version, notas: notas, descarga: descarga);

class _CartelActualizacion extends StatefulWidget {
  const _CartelActualizacion({required this.version, required this.notas, required this.descarga});

  final String version;
  final String notas;
  final String descarga;

  @override
  State<_CartelActualizacion> createState() => _CartelActualizacionState();
}

class _CartelActualizacionState extends State<_CartelActualizacion> {
  _Paso _paso = _Paso.preguntar;

  /// De 0 a 1; null mientras no se sabe cuánto pesa.
  double? _avance;
  String _error = '';
  String? _ruta;
  http.Client? _cliente;

  /// El cartel entero y su botón principal (Actualizar / Instalar / Reintentar).
  final _alcance = FocusScopeNode(debugLabel: 'cartel de actualización');
  final _principal = FocusNode(debugLabel: 'botón principal de la actualización');

  @override
  void initState() {
    super.initState();
    FocusManager.instance.addListener(_retenerFoco);
  }

  @override
  void dispose() {
    FocusManager.instance.removeListener(_retenerFoco);
    _alcance.dispose();
    _principal.dispose();
    _cliente?.close();
    super.dispose();
  }

  /// El control remoto no se va del cartel mientras está abierto. En la TV,
  /// si el cartel aparecía mientras el inicio todavía cargaba, al terminar de
  /// cargar el primer canal se quedaba con el foco: las flechas movían los
  /// canales de atrás y no los botones del cartel.
  void _retenerFoco() {
    if (_alcance.hasFocus) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || _alcance.hasFocus) return;
      // Si se abrió algo encima del cartel, el foco es de eso
      if (!(ModalRoute.of(context)?.isCurrent ?? false)) return;
      (_alcance.focusedChild ?? (_principal.context != null ? _principal : _alcance)).requestFocus();
    });
  }

  Future<void> _bajar() async {
    setState(() {
      _paso = _Paso.bajando;
      _avance = null;
    });
    final cliente = _cliente = http.Client();
    try {
      final carpeta = Directory(Aparato.carpetaTemporal);
      // Las APK de actualizaciones anteriores ya no sirven
      if (carpeta.existsSync()) {
        for (final viejo in carpeta.listSync()) {
          viejo.deleteSync(recursive: true);
        }
      } else {
        carpeta.createSync(recursive: true);
      }
      final respuesta = await cliente.send(http.Request('GET', Uri.parse(widget.descarga)));
      if (respuesta.statusCode != 200) throw HttpException('El servidor respondió ${respuesta.statusCode}.');
      final total = respuesta.contentLength ?? 0;
      final archivo = File('${carpeta.path}/KairosTV-${widget.version}.apk');
      final salida = archivo.openWrite();
      var recibido = 0;
      var ultimoPorcentaje = -1;
      try {
        await for (final pedazo in respuesta.stream) {
          salida.add(pedazo);
          recibido += pedazo.length;
          if (total > 0) {
            // Redibujar solo cuando cambia el porcentaje (son miles de pedazos)
            final porcentaje = recibido * 100 ~/ total;
            if (porcentaje != ultimoPorcentaje && mounted) {
              ultimoPorcentaje = porcentaje;
              setState(() => _avance = recibido / total);
            }
          }
        }
      } finally {
        await salida.close();
      }
      if (total > 0 && recibido < total) throw const HttpException('La descarga se cortó.');
      _ruta = archivo.path;
      if (!mounted) return;
      setState(() => _paso = _Paso.listo);
      await _instalar();
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _paso = _Paso.error;
        _error = e is HttpException ? e.message : 'No se pudo bajar la versión nueva. Revisá la conexión.';
      });
    } finally {
      cliente.close();
      _cliente = null;
    }
  }

  Future<void> _instalar() async {
    try {
      await Aparato.instalar(_ruta!);
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _paso = _Paso.error;
        _error = 'No se pudo abrir el instalador de Android.';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final bajando = _paso == _Paso.bajando;
    // En la TV (pantalla ancha, ver tv/escala.dart) todo más grande: se lee desde el sillón
    final medidas = MediaQuery.of(context);
    final tv = medidas.size.width >= 900;
    final cartel = PopScope(
      canPop: !bajando,
      child: FocusScope(
        node: _alcance,
        child: AlertDialog(
          backgroundColor: Tono.capaAlta,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
          icon: const Icon(Icons.system_update_rounded, color: Tono.celeste, size: 40),
          title: Text(
            'Hay una versión nueva',
            textAlign: TextAlign.center,
            style: TextStyle(fontFamily: Letra.titulos, fontWeight: FontWeight.w700, color: Tono.texto),
          ),
          content: ConstrainedBox(
            constraints: BoxConstraints(maxWidth: tv ? 720 : 420),
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    'Kairos TV ${widget.version} (tenés la ${Aparato.version}).',
                    textAlign: TextAlign.center,
                    style: const TextStyle(color: Tono.textoSuave),
                  ),
                  if (widget.notas.isNotEmpty) ...[
                    const SizedBox(height: 16),
                    Text(widget.notas, style: const TextStyle(color: Tono.texto, height: 1.4)),
                  ],
                  const SizedBox(height: 16),
                  ..._estado(),
                ],
              ),
            ),
          ),
          actionsAlignment: MainAxisAlignment.center,
          actions: _botones(),
        ),
      ),
    );
    return tv
        ? MediaQuery(
            data: medidas.copyWith(textScaler: const TextScaler.linear(1.6)),
            child: cartel,
          )
        : cartel;
  }

  List<Widget> _estado() {
    switch (_paso) {
      case _Paso.preguntar:
        return const [
          Text(
            'Se instala encima de la que tenés: no se pierde tu sesión.',
            textAlign: TextAlign.center,
            style: TextStyle(color: Tono.textoApagado, fontSize: 13),
          ),
        ];
      case _Paso.bajando:
        return [
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: _avance,
              minHeight: 6,
              color: Tono.celeste,
              backgroundColor: Tono.capaMaxima,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            _avance == null ? 'Bajando…' : 'Bajando… ${(_avance! * 100).round()}%',
            textAlign: TextAlign.center,
            style: const TextStyle(color: Tono.textoSuave),
          ),
        ];
      case _Paso.listo:
        return const [
          Text(
            'Listo. En la ventana de Android tocá "Instalar". Si te pide permiso para '
            '"instalar apps de este origen", activalo y volvé.',
            textAlign: TextAlign.center,
            style: TextStyle(color: Tono.textoSuave),
          ),
        ];
      case _Paso.error:
        return [
          Text(
            _error,
            textAlign: TextAlign.center,
            style: const TextStyle(color: Tono.rubiClaro),
          ),
        ];
    }
  }

  List<Widget> _botones() {
    final principal = FilledButton.styleFrom(backgroundColor: Tono.celeste, foregroundColor: Tono.sobreCelesteOscuro);
    final despues = TextButton(
      onPressed: () => Navigator.of(context).pop(false),
      style: TextButton.styleFrom(foregroundColor: Tono.textoSuave),
      child: const Text('Más tarde'),
    );
    switch (_paso) {
      case _Paso.preguntar:
        // autofocus: en la TV el control remoto arranca parado en "Actualizar"
        return [
          despues,
          FilledButton(
            autofocus: true,
            focusNode: _principal,
            style: principal,
            onPressed: _bajar,
            child: const Text('Actualizar'),
          ),
        ];
      case _Paso.bajando:
        return const [];
      case _Paso.listo:
        return [
          despues,
          FilledButton(
            autofocus: true,
            focusNode: _principal,
            style: principal,
            onPressed: _instalar,
            child: const Text('Instalar'),
          ),
        ];
      case _Paso.error:
        return [
          despues,
          FilledButton(
            autofocus: true,
            focusNode: _principal,
            style: principal,
            onPressed: _bajar,
            child: const Text('Reintentar'),
          ),
        ];
    }
  }
}
