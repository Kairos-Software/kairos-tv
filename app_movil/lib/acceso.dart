/// Las pantallas de antes de entrar (diseno_kairos_tv: tv-01..03, tv-17,
/// tv-22 y mobile-01..03, 07, 10). Las mismas en celular y TV: con pantalla
/// ancha se parten en dos columnas.
///
///   PantallaAcceso         el código del cliente con su teclado numérico (lo
///                          principal) y, aparte, usuario y contraseña del panel
///                          (en la TV, con un teclado en la pantalla: ver [_TecladoTexto]).
///   PantallaServicioVencido  a quién pedirle la renovación y "volver a intentar".
///   PantallaCarga          mientras arranca.
///   PantallaSinConexion    el servidor no responde.
library;

import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'actualizacion.dart';
import 'api/cliente.dart';
import 'aparato.dart';
import 'config.dart';
import 'marca.dart';
import 'movil/estilo.dart';
import 'sesion.dart';
import 'tv/foco.dart';

/// El fondo de estas pantallas: grafito con una luz celeste arriba a la izquierda.
class _Fondo extends StatelessWidget {
  const _Fondo({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Theme(
      data: temaMovil(),
      child: Scaffold(
        backgroundColor: Tono.fondo,
        body: DecoratedBox(
          decoration: const BoxDecoration(
            gradient: RadialGradient(
              center: Alignment(-.75, -.85),
              radius: 1.1,
              colors: [Color(0xFF0B2A30), Tono.fondo],
            ),
          ),
          child: SafeArea(child: child),
        ),
      ),
    );
  }
}

bool _esAncha(BuildContext context) => MediaQuery.sizeOf(context).width >= 900;

// ── Login ──────────────────────────────────────────────────────────

class PantallaAcceso extends StatefulWidget {
  const PantallaAcceso({super.key});

  @override
  State<PantallaAcceso> createState() => _PantallaAccesoState();
}

class _PantallaAccesoState extends State<PantallaAcceso> {
  static const _largoCodigo = 8;

  String _codigo = '';
  bool _conCodigo = true;
  bool _enviando = false;
  ApiError? _error;

  final _usuario = TextEditingController();
  final _password = TextEditingController();
  bool _verPassword = false;

  /// Lo que pasó al tocar "Buscar actualización" (null = nada que mostrar).
  String? _estadoVersion;

  // En la TV, usuario y contraseña NO son campos de texto de Android: con el
  // control quedaban trabados (las flechas movían el cursor y no se podía
  // salir) y cada TV abre un teclado distinto. Se escribe con el teclado de la
  // pantalla, como en Buscar, en el campo elegido.
  bool _enPassword = false;
  bool _mayusculas = false;
  bool _simbolos = false;
  final _primeraTecla = FocusNode(debugLabel: 'teclado del login');

  @override
  void initState() {
    super.initState();
    final sesion = SesionScope.leer(context);
    // El último código usado en este aparato, ya escrito (por si el cliente lo olvidó)
    _codigo = sesion.ultimoCodigo;
    // La app quiso volver a entrar sola y el servidor no la dejó: por qué
    _error = sesion.avisoParaElLogin;
    sesion.avisoParaElLogin = null;
  }

  @override
  void dispose() {
    _usuario.dispose();
    _password.dispose();
    _primeraTecla.dispose();
    super.dispose();
  }

  void _tecla(String digito) {
    if (_codigo.length >= _largoCodigo) return;
    setState(() {
      _codigo += digito;
      _error = null;
    });
  }

  void _borrar() {
    if (_codigo.isEmpty) return;
    setState(() {
      _codigo = _codigo.substring(0, _codigo.length - 1);
      _error = null;
    });
  }

  void _irAlPanel() {
    setState(() {
      _conCodigo = false;
      _enPassword = false;
      _error = null;
    });
    // En la TV el foco va directo al teclado de la pantalla
    if (Aparato.esTv) WidgetsBinding.instance.addPostFrameCallback((_) => _primeraTecla.requestFocus());
  }

  void _volverAlCodigo() {
    setState(() {
      _conCodigo = true;
      _error = null;
    });
  }

  TextEditingController get _campoActivo => _enPassword ? _password : _usuario;

  void _escribirTv(String letra) {
    final campo = _campoActivo;
    if (campo.text.length >= 150) return;
    setState(() {
      campo.text += letra;
      _error = null;
    });
  }

  void _borrarTv() {
    final campo = _campoActivo;
    if (campo.text.isEmpty) return;
    setState(() => campo.text = campo.text.substring(0, campo.text.length - 1));
  }

  void _limpiarTv() => setState(() => _campoActivo.text = '');

  /// "Siguiente": del usuario pasa a la contraseña; en la contraseña, entra.
  void _siguienteTv() {
    if (_enPassword) {
      _ingresar();
    } else {
      setState(() => _enPassword = true);
    }
  }

  /// Elegir un campo (OK sobre él): se escribe ahí y el foco baja al teclado.
  void _elegirCampoTv(bool password) {
    setState(() => _enPassword = password);
    _primeraTecla.requestFocus();
  }

  Future<void> _ingresar() async {
    if (_enviando) return;
    if (_conCodigo && _codigo.length < _largoCodigo) {
      setState(
        () => _error = ApiError(status: 400, codigo: 'codigo_corto', detalle: 'Faltan números: son 8 en total.'),
      );
      return;
    }
    // Cierra el teclado de Android (usuario y contraseña en el celular). Con el
    // código no hay teclado que cerrar, y en la TV sacar el foco dejaba la
    // pantalla sin nada elegido si el ingreso fallaba: ni las flechas ni los
    // números del control volvían a escribir.
    if (!_conCodigo && !Aparato.esTv) FocusManager.instance.primaryFocus?.unfocus();
    setState(() {
      _enviando = true;
      _error = null;
    });
    try {
      final sesion = SesionScope.leer(context);
      if (_conCodigo) {
        await sesion.ingresarConCodigo(_codigo);
      } else {
        await sesion.ingresar(_usuario.text.trim(), _password.text);
      }
      // No hace falta navegar: la sesión avisa y main.dart muestra lo que corresponde
    } on ApiError catch (error) {
      if (mounted) setState(() => _error = error);
    } finally {
      if (mounted) setState(() => _enviando = false);
    }
  }

  /// Los números y "borrar" del control remoto o del teclado también escriben
  /// el código. En el panel de la TV, un teclado enchufado escribe en el campo.
  KeyEventResult _teclaFisica(FocusNode _, KeyEvent evento) {
    if (evento is KeyUpEvent) return KeyEventResult.ignored;
    if (!_conCodigo) {
      if (!Aparato.esTv) return KeyEventResult.ignored;
      if (evento.logicalKey == LogicalKeyboardKey.backspace) {
        _borrarTv();
        return KeyEventResult.handled;
      }
      final caracter = evento.character;
      if (caracter != null && caracter.length == 1 && caracter.codeUnitAt(0) > 32) {
        _escribirTv(caracter);
        return KeyEventResult.handled;
      }
      return KeyEventResult.ignored;
    }
    final caracter = evento.character;
    if (caracter != null && RegExp(r'^\d$').hasMatch(caracter)) {
      _tecla(caracter);
      return KeyEventResult.handled;
    }
    final tecla = evento.logicalKey;
    final numero = _numerosDelControl[tecla];
    if (numero != null) {
      _tecla(numero);
      return KeyEventResult.handled;
    }
    if (tecla == LogicalKeyboardKey.backspace || tecla == LogicalKeyboardKey.delete) {
      _borrar();
      return KeyEventResult.handled;
    }
    return KeyEventResult.ignored;
  }

  @override
  Widget build(BuildContext context) {
    final ancha = _esAncha(context);
    final tarjeta = _conCodigo ? _tarjetaCodigo(ancha) : _tarjetaPanel(ancha);
    return PopScope(
      // "Atrás": en el panel vuelve al código; con el código escrito, borra un número
      canPop: _conCodigo && _codigo.isEmpty,
      onPopInvokedWithResult: (salio, _) {
        if (salio) return;
        if (!_conCodigo) {
          _volverAlCodigo();
        } else {
          _borrar();
        }
      },
      child: _Fondo(
        child: Focus(
          onKeyEvent: _teclaFisica,
          child: ancha
              ? Row(
                  children: [
                    const Expanded(flex: 46, child: _Bienvenida()),
                    Expanded(
                      flex: 54,
                      child: Center(
                        child: SingleChildScrollView(
                          padding: const EdgeInsets.symmetric(horizontal: 56, vertical: 32),
                          child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 720), child: tarjeta),
                        ),
                      ),
                    ),
                  ],
                )
              : Center(
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.fromLTRB(22, 32, 22, 24),
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 420),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          const Center(child: SimboloKairos(tamanio: 56)),
                          const SizedBox(height: 40),
                          tarjeta,
                        ],
                      ),
                    ),
                  ),
                ),
        ),
      ),
    );
  }

  /// "Buscar actualización" en el mismo login: si una versión trae un error
  /// que impide entrar, desde acá se puede bajar la que lo arregla.
  Future<void> _buscarActualizacion() async {
    setState(() => _estadoVersion = 'Buscando…');
    final hay = await VigilarActualizacion.buscarAhora(context);
    if (!mounted) return;
    setState(() {
      _estadoVersion = switch (hay) {
        true => null, // ya se mostró el cartel "Hay una versión nueva"
        false => 'Ya tenés la última versión.',
        null => 'No se pudo consultar. Revisá la conexión.',
      };
    });
  }

  Widget _actualizacion(bool ancha) {
    final version = Aparato.version.isEmpty ? '' : ' · versión ${Aparato.version}';
    return Column(
      children: [
        Center(
          child: BotonTv(
            texto: 'Buscar actualización$version',
            icono: Icons.system_update_rounded,
            alOk: _estadoVersion == 'Buscando…' ? null : _buscarActualizacion,
            alto: ancha ? 46 : 40,
            tamanioTexto: ancha ? 15 : 13,
          ),
        ),
        if (_estadoVersion != null) ...[
          const SizedBox(height: 8),
          Text(
            _estadoVersion!,
            textAlign: TextAlign.center,
            style: const TextStyle(color: Tono.textoSuave),
          ),
        ],
      ],
    );
  }

  /// Solo en la versión local ("Kairos TV Local"): a qué PC se conecta, para no confundirla con la de producción.
  Widget _servidor() {
    if (!esVersionLocal) return const SizedBox.shrink();
    return const Center(
      child: Padding(
        padding: EdgeInsets.only(top: 8),
        child: Text(
          'VERSIÓN LOCAL · $urlServidor',
          style: TextStyle(color: Tono.dorado, fontSize: 12, fontWeight: FontWeight.w700),
          overflow: TextOverflow.ellipsis,
        ),
      ),
    );
  }

  Widget _tarjetaCodigo(bool ancha) {
    final contenido = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('ACCESO DE CLIENTES', style: LetraTv.sobretitulo.copyWith(fontSize: ancha ? 14 : 13)),
        const SizedBox(height: 8),
        Text('Ingresá tu código', style: ancha ? LetraTv.pantalla.copyWith(fontSize: 40) : _tituloCelular),
        const SizedBox(height: 4),
        Text(
          ancha ? 'Escribí los 8 números que te dio tu vendedor.' : 'Los 8 números que te dio tu vendedor.',
          style: ancha ? LetraTv.cuerpo : Letra.cuerpo,
        ),
        const SizedBox(height: 24),
        _Visor(codigo: _codigo, largo: _largoCodigo, grande: ancha),
        if (_error != null) ...[const SizedBox(height: 14), _CartelError(_error!)],
        SizedBox(height: ancha ? 22 : 18),
        _TecladoNumerico(
          alTecla: _tecla,
          alBorrar: _borrar,
          alOk: _ingresar,
          enviando: _enviando,
          alto: ancha ? 72 : 56,
        ),
        if (ancha) ...[
          const SizedBox(height: 18),
          const Text(
            '← ↑ ↓ → para moverte · OK para elegir · también podés usar los números del control',
            textAlign: TextAlign.center,
            style: LetraTv.ayuda,
          ),
          const SizedBox(height: 18),
          const Divider(color: Tono.capaMaxima),
        ],
        const SizedBox(height: 18),
        BotonTv(
          texto: ancha ? 'Ingresar como revendedor o administrador' : 'Revendedores / administradores',
          alOk: _irAlPanel,
          ancho: double.infinity,
          tamanioTexto: ancha ? 17 : 15,
          alto: ancha ? 58 : 52,
        ),
        const SizedBox(height: 12),
        _servidor(),
        const SizedBox(height: 4),
        _actualizacion(ancha),
      ],
    );
    return ancha ? _Panel(child: contenido) : contenido;
  }

  Widget _tarjetaPanel(bool ancha) {
    if (Aparato.esTv) return _tarjetaPanelTv();
    final error = _error;
    final errorDeCampo = error?.campo('username') ?? error?.campo('password');
    final contenido = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('ACCESO SECUNDARIO', style: LetraTv.sobretitulo.copyWith(fontSize: ancha ? 14 : 13)),
        const SizedBox(height: 8),
        Text('Revendedores y administradores', style: ancha ? LetraTv.pantalla.copyWith(fontSize: 36) : _tituloCelular),
        const SizedBox(height: 4),
        Text('Ingresá con tu cuenta del panel.', style: ancha ? LetraTv.cuerpo : Letra.cuerpo),
        const SizedBox(height: 24),
        if (error != null && errorDeCampo == null) ...[_CartelError(error), const SizedBox(height: 14)],
        _Campo(
          control: _usuario,
          texto: 'Usuario o email',
          autofocus: true,
          error: error?.campo('username'),
          teclado: TextInputType.emailAddress,
          accion: TextInputAction.next,
        ),
        const SizedBox(height: 14),
        _Campo(
          control: _password,
          texto: 'Contraseña',
          oculto: !_verPassword,
          error: error?.campo('password'),
          accion: TextInputAction.done,
          alEnviar: _ingresar,
          sufijo: IconButton(
            tooltip: _verPassword ? 'Ocultar' : 'Mostrar',
            icon: Icon(_verPassword ? Icons.visibility_off_rounded : Icons.visibility_rounded, color: Tono.textoSuave),
            onPressed: () => setState(() => _verPassword = !_verPassword),
          ),
        ),
        const SizedBox(height: 22),
        BotonTv(
          texto: _enviando ? 'Ingresando…' : 'Ingresar',
          principal: true,
          alOk: _ingresar,
          ancho: double.infinity,
          alto: ancha ? 58 : 52,
        ),
        const SizedBox(height: 12),
        BotonTv(
          texto: 'Volver al código de cliente',
          alOk: _volverAlCodigo,
          ancho: double.infinity,
          alto: ancha ? 58 : 52,
          tamanioTexto: ancha ? 17 : 15,
        ),
        const SizedBox(height: 12),
        _servidor(),
      ],
    );
    return ancha ? _Panel(child: contenido) : contenido;
  }

  /// Usuario y contraseña en la TV: los dos campos (se eligen con las flechas)
  /// y el teclado de la pantalla. Atrás vuelve al código.
  Widget _tarjetaPanelTv() {
    final error = _error;
    final errorUsuario = error?.campo('username');
    final errorPassword = error?.campo('password');
    return _Panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('ACCESO SECUNDARIO', style: LetraTv.sobretitulo.copyWith(fontSize: 14)),
          const SizedBox(height: 6),
          Text('Revendedores y administradores', style: LetraTv.pantalla.copyWith(fontSize: 32)),
          const SizedBox(height: 18),
          if (error != null && errorUsuario == null && errorPassword == null) ...[
            _CartelError(error),
            const SizedBox(height: 14),
          ],
          FocusTraversalGroup(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _CampoTv(
                  titulo: 'Usuario',
                  vacio: 'Usuario o email',
                  valor: _usuario.text,
                  activo: !_enPassword,
                  error: errorUsuario,
                  alActivar: () => setState(() => _enPassword = false),
                  alElegir: () => _elegirCampoTv(false),
                ),
                const SizedBox(height: 12),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: _CampoTv(
                        titulo: 'Contraseña',
                        vacio: 'Tu contraseña',
                        valor: _verPassword ? _password.text : '•' * _password.text.length,
                        activo: _enPassword,
                        error: errorPassword,
                        alActivar: () => setState(() => _enPassword = true),
                        alElegir: () => _elegirCampoTv(true),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Enfocable(
                      alOk: () => setState(() => _verPassword = !_verPassword),
                      curva: Curva.boton,
                      escala: 1.06,
                      etiqueta: _verPassword ? 'Ocultar contraseña' : 'Mostrar contraseña',
                      child: Container(
                        width: 66,
                        height: 66,
                        decoration: BoxDecoration(
                          color: Tono.capaAlta,
                          borderRadius: BorderRadius.circular(Curva.boton),
                          border: Border.all(color: Tono.bordeSuave.withValues(alpha: .6)),
                        ),
                        child: Icon(
                          _verPassword ? Icons.visibility_off_rounded : Icons.visibility_rounded,
                          color: Tono.textoSuave,
                          size: 28,
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(height: 18),
          _TecladoTexto(
            primeraTecla: _primeraTecla,
            mayusculas: _mayusculas,
            simbolos: _simbolos,
            enPassword: _enPassword,
            enviando: _enviando,
            alLetra: _escribirTv,
            alBorrar: _borrarTv,
            alLimpiar: _limpiarTv,
            alMayusculas: () => setState(() => _mayusculas = !_mayusculas),
            alSimbolos: () => setState(() => _simbolos = !_simbolos),
            alSiguiente: _siguienteTv,
          ),
          const SizedBox(height: 12),
          const Text(
            '↑ elegí el campo · OK escribe · mantené OK en Borrar para limpiar · Atrás vuelve',
            textAlign: TextAlign.center,
            style: LetraTv.ayuda,
          ),
          const SizedBox(height: 14),
          BotonTv(texto: 'Volver al código de cliente', alOk: _volverAlCodigo, ancho: double.infinity, alto: 54),
        ],
      ),
    );
  }
}

/// Un campo del login en la TV: no es un campo de texto, muestra lo escrito
/// con el teclado de la pantalla. El que está [activo] (borde celeste y
/// cursor) es donde se escribe; al pasarle el foco encima pasa a ser el activo.
class _CampoTv extends StatelessWidget {
  const _CampoTv({
    required this.titulo,
    required this.vacio,
    required this.valor,
    required this.activo,
    required this.alActivar,
    required this.alElegir,
    this.error,
  });

  final String titulo;
  final String vacio;
  final String valor;
  final bool activo;

  /// Al pasar con el foco: pasa a ser donde se escribe.
  final VoidCallback alActivar;

  /// OK sobre el campo: además, el foco baja al teclado.
  final VoidCallback alElegir;
  final String? error;

  @override
  Widget build(BuildContext context) {
    final colorBorde = error != null ? Tono.rubi : (activo ? Tono.celeste : Tono.bordeSuave.withValues(alpha: .6));
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Enfocable(
          alOk: alElegir,
          alEnfocar: (enfocado) {
            if (enfocado && !activo) alActivar();
          },
          curva: Curva.boton,
          escala: 1.02,
          etiqueta: titulo,
          child: Container(
            height: 66,
            padding: const EdgeInsets.symmetric(horizontal: 22),
            decoration: BoxDecoration(
              color: Tono.capaMinima,
              borderRadius: BorderRadius.circular(Curva.boton),
              border: Border.all(color: colorBorde, width: activo ? 2 : 1),
            ),
            child: Row(
              children: [
                SizedBox(
                  width: 128,
                  child: Text(
                    titulo,
                    style: TextStyle(
                      fontFamily: Letra.texto,
                      fontSize: 15,
                      fontWeight: FontWeight.w700,
                      color: activo ? Tono.celesteClaro : Tono.textoApagado,
                    ),
                  ),
                ),
                Flexible(
                  child: Text(
                    valor.isEmpty ? vacio : valor,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontFamily: Letra.texto,
                      fontSize: 21,
                      color: valor.isEmpty ? Tono.textoApagado : Tono.texto,
                    ),
                  ),
                ),
                if (activo)
                  Container(width: 2, height: 28, margin: const EdgeInsets.only(left: 2), color: Tono.celeste),
              ],
            ),
          ),
        ),
        if (error != null)
          Padding(
            padding: const EdgeInsets.only(left: 6, top: 6),
            child: Text(
              error!,
              style: const TextStyle(fontFamily: Letra.texto, fontSize: 14, color: Tono.rubiClaro),
            ),
          ),
      ],
    );
  }
}

/// El teclado de la pantalla del login de la TV: números, letras (o símbolos)
/// y una fila de control: símbolos · mayúsculas · espacio · borrar (mantener
/// OK: limpia todo) · Siguiente (en la contraseña, "Ingresar").
class _TecladoTexto extends StatelessWidget {
  const _TecladoTexto({
    required this.primeraTecla,
    required this.mayusculas,
    required this.simbolos,
    required this.enPassword,
    required this.enviando,
    required this.alLetra,
    required this.alBorrar,
    required this.alLimpiar,
    required this.alMayusculas,
    required this.alSimbolos,
    required this.alSiguiente,
  });

  final FocusNode primeraTecla;
  final bool mayusculas;
  final bool simbolos;
  final bool enPassword;
  final bool enviando;
  final ValueChanged<String> alLetra;
  final VoidCallback alBorrar;
  final VoidCallback alLimpiar;
  final VoidCallback alMayusculas;
  final VoidCallback alSimbolos;
  final VoidCallback alSiguiente;

  static const _letras = ['1234567890', 'qwertyuiop', 'asdfghjklñ', 'zxcvbnm@._'];
  static const _otros = ['1234567890', r'-_!#$%&*+=', '?/:;,()<>~', r'''[]{}|\^'"`'''];

  @override
  Widget build(BuildContext context) {
    Widget tecla(
      String etiqueta,
      VoidCallback alOk, {
      String? texto,
      IconData? icono,
      int flex = 1,
      bool principal = false,
      bool prendida = false,
      FocusNode? nodo,
      VoidCallback? alOkLargo,
    }) {
      final colorTexto = principal ? Tono.sobreCelesteOscuro : (prendida ? Tono.celesteClaro : Tono.texto);
      return Expanded(
        flex: flex,
        child: Padding(
          padding: const EdgeInsets.all(4),
          child: Enfocable(
            alOk: alOk,
            alOkLargo: alOkLargo,
            nodo: nodo,
            curva: Curva.medio + 2,
            escala: 1.08,
            etiqueta: etiqueta,
            child: Container(
              height: 54,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: principal ? Tono.celeste : (prendida ? Tono.celeste.withValues(alpha: .18) : Tono.capaAlta),
                borderRadius: BorderRadius.circular(Curva.medio + 2),
                border: principal ? null : Border.all(color: Tono.bordeSuave.withValues(alpha: .45)),
              ),
              child: texto == null && icono != null
                  ? Icon(icono, color: colorTexto, size: 24)
                  : Text(
                      texto ?? etiqueta,
                      style: TextStyle(
                        fontFamily: Letra.texto,
                        fontSize: 20,
                        fontWeight: FontWeight.w700,
                        color: colorTexto,
                      ),
                    ),
            ),
          ),
        ),
      );
    }

    final filas = simbolos ? _otros : _letras;
    return FocusTraversalGroup(
      child: Column(
        children: [
          for (final (f, fila) in filas.indexed)
            Row(
              children: [
                for (final (i, caracter) in fila.split('').indexed)
                  tecla(
                    mayusculas ? caracter.toUpperCase() : caracter,
                    () => alLetra(mayusculas ? caracter.toUpperCase() : caracter),
                    nodo: f == 1 && i == 0 ? primeraTecla : null,
                  ),
              ],
            ),
          Row(
            children: [
              tecla(simbolos ? 'Letras' : 'Símbolos', alSimbolos, texto: simbolos ? 'abc' : '#+=', flex: 2),
              tecla('Mayúsculas', alMayusculas, icono: Icons.keyboard_capslock_rounded, flex: 2, prendida: mayusculas),
              tecla('Espacio', () => alLetra(' '), icono: Icons.space_bar_rounded, flex: 2),
              tecla('Borrar', alBorrar, icono: Icons.backspace_outlined, flex: 2, alOkLargo: alLimpiar),
              tecla(
                enPassword ? 'Ingresar' : 'Siguiente',
                alSiguiente,
                texto: enviando ? '…' : (enPassword ? 'Ingresar' : 'Siguiente'),
                flex: 2,
                principal: true,
              ),
            ],
          ),
        ],
      ),
    );
  }
}

const _tituloCelular = TextStyle(
  fontFamily: Letra.titulos,
  fontSize: 28,
  height: 32 / 28,
  fontWeight: FontWeight.w800,
  letterSpacing: -0.8,
  color: Tono.texto,
);

/// Las teclas numéricas del control remoto (algunos mandan estas y no el carácter).
final _numerosDelControl = {
  for (var i = 0; i <= 9; i++) LogicalKeyboardKey(LogicalKeyboardKey.digit0.keyId + i): '$i',
  for (var i = 0; i <= 9; i++) LogicalKeyboardKey(LogicalKeyboardKey.numpad0.keyId + i): '$i',
};

/// La columna izquierda del login en la TV: la marca y la frase.
class _Bienvenida extends StatelessWidget {
  const _Bienvenida();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(80, 64, 40, 64),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SimboloKairos(tamanio: 84),
          const Spacer(),
          Text('KAIROS TV', style: LetraTv.sobretitulo.copyWith(fontSize: 15)),
          const SizedBox(height: 14),
          Text(
            'Todo lo que querés ver, en el momento indicado.',
            style: LetraTv.portada.copyWith(fontSize: 60, letterSpacing: -2),
          ),
          const SizedBox(height: 22),
          const Text(
            'Canales en vivo, películas y series en una experiencia pensada para tu pantalla.',
            style: LetraTv.cuerpo,
          ),
          const Spacer(flex: 2),
        ],
      ),
    );
  }
}

/// La tarjeta de vidrio oscuro donde va el formulario (en la TV).
class _Panel extends StatelessWidget {
  const _Panel({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(Curva.portada),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
        child: Container(
          padding: const EdgeInsets.all(44),
          decoration: BoxDecoration(
            color: Tono.capaBaja.withValues(alpha: .88),
            borderRadius: BorderRadius.circular(Curva.portada),
            border: Border.all(color: Tono.bordeSuave.withValues(alpha: .5)),
          ),
          child: child,
        ),
      ),
    );
  }
}

/// Donde se ve el código: "4821 9037", con rayitas en lo que falta.
class _Visor extends StatelessWidget {
  const _Visor({required this.codigo, required this.largo, required this.grande});

  final String codigo;
  final int largo;
  final bool grande;

  @override
  Widget build(BuildContext context) {
    final estilo = TextStyle(
      fontFamily: Letra.titulos,
      fontWeight: FontWeight.w800,
      fontSize: grande ? 40 : 30,
      letterSpacing: grande ? 10 : 7,
      color: Tono.celesteClaro,
      fontFeatures: const [FontFeature.tabularFigures()],
    );
    String grupo(int desde) =>
        [for (var i = desde; i < desde + largo ~/ 2; i++) i < codigo.length ? codigo[i] : '_'].join();
    return Container(
      height: grande ? 82 : 64,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: Tono.capaMinima,
        borderRadius: BorderRadius.circular(Curva.boton),
        border: Border.all(color: Tono.bordeSuave.withValues(alpha: .6)),
      ),
      child: Semantics(
        label: 'Código: ${codigo.split('').join(' ')}',
        child: Text('${grupo(0)}  ${grupo(largo ~/ 2)}', style: estilo),
      ),
    );
  }
}

/// El teclado numérico de la pantalla (para el control remoto y el dedo).
class _TecladoNumerico extends StatelessWidget {
  const _TecladoNumerico({
    required this.alTecla,
    required this.alBorrar,
    required this.alOk,
    required this.enviando,
    required this.alto,
  });

  final ValueChanged<String> alTecla;
  final VoidCallback alBorrar;
  final VoidCallback alOk;
  final bool enviando;
  final double alto;

  @override
  Widget build(BuildContext context) {
    Widget tecla(String texto, VoidCallback alOk, {IconData? icono, bool autofocus = false, String? etiqueta}) {
      return Expanded(
        child: Padding(
          padding: const EdgeInsets.all(6),
          child: Enfocable(
            alOk: alOk,
            autofocus: autofocus,
            curva: Curva.boton,
            escala: 1.05,
            etiqueta: etiqueta ?? texto,
            child: Container(
              height: alto,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: Tono.capaAlta,
                borderRadius: BorderRadius.circular(Curva.boton),
                border: Border.all(color: Tono.bordeSuave.withValues(alpha: .45)),
              ),
              child: icono != null
                  ? Icon(icono, color: Tono.texto, size: alto * .38)
                  : Text(
                      texto,
                      style: TextStyle(
                        fontFamily: Letra.texto,
                        fontWeight: FontWeight.w700,
                        fontSize: alto * (texto.length > 1 ? .3 : .36),
                        color: Tono.texto,
                      ),
                    ),
            ),
          ),
        ),
      );
    }

    return FocusTraversalGroup(
      policy: ReadingOrderTraversalPolicy(),
      child: Column(
        children: [
          for (final fila in [
            ['1', '2', '3'],
            ['4', '5', '6'],
            ['7', '8', '9'],
          ])
            Row(children: [for (final n in fila) tecla(n, () => alTecla(n), autofocus: n == '1' && Aparato.esTv)]),
          Row(
            children: [
              tecla('Borrar', alBorrar, icono: Icons.backspace_outlined, etiqueta: 'Borrar'),
              tecla('0', () => alTecla('0')),
              tecla(enviando ? '…' : 'OK', alOk, etiqueta: 'Entrar'),
            ],
          ),
        ],
      ),
    );
  }
}

/// Un campo de texto del login del panel (usuario, contraseña).
class _Campo extends StatelessWidget {
  const _Campo({
    required this.control,
    required this.texto,
    this.autofocus = false,
    this.oculto = false,
    this.error,
    this.teclado,
    this.accion,
    this.alEnviar,
    this.sufijo,
  });

  final TextEditingController control;
  final String texto;
  final bool autofocus;
  final bool oculto;
  final String? error;
  final TextInputType? teclado;
  final TextInputAction? accion;
  final VoidCallback? alEnviar;
  final Widget? sufijo;

  @override
  Widget build(BuildContext context) {
    OutlineInputBorder borde(Color color, double ancho) => OutlineInputBorder(
      borderRadius: BorderRadius.circular(Curva.boton),
      borderSide: BorderSide(color: color, width: ancho),
    );
    return TextField(
      controller: control,
      autofocus: autofocus,
      obscureText: oculto,
      keyboardType: teclado,
      textInputAction: accion,
      autocorrect: false,
      onSubmitted: alEnviar == null ? null : (_) => alEnviar!(),
      style: const TextStyle(fontFamily: Letra.texto, fontSize: 17, color: Tono.texto),
      decoration: InputDecoration(
        hintText: texto,
        hintStyle: const TextStyle(color: Tono.textoApagado),
        errorText: error,
        filled: true,
        fillColor: Tono.capaMinima,
        contentPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 18),
        suffixIcon: sufijo,
        enabledBorder: borde(Tono.bordeSuave.withValues(alpha: .6), 1),
        focusedBorder: borde(Tono.celeste, 3),
        errorBorder: borde(Tono.rubi, 1),
        focusedErrorBorder: borde(Tono.rubi, 3),
      ),
    );
  }
}

/// Lo que salió mal al entrar: título y explicación sobre rubí (mobile-03).
class _CartelError extends StatelessWidget {
  const _CartelError(this.error);

  final ApiError error;

  (String, String) get _textos => switch (error.codigo) {
    'codigo_invalido' => ('Código incorrecto', 'Revisá los 8 números.'),
    'codigo_corto' => ('Código incompleto', error.detalle),
    'cuenta_en_uso' => ('Cuenta en uso', error.detalle),
    'login_bloqueado' || 'bloqueado' => ('Demasiados intentos', error.detalle),
    'sin_conexion' => ('Sin conexión', error.detalle),
    _ => ('No se pudo entrar', error.detalle),
  };

  @override
  Widget build(BuildContext context) {
    final (titulo, texto) = _textos;
    return Container(
      padding: const EdgeInsets.fromLTRB(18, 14, 18, 14),
      decoration: BoxDecoration(
        color: const Color(0xFF2A1219),
        borderRadius: BorderRadius.circular(Curva.boton),
        border: Border.all(color: Tono.rubi.withValues(alpha: .55)),
      ),
      child: Semantics(
        liveRegion: true,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              titulo,
              style: const TextStyle(
                fontFamily: Letra.texto,
                fontWeight: FontWeight.w700,
                fontSize: 17,
                color: Tono.rubiClaro,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              texto,
              style: const TextStyle(fontFamily: Letra.texto, fontSize: 14, color: Tono.rubiClaro),
            ),
          ],
        ),
      ),
    );
  }
}

// ── Servicio vencido ───────────────────────────────────────────────

class PantallaServicioVencido extends StatelessWidget {
  const PantallaServicioVencido({super.key});

  @override
  Widget build(BuildContext context) {
    final sesion = SesionScope.of(context);
    final vendedor = sesion.vendedorSinServicio;
    final motivo = sesion.motivoSinServicio ?? 'Tu servicio no está activo.';
    final suspendido = motivo.toLowerCase().contains('suspend');
    final ancha = _esAncha(context);
    // En la TV no hay WhatsApp: ahí se muestra el teléfono para anotarlo
    final puedeEscribir = vendedor.numeroWhatsapp.isNotEmpty && !Aparato.esTv;

    Future<void> escribir() async {
      final abierto = await Aparato.abrir(
        'https://wa.me/${vendedor.numeroWhatsapp}?text=${Uri.encodeComponent('Hola, quiero renovar mi servicio de Kairos TV.')}',
      );
      if (!abierto && context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('No se pudo abrir WhatsApp. El número es ${vendedor.telefono}.')));
      }
    }

    return _Fondo(
      child: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(28),
          child: ConstrainedBox(
            constraints: BoxConstraints(maxWidth: ancha ? 640 : 420),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Icon(Icons.timelapse_rounded, size: ancha ? 64 : 48, color: Tono.rubi),
                const SizedBox(height: 18),
                Text(
                  suspendido ? 'SERVICIO SUSPENDIDO' : 'SERVICIO VENCIDO',
                  textAlign: TextAlign.center,
                  style: LetraTv.sobretitulo.copyWith(color: Tono.rubiClaro, fontSize: ancha ? 15 : 13),
                ),
                const SizedBox(height: 8),
                Text(
                  suspendido ? 'Tu servicio está suspendido' : 'Tu servicio venció',
                  textAlign: TextAlign.center,
                  style: ancha ? LetraTv.pantalla.copyWith(fontSize: 44) : _tituloCelular,
                ),
                const SizedBox(height: 8),
                Text(
                  'Contactá a tu vendedor para volver a mirar Kairos TV.',
                  textAlign: TextAlign.center,
                  style: ancha ? LetraTv.cuerpo : Letra.cuerpo,
                ),
                const SizedBox(height: 24),
                if (vendedor.hayDatos)
                  Container(
                    padding: const EdgeInsets.all(20),
                    decoration: BoxDecoration(
                      color: Tono.capaBaja,
                      borderRadius: BorderRadius.circular(Curva.panel),
                      border: Border.all(color: Tono.bordeSuave.withValues(alpha: .5)),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('Tu vendedor', style: LetraTv.ayuda),
                        const SizedBox(height: 6),
                        if (vendedor.nombre.isNotEmpty)
                          Text(vendedor.nombre, style: LetraTv.tarjeta.copyWith(fontSize: ancha ? 22 : 18)),
                        if (vendedor.telefono.isNotEmpty)
                          Text(
                            vendedor.telefono,
                            style: TextStyle(
                              fontFamily: Letra.texto,
                              fontWeight: FontWeight.w700,
                              fontSize: ancha ? 26 : 18,
                              color: Tono.celeste,
                            ),
                          ),
                      ],
                    ),
                  ),
                const SizedBox(height: 22),
                if (puedeEscribir) ...[
                  BotonTv(
                    texto: 'Escribirle por WhatsApp',
                    icono: Icons.chat_rounded,
                    principal: true,
                    autofocus: true,
                    alOk: escribir,
                    ancho: double.infinity,
                  ),
                  const SizedBox(height: 12),
                ],
                BotonTv(
                  texto: 'Ya renové, volver a intentar',
                  icono: Icons.refresh_rounded,
                  principal: !puedeEscribir,
                  autofocus: !puedeEscribir,
                  alOk: sesion.reintentar,
                  ancho: double.infinity,
                ),
                const SizedBox(height: 12),
                BotonTv(texto: 'Entrar con otro código', alOk: sesion.salir, ancho: double.infinity),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// ── Carga y sin conexión ───────────────────────────────────────────

class PantallaCarga extends StatelessWidget {
  const PantallaCarga({super.key, this.texto = 'Preparando tu contenido…'});

  final String texto;

  @override
  Widget build(BuildContext context) {
    final ancha = _esAncha(context);
    return _Fondo(
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            SimboloKairos(tamanio: ancha ? 120 : 88),
            const SizedBox(height: 22),
            NombreKairos(tamanio: ancha ? 40 : 30),
            const SizedBox(height: 34),
            SizedBox(
              width: ancha ? 260 : 180,
              child: ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: const LinearProgressIndicator(
                  minHeight: 4,
                  color: Tono.celeste,
                  backgroundColor: Tono.capaMaxima,
                ),
              ),
            ),
            const SizedBox(height: 14),
            Text(texto, style: ancha ? LetraTv.ayuda.copyWith(fontSize: 16) : Letra.cuerpo),
          ],
        ),
      ),
    );
  }
}

class PantallaSinConexion extends StatelessWidget {
  const PantallaSinConexion({super.key});

  @override
  Widget build(BuildContext context) {
    final sesion = SesionScope.of(context);
    final ancha = _esAncha(context);
    return _Fondo(
      child: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(28),
          child: ConstrainedBox(
            constraints: BoxConstraints(maxWidth: ancha ? 640 : 420),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Icon(Icons.wifi_off_rounded, size: ancha ? 64 : 48, color: Tono.textoApagado),
                const SizedBox(height: 18),
                Text(
                  'No hay conexión con el servidor',
                  textAlign: TextAlign.center,
                  style: ancha ? LetraTv.pantalla : _tituloCelular,
                ),
                const SizedBox(height: 8),
                Text(
                  sesion.errorConexion ?? 'Revisá la conexión a internet de este aparato.',
                  textAlign: TextAlign.center,
                  style: ancha ? LetraTv.cuerpo : Letra.cuerpo,
                ),
                const SizedBox(height: 28),
                BotonTv(
                  texto: 'Reintentar',
                  icono: Icons.refresh_rounded,
                  principal: true,
                  autofocus: true,
                  alOk: sesion.reintentar,
                  ancho: double.infinity,
                ),
                const SizedBox(height: 12),
                BotonTv(texto: 'Cerrar sesión', alOk: sesion.salir, ancho: double.infinity, tamanioTexto: 15),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
