/// Mi cuenta en la TV (diseno_kairos_tv: tv-16): a la izquierda los datos
/// (código, hasta cuándo, pantallas, vendedor); a la derecha las
/// preferencias: volver al último canal al abrir, modo de video, "Lo que no
/// se ve en esta TV" (qué esconde este aparato y por qué, con volver a
/// mostrarlo o probarlo igual), favoritos, buscar actualizaciones y cerrar sesión.
library;

import 'package:flutter/material.dart';

import '../actualizacion.dart';
import '../api/modelos.dart';
import '../aparato.dart';
import '../movil/componentes.dart';
import '../movil/datos.dart';
import '../movil/estilo.dart';
import '../sesion.dart';
import 'estructura.dart';
import 'foco.dart';
import 'piezas.dart';

class CuentaTv extends StatelessWidget {
  const CuentaTv({super.key});

  static const _meses = [
    'enero',
    'febrero',
    'marzo',
    'abril',
    'mayo',
    'junio',
    'julio',
    'agosto',
    'septiembre',
    'octubre',
    'noviembre',
    'diciembre',
  ];

  Future<void> _buscarActualizacion(BuildContext context) async {
    final hay = await VigilarActualizacion.buscarAhora(context);
    if (!context.mounted || hay == true) return;
    avisoTv(
      context,
      hay == false
          ? 'Ya tenés la última versión${Aparato.version.isEmpty ? '' : ' (${Aparato.version})'}'
          : 'No se pudo consultar. Probá en un rato.',
      icono: hay == false ? Icons.check_circle_rounded : Icons.wifi_off_rounded,
    );
  }

  /// Lo que el panel manda pero esta TV no muestra, y por qué: falló acá, o
  /// tiene un códec que la TV dice no leer. Se puede volver a mostrar lo que
  /// falló y "probar igual" lo de los códecs (por si la TV los lee igual).
  Future<void> _loQueNoSeVe(BuildContext context) async {
    final datos = DatosScope.of(context);
    final catalogo = datos.catalogo;
    final biblioteca = datos.biblioteca;
    final accion = await showDialog<String>(
      context: context,
      builder: (contexto) => CuadroLoQueNoSeVe(
        escondidos: catalogo.escondidos,
        codecs: Aparato.codecs,
        hayFallados: NoAnda.cuantos > 0,
        probarTodo: biblioteca.probarTodo,
      ),
    );
    if (!context.mounted || accion == null) return;
    if (accion == 'mostrar') {
      await NoAnda.volverAMostrarTodo();
      if (context.mounted) avisoTv(context, 'Listo: vuelve a aparecer y se prueba de nuevo');
    } else {
      biblioteca.probarTodo = !biblioteca.probarTodo;
      avisoTv(
        context,
        biblioteca.probarTodo
            ? 'Se muestra todo: si algo no se ve bien, volvé a ponerlo en No'
            : 'Listo: lo que esta TV no lee vuelve a esconderse',
      );
    }
    await catalogo.cargar();
  }

  Future<void> _salir(BuildContext context) async {
    final sesion = SesionScope.leer(context);
    final salir = await showDialog<bool>(
      context: context,
      builder: (contexto) => DialogoTv(
        icono: Icons.logout_rounded,
        titulo: '¿Cerrar sesión en esta TV?',
        texto: sesion.esCliente
            ? 'La pantalla queda libre. Para volver a entrar vas a necesitar tu código.'
            : 'Para volver a entrar vas a necesitar tu usuario y contraseña.',
        botones: [
          BotonTv(texto: 'Cancelar', principal: true, autofocus: true, alOk: () => Navigator.pop(contexto, false)),
          BotonTv(texto: 'Cerrar sesión', alOk: () => Navigator.pop(contexto, true)),
        ],
      ),
    );
    if (salir == true) await sesion.salir();
  }

  @override
  Widget build(BuildContext context) {
    final sesion = SesionScope.of(context);
    final biblioteca = DatosScope.of(context).biblioteca;
    final cliente = sesion.cliente;
    final perfil = sesion.perfil;
    final nombre = cliente?.nombre ?? perfil?.nombreCompleto ?? '';
    final vence = cliente?.vence;
    final dias = cliente?.diasRestantes;

    return ListenableBuilder(
      listenable: biblioteca,
      builder: (context, _) => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const EncabezadoTv(sobretitulo: 'Perfil', titulo: 'Mi cuenta'),
          const SizedBox(height: 26),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: MargenTv.izquierda).copyWith(right: MargenTv.derecha),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  flex: 11,
                  child: _Tarjeta(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Container(
                              width: 92,
                              height: 92,
                              alignment: Alignment.center,
                              decoration: const BoxDecoration(color: Tono.celeste, shape: BoxShape.circle),
                              child: Text(
                                inicialesDe(nombre.isEmpty ? 'TV' : nombre),
                                style: const TextStyle(
                                  fontFamily: Letra.titulos,
                                  fontSize: 34,
                                  fontWeight: FontWeight.w800,
                                  color: Tono.sobreCelesteOscuro,
                                ),
                              ),
                            ),
                            const SizedBox(width: 24),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(nombre, maxLines: 1, overflow: TextOverflow.ellipsis, style: LetraTv.seccion),
                                  Text(
                                    cliente != null ? 'Cliente' : (perfil?.descripcionRol ?? ''),
                                    style: LetraTv.cuerpo,
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ),
                        const Padding(
                          padding: EdgeInsets.symmetric(vertical: 26),
                          child: Divider(height: 1, color: Tono.capaMaxima),
                        ),
                        if (cliente != null) ...[
                          _Dato('Código de acceso', cliente.codigo),
                          _Dato(
                            'Servicio vigente hasta',
                            vence == null ? '—' : '${vence.day} de ${_meses[vence.month - 1]} de ${vence.year}',
                            alerta: dias != null && dias <= 3
                                ? (dias <= 0 ? 'Vence hoy: renovalo con tu vendedor.' : 'Quedan $dias día(s).')
                                : null,
                          ),
                          _Dato('Pantallas', '${cliente.conectados} de ${cliente.pantallas} en uso'),
                          if (cliente.vendedor.hayDatos)
                            _Dato(
                              'Tu vendedor',
                              [
                                cliente.vendedor.nombre,
                                cliente.vendedor.telefono,
                              ].where((d) => d.isNotEmpty).join(' · '),
                            ),
                        ] else
                          _Dato('Usuario del panel', perfil?.username ?? ''),
                        if (Aparato.version.isNotEmpty) _Dato('Versión de la app', Aparato.version),
                      ],
                    ),
                  ),
                ),
                const SizedBox(width: 30),
                Expanded(
                  flex: 9,
                  child: _Tarjeta(
                    child: FocusTraversalGroup(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          const Text('Preferencias', style: LetraTv.tarjeta),
                          const SizedBox(height: 18),
                          BotonTv(
                            texto: biblioteca.volverAlUltimo
                                ? 'Volver al último canal al abrir: Sí'
                                : 'Volver al último canal al abrir: No',
                            icono: biblioteca.volverAlUltimo ? Icons.toggle_on_rounded : Icons.toggle_off_rounded,
                            color: biblioteca.volverAlUltimo ? Tono.celeste : null,
                            autofocus: true,
                            ancho: double.infinity,
                            alOk: () => biblioteca.volverAlUltimo = !biblioteca.volverAlUltimo,
                          ),
                          const SizedBox(height: 14),
                          // Si un canal se ve verde o negro con el sonido bien, el otro modo suele arreglarlo
                          BotonTv(
                            texto: biblioteca.videoEnSuperficie
                                ? 'Modo de video: TV (recomendado)'
                                : 'Modo de video: compatible',
                            icono: Icons.tv_rounded,
                            ancho: double.infinity,
                            alOk: () => biblioteca.videoEnSuperficie = !biblioteca.videoEnSuperficie,
                          ),
                          const SizedBox(height: 6),
                          const Text(
                            '¿Imagen verde o negra con sonido? Probá cambiar el modo de video o desenchufá la TV '
                            '30 segundos.',
                            style: LetraTv.ayuda,
                          ),
                          const SizedBox(height: 14),
                          // ¿Un canal está en el celular y no en la TV? Acá se ve por qué
                          BotonTv(
                            texto: 'Lo que no se ve en esta TV',
                            icono: Icons.visibility_off_rounded,
                            ancho: double.infinity,
                            alOk: () => _loQueNoSeVe(context),
                          ),
                          const SizedBox(height: 14),
                          BotonTv(
                            texto: 'Administrar favoritos',
                            icono: Icons.favorite_rounded,
                            ancho: double.infinity,
                            alOk: () => NavegacionTv.of(context).irA(SeccionTv.favoritos),
                          ),
                          const SizedBox(height: 14),
                          BotonTv(
                            texto: 'Buscar actualizaciones',
                            icono: Icons.system_update_rounded,
                            ancho: double.infinity,
                            alOk: () => _buscarActualizacion(context),
                          ),
                          const SizedBox(height: 14),
                          BotonTv(
                            texto: 'Cerrar sesión',
                            icono: Icons.logout_rounded,
                            color: Tono.rubiClaro,
                            ancho: double.infinity,
                            alOk: () => _salir(context),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// El cuadro "Lo que no se ve en esta TV" (Mi cuenta): qué códecs lee la TV,
/// lo escondido con su motivo y los botones. Devuelve 'mostrar' (volver a
/// mostrar lo que falló acá), 'probar' (cambiar "Probar igual") o null.
class CuadroLoQueNoSeVe extends StatelessWidget {
  const CuadroLoQueNoSeVe({
    super.key,
    required this.escondidos,
    required this.codecs,
    required this.hayFallados,
    required this.probarTodo,
  });

  final List<(Canal, String)> escondidos;
  final Set<String> codecs;
  final bool hayFallados;
  final bool probarTodo;

  /// Cuántos de lo escondido se nombran (el resto: "y N más").
  static const aLaVista = 8;

  @override
  Widget build(BuildContext context) {
    final lee = codecs.map(nombreDeCodec).toList()..sort();
    return DialogoTv(
      icono: Icons.visibility_off_rounded,
      titulo: escondidos.isEmpty
          ? 'Esta TV muestra todo lo que manda el panel'
          : 'No se ${escondidos.length == 1 ? 've 1' : 'ven ${escondidos.length}'} en esta TV',
      texto: lee.isEmpty ? null : 'Esta TV lee videos ${lee.join(', ')}.',
      hijo: escondidos.isEmpty
          ? null
          : Padding(
              padding: const EdgeInsets.only(top: 18),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  for (final (canal, motivo) in escondidos.take(aLaVista))
                    Padding(
                      padding: const EdgeInsets.only(bottom: 6),
                      child: Text.rich(
                        TextSpan(
                          children: [
                            TextSpan(
                              text: '${canal.nombre}: ',
                              style: const TextStyle(fontWeight: FontWeight.w700, color: Tono.texto),
                            ),
                            TextSpan(text: motivo),
                          ],
                        ),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: LetraTv.ayuda.copyWith(fontSize: 17),
                      ),
                    ),
                  if (escondidos.length > aLaVista)
                    Text('Y ${escondidos.length - aLaVista} más.', style: LetraTv.ayuda),
                ],
              ),
            ),
      botones: [
        BotonTv(texto: 'Cerrar', principal: true, autofocus: true, alOk: () => Navigator.pop(context)),
        if (hayFallados)
          BotonTv(
            texto: 'Volver a mostrar lo que falló acá',
            icono: Icons.restart_alt_rounded,
            alOk: () => Navigator.pop(context, 'mostrar'),
          ),
        BotonTv(
          texto: probarTodo ? 'Probar igual lo que quizá no lea: Sí' : 'Probar igual lo que quizá no lea: No',
          icono: probarTodo ? Icons.toggle_on_rounded : Icons.toggle_off_rounded,
          alOk: () => Navigator.pop(context, 'probar'),
        ),
      ],
    );
  }
}

class _Tarjeta extends StatelessWidget {
  const _Tarjeta({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(34),
      decoration: BoxDecoration(
        color: Tono.capaBaja,
        borderRadius: BorderRadius.circular(Curva.portada),
        border: Border.all(color: Tono.bordeSuave.withValues(alpha: .5)),
      ),
      child: child,
    );
  }
}

class _Dato extends StatelessWidget {
  const _Dato(this.titulo, this.valor, {this.alerta});

  final String titulo;
  final String valor;
  final String? alerta;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(titulo, style: LetraTv.ayuda.copyWith(fontSize: 16)),
          const SizedBox(height: 2),
          Text(
            valor,
            style: const TextStyle(
              fontFamily: Letra.texto,
              fontSize: 21,
              fontWeight: FontWeight.w700,
              color: Tono.texto,
            ),
          ),
          if (alerta != null) Text(alerta!, style: LetraTv.ayuda.copyWith(fontSize: 16, color: Tono.rubiClaro)),
        ],
      ),
    );
  }
}
