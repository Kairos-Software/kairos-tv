# app_movil/

**Kairos TV**: la app Android (celulares y televisores) del sistema, hecha con **Flutter** (lenguaje Dart). Muestra los
**canales de TV en vivo, películas y series** y, para los usuarios del panel, algunas herramientas de la web (perfil, usuarios, notificaciones)
hablando con la API de Django (`../api/`). No tiene datos ni reglas
propias: todo lo pide y lo valida el servidor.

```
Celular (esta app)  ──WiFi / internet──>  Django: /api/v1/...  ──>  PostgreSQL
```

## Qué contiene

| Carpeta / archivo | Para qué |
|---|---|
| `lib/` | **El código de la app** (lo único que se toca normalmente). Ver su README. |
| `test/` | Tests (`flutter test`). |
| `assets/` | Lo que va dentro de la app: `logo/` (logo e íconos) y `fuentes/` (Plus Jakarta Sans e Inter; Sora y Manrope para las herramientas del panel: perfil, usuarios y avisos). Cada una con su README. |
| `android/` | El proyecto Android que Flutter genera para compilar. Solo se toca para cosas de Android: permisos y nombre en `android/app/src/main/AndroidManifest.xml`, el id de la app en `android/app/build.gradle.kts`, la pantalla de arranque en `android/app/src/main/res/` (`drawable*/launch_background.xml`, `values*/styles.xml`). |
| `tools/generar_marca.py` | Dibuja logo, símbolo, íconos, pantalla de arranque y banner de Android TV (con las medidas de `lib/marca.dart`). |
| `pubspec.yaml` | Nombre, versión y **paquetes** que usa la app (como `requirements.txt`). |
| `pubspec.lock` | Versiones exactas instaladas (lo genera Flutter, va al repo). |
| `analysis_options.yaml` | Reglas de estilo que revisa `flutter analyze` (como `.flake8`). |
| `build/`, `.dart_tool/` | Generadas al compilar. No van al repo. |

## Dos formas de entrar

- **Código de 8 números** (lo que se ve primero, con teclado numérico en
  pantalla): los clientes. La app da una "señal" al servidor cada 5 minutos;
  si el servicio vence, muestra "Tu servicio venció" con el contacto de su
  vendedor (y al renovar sigue sin volver a poner el código). Si ya hay
  tantos aparatos conectados como pantallas pagadas, el nuevo ve "cuenta en uso".
- **Usuario y contraseña** ("Revendedores / administradores"): ven lo mismo
  que un cliente y, en el celular, sus herramientas en "Mi Espacio" (perfil,
  usuarios, avisos). El superusuario ve los canales sin créditos.

## Android TV

La misma APK se instala en celulares y en televisores Android / Google TV:

- `AndroidManifest.xml`: `leanback` y `touchscreen` como *no obligatorios*,
  la categoría `LEANBACK_LAUNCHER` (aparece en el menú de la TV) y el
  `android:banner` (`res/drawable-xhdpi/banner.png`, 320×180, sale de `tools/generar_marca.py`).
- En la TV la app tiene su propio diseño, pensado para el **control remoto**
  (`lib/tv/`, ver su README): menú a la izquierda, foco celeste bien visible,
  OK largo para favoritos, zapping con flechas y números, guía de canales.
- `MainActivity.kt` le pasa a Flutter el **nombre del aparato** (ej:
  "Philips 55PUD7406") y si es una TV (`lib/aparato.dart`). El nombre se ve
  en el panel, en "Dispositivos conectados" del cliente. Además pone el
  castellano como idioma preferido, mete en el reproductor de YouTube el
  script que elige el audio en castellano ("dentroDeYoutube": la API
  oficial de YouTube no deja cambiar el audio) y, en la TV, no deja que el reproductor de YouTube
  se quede con el foco del control remoto.

## Ver en la tele (teles que no son Android)

Desde el celular, el ícono de la tele de la barra de arriba conecta la app a una tele cualquiera **como segundo monitor**: la tele muestra la app con el diseño de TV y se maneja desde el celular. Sin cable, con "Transmitir pantalla / Smart View"; con cable, USB-C a HDMI. La tele no muestra nada más del teléfono. Ver `lib/tele/README.md`. La parte de Android es `PantallaTele.kt`.

Instalar en una TV: copiar la APK con un pendrive, o con la app *Downloader*
desde una dirección web (cuando esté en producción), o por la red:
`adb connect <ip-de-la-tv>` y `flutter install` / `adb install app-produccion-release.apk`
(en la TV: Ajustes → Preferencias del dispositivo → Opciones de desarrollador →
Depuración por red).

## Paquetes que usa

| Paquete | Para qué |
|---|---|
| `http` | Hacer los pedidos a la API. |
| `flutter_secure_storage` | Guardar el token cifrado en el celular (Keystore de Android). |
| `flutter_localizations` | Textos de Flutter (calendario, copiar/pegar) en español. |
| `video_player` | El reproductor de video (en Android usa ExoPlayer): HLS, DASH, video directo (MPEG-TS/MP4, el de las listas IPTV) y RTSP. Desde la 1.1.0; la 1.0.0 solo HLS. |
| `webview_flutter`, `webview_flutter_android` | El reproductor oficial de YouTube para las películas de canales oficiales (ver `lib/movil/reproductor_youtube.dart`). |
| `youtube_explode_dart` | Saca la dirección del video de YouTube en el aparato (ver `lib/senales.dart`). |
| `cronet_http` | El motor de red de Chrome: con él se le habla a YouTube, que rechaza (error 429) al cliente de red de Dart. `android/app/build.gradle.kts` fija `cronet-api` en la 119 (la 141 no compila con este Android Gradle). |
| `flutter_local_notifications`, `timezone` | Los avisos de "Avisarme" (la Agenda, `lib/movil/agenda.dart`): programados en Android, llegan aunque la app esté cerrada. Piden "desugaring" en `android/app/build.gradle.kts` y los receptores del `AndroidManifest.xml`; el ícono es `res/drawable/ic_aviso.xml` (y `res/raw/keep.xml` para que no se borre al armar la APK). |
| `wakelock_plus` | Que la pantalla no se apague mientras se mira un canal. |
| `flutter_launcher_icons` (solo desarrollo) | Genera los íconos de Android desde el logo: `dart run flutter_launcher_icons`. |

Agregar uno: `flutter pub add <paquete>` (como `pip install`).

## Cómo probarla

1. Django escuchando en la red (no solo en la PC):
   ```
   python manage.py runserver 0.0.0.0:8000
   ```
   La IP de la PC tiene que estar en `ALLOWED_HOSTS` del `.env.local`. Si
   Windows pregunta por el firewall, permitir el acceso en redes privadas.
2. El celular conectado por USB (con depuración USB activada) y en el mismo WiFi.
3. Desde esta carpeta:
   ```
   flutter run --flavor local
   ```
   Instala la app y la abre. Con la app abierta, al guardar un cambio en el
   código y apretar `r` en la terminal, se actualiza al instante (hot reload).

## Las dos versiones: producción y local

Hay dos apps distintas (`android/app/build.gradle.kts`, `lib/config.dart`):

| | Producción | Local |
|---|---|---|
| Nombre en el aparato | Kairos TV | Kairos TV Local |
| Habla con | `https://kairostv.grupokairosarg.com` (fijo: no se puede cambiar ni se ve en la app) | La PC (`192.168.1.241:8000`, o la que se le diga con `--dart-define=API_URL=...`) |
| Se arma con | `flutter build apk --release` | `flutter build apk --release --flavor local` |
| Archivo | `build/app/outputs/flutter-apk/app-produccion-release.apk` | `build/app/outputs/flutter-apk/app-local-release.apk` |

Se pueden tener **las dos instaladas a la vez** en el mismo aparato: tienen
distinto identificador, así que la local nunca reemplaza a la de producción ni
recibe sus actualizaciones. Para probar en el celular conectado:
`flutter run --flavor local`.

**Para publicar se usa SIEMPRE la de producción** (la que sale sin `--flavor`).
`test/config_test.dart` falla si alguna vez apunta a otro lado.

## Generar la APK

**Una sola vez:** crear la clave de firma y el archivo `android/key.properties`
(copiando `android/key.properties.ejemplo`). La clave (`.jks`) se guarda **fuera
del proyecto y con copia de seguridad**: todas las versiones de la app se firman
con ella, y sin ella no se pueden publicar actualizaciones (sin `key.properties`
sale firmada con la clave de desarrollo y después no se puede actualizar sin
desinstalar).

`usesCleartextTraffic` del `AndroidManifest.xml` se deja en `true` también en
producción: muchas fuentes de canales son `http://` y sin eso no reproducen.

## Publicar una versión nueva

1. En `pubspec.yaml` subir `version:`. Ej: de `1.0.0+1` a `1.0.1+2`.
   - `1.0.1` es lo que ve la gente.
   - `+2` es el número interno: **tiene que ser mayor que el anterior** o
     Android no instala la actualización ("App no instalada").
2. Compilar (en `app_movil/`), la de producción:
   ```
   flutter build apk --release
   ```
3. Verificar que salió firmada con la clave propia (tiene que decir `CN=marcos andres lopez`):
   ```
   & "$env:LOCALAPPDATA\Android\Sdk\build-tools\36.0.0\apksigner.bat" verify --print-certs build\app\outputs\flutter-apk\app-produccion-release.apk
   ```
4. Panel de producción → **App Android** → subir `build\app\outputs\flutter-apk\app-produccion-release.apk`
   con la misma versión del paso 1 (ej. `1.0.1`). **Tiene que ser exactamente la
   misma** (sin el `+2`): la app compara ese número con el suyo para avisar que hay
   una nueva. Lo que escribas en "qué cambió" aparece en el cartel.
5. Commit y push del cambio de `pubspec.yaml`, para que el repo sepa qué versión está publicada.

Desde la 1.1.0 la app **avisa sola**: al abrirse (y al volver a ella, cada 6 horas)
le pregunta al servidor la última versión (`/api/v1/app/`). Si la suya es más vieja,
muestra "Hay una versión nueva" → **Actualizar**: la baja y abre el instalador de
Android. Se instala encima, sin perder el login (`lib/actualizacion.dart`). La
primera vez Android pide permiso para "instalar apps de este origen".

Las que tienen la 1.0.0 no traen el aviso: esas se actualizan a mano, bajándola
desde `/descargar/` e instalándola encima.

## Comandos útiles

| Comando | Qué hace |
|---|---|
| `flutter run --flavor local` | Instala y abre la versión local en el celular conectado |
| `flutter build apk --release` | Genera la APK de producción (`build/app/outputs/flutter-apk/app-produccion-release.apk`) |
| `flutter test` | Corre los tests |
| `flutter test test_vista/vista_test.dart` | Dibuja pantallas a PNG en `build/vista/` para mirarlas sin instalar (ver `test_vista/README.md`) |
| `flutter analyze` | Revisa el código buscando errores |
| `flutter pub get` | Instala los paquetes de `pubspec.yaml` (después de clonar el repo) |
| `flutter doctor` | Revisa que las herramientas estén bien instaladas |
