// La Agenda (movil/agenda.dart): qué eventos se muestran, cómo se dice cuándo
// empiezan, "Avisarme" y la fila de Inicio en el celular y en la TV.
import 'package:app_movil/api/cliente.dart';
import 'package:app_movil/api/modelos.dart';
import 'package:app_movil/movil/agenda.dart';
import 'package:app_movil/movil/agenda_vista.dart';
import 'package:app_movil/movil/datos.dart';
import 'package:app_movil/sesion.dart';
import 'package:app_movil/tv/agenda.dart';
import 'package:app_movil/tv/estructura.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Un servidor de mentira con dos canales y la agenda que se le pase.
class _Servidor extends ApiCliente {
  _Servidor(this.eventos) : super(urlBase: 'http://prueba/api/v1/');

  final List<Map<String, dynamic>> eventos;

  @override
  Future<dynamic> get(String ruta, {Map<String, String>? parametros}) async {
    if (ruta == 'agenda/') return {'eventos': eventos};
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

Map<String, dynamic> _evento(
  int id,
  String titulo,
  int canal,
  DateTime empieza, {
  Duration dura = const Duration(hours: 2),
}) => {
  'id': id,
  'titulo': titulo,
  'detalle': 'Liga Profesional',
  'tipo': 'futbol',
  'canal': canal,
  'empieza': empieza.toUtc().toIso8601String(),
  'termina': empieza.add(dura).toUtc().toIso8601String(),
};

Canal _canal() => Canal({'id': 1, 'nombre': 'TyC Sports', 'fuentes': <dynamic>[]}, contenido: 'vivo');

Future<Catalogo> _catalogo(List<Map<String, dynamic>> eventos) async {
  final catalogo = Catalogo(_Servidor(eventos));
  await catalogo.cargar();
  return catalogo;
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
    Avisos.poner({});
  });

  test('llega con su canal; lo de un canal que acá no se ve y lo que terminó no está', () async {
    final ahora = DateTime.now();
    final catalogo = await _catalogo([
      _evento(1, 'Boca vs River', 1, ahora.add(const Duration(hours: 3))),
      _evento(2, 'En un canal que este aparato no muestra', 99, ahora.add(const Duration(hours: 1))),
      _evento(3, 'Ya terminó', 2, ahora.subtract(const Duration(hours: 3))),
      _evento(4, 'Se está dando', 2, ahora.subtract(const Duration(minutes: 30))),
    ]);
    expect(catalogo.agenda.map((e) => e.titulo), ['Boca vs River', 'Se está dando']);
    expect(catalogo.agenda.first.canal.nombre, 'TyC Sports');
    expect(catalogo.agenda.last.enVivo(), isTrue);
  });

  test('un servidor viejo (sin agenda) no es un error', () async {
    final catalogo = Catalogo(_SinAgenda());
    await catalogo.cargar();
    expect(catalogo.cargado, isTrue);
    expect(catalogo.agenda, isEmpty);
  });

  test('cuándo empieza, dicho corto', () {
    final ahora = DateTime(2026, 10, 17, 18, 0); // sábado
    EventoAgenda empieza(DateTime cuando) => EventoAgenda.desdeJson(_evento(1, 'X', 1, cuando), (_) => _canal())!;
    expect(empieza(DateTime(2026, 10, 17, 21, 0)).cuando(ahora), 'Hoy 21:00');
    expect(empieza(DateTime(2026, 10, 18, 9, 5)).cuando(ahora), 'Mañana 09:05');
    expect(empieza(DateTime(2026, 10, 21, 21, 0)).cuando(ahora), 'Mié 21/10 · 21:00');
    expect(empieza(DateTime(2026, 10, 17, 17, 30)).cuando(ahora), 'EN VIVO');
  });

  test('el cartel de la TV: solo lo marcado que está empezando, una vez', () async {
    final ahora = DateTime.now();
    final catalogo = await _catalogo([
      _evento(1, 'Empieza ya', 1, ahora.add(const Duration(seconds: 30))),
      _evento(2, 'Empieza en una hora', 2, ahora.add(const Duration(hours: 1))),
      _evento(3, 'Empieza ya, sin marcar', 2, ahora.add(const Duration(seconds: 30))),
    ]);
    Avisos.poner({1, 2});
    expect(Avisos.empezandoAhora(catalogo.agenda, {}).map((e) => e.id), [1]);
    expect(Avisos.empezandoAhora(catalogo.agenda, {1}), isEmpty); // ya se avisó
  });

  testWidgets('celular: la fila de Inicio, y "Avisarme" se marca y se desmarca', (tester) async {
    final catalogo = await tester.runAsync(
      () => _catalogo([_evento(7, 'Boca vs River', 1, DateTime.now().add(const Duration(hours: 5)))]),
    );
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: DatosScope(catalogo: catalogo!, biblioteca: Biblioteca(), child: const FilaAgenda()),
        ),
      ),
    );
    expect(find.text('Agenda'), findsOneWidget);
    expect(find.text('Boca vs River'), findsOneWidget);
    expect(find.text('TyC Sports'), findsOneWidget);

    await tester.tap(find.text('Avisarme'));
    await tester.pumpAndSettle();
    expect(find.text('Te aviso'), findsOneWidget);
    expect(Avisos.marcado(catalogo.agenda.single), isTrue);
    expect((await SharedPreferences.getInstance()).getStringList('kairos.avisarme'), ['7']);

    await tester.tap(find.text('Te aviso'));
    await tester.pumpAndSettle();
    expect(find.text('Avisarme'), findsOneWidget);
  });

  testWidgets('celular: si se está dando, en vez de "Avisarme" dice "Ver" y lo pide abrir', (tester) async {
    final catalogo = await tester.runAsync(
      () => _catalogo([_evento(8, 'El partido', 2, DateTime.now().subtract(const Duration(minutes: 10)))]),
    );
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: DatosScope(catalogo: catalogo!, biblioteca: Biblioteca(), child: const FilaAgenda()),
        ),
      ),
    );
    expect(find.text('Avisarme'), findsNothing);
    await tester.tap(find.text('Ver'));
    expect(Avisos.canalPedido.value, 2);
    Avisos.canalPedido.value = null;
  });

  testWidgets('TV: la fila de la agenda está en Inicio', (tester) async {
    tester.view.physicalSize = const Size(1920, 1080);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final catalogo = await tester.runAsync(
      () => _catalogo([_evento(9, 'Final de la Copa', 1, DateTime.now().add(const Duration(hours: 2)))]),
    );
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
    expect(find.byType(TarjetaEventoTv), findsOneWidget);
    expect(find.text('Final de la Copa'), findsOneWidget);
  });
}

class _SinAgenda extends _Servidor {
  _SinAgenda() : super(const []);

  @override
  Future<dynamic> get(String ruta, {Map<String, String>? parametros}) async {
    if (ruta == 'agenda/') throw ApiError(status: 404, codigo: 'no_existe', detalle: 'No existe.');
    return super.get(ruta, parametros: parametros);
  }
}
