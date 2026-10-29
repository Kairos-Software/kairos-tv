/// Lo que vio el reproductor de Android por dentro mientras una señal
/// arrancaba (paquetes/video_player_android: KairosVigia): qué llegó, qué
/// decodificador del aparato se usó y si devolvió imagen. Lo pide
/// [ControlSenal] cuando una señal no arranca a tiempo, para saber si fue el
/// servidor de la señal o el aparato (y contarlo bien en el panel).
library;

import 'package:flutter/services.dart';

class Diagnostico {
  const Diagnostico({required this.texto, required this.causa, this.cambiando = false});

  static const _canal = MethodChannel('kairos/reproductor');

  /// Corto, para el panel. Ej: "video h264 1920x1080 25 fps · deco
  /// OMX.MTK.VIDEO.DECODER.AVC: entraron 12, salieron 0 · guardado 9 s".
  final String texto;

  /// aparato: el video llega y este aparato no lo muestra. sin_datos: no
  /// llegó nada del servidor de la señal. sin_video: la señal no trae video.
  /// cambiando: ver [cambiando]. desconocida: no se sabe.
  final String causa;

  /// El decodificador del aparato se trabó y el reproductor está probando con
  /// otro (el de Android): vale la pena esperar un poco más.
  final bool cambiando;

  bool get delAparato => causa == 'aparato';
  bool get sinDatos => causa == 'sin_datos';
  bool get sinVideo => causa == 'sin_video';

  /// La imagen se ve verde o rara (lo dijo la persona): que el reproductor siga con otro
  /// decodificador del aparato. false si no hay otro (o fuera de Android: en las pruebas).
  static Future<bool> otroDecodificador(String url) async {
    try {
      return await _canal.invokeMethod<bool>('otroDecodificador', {'url': url}) ?? false;
    } on MissingPluginException {
      return false;
    } on PlatformException {
      return false;
    }
  }

  /// El del último video abierto con la dirección [url] (null si el
  /// reproductor no sabe nada, o fuera de Android: en las pruebas).
  static Future<Diagnostico?> de(String url) async {
    try {
      final datos = await _canal.invokeMapMethod<String, Object?>('diagnostico', {'url': url});
      if (datos == null) return null;
      return Diagnostico(
        texto: '${datos['texto'] ?? ''}',
        causa: '${datos['causa'] ?? 'desconocida'}',
        cambiando: datos['cambiando'] == true,
      );
    } on MissingPluginException {
      return null;
    } on PlatformException {
      return null;
    }
  }
}
