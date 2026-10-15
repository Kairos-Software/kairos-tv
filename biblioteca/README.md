# biblioteca/

Lo que cada **cuenta** guarda en la app: **favoritos** ("Mi lista"),
**"Continuar viendo"** (por dónde va cada película o capítulo) y los
**últimos canales vistos**.

Hasta la app 1.2.19 esto quedaba guardado en cada aparato: si en una TV
entraba otro cliente, veía lo del anterior, y lo que se miraba en la TV no
aparecía en el celular. Desde la 1.2.20 es de la cuenta y lo ven todos sus
aparatos.

## De quién es cada cosa

| Quién entra a la app | De quién es lo guardado |
|---|---|
| Un cliente con **su código** | Del cliente: lo comparten todos sus aparatos (la TV y el celular de la casa). |
| Una pantalla con **código propio** | De esa pantalla: es otra persona (su titular), tiene lo suyo aparte. |
| Un **usuario del panel** (el administrador probando) | De ese usuario. |

Lo que es del **aparato** sigue en el aparato: qué calidad de YouTube
aguanta, qué señales fallan ahí, el modo de video, "probar igual lo que
quizá no lea" y **volver al último canal al abrir** (con el último canal que
se vio en ESE aparato: si no, la TV arrancaría en lo que alguien miró en el
celular).

## Cómo se sincroniza

- La app tiene una copia por cuenta en el aparato: abre al instante y anda
  sin internet.
- No manda listas enteras: manda **cambios** ("agregué este favorito", "voy
  por el minuto 43"), de a tandas (3 segundos después del último cambio, al
  irse la app al fondo, al volver y cada 15 minutos). Si la TV y el celular
  cambian algo a la vez, se suman: no se pisan. Si llega tarde un progreso
  más viejo (un aparato que estuvo sin internet), gana el más nuevo.
- Lo que una versión vieja había guardado en el aparato pasa, una sola vez,
  a la cuenta de quien esté conectado al actualizar.
- **"Seguir acá"**: al abrir la app, si en las últimas 6 horas se estaba
  mirando algo en OTRO aparato de la cuenta, Inicio lo ofrece arriba ("Estabas
  viendo Toy Story en la TV — Ibas por 43:10"). Una película o capítulo sigue
  en el mismo minuto; un canal, en vivo. Se puede cerrar (no vuelve a salir).

## Qué contiene

| Archivo | Para qué |
|---|---|
| `models.py` | `Favorito` (la clave como la guarda la app: `c:<id>` o `s:<serie>`), `Progreso` (canal, posición y duración en segundos, cuándo y en qué aparato) y `Visto` (canal en vivo, cuándo y dónde). Cada fila es de un cliente, de una pantalla o de un usuario: uno solo. |
| `servicios.py` | `cuenta_de(request)` (de quién es), `leer(cuenta)` y `aplicar(cuenta, cambios, aparato)` (suma los cambios; guarda hasta 500 favoritos, 60 progresos y 12 canales recientes, como la app). |
| `admin.py` | Para mirar en `/admin/` si hace falta. |
| `tests/` | Que cada cuenta vea lo suyo, que dos aparatos no se pisen y que gane el progreso más nuevo. |

La API está en `api/v1/biblioteca.py` (`GET` y `POST /api/v1/biblioteca/`).
En la app: `Biblioteca` en `app_movil/lib/movil/datos.dart`.

No se usa para estadísticas: "Lo más visto" del panel sigue sin saber
quién mira qué (ver `canales/estadisticas.py`).
