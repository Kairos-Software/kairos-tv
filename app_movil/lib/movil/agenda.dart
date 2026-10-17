/// La Agenda: partidos y programas especiales que se cargan en el panel
/// (servidor: agenda/, API /api/v1/agenda/), cada uno con su canal en vivo.
///
///   - [EventoAgenda]: un evento, con su canal ya buscado en el catálogo. Lo
///     que tiene un canal que este aparato no muestra, no aparece.
///   - [Avisos]: "Avisarme". En el CELULAR, un aviso de Android 5 minutos antes
///     (aunque la app esté cerrada); tocarlo abre la app en ese canal. En la
///     TV, un cartel "Empieza ahora" si la app está abierta (tv/agenda.dart).
///     Lo marcado se guarda en el aparato.
///
/// La traen Catalogo.cargar (datos.dart) y las pantallas: movil/agenda_vista.dart
/// (celular) y tv/agenda.dart (TV).
library;

import 'package:flutter/material.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:timezone/data/latest_10y.dart' as zonas;
import 'package:timezone/timezone.dart' as tz;

import '../api/modelos.dart';
import '../aparato.dart';
import 'estilo.dart';

/// Los tipos de evento (los mismos que el panel: agenda/models.py -> Evento.Tipo).
IconData iconoDeEvento(String tipo) => switch (tipo) {
  'futbol' => Icons.sports_soccer_rounded,
  'deporte' => Icons.sports_basketball_rounded,
  'noticias' => Icons.newspaper_rounded,
  'especial' => Icons.star_rounded,
  _ => Icons.event_rounded,
};

class EventoAgenda {
  EventoAgenda({
    required this.id,
    required this.titulo,
    required this.detalle,
    required this.tipo,
    required this.canal,
    required this.empieza,
    required this.termina,
  });

  /// [buscarCanal]: el canal con ese id en el catálogo (null = no se ve en este aparato).
  static EventoAgenda? desdeJson(Map<String, dynamic> json, Canal? Function(int id) buscarCanal) {
    final canal = json['canal'] is int ? buscarCanal(json['canal'] as int) : null;
    final empieza = DateTime.tryParse('${json['empieza']}');
    if (canal == null || empieza == null || json['id'] is! int) return null;
    return EventoAgenda(
      id: json['id'] as int,
      titulo: '${json['titulo'] ?? ''}',
      detalle: '${json['detalle'] ?? ''}',
      tipo: '${json['tipo'] ?? ''}',
      canal: canal,
      empieza: empieza.toLocal(),
      termina: (DateTime.tryParse('${json['termina']}') ?? empieza.add(const Duration(hours: 2))).toLocal(),
    );
  }

  final int id;
  final String titulo;
  final String detalle;
  final String tipo;
  final Canal canal;
  final DateTime empieza;
  final DateTime termina;

  bool enVivo([DateTime? ahora]) {
    final momento = ahora ?? DateTime.now();
    return !momento.isBefore(empieza) && momento.isBefore(termina);
  }

  bool termino([DateTime? ahora]) => !(ahora ?? DateTime.now()).isBefore(termina);

  /// "EN VIVO", "Hoy 21:00", "Mañana 21:00", "Sáb 18/10 · 21:00".
  String cuando([DateTime? ahora]) {
    final momento = ahora ?? DateTime.now();
    if (enVivo(momento)) return 'EN VIVO';
    return '${nombreDelDia(empieza, momento)}${_esHoyOManiana(empieza, momento) ? ' ' : ' · '}${hora(empieza)}';
  }
}

String hora(DateTime momento) =>
    '${momento.hour.toString().padLeft(2, '0')}:${momento.minute.toString().padLeft(2, '0')}';

bool _esHoyOManiana(DateTime dia, DateTime ahora) {
  final diferencia = DateTime(dia.year, dia.month, dia.day).difference(DateTime(ahora.year, ahora.month, ahora.day));
  return diferencia.inDays == 0 || diferencia.inDays == 1;
}

/// "Hoy", "Mañana", "Sáb 18/10".
String nombreDelDia(DateTime dia, DateTime ahora) {
  final diferencia = DateTime(dia.year, dia.month, dia.day).difference(DateTime(ahora.year, ahora.month, ahora.day));
  if (diferencia.inDays == 0) return 'Hoy';
  if (diferencia.inDays == 1) return 'Mañana';
  const dias = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];
  return '${dias[dia.weekday - 1]} ${dia.day}/${dia.month}';
}

/// "Avisarme": lo que la persona marcó en ESTE aparato, y los avisos.
class Avisos {
  Avisos._();

  static const _clave = 'kairos.avisarme';

  /// El aviso del celular llega este tiempo antes de que empiece.
  static const anticipacion = Duration(minutes: 5);

  static final _notificaciones = FlutterLocalNotificationsPlugin();
  static final Set<int> _marcados = {};
  static bool _iniciado = false;
  static bool _conNotificaciones = false;

  /// Cambia cuando se marca o desmarca algo (para redibujar los botones).
  static final cambios = ValueNotifier<int>(0);

  /// El canal que pidió un aviso tocado (la app lo abre en En Vivo: movil/estructura.dart).
  static final canalPedido = ValueNotifier<int?>(null);

  /// Al abrir la app (main.dart). En la TV no hay avisos de Android: se avisa
  /// con un cartel si la app está abierta (tv/agenda.dart).
  static Future<void> iniciar() async {
    if (_iniciado) return;
    _iniciado = true;
    try {
      final guardados = (await SharedPreferences.getInstance()).getStringList(_clave) ?? const [];
      _marcados.addAll(guardados.map(int.tryParse).nonNulls);
    } catch (_) {
      // Sin lo guardado: se arranca sin marcados
    }
    if (Aparato.esTv) return;
    try {
      zonas.initializeTimeZones();
      await _notificaciones.initialize(
        settings: const InitializationSettings(android: AndroidInitializationSettings('ic_aviso')),
        onDidReceiveNotificationResponse: (respuesta) => _abrir(respuesta.payload),
      );
      _conNotificaciones = true;
      final inicio = await _notificaciones.getNotificationAppLaunchDetails();
      if (inicio?.didNotificationLaunchApp ?? false) _abrir(inicio!.notificationResponse?.payload);
    } catch (_) {
      // Este aparato no tiene avisos (o en los tests): "Avisarme" queda marcado igual
    }
  }

  /// Para los tests: marcar sin guardar ni programar.
  @visibleForTesting
  static void poner(Set<int> marcados) {
    _marcados
      ..clear()
      ..addAll(marcados);
    cambios.value++;
  }

  static void _abrir(String? carga) {
    final canal = int.tryParse((carga ?? '').replaceFirst('canal:', ''));
    if (canal != null) canalPedido.value = canal;
  }

  static bool marcado(EventoAgenda evento) => _marcados.contains(evento.id);

  /// Marca o desmarca [evento]. Devuelve si quedó marcado.
  static Future<bool> alternar(EventoAgenda evento) async {
    final marcar = !_marcados.contains(evento.id);
    if (marcar) {
      _marcados.add(evento.id);
      // La primera vez Android (13 en adelante) pregunta si la app puede mostrar avisos
      if (_conNotificaciones) {
        try {
          await _notificaciones
              .resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>()
              ?.requestNotificationsPermission();
        } catch (_) {}
      }
      await _programar(evento);
    } else {
      _marcados.remove(evento.id);
      await _cancelar(evento.id);
    }
    cambios.value++;
    _guardar();
    return marcar;
  }

  /// Llegó la agenda (Catalogo.cargar): los avisos se reprograman con la hora
  /// de ahora (si en el panel cambió) y se olvida lo que ya terminó o se sacó.
  static Future<void> sincronizar(List<EventoAgenda> agenda) async {
    if (!_iniciado || _marcados.isEmpty) return;
    final porId = {for (final e in agenda) e.id: e};
    for (final id in _marcados.toList()) {
      final evento = porId[id];
      if (evento == null || evento.termino()) {
        _marcados.remove(id);
        await _cancelar(id);
      } else {
        await _programar(evento);
      }
    }
    cambios.value++;
    _guardar();
  }

  /// Lo marcado que está empezando ahora (para el cartel de la TV). [yaMostrados]: los ids ya avisados.
  static List<EventoAgenda> empezandoAhora(List<EventoAgenda> agenda, Set<int> yaMostrados, [DateTime? ahora]) {
    final momento = ahora ?? DateTime.now();
    return [
      for (final evento in agenda)
        if (_marcados.contains(evento.id) &&
            !yaMostrados.contains(evento.id) &&
            !momento.isBefore(evento.empieza.subtract(const Duration(minutes: 1))) &&
            momento.isBefore(evento.empieza.add(const Duration(minutes: 20))))
          evento,
    ];
  }

  static Future<void> _programar(EventoAgenda evento) async {
    if (!_conNotificaciones) return;
    final ahora = DateTime.now();
    var cuando = evento.empieza.subtract(anticipacion);
    if (!cuando.isAfter(ahora)) cuando = evento.empieza;
    if (!cuando.isAfter(ahora)) return; // ya empezó: el botón dice "Ver"
    try {
      await _notificaciones.zonedSchedule(
        id: evento.id,
        scheduledDate: tz.TZDateTime.from(cuando.toUtc(), tz.UTC),
        title: '${evento.titulo} empieza a las ${hora(evento.empieza)}',
        body: 'En ${evento.canal.nombre}. Tocá para verlo.',
        payload: 'canal:${evento.canal.id}',
        notificationDetails: const NotificationDetails(
          android: AndroidNotificationDetails(
            'agenda',
            'Agenda',
            channelDescription: 'Cuando empieza lo que marcaste con "Avisarme".',
            importance: Importance.high,
            priority: Priority.high,
            icon: 'ic_aviso',
            color: Tono.celeste,
          ),
        ),
        // Sin pedir el permiso de "alarmas exactas": puede llegar un par de minutos tarde
        androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
      );
    } catch (_) {
      // No se pudo programar (sin permiso): queda marcado; en la app se ve igual
    }
  }

  static Future<void> _cancelar(int id) async {
    if (!_conNotificaciones) return;
    try {
      await _notificaciones.cancel(id: id);
    } catch (_) {}
  }

  static Future<void> _guardar() async {
    try {
      await (await SharedPreferences.getInstance()).setStringList(_clave, [for (final id in _marcados) '$id']);
    } catch (_) {}
  }
}
