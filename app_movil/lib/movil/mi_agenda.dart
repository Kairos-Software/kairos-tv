/// "Mi agenda" en el CELULAR (los datos y los avisos: recordatorios.dart):
///
///   - BotonRecordarme: la campanita de cada canal en En Vivo (encendida si
///     hay algo anotado en ese canal). Abre la hoja "Recordarme".
///   - hojaRecordarme: qué va a ver (opcional), el día, la hora y si se repite
///     todas las semanas. También cambia o borra uno anotado.
///   - FilaMiAgenda: en Inicio, lo anotado (solo si hay algo). "Ver todo"
///     abre PantallaMiAgenda.
///   - PantallaMiAgenda: todo, por día, con "Anotar algo" (elegir el canal en
///     la guía). También se abre desde Mi Espacio.
library;

import 'package:flutter/material.dart';

import '../api/modelos.dart';
import 'componentes.dart';
import 'datos.dart';
import 'estilo.dart';
import 'guia.dart';
import 'recordatorios.dart';

/// La campanita de un canal.
class BotonRecordarme extends StatelessWidget {
  const BotonRecordarme({super.key, required this.canal});

  final Canal canal;

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<int>(
      valueListenable: Recordatorios.cambios,
      builder: (context, _, _) {
        final tiene = Recordatorios.tiene(canal);
        return BotonRedondo(
          icono: tiene ? Icons.notifications_active_rounded : Icons.notifications_none_rounded,
          tamanio: 36,
          tamanioIcono: 18,
          fondo: Tono.capaMinima,
          color: tiene ? Tono.celeste : Tono.textoSuave,
          ayuda: 'Recordarme algo en este canal',
          alTocar: () => hojaRecordarme(context, canal: canal),
        );
      },
    );
  }
}

/// "Recordarme" en [canal]. Con [existente], lo cambia (o lo borra).
Future<void> hojaRecordarme(BuildContext context, {required Canal canal, Recordatorio? existente}) {
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Tono.capaBaja,
    builder: (_) => HojaRecordarme(canal: canal, existente: existente),
  );
}

/// El contenido de la hoja (público para dibujarlo en test_vista).
class HojaRecordarme extends StatefulWidget {
  const HojaRecordarme({super.key, required this.canal, this.existente});

  final Canal canal;
  final Recordatorio? existente;

  @override
  State<HojaRecordarme> createState() => HojaRecordarmeEstado();
}

class HojaRecordarmeEstado extends State<HojaRecordarme> {
  late final _nombre = TextEditingController(text: widget.existente?.nombre ?? '');
  late DateTime _dia;
  late TimeOfDay _hora;
  late bool _semanal = widget.existente?.semanal ?? false;

  @override
  void initState() {
    super.initState();
    final ahora = DateTime.now();
    // Uno nuevo: la próxima hora en punto (a las 23:10, mañana a las 00:00)
    final cuando = widget.existente?.proxima(ahora) ?? DateTime(ahora.year, ahora.month, ahora.day, ahora.hour + 1);
    _dia = DateTime(cuando.year, cuando.month, cuando.day);
    _hora = TimeOfDay(hour: cuando.hour, minute: cuando.minute);
  }

  @override
  void dispose() {
    _nombre.dispose();
    super.dispose();
  }

  DateTime get _cuando => DateTime(_dia.year, _dia.month, _dia.day, _hora.hour, _hora.minute);

  /// Una sola vez y ya pasó: no se puede guardar.
  bool get _yaPaso => !_semanal && !_cuando.isAfter(DateTime.now());

  Future<void> _elegirHora() async {
    final elegida = await showTimePicker(
      context: context,
      initialTime: _hora,
      helpText: '¿A qué hora empieza?',
      cancelText: 'Cancelar',
      confirmText: 'Listo',
      builder: (context, hijo) =>
          MediaQuery(data: MediaQuery.of(context).copyWith(alwaysUse24HourFormat: true), child: hijo!),
    );
    if (elegida != null && mounted) setState(() => _hora = elegida);
  }

  Future<void> _guardar() async {
    final mensajero = ScaffoldMessenger.maybeOf(context);
    final navegador = Navigator.of(context);
    final recordatorio = Recordatorio(
      id: widget.existente?.id ?? Recordatorios.nuevoId(),
      canal: widget.canal.id,
      cuando: _cuando,
      nombre: _nombre.text.trim(),
      semanal: _semanal,
      nombreDelCanal: widget.canal.nombre,
    );
    await Recordatorios.guardar(recordatorio);
    navegador.pop();
    mensajero
      ?..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(
            'Listo: ${recordatorio.cuandoTexto().replaceFirst('Todos', 'todos')}. '
            'Te avisamos ${Recordatorios.anticipacion.inMinutes} minutos antes.',
          ),
        ),
      );
  }

  Future<void> _borrar() async {
    final mensajero = ScaffoldMessenger.maybeOf(context);
    Navigator.of(context).pop();
    await Recordatorios.borrar(widget.existente!.id);
    mensajero
      ?..hideCurrentSnackBar()
      ..showSnackBar(const SnackBar(content: Text('Listo, lo sacamos de tu agenda.')));
  }

  @override
  Widget build(BuildContext context) {
    final hoy = DateTime.now();
    final dias = [for (var i = 0; i < 7; i++) DateTime(hoy.year, hoy.month, hoy.day + i)];
    if (!dias.contains(_dia)) dias.add(_dia);
    Widget subtitulo(String texto) => Padding(
      padding: const EdgeInsets.fromLTRB(0, Espacio.lg, 0, 10),
      child: Text(texto, style: Letra.titulo.copyWith(fontSize: 15)),
    );

    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
      child: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(20, 20, 20, 16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  ClipRRect(
                    borderRadius: BorderRadius.circular(Curva.medio),
                    child: SizedBox(
                      width: 52,
                      height: 38,
                      child: Imagen(
                        url: widget.canal.logo,
                        nombre: widget.canal.nombre,
                        ajuste: BoxFit.contain,
                        relleno: const EdgeInsets.all(4),
                        fondo: Tono.capaAlta,
                        tamanioIniciales: 13,
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(widget.existente == null ? 'Recordarme' : 'Cambiar recordatorio', style: Letra.titulo),
                        Text(widget.canal.nombre, maxLines: 1, overflow: TextOverflow.ellipsis, style: Letra.cuerpo),
                      ],
                    ),
                  ),
                ],
              ),
              subtitulo('¿Qué vas a ver?'),
              TextField(
                controller: _nombre,
                maxLength: 60,
                textCapitalization: TextCapitalization.sentences,
                style: Letra.cuerpoGrande,
                decoration: const InputDecoration(
                  hintText: 'Ej: Boca vs River (opcional)',
                  counterText: '',
                  filled: true,
                  fillColor: Tono.capa,
                  border: OutlineInputBorder(borderSide: BorderSide.none),
                ),
              ),
              subtitulo('¿Qué día?'),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final dia in dias)
                    ChipFiltro(
                      texto: nombreDelDia(dia, hoy),
                      activo: dia == _dia,
                      alTocar: () => setState(() => _dia = dia),
                    ),
                ],
              ),
              subtitulo('¿A qué hora empieza?'),
              OutlinedButton.icon(
                onPressed: _elegirHora,
                style: OutlinedButton.styleFrom(
                  foregroundColor: Tono.celeste,
                  side: const BorderSide(color: Tono.celeste),
                  padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
                ),
                icon: const Icon(Icons.schedule_rounded),
                label: Text(hora(_cuando), style: Letra.titulo.copyWith(color: Tono.celeste)),
              ),
              const SizedBox(height: Espacio.sm),
              SwitchListTile(
                value: _semanal,
                onChanged: (valor) => setState(() => _semanal = valor),
                contentPadding: EdgeInsets.zero,
                activeThumbColor: Tono.celeste,
                title: Text('Todas las semanas', style: Letra.etiqueta.copyWith(fontSize: 14)),
                subtitle: Text('Cada ${diaDeLaSemana(_dia)} a las ${hora(_cuando)}.', style: Letra.cuerpo),
              ),
              const SizedBox(height: Espacio.sm),
              Text(
                _yaPaso
                    ? 'Esa hora ya pasó: elegí otra.'
                    : 'Te avisamos ${Recordatorios.anticipacion.inMinutes} minutos antes, aunque la app esté cerrada. '
                          'Tocás el aviso y se abre este canal.',
                style: Letra.cuerpo.copyWith(color: _yaPaso ? Tono.rubiClaro : Tono.textoSuave),
              ),
              const SizedBox(height: Espacio.lg),
              BotonPrincipal(
                texto: 'Guardar',
                icono: Icons.notifications_active_rounded,
                tamanioTexto: 14,
                alTocar: _yaPaso ? null : _guardar,
              ),
              if (widget.existente != null) ...[
                const SizedBox(height: Espacio.sm),
                Center(
                  child: TextButton.icon(
                    onPressed: _borrar,
                    style: TextButton.styleFrom(foregroundColor: Tono.rubiClaro),
                    icon: const Icon(Icons.delete_outline_rounded),
                    label: const Text('Sacarlo de mi agenda'),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

/// En Inicio: lo anotado (si hay algo).
class FilaMiAgenda extends StatelessWidget {
  const FilaMiAgenda({super.key});

  @override
  Widget build(BuildContext context) {
    final catalogo = DatosScope.of(context).catalogo;
    return ValueListenableBuilder<int>(
      valueListenable: Recordatorios.cambios,
      builder: (context, _, _) {
        final anotados = Recordatorios.conCanal(catalogo);
        if (anotados.isEmpty) return const SizedBox.shrink();
        return Padding(
          padding: const EdgeInsets.only(bottom: 28),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              EncabezadoSeccion(
                titulo: 'Mi agenda',
                icono: const Icon(Icons.event_rounded, size: 20, color: Tono.celeste),
                final_: VerTodo(alTocar: () => abrirPantalla<void>(context, const PantallaMiAgenda())),
              ),
              SizedBox(
                height: 150,
                child: ListView.separated(
                  scrollDirection: Axis.horizontal,
                  padding: const EdgeInsets.symmetric(horizontal: Espacio.margen),
                  itemCount: anotados.length,
                  separatorBuilder: (_, _) => const SizedBox(width: Espacio.sm),
                  itemBuilder: (_, i) => SizedBox(
                    width: 280,
                    child: Align(
                      alignment: Alignment.topCenter,
                      child: TarjetaRecordatorio(recordatorio: anotados[i].$1, canal: anotados[i].$2),
                    ),
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

/// Todo lo anotado, por día.
class PantallaMiAgenda extends StatelessWidget {
  const PantallaMiAgenda({super.key});

  void _anotar(BuildContext context) {
    // Primero el canal (la guía se cierra sola al elegir), después la hoja
    abrirPantalla<void>(context, PantallaGuia(alElegir: (canal) => hojaRecordarme(context, canal: canal)));
  }

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
          'MI AGENDA',
          style: Letra.etiqueta.copyWith(color: Tono.celesteClaro, fontWeight: FontWeight.w700, letterSpacing: 1.2),
        ),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _anotar(context),
        backgroundColor: Tono.celeste,
        foregroundColor: Tono.sobreCelesteOscuro,
        icon: const Icon(Icons.add_alert_rounded),
        label: const Text('Anotar algo'),
      ),
      body: ListenableBuilder(
        listenable: Listenable.merge([catalogo, Recordatorios.cambios]),
        builder: (context, _) {
          final anotados = Recordatorios.conCanal(catalogo);
          if (anotados.isEmpty) {
            return const Vacio(
              icono: Icons.event_note_rounded,
              texto:
                  'Todavía no anotaste nada.\n\nEn En Vivo, tocá la campanita de un canal y elegí el día y la hora: '
                  'te avisamos 5 minutos antes de que empiece.',
            );
          }
          final ahora = DateTime.now();
          final filas = <Widget>[];
          String? dia;
          for (final (recordatorio, canal) in anotados) {
            final este = recordatorio.enVivo(ahora) ? 'Ahora' : nombreDelDia(recordatorio.proxima(ahora), ahora);
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
                child: TarjetaRecordatorio(recordatorio: recordatorio, canal: canal, conDia: false),
              ),
            );
          }
          return ListView(padding: const EdgeInsets.only(bottom: 100), children: filas);
        },
      ),
    );
  }
}

/// Uno anotado: cuándo (o EN VIVO), qué y el canal. Tocarlo lo cambia; si se
/// está dando, "Ver".
class TarjetaRecordatorio extends StatelessWidget {
  const TarjetaRecordatorio({super.key, required this.recordatorio, required this.canal, this.conDia = true});

  final Recordatorio recordatorio;
  final Canal canal;

  /// false = solo la hora (los que no se repiten, en Mi agenda completa).
  final bool conDia;

  @override
  Widget build(BuildContext context) {
    final enVivo = recordatorio.enVivo();
    return Material(
      color: Tono.capaBaja,
      borderRadius: BorderRadius.circular(Curva.tarjeta),
      child: InkWell(
        onTap: () => hojaRecordarme(context, canal: canal, existente: recordatorio),
        borderRadius: BorderRadius.circular(Curva.tarjeta),
        child: Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(Curva.tarjeta),
            border: Border.all(
              color: enVivo ? Tono.rubi.withValues(alpha: .55) : Tono.bordeSuave.withValues(alpha: .5),
            ),
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
                    Expanded(
                      child: Text(
                        // En Mi agenda completa el día ya está arriba (en el título del grupo)
                        conDia || recordatorio.semanal ? recordatorio.cuandoTexto() : hora(recordatorio.proxima()),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: Letra.etiqueta.copyWith(color: Tono.celeste, fontWeight: FontWeight.w700),
                      ),
                    ),
                  if (enVivo) const Spacer(),
                  Icon(
                    recordatorio.semanal ? Icons.repeat_rounded : Icons.notifications_active_rounded,
                    size: 18,
                    color: Tono.textoApagado,
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                recordatorio.titulo(canal),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: Letra.cuerpoGrande.copyWith(fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  ClipRRect(
                    borderRadius: BorderRadius.circular(6),
                    child: SizedBox(
                      width: 44,
                      height: 30,
                      child: Imagen(
                        url: canal.logo,
                        nombre: canal.nombre,
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
                      canal.nombre,
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
                        alTocar: () => Recordatorios.canalPedido.value = canal.id,
                      ),
                    )
                  else
                    const Icon(Icons.edit_rounded, size: 18, color: Tono.textoApagado),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
