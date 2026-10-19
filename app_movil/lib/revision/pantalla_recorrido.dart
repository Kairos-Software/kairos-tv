/// "Revisar canales": la pantalla del modo revisión ([Recorrido]). La misma en
/// el celular (Mi Espacio → Panel) y en la TV (Mi cuenta), para los usuarios
/// del panel que pueden cargar canales.
///
/// Un botón grande (Empezar / Parar), el canal que se está probando con su
/// video chiquito y sin sonido, cuántos anduvieron y cuántos no, y lo último
/// que se probó con el motivo. Mientras recorre, la pantalla no se apaga.
library;

import 'package:flutter/material.dart';
import 'package:video_player/video_player.dart';
import 'package:wakelock_plus/wakelock_plus.dart';

import '../aparato.dart';
import '../movil/estilo.dart';
import '../sesion.dart';
import 'recorrido.dart';

class PantallaRecorrido extends StatefulWidget {
  const PantallaRecorrido({super.key, this.recorrido});

  /// Para las pruebas (sin servidor ni reproductor de verdad).
  final Recorrido? recorrido;

  @override
  State<PantallaRecorrido> createState() => _PantallaRecorridoState();
}

class _PantallaRecorridoState extends State<PantallaRecorrido> {
  Recorrido? _recorrido;
  bool _pantallaPrendida = false;

  Recorrido get recorrido => _recorrido!;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _recorrido ??= (widget.recorrido ??
        Recorrido(ServidorEnLaApi(SesionScope.of(context).api), probarConElReproductor))
      ..addListener(_cambio);
  }

  void _cambio() {
    // La pantalla queda prendida solo mientras recorre
    if (recorrido.corriendo != _pantallaPrendida) {
      _pantallaPrendida = recorrido.corriendo;
      (_pantallaPrendida ? WakelockPlus.enable() : WakelockPlus.disable()).catchError((Object _) {});
    }
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    if (_pantallaPrendida) WakelockPlus.disable().catchError((Object _) {});
    recorrido.removeListener(_cambio);
    if (widget.recorrido == null) recorrido.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final tv = Aparato.esTv;
    final titulo = tv ? LetraTv.pantalla : Letra.titulo;
    final cuerpo = tv ? LetraTv.cuerpo : Letra.cuerpo;
    final r = recorrido;
    return Scaffold(
      backgroundColor: Tono.fondo,
      appBar: tv ? null : AppBar(title: const Text('Revisar canales')),
      body: SafeArea(
        child: ListView(
          padding: EdgeInsets.all(tv ? 48 : Espacio.margen),
          children: [
            if (tv) ...[Text('Revisar canales', style: titulo), const SizedBox(height: 12)],
            Text(
              'Este aparato prueba solo, uno por uno, los canales que el servidor no puede probar o que están '
              'fallando, igual que si los abriera un cliente. Dejalo enchufado, con internet y en esta pantalla '
              '(por ejemplo, de noche). Va de a un canal por vez y sin sonido.',
              style: cuerpo,
            ),
            const SizedBox(height: Espacio.lg),
            Wrap(
              spacing: Espacio.margen,
              runSpacing: Espacio.sm,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                FilledButton.icon(
                  key: const Key('recorrido-boton'),
                  autofocus: true,
                  style: FilledButton.styleFrom(
                    backgroundColor: r.corriendo ? Tono.rubi : Tono.celeste,
                    foregroundColor: r.corriendo ? Tono.sobreRubi : Tono.sobreCelesteOscuro,
                    padding: EdgeInsets.symmetric(horizontal: tv ? 36 : 24, vertical: tv ? 20 : 14),
                  ),
                  onPressed: r.corriendo ? r.parar : r.empezar,
                  icon: Icon(r.corriendo ? Icons.stop_rounded : Icons.play_arrow_rounded),
                  label: Text(r.corriendo ? 'Parar' : (r.probadas > 0 ? 'Seguir' : 'Empezar')),
                ),
                Text(r.estado, style: cuerpo.copyWith(color: Tono.texto)),
              ],
            ),
            const SizedBox(height: Espacio.lg),
            LayoutBuilder(
              builder: (context, medidas) {
                final ancho = medidas.maxWidth > 700;
                final pantalla = _Pantallita(video: r.video, canal: r.actual?.canal ?? '', corriendo: r.corriendo);
                final numeros = _Numeros(recorrido: r, estilo: cuerpo);
                return ancho
                    ? Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          SizedBox(width: medidas.maxWidth * .45, child: pantalla),
                          const SizedBox(width: Espacio.lg),
                          Expanded(child: numeros),
                        ],
                      )
                    : Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [pantalla, const SizedBox(height: Espacio.margen), numeros],
                      );
              },
            ),
          ],
        ),
      ),
    );
  }
}

/// El video que se está probando (chiquito y sin sonido).
class _Pantallita extends StatelessWidget {
  const _Pantallita({required this.video, required this.canal, required this.corriendo});

  final VideoPlayerController? video;
  final String canal;
  final bool corriendo;

  @override
  Widget build(BuildContext context) {
    final actual = video;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(Curva.tarjeta),
          child: AspectRatio(
            aspectRatio: 16 / 9,
            child: ColoredBox(
              color: Tono.capaMinima,
              child: actual != null && actual.value.isInitialized
                  ? FittedBox(
                      fit: BoxFit.contain,
                      child: SizedBox(
                        width: actual.value.size.isEmpty ? 16 : actual.value.size.width,
                        height: actual.value.size.isEmpty ? 9 : actual.value.size.height,
                        child: VideoPlayer(actual),
                      ),
                    )
                  : Center(
                      child: corriendo
                          ? const CircularProgressIndicator(color: Tono.celeste)
                          : const Icon(Icons.fact_check_rounded, size: 48, color: Tono.textoApagado),
                    ),
            ),
          ),
        ),
        if (canal.isNotEmpty) ...[
          const SizedBox(height: Espacio.sm),
          Text(canal, style: Letra.etiqueta.copyWith(fontSize: 15), maxLines: 2, overflow: TextOverflow.ellipsis),
        ],
      ],
    );
  }
}

/// Cuántos anduvieron, cuántos no, cuántos faltan y lo último que se probó.
class _Numeros extends StatelessWidget {
  const _Numeros({required this.recorrido, required this.estilo});

  final Recorrido recorrido;
  final TextStyle estilo;

  @override
  Widget build(BuildContext context) {
    final r = recorrido;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Wrap(
          spacing: Espacio.lg,
          runSpacing: Espacio.sm,
          children: [
            _Numero('Andan', r.andan, Tono.celeste),
            _Numero('No andan', r.fallan, Tono.rubiClaro),
            if (r.quedan != null) _Numero('Faltan', r.quedan!, Tono.textoSuave),
          ],
        ),
        if (r.ultimos.isNotEmpty) ...[
          const SizedBox(height: Espacio.margen),
          Text('Lo último que se probó', style: Letra.etiqueta.copyWith(color: Tono.textoSuave)),
          const SizedBox(height: Espacio.xs),
          for (final p in r.ultimos)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 3),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(
                    p.prueba.anduvo ? Icons.check_circle_rounded : Icons.cancel_rounded,
                    size: 18,
                    color: p.prueba.anduvo ? Tono.celeste : Tono.rubiClaro,
                  ),
                  const SizedBox(width: Espacio.sm),
                  Expanded(
                    child: Text(
                      p.prueba.anduvo ? p.canal : '${p.canal}: ${p.prueba.mensaje}',
                      style: estilo,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
              ),
            ),
        ],
        const SizedBox(height: Espacio.margen),
        Text(
          'Lo que encuentra se ve en el panel: Contenido → Para revisar. Lo que anda vuelve solo a la app.',
          style: estilo.copyWith(color: Tono.textoApagado),
        ),
      ],
    );
  }
}

class _Numero extends StatelessWidget {
  const _Numero(this.texto, this.cantidad, this.color);

  final String texto;
  final int cantidad;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('$cantidad', style: Letra.numeros.copyWith(color: color)),
        Text(texto, style: Letra.mini.copyWith(color: Tono.textoSuave)),
      ],
    );
  }
}
