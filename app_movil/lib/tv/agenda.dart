/// La Agenda en la TV (los datos y "Avisarme": movil/agenda.dart):
///
///   - filaAgendaTv: en Inicio, lo que viene. OK sobre algo que se está dando
///     lo pone; sobre algo que todavía no empezó, lo marca o desmarca ("Avisarme").
///   - CartelEmpiezaTv: si la app está abierta cuando empieza algo marcado,
///     "Empieza ahora" con "Verlo" (lo muestra PantallaTv: estructura.dart).
library;

import 'package:flutter/material.dart';

import '../movil/agenda.dart';
import '../movil/datos.dart';
import '../movil/estilo.dart';
import 'estructura.dart' show DialogoTv;
import 'foco.dart';
import 'piezas.dart';
import 'reproductor.dart';

/// La fila de la Agenda (nada si no hay eventos).
Widget filaAgendaTv(BuildContext context) {
  final agenda = DatosScope.of(context).catalogo.agenda;
  return FilaTv(
    titulo: 'Agenda',
    icono: const Icon(Icons.event_rounded, color: Tono.celeste, size: 26),
    final_: agenda.isEmpty ? null : 'OK: Avisarme',
    alto: 164,
    tarjetas: [for (final evento in agenda) TarjetaEventoTv(evento: evento)],
  );
}

class TarjetaEventoTv extends StatelessWidget {
  const TarjetaEventoTv({super.key, required this.evento});

  final EventoAgenda evento;

  void _alOk(BuildContext context) {
    if (evento.enVivo()) {
      verCanalTv(context, evento.canal);
      return;
    }
    Avisos.alternar(evento).then((marcado) {
      if (!context.mounted) return;
      avisoTv(
        context,
        marcado ? 'Te avisamos cuando empiece (con la app abierta)' : 'Listo, ya no te avisamos',
        icono: marcado ? Icons.notifications_active_rounded : Icons.notifications_off_rounded,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    final enVivo = evento.enVivo();
    return SizedBox(
      width: 360,
      height: 164,
      child: Enfocable(
        alOk: () => _alOk(context),
        curva: Curva.tarjeta,
        etiqueta: '${evento.cuando()}, ${evento.titulo}, en ${evento.canal.nombre}',
        child: DecoratedBox(
          decoration: BoxDecoration(
            gradient: const LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [Tono.capa, Tono.capaMinima],
            ),
            borderRadius: BorderRadius.circular(Curva.tarjeta),
            border: Border.all(
              color: enVivo ? Tono.rubi.withValues(alpha: .6) : Tono.bordeSuave.withValues(alpha: .55),
            ),
          ),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(18, 14, 18, 14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    if (enVivo)
                      const InsigniaEnVivoTv()
                    else
                      Text(
                        evento.cuando(),
                        style: const TextStyle(
                          fontFamily: Letra.texto,
                          fontSize: 17,
                          fontWeight: FontWeight.w700,
                          color: Tono.celeste,
                        ),
                      ),
                    const Spacer(),
                    ValueListenableBuilder<int>(
                      valueListenable: Avisos.cambios,
                      builder: (_, _, _) => Icon(
                        Avisos.marcado(evento) ? Icons.notifications_active_rounded : iconoDeEvento(evento.tipo),
                        size: 22,
                        color: Avisos.marcado(evento) ? Tono.celeste : Tono.textoApagado,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Text(
                  evento.titulo,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontFamily: Letra.titulos,
                    fontSize: 21,
                    height: 1.15,
                    fontWeight: FontWeight.w800,
                    color: Tono.texto,
                  ),
                ),
                const Spacer(),
                Row(
                  children: [
                    SizedBox(width: 46, height: 30, child: LogoCanalTv(canal: evento.canal, tamanioIniciales: 13)),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        evento.detalle.isEmpty ? evento.canal.nombre : '${evento.canal.nombre} · ${evento.detalle}',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: LetraTv.ayuda.copyWith(color: Tono.textoSuave, fontSize: 15),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// "Empieza ahora": algo marcado con "Avisarme" empezó con la app abierta.
/// Devuelve true si eligió verlo.
class CartelEmpiezaTv extends StatelessWidget {
  const CartelEmpiezaTv({super.key, required this.evento});

  final EventoAgenda evento;

  @override
  Widget build(BuildContext context) {
    return DialogoTv(
      icono: Icons.notifications_active_rounded,
      titulo: 'Empieza ${evento.titulo}',
      texto: 'A las ${hora(evento.empieza)} en ${evento.canal.nombre}.',
      botones: [
        BotonTv(texto: 'Verlo', principal: true, autofocus: true, alOk: () => Navigator.pop(context, true)),
        BotonTv(texto: 'Ahora no', alOk: () => Navigator.pop(context, false)),
      ],
    );
  }
}
