/// La Agenda en el CELULAR (los datos y "Avisarme": agenda.dart):
///
///   - FilaAgenda: en Inicio, lo que viene en tarjetas; "Ver todo" abre PantallaAgenda.
///   - PantallaAgenda: todo, por día.
///   - TarjetaEvento: hora (o EN VIVO), título, canal y el botón: "Ver" si se
///     está dando, "Avisarme" si todavía no empezó.
library;

import 'package:flutter/material.dart';

import 'agenda.dart';
import 'componentes.dart';
import 'datos.dart';
import 'estilo.dart';

/// En Inicio: lo que viene en la agenda (si hay algo).
class FilaAgenda extends StatelessWidget {
  const FilaAgenda({super.key});

  @override
  Widget build(BuildContext context) {
    final agenda = DatosScope.of(context).catalogo.agenda;
    if (agenda.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(bottom: 28),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          EncabezadoSeccion(
            titulo: 'Agenda',
            icono: const Icon(Icons.event_rounded, size: 20, color: Tono.celeste),
            final_: VerTodo(alTocar: () => abrirPantalla<void>(context, const PantallaAgenda())),
          ),
          SizedBox(
            height: 176,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: Espacio.margen),
              itemCount: agenda.length,
              separatorBuilder: (_, _) => const SizedBox(width: Espacio.sm),
              itemBuilder: (_, i) => SizedBox(
                width: 290,
                child: Align(
                  alignment: Alignment.topCenter,
                  child: TarjetaEvento(evento: agenda[i]),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Toda la agenda, por día.
class PantallaAgenda extends StatelessWidget {
  const PantallaAgenda({super.key});

  @override
  Widget build(BuildContext context) {
    final catalogo = DatosScope.of(context).catalogo;
    return Scaffold(
      backgroundColor: Tono.fondo,
      appBar: AppBar(
        backgroundColor: Tono.capaMinima,
        surfaceTintColor: Colors.transparent,
        centerTitle: true,
        title: Text(
          'AGENDA',
          style: Letra.etiqueta.copyWith(color: Tono.celesteClaro, fontWeight: FontWeight.w700, letterSpacing: 1.2),
        ),
      ),
      body: ListenableBuilder(
        listenable: catalogo,
        builder: (context, _) {
          final agenda = catalogo.agenda;
          if (agenda.isEmpty) {
            return const Vacio(icono: Icons.event_busy_rounded, texto: 'No hay nada en la agenda por ahora.');
          }
          final ahora = DateTime.now();
          final filas = <Widget>[];
          String? dia;
          for (final evento in agenda) {
            final este = evento.enVivo(ahora) ? 'Ahora' : nombreDelDia(evento.empieza, ahora);
            if (este != dia) {
              dia = este;
              filas.add(
                Padding(
                  padding: const EdgeInsets.fromLTRB(Espacio.margen, Espacio.lg, Espacio.margen, 10),
                  child: Text(este, style: Letra.titulo),
                ),
              );
            }
            filas.add(
              Padding(
                padding: const EdgeInsets.fromLTRB(Espacio.margen, 0, Espacio.margen, 10),
                child: TarjetaEvento(evento: evento, conDia: false),
              ),
            );
          }
          return ListView(padding: const EdgeInsets.only(bottom: 40), children: filas);
        },
      ),
    );
  }
}

class TarjetaEvento extends StatelessWidget {
  const TarjetaEvento({super.key, required this.evento, this.conDia = true});

  final EventoAgenda evento;

  /// false = solo la hora (en la Agenda completa el día ya está arriba, en el título del grupo).
  final bool conDia;

  @override
  Widget build(BuildContext context) {
    final enVivo = evento.enVivo();
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Tono.capaBaja,
        borderRadius: BorderRadius.circular(Curva.tarjeta),
        border: Border.all(color: enVivo ? Tono.rubi.withValues(alpha: .55) : Tono.bordeSuave.withValues(alpha: .5)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              if (enVivo)
                const InsigniaEnVivo()
              else
                Text(
                  conDia ? evento.cuando() : hora(evento.empieza),
                  style: Letra.etiqueta.copyWith(color: Tono.celeste, fontWeight: FontWeight.w700),
                ),
              const Spacer(),
              Icon(iconoDeEvento(evento.tipo), size: 18, color: Tono.textoApagado),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            evento.titulo,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: Letra.cuerpoGrande.copyWith(fontWeight: FontWeight.w700),
          ),
          if (evento.detalle.isNotEmpty)
            Text(evento.detalle, maxLines: 1, overflow: TextOverflow.ellipsis, style: Letra.mini),
          const SizedBox(height: 14),
          Row(
            children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(6),
                child: SizedBox(
                  width: 44,
                  height: 30,
                  child: Imagen(
                    url: evento.canal.logo,
                    nombre: evento.canal.nombre,
                    ajuste: BoxFit.contain,
                    relleno: const EdgeInsets.all(3),
                    fondo: Tono.capaAlta,
                    tamanioIniciales: 11,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  evento.canal.nombre,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: Letra.cuerpo.copyWith(color: Tono.texto),
                ),
              ),
              const SizedBox(width: 8),
              if (enVivo)
                SizedBox(
                  width: 92,
                  child: BotonPrincipal(
                    texto: 'Ver',
                    alto: 36,
                    // Como tocar el aviso: la pantalla principal lo abre en En Vivo (estructura.dart)
                    alTocar: () => Avisos.canalPedido.value = evento.canal.id,
                  ),
                )
              else
                BotonAvisarme(evento: evento),
            ],
          ),
        ],
      ),
    );
  }
}

/// "Avisarme" / "Te aviso" (marcado). Tocarlo lo alterna.
class BotonAvisarme extends StatelessWidget {
  const BotonAvisarme({super.key, required this.evento});

  final EventoAgenda evento;

  Future<void> _alternar(BuildContext context) async {
    final mensajero = ScaffoldMessenger.maybeOf(context);
    final marcado = await Avisos.alternar(evento);
    mensajero
      ?..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(
            marcado
                ? 'Te avisamos ${Avisos.anticipacion.inMinutes} minutos antes de que empiece.'
                : 'Listo, ya no te avisamos.',
          ),
        ),
      );
  }

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<int>(
      valueListenable: Avisos.cambios,
      builder: (context, _, _) {
        final marcado = Avisos.marcado(evento);
        return OutlinedButton.icon(
          onPressed: () => _alternar(context),
          style: OutlinedButton.styleFrom(
            foregroundColor: marcado ? Tono.sobreCelesteOscuro : Tono.celeste,
            backgroundColor: marcado ? Tono.celeste : Colors.transparent,
            side: const BorderSide(color: Tono.celeste),
            visualDensity: VisualDensity.compact,
            padding: const EdgeInsets.symmetric(horizontal: 12),
          ),
          icon: Icon(marcado ? Icons.notifications_active_rounded : Icons.notifications_none_rounded, size: 18),
          label: Text(marcado ? 'Te aviso' : 'Avisarme'),
        );
      },
    );
  }
}
