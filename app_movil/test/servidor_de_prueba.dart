// Para los servidores de mentira de las pruebas (los que contestan `get`).
import 'dart:convert';

import 'package:app_movil/api/cliente.dart';

/// El catálogo se pide con [ApiCliente.getCrudo] (la respuesta tal cual, con
/// su huella). Con esto, un servidor de prueba que contesta `get` lo contesta
/// igual, sin huella (siempre "cambió"). Los errores que tira `get` salen igual.
mixin CrudoDesdeGet on ApiCliente {
  @override
  Future<({List<int>? bytes, String huella})> getCrudo(
    String ruta, {
    Map<String, String>? parametros,
    String huella = '',
  }) async => (bytes: utf8.encode(jsonEncode(await get(ruta, parametros: parametros))), huella: '');
}
