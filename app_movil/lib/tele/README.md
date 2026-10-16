# lib/tele/

**"Ver en la tele"**: la app corre en el celular y usa una tele cualquiera como **segundo monitor**. En el celular se navega con el diseño de celular, y la tele muestra lo mismo con el diseño de TV (`lib/tv/`). En la tele no aparece nada más del teléfono: ni notificaciones ni otras apps mientras Kairos TV está adelante. El único control es el celular.

Sirve para teles que **no son Android**, donde no se puede instalar la app (Samsung, LG, Kanji, Hisense...). Solo hace falta que la tele acepte que el celular se le conecte como pantalla.

## Cómo se conecta

| Forma | Qué hace falta |
|---|---|
| Sin cable | Que el celular tenga **Transmitir pantalla / Smart View / Duplicar pantalla** (Miracast) y la tele lo reciba ("Screen mirroring", "Screen share"). Los dos en el mismo WiFi. Los Pixel de Google no lo traen. |
| Con cable | Un cable **USB-C a HDMI**, si el celular saca imagen por USB-C (muchos de gama media o alta). Se ve perfecto. |

El recorrido, dentro de Kairos TV: tocar el ícono de la tele de la barra de arriba (`BotonTele`) → se abre la lista de teles de Android → elegir la tele → volver a la app. Android no deja que una app se conecte sola: la tele se elige en esa lista del sistema. Si un celular no deja abrirla desde una app, el ícono explica cómo abrirla desde los accesos rápidos (Transmitir / Smart View). Con la tele conectada, el ícono queda celeste y muestra con cuál está y "Desconectar".

## Cómo funciona

```
Celular (motor de Flutter 1)                    Tele (motor de Flutter 2, en el mismo celular)
  lib/movil/ + enlace.dart  ── "estado" ──>  PantallaTele.kt ──>  en_la_tele.dart + lib/tv/
  control_remoto.dart       ── "tecla"  ──>  (Kotlin)        ──>  (como el control remoto)
                            <── "cerrada" ──                 <──
```

1. Al conectarse una tele como pantalla, Android avisa que hay una **pantalla de presentación**. `android/.../PantallaTele.kt` abre ahí una `Presentation` con un **segundo motor de Flutter**, que arranca en `pantallaTele()` (`lib/main.dart`). Ese motor dibuja la app de TV.
2. Los dos motores **no comparten memoria**. El celular no le pasa pantallas a la tele: le pasa una **descripción** de lo que está mostrando, el "estado" (`enlace.dart`): la sección de abajo y lo que abrió encima (un detalle, un reproductor, un canal en vivo). La tele se acomoda sola: abre lo que le falta y cierra lo que sobra (`EspejoTv`).
3. Lo que se **reproduce** lo reproduce la tele. En el celular, en lugar del reproductor queda el **control remoto** (`ControlRemotoTele`):
   - pausa y ±10 s;
   - flechas, OK y Atrás para las opciones de la tele (siguiente capítulo, Ajustes, subtítulos);
   - Dejar de ver.

   Los botones le llegan a la tele **como si fueran del control remoto** de un Android TV (`PantallaTele.kt` → `teclear`). Por eso los reproductores de `lib/tv/` funcionan tal cual.
4. En **En Vivo**, tocar un canal lo pone en la tele, y arriba queda `PanelEnLaTele` con anterior, siguiente, control y detener. Si la tele se desconecta, el canal sigue en el celular.

Todo pasa por `abrirPantalla` (`movil/componentes.dart`), por donde el celular abre cualquier pantalla: ahí se ve si la tele tiene que mostrarla (`Tele.abrir`). Por eso no hubo que tocar las pantallas una por una.

## Sesión, servidor y video

- La tele entra con **la misma sesión** que el celular (el token que guardó). Para el servidor es **el mismo aparato**: no ocupa otra pantalla del cliente.
- La tele pide su propio catálogo. Favoritos y "Continuar viendo" son los de la cuenta, en el servidor. La tele guarda su copia aparte en el aparato (`<cuenta>~tele`) para no pisar la del celular. Lo que se mira en la tele aparece en el celular unos segundos después.
- **El video no pasa por el servidor.** Lo baja y lo decodifica el celular, y Android se lo manda a la tele. Sin cable, la calidad depende del WiFi: puede haber un poco de demora o pixelado, y el celular gasta más batería.

## Para que ande mejor (PantallaTele.kt)

- **Calidad:** el celular baja el canal y a la vez manda la imagen a la tele por el mismo WiFi. Por eso, mientras hay tele, el video no pasa de **720p** y después de un corte junta 8 s antes de seguir (`KairosTele`, ver `paquetes/README.md`). Lo que más ayuda además: un router en **5 GHz** y el celular cerca de la tele. Con un cable USB-C a HDMI no hay ese problema.
- **Volumen:** con la tele, el sonido sale solo por la tele y depende del volumen del celular. Al conectarse lo sube al máximo, y al desconectarse lo devuelve como estaba. El volumen se maneja con el control de la tele.
- **Privacidad:** con el permiso **"Mostrar sobre otras apps"**, que se da una vez desde el ícono de la tele, la ventana de la app queda **fija en la tele**. La tele no muestra el celular ni mientras se elige la tele en los ajustes, ni al salir de la app (WhatsApp, fotos), y lo que se ve en la tele sigue andando. Sin el permiso anda igual, pero Android vuelve a mostrar el celular en la tele cuando la app no está adelante. Si el permiso se da con la tele ya conectada, la ventana pasa a ser fija al volver a la app (`alVolver`).
- **Atrás** en el Inicio del celular no cierra la app mientras hay tele: la manda al fondo (`MainActivity.popSystemNavigator`). Si se cerrara, la tele volvería a mostrar el celular.
- Lo que **no** se puede desde la app: conectarse sin abrir la función de la tele (en la Kanji, Screencast), porque la tele solo escucha mientras está abierta, y elegir la tele sin pasar por la lista de Android, porque Android no deja que una app se conecte sola.

## Archivos

| Archivo | Qué es |
|---|---|
| `enlace.dart` | `Tele`: del lado del celular. Si hay tele conectada, el estado que se le manda, las teclas del control y lo que la tele cerró sola. |
| `en_la_tele.dart` | Del lado de la tele: `iniciarTele` (arranque), `AppTele`, la pantalla de espera ("Elegí qué ver desde el celular", mientras el celular está en el login) y `EspejoTv`, que abre y cierra lo que pide el celular. Usa `PantallaTv(espejo: true)` (`lib/tv/estructura.dart`): ahí la sección la decide el celular, Atrás no sale de la app y no aparece "volver al último canal". El modo reposo sí aparece si el celular no hace nada. |
| `control_remoto.dart` | Lo que se ve en el celular: `BotonTele` (con la hoja que explica cómo conectar), `ControlRemotoTele` y `PanelEnLaTele`. |

La parte de Android está en `android/app/src/main/kotlin/.../PantallaTele.kt`. `MainActivity.kt` la arranca solo en celulares: en un Android TV no hace falta.

Tests: `test/tele_test.dart`. Simula el canal de Android, así que corre sin una tele de verdad.

## Lo que todavía no hace

- Si la tele **cambia de canal o de capítulo sola** (con su guía o con "siguiente capítulo"), el celular sigue mostrando el nombre anterior.
- Si se conecta la tele **mientras una película se está viendo en el celular**, sigue en el celular. Los canales en vivo sí pasan solos a la tele.
- Sin el permiso "Mostrar sobre otras apps", al **salir de la app** Android vuelve a mostrar el celular en la tele.
- Con la pantalla del celular **apagada o bloqueada**, la tele muestra lo que decida Android (suele ser un reloj).
- YouTube oficial en la tele usa el WebView de Android en la segunda pantalla. Si en algún celular no anda, se sabe recién probándolo.
