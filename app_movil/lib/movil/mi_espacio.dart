/// Mi Espacio: la cuenta (código, vencimiento, pantallas, vendedor),
/// "Continuar viendo", las preferencias y, para los usuarios del panel, sus
/// herramientas. Los favoritos tienen su propia sección (favoritos.dart).
/// Stitch no tenía esta pantalla: está armada con sus mismas piezas.
library;

import 'package:flutter/material.dart';

import '../pantallas/notificaciones.dart';
import '../pantallas/perfil.dart';
import '../pantallas/usuarios_lista.dart';
import '../sesion.dart';
import '../utiles.dart';
import 'componentes.dart';
import 'datos.dart';
import 'estilo.dart';
import 'estructura.dart';
import 'inicio.dart';
import 'mi_agenda.dart';
import 'recordatorios.dart';

class SeccionMiEspacio extends StatelessWidget {
  const SeccionMiEspacio({super.key});

  @override
  Widget build(BuildContext context) {
    final datos = DatosScope.of(context);
    final sesion = SesionScope.of(context);
    return ListenableBuilder(
      listenable: Listenable.merge([datos.catalogo, datos.biblioteca]),
      builder: (context, _) {
        final catalogo = datos.catalogo;
        final biblioteca = datos.biblioteca;

        return ListView(
          padding: EdgeInsets.only(
            top: altoBarraSuperior(context) + Espacio.margen,
            bottom: altoBarraInferior(context) + 40,
          ),
          children: [
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: Espacio.margen),
              child: _Cuenta(),
            ),
            const SizedBox(height: 28),
            _Continuar(biblioteca: biblioteca, catalogo: catalogo),
            Padding(
              padding: const EdgeInsets.fromLTRB(Espacio.margen, 0, Espacio.margen, 12),
              child: Material(
                color: Tono.capa,
                borderRadius: BorderRadius.circular(Curva.grande),
                clipBehavior: Clip.antiAlias,
                child: ValueListenableBuilder<int>(
                  valueListenable: Recordatorios.cambios,
                  builder: (context, _, _) {
                    final cuantos = Recordatorios.conCanal(catalogo).length;
                    return ListTile(
                      onTap: () => abrirPantalla<void>(context, const PantallaMiAgenda()),
                      leading: const Icon(Icons.event_rounded, color: Tono.celeste),
                      title: Text('Mi agenda', style: Letra.etiqueta.copyWith(fontSize: 14)),
                      subtitle: Text(
                        cuantos == 0
                            ? 'Anotá lo que querés ver y te avisamos antes.'
                            : cuantos == 1
                            ? '1 recordatorio anotado.'
                            : '$cuantos recordatorios anotados.',
                        style: Letra.cuerpo,
                      ),
                      trailing: const Icon(Icons.chevron_right_rounded, color: Tono.textoApagado),
                    );
                  },
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: Espacio.margen),
              child: Material(
                color: Tono.capa,
                borderRadius: BorderRadius.circular(Curva.grande),
                clipBehavior: Clip.antiAlias,
                child: SwitchListTile(
                  value: biblioteca.volverAlUltimo,
                  onChanged: (valor) => biblioteca.volverAlUltimo = valor,
                  activeThumbColor: Tono.celeste,
                  secondary: const Icon(Icons.restore_rounded, color: Tono.celeste),
                  title: Text('Volver al último canal al abrir', style: Letra.etiqueta.copyWith(fontSize: 14)),
                  subtitle: Text('Arranca directo en el canal que estabas viendo.', style: Letra.cuerpo),
                ),
              ),
            ),
            const SizedBox(height: 28),
            if (sesion.perfil != null && !sesion.esCliente) const _HerramientasDelPanel(),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: Espacio.margen),
              child: OutlinedButton.icon(
                style: OutlinedButton.styleFrom(
                  foregroundColor: Tono.rubiClaro,
                  side: const BorderSide(color: Tono.capaMaxima),
                  minimumSize: const Size.fromHeight(46),
                  shape: const StadiumBorder(),
                ),
                onPressed: () => sesion.esCliente ? _salirCliente(context) : preguntarYSalir(context),
                icon: const Icon(Icons.logout_rounded, size: 20),
                label: Text('Cerrar sesión en este aparato', style: Letra.etiqueta.copyWith(color: Tono.rubiClaro)),
              ),
            ),
          ],
        );
      },
    );
  }

  Future<void> _salirCliente(BuildContext context) async {
    final salir = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('¿Cerrar sesión?', style: Letra.titulo),
        content: Text(
          'Esta pantalla queda libre. Para volver a entrar vas a necesitar tu código.',
          style: Letra.cuerpo,
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancelar')),
          TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Cerrar sesión')),
        ],
      ),
    );
    if (salir == true && context.mounted) await SesionScope.leer(context).salir();
  }
}

/// La tarjeta de la cuenta: avatar, nombre y sus datos.
class _Cuenta extends StatelessWidget {
  const _Cuenta();

  @override
  Widget build(BuildContext context) {
    final sesion = SesionScope.of(context);
    final cliente = sesion.cliente;
    final perfil = sesion.perfil;
    final nombre = cliente?.nombre ?? perfil?.nombreCompleto ?? '';
    final dias = cliente?.diasRestantes;
    return Container(
      padding: const EdgeInsets.all(Espacio.margen),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(Curva.tarjeta),
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF0B3B42), Tono.capa],
        ),
        border: Border.all(color: Tono.celeste.withValues(alpha: .25)),
        boxShadow: brilloCeleste(desenfoque: 16, opacidad: .12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Container(
                width: 52,
                height: 52,
                alignment: Alignment.center,
                decoration: const BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: LinearGradient(colors: [Tono.celeste, Tono.sobreCeleste]),
                ),
                child: Text(
                  inicialesDe(nombre.isEmpty ? 'TV' : nombre),
                  style: Letra.titulo.copyWith(fontSize: 18, color: Tono.sobreCelesteOscuro),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(nombre, maxLines: 1, overflow: TextOverflow.ellipsis, style: Letra.titulo),
                    Text(
                      cliente != null ? 'Cliente de Kairos TV' : (perfil?.descripcionRol ?? ''),
                      style: Letra.cuerpo,
                    ),
                  ],
                ),
              ),
            ],
          ),
          if (cliente != null) ...[
            const SizedBox(height: Espacio.margen),
            Row(
              children: [
                _Dato(icono: Icons.key_rounded, titulo: 'Tu código', valor: cliente.codigo),
                const SizedBox(width: Espacio.sm),
                _Dato(
                  icono: Icons.event_available_rounded,
                  titulo: 'Vence',
                  valor: cliente.vence == null
                      ? '—'
                      : '${cliente.vence!.day.toString().padLeft(2, '0')}/'
                            '${cliente.vence!.month.toString().padLeft(2, '0')}/${cliente.vence!.year % 100}',
                  alerta: dias != null && dias <= 3,
                ),
                const SizedBox(width: Espacio.sm),
                _Dato(
                  icono: Icons.tv_rounded,
                  titulo: 'Pantallas',
                  valor: '${cliente.conectados}/${cliente.pantallas}',
                ),
              ],
            ),
            if (cliente.vendedor.hayDatos)
              Padding(
                padding: const EdgeInsets.only(top: 10),
                child: Text(
                  'Tu vendedor: ${[cliente.vendedor.nombre, cliente.vendedor.telefono].where((d) => d.isNotEmpty).join(' · ')}',
                  style: Letra.cuerpo,
                ),
              ),
            if (dias != null && dias <= 3)
              Padding(
                padding: const EdgeInsets.only(top: 10),
                child: Text(
                  dias <= 0
                      ? 'Tu servicio vence hoy. Renovalo con quien te lo vendió.'
                      : '¡Quedan $dias día(s)! Renovalo con quien te lo vendió.',
                  style: Letra.etiqueta.copyWith(color: Tono.rubiClaro),
                ),
              ),
          ],
        ],
      ),
    );
  }
}

class _Dato extends StatelessWidget {
  const _Dato({required this.icono, required this.titulo, required this.valor, this.alerta = false});

  final IconData icono;
  final String titulo;
  final String valor;
  final bool alerta;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: Tono.capaMinima.withValues(alpha: .7),
          borderRadius: BorderRadius.circular(Curva.grande),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icono, size: 16, color: alerta ? Tono.rubiClaro : Tono.celeste),
            const SizedBox(height: 6),
            Text(titulo.toUpperCase(), style: Letra.mini.copyWith(color: Tono.textoSuave, letterSpacing: .6)),
            const SizedBox(height: 2),
            Text(
              valor,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: Letra.numeros.copyWith(color: alerta ? Tono.rubiClaro : Tono.texto, fontWeight: FontWeight.w700),
            ),
          ],
        ),
      ),
    );
  }
}

class _Continuar extends StatelessWidget {
  const _Continuar({required this.biblioteca, required this.catalogo});

  final Biblioteca biblioteca;
  final Catalogo catalogo;

  @override
  Widget build(BuildContext context) {
    final tarjetas = <Widget>[];
    for (final progreso in biblioteca.continuarViendo) {
      final canal = catalogo.canalPorId(progreso.id);
      if (canal == null) continue;
      final serie = canal.contenido == 'serie' ? catalogo.serieDe(canal) : null;
      final episodio = serie?.episodios.firstWhere((e) => e.canal.id == canal.id);
      tarjetas.add(
        TarjetaContinuar(
          titulo: serie?.nombre ?? sinAnio(canal.nombre),
          subtitulo: episodio == null
              ? 'Película'
              : 'Ep. ${episodio.numero}${episodio.titulo.isEmpty ? '' : ': ${episodio.titulo}'}',
          imagen: canal.logo.isNotEmpty ? canal.logo : (serie?.imagen ?? ''),
          etiqueta: episodio == null ? 'Película' : 'T${episodio.temporada} : E${episodio.numero}',
          progreso: progreso,
          alTocar: () => reproducirContenido(context, canal, serie: serie, desde: progreso.posicion),
          alQuitar: () => biblioteca.olvidarProgreso(progreso.id),
        ),
      );
    }
    if (tarjetas.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(bottom: 28),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const EncabezadoSeccion(
            titulo: 'Continuar Viendo',
            icono: Icon(Icons.history_rounded, size: 20, color: Tono.celeste),
          ),
          SizedBox(
            height: 256,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: Espacio.margen),
              itemCount: tarjetas.length,
              separatorBuilder: (_, _) => const SizedBox(width: Espacio.sm),
              itemBuilder: (_, i) => Align(alignment: Alignment.topCenter, child: tarjetas[i]),
            ),
          ),
        ],
      ),
    );
  }
}

/// Para los usuarios del panel (no los clientes): perfil, usuarios, avisos.
class _HerramientasDelPanel extends StatelessWidget {
  const _HerramientasDelPanel();

  @override
  Widget build(BuildContext context) {
    final perfil = SesionScope.of(context).perfil!;
    void abrir(Widget pantalla) => Navigator.push(context, MaterialPageRoute<void>(builder: (_) => pantalla));
    return Padding(
      padding: const EdgeInsets.only(bottom: 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const EncabezadoSeccion(
            titulo: 'Panel de Kairos TV',
            icono: Icon(Icons.admin_panel_settings_rounded, size: 20, color: Tono.dorado),
          ),
          _Opcion(icono: Icons.person_rounded, texto: 'Mi perfil', alTocar: () => abrir(const PantallaPerfil())),
          if (perfil.puede('ver_usuarios'))
            _Opcion(icono: Icons.group_rounded, texto: 'Usuarios', alTocar: () => abrir(const PantallaUsuarios())),
          _Opcion(
            icono: Icons.notifications_rounded,
            texto: 'Avisos',
            alTocar: () => abrir(PantallaNotificaciones(alCambiar: (_) {})),
          ),
        ],
      ),
    );
  }
}

class _Opcion extends StatelessWidget {
  const _Opcion({required this.icono, required this.texto, required this.alTocar});

  final IconData icono;
  final String texto;
  final VoidCallback alTocar;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(Espacio.margen, 0, Espacio.margen, Espacio.sm),
      child: Material(
        color: Tono.capa,
        borderRadius: BorderRadius.circular(Curva.grande),
        child: ListTile(
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Curva.grande)),
          leading: Icon(icono, color: Tono.celeste),
          title: Text(texto, style: Letra.etiqueta.copyWith(fontSize: 14)),
          trailing: const Icon(Icons.chevron_right_rounded, color: Tono.textoSuave),
          onTap: alTocar,
        ),
      ),
    );
  }
}
