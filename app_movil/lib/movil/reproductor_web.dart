/// Páginas con reproductor: se ejecutan en el dispositivo, sin resolver la
/// señal en el servidor ni declarar que el video se está reproduciendo.
library;

import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:webview_flutter_android/webview_flutter_android.dart';

import '../api/modelos.dart';
import '../aparato.dart';

/// A source is a player, not a browser: even links on the same site are blocked.
bool esDestinoDelReproductorWeb(Uri source, Uri destination) =>
    ['http', 'https'].contains(destination.scheme) && source.replace(fragment: '') == destination.replace(fragment: '');

class ReproductorWeb extends StatefulWidget {
  const ReproductorWeb({super.key, required this.fuente, this.silenciado = false, this.solicitudFoco = 0});

  final FuenteCanal fuente;
  final bool silenciado;
  final int solicitudFoco;

  @override
  State<ReproductorWeb> createState() => _ReproductorWebState();
}

class _ReproductorWebState extends State<ReproductorWeb> {
  WebViewController? _web;
  AppLifecycleListener? _ciclo;
  Timer? _limite;
  bool _cargando = true;
  bool _suspendido = false;
  String? _error;
  bool _listo = false;
  bool _reproduciendo = false;
  bool _vio403 = false;
  int _generacion = 0;
  String _token = '';
  late final Future<String> _script = rootBundle.loadString('assets/reproductor_web.js');

  Uri get _direccion => Uri.parse(widget.fuente.url);

  @override
  void initState() {
    super.initState();
    _iniciar();
    _ciclo = AppLifecycleListener(
      onHide: () {
        _suspendido = true;
        // Pausar solo el documento principal no detiene videos en iframes.
        _limite?.cancel();
        unawaited(_web?.loadRequest(Uri.parse('about:blank')).catchError((Object _) {}));
      },
      onShow: () {
        if (_suspendido) {
          _suspendido = false;
          _cargar();
        }
      },
    );
  }

  Future<void> _iniciar() async {
    try {
      if (!['http', 'https'].contains(_direccion.scheme) || _direccion.host.isEmpty) {
        throw const FormatException('Dirección de reproductor inválida');
      }
      final web = WebViewController(onPermissionRequest: (pedido) => pedido.deny());
      _web = web;
      await web.setJavaScriptMode(JavaScriptMode.unrestricted);
      await web.setBackgroundColor(Colors.black);
      await web.addJavaScriptChannel('KairosWebPlayer', onMessageReceived: (message) => _mensaje(message.message));
      if (widget.fuente.userAgent.isNotEmpty) await web.setUserAgent(widget.fuente.userAgent);
      await web.setNavigationDelegate(
        NavigationDelegate(
          // No abrir anuncios, otras apps ni enlaces externos en la ventana principal.
          // Los marcos del reproductor pueden cargar su contenido HTTP(S).
          onNavigationRequest: (pedido) {
            final destino = Uri.tryParse(pedido.url);
            if (pedido.url == 'about:blank') return NavigationDecision.navigate;
            if (destino == null || !['http', 'https'].contains(destino.scheme)) {
              return NavigationDecision.prevent;
            }
            if (pedido.isMainFrame && !esDestinoDelReproductorWeb(_direccion, destino)) {
              return NavigationDecision.prevent;
            }
            if (!pedido.isMainFrame && _reproduciendo) return NavigationDecision.prevent;
            return NavigationDecision.navigate;
          },
          onPageFinished: (url) {
            if (!mounted || _suspendido || url == 'about:blank') return;
            // Loading HTML is not evidence that a video exists or plays.
            _comando(play: true);
          },
          onHttpError: (error) {
            if (error.response?.statusCode == 403) _vio403 = true;
            if (error.request?.uri == _direccion) {
              _fallo('El proveedor rechazó la página (HTTP ${error.response?.statusCode}).');
            }
          },
          onWebResourceError: (error) {
            if (error.isForMainFrame == true && !_suspendido) {
              _fallo('No se pudo abrir el reproductor web.');
            }
          },
        ),
      );
      final android = web.platform;
      if (android is AndroidWebViewController) {
        await android.setMediaPlaybackRequiresUserGesture(false);
        await Aparato.prepararReproductorWeb(android.webViewIdentifier);
      }
      if (mounted) await _cargar();
    } catch (_) {
      _fallo('Este dispositivo no pudo iniciar el reproductor web.');
    }
  }

  Future<void> _cargar() async {
    if (!mounted || _web == null) return;
    setState(() {
      _cargando = true;
      _error = null;
      _listo = false;
      _reproduciendo = false;
      _vio403 = false;
    });
    _limite?.cancel();
    _limite = Timer(
      const Duration(seconds: 35),
      () => _fallo(
        _vio403
            ? 'El video no comenzó. El proveedor devolvió HTTP 403 en una solicitud.'
            : 'La página no inició un video compatible. Probá otra fuente.',
      ),
    );
    try {
      _token = '${widget.fuente.id}-${++_generacion}-${DateTime.now().microsecondsSinceEpoch}';
      final script = (await _script)
          .replaceAll('__KAIROS_TOKEN__', jsonEncode(_token))
          .replaceAll('__KAIROS_MUTED__', jsonEncode(widget.silenciado));
      final android = _web!.platform;
      if (android is! AndroidWebViewController ||
          !await Aparato.prepararReproductorWeb(android.webViewIdentifier, script: script)) {
        _fallo('Actualizá Android System WebView para usar el reproductor integrado.');
        return;
      }
      if (!mounted || _suspendido) return;
      await _web!.loadRequest(_direccion, headers: widget.fuente.cabeceras);
    } catch (_) {
      _fallo('No se pudo abrir el reproductor web.');
    }
  }

  void _mensaje(String texto) {
    if (!mounted || _suspendido || _error != null || texto.length > 250) return;
    try {
      final message = jsonDecode(texto);
      if (message is! Map || message['token'] != _token) return;
      switch (message['event']) {
        case 'forbidden':
          _vio403 = true;
          return;
        case 'video_error':
          if (_listo) _fallo('El reproductor informó un error de video. Probá otra fuente.');
          return;
        case 'ready':
        case 'playing':
          final primero = !_listo;
          setState(() {
            _listo = true;
            _cargando = false;
            if (message['event'] == 'playing') _reproduciendo = true;
          });
          if (_reproduciendo) _limite?.cancel();
          if (primero) {
            WidgetsBinding.instance.addPostFrameCallback((_) {
              if (mounted) _enfocar();
            });
          }
          return;
      }
    } catch (_) {
      // Untrusted frames may only send the small playback-state messages above.
    }
  }

  void _fallo(String mensaje) {
    if (!mounted) return;
    _limite?.cancel();
    setState(() {
      _error = mensaje;
      _cargando = false;
      _listo = false;
    });
  }

  void _enfocar() {
    final android = _web?.platform;
    if (Aparato.esTv && android is AndroidWebViewController) {
      unawaited(Aparato.prepararReproductorWeb(android.webViewIdentifier, enfocar: true));
    }
  }

  void _comando({bool play = false}) {
    final command = jsonEncode({'kairosWebPlayer': _token, 'muted': widget.silenciado, 'play': play});
    unawaited(_web?.runJavaScript('window.postMessage($command, "*");').catchError((Object _) {}));
  }

  void _sonido() => _comando();

  @override
  void didUpdateWidget(covariant ReproductorWeb oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.solicitudFoco != widget.solicitudFoco) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _enfocar();
      });
    }
    if (oldWidget.fuente.url != widget.fuente.url) {
      _cargar();
    } else if (oldWidget.silenciado != widget.silenciado) {
      _sonido();
    }
  }

  @override
  void dispose() {
    _limite?.cancel();
    _ciclo?.dispose();
    unawaited(_web?.loadRequest(Uri.parse('about:blank')).catchError((Object _) {}));
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => ColoredBox(
    color: Colors.black,
    child: Stack(
      fit: StackFit.expand,
      children: [
        if (_web != null) WebViewWidget(controller: _web!),
        // Do not expose the website while it is loading or without a real player.
        if (!_listo && _error == null)
          const ColoredBox(
            color: Colors.black,
            child: Center(child: CircularProgressIndicator()),
          ),
        if (_error != null)
          ColoredBox(
            color: Colors.black,
            child: Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(_error!, style: const TextStyle(color: Colors.white)),
                  TextButton(onPressed: _cargar, child: const Text('Reintentar')),
                ],
              ),
            ),
          ),
      ],
    ),
  );
}
