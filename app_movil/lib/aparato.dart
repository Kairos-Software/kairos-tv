/// Datos del aparato donde corre la app (los da MainActivity.kt por el
/// canal "kairos/dispositivo"). Se leen una sola vez, al abrir la app.
library;

import 'package:flutter/services.dart';

class Aparato {
  Aparato._();

  static const _canal = MethodChannel('kairos/dispositivo');

  /// Fabricante y modelo (ej: "Philips 55PUD7406"). Se le informa al servidor
  /// al entrar, y aparece en el panel en "Dispositivos conectados".
  static String nombre = 'App Android';

  /// ¿Es un televisor (Android TV / Google TV)? Se maneja con el control remoto.
  static bool esTv = false;

  /// La versión instalada (la de pubspec.yaml, ej: "1.1.0"). Vacía = no se sabe.
  static String version = '';

  /// Dónde se deja la APK nueva que se baja para actualizar (lib/actualizacion.dart).
  static String carpetaTemporal = '';

  /// Los códecs de video que este aparato sabe mostrar (h264, h265, mpeg2...,
  /// los mismos nombres que usa el servidor). Vacío = no se sabe (se prueba todo).
  static Set<String> codecs = {};

  /// Abre el instalador de Android con la APK de [ruta] (la persona confirma).
  static Future<void> instalar(String ruta) => _canal.invokeMethod('instalar', {'ruta': ruta});

  /// Abre un enlace en otra app (WhatsApp, el navegador). false = no hay ninguna que lo abra.
  static Future<bool> abrir(String url) async {
    try {
      return await _canal.invokeMethod<bool>('abrir', {'url': url}) ?? false;
    } on MissingPluginException {
      return false;
    }
  }

  /// Mete [script] en los marcos de youtube.com del WebView [webview] (se
  /// llama antes de cargar la página). false = este aparato no lo permite.
  static Future<bool> dentroDeYoutube(int webview, String script) async {
    try {
      return await _canal.invokeMethod<bool>('dentroDeYoutube', {'webview': webview, 'script': script}) ?? false;
    } on MissingPluginException {
      return false;
    } on PlatformException {
      return false;
    }
  }

  static Future<void> cargar() async {
    try {
      final datos = await _canal.invokeMapMethod<String, Object?>('datos');
      nombre = '${datos?['nombre'] ?? nombre}';
      esTv = datos?['esTv'] == true;
      version = '${datos?['version'] ?? ''}';
      carpetaTemporal = '${datos?['carpetaTemporal'] ?? ''}';
      codecs = {for (final c in datos?['codecs'] as List? ?? const []) '$c'};
    } on MissingPluginException {
      // En los tests (o fuera de Android) no hay canal: quedan los valores por defecto
    } on PlatformException {
      // Idem
    }
  }
}
