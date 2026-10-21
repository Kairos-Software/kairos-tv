// "Mi agenda" (movil/recordatorios.dart): lo que cada uno anota con
// "Recordarme" en su aparato. Cuándo es la próxima vez, cómo se dice, guardar
// y borrar, la campanita y la hoja del celular, el diálogo de la TV (con las
// flechas) y la fila de Inicio.
import 'dart:convert';

import 'package:app_movil/api/cliente.dart';
import 'package:app_movil/api/modelos.dart';
import 'package:app_movil/movil/datos.dart';
import 'package:app_movil/movil/mi_agenda.dart';
import 'package:app_movil/movil/recordatorios.dart';
import 'package:app_movil/sesion.dart';
import 'package:app_movil/tv/estructura.dart';
import 'package:app_movil/tv/mi_agenda.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'servidor_de_prueba.dart';

/// Un servidor de mentira con dos canales en vivo.
class _Servidor extends ApiCliente with CrudoDesdeGet {
  _Servidor() : super(urlBase: 'http://prueba/api/v1/');

  @override
  Future<dynamic> get(String ruta, {Map<String, String>? parametros}) async {
    if (ruta == 'canales/secciones/') return {'secciones': []};
    if (parametros?['contenido'] != 'vivo') return {'cantidad': 0, 'categorias': []};
    return {
      'cantidad': 2,
      'categorias': [
        {
          'nombre': 'Deportes',
          'canales': [
            for (final (id, nombre) in [(1, 'TyC Sports'), (2, 'ESPN')])
              {
                'id': id,
                'nombre': nombre,
                'fuentes': [
                  {'id': id, 'url': 'https://x/$id.m3u8', 'tipo': 'hls'},
                ],
              },
          ],
        },
      ],
    };
  }
}

Future<Catalogo> _catalogo() async {
  final catalogo = Catalogo(_Servidor());
  await catalogo.cargar();
  return catalogo;
}

Recordatorio _anotado(int id, int canal, DateTime cuando, {String nombre = '', bool semanal = false}) =>
    Recordatorio(id: id, canal: canal, cuando: cuando, nombre: nombre, semanal: semanal);

Future<List<Map<String, dynamic>>> _guardados() async => [
  for (final texto in (await SharedPreferences.getInstance()).getStringList('kairos.recordatorios') ?? <String>[])
    jsonDecode(texto) as Map<String, dynamic>,
];

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
    Recordatorios.poner([]);
  });

  test('una sola vez: cuándo se dice, "en vivo" las 2 horas siguientes y después se va', () {
    final sabado = DateTime(2026, 10, 17, 18, 0);
    final partido = _anotado(1, 1, DateTime(2026, 10, 17, 21, 0), nombre: 'Boca vs River');
    expect(partido.cuandoTexto(sabado), 'Hoy 21:00');
    expect(partido.cuandoTexto(DateTime(2026, 10, 16, 12)), 'Mañana 21:00');
    expect(partido.cuandoTexto(DateTime(2026, 10, 14, 12)), 'Sáb 17/10 · 21:00');
    expect(partido.enVivo(DateTime(2026, 10, 17, 22, 30)), isTrue);
    expect(partido.cuandoTexto(DateTime(2026, 10, 17, 22, 30)), 'EN VIVO');
    expect(partido.vencido(DateTime(2026, 10, 17, 22, 59)), isFalse);
    expect(partido.vencido(DateTime(2026, 10, 17, 23, 0)), isTrue);
  });

  test('todas las semanas: la próxima vez es la semana que viene y nunca vence', () {
    final domingos = _anotado(1, 1, DateTime(2026, 10, 18, 21, 0), semanal: true);
    final despues = DateTime(2026, 10, 19, 10, 0); // lunes
    expect(domingos.proxima(despues), DateTime(2026, 10, 25, 21, 0));
    expect(domingos.vencido(DateTime(2027, 1, 1)), isFalse);
    expect(domingos.cuandoTexto(despues), 'Todos los domingos · 21:00');
    expect(domingos.enVivo(DateTime(2026, 11, 1, 21, 30)), isTrue);
  });

  test('guardar, cambiar y borrar quedan en el aparato', () async {
    final cuando = DateTime.now().add(const Duration(days: 1));
    await Recordatorios.guardar(_anotado(5, 1, cuando, nombre: 'La final'));
    expect((await _guardados()).single['nombre'], 'La final');

    await Recordatorios.guardar(_anotado(5, 1, cuando, nombre: 'La final', semanal: true)); // mismo id: cambia
    expect((await _guardados()).single['semanal'], isTrue);

    await Recordatorios.borrar(5);
    expect(await _guardados(), isEmpty);
  });

  test('la lista: lo más cercano primero, sin lo vencido ni lo de un canal que acá no se ve', () async {
    final ahora = DateTime.now();
    final catalogo = await _catalogo();
    Recordatorios.poner([
      _anotado(1, 2, ahora.add(const Duration(days: 2)), nombre: 'Pasado mañana'),
      _anotado(2, 1, ahora.add(const Duration(hours: 1)), nombre: 'En una hora'),
      _anotado(3, 99, ahora.add(const Duration(hours: 2)), nombre: 'Canal que no está'),
      _anotado(4, 1, ahora.subtract(const Duration(hours: 3)), nombre: 'Ya pasó'),
    ]);
    expect(Recordatorios.conCanal(catalogo).map((e) => e.$1.nombre), ['En una hora', 'Pasado mañana']);
    expect(Recordatorios.conCanal(catalogo).first.$2.nombre, 'TyC Sports');
  });

  test('el cartel de la TV: lo que está empezando, una vez por vez', () {
    final ahora = DateTime.now();
    Recordatorios.poner([
      _anotado(1, 1, ahora.add(const Duration(seconds: 30))),
      _anotado(2, 2, ahora.add(const Duration(hours: 1))),
    ]);
    final empezando = Recordatorios.empezandoAhora({});
    expect(empezando.map((e) => e.$1.id), [1]);
    final yaAvisado = Recordatorios.claveDeLaVez(empezando.single.$1, empezando.single.$2);
    expect(Recordatorios.empezandoAhora({yaAvisado}), isEmpty);
  });

  testWidgets('celular: la campanita abre "Recordarme", se guarda y aparece en Mi agenda', (tester) async {
    final catalogo = await tester.runAsync(_catalogo);
    final canal = catalogo!.canalPorId(1)!;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: DatosScope(
            catalogo: catalogo,
            biblioteca: Biblioteca(),
            child: ListView(
              children: [
                BotonRecordarme(canal: canal),
                const FilaMiAgenda(),
              ],
            ),
          ),
        ),
      ),
    );
    expect(find.text('Mi agenda'), findsNothing); // sin nada anotado, no está
    expect(find.byIcon(Icons.notifications_none_rounded), findsOneWidget);

    await tester.tap(find.byType(BotonRecordarme));
    await tester.pumpAndSettle();
    expect(find.text('Recordarme'), findsOneWidget);
    await tester.enterText(find.byType(TextField), 'Boca vs River');
    await tester.ensureVisible(find.text('Guardar'));
    await tester.tap(find.text('Guardar'));
    await tester.pumpAndSettle();

    expect(find.text('Mi agenda'), findsOneWidget);
    expect(find.text('Boca vs River'), findsOneWidget);
    expect(find.byIcon(Icons.notifications_active_rounded), findsWidgets); // la campanita, encendida
    expect((await _guardados()).single, containsPair('nombre_del_canal', 'TyC Sports'));

    // Tocar la tarjeta lo abre para cambiarlo (o sacarlo)
    await tester.tap(find.text('Boca vs River'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Sacarlo de mi agenda'));
    await tester.tap(find.text('Sacarlo de mi agenda'));
    await tester.pumpAndSettle();
    expect(find.text('Mi agenda'), findsNothing);
  });

  testWidgets('celular: si ya empezó, "Ver" pide abrir el canal', (tester) async {
    final catalogo = await tester.runAsync(_catalogo);
    Recordatorios.poner([_anotado(8, 2, DateTime.now().subtract(const Duration(minutes: 10)), nombre: 'El partido')]);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: DatosScope(catalogo: catalogo!, biblioteca: Biblioteca(), child: const FilaMiAgenda()),
        ),
      ),
    );
    await tester.tap(find.text('Ver'));
    expect(Recordatorios.canalPedido.value, 2);
    Recordatorios.canalPedido.value = null;
  });

  testWidgets('TV: en "Recordarme" las flechas cambian el día y la hora', (tester) async {
    tester.view.physicalSize = const Size(1920, 1080);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final canal = Canal({'id': 1, 'nombre': 'TyC Sports', 'fuentes': <dynamic>[]}, contenido: 'vivo');
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => Scaffold(
            body: TextButton(
              onPressed: () => showDialog<String>(
                context: context,
                builder: (_) => DialogoRecordarmeTv(canal: canal),
              ),
              child: const Text('abrir'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('abrir'));
    await tester.pumpAndSettle();
    // Uno nuevo arranca en la próxima hora en punto (después de las 23, mañana)
    final hoy = DateTime.now();
    final primerDia = DateTime(hoy.year, hoy.month, hoy.day, hoy.hour + 1);
    String valor(int renglon) => (tester.widget(find.byType(AjusteTv).at(renglon)) as AjusteTv).valor;
    final antes = valor(0);
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight); // Día: el siguiente
    await tester.pump();
    expect(valor(0), isNot(antes));
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown); // a la Hora
    await tester.pump();
    final hora = int.parse(valor(1));
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowLeft);
    await tester.pump();
    expect(valor(1), ((hora + 23) % 24).toString().padLeft(2, '0'));

    await tester.tap(find.text('Guardar'));
    await tester.pumpAndSettle();
    final siguiente = DateTime(primerDia.year, primerDia.month, primerDia.day + 1);
    final guardado = (await _guardados()).single;
    final cuando = DateTime.parse(guardado['cuando'] as String).toLocal();
    expect((cuando.year, cuando.month, cuando.day), (siguiente.year, siguiente.month, siguiente.day));
    expect(cuando.hour, (hora + 23) % 24);
  });

  testWidgets('TV: la fila de Mi agenda está en Inicio', (tester) async {
    tester.view.physicalSize = const Size(1920, 1080);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final catalogo = await tester.runAsync(_catalogo);
    Recordatorios.poner([_anotado(9, 1, DateTime.now().add(const Duration(hours: 2)), nombre: 'Final de la Copa')]);
    await tester.pumpWidget(
      SesionScope(
        sesion: Sesion(),
        child: MaterialApp(
          home: PantallaTv(catalogo: catalogo!, biblioteca: Biblioteca()),
        ),
      ),
    );
    // Sin pumpAndSettle: el punto de EN VIVO de las tarjetas de canales titila siempre
    await tester.pump(const Duration(seconds: 1));
    expect(find.byType(TarjetaRecordatorioTv), findsOneWidget);
    expect(find.text('Final de la Copa'), findsOneWidget);
  });
}
