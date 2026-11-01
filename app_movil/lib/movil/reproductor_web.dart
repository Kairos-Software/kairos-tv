/// Páginas con reproductor: se ejecutan en el dispositivo, sin resolver la
/// señal en el servidor ni declarar que el video se está reproduciendo.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:webview_flutter_android/webview_flutter_android.dart';

import '../api/modelos.dart';
import '../aparato.dart';

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
            if (pedido.isMainFrame && destino.host != _direccion.host) {
              return NavigationDecision.prevent;
            }
            return NavigationDecision.navigate;
          },
          onPageFinished: (url) {
            if (!mounted || _suspendido || url == 'about:blank') return;
            _limite?.cancel();
            setState(() => _cargando = false);
            _sonido();
            if (_error == null) _enfocar();
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
    });
    _limite?.cancel();
    _limite = Timer(const Duration(seconds: 30), () => _fallo('La página tardó demasiado en abrir.'));
    try {
      await _web!.loadRequest(_direccion, headers: widget.fuente.cabeceras);
    } catch (_) {
      _fallo('No se pudo abrir el reproductor web.');
    }
  }

  void _fallo(String mensaje) {
    if (!mounted) return;
    _limite?.cancel();
    setState(() {
      _error = mensaje;
      _cargando = false;
    });
  }

  void _enfocar() {
    final android = _web?.platform;
    if (Aparato.esTv && android is AndroidWebViewController) {
      unawaited(Aparato.prepararReproductorWeb(android.webViewIdentifier, enfocar: true));
    }
  }

  void _sonido() {
    // Solo los videos accesibles del documento: no se invade ningún iframe externo.
    unawaited(
      _web
          ?.runJavaScript('document.querySelectorAll("video,audio").forEach(v => { v.muted = ${widget.silenciado}; });')
          .catchError((Object _) {}),
    );
  }

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
        if (_cargando) const Center(child: CircularProgressIndicator()),
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
