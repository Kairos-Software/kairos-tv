/// Cuánto se mira cada cosa, para "Lo más visto" del panel (en el servidor:
/// canales/estadisticas.py).
///
/// [ControlSenal] le va sumando el tiempo que un video se ve de verdad (no
/// en pausa ni cargando) y le avisa cuando algo se miró más de un minuto
/// seguido (una "vista"). La Biblioteca le avisa lo que se agrega a favoritos.
///
/// Se le manda al servidor de a ratos (POST canales/visto/): al juntar
/// [cadaCuanto] de video, y al salir del reproductor. Va solo qué se miró y
/// cuántos segundos: nada que diga quién es (el servidor tampoco lo guarda).
/// Si no se puede mandar (sin internet), queda para la próxima vez. Vive en
/// memoria: si la app se cierra de golpe se pierde lo último, y está bien
/// (son estadísticas, no hace falta más).
library;

import 'package:flutter/foundation.dart';

import '../api/cliente.dart';

class Medidor {
  Medidor._();

  /// Cada cuánto video mirado se le avisa al servidor (además de al salir del reproductor).
  static const cadaCuanto = Duration(minutes: 5);

  /// Lo que hace falta mirar de una vez para que cuente como una vista.
  static const paraUnaVista = Duration(minutes: 1);

  /// Lo que acepta el servidor en un aviso (canales/estadisticas.py: MAXIMO_DE_ELEMENTOS).
  static const _maximoPorAviso = 50;

  /// Si un aviso no llegó (sin internet), no se vuelve a probar solo hasta que pase esto.
  static const _esperaSiFalla = Duration(minutes: 2);

  static final Map<int, int> _milisegundos = {};
  static final Set<int> _vistas = {};
  static final List<String> _favoritos = [];
  static bool _enviando = false;
  static DateTime? _noAntesDe;

  /// Suma tiempo mirado de [id]. Si ya se juntó [cadaCuanto], avisa al servidor.
  static void sumar(ApiCliente api, int id, Duration cuanto) {
    if (cuanto <= Duration.zero) return;
    _milisegundos[id] = (_milisegundos[id] ?? 0) + cuanto.inMilliseconds;
    final total = _milisegundos.values.fold<int>(0, (suma, ms) => suma + ms);
    final espera = _noAntesDe;
    if (total >= cadaCuanto.inMilliseconds && (espera == null || DateTime.now().isAfter(espera))) enviar(api);
  }

  /// [id] se miró más de [paraUnaVista] de una vez.
  static void contarVista(int id) => _vistas.add(id);

  /// Se agregó a favoritos ("c:12" o "s:Nombre de la serie"). Va con el próximo aviso.
  static void favorito(String clave) {
    if (_favoritos.length < _maximoPorAviso) _favoritos.add(clave);
  }

  /// Le manda al servidor lo juntado. Si falla, lo devuelve para la próxima.
  static Future<void> enviar(ApiCliente api) async {
    // Lo que no llega a un segundo espera a juntar más
    final ids = {
      for (final MapEntry(:key, :value) in _milisegundos.entries)
        if (value >= 1000) key,
      ..._vistas,
    }.take(_maximoPorAviso).toList();
    if (_enviando || (ids.isEmpty && _favoritos.isEmpty)) return;
    final segundos = {for (final id in ids) id: (_milisegundos[id] ?? 0) ~/ 1000};
    final vistas = {
      for (final id in ids)
        if (_vistas.contains(id)) id,
    };
    final favoritos = List.of(_favoritos);
    // Se sacan ahora (lo que se mire mientras viaja el aviso se junta aparte);
    // queda lo que no llega a un segundo
    for (final id in ids) {
      final resto = (_milisegundos[id] ?? 0) % 1000;
      resto > 0 ? _milisegundos[id] = resto : _milisegundos.remove(id);
      _vistas.remove(id);
    }
    _favoritos.clear();

    _enviando = true;
    try {
      await api.post('canales/visto/', {
        'vistos': [
          for (final id in ids) {'id': id, 'segundos': segundos[id], 'vista': vistas.contains(id)},
        ],
        'favoritos': favoritos,
      });
      _noAntesDe = null;
    } catch (_) {
      _noAntesDe = DateTime.now().add(_esperaSiFalla);
      // Se devuelve: va con el próximo aviso
      for (final id in ids) {
        _milisegundos[id] = (_milisegundos[id] ?? 0) + segundos[id]! * 1000;
      }
      _vistas.addAll(vistas);
      for (final clave in favoritos) {
        favorito(clave);
      }
    } finally {
      _enviando = false;
    }
  }

  /// Lo que está juntado sin mandar (para los tests).
  @visibleForTesting
  static Map<String, dynamic> get pendiente => {
    'segundos': {for (final MapEntry(:key, :value) in _milisegundos.entries) key: value ~/ 1000},
    'vistas': Set.of(_vistas),
    'favoritos': List.of(_favoritos),
  };

  @visibleForTesting
  static void olvidar() {
    _milisegundos.clear();
    _vistas.clear();
    _favoritos.clear();
    _enviando = false;
    _noAntesDe = null;
  }
}
