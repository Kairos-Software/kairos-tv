/// El estado de la sesión: ¿hay alguien logueado? ¿quién?
///
/// Es el equivalente a `request.user` de Django, pero del lado de la app.
/// Cuando cambia (alguien entra o sale), avisa y la app redibuja lo que
/// corresponde: el login o las pantallas del sistema.
///
/// Hay dos tipos de sesión:
///   - CLIENTE: entra con su código de 8 números (los que miran la TV).
///     Su token empieza con "c_". Solo ve los canales.
///   - USUARIO del panel (administrador, revendedor): usuario y contraseña.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api/cliente.dart';
import 'aparato.dart';
import 'api/modelos.dart';
import 'config.dart';
import 'movil/copia_catalogo.dart';

enum EstadoSesion { cargando, sinConexion, sinSesion, sinServicio, conSesion }

class Sesion extends ChangeNotifier {
  /// Guarda el token cifrado en el celular (en el Keystore de Android), no en texto plano.
  final FlutterSecureStorage _almacen = const FlutterSecureStorage();
  static const _claveToken = 'token';

  /// Las versiones viejas guardaban acá un servidor elegido a mano: ya no se usa (se borra).
  static const _claveServidorViejo = 'servidor';

  /// El último código con el que entró un cliente en este aparato. NO se
  /// borra al cerrar sesión: el login lo muestra ya escrito (por si lo olvida).
  static const _claveUltimoCodigo = 'ultimo_codigo';
  String ultimoCodigo = '';

  /// Copia del token y del código en las preferencias de la app (privadas, no
  /// cifradas). Si el aparato pierde el almacén seguro (la clave de Android
  /// falla y el almacén se vacía solo: resetOnError), la sesión sigue igual y
  /// no hace falta volver a poner el código ni ocupar otra pantalla. El token
  /// se puede liberar desde el panel y la copia se borra al cerrar sesión.
  static const _copiaToken = 'sesion_token';
  static const _copiaCodigo = 'sesion_ultimo_codigo';

  /// Cada cuánto el cliente le avisa al servidor "sigo acá". El servidor
  /// libera la pantalla si no recibe señales en 2 horas: con esto, una TV
  /// en uso nunca se libera.
  static const _cadaCuantoSenal = Duration(minutes: 5);

  late final ApiCliente api = ApiCliente(
    urlBase: urlServidor,
    alPerderSesion: _sesionPerdida,
    alPerderServicio: _servicioPerdido,
  );

  EstadoSesion estado = EstadoSesion.cargando;

  /// El usuario del panel (null si es un cliente).
  Perfil? perfil;

  /// El cliente que mira la TV (null si es un usuario del panel).
  DatosCliente? cliente;

  String? errorConexion;

  /// Por qué no puede ver (servicio vencido o suspendido) y a quién pedirle la renovación.
  String? motivoSinServicio;
  Vendedor vendedorSinServicio = Vendedor(null);

  /// El código con el que se intentó entrar y el servicio estaba vencido:
  /// "Volver a intentar" lo vuelve a probar sin tener que escribirlo.
  String? _codigoSinServicio;

  /// Por qué se volvió al login sin que nadie cerrara la sesión: la app quiso
  /// volver a entrar sola ([_volverAEntrar]) y el servidor no la dejó (ej:
  /// cuenta en uso). El login lo muestra una vez.
  ApiError? avisoParaElLogin;

  /// La vuelta a entrar en curso: si fallan varios pedidos juntos, se intenta una sola vez.
  Future<void>? _volviendo;

  Timer? _senal;

  /// Se llama al cerrar la sesión, para volver a la primera pantalla (ver main.dart).
  VoidCallback? alSalir;

  bool get esCliente => (api.token ?? '').startsWith('c_');

  /// De quién es lo guardado en este aparato (favoritos, "Continuar
  /// viendo"...: ver Biblioteca): el código con que entró el cliente (el
  /// suyo o el propio de una pantalla) o el usuario del panel.
  String get cuenta => esCliente ? 'c$ultimoCodigo' : 'u${perfil?.username ?? ''}';

  /// Al abrir la app: ¿quedó una sesión guardada de la vez anterior?
  Future<void> iniciar() async {
    // El servidor es siempre el de esta versión de la app (config.dart)
    try {
      await _almacen.delete(key: _claveServidorViejo);
    } catch (_) {
      // Si el almacén falla, se sigue con la copia (ver abajo)
    }
    api.token = await _recuperar(_claveToken, _copiaToken);
    ultimoCodigo = await _recuperar(_claveUltimoCodigo, _copiaCodigo) ?? '';
    if (api.token == null) {
      _cambiar(EstadoSesion.sinSesion);
      return;
    }
    await reintentar();
  }

  /// Vuelve a pedir los datos con el token guardado (al abrir la app, o tras un error).
  Future<void> reintentar() async {
    if (api.token == null) {
      // Venía de un código vencido (todavía no entró): se prueba ese código de nuevo
      final codigo = _codigoSinServicio;
      if (codigo == null) return _cambiar(EstadoSesion.sinSesion);
      _cambiar(EstadoSesion.cargando);
      try {
        await ingresarConCodigo(codigo);
      } on ApiError catch (error) {
        if (!error.sinServicio) _cambiar(EstadoSesion.sinSesion);
      }
      return;
    }
    _cambiar(EstadoSesion.cargando);
    try {
      if (esCliente) {
        cliente = DatosCliente(await api.get('cliente/') as Map<String, dynamic>);
        _empezarSenal();
      } else {
        perfil = Perfil(await api.get('perfil/') as Map<String, dynamic>);
      }
      _cambiar(EstadoSesion.conSesion);
    } on ApiError catch (error) {
      if (error.sinServicio) {
        _servicioPerdido(error);
      } else if (error.sesionVencida) {
        if (!await _volverAEntrar()) await _olvidarSesion();
      } else {
        // Sin conexión o cualquier otro problema del servidor: la sesión sigue
        // siendo buena. Solo un 401 dice que el token ya no vale.
        errorConexion = error.detalle;
        _cambiar(EstadoSesion.sinConexion);
      }
    }
  }

  /// El servidor ya no reconoce el token del cliente (401). Casi siempre es
  /// porque el aparato pasó más de 2 horas sin dar señales (la TV apagada, la
  /// app en segundo plano) y el servidor liberó su pantalla. Antes eso mandaba
  /// al login justo al abrir la app o después de actualizarla, y borraba el
  /// catálogo guardado (había que bajarlo entero otra vez). Ahora vuelve a
  /// entrar sola con el último código, como si se tocara "Ingresar": si hay
  /// una pantalla libre, sigue todo como estaba.
  ///
  /// Devuelve false si no se pudo y hay que cerrar la sesión (no hay código,
  /// o el servidor no lo deja entrar: cuenta en uso, código dado de baja...);
  /// lo que dijo el servidor queda en [avisoParaElLogin].
  Future<bool> _volverAEntrar() async {
    final codigo = ultimoCodigo;
    if (!esCliente || codigo.length != 8) return false;
    // El token viejo ya no vale: si se manda, el servidor rechaza también el login
    api.token = null;
    try {
      await ingresarConCodigo(codigo);
      return true;
    } on ApiError catch (error) {
      if (error.sinConexion || error.status >= 500) {
        // "Reintentar" vuelve a probar el código (_codigoSinServicio)
        errorConexion = error.detalle;
        _cambiar(EstadoSesion.sinConexion);
        return true;
      }
      // Vencido o suspendido: ya muestra "Tu servicio venció" (_servicioPerdido)
      if (error.sinServicio) return true;
      avisoParaElLogin = error;
      return false;
    }
  }

  /// Usuario del panel: usuario (o email) y contraseña.
  Future<void> ingresar(String usuario, String password) async {
    final datos = await api.post('login/', {
      'username': usuario,
      'password': password,
      'dispositivo': Aparato.nombre,
    }) as Map<String, dynamic>;
    await _guardarToken(datos['token'] as String);
    perfil = Perfil(datos['usuario'] as Map<String, dynamic>);
    _cambiar(EstadoSesion.conSesion);
  }

  /// Cliente: su código de 8 números.
  Future<void> ingresarConCodigo(String codigo) async {
    _codigoSinServicio = codigo;
    final datos =
        await api.post('cliente/login/', {'codigo': codigo, 'dispositivo': Aparato.nombre}) as Map<String, dynamic>;
    _codigoSinServicio = null;
    await _guardarToken(datos['token'] as String);
    ultimoCodigo = codigo.replaceAll(RegExp(r'\D'), '');
    await _guardar(_claveUltimoCodigo, _copiaCodigo, ultimoCodigo);
    cliente = DatosCliente(datos['cliente'] as Map<String, dynamic>);
    _empezarSenal();
    _cambiar(EstadoSesion.conSesion);
  }

  Future<void> salir() async {
    try {
      await api.post(esCliente ? 'cliente/logout/' : 'logout/');
    } on ApiError {
      // Aunque el servidor no responda, en el aparato la sesión se cierra igual
    }
    await _olvidarSesion();
  }

  /// Después de editar mis datos o cambiar la contraseña.
  Future<void> recargarPerfil() async {
    perfil = Perfil(await api.get('perfil/') as Map<String, dynamic>);
    notifyListeners();
  }

  void actualizarPerfil(Perfil nuevo) {
    perfil = nuevo;
    notifyListeners();
  }

  Future<void> _guardarToken(String token) async {
    api.token = token;
    await _guardar(_claveToken, _copiaToken, token);
  }

  /// Guarda en el almacén seguro y en la copia. Con que ande uno, alcanza.
  Future<void> _guardar(String clave, String copia, String valor) async {
    try {
      await _almacen.write(key: clave, value: valor);
    } catch (_) {
      // Queda la copia
    }
    try {
      await (await SharedPreferences.getInstance()).setString(copia, valor);
    } catch (_) {
      // Queda el almacén seguro
    }
  }

  /// Lee del almacén seguro y, si no está, de la copia. Deja los dos iguales:
  /// la primera vez que abre esta versión, crea la copia.
  Future<String?> _recuperar(String clave, String copia) async {
    String? seguro;
    try {
      seguro = await _almacen.read(key: clave);
    } catch (_) {
      // Se sigue con la copia
    }
    String? copiado;
    try {
      copiado = (await SharedPreferences.getInstance()).getString(copia);
    } catch (_) {
      // Se sigue con el almacén seguro
    }
    final valor = seguro ?? copiado;
    if (valor != null && (seguro == null || copiado != valor)) await _guardar(clave, copia, valor);
    return valor;
  }

  /// La "señal" del cliente: mantiene ocupada su pantalla y trae su estado
  /// (si venció o lo suspendieron, el cliente HTTP avisa con _servicioPerdido;
  /// si liberaron el dispositivo, con _sesionPerdida).
  void _empezarSenal() {
    _senal?.cancel();
    _senal = Timer.periodic(_cadaCuantoSenal, (_) async {
      try {
        cliente = DatosCliente(await api.get('cliente/') as Map<String, dynamic>);
        notifyListeners();
      } on ApiError {
        // Sin conexión un rato: no pasa nada, se reintenta en la próxima señal
      }
    });
  }

  /// El servidor dijo 401: el token venció o lo cerraron (desde la web, o liberaron el dispositivo).
  /// Un cliente mirando vuelve a entrar solo (ej: la primera señal al volver de horas en segundo plano).
  void _sesionPerdida() {
    if (estado == EstadoSesion.conSesion && esCliente) {
      _volviendo ??= _volverAEntrar()
          .then((entro) async {
            if (!entro) await _olvidarSesion();
          })
          .whenComplete(() => _volviendo = null);
    } else if (estado == EstadoSesion.conSesion || estado == EstadoSesion.sinServicio) {
      _olvidarSesion();
    }
  }

  /// El cliente se quedó sin servicio. El token se guarda: cuando renueve,
  /// "Reintentar" lo deja seguir sin volver a poner el código.
  void _servicioPerdido(ApiError error) {
    motivoSinServicio = error.detalle;
    vendedorSinServicio = Vendedor(error.extra['vendedor']);
    if (api.token != null) _codigoSinServicio = null;
    _senal?.cancel();
    if (estado != EstadoSesion.sinServicio) {
      _cambiar(EstadoSesion.sinServicio);
      alSalir?.call();
    }
  }

  Future<void> _olvidarSesion() async {
    _senal?.cancel();
    _codigoSinServicio = null;
    api.token = null;
    perfil = null;
    cliente = null;
    try {
      await _almacen.delete(key: _claveToken);
    } catch (_) {
      // Lo importante es la copia: sin las dos, no vuelve a entrar sola
    }
    try {
      await (await SharedPreferences.getInstance()).remove(_copiaToken);
    } catch (_) {
      // Sin preferencias tampoco hay copia que borrar
    }
    // El catálogo guardado tiene las direcciones de los videos: no queda en el aparato
    unawaited(CopiaCatalogo.borrarTodo());
    _cambiar(EstadoSesion.sinSesion);
    alSalir?.call();
  }

  void _cambiar(EstadoSesion nuevo) {
    estado = nuevo;
    notifyListeners();
  }

  @override
  void dispose() {
    _senal?.cancel();
    super.dispose();
  }
}

/// Deja la sesión disponible para todas las pantallas:  `SesionScope.of(context)`.
class SesionScope extends InheritedNotifier<Sesion> {
  const SesionScope({super.key, required Sesion sesion, required super.child}) : super(notifier: sesion);

  /// Para usar en `build`: la pantalla se redibuja cuando la sesión cambia.
  static Sesion of(BuildContext context) => context.dependOnInheritedWidgetOfExactType<SesionScope>()!.notifier!;

  /// Para usar en botones y funciones (no redibuja).
  static Sesion leer(BuildContext context) => context.getInheritedWidgetOfExactType<SesionScope>()!.notifier!;
}
