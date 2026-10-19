# lib/revision/

El **modo revisión**: este aparato recorre los canales **solo**, de a uno, y le
cuenta al servidor cuáles andan. Desde la app 1.2.30.

## Para qué

El servidor prueba las fuentes cada 6 horas, pero los paneles **Xtream
bloquean las IP de los servidores**: desde el VPS no se puede saber si andan
(quedan "Sin datos"). Desde una **casa** sí entregan la señal, como a un
cliente. Este modo hace lo mismo que probar cada canal a mano con VLC, pero
para todos y sin que nadie los mire.

## Quién lo ve y dónde

Solo un **usuario del panel** con permiso para cargar canales
(`importar_canales`), nunca un cliente:

- en el celular: **Mi Espacio → Panel de Kairos TV → Revisar canales**;
- en la TV: **Mi cuenta → Revisar canales (modo revisión)**.

Conviene dejar una TV o un celular viejo **enchufado, con internet y en esa
pantalla** (por ejemplo, de noche). Mientras recorre, la pantalla no se apaga.

## Archivos

| Archivo | Para qué |
|---|---|
| `recorrido.dart` | La lógica. `Recorrido` pide al servidor las próximas fuentes (`GET /api/v1/canales/recorrido/`, de a 20), prueba una por una con `probarConElReproductor` y cuenta lo que encontró (`POST`, de a 5). Si el aparato se queda sin internet, no lo cuenta (no es la señal): espera un minuto y sigue. Si no llega al servidor, guarda lo probado y lo manda después. `probarConElReproductor` abre la fuente con el reproductor de la app, igual que un cliente (mismas cabeceras y esperas que `movil/control_senal.dart`), sin sonido, y la da por buena si **se ve 6 segundos seguidos** (reproduciendo, sin quedarse cargando: lo mismo que el reproductor toma como "se ve"; la posición no sirve porque en vivo no avanza como en una película). Un Xtream en vivo se prueba dos veces antes de darlo por fallado. Después cierra el video del todo y espera 2 segundos antes del siguiente: hay cuentas que aceptan **una sola conexión**. |
| `pantalla_recorrido.dart` | La pantalla, igual en celular y TV: Empezar / Parar, el canal que se está probando con su video chiquito, cuántos andan y cuántos no, cuántos faltan y lo último que se probó con el motivo. |

## Qué hace el servidor con lo que encuentra

Ver `canales/recorrido.py` y la sección "Salud de las fuentes" de
`canales/README.md`:

- cada resultado se suma a la memoria de la fuente (lo que anduvo cuenta como
  visto en un aparato; lo que falló, como falla);
- si anda una fuente de un canal que había quitado la limpieza, el canal
  **vuelve a la app en el momento**;
- la misma fuente no se vuelve a pedir en 20 horas, y no se piden las que un
  cliente vio andar en las últimas 12 (no hace falta).

Primero lo **en vivo**, y dentro de eso: lo que quitó la limpieza, lo que está
fallando, lo que nadie vio nunca y lo demás. YouTube y las páginas de video no
(esas el servidor sí las puede probar). Todo se ve en el panel: Contenido →
**Para revisar**.

Pruebas: `test/recorrido_test.dart`.
