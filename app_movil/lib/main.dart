/// Punto de entrada de la app (como manage.py / wsgi.py en Django).
library;

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'acceso.dart';
import 'actualizacion.dart';
import 'aparato.dart';
import 'bienvenida.dart';
import 'config.dart';
import 'movil/agenda.dart';
import 'movil/estructura.dart';
import 'pantallas/perfil.dart';
import 'sesion.dart';
import 'tele/en_la_tele.dart';
import 'tele/enlace.dart';
import 'tema.dart';
import 'tv/escala.dart';
import 'tv/estructura.dart';

/// Permite volver a la primera pantalla desde cualquier lado (ej: al vencer la sesión).
final claveNavegador = GlobalKey<NavigatorState>();

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Aparato.cargar();
  final sesion = Sesion();
  sesion.alSalir = () => claveNavegador.currentState?.popUntil((ruta) => ruta.isFirst);
  sesion.iniciar();
  // "Ver en la tele": si se conecta una tele como pantalla (lib/tele/)
  Tele.instancia.escuchar();
  // "Avisarme" de la Agenda (lo marcado y, en el celular, los avisos de Android)
  Avisos.iniciar();
  runApp(
    SesionScope(
      sesion: sesion,
      // El aviso "Hay una versión nueva" (lib/actualizacion.dart)
      // La presentación en video al abrir (lib/bienvenida.dart), encima de todo
      child: Bienvenida(
        child: VigilarActualizacion(sesion: sesion, navegador: claveNavegador, child: const App()),
      ),
    ),
  );
}

/// La app en la TELE, cuando el celular se conecta a una como pantalla
/// ("Ver en la tele", lib/tele/). La arranca Android (PantallaTele.kt) en un
/// segundo motor de Flutter: no pasa por main().
@pragma('vm:entry-point')
Future<void> pantallaTele() => iniciarTele();

class App extends StatelessWidget {
  const App({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: nombreSistema,
      navigatorKey: claveNavegador,
      debugShowCheckedModeBanner: false,
      theme: temaDeLaApp(),
      // Textos de Flutter (calendario, copiar/pegar...) en español
      locale: const Locale('es', 'AR'),
      supportedLocales: const [Locale('es', 'AR'), Locale('es')],
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
      // En la TV todo se dibuja en 1920×1080 (las medidas del diseño) y se escala a la pantalla
      builder: (context, hijo) => Aparato.esTv ? EscalaTv(child: hijo!) : hijo!,
      home: const Raiz(),
    );
  }
}

/// Decide qué mostrar según la sesión (como el @login_required de Django).
class Raiz extends StatelessWidget {
  const Raiz({super.key});

  @override
  Widget build(BuildContext context) {
    final sesion = SesionScope.of(context);
    switch (sesion.estado) {
      case EstadoSesion.cargando:
        return const PantallaCarga();
      case EstadoSesion.sinConexion:
        return const PantallaSinConexion();
      case EstadoSesion.sinSesion:
        return const PantallaAcceso();
      case EstadoSesion.sinServicio:
        return const PantallaServicioVencido();
      case EstadoSesion.conSesion:
        // Un administrador le asignó una contraseña temporal: primero tiene que cambiarla
        if (!sesion.esCliente && sesion.perfil!.debeCambiarPassword) {
          return const PantallaCambiarPassword(obligatorio: true);
        }
        // Celular (lib/movil/) o TV (lib/tv/): el mismo diseño, cada uno a su medida.
        // Los clientes y los usuarios del panel ven lo mismo; estos últimos tienen
        // además sus herramientas en "Mi Espacio" del celular.
        return Aparato.esTv ? const PantallaTv() : const PantallaMovil();
    }
  }
}
