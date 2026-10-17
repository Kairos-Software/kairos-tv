/// "Mi agenda" en la TV (los datos: movil/recordatorios.dart):
///
///   - DialogoRecordarmeTv: se abre desde las opciones del reproductor en vivo
///     ("Recordarme"). Renglones Día, Hora, Minutos y Repetir: ← → cambian el
///     valor, ↑ ↓ pasan de renglón. También cambia o saca uno anotado.
///   - FilaMiAgendaTv: en Inicio, lo anotado (solo si hay algo). OK sobre algo
///     que se está dando lo pone; si no, lo abre para cambiarlo.
///   - CartelEmpiezaTv: si la app está abierta cuando empieza algo anotado,
///     "Empieza ..." con "Verlo" (lo muestra PantallaTv: estructura.dart).
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/modelos.dart';
import '../movil/datos.dart';
import '../movil/estilo.dart';
import '../movil/recordatorios.dart';
import 'estructura.dart' show DialogoTv;
import 'foco.dart';
import 'piezas.dart';
import 'reproductor.dart';

/// "Recordarme" en [canal] (con [existente], lo cambia). Avisa cómo quedó.
Future<void> recordarmeTv(BuildContext context, {required Canal canal, Recordatorio? existente}) async {
  final mensaje = await showDialog<String>(
    context: context,
    builder: (_) => DialogoRecordarmeTv(canal: canal, existente: existente),
  );
  if (mensaje != null && context.mounted) avisoTv(context, mensaje, icono: Icons.notifications_active_rounded);
}

class DialogoRecordarmeTv extends StatefulWidget {
  const DialogoRecordarmeTv({super.key, required this.canal, this.existente});

  final Canal canal;
  final Recordatorio? existente;

  @override
  State<DialogoRecordarmeTv> createState() => _DialogoRecordarmeTvState();
}

class _DialogoRecordarmeTvState extends State<DialogoRecordarmeTv> {
  late final List<DateTime> _dias;
  late int _dia;
  late int _hora;
  late int _minutos;
  late bool _semanal = widget.existente?.semanal ?? false;

  @override
  void initState() {
    super.initState();
    final ahora = DateTime.now();
    _dias = [for (var i = 0; i < 7; i++) DateTime(ahora.year, ahora.month, ahora.day + i)];
    // Uno nuevo: la próxima hora en punto
    final cuando = widget.existente?.proxima(ahora) ?? DateTime(ahora.year, ahora.month, ahora.day, ahora.hour + 1);
    final dia = DateTime(cuando.year, cuando.month, cuando.day);
    if (!_dias.contains(dia)) _dias.add(dia);
    _dia = _dias.indexOf(dia);
    _hora = cuando.hour;
    _minutos = cuando.minute - cuando.minute % 5;
  }

  DateTime get _cuando {
    final dia = _dias[_dia];
    return DateTime(dia.year, dia.month, dia.day, _hora, _minutos);
  }

  bool get _yaPaso => !_semanal && !_cuando.isAfter(DateTime.now());

  Future<void> _guardar() async {
    final navegador = Navigator.of(context);
    final recordatorio = Recordatorio(
      id: widget.existente?.id ?? Recordatorios.nuevoId(),
      canal: widget.canal.id,
      cuando: _cuando,
      nombre: widget.existente?.nombre ?? '',
      semanal: _semanal,
      nombreDelCanal: widget.canal.nombre,
    );
    await Recordatorios.guardar(recordatorio);
    navegador.pop('Anotado: ${recordatorio.cuandoTexto().replaceFirst('Todos', 'todos')}');
  }

  Future<void> _sacar() async {
    final navegador = Navigator.of(context);
    await Recordatorios.borrar(widget.existente!.id);
    navegador.pop('Listo, lo sacamos de tu agenda');
  }

  @override
  Widget build(BuildContext context) {
    final ahora = DateTime.now();
    return DialogoTv(
      icono: Icons.notifications_active_rounded,
      titulo: widget.existente == null ? 'Recordarme' : 'Cambiar recordatorio',
      texto: widget.existente == null
          ? '¿Cuándo empieza lo que querés ver en ${widget.canal.nombre}?'
          : '${widget.existente!.titulo(widget.canal)} en ${widget.canal.nombre}',
      hijo: Padding(
        padding: const EdgeInsets.only(top: 26),
        child: FocusTraversalGroup(
          child: Column(
            children: [
              AjusteTv(
                etiqueta: 'Día',
                valor: nombreDelDia(_dias[_dia], ahora),
                autofocus: true,
                alCambiar: (paso) => setState(() => _dia = (_dia + paso).clamp(0, _dias.length - 1)),
              ),
              AjusteTv(
                etiqueta: 'Hora',
                valor: _hora.toString().padLeft(2, '0'),
                alCambiar: (paso) => setState(() => _hora = (_hora + paso) % 24),
              ),
              AjusteTv(
                etiqueta: 'Minutos',
                valor: _minutos.toString().padLeft(2, '0'),
                alCambiar: (paso) => setState(() => _minutos = (_minutos + 5 * paso) % 60),
              ),
              AjusteTv(
                etiqueta: 'Repetir',
                valor: _semanal ? 'Todos los ${diaDeLaSemana(_cuando, plural: true)}' : 'Solo esa vez',
                alCambiar: (_) => setState(() => _semanal = !_semanal),
              ),
              const SizedBox(height: 14),
              Text(
                _yaPaso
                    ? 'Esa hora ya pasó: elegí otra.'
                    : '← → cambiar  ·  ↑ ↓ moverse  ·  Si la app está abierta, te avisamos cuando empiece.',
                textAlign: TextAlign.center,
                style: LetraTv.ayuda.copyWith(color: _yaPaso ? Tono.rubiClaro : null, fontSize: 16),
              ),
            ],
          ),
        ),
      ),
      botones: [
        BotonTv(texto: 'Guardar', principal: true, icono: Icons.check_rounded, alOk: _yaPaso ? null : _guardar),
        if (widget.existente != null) BotonTv(texto: 'Sacarlo', icono: Icons.delete_outline_rounded, alOk: _sacar),
        BotonTv(texto: 'Cancelar', alOk: () => Navigator.pop(context)),
      ],
    );
  }
}

/// Un renglón con un valor que se cambia con ← → (u OK, que avanza).
class AjusteTv extends StatefulWidget {
  const AjusteTv({
    super.key,
    required this.etiqueta,
    required this.valor,
    required this.alCambiar,
    this.autofocus = false,
  });

  final String etiqueta;
  final String valor;

  /// -1 (izquierda) o +1 (derecha / OK).
  final ValueChanged<int> alCambiar;
  final bool autofocus;

  @override
  State<AjusteTv> createState() => _AjusteTvState();
}

class _AjusteTvState extends State<AjusteTv> {
  bool _enfocado = false;

  KeyEventResult _tecla(KeyEvent evento) {
    if (evento is KeyUpEvent) return KeyEventResult.ignored;
    if (evento.logicalKey == LogicalKeyboardKey.arrowLeft) {
      widget.alCambiar(-1);
      return KeyEventResult.handled;
    }
    if (evento.logicalKey == LogicalKeyboardKey.arrowRight) {
      widget.alCambiar(1);
      return KeyEventResult.handled;
    }
    return KeyEventResult.ignored;
  }

  @override
  Widget build(BuildContext context) {
    final color = _enfocado ? Tono.celeste : Tono.textoApagado;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Enfocable(
        autofocus: widget.autofocus,
        escala: 1.02,
        alTecla: _tecla,
        alOk: () => widget.alCambiar(1),
        alEnfocar: (enfocado) => setState(() => _enfocado = enfocado),
        etiqueta: '${widget.etiqueta}: ${widget.valor}',
        child: Container(
          width: 560,
          padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 12),
          color: _enfocado ? Tono.capaAlta : Tono.capa,
          child: Row(
            children: [
              SizedBox(width: 130, child: Text(widget.etiqueta, style: LetraTv.cuerpo)),
              Icon(Icons.chevron_left_rounded, size: 30, color: color),
              Expanded(
                child: Text(
                  widget.valor,
                  textAlign: TextAlign.center,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: LetraTv.tarjeta.copyWith(fontSize: 22),
                ),
              ),
              Icon(Icons.chevron_right_rounded, size: 30, color: color),
            ],
          ),
        ),
      ),
    );
  }
}

/// La fila de Mi agenda en Inicio (nada si no hay nada anotado).
class FilaMiAgendaTv extends StatelessWidget {
  const FilaMiAgendaTv({super.key});

  @override
  Widget build(BuildContext context) {
    final catalogo = DatosScope.of(context).catalogo;
    return ValueListenableBuilder<int>(
      valueListenable: Recordatorios.cambios,
      builder: (context, _, _) => FilaTv(
        titulo: 'Mi agenda',
        icono: const Icon(Icons.event_rounded, color: Tono.celeste, size: 26),
        final_: 'OK: ver o cambiar',
        alto: 150,
        tarjetas: [
          for (final (recordatorio, canal) in Recordatorios.conCanal(catalogo))
            TarjetaRecordatorioTv(recordatorio: recordatorio, canal: canal),
        ],
      ),
    );
  }
}

class TarjetaRecordatorioTv extends StatelessWidget {
  const TarjetaRecordatorioTv({super.key, required this.recordatorio, required this.canal});

  final Recordatorio recordatorio;
  final Canal canal;

  @override
  Widget build(BuildContext context) {
    final enVivo = recordatorio.enVivo();
    return SizedBox(
      width: 360,
      height: 150,
      child: Enfocable(
        alOk: () => enVivo ? verCanalTv(context, canal) : recordarmeTv(context, canal: canal, existente: recordatorio),
        curva: Curva.tarjeta,
        etiqueta: '${recordatorio.cuandoTexto()}, ${recordatorio.titulo(canal)}, en ${canal.nombre}',
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
                      Expanded(
                        child: Text(
                          recordatorio.cuandoTexto(),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontFamily: Letra.texto,
                            fontSize: 17,
                            fontWeight: FontWeight.w700,
                            color: Tono.celeste,
                          ),
                        ),
                      ),
                    if (enVivo) const Spacer(),
                    Icon(
                      recordatorio.semanal ? Icons.repeat_rounded : Icons.notifications_active_rounded,
                      size: 22,
                      color: Tono.textoApagado,
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Text(
                  recordatorio.titulo(canal),
                  maxLines: 1,
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
                    SizedBox(width: 46, height: 30, child: LogoCanalTv(canal: canal, tamanioIniciales: 13)),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        canal.nombre,
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

/// "Empieza ...": algo anotado empezó con la app abierta. Devuelve true si eligió verlo.
class CartelEmpiezaTv extends StatelessWidget {
  const CartelEmpiezaTv({super.key, required this.recordatorio, required this.canal, required this.vez});

  final Recordatorio recordatorio;
  final Canal canal;
  final DateTime vez;

  @override
  Widget build(BuildContext context) {
    return DialogoTv(
      icono: Icons.notifications_active_rounded,
      titulo: 'Empieza ${recordatorio.titulo(canal)}',
      texto: 'A las ${hora(vez)} en ${canal.nombre}.',
      botones: [
        BotonTv(texto: 'Verlo', principal: true, autofocus: true, alOk: () => Navigator.pop(context, true)),
        BotonTv(texto: 'Ahora no', alOk: () => Navigator.pop(context, false)),
      ],
    );
  }
}
