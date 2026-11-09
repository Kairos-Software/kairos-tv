# descargas/

La **app Android (APK) para descargar** desde el panel y, solo para los
superusuarios, el **instalador para PC del analizador de canales** (ver abajo).

| Ruta | Quién | Para qué |
|---|---|---|
| `/descargar/` | **Cualquiera** (sin sesión) | Baja la última versión publicada. Corta a propósito: se escribe con el control remoto en la app *Downloader* de la TV. Sin un código de cliente válido la app no sirve, por eso es pública. |
| `/descargar/<id>/` | Cualquiera (las ocultas, solo quien publica) | Una versión puntual. |
| `/api/v1/app/` | Cualquiera | La última versión publicada (`version`, `notas`, `descarga`). La app la consulta al abrirse y, si la suya es más vieja, ofrece actualizar (ver `api/v1/app.py`). |
| `/app-android/` | Usuarios del panel (revendedores incluidos) | Link, instrucciones de instalación y, con `publicar_app`, subir versiones y ocultarlas. |

## Publicar una versión

1. Subir el número en `app_movil/pubspec.yaml` (`version: 1.0.1+2`).
2. `flutter build apk --release` (en `app_movil/`).
3. En el panel, `/app-android/` → subir `build/app/outputs/flutter-apk/app-release.apk`
   con la **misma versión** de `pubspec.yaml` (ej. `1.0.1`): la app compara ese
   número con el suyo para saber si hay una nueva. Lo que se escriba en
   "qué cambió" aparece en el cartel de la app.

Se valida que sea `.apk`, que sea de verdad una APK (un ZIP: empieza con
`PK`), que pese menos de 200 MB y que la versión no esté repetida. Los
archivos quedan en `media/apk/` (no van al repo).

## El analizador de canales para PC (solo superusuarios)

Para los superusuarios el menú dice **Descargas** y la página tiene dos
pestañas: *App Android* y *Analizador para PC* (`/app-android/?ver=analizador`).
Los revendedores y los otros roles no la ven (y las rutas les dan 403).

| Ruta | Quién | Para qué |
|---|---|---|
| `/app-android/?ver=analizador` | Superusuarios | Bajar el instalador, cómo instalarlo, las PCs donde está (versión, última consulta, «Desconectar») y publicar versiones |
| `/app-android/analizador/pedazo/`, `.../publicar/` | Superusuarios | La subida de a pedazos de 20 MB (`static/js/subir_analizador.js`: el instalador pesa cientos de MB y nginx acepta hasta 160 por pedido) y el final, que revisa que sea un `.exe` y calcula su huella |
| `/app-android/analizador/descargar/[<id>/]` | Superusuarios | El instalador (la última publicada o una puntual) |
| `/api/v1/analizador/`, `/api/v1/analizador/descargar/<id>/` | Un analizador instalado | Cuál es la última versión y bajarla, para actualizarse solo (`api/v1/analizador.py`) |

- Los instaladores van a `privado/analizador/` (`settings.ARCHIVOS_PRIVADOS`),
  **no** a `media/`, que nginx sirve a cualquiera. Salen solo por esas vistas.
- Un analizador instalado se presenta con la **huella (SHA-256) del instalador
  del que salió**: solo la tiene quien bajó un instalador del panel, y no se
  puede adivinar. Con su número de instalación queda anotado en
  `PcConAnalizador` (nombre de la PC, versión, última vez); una PC
  desconectada ya no recibe versiones nuevas.
- Se instala la publicada con el **número más alto** (la versión es la fecha y
  hora en que se armó). Ocultar una la saca de las PCs que todavía no la tienen.
- Cómo se arma el instalador y cómo se actualiza del lado de la PC:
  `analizador-canales/instalador/README.md`.

## Qué contiene

| Archivo | Para qué |
|---|---|
| `models.py` | `VersionApp`: versión, archivo, notas, publicada, quién y cuándo. `VersionAnalizador` (el instalador para PC, en `privado/`) y `PcConAnalizador` (migración 0002). |
| `analizador.py` | El instalador del analizador: juntar los pedazos, publicar, la huella y quién lo puede bajar. |
| `views.py`, `urls.py`, `forms.py`, `templates/` | La descarga pública y la página del panel (`_analizador.html`: la pestaña del analizador). |
| `admin.py` | Vista técnica en `/admin/`. |
| `tests/` | Subir, validar, descargar, ocultar y permisos; `test_analizador.py`, el analizador para PC (solo superusuarios, de a pedazos, la consulta con la huella, PCs desconectadas). |

## En producción

nginx tiene que aceptar archivos grandes en esa ruta
(`client_max_body_size 200m;`) y conviene que sirva `/media/` directamente.
El instalador del analizador no necesita nada más en nginx: se sube de a
pedazos de 20 MB y se baja por Django (nginx guarda la respuesta mientras se
entrega, así gunicorn queda libre enseguida). Hay que correr `migrate`
(descargas 0002).
