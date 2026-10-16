// "Ver en la tele" (lib/tele/) sin una tele de verdad: el canal "kairos/tele"
// de Android se simula. Del lado del celular, qué le manda a la tele; del lado
// de la tele, que abra y cierre lo que el celular le dice.
import 'package:app_movil/api/cliente.dart';
import 'package:app_movil/api/modelos.dart';
import 'package:app_movil/movil/datos.dart';
import 'package:app_movil/movil/detalle.dart';
import 'package:app_movil/movil/reproductor_vod.dart';
import 'package:app_movil/sesion.dart';
import 'package:app_movil/tele/control_remoto.dart';
import 'package:app_movil/tele/en_la_tele.dart';
import 'package:app_movil/tele/enlace.dart';
import 'package:app_movil/tv/detalle.dart';
import 'package:app_movil/tv/estructura.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

const _canal = MethodChannel('kairos/tele');

Canal _pelicula(int id) =>
    Canal({'id': id, 'nombre': 'Película $id', 'fuentes': <dynamic>[]}, categoria: 'Acción', contenido: 'pelicula');

Canal _vivo(int id) => Canal({'id': id, 'nombre': 'Canal $id', 'fuentes': <dynamic>[]}, contenido: 'vivo');

/// Lo que la app le pidió a Android por el canal de la tele.
final _llamadas = <MethodCall>[];

/// El último estado que el celular le mandó a la tele.
Map<Object?, Object?> get _ultimaOrden => _llamadas.lastWhere((l) => l.method == 'orden').arguments as Map;

List<Map<Object?, Object?>> get _capas => [for (final c in _ultimaOrden['capas'] as List) c as Map];

/// Android avisa algo por el canal (que se conectó la tele, que cerró algo...).
Future<void> _avisaAndroid(String metodo, [Object? datos]) async {
  await TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.handlePlatformMessage(
    _canal.name,
    const StandardMethodCodec().encodeMethodCall(MethodCall(metodo, datos)),
    (_) {},
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    _llamadas.clear();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(_canal, (llamada) async {
      _llamadas.add(llamada);
      return llamada.method == 'estado' ? {'conectada': false, 'nombre': ''} : null;
    });
    await Tele.instancia.escuchar();
  });

  tearDown(() async {
    await _avisaAndroid('desconectada');
    Tele.instancia.seccion(null);
  });

  group('el celular le dice a la tele qué mostrar', () {
    test('sin tele no manda nada y las pantallas se abren como siempre', () {
      expect(Tele.instancia.abrir(PantallaDetalle.pelicula(_pelicula(1))), isNull);
      expect(_llamadas.where((l) => l.method == 'orden'), isEmpty);
    });

    test('al conectarse manda dónde está el celular; un detalle y una película van encima', () async {
      Tele.instancia.seccion('peliculas');
      await _avisaAndroid('conectada', {'nombre': 'Kanji Smart TV'});
      expect(Tele.instancia.conectada, isTrue);
      expect(Tele.instancia.nombre, 'Kanji Smart TV');
      expect(_ultimaOrden['seccion'], 'peliculas');
      expect(_capas, isEmpty);

      final pelicula = _pelicula(7);
      final detalle = Tele.instancia.abrir(PantallaDetalle.pelicula(pelicula))!;
      expect(detalle.enElCelular, isNull); // en el celular se ve el detalle de siempre
      expect(_capas.single['tipo'], 'detalle');
      expect(_capas.single['canal'], 7);

      // La película se reproduce en la tele: en el celular, el control remoto
      final reproductor = Tele.instancia.abrir(
        PantallaReproductorVod(canal: pelicula, desde: const Duration(minutes: 12)),
      )!;
      expect(reproductor.enElCelular, isA<ControlRemotoTele>());
      expect(_capas.map((c) => c['tipo']), ['detalle', 'pelicula']);
      expect(_capas.last['desde'], const Duration(minutes: 12).inMilliseconds);

      // Volver atrás en el celular la cierra también en la tele
      Tele.instancia.cerrar(reproductor);
      expect(_capas.map((c) => c['tipo']), ['detalle']);
      Tele.instancia.cerrar(detalle);
      expect(_capas, isEmpty);
    });

    test('un canal en vivo va en la tele mientras se está en En Vivo', () async {
      await _avisaAndroid('conectada', {'nombre': ''});
      final enVivo = Object();
      Tele.instancia.seccion('enVivo');
      Tele.instancia.verEnVivo(_vivo(3), duenio: enVivo);
      expect(_capas.single['tipo'], 'vivo');
      expect(_capas.single['canal'], 3);
      expect(Tele.instancia.enVivoDe(enVivo)?.id, 3);
      expect(Tele.instancia.enVivoDe(Object()), isNull); // solo quien lo puso lo ve como suyo

      // Cambiar de canal es otra capa (la tele cierra uno y abre el otro)
      final antes = _capas.single['clave'];
      Tele.instancia.verEnVivo(_vivo(4), duenio: enVivo);
      expect(_capas.single['clave'], isNot(antes));

      // Irse de En Vivo lo saca enseguida (la tele no lo abre encima de Inicio)
      Tele.instancia.seccion('inicio');
      expect(_ultimaOrden['seccion'], 'inicio');
      expect(_capas, isEmpty);
    });

    test('si la tele cierra la película sola, el control remoto se entera', () async {
      await _avisaAndroid('conectada', {'nombre': ''});
      final capa = Tele.instancia.abrir(PantallaReproductorVod(canal: _pelicula(2)))!;
      final cerradas = <String>[];
      final escucha = Tele.instancia.cerradas.listen(cerradas.add);
      await _avisaAndroid('cerrada', {'clave': capa.clave});
      await Future<void>.delayed(Duration.zero);
      expect(cerradas, [capa.clave]);
      await escucha.cancel();
      Tele.instancia.cerrar(capa);
    });

    test('los botones del control llegan a Android solo con la tele conectada', () async {
      Tele.instancia.tecla('pausa');
      expect(_llamadas.where((l) => l.method == 'tecla'), isEmpty);
      await _avisaAndroid('conectada', {'nombre': ''});
      Tele.instancia.tecla('pausa');
      expect(_llamadas.lastWhere((l) => l.method == 'tecla').arguments, {'tecla': 'pausa'});
    });
  });

  group('la tele copia al celular', () {
    Future<void> abrirTele(WidgetTester tester) async {
      tester.view.physicalSize = const Size(1920, 1080);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final catalogo = Catalogo(ApiCliente(urlBase: 'http://prueba/api/v1/'))
        ..peliculas = [for (var i = 1; i <= 6; i++) _pelicula(i)]
        ..cargado = true;
      await tester.pumpWidget(
        SesionScope(
          sesion: Sesion(),
          child: MaterialApp(
            home: PantallaTv(catalogo: catalogo, biblioteca: Biblioteca(), espejo: true),
          ),
        ),
      );
      await tester.pumpAndSettle();
    }

    testWidgets('cambia de sección y abre y cierra el detalle que abrió el celular', (tester) async {
      await abrirTele(tester);
      EspejoTv.instancia.recibir({'seccion': 'peliculas', 'capas': <Object>[]});
      await tester.pumpAndSettle();
      expect(find.text('Película 6'), findsWidgets); // la grilla de Películas

      EspejoTv.instancia.recibir({
        'seccion': 'peliculas',
        'capas': [
          {'clave': 'c1', 'tipo': 'detalle', 'canal': 3},
        ],
      });
      await tester.pumpAndSettle();
      expect(find.byType(DetalleTv), findsOneWidget);

      // El mismo estado otra vez no abre otro detalle
      EspejoTv.instancia.recibir({
        'seccion': 'peliculas',
        'capas': [
          {'clave': 'c1', 'tipo': 'detalle', 'canal': 3},
        ],
      });
      await tester.pumpAndSettle();
      expect(find.byType(DetalleTv), findsOneWidget);

      // El celular volvió atrás
      EspejoTv.instancia.recibir({'seccion': 'peliculas', 'capas': <Object>[]});
      await tester.pumpAndSettle();
      expect(find.byType(DetalleTv), findsNothing);
      expect(ModalRoute.of(tester.element(find.byType(PantallaTv)))?.isCurrent, isTrue);
    });

    testWidgets('si algo ya no está en el catálogo de la tele, no abre nada (ni lo de encima)', (tester) async {
      await abrirTele(tester);
      EspejoTv.instancia.recibir({
        'seccion': 'peliculas',
        'capas': [
          {'clave': 'c1', 'tipo': 'detalle', 'canal': 999},
          {'clave': 'c2', 'tipo': 'detalle', 'canal': 2},
        ],
      });
      await tester.pumpAndSettle();
      expect(find.byType(DetalleTv), findsNothing);
    });

    testWidgets('si la tele cierra sola lo que abrió el celular, le avisa', (tester) async {
      await abrirTele(tester);
      EspejoTv.instancia.recibir({
        'seccion': 'inicio',
        'capas': [
          {'clave': 'c9', 'tipo': 'detalle', 'canal': 1},
        ],
      });
      await tester.pumpAndSettle();
      Navigator.pop(tester.element(find.byType(DetalleTv)));
      await tester.pumpAndSettle();
      expect(_llamadas.lastWhere((l) => l.method == 'cerrada').arguments, {'clave': 'c9'});
    });
  });
}
