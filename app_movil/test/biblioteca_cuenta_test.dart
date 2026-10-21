// Favoritos, "Continuar viendo" y últimos canales vistos son de la CUENTA
// (desde la 1.2.20): se traen del servidor, los cambios se mandan de a
// tandas sin pisarse, y "Seguir acá" ofrece lo que se miró en otro aparato.

import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:app_movil/api/cliente.dart';
import 'package:app_movil/aparato.dart';
import 'package:app_movil/movil/datos.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'servidor_de_prueba.dart';

/// Un servidor de prueba que hace lo mismo que biblioteca/servicios.py: suma los cambios.
class _Servidor extends ApiCliente with CrudoDesdeGet {
  _Servidor() : super(urlBase: 'http://prueba/api/v1/');

  final Set<String> favoritos = {};
  final Map<int, Map<String, dynamic>> progresos = {};
  final Map<int, Map<String, dynamic>> recientes = {};
  final List<Map<String, dynamic>> recibidos = [];
  bool sinInternet = false;

  /// Para frenar una respuesta (y hacer cambios mientras "viaja").
  Completer<void>? frenar;

  Map<String, dynamic> get _estado => {
    'favoritos': favoritos.toList(),
    'progresos': progresos.values.toList(),
    'recientes': recientes.values.toList(),
  };

  @override
  Future<dynamic> get(String ruta, {Map<String, String>? parametros}) async {
    if (sinInternet) throw ApiError(status: 0, codigo: 'sin_conexion', detalle: 'Sin conexión');
    return _estado;
  }

  @override
  Future<dynamic> post(String ruta, [Map<String, dynamic>? cuerpo]) async {
    if (sinInternet) throw ApiError(status: 0, codigo: 'sin_conexion', detalle: 'Sin conexión');
    final cambios = cuerpo ?? {};
    recibidos.add(cambios);
    await frenar?.future;
    favoritos
      ..addAll([for (final c in cambios['agregar'] as List) '$c'])
      ..removeAll([for (final c in cambios['quitar'] as List) '$c']);
    for (final id in cambios['olvidar'] as List) {
      progresos.remove(id);
    }
    for (final p in cambios['progresos'] as List) {
      progresos[p['id'] as int] = {...p as Map<String, dynamic>, 'aparato': cambios['aparato']};
    }
    for (final v in cambios['vistos'] as List) {
      recientes[v['id'] as int] = {...v as Map<String, dynamic>, 'aparato': cambios['aparato']};
    }
    return _estado;
  }
}

int _ms(DateTime momento) => momento.millisecondsSinceEpoch;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
    Aparato.nombre = 'TV del living';
  });

  test('trae lo de la cuenta y manda los cambios', () async {
    final servidor = _Servidor()
      ..favoritos.add('s:Pocoyó')
      ..progresos[5] = {'id': 5, 'p': 2580, 'd': 5400, 't': _ms(DateTime.now()), 'aparato': 'Celular'};
    final biblioteca = Biblioteca(api: servidor, cuenta: 'c48219037');
    await biblioteca.cargar();
    expect(biblioteca.estaEnMiLista('s:Pocoyó'), isTrue);
    expect(biblioteca.continuarViendo.single.posicion, const Duration(seconds: 2580));

    biblioteca.alternarMiLista('c:12');
    expect(biblioteca.estaEnMiLista('c:12'), isTrue); // se ve ya, sin esperar al servidor
    await biblioteca.sincronizar();
    expect(servidor.recibidos.last['agregar'], ['c:12']);
    expect(servidor.recibidos.last['aparato'], 'TV del living');
    expect(servidor.favoritos, {'s:Pocoyó', 'c:12'});
    biblioteca.dispose();
  });

  test('lo que se cambia mientras viaja la respuesta no se pierde', () async {
    final servidor = _Servidor();
    final biblioteca = Biblioteca(api: servidor, cuenta: 'c1');
    await biblioteca.cargar();
    biblioteca.alternarMiLista('c:1');
    servidor.frenar = Completer();
    final enviando = biblioteca.sincronizar();
    biblioteca.alternarMiLista('c:2'); // mientras tanto
    servidor.frenar!.complete();
    await enviando;
    expect(biblioteca.miLista, containsAll(['c:1', 'c:2']));
    servidor.frenar = null;
    await biblioteca.sincronizar();
    expect(servidor.favoritos, {'c:1', 'c:2'});
    biblioteca.dispose();
  });

  test('sin internet guarda los cambios y los manda después', () async {
    final servidor = _Servidor()..sinInternet = true;
    final biblioteca = Biblioteca(api: servidor, cuenta: 'c1');
    await biblioteca.cargar();
    biblioteca.guardarProgreso(7, const Duration(minutes: 10), const Duration(minutes: 90));
    await biblioteca.sincronizar();
    expect(servidor.progresos, isEmpty);
    biblioteca.dispose();

    // Se cerró la app: al abrirla de nuevo (con internet) manda lo que había quedado
    servidor.sinInternet = false;
    final otraVez = Biblioteca(api: servidor, cuenta: 'c1');
    await otraVez.cargar();
    expect(servidor.progresos[7]!['p'], 600);
    expect(otraVez.progresoDe(7)!.posicion, const Duration(minutes: 10));
    otraVez.dispose();
  });

  test('cada cuenta tiene su copia: otro cliente en la misma TV no ve lo del anterior', () async {
    final deAna = _Servidor()..favoritos.add('c:1');
    final ana = Biblioteca(api: deAna, cuenta: 'cAna');
    await ana.cargar();
    ana.dispose();
    final deLuis = _Servidor()..sinInternet = true; // ni siquiera con lo guardado en el aparato
    final luis = Biblioteca(api: deLuis, cuenta: 'cLuis');
    await luis.cargar();
    expect(luis.miLista, isEmpty);
    luis.dispose();
  });

  test('lo que guardaban las versiones anteriores en el aparato pasa a la cuenta', () async {
    SharedPreferences.setMockInitialValues({
      'kairos.mi_lista': ['c:3'],
      'kairos.recientes': ['8', '9'],
      'kairos.progreso': '[{"id":4,"p":60,"d":3000,"t":${_ms(DateTime.now())}}]',
    });
    final servidor = _Servidor();
    final biblioteca = Biblioteca(api: servidor, cuenta: 'c1');
    await biblioteca.cargar();
    expect(servidor.favoritos, {'c:3'});
    expect(servidor.progresos.keys, [4]);
    expect(biblioteca.recientes, [8, 9]);
    expect(biblioteca.ultimoCanal, 8);
    final preferencias = await SharedPreferences.getInstance();
    expect(preferencias.getStringList('kairos.mi_lista'), isNull); // una sola vez
    biblioteca.dispose();
  });

  test('el último canal para "volver al abrir" es el de este aparato', () async {
    final servidor = _Servidor()..recientes[20] = {'id': 20, 't': _ms(DateTime.now()), 'aparato': 'Celular'};
    final biblioteca = Biblioteca(api: servidor, cuenta: 'c1');
    await biblioteca.cargar();
    expect(biblioteca.recientes, [20]); // en "Últimos canales vistos", sí
    expect(biblioteca.ultimoCanal, isNull); // pero la TV no arranca en lo que se vio en el celular
    biblioteca.registrarCanalVisto(21);
    expect(biblioteca.ultimoCanal, 21);
    expect(biblioteca.recientes, [21, 20]);
    biblioteca.dispose();
  });

  test('"Seguir acá": lo último que se miró en otro aparato', () async {
    final hace10 = DateTime.now().subtract(const Duration(minutes: 10));
    final servidor = _Servidor()
      ..progresos[5] = {'id': 5, 'p': 2580, 'd': 5400, 't': _ms(hace10), 'aparato': 'Celular de Ana'}
      ..recientes[3] = {'id': 3, 't': _ms(hace10.subtract(const Duration(minutes: 30))), 'aparato': 'Celular de Ana'};
    final biblioteca = Biblioteca(api: servidor, cuenta: 'c1');
    await biblioteca.cargar();
    final seguir = biblioteca.seguirDeOtroAparato!;
    expect(
      (seguir.id, seguir.aparato, seguir.progreso!.posicion),
      (5, 'Celular de Ana', const Duration(seconds: 2580)),
    );

    biblioteca.descartarSeguir(seguir);
    expect(biblioteca.seguirDeOtroAparato, isNull);
    biblioteca.dispose();

    // Ni lo de este aparato, ni lo viejo, ni si después ya se miró algo acá
    // (otro momento: lo descartado recién queda descartado en este aparato)
    final otra = Biblioteca(
      api: _Servidor()..progresos[5] = {...servidor.progresos[5]!, 't': _ms(DateTime.now()) - 60000},
      cuenta: 'c2',
    );
    await otra.cargar();
    expect(otra.seguirDeOtroAparato, isNotNull);
    otra.registrarCanalVisto(9);
    expect(otra.seguirDeOtroAparato, isNull);
    otra.dispose();
    final vieja = Biblioteca(
      api: _Servidor()
        ..progresos[5] = {
          'id': 5,
          'p': 10,
          'd': 5400,
          't': _ms(DateTime.now().subtract(const Duration(hours: 8))),
          'aparato': 'Celular',
        },
      cuenta: 'c3',
    );
    await vieja.cargar();
    expect(vieja.seguirDeOtroAparato, isNull);
    vieja.dispose();
  });
}
