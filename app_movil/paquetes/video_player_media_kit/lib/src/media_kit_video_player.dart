/// This file is a part of media_kit (https://github.com/media-kit/media-kit).
///
/// Copyright © 2023 & onwards, Hitesh Kumar Saini <saini123hitesh@gmail.com>.
/// All rights reserved.
/// Use of this source code is governed by MIT license that can be found in the LICENSE file.
import 'dart:async';
import 'dart:collection';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:media_kit/media_kit.dart';
import 'package:media_kit_video/media_kit_video.dart';
import 'package:video_player_platform_interface/video_player_platform_interface.dart';

// https://github.com/dart-lang/linter/issues/1381
// ignore_for_file: close_sinks

/// KAIROS TV: la duración de un video sin duración (en vivo), la misma que pasa Android (KAIROS_SIN_FIN_MS en
/// paquetes/video_player_android): unos 100 años.
const kairosSinFin = Duration(days: 36500);

/// KAIROS TV: lo que se espera la duración después de saber el tamaño de la imagen; sin ella, es en vivo.
const kairosEsperaDuracion = Duration(milliseconds: 800);

/// KAIROS TV: ¿es en vivo? En vivo mpv no dice "sin duración": pasa como duración lo que lleva cargado (y crece),
/// y con eso video_player daba el canal por terminado apenas arrancaba. Medido el 10/11/2026 (Canal 26 HLS, un TS
/// en vivo, una radio MP3, películas local y por HTTP sin "Range"): en vivo no se puede adelantar y además es HLS,
/// o no tiene tamaño de archivo, o su duración es lo poco que lleva cargado (menos de un minuto: así se ve un vivo
/// que manda un tamaño de mentira). Una película que no deja adelantar (servidor sin "Range") tiene tamaño y dura
/// más que eso: sigue siendo película.
Future<bool> kairosEnVivo(Player player) async {
  final nativo = player.platform;
  if (player.state.duration <= Duration.zero) return true;
  if (nativo is! NativePlayer) return false;
  try {
    if (await nativo.getProperty('seekable') == 'yes') return false;
    if (await nativo.getProperty('file-format') == 'hls') return true;
    if ((await nativo.getProperty('file-size')).isEmpty) return true;
    final cargado = double.tryParse(await nativo.getProperty('demuxer-cache-time'));
    final duracion = double.tryParse(await nativo.getProperty('duration'));
    return cargado != null && duracion != null && duracion < 60 && (duracion - cargado).abs() < .5;
  } catch (_) {
    return false;
  }
}

/// KAIROS TV: ¿este aviso de mpv (antes de que el video esté listo) quiere decir que la dirección no abre?
/// Sí: los de abrir el archivo o la conexión ("file", "stream": "Failed to open...", un 404; "tcp:" de FFmpeg) y
/// el lector que se rinde ("lavf": "...treating it as fatal error"). No: los del decodificador ("vd", "ad", el
/// resto de FFmpeg), que en IPTV salen seguido sin que pase nada, ni los de "cplayer" (mezcla cosas que no impiden
/// ver, como no tener por dónde sonar). Medido el 10/11/2026 con un 404, un puerto cerrado y un TS en vivo.
bool kairosNoAbre(String prefijo, String nivel, String texto) {
  if (nivel != 'error' && nivel != 'fatal') return false;
  if (prefijo == 'file' || prefijo == 'stream') return true;
  if (prefijo == 'lavf' && texto.contains('treating it as fatal error')) return true;
  return prefijo == 'ffmpeg' && texto.startsWith('tcp:');
}

/// package:media_kit implementation of [VideoPlayerPlatform].
///
/// References:
/// * https://pub.dev/packages/media_kit
/// * https://github.com/media-kit/media-kit
///
class MediaKitVideoPlayer extends VideoPlayerPlatform {
  // The implementation uses [Player.hashCode] as texture ID.
  final _players = HashMap<int, Player>();
  final _completers = HashMap<int, Completer<void>>();
  final _videoControllers = HashMap<int, VideoController>();
  final _streamControllers = HashMap<int, StreamController<VideoEvent>>();
  final _streamSubscriptions = HashMap<int, List<StreamSubscription>>();

  /// KAIROS TV: los que avisaron que no abren (para no avisar el mismo error dos veces).
  final fallo = HashMap<int, bool>();

  /// Registers this class as the default instance of [VideoPlayerPlatform].
  static void registerWith() {
    VideoPlayerPlatform.instance = MediaKitVideoPlayer();
  }

  /// Initializes the platform interface and disposes all existing players.
  ///
  /// This method is called when the plugin is first initialized and on every full restart.
  @override
  Future<void> init() async {
    for (final textureId in _players.keys) {
      await dispose(textureId);
    }

    _players.clear();
    _videoControllers.clear();
    _streamControllers.clear();
    _streamSubscriptions.clear();
  }

  /// Clears one video.
  @override
  Future<void> dispose(int textureId) async {
    await _players[textureId]?.dispose();

    await _streamControllers[textureId]?.close();
    await Future.wait(
      _streamSubscriptions[textureId]?.map((e) => e.cancel()) ?? [],
    );

    _players.remove(textureId);
    _videoControllers.remove(textureId);
    _streamControllers.remove(textureId);
    _streamSubscriptions.remove(textureId);
    fallo.remove(textureId);
  }

  /// Creates an instance of a video player and returns its textureId.
  @override
  Future<int?> create(DataSource dataSource) async {
    final player = Player();
    final completer = Completer();
    final videoController = VideoController(player);
    // NOTE: [StreamController] without broadcast buffers events.
    final streamController = StreamController<VideoEvent>();
    final streamSubscriptions = <StreamSubscription>[];

    final textureId = player.hashCode;

    _players[textureId] = player;
    _completers[textureId] = completer;
    _videoControllers[textureId] = videoController;
    _streamControllers[textureId] = streamController;
    _streamSubscriptions[textureId] = streamSubscriptions;

    // --------------------------------------------------
    _initialize(textureId);
    // --------------------------------------------------

    final String resource;
    final Map<String, String> httpHeaders = dataSource.httpHeaders;

    switch (dataSource.sourceType) {
      case DataSourceType.asset:
        final String? asset;
        if (dataSource.package == null) {
          asset = dataSource.asset;
        } else {
          asset = 'packages/${dataSource.package}/${dataSource.asset}';
        }
        resource = 'asset:///$asset';
        break;

      case DataSourceType.network:
      case DataSourceType.file:
      case DataSourceType.contentUri:
        if (dataSource.uri == null) {
          throw ArgumentError('uri must not be null');
        }
        resource = dataSource.uri!;
        break;

      default:
        throw UnsupportedError('${dataSource.sourceType} is not supported');
    }

    await player.open(
      Media(
        resource,
        httpHeaders: httpHeaders,
      ),
      play: false,
    );

    return textureId;
  }

  /// Returns a Stream of [VideoEventType]s.
  @override
  Stream<VideoEvent> videoEventsFor(int textureId) {
    if (_streamControllers[textureId] == null) {
      throw StateError(
          'VideoPlayer for textureId $textureId is not found, Check if its disposed.');
    }
    return _streamControllers[textureId]!.stream;
  }

  /// Sets the looping attribute of the video.
  @override
  Future<void> setLooping(int textureId, bool looping) async {
    final playlistMode = looping ? PlaylistMode.single : PlaylistMode.none;
    return _players[textureId]?.setPlaylistMode(playlistMode);
  }

  /// Starts the video playback.
  @override
  Future<void> play(int textureId) async {
    return _players[textureId]?.play();
  }

  /// Stops the video playback.
  @override
  Future<void> pause(int textureId) async {
    return _players[textureId]?.pause();
  }

  /// Sets the volume to a range between 0.0 and 1.0.
  @override
  Future<void> setVolume(int textureId, double volume) async {
    // NOTE: [volume] is in the range of 0.0 to 1.0 while [setVolume] expects 0.0 to 100.
    return _players[textureId]?.setVolume(volume * 100);
  }

  /// Sets the video position to a [Duration] from the start.
  @override
  Future<void> seekTo(int textureId, Duration position) async {
    return _players[textureId]?.seek(position);
  }

  /// Sets the playback speed to a [speed] value indicating the playback rate.
  @override
  Future<void> setPlaybackSpeed(int textureId, double speed) async {
    return _players[textureId]?.setRate(speed);
  }

  /// Gets the video position as [Duration] from the start.
  @override
  Future<Duration> getPosition(int textureId) async {
    return _players[textureId]?.platform?.state.position ?? Duration.zero;
  }

  /// Returns a widget displaying the video with a given textureId.
  @override
  Widget buildView(int textureId) {
    if (_videoControllers[textureId] == null) {
      throw StateError(
          'VideoPlayer for textureId $textureId is not found, Check if its disposed.');
    }
    return Video(
      key: ValueKey(_videoControllers[textureId]!),
      controller: _videoControllers[textureId]!,
      wakelock: false,
      controls: NoVideoControls,
      fill: const Color(0x00000000),
      pauseUponEnteringBackgroundMode: false,
      resumeUponEnteringForegroundMode: false,
    );
  }

  /// Sets the audio mode to mix with other sources.
  @override
  Future<void> setMixWithOthers(bool mixWithOthers) => Future.value();

  /// Sets additional options on web.
  @override
  Future<void> setWebOptions(int textureId, VideoPlayerWebOptions options) =>
      Future.value();

  /// Initialize the [Stream]s for a given textureId.
  void _initialize(int textureId) {
    if (_streamSubscriptions[textureId]?.isNotEmpty ?? false) {
      return;
    }

    final player = _players[textureId];
    final completer = _completers[textureId];
    final streamController = _streamControllers[textureId];
    final streamSubscriptions = _streamSubscriptions[textureId];

    if (player != null &&
        completer != null &&
        streamController != null &&
        streamSubscriptions != null) {
      // VideoEventType.initialized
      //
      // KAIROS TV (ver paquetes/README.md): listo apenas se sabe el tamaño de la imagen (o que es solo audio,
      // una radio), con la duración que haya. De fábrica esperaba tamaño Y duración: un canal en vivo no tiene
      // duración y no quedaba listo nunca, y el tamaño 0×0 de antes del primer cuadro lo daba listo con 0×0
      // (sonido sin imagen). Sin duración (en vivo) se pasa la misma de Android, unos 100 años: con 0,
      // video_player deja la posición en 0, lo da por terminado y vuelve al principio antes de reproducir.

      var width = 0;
      var height = 0;
      var soloAudio = false;
      var decidiendo = false;
      Timer? sinDuracion;

      Future<void> listo() async {
        sinDuracion?.cancel();
        if (completer.isCompleted || decidiendo) return;
        decidiendo = true;
        final enVivo = await kairosEnVivo(player);
        if (completer.isCompleted) return;
        streamController.add(
          VideoEvent(
            eventType: VideoEventType.initialized,
            size: Size(width * 1.0, height * 1.0),
            duration: enVivo ? kairosSinFin : player.state.duration,
          ),
        );
        completer.complete();
      }

      void notify() {
        if (completer.isCompleted || decidiendo) return;
        if (!soloAudio && (width <= 0 || height <= 0)) return;
        if (player.state.duration > Duration.zero) {
          listo();
          return;
        }
        // Una película puede tardar un instante más en decir su duración; sin ella, es en vivo
        sinDuracion ??= Timer(kairosEsperaDuracion, listo);
      }

      streamSubscriptions.add(
        player.stream.duration.listen(
          (event) {
            if (event > Duration.zero) notify();
          },
        ),
      );
      streamSubscriptions.add(
        player.stream.videoParams.listen(
          (event) {
            width = event.dw ?? 0;
            height = event.dh ?? 0;
            notify();
          },
        ),
      );
      streamSubscriptions.add(
        player.stream.tracks.listen(
          (event) {
            // No video track is available i.e. an audio file.
            if (event.video.length == 2 && event.audio.length > 2) {
              soloAudio = true;
              width = 0;
              height = 0;
              notify();
            }
          },
        ),
      );
      // KAIROS TV: si la dirección no abre (no existe, el servidor no contesta, formato desconocido), se avisa
      // ya y la app pasa a otra fuente. De fábrica los errores esperaban a que estuviera listo: la app esperaba su
      // tiempo entero. Los avisos del decodificador (comunes en IPTV y casi siempre sin consecuencias) no cuentan.
      streamSubscriptions.add(
        player.stream.log.listen(
          (log) {
            if (completer.isCompleted || !kairosNoAbre(log.prefix, log.level, log.text)) return;
            sinDuracion?.cancel();
            completer.complete();
            fallo[textureId] = true;
            streamController.addError(PlatformException(code: 'media_kit', message: log.text));
          },
        ),
      );
      // VideoEventType.isPlayingStateUpdate
      streamSubscriptions.add(
        player.stream.playing.listen(
          (event) async {
            await completer.future;
            streamController.add(
              VideoEvent(
                eventType: VideoEventType.isPlayingStateUpdate,
                isPlaying: event,
              ),
            );
          },
        ),
      );
      // VideoEventType.completed
      streamSubscriptions.add(
        player.stream.completed.listen(
          (event) async {
            await completer.future;
            if (event) {
              streamController.add(
                VideoEvent(
                  eventType: VideoEventType.completed,
                ),
              );
            }
          },
        ),
      );
      // VideoEventType.bufferingStart
      streamSubscriptions.add(
        player.stream.buffering.listen(
          (event) async {
            await completer.future;
            streamController.add(
              VideoEvent(
                eventType: event
                    ? VideoEventType.bufferingStart
                    : VideoEventType.bufferingEnd,
              ),
            );
          },
        ),
      );
      // VideoEventType.bufferingUpdate
      streamSubscriptions.add(
        player.stream.buffer.listen(
          (event) async {
            await completer.future;
            streamController.add(
              VideoEvent(
                eventType: VideoEventType.bufferingUpdate,
                buffered: [
                  DurationRange(
                    Duration.zero,
                    event,
                  ),
                ],
              ),
            );
          },
        ),
      );

      streamSubscriptions.add(
        player.stream.error.listen(
          (event) async {
            await completer.future;
            if (fallo[textureId] == true) return; // KAIROS TV: ya se avisó que no abre
            streamController.addError(
              PlatformException(
                code: '',
                message: event,
              ),
            );
          },
        ),
      );
    }
  }
}
