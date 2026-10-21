# core/

Páginas generales del sistema que no pertenecen a ningún módulo en particular.

## Propósito

- La pantalla de **inicio** (a donde llega el usuario después de iniciar sesión).
- Las **páginas de error** (403, 404, 500).
- Datos de la **marca** (nombre del sistema y de la empresa) disponibles en
  todos los templates.
- El **modo mantenimiento**.
- Las **herramientas de desarrollador**.
- El comando **`limpiar_registros`** (borra actividad y notificaciones viejas, y las sesiones de la app vencidas).

## Archivos

| Archivo | Capa | Qué contiene |
|---|---|---|
| `models.py` | Base | `EstadoMantenimiento`: una sola fila con el estado del modo mantenimiento. `Trabajo`: un trabajo pesado en curso (ver `trabajos.py`). |
| `trabajos.py` | Base | Los **trabajos pesados en curso** (probar o cargar una lista, verificar todas las fuentes, la verificación automática). Cada tanda pide su turno: si hay OTRO corriendo, espera; todos los que entran al panel, en cualquier navegador, ven arriba qué corre, quién lo empezó y cuánto va (`templates/parciales/_trabajos.html` + `static/js/trabajos.js`, que pregunta a `/sistema/trabajos/` cada 10 s). Si un trabajo deja de avisar 3 minutos (cerraron la pestaña), se da por cortado. |
| `mantenimiento.py` | Base | Lee el estado (con 5 segundos de caché) y lo guarda (registrándolo en la actividad). |
| `middleware.py` | Presentación | `ModoMantenimientoMiddleware`: si está activo, muestra "Estamos actualizando" a todos menos a los superusuarios, y les cierra la sesión a los que la tenían abierta (así el login queda libre para un superusuario). No toca `/api/`: la API responde su propio error 503 en JSON. |
| `compresion.py` | Presentación | `ComprimirMiddleware`: manda comprimidas (gzip) las páginas del panel y las respuestas JSON de la API, si quien pide lo acepta (llegan 5 a 10 veces más livianas). No toca las descargas (la APK: perdería el tamaño total y la app no podría mostrar cuánto falta) ni lo que ya viene comprimido (el catálogo, `api/v1/catalogo.py`). Es el `GZipMiddleware` de Django (con su protección contra BREACH) limitado a esos tipos. |
| `herramientas_dev.py` | Base | Las herramientas de desarrollador: estado del sistema, mail de prueba, cerrar sesiones, limpiar caché, roles, datos de demostración, borrar actividad/notificaciones, reiniciar el sistema. |
| `forms.py` | Presentación | Formulario del modo mantenimiento. |
| `views.py` | Presentación | Inicio, mantenimiento (configuración y vista previa), herramientas, páginas de error. |
| `urls.py` | Presentación | `/` (inicio), `/sistema/mantenimiento/`, `/sistema/herramientas/` y `/sistema/trabajos/` (los trabajos en curso, JSON). |
| `context_processors.py` | Presentación | Deja `NOMBRE_SISTEMA` y `NOMBRE_EMPRESA` en todos los templates (se configuran en el `.env`), los trabajos en curso (con sesión iniciada) y, a los superusuarios, si el mantenimiento está activo. |
| `management/commands/` | Técnica | `limpiar_registros` (borra actividad, notificaciones leídas viejas y sesiones de la app vencidas) y `mantenimiento` (activar/desactivar desde la terminal). |
| `tests/` | Técnica | Pruebas automáticas. |
| `templatetags/momento.py` | Presentación | `{% saludo %}` y `{% avance_dia %}`: saludo según la hora y avance del día, para el "momento" del login y del inicio. |
| `templates/core/` | Presentación | `inicio.html` (saludo, cuenta, accesos rápidos), `mantenimiento_config.html` y `herramientas.html`. |

## Qué NO va acá

- Lógica de un módulo (usuarios, clientes, ventas...): va en su propia app.
- Código reutilizable genérico: va en `herramientas/`.

## Cómo sumar un acceso rápido al inicio

En `templates/core/inicio.html`, dentro de la tarjeta "Accesos", agregar un
bloque `acceso-rapido` protegido por el permiso del módulo:

```django
{% if permisos.ver_clientes %}
<a href="{% url 'clientes:lista' %}" class="acceso-rapido">...</a>
{% endif %}
```

## Modo mantenimiento

Menú: Sistema → Mantenimiento (solo superusuarios). Se activa con un
mensaje opcional y una hora estimada de vuelta. Mientras está activo:

- Los usuarios ven "Estamos actualizando el sistema" (respuesta 503).
- Los **superusuarios** siguen usando el sistema, con un aviso arriba.
- El login y `/admin/` siguen disponibles.

También se puede **forzar desde el `.env`** con `MODO_MANTENIMIENTO=True`
(útil durante un despliegue: funciona aunque la base de datos no responda).
La pantalla de mantenimiento no consulta la base de datos, por el mismo motivo.

### Cómo se sale del modo mantenimiento

1. **Desde el sistema:** entrá con un superusuario (el login sigue
   funcionando: la pantalla de mantenimiento tiene el link "¿Sos
   administrador? Ingresar", y los demás usuarios no pueden iniciar sesión) → aviso amarillo "Cambiar", o menú Sistema → Mantenimiento →
   destildar "Activar el modo mantenimiento" → Guardar.
2. **Desde la terminal** (si no podés entrar desde el navegador):
   `python manage.py mantenimiento desactivar`. El servidor lo nota solo en
   unos segundos.
3. **Si está forzado desde el `.env`** (`MODO_MANTENIMIENTO=True`): cambiarlo
   a `False` y reiniciar el servidor. Mientras esté en `True`, 1 y 2 no lo
   apagan (la pantalla y el comando lo avisan).

## Herramientas de desarrollador

Menú: Sistema → Herramientas. **Solo superusuarios** (no se delega con roles
ni permisos). Todo lo que se hace queda en el registro de actividad.

| Grupo | Herramienta |
|---|---|
| Estado | Entorno, versiones, base de datos y su tamaño, mails, mantenimiento, cantidades. |
| Diagnóstico | Enviar mail de prueba · Limpiar la caché (desbloquea logins bloqueados). |
| Usuarios y sesiones | Cerrar todas las sesiones, en la web y en la app (menos las propias) · Sincronizar roles iniciales. |
| Demostración | Cargar / borrar usuarios `demo_*`. |
| Zona de peligro | Borrar toda la actividad · Borrar todas las notificaciones (escribiendo BORRAR) · **Reiniciar el sistema**: borra todos los datos menos los superusuarios (escribiendo REINICIAR + tu contraseña; antes muestra qué se borraría). |

Para sumar una herramienta: una función en `herramientas_dev.py`, una línea
en `HERRAMIENTAS` (`views.py`) y su tarjeta en `herramientas.html`.

## Contenido actual

Inicio, modo mantenimiento, herramientas de desarrollador, comandos, páginas de error y datos de marca.
