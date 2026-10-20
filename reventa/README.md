# reventa/

El **negocio de reventa** de Kairos TV: revendedores, sus clientes, los
créditos, los paquetes que se venden y las compras.

```
Revendedor 1 ──< Cliente 1 ──< Pantalla 1 ──< Dispositivo  (el aparato conectado)
     │              ├──< CreditoCliente   (su saldo: cargas + y meses −)
     │              └──< Renovacion       (cada mes de servicio)
     ├──< Movimiento      (la libreta de créditos del revendedor: + y −)
     └──< Compra >── Paquete
```

## Reglas del negocio

- **1 crédito = 1 pantalla durante 30 días.** Una pantalla es un lugar para
  UN aparato a la vez (TV, celular...).
- Un crédito comprado o regalado **no vence**: queda en el saldo hasta que
  se usa.
- **El cliente tiene su propio saldo.** Al activarlo se eligen pantallas y
  meses: se le cargan pantallas × meses créditos (3 pantallas × 10 meses =
  30) y **cada mes se descuentan solos** los de sus pantallas, hasta que no
  alcancen. Lo cargado ya está pagado: **no vuelve al revendedor** aunque el
  cliente no lo use. Con el cliente activo, "Cargar meses" suma más.
- El mes siguiente empieza pegado al anterior (o desde ahora, si ya había
  vencido). Lo hace la tarea diaria (`limpiar_registros` →
  `servicios.renovar_los_que_tocan`, que además avisa en la campanita al
  revendedor del cliente al que no le alcanza) y, por las dudas, la app y la
  ficha del cliente al usarse (`renovar_si_toca`).
- **Pantallas** (`Pantalla`): nombre ("TV habitación") y titular ("Mica
  Giménez") opcionales, para saber cuál es cuál. Con el código del cliente
  se entra a cualquier pantalla libre; una pantalla puede tener **su propio
  código** y entonces se entra a ella solo con ese. Se puede **cortar** una
  sola (su aparato se desconecta y no puede volver; se sigue pagando: es un
  castigo, no una baja), **agregar** una a mitad de mes (1 crédito, hasta
  que vence el resto; desde el mes siguiente se paga con las demás) o
  **quitarla** (sin devolución).
- **Cobrado o cortesía:** cada carga anota lo que se le cobró al cliente o
  que fue una cortesía (regalo). Sin monto, se propone el precio del
  revendedor (`precio_pantalla`, que pone él en "Mis créditos") × créditos.
- **Créditos gratis:** el administrador se los regala a un revendedor.
- **Créditos pagos:** el administrador arma paquetes (créditos + precio). El
  revendedor pide uno y queda *pendiente*. Cuando el administrador confirma
  el pago, se suman los créditos. También puede cargar una compra ya pagada.
- **Ganancia del revendedor** = lo cobrado a sus clientes − lo pagado por sus créditos.
- **El revendedor también paga lo que mira:** con su usuario del panel NO ve
  los canales en la app (la API responde `revendedor_sin_pantalla`). En el
  inicio de reventa tiene **"Mi pantalla"**: un cliente propio
  (`Cliente.propio`, `servicios.pantalla_propia`) que activa con sus créditos
  como a cualquier otro, y entra a la app con ese código. El administrador
  (`administrar_reventa`) sí ve gratis con su usuario, para probar.
- **Clientes directos:** un cliente sin revendedor es de la empresa (familia,
  pruebas). Solo lo maneja el administrador y sus créditos los pone la
  empresa. Si un día paga a través de un revendedor, se le pasa desde su
  ficha ("Pasarlo a un revendedor"; su saldo se queda con él). Con un
  cliente de revendedor, el administrador también puede elegir que los
  créditos los ponga la empresa ("Los pone la empresa").
- **Sesión única:** cada pantalla admite 1 aparato conectado. Si están todas
  ocupadas, el aparato nuevo se **bloquea** ("cuenta en uso"). Un aparato
  sin señales durante 2 horas (`HORAS_SIN_SENAL`) se libera solo; también se
  puede liberar a mano desde la ficha del cliente.

## Demos (pruebas gratis)

- Cada cliente tiene **3 demos de 1 hora** (`DEMOS_POR_CLIENTE`,
  `HORAS_POR_DEMO` en `models.py`). En la ficha de un cliente que no tiene el
  servicio pago activo, **"Dar demo"** deja elegir cuántas: 1, 2 o las 3
  juntas (3 horas seguidas). Si todavía está en una prueba, la nueva va
  después. Usadas las 3, **no hay más** (la ficha lo dice).
- **No gastan créditos** (ni del revendedor ni del cliente). Si no tiene
  pantallas, se le crea una (un aparato).
- Una prueba **no es un mes pagado**: va en `Cliente.demo_hasta`, aparte de
  `vence`; no renueva ni cuenta como "Vigente" en las estadísticas.
  `Cliente.puede_ver` (pago o prueba) es lo que mira la app para dejar
  entrar; al terminar, la app muestra "Tu prueba gratis terminó".
- La lista de clientes tiene el estado **"En prueba (demo)"** y el chip "En
  prueba hasta las HH:MM". Cada demo dada queda en `Demo` (quién, cuándo,
  cuántas) y en la actividad. Reglas en `servicios.dar_demo`; tests en
  `tests/test_demos.py`. Migración `0008_demos`.

## El saldo es una libreta

El saldo **no** es un número que se pisa: es la suma de los `Movimiento`
(+regalo, +compra, −renovación, ±ajuste). Así cada crédito tiene historia
(quién lo dio, cuándo y para qué), nada se pierde, y las estadísticas salen
solas. Todo lo que mueve créditos pasa por `servicios.py`, que bloquea la
fila del revendedor mientras trabaja: dos renovaciones al mismo tiempo no
pueden gastar el mismo crédito.

## Qué contiene

| Archivo | Capa | Para qué |
|---|---|---|
| `models.py` | Base | `Revendedor`, `Cliente` (con su código de acceso de 8 números y su saldo), `Pantalla`, `Dispositivo`, `CreditoCliente`, `Renovacion`, `Paquete`, `Compra`, `Movimiento`. |
| `servicios.py` | Base | Crear revendedores y clientes, regalar / ajustar créditos, pedir / confirmar / cancelar compras, `activar` (pantallas × meses), `cargar_meses`, el mes que empieza solo (`renovar_si_toca`, `renovar_los_que_tocan`), pantallas (`agregar_pantalla`, `quitar_pantalla`, `cortar_pantalla`, `editar_pantalla`, `codigo_de_pantalla`), `pasar_a_revendedor`, regenerar el código. |
| `consultas.py` | Base | Clientes visibles, filtros por estado, números de cada revendedor y del negocio. |
| `sesiones.py` | Base | La app de los clientes: entrar con el código (el del cliente o el propio de una pantalla), validar su token, la "señal", liberar inactivos. |
| `estadisticas.py` | Base | Mes a mes, ranking de revendedores, "ahora mismo" y los números de cada cliente. |
| `views.py`, `urls.py`, `forms.py`, `templates/` | Panel | Pantallas en `/reventa/`. |
| `admin.py` | Técnica | Vista técnica en `/admin/` (la libreta, compras y renovaciones son de solo lectura). |
| `tests/` | Técnica | Reglas del negocio y seguridad de las pantallas. |

## Quién ve qué

| Pantalla | Administrador (`administrar_reventa`) | Revendedor |
|---|---|---|
| `/reventa/` resumen | Números del negocio + compras pendientes | Sus números + clientes por vencer |
| `/reventa/clientes/` | Todos, también los directos (filtra por revendedor) | Solo los suyos |
| `/reventa/estadisticas/` | El negocio mes a mes + ranking de revendedores | Lo suyo mes a mes |
| `/reventa/creditos/` | — | Su saldo, comprar paquetes, su libreta |
| `/reventa/revendedores/` | Lista, alta, detalle, regalar / ajustar créditos | — |
| `/reventa/compras/` | Todas; confirmar pago (`confirmar_compras`) | Las suyas; cancelar las pendientes |
| `/reventa/paquetes/` | Con `gestionar_paquetes` | — |

Un revendedor **no necesita permisos**: entra porque tiene perfil de
`Revendedor`. El superusuario tiene todos los permisos. Los clientes siempre
se buscan dentro de los que el usuario puede ver: cambiar el número en la URL
da 404.

## El código de acceso del cliente

Cada cliente tiene un código fijo de 8 números (ej: `4821 9037`) para entrar
a la app. Es cómodo con el control remoto, y si cierra sesión o reinstala
vuelve a poner el mismo. Si se filtra, se genera otro desde su ficha (eso
desconecta los aparatos que entraron con él). Una pantalla puede tener su
propio código (también de 8 números, nunca repetido con otro cliente o
pantalla): sirve solo para ella. Los códigos equivocados se cuentan por
conexión: tras varios intentos, se bloquea unos minutos (igual que el login
del panel). La API está en `api/v1/cliente.py`.

## Avisos (la campanita)

- Un revendedor pide un paquete → les llega a quienes confirman pagos.
- Se confirma el pago → le llega al revendedor.

## Pendiente

- Diseño nuevo del panel (con gráficos en las estadísticas).
- Pasarela de pago (hoy todo se confirma a mano).
