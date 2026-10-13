# templates/

HTML generales, compartidos por todo el sistema.

## Qué va acá

| Archivo | Qué es |
|---|---|
| `base_html.html` | Esqueleto HTML común: fuentes, Bootstrap (modo oscuro), íconos, `kairos.css` y `sistema.js`. Todos los demás lo extienden. |
| `base.html` | Layout de las pantallas **con sesión**: menú lateral + contenido. Las páginas completan `titulo`, `encabezado` y `contenido`. |
| `base_acceso.html` | Layout de las pantallas **sin sesión** (login, recuperar contraseña), como el acceso de la app: la marca a la izquierda y el formulario a la derecha. |
| `parciales/_campanita.html` | Campanita de notificaciones de la barra superior. |
| `parciales/_menu.html` | Menú lateral. Cada opción se muestra según los permisos del usuario. |
| `parciales/_mensajes.html` | Mensajes de éxito, error o aviso (`messages` de Django). |
| `parciales/_trabajos.html` | Los trabajos pesados en curso (probar o cargar una lista, verificar fuentes), arriba de todas las pantallas: se actualiza solo (`static/js/trabajos.js`, `static/css/trabajos.css`; ver `core/trabajos.py`). |
| `parciales/_campo.html` | Un campo de formulario completo (etiqueta, control, ayuda, errores): `{% include "parciales/_campo.html" with campo=form.email %}` |
| `parciales/_paginacion.html` | Paginación que conserva los filtros de la búsqueda. |
| `parciales/_avatar.html` | Foto del usuario o sus iniciales si no tiene. |
| `mantenimiento.html` | Pantalla "Estamos actualizando el sistema". Independiente (no usa la base de datos). |
| `403.html` / `404.html` / `500.html` | Páginas de error: sin permiso, no encontrada y error del servidor. |

## Cómo se arma una página nueva

```django
{% extends "base.html" %}
{% block titulo %}Clientes{% endblock %}
{% block contenido %} ... {% endblock %}
```

## Qué NO va acá

Los HTML propios de una app van dentro de esa app, en
`<app>/templates/<app>/`. Por ejemplo, `usuarios/templates/usuarios/login.html`.

## Contenido actual

Layouts, menú, parciales (mensajes, campo, paginación, avatar) y páginas de error.
