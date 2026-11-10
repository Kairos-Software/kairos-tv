/// Punto de entrada de la app (como manage.py / wsgi.py en Django).
library;

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:video_player_media_kit/video_player_media_kit.dart';

import 'acceso.dart';
import 'actualizacion.dart';
import 'aparato.dart';
import 'bienvenida.dart';
import 'config.dart';
import 'movil/recordatorios.dart';
import 'movil/estructura.dart';
import 'pantallas/perfil.dart';
import 'pc.dart';
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
  // La app de PC: el video lo reproduce media_kit (mpv), que abre lo mismo que el de Android con sus
  // arreglos (TS, HLS, MP2, Dolby, DTS). En Android no se toca: sigue el reproductor de Android.
  if (Platform.isWindows) VideoPlayerMediaKit.ensureInitialized(windows: true);
  await Aparato.cargar();
  final sesion = Sesion();
  sesion.alSalir = () => claveNavegador.currentState?.popUntil((ruta) => ruta.isFirst);
  sesion.iniciar();
  // "Ver en la tele": si se conecta una tele como pantalla (lib/tele/)
  Tele.instancia.escuchar();
  // "Mi agenda": lo que cada uno anotó con "Recordarme" (en el celular, con avisos de Android)
  Recordatorios.iniciar();
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
      // En la PC: Esc vuelve (el "Atrás" del control), F11 pantalla completa, y las listas se arrastran con el
      // mouse (lib/pc.dart). En Android quedan los de siempre.
      shortcuts: Aparato.esPc ? atajosDePc : null,
      actions: Aparato.esPc ? accionesDePc(claveNavegador) : null,
      scrollBehavior: Aparato.esPc ? const ScrollDePc() : null,
      // En la TV todo se dibuja en 1920×1080 (las medidas del diseño) y se escala a la pantalla
      builder: (context, hijo) => Aparato.esTv
          ? EscalaTv(
              child: Aparato.esPc ? MouseDePc(navegador: claveNavegador, child: hijo!) : hijo!,
            )
          : hijo!,
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
