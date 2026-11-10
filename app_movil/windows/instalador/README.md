# windows/instalador/

El **instalador de Kairos TV para PC** (`KairosTV-<versión>.exe`), el que se sube
al panel en **Descargas → App para PC** y que las PCs con la app bajan solas
para actualizarse.

| Archivo | Qué es |
|---|---|
| `armar.ps1` | Lo arma todo: compila la app con la versión del momento, junta lo necesario y corre Inno Setup. |
| `kairos_tv.iss` | El guion de Inno Setup 6 (el mismo programa que arma el instalador del analizador). No se compila a mano: lo llama `armar.ps1`. |

## Armarlo

Parado en `app_movil`:

```powershell
powershell -ExecutionPolicy Bypass -File windows\instalador\armar.ps1
```

Sale en `build\instalador\KairosTV-<versión>.exe` (con su tamaño y su huella).
Tarda unos minutos. Hace falta lo de `windows/README.md` (Visual Studio con C++,
el modo para programadores) más **Inno Setup 6**
(`winget install JRSoftware.InnoSetup --scope user`). Usa la unidad `K:` para la
ruta corta (la crea si no está).

- **La versión** es la fecha y la hora del armado (`2026.11.10.1530`): cada
  instalador sale con un número nuevo y más alto, que es lo que comparan el
  panel y la app. **No toca la versión de la APK** (`pubspec.yaml`): se le pasa a
  Flutter solo para este armado (`--build-name 2026.11.10 --build-number 1530`).
- Lleva las **bibliotecas de C++ de Microsoft** que usan la app y el
  reproductor (`msvcp140`, `vcruntime140`, `vcruntime140_1`), al lado del
  programa: no hay que instalar nada aparte ni pedir permiso de administrador.

## Qué hace al instalar

- Se instala **solo para el usuario**, sin permiso de administrador, en
  `%LOCALAPPDATA%\Programs\Kairos TV`, con "Kairos TV" en el menú Inicio y (si se
  deja marcado) en el escritorio. Se desinstala desde Configuración → Aplicaciones.
- La sesión y lo guardado (catálogo, favoritos) están en `%APPDATA%\Kairos
  Software`: no se tocan al actualizar ni al desinstalar.
- Si la app está abierta, espera a que se cierre (su marca "KairosTVAbierta",
  `windows/runner/main.cpp`): a mano lo pide; en silencio espera hasta 1 minuto.
- Al terminar abre la app. `/SINABRIR=1` no la abre (para probarlo).
- **No está firmado**: el navegador y Windows avisan que no lo conocen ("Más
  información → Ejecutar de todas formas"). Con el *Control inteligente de
  aplicaciones* de Windows 11 prendido no deja: hay que apagarlo antes. Algunos
  antivirus (McAfee) lo ponen en cuarentena al bajarlo: se restaura desde ahí.

## Cómo se actualiza sola

1. Se arma un instalador nuevo y se sube en el panel (Descargas → App para PC →
   Publicar una versión nueva).
2. Al abrirse (y cada 6 horas si queda abierta), la app pregunta a
   `/api/v1/app-pc/` cuál es la última. Si es más nueva que la suya, muestra el
   cartel "Hay una versión nueva" (el mismo de la APK).
3. Con "Actualizar": baja el instalador, revisa que el tamaño y la huella
   (SHA-256) sean los que dice el panel, lo corre en silencio
   (`/VERYSILENT /SUPPRESSMSGBOXES /NORESTART`) y se cierra. El instalador
   reemplaza los archivos y la vuelve a abrir. La sesión sigue.

Lo que la app baja ella misma no pasa por el aviso del navegador (Windows no lo
marca como "bajado de internet").
