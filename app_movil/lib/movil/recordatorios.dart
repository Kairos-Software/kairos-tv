/// "Mi agenda": lo que cada persona quiere que le recordemos. Lo anota ella
/// misma con la campanita de un canal ("Recordarme": qué va a ver, día y
/// hora, y si se repite todas las semanas). Se guarda en ESTE aparato: nadie
/// más lo ve y el servidor no participa.
///
///   - [Recordatorio]: uno anotado (canal, nombre opcional, cuándo, semanal).
///   - [Recordatorios]: la lista y los avisos. En el CELULAR, un aviso de
///     Android 5 minutos antes (aunque la app esté cerrada); tocarlo abre la
///     app en ese canal. En la TV, un cartel "Empieza ..." si la app está
///     abierta (tv/mi_agenda.dart).
///
/// Las pantallas: movil/mi_agenda.dart (celular) y tv/mi_agenda.dart (TV).
library;

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:timezone/data/latest_10y.dart' as zonas;
import 'package:timezone/timezone.dart' as tz;

import '../api/modelos.dart';
import '../aparato.dart';
import 'datos.dart';
import 'estilo.dart';

class Recordatorio {
  const Recordatorio({
    required this.id,
    required this.canal,
    required this.cuando,
    this.nombre = '',
    this.semanal = false,
    this.nombreDelCanal = '',
  });

  static Recordatorio? desdeJson(Map<String, dynamic> json) {
    final cuando = DateTime.tryParse('${json['cuando']}');
    if (json['id'] is! int || json['canal'] is! int || cuando == null) return null;
    return Recordatorio(
      id: json['id'] as int,
      canal: json['canal'] as int,
      cuando: cuando.toLocal(),
      nombre: '${json['nombre'] ?? ''}',
      semanal: json['semanal'] == true,
      nombreDelCanal: '${json['nombre_del_canal'] ?? ''}',
    );
  }

  Map<String, dynamic> aJson() => {
    'id': id,
    'canal': canal,
    'cuando': cuando.toUtc().toIso8601String(),
    'nombre': nombre,
    'semanal': semanal,
    'nombre_del_canal': nombreDelCanal,
  };

  /// También es el número del aviso de Android.
  final int id;

  /// El id del canal en vivo.
  final int canal;

  /// Cuándo empieza (si es semanal, la primera vez).
  final DateTime cuando;

  /// Lo que va a ver ("Boca vs River"); vacío = el nombre del canal.
  final String nombre;
  final bool semanal;

  /// Para el aviso de Android (que sale con la app cerrada, sin el catálogo).
  final String nombreDelCanal;

  /// Hasta cuánto después de empezar cuenta como "se está dando" (botón Ver).
  static const duracion = Duration(hours: 2);

  /// La vez que viene (o la que se está dando ahora).
  DateTime proxima([DateTime? ahora]) {
    final momento = ahora ?? DateTime.now();
    var vez = cuando;
    while (semanal && !momento.isBefore(vez.add(duracion))) {
      vez = DateTime(vez.year, vez.month, vez.day + 7, vez.hour, vez.minute);
    }
    return vez;
  }

  bool enVivo([DateTime? ahora]) {
    final momento = ahora ?? DateTime.now();
    final vez = proxima(momento);
    return !momento.isBefore(vez) && momento.isBefore(vez.add(duracion));
  }

  /// Ya pasó y no se repite: se borra solo.
  bool vencido([DateTime? ahora]) => !semanal && !(ahora ?? DateTime.now()).isBefore(cuando.add(duracion));

  String titulo(Canal canal) => nombre.isNotEmpty ? nombre : canal.nombre;

  /// "EN VIVO", "Hoy 21:00", "Mañana 21:00", "Sáb 18/10 · 21:00", "Todos los sábados · 21:00".
  String cuandoTexto([DateTime? ahora]) {
    final momento = ahora ?? DateTime.now();
    if (enVivo(momento)) return 'EN VIVO';
    final vez = proxima(momento);
    if (semanal) return 'Todos los ${diaDeLaSemana(vez, plural: true)} · ${hora(vez)}';
    final dia = nombreDelDia(vez, momento);
    return '$dia${dia == 'Hoy' || dia == 'Mañana' ? ' ' : ' · '}${hora(vez)}';
  }

  Recordatorio copiar({DateTime? cuando, String? nombre, bool? semanal}) => Recordatorio(
    id: id,
    canal: canal,
    cuando: cuando ?? this.cuando,
    nombre: nombre ?? this.nombre,
    semanal: semanal ?? this.semanal,
    nombreDelCanal: nombreDelCanal,
  );
}

String hora(DateTime momento) =>
    '${momento.hour.toString().padLeft(2, '0')}:${momento.minute.toString().padLeft(2, '0')}';

/// "Hoy", "Mañana", "Sáb 18/10".
String nombreDelDia(DateTime dia, DateTime ahora) {
  final diferencia = DateTime(dia.year, dia.month, dia.day).difference(DateTime(ahora.year, ahora.month, ahora.day));
  if (diferencia.inDays == 0) return 'Hoy';
  if (diferencia.inDays == 1) return 'Mañana';
  const dias = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];
  return '${dias[dia.weekday - 1]} ${dia.day}/${dia.month}';
}

/// "sábado" (o "sábados").
String diaDeLaSemana(DateTime dia, {bool plural = false}) {
  const dias = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'];
  final nombre = dias[dia.weekday - 1];
  return plural && !nombre.endsWith('s') ? '${nombre}s' : nombre;
}

class Recordatorios {
  Recordatorios._();

  static const _clave = 'kairos.recordatorios';

  /// Lo que guardaba la Agenda del panel de la 1.2.25 (ya no existe): se borra.
  static const _claveVieja = 'kairos.avisarme';

  /// El aviso del celular llega este tiempo antes de que empiece.
  static const anticipacion = Duration(minutes: 5);

  static final _notificaciones = FlutterLocalNotificationsPlugin();
  static final List<Recordatorio> _lista = [];
  static bool _iniciado = false;
  static bool _conNotificaciones = false;

  /// Cambia cuando se agrega, cambia o borra algo (para redibujar).
  static final cambios = ValueNotifier<int>(0);

  /// El canal que pidió un aviso tocado o "Ver" (la app lo abre en En Vivo: movil/estructura.dart).
  static final canalPedido = ValueNotifier<int?>(null);

  /// Al abrir la app (main.dart). En la TV no hay avisos de Android: se avisa
  /// con un cartel si la app está abierta (tv/mi_agenda.dart).
  static Future<void> iniciar() async {
    if (_iniciado) return;
    _iniciado = true;
    List<String> viejos = const [];
    try {
      final preferencias = await SharedPreferences.getInstance();
      for (final texto in preferencias.getStringList(_clave) ?? const <String>[]) {
        try {
          final recordatorio = Recordatorio.desdeJson(jsonDecode(texto) as Map<String, dynamic>);
          if (recordatorio != null) _lista.add(recordatorio);
        } catch (_) {}
      }
      viejos = preferencias.getStringList(_claveVieja) ?? const [];
      if (viejos.isNotEmpty) await preferencias.remove(_claveVieja);
    } catch (_) {
      // Sin lo guardado: se arranca vacío
    }
    _lista.removeWhere((r) => r.vencido());
    cambios.value++;
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
      // Este aparato no tiene avisos (o en los tests): queda anotado igual
      return;
    }
    // Los avisos de la Agenda vieja que hayan quedado programados
    for (final id in viejos.map(int.tryParse).nonNulls) {
      await _cancelar(id);
    }
    // Por si Android los perdió (se reprograman con el mismo número: no se duplican)
    for (final recordatorio in _lista) {
      await _programar(recordatorio);
    }
  }

  /// Para los tests: poner la lista sin guardar ni programar.
  @visibleForTesting
  static void poner(List<Recordatorio> lista) {
    _lista
      ..clear()
      ..addAll(lista);
    cambios.value++;
  }

  static void _abrir(String? carga) {
    final canal = int.tryParse((carga ?? '').replaceFirst('canal:', ''));
    if (canal != null) canalPedido.value = canal;
  }

  /// Lo anotado (sin lo vencido), lo más cercano primero, con su canal. Lo de
  /// un canal que ya no se ve en este aparato no aparece.
  static List<(Recordatorio, Canal)> conCanal(Catalogo catalogo, [DateTime? ahora]) {
    final momento = ahora ?? DateTime.now();
    return [
      for (final recordatorio in _lista)
        if (!recordatorio.vencido(momento))
          if (catalogo.canalPorId(recordatorio.canal) case final canal?) (recordatorio, canal),
    ]..sort((a, b) => a.$1.proxima(momento).compareTo(b.$1.proxima(momento)));
  }

  /// Si hay algo anotado en [canal] (la campanita se ve encendida).
  static bool tiene(Canal canal) => _lista.any((r) => r.canal == canal.id && !r.vencido());

  /// Un número nuevo (también es el del aviso de Android, que tiene que entrar en 31 bits).
  static int nuevoId() {
    var id = DateTime.now().millisecondsSinceEpoch ~/ 1000 % 0x7fffffff;
    while (_lista.any((r) => r.id == id)) {
      id++;
    }
    return id;
  }

  /// Agrega [recordatorio] o, si ya estaba (mismo id), lo cambia.
  static Future<void> guardar(Recordatorio recordatorio) async {
    _lista
      ..removeWhere((r) => r.id == recordatorio.id)
      ..add(recordatorio);
    cambios.value++;
    // La primera vez Android (13 en adelante) pregunta si la app puede mostrar avisos
    if (_conNotificaciones) {
      try {
        await _notificaciones
            .resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>()
            ?.requestNotificationsPermission();
      } catch (_) {}
    }
    await _cancelar(recordatorio.id);
    await _programar(recordatorio);
    await _guardar();
  }

  static Future<void> borrar(int id) async {
    _lista.removeWhere((r) => r.id == id);
    cambios.value++;
    await _cancelar(id);
    await _guardar();
  }

  /// Lo que está empezando ahora (para el cartel de la TV), con la vez que
  /// empieza. [yaMostrados]: lo ya avisado (ver [claveDeLaVez]).
  static List<(Recordatorio, DateTime)> empezandoAhora(Set<String> yaMostrados, [DateTime? ahora]) {
    final momento = ahora ?? DateTime.now();
    return [
      for (final recordatorio in _lista)
        if (recordatorio.proxima(momento) case final vez
            when !yaMostrados.contains(claveDeLaVez(recordatorio, vez)) &&
                !momento.isBefore(vez.subtract(const Duration(minutes: 1))) &&
                momento.isBefore(vez.add(const Duration(minutes: 20))))
          (recordatorio, vez),
    ];
  }

  /// Cada vez de uno semanal se avisa una vez.
  static String claveDeLaVez(Recordatorio recordatorio, DateTime vez) =>
      '${recordatorio.id}@${vez.millisecondsSinceEpoch}';

  static Future<void> _programar(Recordatorio recordatorio) async {
    if (!_conNotificaciones) return;
    final ahora = DateTime.now();
    var vez = recordatorio.proxima(ahora);
    var aviso = vez.subtract(anticipacion);
    if (recordatorio.semanal) {
      // El aviso se repite a la misma hora: la primera vez es la que todavía llega 5 minutos antes
      while (!aviso.isAfter(ahora)) {
        vez = DateTime(vez.year, vez.month, vez.day + 7, vez.hour, vez.minute);
        aviso = vez.subtract(anticipacion);
      }
    } else {
      if (!aviso.isAfter(ahora)) aviso = vez;
      if (!aviso.isAfter(ahora)) return; // ya empezó: en la app dice "Ver"
    }
    final que = recordatorio.nombre.isNotEmpty ? recordatorio.nombre : recordatorio.nombreDelCanal;
    final donde = recordatorio.nombre.isNotEmpty && recordatorio.nombreDelCanal.isNotEmpty
        ? 'En ${recordatorio.nombreDelCanal}. '
        : '';
    try {
      await _notificaciones.zonedSchedule(
        id: recordatorio.id,
        // En UTC: los semanales se repiten a la misma hora UTC (en Argentina no hay cambio de hora)
        scheduledDate: tz.TZDateTime.from(aviso.toUtc(), tz.UTC),
        title: que.isEmpty ? 'Empieza a las ${hora(vez)}' : '$que empieza a las ${hora(vez)}',
        body: '${donde}Tocá para verlo.',
        payload: 'canal:${recordatorio.canal}',
        notificationDetails: const NotificationDetails(
          android: AndroidNotificationDetails(
            'agenda',
            'Mi agenda',
            channelDescription: 'Lo que anotaste con "Recordarme".',
            importance: Importance.high,
            priority: Priority.high,
            icon: 'ic_aviso',
            color: Tono.celeste,
          ),
        ),
        // Sin pedir el permiso de "alarmas exactas": puede llegar un par de minutos tarde
        androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
        matchDateTimeComponents: recordatorio.semanal ? DateTimeComponents.dayOfWeekAndTime : null,
      );
    } catch (_) {
      // No se pudo programar (sin permiso): queda anotado; en la app se ve igual
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
      await (await SharedPreferences.getInstance()).setStringList(_clave, [
        for (final recordatorio in _lista) jsonEncode(recordatorio.aJson()),
      ]);
    } catch (_) {}
  }
}
